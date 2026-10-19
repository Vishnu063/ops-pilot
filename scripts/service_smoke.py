"""Opt-in CI acceptance against real systemd; never run on a customer server."""
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def command(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def run():
    if os.environ.get('OPS_PILOT_SERVICE_LAB') != '1':
        raise SystemExit('Set OPS_PILOT_SERVICE_LAB=1 only on a disposable systemd CI runner')
    # Never overwrite an existing installation, including an inactive one.
    if Path('/etc/systemd/system/ops-pilot.service').exists():
        raise SystemExit('Existing unit found; refusing the lab')
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self): self.send_response(200); self.end_headers()
    http = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    with tempfile.TemporaryDirectory(prefix='ops-pilot-service-') as home:
        env = {**os.environ, 'HOME': home}
        config = Path(home) / '.config/ops-pilot/config.json'
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps(dict(name='Systemd CI app', docker_context='default',
            container='disposable-service-lab', health_url=f'http://127.0.0.1:{http.server_port}/', interval_seconds=15)))
        origin = 'http://127.0.0.1:8767'
        def fresh_token(previous=None):
            for _ in range(80):
                logs = command('sudo', 'journalctl', '-u', 'ops-pilot', '-n', '40', '--no-pager', '-o', 'cat')
                tokens = re.findall(r'/login\?token=([A-Za-z0-9_-]+)', logs)
                if tokens and tokens[-1] != previous:
                    try:
                        with urllib.request.urlopen(origin + '/login?token=' + tokens[-1], timeout=1) as response:
                            pass
                    except Exception:
                        pass  # Redirect requires a cookie-aware client; authenticated state below is authoritative.
                    request = urllib.request.Request(origin + '/api/state', headers={'Cookie':'ops_pilot=' + tokens[-1]})
                    try:
                        with urllib.request.urlopen(request, timeout=1) as response:
                            if not json.load(response).get('busy'): return tokens[-1]
                    except Exception: pass
                time.sleep(.25)
            raise AssertionError('Service did not become ready with a fresh session')
        def state(token):
            request = urllib.request.Request(origin + '/api/state', headers={'Cookie':'ops_pilot=' + token})
            with urllib.request.urlopen(request, timeout=3) as response: return json.load(response)
        try:
            subprocess.run(['bash', str(ROOT/'scripts/install-service.sh')], env=env, check=True, capture_output=True)
            assert command('sudo','systemctl','is-enabled','ops-pilot') == 'enabled'
            token = fresh_token()
            before = state(token)
            assert before['name'] == 'Systemd CI app'
            # Control change through the actual authenticated server.
            request = urllib.request.Request(origin+'/api/action', data=b'{"action":"maintenance"}',
                headers={'Cookie':'ops_pilot='+token,'Origin':origin,'Content-Type':'application/json'})
            with urllib.request.urlopen(request, timeout=3): pass
            command('sudo','systemctl','restart','ops-pilot')
            restarted = fresh_token(token)
            assert state(restarted)['maintenance_until'] > time.time()
            assert state(restarted)['history'] == []
            # Real crash recovery: launcher has already exited, systemd restarts it.
            command('sudo','systemctl','kill','--kill-whom=main','--signal=SIGKILL','ops-pilot')
            recovered = fresh_token(restarted)
            assert state(recovered)['history'] == []
            try:
                state(token)
            except urllib.error.HTTPError as error:
                assert error.code == 401
            else: raise AssertionError('Old login session survived server restart')
            print('Systemd acceptance passed: enabled for boot, detached start, persistent maintenance, crash restart, rotated sessions, no repairs.')
            print('A full machine reboot was not performed.')
        finally:
            subprocess.run(['sudo','systemctl','disable','--now','ops-pilot'], capture_output=True)
            subprocess.run(['sudo','rm','-f','/etc/systemd/system/ops-pilot.service'], check=True)
            subprocess.run(['sudo','systemctl','daemon-reload'], check=True)
            http.shutdown(); http.server_close(); thread.join()


if __name__ == '__main__': run()
