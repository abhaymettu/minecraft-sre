"""127.0.0.1 HTTP bridge so the MCP shim (a child of `claude -p`) can reach the episode's ToolHost."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve(host):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send({"tools": host.specs()})

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            text, err = host.call(req["name"], req.get("arguments"))
            self._send({"text": text, "is_error": err})

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"
