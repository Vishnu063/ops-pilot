"""Single-owner loopback dashboard. No shell-command or remote-target input API."""
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import os
from urllib.parse import parse_qs, urlsplit


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, pilot, port=8767, ingest_token=None):
        self.pilot = pilot
        if ingest_token is not None and (len(ingest_token) < 32 or not ingest_token.isascii() or any(c.isspace() for c in ingest_token)):
            raise ValueError("Ingest token needs at least 32 non-whitespace ASCII characters")
        self.ingest_token = ingest_token
        self.token = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), Handler)
        self.origins = {f"http://127.0.0.1:{self.server_port}", f"http://localhost:{self.server_port}"}


class Handler(BaseHTTPRequestHandler):
    server_version = "OpsPilot"
    def log_message(self, *args):
        pass  # Login URLs and private incident data must not enter access logs.

    def send(self, status, value, content_type="application/json", headers=None):
        raw = (json.dumps(value) if content_type == "application/json" else value).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, item in (headers or {}).items():
            self.send_header(key, item)
        self.end_headers()
        self.wfile.write(raw)

    def host_allowed(self):
        return "http://" + self.headers.get("Host", "") in self.server.origins

    def authenticated(self):
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            value = cookies.get("ops_pilot")
            return value is not None and secrets.compare_digest(value.value, self.server.token)
        except Exception:
            return False

    def ingest_authenticated(self):
        expected = self.server.ingest_token
        supplied = self.headers.get("Authorization", "")
        return bool(expected and secrets.compare_digest(supplied.encode(), ("Bearer " + expected).encode()))

    def do_GET(self):
        if not self.host_allowed():
            return self.send(403, {"error": "Use the loopback URL printed by Ops Pilot"})
        if self.path == "/metrics" and self.ingest_authenticated():
            return self.send(200, self.server.pilot.metrics(), "text/plain")
        url = urlsplit(self.path)
        if url.path == "/login":
            supplied = parse_qs(url.query).get("token", [""])[0]
            if not secrets.compare_digest(supplied, self.server.token):
                return self.send(401, {"error": "Use the fresh login link printed in your server terminal"})
            return self.send(303, "", "text/plain", {"Location": "/", "Set-Cookie": "ops_pilot=" + self.server.token + "; HttpOnly; SameSite=Strict; Path=/"})
        if not self.authenticated():
            return self.send(401, "Open the login link printed by start.sh. On EC2, create the SSH tunnel first. Restarting Ops Pilot changes the link.", "text/plain")
        if url.path == "/":
            return self.send(200, Path(__file__).with_name("dashboard.html").read_text(), "text/html")
        if url.path == "/api/report":
            try:
                report = self.server.pilot.export_report()
            except ValueError:
                return self.send(409, {"error": "Wait for the current operation before exporting"})
            return self.send(200, report, headers={"Content-Disposition": 'attachment; filename="ops-pilot-incident.json"'})
        if url.path == "/api/state":
            return self.send(200, self.server.pilot.state())
        return self.send(404, {"error": "Not found"})

    def do_POST(self):
        if self.path == "/api/events":
            if not self.host_allowed() or not self.ingest_authenticated() or self.headers.get("Origin"):
                return self.send(403, {"error": "Event ingestion requires its own configured bearer token"})
            try:
                if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Expected JSON")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    return self.send(413, {"error": "Event exceeds 64 KiB"})
                self.connection.settimeout(5)
                payload = json.loads(self.rfile.read(length))
                return self.send(200, self.server.pilot.ingest(payload))
            except (ValueError, TypeError, KeyError, RecursionError):
                return self.send(400, {"error": "Invalid event or conflicting event ID"})
            except (RuntimeError, OSError):
                return self.send(503, {"error": "Investigation unavailable; retry the same event IDs"})
        if not self.host_allowed() or not self.authenticated() or self.headers.get("Origin") not in self.server.origins:
            return self.send(403, {"error": "Open Ops Pilot locally and use its controls"})
        if self.path != "/api/action":
            return self.send(404, {"error": "Not found"})
        try:
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("Use a bounded JSON request")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Request must be between 1 and 4096 bytes")
            self.connection.settimeout(5)
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or set(data) - {"action", "plan_id"} or not isinstance(data.get("action"), str):
                raise ValueError("Choose an existing dashboard action")
            if "plan_id" in data and (not isinstance(data["plan_id"], str) or len(data["plan_id"]) > 80):
                raise ValueError("Invalid plan ID")
            result = self.server.pilot.action(data["action"], data.get("plan_id"))
            return self.send(200, result)
        except (ValueError, RuntimeError):
            return self.send(409, {"error": "Action refused. The plan may be missing, expired, already used, changed, or another operation is running. Refresh and review the current evidence."})
        except OSError:
            return self.send(503, {"error": "Local access failed. Inspect Docker and stored history before another repair."})


def run(pilot, port):
    server = Server(pilot, port, ingest_token=os.environ.get("OPS_PILOT_INGEST_TOKEN"))
    print(f"Open http://127.0.0.1:{server.server_port}/login?token={server.token}", flush=True)
    print("Single-owner preview. Keep this login link private. Ctrl+C stops monitoring.", flush=True)
    pilot.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        pilot.close()
