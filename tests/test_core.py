import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

from core import server as core


CALLS = []
ANALYZER_CONTEXTS = []


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def send_json(self, data, status=200, session=False):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if session: self.send_header("MCP-Session-Id", "fixture-session")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        req = json.loads(self.rfile.read(n) or b"{}")
        method = req.get("method")
        if self.path == "/analyzer/v1/chat/completions":
            data = req["messages"][1]["content"]
            context = json.loads(data)
            ANALYZER_CONTEXTS.append(context)
            self.send_json({"choices":[{"message":{"content":"Candidate answer using configured context."}}]})
            return
        if method == "initialize":
            self.send_json({"jsonrpc":"2.0","id":req["id"],"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"fixture","version":"1"}}}, session=True)
        elif method == "notifications/initialized":
            self.send_response(202); self.end_headers()
        elif method == "ping":
            self.send_json({"jsonrpc":"2.0","id":req["id"],"result":{}})
        elif method == "tools/list":
            names = ["enrich_a", "enrich_b", "retrieve", "validate", "ingest", "unlisted"]
            self.send_json({"jsonrpc":"2.0","id":req["id"],"result":{"tools":[{"name":name,"description":"fixture tool","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"prior":{"type":"object"},"collection":{"type":"string"},"answer":{"type":"string"},"evidence":{}},"required":[]}} for name in names]}})
        elif method == "tools/call":
            name=req["params"]["name"]; args=req["params"].get("arguments",{}); CALLS.append((name,args))
            outputs={
                "enrich_a":{"stage":"a","query":args.get("query")},
                "enrich_b":{"stage":"b","prior":args.get("prior")},
                "retrieve":{"content":[{"text":"retrieved evidence"}],"collection":args.get("collection")},
                "validate":{"valid":True,"checked_answer":args.get("answer")},
                "ingest":{"registered":True},
                "unlisted":{"unexpected":True},
            }
            self.send_json({"jsonrpc":"2.0","id":req["id"],"result":outputs[name]})
        else:
            self.send_json({"jsonrpc":"2.0","id":req.get("id"),"error":{"code":-32601,"message":"method not found"}})


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        core.DB_PATH = core.Path(cls.temp.name) / "test.sqlite3"
        core._mcp_sessions.clear()
        core.init_db()
        cls.fixture = ThreadingHTTPServer(("127.0.0.1",0),FixtureHandler)
        cls.fixture_thread = threading.Thread(target=cls.fixture.serve_forever,daemon=True); cls.fixture_thread.start()
        cls.core_http = ThreadingHTTPServer(("127.0.0.1",0),core.Handler)
        cls.core_thread=threading.Thread(target=cls.core_http.serve_forever,daemon=True); cls.core_thread.start()
        cls.base=f"http://127.0.0.1:{cls.core_http.server_port}/api"
        cls.fixture_url=f"http://127.0.0.1:{cls.fixture.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.core_http.shutdown(); cls.fixture.shutdown(); cls.temp.cleanup()

    def request(self, path, method="GET", body=None):
        payload=json.dumps(body).encode() if body is not None else None
        req=Request(self.base+path,data=payload,method=method,headers={"Content-Type":"application/json"})
        with urlopen(req,timeout=5) as response:
            return response.status,json.loads(response.read() or b"null")

    def create_server(self,name,category,allow):
        _,s=self.request("/mcp/servers","POST",{"name":name,"category":category,"endpoint":self.fixture_url,"secret_ref":"TEST_TOKEN","secret_value":"raw-never-save-me"})
        self.assertNotIn("secret_value",s); self.assertNotIn("raw-never-save-me",json.dumps(s))
        _,d=self.request(f"/mcp/servers/{s['id']}/discover","POST",{})
        self.assertEqual(len(d["tools"]),6)
        for tool in allow:
            _,desc=self.request(f"/mcp/servers/{s['id']}/tools/{tool}","PATCH",{"allowlisted":True})
            self.assertTrue(desc["allowlisted"])
        return s

    def test_end_to_end_configured_workflow(self):
        CALLS.clear(); ANALYZER_CONTEXTS.clear(); core._mcp_sessions.clear()
        a=self.create_server("ML A","ML",["enrich_a"])
        b=self.create_server("ML B","ML",["enrich_b"])
        rag=self.create_server("RAG","RAG",["retrieve","ingest"])
        validator=self.create_server("Validator","VALIDATOR",["validate"])
        _,wf=self.request("/workflows","POST",{"name":"A then B","steps":[
            {"name":"A","server_id":a["id"],"tool_name":"enrich_a","enabled":True,"output_name":"first","input_mappings":{"query":{"source_type":"OPERATOR_PROMPT"}}},
            {"name":"B","server_id":b["id"],"tool_name":"enrich_b","enabled":True,"output_name":"second","input_mappings":{"prior":{"source_type":"PRIOR_STEP","source_ref":"first"}}},
            {"name":"Disabled","server_id":a["id"],"tool_name":"enrich_a","enabled":False,"output_name":"disabled","input_mappings":{}},
        ]})
        _,ragp=self.request("/rag/profiles","POST",{"name":"Docs","server_id":rag["id"],"retrieval_tool":"retrieve","ingest_tool":"ingest","collection":"ops-v1","retrieval_argument_mappings":{"query":{"source_type":"OPERATOR_PROMPT"}}})
        _,doc=self.request("/documents","POST",{"title":"Runbook","local_reference":"/tmp/runbook.md","rag_profile_id":ragp["id"],"rag_server_id":rag["id"],"rag_collection":"ops-v1","status":"MAPPED"})
        status,ingest=self.request(f"/documents/{doc['id']}/ingest","POST",{})
        self.assertEqual(status,200); self.assertEqual(ingest["status"],"REGISTERED")
        _,an=self.request("/analyzers","POST",{"name":"Test analyzer","adapter":"openai-compatible","model":"fixture-model","base_url":self.fixture_url+"/analyzer/v1","enable_rag":True,"rag_profile_id":ragp["id"],"instructions":"Use supplied context."})
        _,vp=self.request("/validators","POST",{"name":"Test validator","server_id":validator["id"],"tool_name":"validate","input_mappings":{"answer":{"source_type":"ANALYZER_ANSWER"},"evidence":{"source_type":"RAG_EVIDENCE"}}})
        status,run=self.request("/runs","POST",{"workflow_id":wf["id"],"analyzer_profile_id":an["id"],"validator_profile_id":vp["id"],"operator_prompt":"Check route reachability"})
        self.assertEqual(status,202)
        deadline=time.time()+8
        while time.time()<deadline:
            _,run=self.request(f"/runs/{run['id']}")
            if run["status"] in ("COMPLETED","FAILED"): break
            time.sleep(.03)
        self.assertEqual(run["status"],"COMPLETED",run.get("error_summary"))
        names=[name for name,_ in CALLS]
        self.assertLess(names.index("enrich_a"),names.index("enrich_b"))
        self.assertLess(names.index("enrich_b"),names.index("retrieve"))
        self.assertLess(names.index("retrieve"),names.index("validate"))
        b_args=next(args for name,args in CALLS if name=="enrich_b")
        self.assertEqual(b_args["prior"]["stage"],"a")
        self.assertEqual(ANALYZER_CONTEXTS[-1]["operator_prompt"],"Check route reachability")
        self.assertEqual(ANALYZER_CONTEXTS[-1]["workflow_outputs"]["second"]["stage"],"b")
        self.assertEqual(ANALYZER_CONTEXTS[-1]["retrieved_evidence"][0]["text"],"retrieved evidence")
        self.assertEqual(run["analyzer_answer"],"Candidate answer using configured context.")
        self.assertTrue(run["validator_result"]["valid"])
        _,trace=self.request(f"/runs/{run['id']}/trace")
        self.assertEqual([t["sequence"] for t in trace],list(range(1,len(trace)+1)))
        self.assertTrue(all(t["duration_ms"] is not None for t in trace))
        self.assertTrue(any(t["status"]=="SKIPPED" for t in trace))
        self.assertEqual(run["workflow_version"],1)
        # A later edit advances the workflow but cannot alter the captured run config.
        _,changed=self.request(f"/workflows/{wf['id']}","PUT",{**wf,"name":"Edited afterward"})
        self.assertEqual(changed["version"],2)
        _,stored_run=self.request(f"/runs/{run['id']}")
        self.assertEqual(stored_run["workflow_snapshot"]["name"],"A then B")

    def test_workflow_rejects_missing_prior_output_and_allowlist(self):
        s=self.create_server("No allowed calls","ML",[])
        wf={"steps":[{"server_id":s["id"],"tool_name":"unlisted","output_name":"x","input_mappings":{"x":{"source_type":"PRIOR_STEP","source_ref":"missing"}}}]}
        problems=core.validate_workflow(wf)
        self.assertTrue(any("not allowlisted" in p for p in problems))
        self.assertTrue(any("unavailable prior output" in p for p in problems))

    def test_server_failures_return_structured_api_result(self):
        _,s=self.request("/mcp/servers","POST",{"name":"unreachable","category":"ML","endpoint":"http://127.0.0.1:1/mcp"})
        _,result=self.request(f"/mcp/servers/{s['id']}/test","POST",{})
        self.assertFalse(result["connected"])
        self.assertIn("MCP connection failed",result["error"])

    def test_server_edit_and_ingest_unavailable_without_configured_tool(self):
        s=self.create_server("Editable RAG","RAG",["retrieve"])
        _,edited=self.request(f"/mcp/servers/{s['id']}","PATCH",{"name":"Renamed RAG","enabled":False})
        self.assertEqual(edited["name"],"Renamed RAG")
        self.assertFalse(edited["enabled"])
        self.assertNotIn("secret_value",json.dumps(edited))
        _,profile=self.request("/rag/profiles","POST",{"name":"No ingest","server_id":s["id"],"retrieval_tool":"retrieve","collection":"docs"})
        _,doc=self.request("/documents","POST",{"title":"Metadata only","local_reference":"/tmp/doc","rag_profile_id":profile["id"]})
        try:
            self.request(f"/documents/{doc['id']}/ingest","POST",{})
            self.fail("ingest should reject profiles without an external ingest tool")
        except Exception as exc:
            self.assertIn("HTTP Error 400",str(exc))


if __name__ == "__main__": unittest.main()
