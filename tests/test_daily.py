"""Daily operation boundaries using existing Docker fixture and actual HTTP/SQLite."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import test_pilot as fixtures
from test_pilot import FakeDocker, CONFIG, ProbeHandler
from ops_pilot.service import Pilot
from ops_pilot.config import validate
from ops_pilot.alerts import deliver
from ops_pilot.system_service import unit
from ops_pilot.web import Server
from triage.experience import ExperienceEngine
from triage.tool_engine import ToolEngine


class DailyTests(unittest.TestCase):
    setUp = fixtures.PilotTests.setUp
    tearDown = fixtures.PilotTests.tearDown
    plan = fixtures.PilotTests.plan

    def reopen(self):
        engine = ExperienceEngine(ToolEngine(FakeDocker(), self.temp.name), self.engine.health)
        return Pilot(self.config, self.temp.name, engine=engine, probe=lambda _: {'healthy': False})

    def test_maintenance_cancels_approval_blocks_repairs_and_survives_restart(self):
        plan = self.plan(); self.pilot.action('approve', plan)
        until = self.pilot.action('maintenance')['maintenance_until']
        self.assertGreater(until, time.time())
        self.assertEqual('cancelled', self.engine.show(plan)['status'])
        for action in ('plan', 'approve', 'apply'):
            with self.assertRaises(ValueError): self.pilot.action(action, plan)
        before = len(self.engine.store.search(self.adapter.target)['results'])
        self.pilot.tick()
        self.assertEqual(before, len(self.engine.store.search(self.adapter.target)['results']))
        self.assertFalse(self.pilot.runtime.alerts())
        reopened = self.reopen()
        self.assertEqual(until, reopened.maintenance_until)
        self.assertFalse(reopened.engine.adapter.mutations)
        reopened.action('maintenance'); reopened.tick()
        self.assertEqual('application_failed', reopened.runtime.alerts()[0]['event'])
        self.assertFalse(self.adapter.mutations)

    def test_expired_maintenance_resumes_failure_detection(self):
        self.pilot.maintenance_until = time.time() - 1
        self.pilot.failed = True
        self.assertTrue(self.pilot.tick())
        self.assertEqual(0, self.pilot.maintenance_until)
        self.assertEqual('application_failed', self.pilot.runtime.alerts()[0]['event'])

    def test_outage_alert_dedup_pause_and_target_scope_survive_restart(self):
        self.pilot.tick(); self.pilot.tick()
        reopened = self.reopen(); reopened.tick()
        self.assertEqual(1, len(reopened.runtime.alerts()))
        reopened.action('monitor')
        self.assertFalse(self.reopen().monitor['enabled'])
        alternate = dict(self.config, health_url=self.config['health_url'] + '/another')
        other = Pilot(alternate, self.temp.name, engine=self.engine)
        self.assertTrue(other.monitor['enabled'])
        self.assertFalse(other.runtime.alerts())
        self.assertEqual(0o600, self.pilot.runtime.path.stat().st_mode & 0o777)

    def test_delivery_failure_does_not_change_repair_outcome_or_replay(self):
        self.pilot.config['alert_url'] = 'https://example.com/private-webhook'
        plan = self.plan(); self.pilot.action('approve', plan)
        with patch('ops_pilot.service.deliver', side_effect=OSError('secret token')):
            result = self.pilot.action('apply', plan)
        self.assertEqual('verified', result['status'])
        self.assertEqual('failed', self.pilot.runtime.alerts()[0]['delivery'])
        self.assertNotIn('secret token', json.dumps(self.pilot.state()))
        self.assertNotIn('private-webhook', json.dumps(self.pilot.export_report()))
        reopened = self.reopen()
        self.assertEqual('verified', reopened.result['status'])
        self.assertFalse(reopened.engine.adapter.mutations)
        with self.assertRaises(ValueError): reopened.action('apply', plan)

    def test_failed_application_after_restart_emits_attention_alert(self):
        plan = self.plan(); self.pilot.action('approve', plan)
        ProbeHandler.status = 503
        self.assertEqual('needs_attention', self.pilot.action('apply', plan)['status'])
        self.assertEqual('repair_needs_attention', self.pilot.runtime.alerts()[0]['event'])

    def test_diagnosis_retains_restart_count_and_does_not_invent_oom(self):
        raw = json.dumps([{'Id': 'a'*64, 'RestartCount': 7, 'State': {'Status': 'exited', 'ExitCode': 137, 'OOMKilled': False}}])
        obs = self.adapter.parse(raw)
        self.pilot.report = {'snapshot': {'observations': obs}}
        diagnosis = self.pilot.diagnosis()
        self.assertEqual(7, diagnosis['restart_count'])
        self.assertFalse(diagnosis['oom_killed'])
        self.assertNotIn('out-of-memory kill', diagnosis['explanation'])
        obs['oom'] = [True]
        self.assertIn('out-of-memory kill', self.pilot.diagnosis()['explanation'])

    def test_report_download_requires_session_and_never_contains_raw_logs(self):
        self.pilot.action('investigate')
        server = Server(self.pilot, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/api/report'
            with self.assertRaises(HTTPError) as error: urlopen(url)
            self.assertEqual(401, error.exception.code)
            with urlopen(Request(url, headers={'Cookie': 'ops_pilot=' + server.token})) as response:
                self.assertIn('attachment', response.headers['Content-Disposition'])
                report = response.read().decode()
                self.assertEqual(1, json.loads(report)['schema_version'])
                self.assertNotIn('never-persist-this', report)
                self.assertNotIn(server.token, report)
            self.pilot.lock.acquire()
            try:
                with self.assertRaises(ValueError): self.pilot.export_report()
            finally: self.pilot.lock.release()
        finally:
            server.shutdown(); server.server_close(); thread.join()


class IntegrationTests(unittest.TestCase):
    def test_local_webhook_posts_minimal_json_and_refuses_redirect(self):
        class Handler(BaseHTTPRequestHandler):
            calls = []
            def log_message(self, *args): pass
            def do_POST(self):
                self.calls.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(302 if self.path == '/redirect' else 204)
                self.send_header('Location', '/must-not-receive'); self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}'
            deliver(url + '/hook', 'application_failed')
            self.assertEqual({'source':'ops-pilot','event':'application_failed'}, Handler.calls[0][1])
            with self.assertRaises(HTTPError): deliver(url + '/redirect', 'application_failed')
            self.assertEqual(2, len(Handler.calls))
        finally:
            server.shutdown(); server.server_close(); thread.join()
        for invalid in ('http://example.com/hook', 'https://user:password@example.com/hook', 'https://example.com/\nheader'):
            with self.assertRaises(ValueError): validate(dict(CONFIG, alert_url=invalid))

    def test_service_template_refuses_expansion_and_uses_nonroot_fixed_entrypoint(self):
        text = unit('/home/ubuntu/ops-pilot', '/home/ubuntu', 'ubuntu')
        self.assertIn('User=ubuntu', text)
        self.assertIn('ExecStart=/home/ubuntu/ops-pilot/.venv/bin/python -m ops_pilot.cli', text)
        self.assertIn('Restart=on-failure', text)
        self.assertNotIn('start.sh', text)
        for root, home, user in [('/tmp/a%u','/home/ubuntu','ubuntu'), ('/tmp/a b','/home/ubuntu','ubuntu'), ('/tmp/app','/root','root'), ('/tmp/app','/home/u','u\nExecStart=bad')]:
            with self.assertRaises(ValueError): unit(root, home, user)
