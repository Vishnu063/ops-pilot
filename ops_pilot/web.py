"""Single-owner loopback dashboard. No shell-command or remote-target input API."""
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, urlsplit


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8
    def __init__(self, pilot, port=8767, workspace=None, eventhub=None, diagnostics=None):
        self.request_slots = threading.BoundedSemaphore(8)
        self.diagnostics = diagnostics
        self.eventhub = eventhub
        self.pilot = pilot
        self.workspace = workspace
        self.token = secrets.token_urlsafe(32)
        self.bridge_keys = {role: os.environ.get(key, '') for role, key in
                            [('worker', 'OPS_PILOT_WORKFLOW_TOKEN'), ('owner', 'OPS_PILOT_OWNER_TOKEN')]}
        if eventhub is not None:
            source_keys={key for key in [*eventhub.keys.values(),eventhub.read_key] if key}
            if source_keys.intersection(key for key in self.bridge_keys.values() if key):
                raise ValueError('Ecosystem source/read keys must differ from agency owner/workflow keys')
        if any(value and len(value) < 32 for value in self.bridge_keys.values()):
            raise ValueError('Bridge tokens must contain at least 32 characters')
        if self.bridge_keys['worker'] and self.bridge_keys['worker'] == self.bridge_keys['owner']:
            raise ValueError('Owner and workflow tokens must be different')
        super().__init__(("127.0.0.1", port), Handler)
        self.origins = {f"http://127.0.0.1:{self.server_port}", f"http://localhost:{self.server_port}"}

    def process_request(self, request, client_address):
        if not self.request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "OpsPilot"
    def setup(self):
        self.request.settimeout(10)
        super().setup()
    def log_message(self, *args):
        pass  # Login URLs and private incident data must not enter access logs.

    def send(self, status, value, content_type="application/json", headers=None):
        raw = value if isinstance(value, bytes) else (json.dumps(value) if content_type == "application/json" else value).encode()
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

    def bridge_role(self):
        supplied = self.headers.get('X-Ops-Pilot-Key', '')
        for role, key in self.server.bridge_keys.items():
            if key and secrets.compare_digest(supplied, key):
                return role
        return None

    def do_GET(self):
        if not self.host_allowed():
            return self.send(403, {"error": "Use the loopback URL printed by Ops Pilot"})
        url = urlsplit(self.path)
        if url.path in ('/bridge/state', '/bridge/board', '/bridge/package'):
            if not self.bridge_role() or self.server.workspace is None:
                return self.send(401, {'error': 'Configure the private bridge credential'})
            workspace = self.server.workspace
            if url.path == '/bridge/package':
                try:
                    job_id = parse_qs(url.query).get('job_id', [''])[0]
                    return self.send(200, workspace.package(job_id), 'application/zip',
                                     {'Content-Disposition': f'attachment; filename="ops-pilot-{job_id}.zip"'})
                except ValueError as exc:
                    return self.send(409, {'error': str(exc)})
            return self.send(200, workspace.state() if url.path.endswith('state') else {'summary_html': workspace.summary()})
        if url.path in ('/integration/state','/integration/diagnostics','/metrics') and self.server.eventhub is not None:
            if not self.server.eventhub.authorized(self.headers.get('Authorization',''),read=True):
                return self.send(401,{'error':'Configure the private read-only integration credential'})
            if url.path=='/metrics':return self.send(200,self.server.eventhub.metrics(),'text/plain')
            if url.path=='/integration/diagnostics':
                return self.send(200,self.server.diagnostics.state() if self.server.diagnostics else {'connected':False})
            return self.send(200,self.server.eventhub.state())
        if url.path == "/login":
            supplied = parse_qs(url.query).get("token", [""])[0]
            if not secrets.compare_digest(supplied, self.server.token):
                return self.send(401, {"error": "Use the fresh login link printed in your server terminal"})
            return self.send(303, "", "text/plain", {"Location": "/", "Set-Cookie": "ops_pilot=" + self.server.token + "; HttpOnly; SameSite=Strict; Path=/"})
        if not self.authenticated():
            return self.send(401, "Open the login link printed by start.sh. On EC2, create the SSH tunnel first. Restarting Ops Pilot changes the link.", "text/plain")
        if url.path == '/diagnostics':
            return self.send(200, Path(__file__).with_name('diagnostics.html').read_text(), 'text/html')
        if url.path in ('/api/diagnostics/state', '/api/diagnostics/report'):
            desk = self.server.diagnostics
            if desk is None:
                return self.send(200, {'connected': False, 'reason': 'Read-only diagnostics are not configured'})
            try:
                if url.path.endswith('/state'):
                    return self.send(200, desk.state())
                report = desk.report(parse_qs(url.query).get('id', [''])[0])
                return self.send(200, report, headers={'Content-Disposition':'attachment; filename="ops-pilot-diagnostic-'+report['id']+'.json"'})
            except ValueError:
                return self.send(404, {'error': 'Diagnostic report not found in this environment'})
        if url.path == '/ecosystem':
            return self.send(200,Path(__file__).with_name('ecosystem.html').read_text(),'text/html')
        if url.path == '/api/ecosystem/state':
            return self.send(200,self.server.eventhub.state() if self.server.eventhub else {'connected':False,'reason':'Optional ecosystem is not configured'})
        if url.path == '/api/ecosystem/report' and self.server.eventhub:
            try:return self.send(200,self.server.eventhub.report(parse_qs(url.query).get('id',[''])[0],int(parse_qs(url.query).get('after',['0'])[0])))
            except ValueError:return self.send(409,{'error':'Report missing or exceeds export bounds'})
        if url.path == '/freelance' or (url.path == '/' and self.server.pilot is None):
            if self.server.workspace is None:
                return self.send(404, {'error': 'Freelance workspace not enabled'})
            return self.send(200, Path(__file__).with_name('freelance.html').read_text(), 'text/html')
        if url.path == '/api/freelance/state' and self.server.workspace is not None:
            return self.send(200, self.server.workspace.state())
        if url.path == '/api/freelance/history' and self.server.workspace is not None:
            try:
                return self.send(200,self.server.workspace.history(parse_qs(url.query).get('job_id',[''])[0]))
            except ValueError as exc:
                return self.send(409,{'error':str(exc)})
        if url.path == '/api/freelance/package' and self.server.workspace is not None:
            try:
                job_id = parse_qs(url.query).get('job_id', [''])[0]
                return self.send(200, self.server.workspace.package(job_id), 'application/zip',
                                 {'Content-Disposition': f'attachment; filename="ops-pilot-{job_id}.zip"'})
            except ValueError as exc:
                return self.send(409, {'error': str(exc)})
        if self.server.pilot is None:
            return self.send(404, {'error': 'Monitoring is not running in freelance-only mode'})
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
        if self.path in ('/api/diagnostics/collect', '/api/diagnostics/trivy'):
            return self.diagnostic_request()
        if self.path in ('/webhooks/ecosystem','/webhooks/alertmanager','/api/ecosystem/action'):
            return self.ecosystem_request()
        if self.path in ('/api/freelance/action', '/bridge/action'):
            return self.freelance_action()
        if not self.host_allowed() or not self.authenticated() or self.headers.get("Origin") not in self.server.origins:
            return self.send(403, {"error": "Open Ops Pilot locally and use its controls"})
        if self.path != "/api/action":
            return self.send(404, {"error": "Not found"})
        if self.server.pilot is None:
            return self.send(404, {"error": "Monitoring is not running in freelance-only mode"})
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

    def freelance_action(self):
        bridge = self.path == '/bridge/action'
        role = self.bridge_role() if bridge else 'owner'
        valid = self.host_allowed() and self.server.workspace is not None
        if bridge:
            # Bridge is for trusted server-to-server n8n calls, never a browser API.
            valid = valid and bool(role) and not self.headers.get('Origin')
        else:
            valid = valid and self.authenticated() and self.headers.get('Origin') in self.server.origins
        if not valid:
            return self.send(403, {'error': 'Use the owner dashboard or configured n8n credential'})
        try:
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Use bounded application/json')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 32768:
                raise ValueError('Request must be between 1 and 32768 bytes')
            self.connection.settimeout(5)
            payload = json.loads(self.rfile.read(length))
            result = self.server.workspace.act(payload, owner=role == 'owner')
            return self.send(200, result)
        except PermissionError as exc:
            return self.send(403, {'error': str(exc)})
        except (ValueError, TypeError, KeyError) as exc:
            return self.send(409, {'error': str(exc)})
        except OSError:
            return self.send(503, {'error': 'Workspace storage unavailable'})


    def diagnostic_request(self):
        if not self.host_allowed() or not self.authenticated() or self.headers.get('Origin') not in self.server.origins:
            return self.send(403, {'error': 'Owner session required; read/source credentials cannot collect or import'})
        desk = self.server.diagnostics
        if desk is None:
            return self.send(404, {'error': 'Read-only diagnostics are not configured'})
        try:
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Use bounded JSON')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 262144:
                raise ValueError('Input exceeds bounds')
            self.connection.settimeout(5)
            data = json.loads(self.rfile.read(length))
            if self.path.endswith('/collect'):
                if not isinstance(data, dict) or set(data) != {'tool'} or not isinstance(data['tool'], str):
                    raise ValueError('Select one configured tool')
                result = desk.collect(data['tool'])
            else:
                result = desk.trivy(data)
            return self.send(200, result)
        except (ValueError, TypeError, KeyError, RuntimeError):
            return self.send(409, {'error': 'Diagnostic request refused; check configured scope and report bounds'})
        except OSError:
            return self.send(503, {'error': 'Private diagnostic storage unavailable'})

    def ecosystem_request(self):
        hub=self.server.eventhub
        if hub is None:return self.send(404,{'error':'Optional ecosystem not configured'})
        if not self.host_allowed():return self.send(403,{'error':'Use loopback'})
        owner=self.path=='/api/ecosystem/action'
        source=hub.authorized(self.headers.get('Authorization','')) if not owner else None
        if owner:
            allowed=self.authenticated() and self.headers.get('Origin') in self.server.origins
        else:
            allowed=source is not None and not self.headers.get('Origin')
            if self.path=='/webhooks/alertmanager':allowed=allowed and source=='alertmanager'
        if not allowed:return self.send(403,{'error':'Valid source or owner authorization required'})
        try:
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError()
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536:raise ValueError()
            self.connection.settimeout(5)
            data=json.loads(self.rfile.read(length))
            if owner:result=hub.action(data)
            else:
                import time
                minute=int(time.time()/60);window,count=hub.rate.get(source,(minute,0))
                count=count+1 if window==minute else 1;hub.rate[source]=(minute,count)
                if count>120:return self.send(429,{'error':'Source rate limit reached'})
                result=hub.alertmanager(data) if self.path=='/webhooks/alertmanager' else hub.ingest(data,source)
            return self.send(200,result)
        except (ValueError,TypeError,KeyError,RuntimeError):return self.send(409,{'error':'Event or action refused; refresh and inspect current evidence'})
        except OSError:return self.send(503,{'error':'Local evidence storage or transport unavailable'})

def run(pilot, port, workspace=None, eventhub=None, diagnostics=None):
    server = Server(pilot, port, workspace, eventhub, diagnostics)
    print(f"Open http://127.0.0.1:{server.server_port}/login?token={server.token}", flush=True)
    print("Single-owner preview. Keep this login link private. Ctrl+C stops monitoring.", flush=True)
    if pilot is not None:
        pilot.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if pilot is not None:
            pilot.close()

