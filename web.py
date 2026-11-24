"""Read-only demo UI; each GET uses a fresh temporary SQLite database."""
import argparse
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from urllib.parse import parse_qs, urlsplit

from demo import run_demo


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if parsed.path not in {"/", "/api/demo"}:
            self.send_error(404)
            return
        parameters = parse_qs(parsed.query)
        query = parameters.get("query", ["vegetarian dinner Kyoto"])[0]
        person = parameters.get("person", ["traveler"])[0]
        if not query.strip() or len(query) > 500 or person not in {"traveler", "other-person"}:
            self.send_error(400, "Use a nonempty query of at most 500 characters and a demo identity")
            return
        with tempfile.TemporaryDirectory() as folder:
            result = run_demo(Path(folder) / "memory.sqlite", query, person)
        if parsed.path == "/api/demo":
            body, mime = json.dumps(result, indent=2), "application/json"
        else:
            rows = "".join("<tr><td>" + escape(x["record"]["type"]) + "</td><td>" +
                           escape(x["record"]["content"][0]["text"]) + "</td><td>" +
                           escape(x["record"]["written_by"]["id"]) + "</td><td>untrusted</td></tr>"
                           for x in result["result"]["recall"]["results"])
            selected = lambda x: " selected" if person == x else ""
            body = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cross-harness memory</title><style>body{font:17px system-ui;background:#f2f5f6;color:#172c36;margin:auto;max-width:1050px;padding:40px}h1{font-size:42px}main,aside{background:white;padding:24px;border-radius:14px;margin:20px 0}small{color:#4d6572}label{display:block;margin:14px 0 5px}input,select,button{font:inherit;padding:10px;border:1px solid #a6bbc4;border-radius:6px}input{width:65%}button{background:#166c65;color:white}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:14px;border-bottom:1px solid #d4e0e5}pre{overflow:auto;background:#142e39;color:#e1f0f2;padding:20px;border-radius:8px}.flow{padding:15px;background:#e0f1ed}</style>
<h1>Memory follows the person</h1><p>A fresh harness can recall preferences another harness kept. Each person has an isolated memory root.</p>
<div class="flow">Claude Code session → private SQLite memory → fresh Codex session</div>
<main><h2>Try the handoff</h2><small>Offline deterministic demonstration. No model, provider, account, or external service is called.</small>
<form><label for="person">Synthetic identity</label><select id="person" name="person"><option value="traveler"''' + selected("traveler") + '''>Traveler</option><option value="other-person"''' + selected("other-person") + '''>Other person</option></select>
<label for="query">Per-turn memory search</label><input id="query" name="query" maxlength="500" value="''' + escape(query, quote=True) + '''" required> <button>Recall memory</button></form>
<h3>Fresh Codex session result</h3><p>''' + escape(result["result"]["answer"]) + '''</p>
<table><thead><tr><th>Type</th><th>Recalled data</th><th>Writer</th><th>Trust</th></tr></thead><tbody>''' + (rows or '<tr><td colspan="4">No matching memory. The demo abstains.</td></tr>') + '''</tbody></table></main>
<aside><h2>Session lifecycle</h2><ol><li>Prime standing preferences once at session start.</li><li>Search the bound private root before each turn.</li><li>Pass JSON records as tool data with provenance.</li><li>Observe the completed question and answer as an episode.</li></ol><p>Structured data is a boundary, not a guarantee that a language model resists prompt injection. No model is used here.</p>
<details><summary>Inspect lifecycle evidence</summary><pre>''' + escape(json.dumps(result, indent=2)) + '''</pre></details></aside></html>'''
            mime = "text/html"
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(encoded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8885)
    args = parser.parse_args()
    print(f"Memory preview: http://127.0.0.1:{args.port}/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
