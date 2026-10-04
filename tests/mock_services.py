"""Development-only MCP and OpenAI-compatible fixtures for manual UI demos."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


TOOLS = [
    {"name":"enrich_summary","description":"Return a mock enrichment result","inputSchema":{"type":"object","properties":{"prompt":{"type":"string"}},"required":["prompt"]}},
    {"name":"search_documents","description":"Return mock retrieved evidence","inputSchema":{"type":"object","properties":{"query":{"type":"string"},"collection":{"type":"string"}},"required":["query"]}},
    {"name":"validate_candidate","description":"Return a mock validation result","inputSchema":{"type":"object","properties":{"answer":{"type":"string"},"evidence":{}},"required":["answer"]}},
    {"name":"register_document","description":"Record mock external document registration","inputSchema":{"type":"object","properties":{"title":{"type":"string"},"local_reference":{"type":"string"}},"required":["title"]}},
]


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): print("mock:", fmt % args)
    def respond(self, payload, status=200, session=False):
        body=json.dumps(payload).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body)))
        if session:self.send_header("MCP-Session-Id","meta-harness-demo")
        self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))) or b"{}")
        if self.path.endswith("/chat/completions"):
            context=json.loads(request["messages"][1]["content"])
            answer="Demo analyzer candidate: " + context.get("operator_prompt", "")
            return self.respond({"choices":[{"message":{"content":answer}}]})
        method=request.get("method"); params=request.get("params",{})
        if method=="initialize":return self.respond({"jsonrpc":"2.0","id":request["id"],"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"demo-mcp-fixture","version":"1"}}},session=True)
        if method=="notifications/initialized":return self.respond({},202)
        if method=="ping":return self.respond({"jsonrpc":"2.0","id":request["id"],"result":{}})
        if method=="tools/list":return self.respond({"jsonrpc":"2.0","id":request["id"],"result":{"tools":TOOLS}})
        if method=="tools/call":
            name=params.get("name"); args=params.get("arguments",{})
            if name=="enrich_summary":result={"summary":"Mock enrichment for: "+args.get("prompt","")}
            elif name=="search_documents":result={"content":[{"text":"Demo retrieved evidence for: "+args.get("query","")}],"collection":args.get("collection")}
            elif name=="validate_candidate":result={"valid":True,"note":"Demo validator accepted the candidate.","candidate":args.get("answer")}
            elif name=="register_document":result={"registered":True,"title":args.get("title")}
            else:return self.respond({"jsonrpc":"2.0","id":request["id"],"error":{"code":-32601,"message":"unknown tool"}})
            return self.respond({"jsonrpc":"2.0","id":request["id"],"result":result})
        return self.respond({"jsonrpc":"2.0","id":request.get("id"),"error":{"code":-32601,"message":"unknown method"}})


if __name__=="__main__":
    mcp=ThreadingHTTPServer(("0.0.0.0",9000),FixtureHandler)
    analyzer=ThreadingHTTPServer(("0.0.0.0",9001),FixtureHandler)
    threading.Thread(target=analyzer.serve_forever,daemon=True).start()
    print("Development fixtures: MCP http://localhost:9000/mcp; analyzer http://localhost:9001/v1")
    mcp.serve_forever()
