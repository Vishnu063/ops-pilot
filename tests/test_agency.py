import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from ops_pilot.freelance import Workspace
from ops_pilot.backup import backup, restore, verify
from ops_pilot.deployment_lab import Lab


class AgencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.ws = Workspace(self.temp.name)
        self.job = self.ws.import_job(dict(title='Synthetic Docker pilot',description='Docker stateless HTTP'))
    def act(self,action,data=None,owner=True):
        self.job = self.ws.act(dict(action=action,job_id=self.job['id'],revision=self.job['revision'],data=data or {}),owner=owner)['job']
        return self.job
    def build(self):
        for action in ('scout','evaluator','manager','client','proposal','approve_proposal'):
            self.act(action)
        self.act('accept',dict(confirmation=self.job['id']))
        self.act('approve_work',dict(confirmation=self.job['id']))
        self.act('worker',dict(image='example/app@sha256:'+'a'*64))
    def test_finances_do_not_offset_another_clients_balance(self):
        self.act('invoice',dict(reference='i',amount='100.10',due='2020-01-01'))
        self.act('expense',dict(reference='e',amount='1.05'))
        self.act('time_entry',dict(reference='t',hours='1.50',hourly_rate='10.10'))
        other = self.ws.import_job(dict(title='Other Docker client',description='Docker'))
        with self.ws.connect() as db:
            db.execute('INSERT INTO payments VALUES (?,?,?,?,?,?)',('other',other['id'],'USD',20000,50,'2026-01-01'))
            db.execute('INSERT INTO payments VALUES (?,?,?,?,?,?)',('this',self.job['id'],'USD',1000,10,'2026-01-01'))
        totals = next(x['business_summary'] for x in self.ws.state()['jobs'] if x['id']==self.job['id'])
        self.assertEqual(9010,totals['outstanding_cents'])
        self.assertEqual(1515,totals['estimated_labor_cents'])
        self.assertEqual(-630,totals['estimated_profit_cents'])
        with self.assertRaises(ValueError): self.act('invoice',dict(reference='i',amount='1'))
        with self.assertRaises(ValueError): self.act('expense',dict(reference='bad',amount='NaN'))
        with self.assertRaises(PermissionError): self.act('expense',dict(reference='e2',amount='1'),False)
    def test_scope_secrets_dependencies_and_closure(self):
        with self.assertRaises(ValueError): self.act('brief',dict(client_alias='a',target='b',scope='c',constraints='password=bad'))
        self.act('task',dict(id='one',title='Requirement review',owner='owner',status='blocked',blocker='Missing image'))
        with self.assertRaises(ValueError): self.act('task',dict(id='two',title='Deploy',owner='owner',status='done',depends_on='one'))
        with self.assertRaises(ValueError): self.act('close')
        self.build()
        with self.assertRaises(ValueError): self.act('brief',dict(client_alias='a',target='b',scope='changed',constraints='none'))
        self.act('reviewer'); self.act('sign_off',dict(confirmation=self.job['id']))
        self.act('validation',dict(kind='customer_runtime',reference='synthetic-unverified',result='unverified',limitations='No customer access'))
        self.assertNotIn('delivery',self.job['approvals'])
    def test_cross_process_revision_cas(self):
        other = Workspace(self.temp.name)
        payload = dict(action='task',job_id=self.job['id'],revision=self.job['revision'],data=dict(id='x',title='x',owner='x',status='todo'))
        def run(ws):
            try: ws.act(payload,owner=True); return True
            except ValueError: return False
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(run,[self.ws,other]))
        self.assertEqual([False,True],sorted(results))
    def test_consistent_backup_restore_and_tamper_refusal(self):
        self.build()
        destination = Path(self.temp.name)/'snapshot'
        backup(self.ws,destination); verify(destination)
        restored = Path(self.temp.name)/'restored'
        restore(destination,restored)
        copy = Workspace(restored).get(self.job['id'])
        self.assertEqual(self.job['artifacts'],copy['artifacts'])
        self.assertEqual({},copy['approvals'])
        self.assertEqual(0o600,(restored/'freelance/workspace.sqlite3').stat().st_mode & 0o777)
        with self.assertRaises(FileExistsError): restore(destination,restored)
        with (destination/'workspace.sqlite3').open('ab') as stream: stream.write(b'tamper')
        with self.assertRaises(ValueError): restore(destination,Path(self.temp.name)/'bad')
        self.assertFalse((Path(self.temp.name)/'bad').exists())
    def test_lab_approval_durable_before_side_effect_failure_and_replay(self):
        self.build(); self.act('approve_lab',dict(confirmation=self.job['id']))
        digest = self.ws.digest(self.job)
        observed = []
        def docker(args,timeout=30):
            persisted = Workspace(self.temp.name).get(self.job['id'])
            observed.append(persisted['lab']['status'])
            self.assertNotIn('lab',persisted['approvals'])
            raise ValueError('simulated config failure')
        with patch.object(Lab,'preflight',return_value=(json.loads(self.job['artifacts']['acceptance.json']),digest)), patch.object(Lab,'docker',side_effect=docker), patch.object(Lab,'cleanup'):
            self.act('lab_run')
            self.assertEqual('failed',self.job['lab']['status'])
            self.assertEqual('verified',self.job['lab']['cleanup'])
            with self.assertRaises(ValueError): self.act('lab_run')
        self.assertEqual(['running'],observed)
    def test_lab_disabled_expiry_ownership_and_cleanup_failure(self):
        self.build()
        with patch.dict('os.environ',{'OPS_PILOT_LAB':'0'}):
            with self.assertRaises(ValueError): self.act('lab_run')
        self.act('approve_lab',dict(confirmation=self.job['id']))
        digest = self.ws.digest(self.job)
        with patch.object(Lab,'preflight',return_value=(json.loads(self.job['artifacts']['acceptance.json']),digest)), patch.object(Lab,'docker',side_effect=ValueError('simulated failure')), patch.object(Lab,'cleanup',side_effect=ValueError('simulated cleanup failure')):
            self.act('lab_run')
        self.assertEqual('cleanup_failed',self.job['lab']['status'])
        with self.assertRaises(ValueError): self.act('approve_lab',dict(confirmation=self.job['id']))
        with patch.object(Lab,'docker',side_effect=['foreign',json.dumps([{'Config':{'Labels':{}}}])]):
            with self.assertRaises(ValueError): Lab(self.ws).cleanup(self.job)
    def test_expired_approval_blocks_work(self):
        self.build()
        self.assertFalse(self.ws.approval_valid(dict(time='2000-01-01T00:00:00+00:00')))
    def test_interrupted_recovery_is_visible_and_does_not_redeploy(self):
        self.build()
        self.job['lab'] = dict(status='running',project='opslab-'+self.job['id']+'-interrupted',digest=self.ws.digest(self.job))
        with self.ws.connect() as db:
            db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(self.job),self.job['id']))
        reopened = Workspace(self.temp.name)
        self.assertEqual('running',reopened.get(self.job['id'])['lab']['status'])
        with self.assertRaises(ValueError): self.act('invoice',dict(reference='x',amount='1'))
        with patch.object(Lab,'preflight',return_value=(json.loads(self.job['artifacts']['acceptance.json']),self.ws.digest(self.job))), patch.object(Lab,'cleanup') as cleanup, patch.object(Lab,'docker') as docker:
            self.act('lab_recover')
            cleanup.assert_called_once();docker.assert_not_called()
            self.assertEqual('recovered',self.job['lab']['status'])

    def test_lab_expiry_digest_timeout_and_active_process_lock(self):
        import fcntl
        import subprocess
        self.build();self.act('approve_lab',dict(confirmation=self.job['id']))
        self.job['approvals']['lab']['expires']='2000-01-01T00:00:00+00:00'
        with self.ws.connect() as db:
            db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(self.job),self.job['id']))
        with patch.object(Lab,'preflight',return_value=(json.loads(self.job['artifacts']['acceptance.json']),self.ws.digest(self.job))):
            with self.assertRaises(ValueError): self.act('lab_run')
            self.act('approve_lab',dict(confirmation=self.job['id']))
            with (self.ws.directory/'.lab.lock').open('w') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(ValueError): self.act('lab_run')
            with patch.object(Lab,'docker',side_effect=subprocess.TimeoutExpired('simulated',30)), patch.object(Lab,'cleanup'):
                self.act('lab_run')
                self.assertEqual('failed',self.job['lab']['status'])
                self.assertEqual('TimeoutExpired',self.job['lab']['error'])

    def test_model_is_optional_and_rejects_missing_model_without_download(self):
        from ops_pilot.advisor import Advisor
        with patch('ops_pilot.advisor.build_opener') as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b'{"models":[]}'
            with self.assertRaises(ValueError): Advisor(self.ws).advise('Which requirement is missing?','missing:latest')
            self.assertEqual(1,opener.return_value.open.call_count)


if __name__ == '__main__': unittest.main()
