import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

from ops_pilot.freelance import Workspace
from ops_pilot.web import Server


class FreelanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Workspace(self.temp.name)
        self.job = self.workspace.import_job(dict(title='Docker EC2 deployment', description='Docker Compose, Linux and nginx setup', source_id='one'))
    def tearDown(self):
        self.temp.cleanup()
    def act(self, action, data=None, owner=True):
        self.job = self.workspace.act(dict(action=action, job_id=self.job['id'], revision=self.job['revision'], data=data or {}), owner=owner)['job']
        return self.job
    def plan(self):
        for action in ['scout', 'evaluator', 'manager', 'client', 'proposal']:
            self.act(action)
    def build(self):
        self.plan()
        self.act('approve_proposal')
        self.act('accept', {'confirmation': self.job['id']})
        self.act('approve_work', {'confirmation': self.job['id']})
        self.act('worker', {'image': 'example/app@sha256:'+'a'*64})
    def test_complete_flow_is_persistent_and_does_not_claim_live_delivery(self):
        self.build()
        self.act('reviewer')
        self.act('sign_off', {'confirmation': self.job['id']})
        self.act('delivery')
        with zipfile.ZipFile(io.BytesIO(self.workspace.package(self.job['id']))) as z:
            self.assertEqual(4, len(z.namelist()))
            self.assertFalse(json.loads(z.read('acceptance.json'))['runtime_verified'])
        self.act('payment', {'reference': 'receipt-one', 'amount': '100.10', 'fee': '10.01'})
        self.act('earnings')
        self.assertEqual(9009, self.job['agents']['earnings']['output']['net_cents'])
        self.assertFalse(self.job['agents']['delivery']['output']['sent'])
        reopened = Workspace(self.temp.name)
        self.assertEqual('packaged', reopened.get(self.job['id'])['state'])
        self.assertEqual(9, len(self.job['agents']))
        self.assertEqual(0o600, reopened.path.stat().st_mode & 0o777)
    def test_worker_cannot_approve_or_skip_order_or_replay(self):
        with self.assertRaises(ValueError): self.act('worker', {'image': 'nginx:alpine'})
        self.plan()
        for action in ('approve_proposal', 'edit_proposal', 'reject'):
            with self.assertRaises(PermissionError): self.act(action, owner=False)
        self.act('approve_proposal')
        with self.assertRaises(ValueError): self.act('accept', {'confirmation': 'wrong'})
        self.act('accept', {'confirmation': self.job['id']})
        with self.assertRaises(PermissionError): self.act('approve_work', owner=False)
        with self.assertRaises(ValueError): self.act('worker', {'image': 'nginx:alpine'})
        self.act('approve_work', {'confirmation': self.job['id']})
        with self.assertRaises(ValueError): self.act('worker', {'image': '$(touch /tmp/no)'})
        self.act('worker', {'image': 'nginx:alpine'})
        with self.assertRaises(ValueError): self.act('worker', {'image': 'nginx:alpine'})
        with self.assertRaises(ValueError): self.act('delivery')
    def test_stale_revisions_duplicates_and_edit_invalidation(self):
        duplicate = self.workspace.import_job(dict(title='Docker EC2 deployment', description='changed', source_id='one'))
        self.assertEqual(self.job['id'], duplicate['id'])
        old = self.job.copy()
        self.plan()
        with self.assertRaises(ValueError):
            self.workspace.act(dict(action='earnings', job_id=old['id'], revision=old['revision']))
        self.act('approve_proposal')
        self.act('edit_proposal', {'draft': 'My reviewed proposal'})
        self.assertNotIn('proposal', self.job['approvals'])
        with self.assertRaises(ValueError): self.act('accept', {'confirmation': self.job['id']})
    def test_unsupported_jobs_are_not_silently_implemented(self):
        self.job = self.workspace.import_job(dict(title='Production database migration', description='Docker production database migration'))
        self.plan(); self.act('approve_proposal'); self.act('accept', {'confirmation': self.job['id']})
        with self.assertRaises(ValueError): self.act('approve_work', {'confirmation': self.job['id']})
    def test_html_is_escaped_and_money_is_exact_and_not_double_recorded(self):
        self.job = self.workspace.import_job(dict(title='<script>alert(1)</script>', description='Docker Linux', currency='INR'))
        self.assertNotIn('<script>', self.workspace.summary())
        self.build(); self.act('reviewer'); self.act('sign_off', {'confirmation': self.job['id']}); self.act('delivery')
        for bad in ['NaN', '-1', '0.001', 'Infinity']:
            with self.assertRaises(ValueError): self.act('payment', {'reference': 'a', 'amount': bad})
        self.act('payment', {'reference': 'r', 'amount': '0.10'})
        with self.assertRaises(ValueError): self.act('payment', {'reference': 'r', 'amount': '0.10'})
        self.assertEqual(10, self.workspace.state()['earnings'][0]['gross_cents'])


class FreelanceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Workspace(self.temp.name)
        with patch.dict(os.environ, {'OPS_PILOT_WORKFLOW_TOKEN':'w'*40, 'OPS_PILOT_OWNER_TOKEN':'o'*40}):
            self.server = Server(None, 0, self.workspace)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()
    def request(self, path, payload=None, **headers):
        request = Request(self.origin+path, data=None if payload is None else json.dumps(payload).encode(), headers={'Content-Type':'application/json', **headers})
        try: result = urlopen(request)
        except HTTPError as exc: result = exc
        with result: return result.code, result.read()
    def test_owner_bridge_scope_origin_and_cookie_protection(self):
        self.assertEqual(401, self.request('/api/freelance/state')[0])
        self.assertEqual(401, self.request('/bridge/state')[0])
        self.assertEqual(200, self.request('/bridge/state', **{'X-Ops-Pilot-Key':'w'*40})[0])
        payload = dict(action='import', data=dict(title='Docker job', description='Docker Compose'))
        self.assertEqual(403, self.request('/bridge/action', payload, **{'X-Ops-Pilot-Key':'w'*40,'Origin':self.origin})[0])
        code, body = self.request('/bridge/action', payload, **{'X-Ops-Pilot-Key':'w'*40})
        self.assertEqual(200, code)
        job = json.loads(body)['job']
        payload = dict(action='approve_proposal', job_id=job['id'], revision=job['revision'])
        self.assertEqual(403, self.request('/bridge/action', payload, **{'X-Ops-Pilot-Key':'w'*40})[0])
        self.assertEqual(403, self.request('/api/freelance/action', payload, Cookie='ops_pilot='+self.server.token)[0])
        self.assertEqual(403, self.request('/bridge/state', **{'X-Ops-Pilot-Key':'w'*40,'Host':'evil.example'})[0])
        code, page = self.request('/freelance', Cookie='ops_pilot='+self.server.token)
        self.assertEqual(200, code); self.assertIn(b'The agent canvas', page); self.assertNotIn(b'innerHTML',page)
        self.assertEqual(404, self.request('/api/action', {'action':'plan'},
                         Cookie='ops_pilot='+self.server.token, Origin=self.origin)[0])
