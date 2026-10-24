import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPRedirectHandler, Request
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from triage.experience import ExperienceEngine
from triage.tool_engine import ToolEngine
from ops_pilot.config import load, save, validate
from ops_pilot.service import DockerAdapter, Pilot
from ops_pilot.web import Server

CONFIG = {"name": "Test application", "docker_context": "default", "container": "owned-app", "health_url": "http://127.0.0.1:9999/health", "interval_seconds": 15}


class FakeDocker(DockerAdapter):
    def __init__(self):
        super().__init__({"context": "default", "resource": "owned-app"})
        self.current_id = "a" * 64
        self.current_daemon = "daemon-a"
        self.container_state = "exited"
        self.mutations = []
        self.permission_denied = False
        self.timeout = False
    def command(self, recipe, **kwargs):
        if self.permission_denied:
            raise RuntimeError("Native CLI authentication/permission failed")
        if "info" in recipe:
            return self.current_daemon, 0
        if "inspect" in recipe:
            return json.dumps([{"Id": self.current_id, "Name": "/owned-app", "State": {"Status": self.container_state, "ExitCode": 1, "OOMKilled": False, "StartedAt": "2026-10-19T04:00:00Z"}}]), 0
        if "logs" in recipe:
            return "connection refused token=never-persist-this", 0
        if "restart" in recipe:
            self.mutations.append(recipe)
            if self.timeout:
                raise RuntimeError("Command timed out. Outcome may be unknown.")
            self.container_state = "running"
            return self.current_id, 0
        raise AssertionError(recipe)


class ProbeHandler(BaseHTTPRequestHandler):
    status = 200
    def log_message(self, *args):
        pass
    def do_GET(self):
        self.send_response(type(self).status)
        self.end_headers()
        self.wfile.write(b'{"healthy":true}')


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.adapter = FakeDocker()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
        self.http_thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.http_thread.start()
        ProbeHandler.status = 200
        self.config = dict(CONFIG, health_url=f"http://127.0.0.1:{self.http.server_port}/health")
        _, health = validate(self.config)
        health.update(interval=0, recovery_timeout_seconds=1)
        core = ToolEngine(self.adapter, self.temp.name)
        self.engine = ExperienceEngine(core, health)
        self.pilot = Pilot(self.config, self.temp.name, engine=self.engine, probe=lambda _: {"healthy": False})
    def tearDown(self):
        self.pilot.close()
        self.http.shutdown(); self.http.server_close(); self.http_thread.join()
        self.temp.cleanup()
    def plan(self):
        self.pilot.action("investigate")
        return self.pilot.action("plan")["id"]
    def test_monitor_investigates_once_per_outage_and_never_mutates(self):
        for _ in range(3):
            self.pilot.tick()
        self.assertEqual(1, len(self.engine.store.search(self.adapter.target)["results"]))
        self.assertFalse(self.adapter.mutations)
        self.assertIsNone(self.pilot.plan_id)
        self.pilot.probe = lambda _: {"healthy": True}; self.pilot.tick()
        self.pilot.probe = lambda _: {"healthy": False}; self.pilot.tick()
        self.assertEqual(2, len(self.engine.store.search(self.adapter.target)["results"]))
    def test_repair_requires_separate_approval_and_replay_is_refused(self):
        plan = self.plan()
        with self.assertRaises(ValueError): self.pilot.action("apply", plan)
        self.pilot.action("approve", plan)
        self.assertFalse(self.adapter.mutations)
        result = self.pilot.action("apply", plan)
        self.assertEqual("verified", result["status"])
        self.assertTrue(result["application_health"]["healthy"])
        self.assertEqual("a" * 64, self.adapter.mutations[0][-1])
        with self.assertRaises(ValueError): self.pilot.action("apply", plan)
        self.assertEqual(1, len(self.adapter.mutations))
    def test_running_container_with_failed_http_is_not_recovery(self):
        plan = self.plan(); self.pilot.action("approve", plan)
        ProbeHandler.status = 503
        result = self.pilot.action("apply", plan)
        self.assertEqual("needs_attention", result["status"])
        self.assertEqual("verified", result["infrastructure_status"])
        self.assertFalse(result["application_health"]["healthy"])
    def test_replacement_state_daemon_expiry_and_cancellation_invalidate_plan(self):
        for change in ("replacement", "state", "daemon", "expiry", "cancel"):
            with self.subTest(change=change):
                plan = self.plan()
                if change == "replacement": self.adapter.current_id = "b" * 64
                if change == "state": self.adapter.container_state = "running"
                if change == "daemon": self.adapter.current_daemon = "daemon-b"
                if change == "expiry":
                    p = self.engine.show(plan); p["expires_at"] = time.time() - 1; self.engine._save(p)
                if change == "cancel": self.pilot.action("cancel", plan)
                with self.assertRaises(ValueError): self.pilot.action("approve", plan)
                self.assertFalse(self.adapter.mutations)
                if change != "cancel": self.engine.cancel(plan)
                self.adapter.current_id = "a" * 64; self.adapter.current_daemon = "daemon-a"; self.adapter.container_state = "exited"
    def test_timeout_consumes_approval_and_is_never_retried(self):
        plan = self.plan(); self.pilot.action("approve", plan); self.adapter.timeout = True
        self.assertEqual("needs_attention", self.pilot.action("apply", plan)["status"])
        with self.assertRaises(ValueError): self.pilot.action("apply", plan)
        self.assertEqual(1, len(self.adapter.mutations))
    def test_missing_permissions_and_missing_health_are_not_success(self):
        self.adapter.permission_denied = True
        self.pilot.action("investigate")
        self.assertTrue(self.pilot.report["snapshot"]["errors"])
        self.assertFalse(self.pilot.report["actions"])
        with self.assertRaises(RuntimeError): self.pilot.action("plan")
        self.pilot.probe = lambda _: {"healthy": None}
        self.assertFalse(self.pilot.tick()); self.assertIsNone(self.pilot.monitor["healthy"])
    def test_pause_busy_and_secret_projection(self):
        self.pilot.action("monitor"); self.assertFalse(self.pilot.tick())
        self.pilot.lock.acquire()
        try:
            self.assertTrue(self.pilot.state()["busy"])
            with self.assertRaises(ValueError): self.pilot.action("investigate")
        finally: self.pilot.lock.release()
        self.pilot.action("investigate")
        self.assertNotIn("never-persist-this", json.dumps(self.pilot.report))
    def test_restart_restores_plan_without_approving_or_replaying_it(self):
        plan = self.plan()
        adapter = FakeDocker()
        engine = ExperienceEngine(ToolEngine(adapter, self.temp.name), self.engine.health)
        reopened = Pilot(self.config, self.temp.name, engine=engine)
        self.assertEqual(plan, reopened.plan_id)
        self.assertEqual("pending", reopened.state()["plan"]["status"])
        self.assertFalse(adapter.mutations)
        reopened.action("approve", plan)
        self.assertFalse(adapter.mutations)


class ConfigTests(unittest.TestCase):
    def test_rejects_ambiguous_targets_credentials_and_nonlocal_http(self):
        for key, value in [("container", "*"), ("container", "--help"), ("docker_context", "a;b"), ("health_url", "http://example.com/health"), ("health_url", "https://u:password@example.com"), ("interval_seconds", True), ("interval_seconds", 1)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): validate(dict(CONFIG, **{key: value}))
        with self.assertRaises(ValueError): validate(dict(CONFIG, token="secret"))
    def test_private_configuration_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "config.json"
            save(path, CONFIG)
            self.assertEqual(CONFIG, load(path)[0])
            self.assertEqual(0o600, path.stat().st_mode & 0o777)


class WebTests(unittest.TestCase):
    def setUp(self):
        class Stub:
            calls = []
            def state(self): return {"name": "test"}
            def action(self, action, plan_id=None): self.calls.append((action, plan_id)); return {"ok": True}
        self.pilot = Stub()
        self.server = Server(self.pilot, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
    def request(self, path, body=None, authenticated=False, **extra):
        headers = {"Content-Type": "application/json", **extra}
        if authenticated: headers["Cookie"] = "ops_pilot=" + self.server.token
        request = Request(self.origin + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            response = build_opener().open(request)
        except HTTPError as error:
            response = error
        with response:
            return response.code, response.read().decode()
    def test_session_origin_host_and_payload_are_checked(self):
        self.assertEqual(401, self.request("/api/state")[0])
        self.assertEqual(200, self.request("/api/state", authenticated=True)[0])
        self.assertEqual(403, self.request("/api/state", authenticated=True, Host="evil.example")[0])
        self.assertEqual(403, self.request("/api/action", {"action": "plan"}, True, Origin="https://evil.example")[0])
        self.assertEqual(403, self.request("/api/action", {"action": "plan"}, True)[0])
        self.assertEqual(409, self.request("/api/action", {"action": "plan", "command": "bad"}, True, Origin=self.origin)[0])
        self.assertFalse(self.pilot.calls)
        self.assertEqual(200, self.request("/api/action", {"action": "investigate"}, True, Origin=self.origin)[0])
        self.assertEqual([("investigate", None)], self.pilot.calls)
    def test_dashboard_is_self_contained_and_has_no_external_dependencies(self):
        status, page = self.request("/", authenticated=True)
        self.assertEqual(200, status)
        self.assertIn("Approve this plan", page)
        self.assertNotIn("<script src=", page)
        self.assertNotIn("innerHTML", page)
