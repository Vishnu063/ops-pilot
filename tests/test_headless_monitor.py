import contextlib
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
import unittest
from unittest.mock import patch

from ops_pilot.cli import main
from ops_pilot.config import save
from ops_pilot.service import Pilot
from test_pilot import FakeDocker, CONFIG
from triage.experience import ExperienceEngine
from triage.tool_engine import ToolEngine


class HeadlessCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / 'config.json'
        self.state = self.root / 'state'
        save(self.config, dict(CONFIG))

    def tearDown(self):
        self.temp.cleanup()

    def test_lock_precedes_pilot_initialization(self):
        import ops_pilot.service
        def check(*args, **kwargs):
            self.assertTrue((self.state / 'headless.lock').exists())
            return StubPilot()
        with patch.object(ops_pilot.service, 'Pilot', side_effect=check), patch('sys.argv', ['ops-pilot','monitor','--headless','--config',str(self.config),'--state-dir',str(self.state)]), patch('ops_pilot.cli.load', wraps=__import__('ops_pilot.config',fromlist=['load']).load), contextlib.redirect_stdout(io.StringIO()):
            # Stop after first tick to avoid waiting for the default interval.
            handler = {}
            def capture(sig, fn): handler[sig] = fn
            def wait(_): handler[signal.SIGTERM](signal.SIGTERM, None)
            with patch('signal.signal', side_effect=capture), patch('threading.Event.wait', side_effect=wait):
                self.assertEqual(0, main())

    def test_duplicate_monitor_rejected_without_state_mutation(self):
        self.state.mkdir(mode=0o700)
        lock = (self.state/'headless.lock').open('w')
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        before = sorted(p.name for p in self.state.iterdir())
        try:
            with patch('sys.argv', ['ops-pilot','monitor','--headless','--config',str(self.config),'--state-dir',str(self.state)]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(2, main())
            self.assertEqual(before, sorted(p.name for p in self.state.iterdir()))
        finally:
            lock.close()

    def test_lock_released_when_pilot_initialization_fails(self):
        import ops_pilot.service
        with patch.object(ops_pilot.service, 'Pilot', side_effect=RuntimeError('init failed')), patch('sys.argv', ['ops-pilot','monitor','--headless','--config',str(self.config),'--state-dir',str(self.state)]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(2, main())
        import fcntl
        with (self.state/'headless.lock').open('a+') as f:
            fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_sigterm_and_sigint_exit_cleanly(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(sig=sig):
                import ops_pilot.cli
                prior = signal.getsignal(sig)
                def install(s, handler):
                    if s == sig: handler(s, None)
                    return None
                with patch('signal.signal', side_effect=install), patch('sys.argv', ['ops-pilot','monitor','--headless','--config',str(self.config),'--state-dir',str(self.state)]), patch('ops_pilot.service.Pilot', return_value=StubPilot()), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(0, main())
                signal.signal(sig, prior)

    def test_no_dashboard_listener(self):
        import socket
        handler = {}
        def capture(sig, fn): handler[sig] = fn
        def wait(_): handler[signal.SIGTERM](signal.SIGTERM, None)
        with patch('sys.argv', ['ops-pilot','monitor','--headless','--config',str(self.config),'--state-dir',str(self.state)]), patch('ops_pilot.service.Pilot', return_value=StubPilot()), patch('signal.signal', side_effect=capture), patch('threading.Event.wait', side_effect=wait), patch('ops_pilot.web.run', side_effect=AssertionError('dashboard must not start')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, main())


class StubPilot:
    def __init__(self):
        self.n = 0
    def tick(self): self.n += 1
    def state(self): return {'monitor':{'checked_at':float(self.n),'healthy':True},'container':'fixture'}
    def close(self): pass


class PilotHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.adapter = FakeDocker()
        self.config = dict(CONFIG, health_url='http://127.0.0.1:18081/health')
        _, health = __import__('ops_pilot.config',fromlist=['validate']).validate(self.config)
        health.update(interval=0)
        self.engine = ExperienceEngine(ToolEngine(self.adapter, self.temp.name), health)
        self.status = 200
        self.pilot = Pilot(self.config, self.temp.name, engine=self.engine,
            probe=lambda _: {'healthy': self.status == 200})
    def tearDown(self):
        self.pilot.close(); self.temp.cleanup()
    def test_http_200_healthy(self):
        self.assertTrue(self.pilot.tick())
        self.assertTrue(self.pilot.state()['monitor']['healthy'])
    def test_http_500_detects_incident_while_container_running(self):
        self.adapter.container_state = 'running'; self.status = 500
        self.assertTrue(self.pilot.tick())
        self.assertFalse(self.pilot.state()['monitor']['healthy'])
        self.assertEqual('running', self.adapter.container_state)
        self.assertTrue(self.pilot.report)
        diagnosis = self.pilot.diagnosis()
        self.assertEqual('running', diagnosis['state'])
        self.assertIn('compare it with the current endpoint check', diagnosis['explanation'])
        self.assertFalse(self.pilot.failed is False)
    def test_recovery_clears_failed_state(self):
        self.status = 500; self.pilot.tick()
        self.status = 200; self.pilot.tick()
        self.assertTrue(self.pilot.state()['monitor']['healthy'])
        self.assertFalse(self.pilot.failed)
    def test_profile_state_is_isolated(self):
        other = tempfile.TemporaryDirectory()
        try:
            p = Pilot(self.config, other.name, engine=ExperienceEngine(ToolEngine(FakeDocker(), other.name), self.engine.health), probe=lambda _: {'healthy':True})
            self.pilot.action('monitor')
            self.assertTrue(p.monitor['enabled'])
            p.close()
        finally: other.cleanup()


if __name__ == '__main__': unittest.main()
