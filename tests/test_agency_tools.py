"""Business assistance uses real workspace transactions, never customer infrastructure."""
import tempfile
import unittest
from ops_pilot.freelance import Workspace


class AgencyToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.ws = Workspace(self.temp.name)
        self.job = self.ws.import_job(dict(title='SYNTHETIC Docker project', description='Docker stateless HTTP',currency='INR'))

    def act(self, action, data=None, owner=True):
        self.job = self.ws.act(dict(action=action,job_id=self.job['id'],revision=self.job['revision'],data=data or {}),owner=owner)['job']
        return self.job

    def brief(self, **changes):
        values=dict(client_alias='SYNTHETIC',target='owned test host reference',scope='One image',constraints='No customer infrastructure',
            runtime_assumptions='Known stateless HTTP image, no writable persistent paths',environment='Linux Docker Compose',
            image='example/app@sha256:'+'a'*64,port='8000',health_path='/health',expected_status='200',
            configuration='none',stateless='yes',persistent_storage='no',private_network='no',
            access_reference='SYNTHETIC-NOT-REAL-AUTHORIZATION',access_expires='2100-01-01T00:00:00+00:00',
            agreement_reference='SYNTHETIC-NOT-SIGNED',first_deployment='no',rollback_image='example/app@sha256:'+'b'*64,
            rollback_reference='SYNTHETIC-RECOVERY-PLAN')
        return {**values,**changes}

    def test_quote_exact_rounding_and_limits_leave_ledger_unchanged(self):
        self.act('quote',dict(hours='2.00',hourly_rate='20.00',complexity='1.25',platform_fees='5.00'))
        q=self.job['agency']['quote_estimate']
        self.assertEqual(5500,q['total_cents']);self.assertEqual('INR',q['currency'])
        self.assertFalse(q['customer_agreed']);self.assertFalse(q['sent'])
        self.act('quote',dict(hours='0.03',hourly_rate='0.50'))
        self.assertEqual(2,self.job['agency']['quote_estimate']['labor_cents'])
        for values in (dict(hours='NaN',hourly_rate='1'),dict(hours='241',hourly_rate='1'),
                       dict(hours='1',hourly_rate='1',complexity='0'),dict(hours='1',hourly_rate='1',tools='-1'),
                       dict(hours='1',hourly_rate='1',currency='USD')):
            with self.assertRaises(ValueError):self.act('quote',values)
        self.assertEqual([],self.job['agency']['invoices'])
        self.assertEqual([],self.ws.state()['earnings'])

    def test_quote_invalidates_proposal_approval_and_cannot_change_accepted_scope(self):
        for action in ('scout','evaluator','manager','client','proposal','approve_proposal'):self.act(action)
        self.act('quote',dict(hours='1',hourly_rate='1'))
        self.assertNotIn('proposal',self.job['approvals'])
        with self.assertRaises(ValueError):self.act('accept',dict(confirmation=self.job['id']))
        self.act('approve_proposal');self.act('accept',dict(confirmation=self.job['id']))
        with self.assertRaises(ValueError):self.act('quote',dict(hours='2',hourly_rate='20'))

    def test_intake_reports_missing_expired_and_unsupported_requirements(self):
        self.act('intake_check')
        self.assertFalse(self.job['agency']['intake_check']['ready_for_manual_review'])
        self.act('brief',self.brief(access_expires='2000-01-01T00:00:00+00:00',private_network='yes',expected_status='201'))
        self.act('intake_check');report=self.job['agency']['intake_check']
        self.assertTrue(any('expired' in s for s in report['blockers']))
        self.assertTrue(any('private_network' in s for s in report['blockers']))
        self.assertTrue(any('HTTP 200' in s for s in report['blockers']))
        self.assertFalse(report['authorized_to_deploy'])
        self.act('brief',self.brief(access_expires='2100-01-01'))
        self.act('intake_check')
        self.assertTrue(any('timezone' in s for s in self.job['agency']['intake_check']['blockers']))

    def test_complete_intake_is_only_ready_for_manual_review_and_replaced_brief_invalidates_it(self):
        self.act('brief',self.brief());self.act('intake_check')
        report=self.job['agency']['intake_check']
        self.assertTrue(report['ready_for_manual_review']);self.assertFalse(report['authorized_to_deploy'])
        self.assertFalse(report['customer_runtime_verified']);self.assertEqual({},self.job['approvals'])
        self.act('quote',dict(hours='1',hourly_rate='1'))
        self.act('brief',self.brief(first_deployment='yes',rollback_image=''))
        self.assertNotIn('quote_estimate',self.job['agency']);self.assertNotIn('intake_check',self.job['agency'])
        self.act('intake_check');self.assertTrue(self.job['agency']['intake_check']['ready_for_manual_review'])

    def test_drafts_persist_without_sending_or_cross_project_payment_offset(self):
        self.act('task',dict(id='check',title='Inspect starter files',owner='owner',status='done'))
        self.act('task',dict(id='access',title='Access review',owner='owner',status='blocked',blocker='Missing written authorization'))
        self.act('invoice',dict(reference='SYNTHETIC',amount='100.00'))
        other=self.ws.import_job(dict(title='Other synthetic client',description='Docker',currency='INR'))
        with self.ws.connect() as db:
            db.execute('INSERT INTO payments VALUES (?,?,?,?,?,?)',('other',other['id'],'INR',20000,0,'2026-10-24'))
        for kind in ('requirements','progress','incident','overdue','follow_up'):
            self.act('draft_message',dict(kind=kind,details='Synthetic observed outage; not customer evidence'))
        saved=Workspace(self.temp.name).get(self.job['id'])['agency']['drafts']
        self.assertEqual(5,len(saved));self.assertTrue(all(not d['sent'] and not d['approved_to_send'] for d in saved))
        self.assertIn('INR 100.00',next(d['text'] for d in saved if d['kind']=='overdue'))
        self.assertIn('Missing written authorization',next(d['text'] for d in saved if d['kind']=='progress'))
        with self.assertRaises(ValueError):self.act('draft_message',dict(kind='incident'))
        with self.assertRaises(ValueError):self.act('draft_message',dict(kind='automatic_send'))
        self.assertEqual(5,len(self.ws.get(self.job['id'])['agency']['drafts']))
        for action,data in [('quote',dict(hours='1',hourly_rate='1')),('intake_check',{}),('draft_message',dict(kind='progress'))]:
            with self.assertRaises(PermissionError):self.act(action,data,owner=False)

    def test_worker_refuses_explicitly_unsupported_requirements(self):
        self.act('brief',self.brief(private_network='yes'))
        for action in ('scout','evaluator','manager','client','proposal','approve_proposal'):self.act(action)
        self.act('accept',dict(confirmation=self.job['id']));self.act('approve_work',dict(confirmation=self.job['id']))
        with self.assertRaises(ValueError):self.act('worker',dict(image=self.brief()['image']))
        self.assertEqual({},self.ws.get(self.job['id'])['artifacts'])
        self.assertIn('work',self.ws.get(self.job['id'])['approvals'])


if __name__=='__main__':unittest.main()
