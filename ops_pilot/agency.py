"""Owner-maintained business records. References are assertions, never independent proof."""
from datetime import datetime, timezone
import re

ACTIONS = {'brief', 'task', 'scope_change', 'invoice', 'expense', 'time_entry',
           'validation', 'customer_acceptance', 'offboard', 'close', 'approve_lab'}


def checked(data, fields, required=()):
    from .freelance import text
    if set(data) - set(fields) or any(k not in data for k in required):
        raise ValueError('Unknown or missing record fields: ' + ', '.join(fields))
    out = {}
    for key, value in data.items():
        out[key] = text(value, key, 2000, key in required)
        if re.search(r'(?i)(-----BEGIN .*PRIVATE KEY|AKIA[A-Z0-9]{16}|(?:password|secret|token)\s*[:=]\s*\S+)', out[key]):
            raise ValueError('Store credentials outside project text; use a reference only')
    return out


def records(job):
    return job.setdefault('agency', dict(brief={}, tasks={}, scope_changes=[], invoices=[],
        expenses=[], time_entries=[], validations=[], customer_acceptance={}, offboarding={}, closed=False))


def handle(action, job, data):
    from .freelance import money, now, Workspace
    a = records(job)
    if a['closed']:
        raise ValueError('Closed projects are read-only')
    if action == 'brief':
        if job['state'] not in ('imported', 'evaluated', 'proposal_ready'):
            raise ValueError('Accepted scope is frozen; record a scope change and create a new scoped project')
        a['brief'] = checked(data, ('client_alias','target','access_reference','access_expires','image','port','health_path',
            'expected_status','rollback_image','configuration','constraints','scope','agreement_reference','quote',
            'milestones','revisions','support_hours','support_days','response_expectation','retention_days','deadline'),
            ('client_alias','target','scope','constraints'))
        job['approvals'].clear()
    elif action == 'task':
        item = checked(data, ('id','title','owner','due','status','blocker','depends_on'), ('id','title','owner','status'))
        if item['status'] not in ('todo','doing','blocked','done'):
            raise ValueError('Task status must be todo, doing, blocked or done')
        if item.get('due'):
            datetime.fromisoformat(item['due']).replace(tzinfo=timezone.utc)
        if item.get('depends_on') == item['id'] or (item.get('depends_on') and item['depends_on'] not in a['tasks']):
            raise ValueError('Dependency must be an existing different task')
        if item['status'] == 'done' and item.get('depends_on') and a['tasks'][item['depends_on']]['status'] != 'done':
            raise ValueError('Complete the dependency first')
        a['tasks'][item['id']] = item
    elif action == 'scope_change':
        a['scope_changes'].append(dict(**checked(data, ('reference','change','price_impact','deadline_impact','agreement_reference'),
            ('reference','change','price_impact','deadline_impact')), time=now(), applied=False))
        job['approvals'].clear()
    elif action in ('invoice','expense','time_entry'):
        fields = {'invoice':('reference','amount','due','milestone'), 'expense':('reference','amount','description'),
                  'time_entry':('reference','hours','hourly_rate','description')}[action]
        item = checked(data, fields, fields[:2])
        collection = a[{'invoice':'invoices','expense':'expenses','time_entry':'time_entries'}[action]]
        if any(x['reference'] == item['reference'] for x in collection):
            raise ValueError('Reference already recorded')
        if action == 'time_entry':
            from decimal import Decimal, ROUND_HALF_UP
            hours100 = money(item['hours'])
            if hours100 > 2400:
                raise ValueError('A time entry cannot exceed 24 hours')
            item['labor_cents'] = int((Decimal(hours100) * money(item.get('hourly_rate','0')) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        else:
            item['amount_cents'] = money(item['amount'])
        if action == 'invoice' and item.get('due'):
            datetime.fromisoformat(item['due'])
        collection.append(dict(**item, currency=job['currency'], time=now()))
    elif action == 'validation':
        item = checked(data, ('kind','reference','result','limitations'), ('kind','reference','result','limitations'))
        if item['kind'] not in ('static','sandbox','customer_runtime','independent_review') or item['result'] not in ('passed','failed','unverified'):
            raise ValueError('Choose a validation kind and passed, failed or unverified')
        a['validations'].append(dict(**item, digest=Workspace.digest(job), time=now(), source='owner-recorded'))
        job['approvals'].pop('delivery', None)
    elif action == 'customer_acceptance':
        if job['state'] != 'packaged':
            raise ValueError('Package the exact reviewed bundle first')
        a['customer_acceptance'] = dict(**checked(data, ('reference','limitations'), ('reference','limitations')),
            digest=Workspace.digest(job), time=now(), source='owner-recorded; not independently verified')
    elif action == 'offboard':
        a['offboarding'] = dict(**checked(data, ('revocation_reference','retention_until','follow_up'),
            ('revocation_reference','retention_until','follow_up')), time=now())
    elif action == 'close':
        if not a['customer_acceptance'] or not a['offboarding'] or any(t['status'] != 'done' for t in a['tasks'].values()):
            raise ValueError('Record customer acceptance, offboarding and complete tasks before closure')
        a['closed'] = True
    elif action == 'approve_lab':
        from datetime import timedelta
        if job['state'] not in ('built','reviewed','packaged') or data.get('confirmation') != job['id']:
            raise ValueError('Generate artifacts and confirm the job ID for a disposable lab only')
        if job.get('lab',{}).get('status') in ('running','interrupted','cleanup_failed'):
            raise ValueError('Recover the existing lab before approving another')
        job['approvals']['lab'] = dict(digest=Workspace.digest(job), time=now(),
            expires=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat())


def summary(job, payments):
    a = records(job)
    gross = sum(p[0] for p in payments); fees = sum(p[1] for p in payments)
    invoices = sum(x['amount_cents'] for x in a['invoices'])
    expenses = sum(x['amount_cents'] for x in a['expenses'])
    labor = sum(x['labor_cents'] for x in a['time_entries'])
    today = datetime.now(timezone.utc).date().isoformat()
    alerts = [f"Task {t['id']}: {t.get('blocker') or 'overdue'}" for t in a['tasks'].values()
              if t['status']=='blocked' or (t.get('due','9999')[:10]<today and t['status']!='done')]
    # Credit stays on this project and currency; it never offsets another client's balance.
    if invoices > gross and any(i.get('due','9999')[:10]<today for i in a['invoices']):
        alerts.append('Outstanding invoice: prepare a follow-up draft; nothing sent')
    if job.get('lab',{}).get('status') in ('running','interrupted','cleanup_failed','failed'):
        alerts.append('Practice lab requires attention: '+job['lab']['status'])
    return dict(currency=job['currency'], invoiced_cents=invoices, cash_received_cents=gross,
        fee_cents=fees, expense_cents=expenses, estimated_labor_cents=labor,
        outstanding_cents=max(0,invoices-gross), unallocated_credit_cents=max(0,gross-invoices),
        estimated_profit_cents=gross-fees-expenses-labor, alerts=alerts,
        next_action='Review outstanding records and workflow gates', source='owner-recorded; not independently verified')
