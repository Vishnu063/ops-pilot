"""Exercise nine roles and agency records without customer access, deployment or money."""
import json
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ops_pilot.freelance import Workspace
from ops_pilot.backup import backup, restore

start=time.monotonic()
with tempfile.TemporaryDirectory() as directory:
    ws=Workspace(directory)
    job=ws.import_job(dict(title='SYNTHETIC · one stateless Docker HTTP app',description='Docker Compose on Linux EC2; synthetic exercise, no real client',platform='synthetic',source_id='pilot-v2'))
    actions=[]
    def act(action,data=None):
        global job
        job=ws.act(dict(action=action,job_id=job['id'],revision=job['revision'],data=data or {}),owner=True)['job']
        actions.append(action)
    act('brief',dict(client_alias='SYNTHETIC ONLY',target='owned disposable test host (not accessed)',scope='One existing stateless HTTP image',constraints='No customer infrastructure',agreement_reference='SYNTHETIC-NOT-SIGNED',quote='USD 100.10 synthetic example',milestones='On acceptance (synthetic)',revisions='1',support_hours='Weekdays 10:00-18:00 Asia/Kolkata',support_days='7',response_expectation='Next working day',retention_days='30',runtime_assumptions='SYNTHETIC stateless HTTP image',environment='Linux Docker Compose',image='example/synthetic-app@sha256:'+'a'*64,port='8000',health_path='/health',expected_status='200',configuration='none',stateless='yes',persistent_storage='no',private_network='no',access_reference='SYNTHETIC-NOT-AUTHORIZED',access_expires='2100-01-01T00:00:00+00:00',first_deployment='yes',rollback_reference='SYNTHETIC first-deployment recovery plan, no prior image'))
    act('quote',dict(hours='2.00',hourly_rate='40.04',complexity='1.25'))
    act('intake_check')
    act('draft_message',dict(kind='requirements'))
    act('task',dict(id='review',title='Inspect starter files',owner='owner',status='todo'))
    for a in ('scout','evaluator','manager','client','proposal','approve_proposal'):act(a)
    act('accept',dict(confirmation=job['id'])); act('approve_work',dict(confirmation=job['id']))
    act('worker',dict(image='example/synthetic-app@sha256:'+'a'*64,port=8000,health_path='/health'))
    act('reviewer')
    act('draft_message',dict(kind='progress'))
    act('draft_message',dict(kind='incident',details='SYNTHETIC exercise only: no real outage observed'))
    act('validation',dict(kind='customer_runtime',reference='SYNTHETIC-NO-ACCESS',result='unverified',limitations='No customer endpoint or infrastructure connected'))
    act('sign_off',dict(confirmation=job['id'])); act('delivery')
    act('invoice',dict(reference='SYNTHETIC-INVOICE',amount='100.10',due='2026-10-24',milestone='Synthetic example only'))
    act('draft_message',dict(kind='overdue'))
    act('expense',dict(reference='SYNTHETIC-EXPENSE',amount='1.05'))
    act('time_entry',dict(reference='SYNTHETIC-TIME',hours='1.50',hourly_rate='10.10'))
    act('payment',dict(reference='SYNTHETIC-NOT-A-RECEIPT',amount='100.10',fee='10.01')); act('earnings')
    act('draft_message',dict(kind='follow_up'))
    act('task',dict(id='review',title='Inspect starter files',owner='owner',status='done'))
    act('customer_acceptance',dict(reference='SYNTHETIC-NOT-REAL-ACCEPTANCE',limitations='Simulates owner record only; no customer'))
    act('offboard',dict(revocation_reference='SYNTHETIC-NO-CREDENTIALS',retention_until='2026-11-23',follow_up='Draft only, nothing sent'))
    backup(ws,Path(directory)/'backup'); restore(Path(directory)/'backup',Path(directory)/'recovered')
    assert Workspace(Path(directory)/'recovered').get(job['id'])['artifacts']==job['artifacts']
    act('close')
    report=dict(label='SYNTHETIC ONLY; no customer, deployment, payment or acceptance occurred',actions=actions,roles=len(job['agents']),
        finance=ws.state()['jobs'][0]['business_summary'],quote_estimate_cents=job['agency']['quote_estimate']['total_cents'],intake_ready_for_manual_review=job['agency']['intake_check']['ready_for_manual_review'],unsent_drafts=len(job['agency']['drafts']),backup_restored=True,customer_runtime_verified=False,elapsed_seconds=round(time.monotonic()-start,3))
    root=Path(__file__).resolve().parents[1]
    (root/'docs/evidence/synthetic-pilot.json').write_text(json.dumps(report,indent=2)+'\n')
    example=root/'docs/example-delivery';example.mkdir(exist_ok=True)
    for name,contents in job['artifacts'].items():
        (example/name).write_text(contents)
print('Synthetic pilot passed; report and example files saved. No external actions occurred.')
