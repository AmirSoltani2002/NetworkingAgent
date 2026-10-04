"""Local meta-harness API and generic MCP client (standard library only)."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("META_HARNESS_DATA", "/data"))
DB_PATH = Path(os.environ.get("META_HARNESS_DB", str(DATA_DIR / "meta_harness.sqlite3")))
MCP_TIMEOUT = float(os.environ.get("MCP_TIMEOUT_SECONDS", "20"))
_locks: dict[str, threading.Lock] = {}
_mcp_sessions: dict[str, str] = {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return str(uuid.uuid4())


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(kind,id))")


def save(kind: str, item: dict[str, Any]) -> dict[str, Any]:
    item = dict(item)
    if kind == "server":
        for key in ("secret", "token", "password", "secret_value", "authorization"):
            item.pop(key, None)
    item.setdefault("id", uid())
    with db() as c:
        c.execute("INSERT INTO records(kind,id,body) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body", (kind, item["id"], json.dumps(item)))
    return item


def get(kind: str, ident: str) -> dict[str, Any] | None:
    with db() as c:
        row = c.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, ident)).fetchone()
    return json.loads(row[0]) if row else None


def all_records(kind: str) -> list[dict[str, Any]]:
    with db() as c:
        rows = c.execute("SELECT body FROM records WHERE kind=?", (kind,)).fetchall()
    return [json.loads(row[0]) for row in rows]


def remove(kind: str, ident: str) -> bool:
    with db() as c:
        return c.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, ident)).rowcount > 0


def error(code: str, message: str, status: int = 400, field_errors: dict | None = None) -> tuple[int, dict]:
    return status, {"code": code, "message": message, "field_errors": field_errors}


def mcp_request(server: dict[str, Any], method: str, params: dict | None = None) -> Any:
    if not server.get("enabled", True):
        raise RuntimeError("MCP server is disabled")
    endpoint = server.get("endpoint", "").strip()
    if not endpoint.startswith(("http://", "https://")):
        raise RuntimeError("MCP endpoint must be an http(s) URL")
    request_id = int(time.time() * 1000) % 2_000_000_000
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26"}
    secret_ref = server.get("secret_ref")
    token = os.environ.get(secret_ref or "", "") if secret_ref else ""
    if token:
        headers["Authorization"] = "Bearer " + token
    def exchange(message: dict, session: str | None = None) -> tuple[dict, str, int]:
        call_headers = dict(headers)
        if session: call_headers["MCP-Session-Id"] = session
        req = urllib.request.Request(endpoint, data=json.dumps(message).encode(), headers=call_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=MCP_TIMEOUT) as response:
                raw = response.read().decode("utf-8", "replace")
                if raw.lstrip().startswith("data:") or "\ndata:" in raw:
                    chunks = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:") and line[5:].strip()]
                    raw = chunks[-1] if chunks else "{}"
                return json.loads(raw or "{}"), response.headers.get("MCP-Session-Id", session or ""), response.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"MCP HTTP {exc.code}: {body}") from exc
        except Exception as exc:
            raise RuntimeError(f"MCP connection failed: {exc}") from exc

    session = _mcp_sessions.get(server["id"])
    # Establish the standard MCP session once per configured endpoint.
    if not session and method != "initialize":
        init_message = {"jsonrpc": "2.0", "id": request_id, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "local-meta-harness", "version": "1.0.0"}}}
        init_response, session, _ = exchange(init_message)
        if "error" in init_response:
            raise RuntimeError(f"MCP initialize failed: {init_response['error'].get('message', 'initialization error')}")
        _mcp_sessions[server["id"]] = session or ""
        if session:
            notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            try: exchange(notification, session)
            except RuntimeError: pass
        request_id += 1
    message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
    try:
        message, returned_session, _ = exchange(message, session)
        if returned_session: _mcp_sessions[server["id"]] = returned_session
    except json.JSONDecodeError as exc:
        raise RuntimeError("MCP returned a malformed JSON-RPC response") from exc
    if "error" in message:
        detail = message["error"]
        raise RuntimeError(f"MCP {detail.get('code', 'error')}: {detail.get('message', 'tool call failed')}")
    if "result" not in message:
        raise RuntimeError("MCP response did not contain a result")
    return message["result"]


def server_by_id(ident: str) -> dict[str, Any]:
    item = get("server", ident)
    if not item:
        raise ValueError("MCP server not found")
    return item


def tool_by_name(server: dict, name: str) -> dict | None:
    return next((t for t in server.get("tools", []) if t.get("name") == name), None)


def call_tool(server_id: str, tool_name: str, args: dict) -> Any:
    server = server_by_id(server_id)
    descriptor = tool_by_name(server, tool_name)
    if not descriptor or not descriptor.get("allowlisted"):
        raise RuntimeError(f"Tool {tool_name!r} is not allowlisted")
    return mcp_request(server, "tools/call", {"name": tool_name, "arguments": args})


def path_value(source: Any, path: str | None) -> Any:
    if not path:
        return source
    current = source
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)] if int(part) < len(current) else None
        else:
            return None
    return current


def mapped_value(mapping: dict, ctx: dict) -> Any:
    source = mapping.get("source_type", "OPERATOR_PROMPT")
    if source == "OPERATOR_PROMPT": return ctx.get("prompt", "")
    if source == "STATIC": return mapping.get("value")
    if source == "RUN_METADATA": return ctx.get("metadata", {}).get(mapping.get("source_ref", ""))
    if source in ("PRIOR_STEP", "PRIOR_STEP_FIELD"):
        value = ctx.get("outputs", {}).get(mapping.get("source_ref", ""))
        return path_value(value, mapping.get("path") if source == "PRIOR_STEP_FIELD" else None)
    if source == "ANALYZER_ANSWER": return ctx.get("answer")
    if source == "RAG_EVIDENCE": return ctx.get("evidence", [])
    if source == "EXECUTION_TRACE": return ctx.get("trace_summary", [])
    return None


def resolve_mappings(mappings: dict, ctx: dict) -> dict:
    return {key: mapped_value(value or {}, ctx) for key, value in (mappings or {}).items()}


def sanitize_trace_value(value: Any) -> Any:
    """Redact credential-like fields from persisted argument summaries."""
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if any(word in key.lower() for word in ("token", "password", "secret", "authorization", "api_key")) else sanitize_trace_value(item)) for key, item in value.items()}
    if isinstance(value, list): return [sanitize_trace_value(item) for item in value]
    return value


def validate_workflow(wf: dict) -> list[str]:
    problems: list[str] = []
    produced: set[str] = set()
    for i, step in enumerate(wf.get("steps", [])):
        if not step.get("enabled", True): continue
        server = get("server", step.get("server_id", ""))
        if not server:
            problems.append(f"Step {i+1}: MCP server is missing")
        else:
            descriptor = tool_by_name(server, step.get("tool_name", ""))
            if not descriptor or not descriptor.get("allowlisted"):
                problems.append(f"Step {i+1}: selected tool is missing or not allowlisted")
            else:
                required = descriptor.get("input_schema", {}).get("required", [])
                mappings = step.get("input_mappings", {}) or {}
                for argument in required:
                    if not mappings.get(argument, {}).get("source_type"):
                        problems.append(f"Step {i+1}: required argument {argument!r} needs an explicit input mapping")
        if not step.get("output_name"): problems.append(f"Step {i+1}: output name is required")
        for arg, mapping in (step.get("input_mappings") or {}).items():
            m = mapping or {}
            if m.get("source_type") in ("PRIOR_STEP", "PRIOR_STEP_FIELD") and m.get("source_ref") not in produced:
                problems.append(f"Step {i+1}: {arg} references unavailable prior output {m.get('source_ref')!r}")
        if step.get("output_name"): produced.add(step["output_name"])
    return problems


def openai_analyze(profile: dict, prompt: str, ml_outputs: dict, evidence: Any) -> str:
    base = profile.get("base_url") or os.environ.get("ANALYZER_BASE_URL", "https://api.openai.com/v1")
    model = profile.get("model", "")
    if not model: raise RuntimeError("Analyzer model identifier is required")
    url = base.rstrip("/") + "/chat/completions"
    key = os.environ.get(profile.get("secret_ref") or "", "") if profile.get("secret_ref") else os.environ.get("ANALYZER_API_KEY", "")
    system = profile.get("instructions") or "Answer the operator using the supplied context. Clearly distinguish retrieved evidence from model inference."
    context = {"operator_prompt": prompt, "workflow_outputs": ml_outputs, "retrieved_evidence": evidence}
    body = json.dumps({"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]}).encode()
    headers = {"Content-Type": "application/json"}
    if key: headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as response: data = json.loads(response.read())
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"Analyzer call failed: {exc}") from exc


def run_workflow(run_id: str) -> None:
    run = get("run", run_id)
    if not run: return
    run["status"] = "RUNNING"; run["started_at"] = now(); save("run", run)
    trace: list[dict] = []
    ctx = {"prompt": run["operator_prompt"], "metadata": {"run_id": run_id}, "outputs": {}, "evidence": []}
    start_all = time.monotonic()

    def step_trace(kind: str, server_id: str | None, tool_name: str | None, input_value: Any, output_name: str | None = None):
        started = now(); t0 = time.monotonic()
        item = {"id": uid(), "run_id": run_id, "sequence": len(trace)+1, "kind": kind, "server_id": server_id, "tool_name": tool_name, "started_at": started, "finished_at": None, "status": "RUNNING", "sanitized_input": sanitize_trace_value(input_value), "normalized_output": None, "error": None, "output_name": output_name, "duration_ms": None}
        trace.append(item); save("trace", item)
        return item, t0

    def finish(item: dict, t0: float, status: str, output: Any = None, err: str | None = None):
        item.update(finished_at=now(), status=status, normalized_output=output, error=err, duration_ms=round((time.monotonic()-t0)*1000, 2)); save("trace", item)

    try:
        wf = run.get("workflow_snapshot") or get("workflow", run["workflow_id"])
        analyzer = run.get("analyzer_snapshot") or get("analyzer", run["analyzer_profile_id"])
        validator = run.get("validator_snapshot") or (get("validator", run.get("validator_profile_id")) if run.get("validator_profile_id") else None)
        if not wf or not analyzer: raise RuntimeError("Workflow or analyzer profile no longer exists")
        run["workflow_version"] = wf.get("version", 1); save("run", run)
        problems = validate_workflow(wf)
        if problems: raise RuntimeError("Workflow invalid: " + "; ".join(problems))
        for step in wf.get("steps", []):
            if not step.get("enabled", True):
                item, t0 = step_trace("ML_MCP", step.get("server_id"), step.get("tool_name"), {}, step.get("output_name")); finish(item, t0, "SKIPPED"); continue
            args = resolve_mappings(step.get("input_mappings", {}), ctx)
            item, t0 = step_trace("ML_MCP", step["server_id"], step["tool_name"], args, step.get("output_name"))
            try:
                result = call_tool(step["server_id"], step["tool_name"], args)
                ctx["outputs"][step["output_name"]] = result; finish(item, t0, "SUCCESS", result)
            except Exception as exc:
                finish(item, t0, "ERROR", err=str(exc)); raise RuntimeError(f"ML step {step.get('name') or step['tool_name']} failed: {exc}") from exc
        rag_profile = get("rag", analyzer.get("rag_profile_id")) if analyzer.get("enable_rag") and analyzer.get("rag_profile_id") else None
        if rag_profile:
            args = resolve_mappings(rag_profile.get("retrieval_argument_mappings", {}), {**ctx, "metadata": {**ctx["metadata"], "collection": rag_profile.get("collection")}})
            if "collection" not in args: args["collection"] = rag_profile.get("collection", "")
            item, t0 = step_trace("RAG_MCP", rag_profile["server_id"], rag_profile["retrieval_tool"], args)
            try:
                raw = call_tool(rag_profile["server_id"], rag_profile["retrieval_tool"], args)
                ctx["evidence"] = raw.get("content", raw) if isinstance(raw, dict) else raw
                run["rag_evidence"] = ctx["evidence"]; finish(item, t0, "SUCCESS", raw)
                evidence = raw.get("content", raw) if isinstance(raw, dict) else raw
                save("evidence", {"id": uid(), "run_id": run_id, "source_kind": "RAG", "source_ref": rag_profile.get("collection", ""), "summary": "Retrieved by configured RAG MCP tool", "payload_or_reference": evidence, "created_at": now()})
            except Exception as exc:
                finish(item, t0, "ERROR", err=str(exc)); raise RuntimeError(f"RAG retrieval failed: {exc}") from exc
        else: run["rag_evidence"] = []
        analyzer_input = {"operator_prompt": run["operator_prompt"], "workflow_outputs": ctx["outputs"], "retrieved_evidence": ctx["evidence"]}
        item, t0 = step_trace("ANALYZER", None, analyzer.get("adapter", "openai-compatible"), {"context_summary": analyzer_input})
        try:
            answer = openai_analyze(analyzer, run["operator_prompt"], ctx["outputs"], ctx["evidence"])
            ctx["answer"] = answer; run["analyzer_answer"] = answer; finish(item, t0, "SUCCESS", answer)
        except Exception as exc:
            finish(item, t0, "ERROR", err=str(exc)); raise
        if validator:
            ctx["trace_summary"] = [{"sequence": t["sequence"], "kind": t["kind"], "status": t["status"], "tool_name": t["tool_name"]} for t in trace]
            args = resolve_mappings(validator.get("input_mappings", {}), ctx)
            item, t0 = step_trace("VALIDATOR_MCP", validator["server_id"], validator["tool_name"], args)
            try:
                result = call_tool(validator["server_id"], validator["tool_name"], args)
                run["validator_result"] = result; finish(item, t0, "SUCCESS", result)
            except Exception as exc:
                run["validator_error"] = str(exc); finish(item, t0, "ERROR", err=str(exc))
        run["status"] = "COMPLETED"; run["duration_ms"] = round((time.monotonic()-start_all)*1000, 2)
    except Exception as exc:
        run["status"] = "FAILED"; run["error_summary"] = str(exc); run["duration_ms"] = round((time.monotonic()-start_all)*1000, 2)
    finally:
        run["finished_at"] = now(); save("run", run)


def sanitize_server(server: dict) -> dict:
    result = dict(server)
    result.pop("secret_value", None)
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "MetaHarnessCore/1.0"
    def log_message(self, fmt: str, *args: Any) -> None: print("core:", fmt % args)
    def send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body)))
        if os.environ.get("UI_ORIGIN"):
            self.send_header("Access-Control-Allow-Origin", os.environ["UI_ORIGIN"]); self.send_header("Access-Control-Allow-Headers", "Content-Type"); self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
        self.end_headers(); self.wfile.write(body)
    def body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0)); return json.loads(self.rfile.read(n) or b"{}")
    def do_OPTIONS(self) -> None: self.send_json(204, {})
    def do_GET(self) -> None: self.route("GET")
    def do_POST(self) -> None: self.route("POST")
    def do_PUT(self) -> None: self.route("PUT")
    def do_PATCH(self) -> None: self.route("PATCH")
    def do_DELETE(self) -> None: self.route("DELETE")

    def route(self, method: str) -> None:
        p = self.path.split("?", 1)[0].rstrip("/")
        parts = p.split("/")[1:]
        try:
            result = self.dispatch(method, parts)
            if isinstance(result, tuple): status, data = result
            else: status, data = 200, result
            self.send_json(status, data)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self.send_json(400, {"code": "INVALID_REQUEST", "message": str(exc), "field_errors": None})
        except Exception as exc:
            self.send_json(500, {"code": "INTERNAL_ERROR", "message": str(exc), "field_errors": None})

    def dispatch(self, method: str, p: list[str]) -> Any:
        if p == ["health"]: return {"status": "ok"}
        if len(p) >= 2 and p[0] == "api":
            resource = p[1]
            kinds = {"servers":"server", "workflows":"workflow", "profiles":"rag", "documents":"document", "analyzers":"analyzer", "validators":"validator", "runs":"run"}
            if resource == "mcp" and len(p) >= 3 and p[2] == "servers": return self.server_routes(method, p[3:])
            if resource == "rag" and len(p) >= 3 and p[2] == "profiles": return self.collection_routes(method, "rag", p[3:])
            if resource not in kinds: return error("NOT_FOUND", "Route not found", 404)
            kind = kinds[resource]; tail = p[2:]
            if resource == "workflows": return self.workflow_routes(method, tail)
            if resource == "runs": return self.run_routes(method, tail)
            if resource == "documents" and tail and len(tail) == 2 and tail[1] == "ingest" and method == "POST": return self.ingest(tail[0])
            return self.collection_routes(method, kind, tail)
        return error("NOT_FOUND", "Route not found", 404)

    def server_routes(self, method: str, tail: list[str]) -> Any:
        if not tail:
            if method == "GET": return [sanitize_server(x) for x in all_records("server")]
            if method == "POST":
                x = self.body(); x.update(id=uid(), created_at=now(), updated_at=now()); x.setdefault("tools", []); x.setdefault("enabled", True); x.setdefault("metadata", {}); x["transport"] = x.get("transport", "streamable-http"); return sanitize_server(save("server", x))
        ident = tail[0]; x = get("server", ident)
        if not x: return error("NOT_FOUND", "MCP server not found", 404)
        if len(tail) == 1:
            if method == "GET": return sanitize_server(x)
            if method == "PATCH": x.update(self.body()); x["updated_at"] = now(); return sanitize_server(save("server", x))
            if method == "DELETE": remove("server", ident); return {"deleted": True}
            if method == "POST": return error("METHOD_NOT_ALLOWED", "Unsupported action", 405)
        action = tail[1]
        if action == "test" and method == "POST":
            try: result = mcp_request(x, "ping", {}); return {"connected": True, "result": result}
            except Exception as exc: return {"connected": False, "error": str(exc)}
        if action == "discover" and method == "POST":
            try:
                result = mcp_request(x, "tools/list", {})
                existing = {t.get("name"): t.get("allowlisted", False) for t in x.get("tools", [])}
                x["tools"] = [{"name": t["name"], "description": t.get("description", ""), "input_schema": t.get("inputSchema", {}), "last_discovered_at": now(), "allowlisted": existing.get(t["name"], False)} for t in result.get("tools", [])]
                save("server", x); return sanitize_server(x)
            except Exception as exc: return {"discovered": False, "error": str(exc)}
        if action == "tools" and len(tail) >= 3 and method == "PATCH":
            name = tail[2]; body = self.body(); tool = tool_by_name(x, name)
            if not tool: return error("NOT_FOUND", "Tool not discovered", 404)
            tool["allowlisted"] = bool(body.get("allowlisted")); save("server", x); return tool
        return error("NOT_FOUND", "Route not found", 404)

    def workflow_routes(self, method: str, tail: list[str]) -> Any:
        if not tail:
            if method == "GET": return all_records("workflow")
            if method == "POST":
                x=self.body(); x.update(id=uid(), version=1, enabled=x.get("enabled", True), created_at=now(), updated_at=now()); x.setdefault("steps", []); return save("workflow", x)
        ident=tail[0]; x=get("workflow",ident)
        if not x: return error("NOT_FOUND", "Workflow not found", 404)
        if len(tail)==1:
            if method=="GET": return x
            if method=="PUT":
                y=self.body(); y.update(id=ident, version=x.get("version",1)+1, created_at=x.get("created_at"), updated_at=now()); return save("workflow", y)
        if len(tail)==2 and tail[1]=="validate" and method=="POST":
            problems=validate_workflow(x); return {"valid": not problems, "errors": problems}
        if len(tail)==2 and tail[1]=="duplicate" and method=="POST":
            y=dict(x); y.update(id=uid(),name=x["name"]+" copy",version=1,created_at=now(),updated_at=now()); return save("workflow", y)
        return error("NOT_FOUND", "Route not found", 404)

    def collection_routes(self, method: str, kind: str, tail: list[str]) -> Any:
        if not tail:
            if method=="GET": return all_records(kind)
            if method=="POST":
                x=self.body(); x.update(id=uid(),created_at=now(),updated_at=now()); return save(kind,x)
        ident=tail[0]; x=get(kind,ident)
        if not x: return error("NOT_FOUND", f"{kind} not found",404)
        if len(tail)==1:
            if method=="GET": return x
            if method in ("PUT","PATCH"):
                y=self.body(); y.update(id=ident,created_at=x.get("created_at"),updated_at=now()); return save(kind,y)
            if method=="DELETE": remove(kind,ident); return {"deleted":True}
        return error("NOT_FOUND", "Route not found",404)

    def ingest(self, document_id: str) -> Any:
        doc=get("document",document_id)
        if not doc: return error("NOT_FOUND","Document not found",404)
        profile=get("rag",doc.get("rag_profile_id"))
        if not profile or not profile.get("ingest_tool"): return error("INGEST_UNAVAILABLE","Assigned RAG profile has no ingestion tool",400)
        args={"title":doc.get("title"),"local_reference":doc.get("local_reference"),"description":doc.get("description"),"tags":doc.get("tags",[]),"collection":profile.get("collection")}
        try:
            result=call_tool(profile["server_id"],profile["ingest_tool"],args); doc["status"]="REGISTERED"; doc["ingest_result"]=result; save("document",doc); return {"status":"REGISTERED","result":result}
        except Exception as exc: doc["status"]="INGEST_ERROR"; doc["ingest_error"]=str(exc); save("document",doc); return error("MCP_ERROR",str(exc),502)

    def run_routes(self, method: str, tail: list[str]) -> Any:
        if not tail:
            if method=="GET": return sorted(all_records("run"),key=lambda x:x.get("started_at",x.get("created_at","")),reverse=True)
            if method=="POST":
                x=self.body()
                wf=get("workflow",x.get("workflow_id","")); an=get("analyzer",x.get("analyzer_profile_id",""))
                if not wf or not an: return error("CONFIG_NOT_FOUND","Workflow and analyzer profile are required",400)
                problems=validate_workflow(wf)
                if problems:return error("WORKFLOW_INVALID","Workflow validation failed",422,{"steps":problems})
                validator_profile = get("validator", x.get("validator_profile_id")) if x.get("validator_profile_id") else None
                x.update(id=uid(),status="PENDING",created_at=now(),started_at=None,finished_at=None,workflow_version=wf.get("version",1),workflow_snapshot=wf,analyzer_snapshot=an,validator_snapshot=validator_profile,rag_evidence=[],analyzer_answer=None,validator_result=None)
                save("run",x); threading.Thread(target=run_workflow,args=(x["id"],),daemon=True).start(); return 202,x
        ident=tail[0]; x=get("run",ident)
        if not x:return error("NOT_FOUND","Run not found",404)
        if len(tail)==1 and method=="GET": return x
        if len(tail)==2 and tail[1]=="trace" and method=="GET": return sorted([t for t in all_records("trace") if t.get("run_id")==ident],key=lambda t:t["sequence"])
        if len(tail)==2 and tail[1]=="cancel" and method=="POST":
            if x["status"] in ("PENDING","RUNNING"): x["cancel_requested"]=True; save("run",x); return {"cancel_requested":True,"supported":False}
        return error("NOT_FOUND","Route not found",404)


def main() -> None:
    init_db()
    host=os.environ.get("CORE_HOST","0.0.0.0"); port=int(os.environ.get("CORE_PORT","8000"))
    print(f"Meta-harness core listening on {host}:{port}; database {DB_PATH}")
    ThreadingHTTPServer((host,port),Handler).serve_forever()


if __name__=="__main__": main()
