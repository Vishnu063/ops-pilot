import copy
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import test_pilot
from ops_pilot.events import normalize, EventStore
from ops_pilot.events_client import send
from ops_pilot.web import Server


def event():
    return dict(schema_version=1, kind='DeploymentEvent', id='release:failed', source='cloudlaunch', service='owned-app',
                timestamp='2026-10-24T00:00:00Z', correlation_id='build-1', status='failed', release_id='sha256:abc')


class EventTests(unittest.TestCase):
    setUp = test_pilot.PilotTests.setUp
    tearDown = test_pilot.PilotTests.tearDown
    def test_authenticated_ingress_cannot_approve_and_dedup_survives_restart(self):
        server = Server(self.pilot, 0, ingest_token='x' * 40)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        url = f'http://127.0.0.1:{server.server_port}/api/events'
        try:
            with self.assertRaises(HTTPError) as error:
                build_opener(ProxyHandler({})).open(Request(url, data=json.dumps(event()).encode(), headers={'Content-Type': 'application/json'}))
            self.assertEqual(403, error.exception.code)
            result = send(url, 'x' * 40, event())
            self.assertFalse(result['repair_executed'])
            self.assertTrue(result['receipts'][0]['incident_id'])
            self.assertIsNone(self.pilot.plan_id)
            self.assertFalse(self.adapter.mutations)
            before = len(self.engine.store.search(self.adapter.target)['results'])
            self.pilot.events = EventStore(self.pilot.runtime)
            self.assertTrue(send(url, 'x' * 40, event())['receipts'][0]['duplicate'])
            self.assertEqual(before, len(self.engine.store.search(self.adapter.target)['results']))
            with self.assertRaises(ValueError): send(url, 'x' * 40, dict(event(), release_id='different'))
            with self.assertRaises(ValueError): send(url, 'x' * 40, dict(event(), command='restart'))
            self.assertIn('ops_pilot_events_total 1', self.pilot.metrics())
            self.assertEqual(1, len(self.pilot.export_report()['incoming_events']))
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_alert_resolution_does_not_claim_recovery_and_batch_validation_is_atomic(self):
        alert = dict(status='firing', fingerprint='abc123', startsAt='2026-10-24T00:00:00Z', labels={'service': 'owned-app', 'alertname': 'ApplicationDown'})
        payload = dict(version='4', alerts=[alert])
        first = self.pilot.ingest(payload)
        self.assertFalse(first['receipts'][0]['duplicate'])
        self.assertTrue(self.pilot.ingest(payload)['receipts'][0]['duplicate'])
        bad = copy.deepcopy(payload); bad['alerts'].append(dict(alert, labels={'service': 'other'}))
        with self.assertRaises(ValueError): self.pilot.ingest(bad)
        alert['status'] = 'resolved'; self.pilot.ingest(payload)
        self.assertIsNone(self.pilot.monitor['healthy'])
        self.assertFalse(self.adapter.mutations)
        self.assertEqual(2, len(self.pilot.events.history()))
        alert['startsAt'] = '2026-10-25T00:00:00Z'; alert['status'] = 'firing'
        self.assertFalse(self.pilot.ingest(payload)['receipts'][0]['duplicate'])

    def test_busy_and_maintenance_never_lose_or_execute_events(self):
        self.pilot.lock.acquire()
        try:
            with self.assertRaises(RuntimeError): self.pilot.ingest(event())
        finally: self.pilot.lock.release()
        self.assertEqual([], self.pilot.events.history())
        self.pilot.action('maintenance')
        self.assertIsNone(self.pilot.ingest(event())['receipts'][0]['incident_id'])
        self.pilot.action('maintenance')
        self.assertTrue(self.pilot.ingest(event())['receipts'][0]['incident_id'])
        self.assertFalse(self.adapter.mutations)


if __name__ == '__main__': unittest.main()
