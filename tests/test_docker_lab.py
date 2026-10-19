"""Opt-in acceptance on disposable, uniquely labelled local Docker containers."""
import json
import os
from pathlib import Path
import subprocess
import socket
import tempfile
import time
import unittest
import uuid

from ops_pilot.service import Pilot


def docker(*args):
    return subprocess.check_output(["docker", "--context", "default", *args], text=True, timeout=90).strip()


@unittest.skipUnless(os.environ.get("OPS_PILOT_DOCKER_LAB") == "1", "opt-in local Docker lab")
class DockerLab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        endpoint = docker("context", "inspect", "default", "--format", "{{.Endpoints.docker.Host}}")
        if not endpoint.startswith("unix://"):
            raise RuntimeError("The acceptance lab refuses a remote Docker endpoint")
        image = os.environ.get("OPS_PILOT_LAB_IMAGE", "python:3.12-alpine")
        # The chosen digest and Docker version are printed in CI for reproducibility.
        docker("pull", image)
        cls.image = image
        print("Docker:", docker("version", "--format", "{{.Server.Version}}"))
        print("Image:", docker("image", "inspect", image, "--format", "{{json .RepoDigests}}"))
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.name = "ops-pilot-lab-" + uuid.uuid4().hex[:12]
        # Choose a free port, then publish it explicitly: Docker may allocate a
        # different host port after restarting a dynamically published container.
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        self.identifier = docker("run", "-d", "--name", self.name, "--label", "ops-pilot.lab=" + self.name,
            "-p", f"127.0.0.1:{port}:8000", self.image, "python", "-m", "http.server", "8000")
        self.addCleanup(self.cleanup_container)
        self.addCleanup(self.temp.cleanup)
        self.url = f"http://127.0.0.1:{port}/"
        self.config = {"name": "Owned disposable lab", "docker_context": "default", "container": self.name, "health_url": self.url, "interval_seconds": 15}
        self.pilot = Pilot(self.config, self.temp.name)
        self.addCleanup(self.pilot.close)
        self.assertTrue(self.wait_health())
    def cleanup_container(self):
        state = json.loads(docker("container", "inspect", self.identifier))[0]
        if state["Config"]["Labels"].get("ops-pilot.lab") != self.name:
            raise RuntimeError("Lab ownership changed; refusing cleanup")
        docker("rm", "-f", self.identifier)
    def wait_health(self):
        from triage.health import check_health
        for _ in range(15):
            if check_health(dict(self.pilot.health, attempts=1, successes=1, interval=0))["healthy"]:
                return True
            time.sleep(.5)
        return False
    def fail_and_plan(self):
        docker("stop", "--time", "1", self.identifier)
        self.pilot.tick()
        self.assertFalse(self.pilot.monitor["healthy"])
        self.assertTrue(self.pilot.report["findings"])
        self.assertEqual("exited", json.loads(docker("inspect", self.identifier))[0]["State"]["Status"])
        return self.pilot.action("plan")["id"]
    def test_real_outage_approval_restart_http_verification_and_replay(self):
        plan = self.fail_and_plan()
        with self.assertRaises(ValueError): self.pilot.action("apply", plan)
        self.pilot.action("approve", plan)
        self.assertEqual("exited", json.loads(docker("inspect", self.identifier))[0]["State"]["Status"])
        result = self.pilot.action("apply", plan)
        self.assertEqual("verified", result["status"], result)
        self.assertTrue(result["application_health"]["healthy"])
        self.assertEqual(self.identifier, self.pilot.engine.show(plan)["command"][-1])
        with self.assertRaises(ValueError): self.pilot.action("apply", plan)
    def test_real_state_change_refuses_stale_approval(self):
        plan = self.fail_and_plan()
        docker("start", self.identifier)
        self.assertTrue(self.wait_health())
        with self.assertRaises(ValueError): self.pilot.action("approve", plan)
        self.assertEqual("pending", self.pilot.engine.show(plan)["status"])
    def test_real_restart_with_wrong_application_endpoint_is_not_success(self):
        # Rebuild the engine with an endpoint this HTTP server consistently rejects.
        self.pilot = Pilot(dict(self.config, health_url=self.url + "not-found-" + uuid.uuid4().hex), Path(self.temp.name) / "wrong-health")
        plan = self.fail_and_plan()
        self.pilot.action("approve", plan)
        result = self.pilot.action("apply", plan)
        self.assertEqual("verified", result["infrastructure_status"])
        self.assertEqual("needs_attention", result["status"])
        self.assertFalse(result["application_health"]["healthy"])
