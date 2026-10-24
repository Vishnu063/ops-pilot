"""Single-owner freelance workspace. Named, bounded agents; no platform scraping or shell execution."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import zipfile
from . import agency

AGENTS = {
    'scout': ('Job finder', 'Imports owner-provided listings; never scrapes a platform.'),
    'evaluator': ('Job evaluator', 'Matches DevOps skills and flags unsupported scope.'),
    'manager': ('Manager', 'Produces a scoped task plan and next action.'),
    'client': ('Client assistant', 'Drafts questions and a requirements checklist; sends nothing.'),
    'proposal': ('Proposal writer', 'Produces an editable, rule-based proposal draft.'),
    'worker': ('DevOps worker', 'Builds a Docker deployment starter bundle after owner approval.'),
    'reviewer': ('Reviewer', 'Checks the generated bundle; records live checks as unverified.'),
    'delivery': ('Delivery assistant', 'Packages a reviewed bundle after owner sign-off.'),
    'earnings': ('Earnings tracker', 'Summarizes owner-recorded payments; never charges anyone.'),
}
SKILLS = ('aws', 'ec2', 'docker', 'compose', 'jenkins', 'github actions', 'linux', 'nginx', 'kubernetes', 'helm', 'bash', 'python', 'grafana', 'prometheus')
OWNER_ACTIONS = agency.ACTIONS | {'lab_run', 'lab_recover', 'advice'} | {'approve_proposal', 'accept', 'approve_work', 'sign_off', 'payment', 'edit_proposal', 'reject'}
ACTIONS = {'import', 'edit_proposal', 'reject', *OWNER_ACTIONS, *AGENTS}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def text(value, name, limit=12000, required=True):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()) or '\x00' in value:
        raise ValueError(f'Enter a valid {name} (maximum {limit} characters)')
    if re.search(r'(?i)(-----BEGIN .*PRIVATE KEY|AKIA[A-Z0-9]{16}|(?:password|secret|token)\s*[:=]\s*\S+)', value):
        raise ValueError('Keep credentials outside project text; use a reference')
    return value.strip()


def money(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError('Enter an amount as a decimal string')
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > 100000000 or amount.as_tuple().exponent < -2:
            raise ValueError('Amount must be positive with at most two decimal places')
        return int(amount * 100)
    except InvalidOperation as exc:
        raise ValueError('Invalid amount') from exc


class PrivateConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class Workspace:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser() / 'freelance'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'workspace.sqlite3'
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        os.chmod(self.directory, 0o700)
        os.chmod(self.path, 0o600)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, source_key TEXT UNIQUE, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS revisions (job TEXT, revision INTEGER, payload TEXT NOT NULL, PRIMARY KEY(job,revision))')
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, job TEXT, time TEXT, action TEXT, revision INTEGER)')
            db.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, job TEXT, time TEXT, action TEXT, revision INTEGER, actor TEXT, evidence TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS payments (reference TEXT PRIMARY KEY, job TEXT, currency TEXT, gross INTEGER, fee INTEGER, time TEXT)')
            db.execute('BEGIN IMMEDIATE')
            for ident,payload in db.execute('SELECT id,payload FROM jobs').fetchall():
                job = json.loads(payload)
                approval = job['approvals'].get('delivery')
                if approval and approval.get('evidence_version') != 2:
                    if approval.get('digest') == self.digest(job) and not job.get('lab') and not job.get('agency',{}).get('validations'):
                        approval.update(digest=self.review_digest(job),evidence_version=2)
                        if job['state'] == 'packaged':
                            job['package_digest'] = self.review_digest(job)
                    else:
                        job['approvals'].pop('delivery')
                        if job['state'] == 'packaged': job['state'] = 'reviewed'
                    job['revision'] += 1
                    db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(job),ident))
                    db.execute('INSERT INTO audit(job,time,action,revision,actor,evidence) VALUES (?,?,?,?,?,?)',
                        (ident,now(),'delivery_evidence_migrated',job['revision'],'migration',self.digest(job)))


    def connect(self):
        return sqlite3.connect(self.path, timeout=10, factory=PrivateConnection)

    def get(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{12}', job_id):
            raise ValueError('Use the 12-character job ID from the workspace')
        with self.connect() as db:
            row = db.execute('SELECT payload FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise ValueError('Job not found')
        return json.loads(row[0])

    def import_job(self, data, actor="manual"):
        allowed = {'title', 'description', 'platform', 'url', 'source_id', 'budget', 'currency'}
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValueError('Unknown listing fields')
        title = text(data.get('title'), 'title', 160)
        description = text(data.get('description'), 'description')
        platform = text(data.get('platform', 'manual'), 'platform', 40)
        url = text(data.get('url', ''), 'URL', 1000, False)
        if url and not re.fullmatch(r'https://[^\s<>"\x00-\x1f]+', url):
            raise ValueError('Listing URL must be HTTPS')
        source_id = text(data.get('source_id', ''), 'source ID', 300, False)
        # Duplicate email deliveries and repeated form submissions resolve to one job.
        key = hashlib.sha256(json.dumps([platform, source_id or url or [title, description]], sort_keys=True).encode()).hexdigest()
        currency = data.get('currency', 'USD')
        if currency not in ('USD', 'INR', 'EUR', 'GBP'):
            raise ValueError('Choose USD, INR, EUR or GBP')
        job = dict(id=secrets.token_hex(6), title=title, description=description, platform=platform, url=url,
                   budget_cents=money(data.get('budget', '0')), currency=currency, state='imported', revision=1,
                   created=now(), updated=now(), agents={}, artifacts={}, approvals={}, source_key=key)
        with self.lock, self.connect() as db:
            existing = db.execute('SELECT payload FROM jobs WHERE source_key=?', (key,)).fetchone()
            if existing:
                return json.loads(existing[0])
            db.execute('INSERT INTO jobs VALUES (?,?,?)', (job['id'], key, json.dumps(job)))
            db.execute('INSERT INTO revisions VALUES (?,?,?)',(job['id'],job['revision'],json.dumps(job)))
            db.execute('INSERT INTO events(job,time,action,revision) VALUES (?,?,?,?)', (job['id'], now(), 'import', 1))
            db.execute('INSERT INTO audit(job,time,action,revision,actor,evidence) VALUES (?,?,?,?,?,?)',
                (job['id'],now(),'import',1,actor,'saved:'+key))
        return job

    def state(self):
        with self.connect() as db:
            jobs = [json.loads(r[0]) for r in db.execute('SELECT payload FROM jobs ORDER BY rowid DESC LIMIT 200')]
            events = [dict(job=j, time=t, action=a, revision=v) for j,t,a,v in db.execute('SELECT job,time,action,revision FROM events ORDER BY id DESC LIMIT 80')]
            audit = [dict(job=j,time=t,action=a,revision=v,actor=actor,result=e) for j,t,a,v,actor,e in db.execute('SELECT job,time,action,revision,actor,evidence FROM audit ORDER BY id DESC LIMIT 80')]
            totals = [dict(currency=c, gross_cents=g, fee_cents=f, net_cents=g-f) for c,g,f in db.execute('SELECT currency,SUM(gross),SUM(fee) FROM payments GROUP BY currency')]
            for job in jobs:
                job['business_summary'] = agency.summary(job, db.execute('SELECT gross,fee FROM payments WHERE job=?', (job['id'],)).fetchall())
        return dict(jobs=jobs, events=events, audit=audit, earnings=totals,
                    agents=[dict(id=k, name=v[0], description=v[1], mode='bounded local automation') for k,v in AGENTS.items()],
                    connectors={'upwork': 'not connected; manual import supported', 'fiverr': 'not connected',
                                'openhands': 'not connected', 'ai_model': 'not configured; deterministic drafts',
                                'customer_infrastructure': 'not connected'},
                    limits='Single owner. No automatic bidding, messages, live deployment or payment processing.')

    def act(self, payload, owner=False):
        try:
            return self._act(payload, owner)
        except (ValueError, PermissionError, OSError) as exc:
            if isinstance(payload, dict) and payload.get('action') in ACTIONS:
                ident = payload.get('job_id')
                if isinstance(ident,str) and re.fullmatch(r'[a-f0-9]{12}',ident):
                    with self.connect() as db:
                        db.execute('INSERT INTO audit(job,time,action,revision,actor,evidence) VALUES (?,?,?,?,?,?)',
                            (ident,now(),payload['action'],payload.get('revision') if type(payload.get('revision')) is int else 0,
                             'owner' if owner else 'workflow','refused:'+type(exc).__name__))
            raise

    def _act(self, payload, owner=False):
        if not isinstance(payload, dict) or set(payload) - {'action', 'job_id', 'revision', 'data'}:
            raise ValueError('Unknown command fields')
        action = payload.get('action')
        if action not in ACTIONS:
            raise ValueError('Unknown workspace action')
        if action in OWNER_ACTIONS and not owner:
            raise PermissionError('This decision requires the owner credential or owner dashboard')
        data = payload.get('data', {})
        if not isinstance(data, dict):
            raise ValueError('data must be an object')
        if action == 'import':
            job = self.import_job(data,actor="owner" if owner else "workflow")
            return dict(job=job, summary_html=self.summary())
        if action in ('lab_run', 'lab_recover'):
            from .deployment_lab import Lab
            return Lab(self).run(payload, recover=action == 'lab_recover')
        with self.lock, self.connect() as db:
            if action != 'advice':
                db.execute('BEGIN IMMEDIATE')
            payment = None
            self.get(payload.get('job_id'))  # validates the identifier
            job = json.loads(db.execute('SELECT payload FROM jobs WHERE id=?', (payload['job_id'],)).fetchone()[0])
            if type(payload.get('revision')) is not int or payload['revision'] != job['revision']:
                raise ValueError('Job changed. Refresh its revision before acting')
            if job['state'] == 'rejected':
                raise ValueError('Rejected jobs cannot run agents')
            if job.get('lab',{}).get('status') == 'running':
                raise ValueError('Lab is running or interrupted; inspect and recover it before editing')
            if job.get('agency', {}).get('closed'):
                raise ValueError('Closed projects are read-only')
            if action == 'advice':
                from .advisor import Advisor
                advice = Advisor(self).advise(agency.checked(data, ('prompt','model'), ('prompt','model'))['prompt'],data['model'])
                db.execute('BEGIN IMMEDIATE')
                latest = json.loads(db.execute('SELECT payload FROM jobs WHERE id=?',(job['id'],)).fetchone()[0])
                if latest['revision'] != job['revision']:
                    raise ValueError('Job changed during advice; refresh')
                job['advice'] = advice
            elif action in agency.ACTIONS:
                agency.handle(action, job, data)
            elif action in AGENTS:
                result = self.agent(action, job, data)
                job['agents'][action] = dict(time=now(), output=result, mode='bounded local automation')
            elif action == 'edit_proposal':
                if job['state'] != 'proposal_ready':
                    raise ValueError('Draft a proposal before editing; accepted jobs are frozen')
                job['agents']['proposal']['output']['draft'] = text(data.get('draft'), 'proposal draft', 8000)
                job['approvals'].pop('proposal', None)
            elif action == 'approve_proposal':
                if job['state'] != 'proposal_ready':
                    raise ValueError('Run the proposal agent first')
                job['approvals']['proposal'] = dict(time=now(), revision=job['revision'])
            elif action == 'accept':
                if job['state'] != 'proposal_ready' or not self.approval_valid(job['approvals'].get('proposal')):
                    raise ValueError('Review and approve the proposal first')
                if data.get('confirmation') != job['id']:
                    raise ValueError('Type the job ID to confirm the client actually accepted')
                job['state'] = 'accepted'
            elif action == 'approve_work':
                if job['state'] != 'accepted':
                    raise ValueError('Record client acceptance first')
                if job.get('agency',{}).get('scope_changes'):
                    raise ValueError('Scope changes require a separately agreed new project')
                if data.get('confirmation') != job['id']:
                    raise ValueError('Type the job ID to approve starter-file generation')
                if job['agents']['evaluator']['output']['scope'] != 'docker_starter':
                    raise ValueError('Worker supports Docker deployment starter files only; other jobs require manual work')
                job['approvals']['work'] = dict(time=now(), revision=job['revision'])
            elif action == 'sign_off':
                if job['state'] != 'reviewed' or not job['agents']['reviewer']['output']['checks_passed']:
                    raise ValueError('Pass the artifact checks before signing off')
                if data.get('confirmation') != job['id']:
                    raise ValueError('Type the job ID to confirm you reviewed the files and limitations')
                job['approvals']['delivery'] = dict(time=now(), digest=self.review_digest(job),evidence_version=2)
            elif action == 'payment':
                if job['state'] != 'packaged':
                    raise ValueError('Package the work before recording a payment')
                reference = text(data.get('reference'), 'unique payment reference', 150)
                gross = money(data.get('amount'))
                fee = money(data.get('fee', '0'))
                if gross <= 0 or fee > gross:
                    raise ValueError('Payment must be greater than zero; fee cannot exceed amount')
                payment = (reference, job['id'], job['currency'], gross, fee, now())
            elif action == 'reject':
                job['state'] = 'rejected'
            job['revision'] += 1
            job['updated'] = now()
            if payment is not None:
                try:
                    db.execute('INSERT INTO payments VALUES (?,?,?,?,?,?)', payment)
                except sqlite3.IntegrityError as exc:
                    raise ValueError('Payment reference already recorded; no duplicate added') from exc
            db.execute('UPDATE jobs SET payload=? WHERE id=?', (json.dumps(job), job['id']))
            db.execute('INSERT INTO revisions VALUES (?,?,?)',(job['id'],job['revision'],json.dumps(job)))
            db.execute('INSERT INTO events(job,time,action,revision) VALUES (?,?,?,?)', (job['id'], now(), action, job['revision']))
            db.execute('INSERT INTO audit(job,time,action,revision,actor,evidence) VALUES (?,?,?,?,?,?)',
                (job['id'], now(), action, job['revision'], 'owner' if owner else 'workflow', self.digest(job)))
        return dict(job=job, summary_html=self.summary())

    @staticmethod
    def approval_valid(approval):
        if not approval:
            return False
        return 0 <= (datetime.now(timezone.utc)-datetime.fromisoformat(approval['time'])).total_seconds() <= 3600

    @staticmethod
    def review_digest(job):
        evidence = dict(artifacts=job['artifacts'], lab=job.get('lab',{}), validations=job.get('agency',{}).get('validations',[]))
        return hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()

    @staticmethod
    def digest(job):
        return hashlib.sha256(json.dumps(job['artifacts'], sort_keys=True).encode()).hexdigest()

    def agent(self, name, job, data):
        if name in job['agents'] and name not in ('earnings','delivery'):
            raise ValueError('Agent already completed for this job; output is preserved')
        if name == 'scout':
            return dict(source=job['platform'], provenance='owner-provided listing; not fetched or independently verified', title=job['title'])
        if name == 'evaluator':
            if 'scout' not in job['agents']:
                raise ValueError('Run scout first')
            body = (job['title'] + '\n' + job['description']).lower()
            matched = [s for s in SKILLS if re.search(r'(?<!\w)' + re.escape(s) + r'(?!\w)', body)]
            risks = [s for s in ('24/7', 'guaranteed', 'certified', 'delete', 'database', 'migration', 'persistent storage', 'private network') if s in body]
            scope = 'docker_starter' if 'docker' in matched and not risks else 'manual_review'
            job['state'] = 'evaluated'
            return dict(score=min(95, len(matched)*12), matched=matched, flags=risks, scope=scope,
                        explanation='Keyword match only. Budget, client identity and feasibility require owner review.')
        if name == 'manager':
            if 'evaluator' not in job['agents']:
                raise ValueError('Run evaluator first')
            return dict(tasks=['Confirm scope and access requirements', 'Review proposal and record client acceptance',
                               'Prepare deployment starter files if supported', 'Review files and record live validation separately', 'Package handover'],
                        next='Review client questions, then proposal. No customer changes have occurred.')
        if name == 'client':
            if 'manager' not in job['agents']:
                raise ValueError('Run manager first')
            return dict(questions=['What application, runtime and start command are used?', 'Which repository and deployment environment are in scope?',
                                   'What is the readiness endpoint?', 'What is the rollback and backup plan?', 'What exact acceptance checks define completion?'],
                        reply='Thanks for sharing the project. Please confirm the application runtime, deployment target and acceptance checks so I can confirm scope and delivery time.',
                        sent=False)
        if name == 'proposal':
            if 'client' not in job['agents']:
                raise ValueError('Run client assistant first')
            job['state'] = 'proposal_ready'
            skills = ', '.join(job['agents']['evaluator']['output']['matched']) or 'the deployment requirements'
            return dict(draft=f"Hello, I reviewed your request: {job['title']}.\n\nThe request mentions {skills}. My stated skills require owner verification before this draft is sent. I would first confirm the runtime and acceptance criteria, inspect the configuration, prepare a focused change, and document validation and rollback.\n\nPlease share the current setup and the specific issue. I will confirm the scope, price and delivery time after reviewing them.",
                        sent=False, caveat='Template draft. Verify every claim; no price, deadline or outcome is promised.')
        if name == 'worker':
            if job['state'] != 'accepted' or not self.approval_valid(job['approvals'].get('work')):
                raise ValueError('Owner must accept the job and separately approve work')
            image = text(data.get('image'), 'existing application image', 200)
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/:@-]{0,199}', image):
                raise ValueError('Use one image reference without whitespace or shell syntax')
            port = data.get('port', 8000)
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError('Choose a valid internal application port')
            health = text(data.get('health_path', '/health'), 'health path', 200)
            if not re.fullmatch(r'/[A-Za-z0-9_./-]*', health):
                raise ValueError('Use a simple absolute health path')
            brief = job.get('agency',{}).get('brief',{})
            if brief.get('image') and brief['image'] != image:
                raise ValueError('Image differs from the agreed requirements')
            if brief.get('port') and brief['port'] != str(port):
                raise ValueError('Port differs from the agreed requirements')
            if brief.get('health_path') and brief['health_path'] != health:
                raise ValueError('Readiness path differs from the agreed requirements')
            if brief.get('configuration') and brief['configuration'].lower() not in ('none','no configuration'):
                raise ValueError('First worker cannot supply custom application configuration')
            files = {
                'compose.yaml': f'services:\n  app:\n    image: "{image}"\n    restart: "no"\n    mem_limit: 256m\n    cpus: 0.5\n    pids_limit: 100\n    labels:\n      io.ops-pilot.job: {job["id"]}\n    ports:\n      - "127.0.0.1:${{OPS_PILOT_HOST_PORT:-8080}}:{port}"\n    security_opt:\n      - no-new-privileges:true\n    cap_drop:\n      - ALL\n    logging:\n      driver: json-file\n      options:\n        max-size: "10m"\n        max-file: "3"\n',
                '.env.example': '# Put real secrets in your approved secret store. Never commit them.\n',
                'HANDOVER.md': f'# Docker deployment starter\n\nJob: {job["id"]}\n\nStatus: generated starter files, not deployed or runtime-verified.\n\n## Prerequisites\nConfirm that the existing image `{image}` is trusted and listens on port {port}. Docker Compose is required. No application code or image is built by this package. Review capabilities and writable paths for your application.\n\n## Review and validation\nRun `docker compose config --quiet` to validate the Compose file before starting anything. We use it to catch configuration errors.\nRun `docker compose up -d` only in the agreed test environment to start the application after approval.\nRun `curl --fail http://127.0.0.1:8080{health}` to check the agreed readiness endpoint. We use this to check an actual application response; it is not a load or security test.\nInspect application logs locally and redact secrets before sharing.\n\n## Rollback\nRecord the previous immutable image digest before deployment. Restore that digest in compose.yaml and recreate the service only after approval. Data changes and database rollback require a separate backup plan.\n\n## Still required\nRegistry access, runtime validation, DNS/TLS, backups, application configuration and customer acceptance. No infrastructure was changed.\n',
                'acceptance.json': json.dumps(dict(job=job['id'], image=image, internal_port=port, health_path=health, runtime_verified=False, customer_accepted=False), indent=2),
            }
            job['artifacts'] = files
            job['state'] = 'built'
            job['approvals'].pop('work')  # consumed; cannot replay
            return dict(files=list(files), executed=False, status='starter files generated', image=image)
        if name == 'reviewer':
            if job['state'] != 'built':
                raise ValueError('Generate starter files first')
            files = job['artifacts']
            checks = dict(required_files=all(p in files for p in ('compose.yaml','HANDOVER.md','acceptance.json','.env.example')),
                          loopback_binding='127.0.0.1:${OPS_PILOT_HOST_PORT:-8080}:' in files.get('compose.yaml',''),
                          no_privileged='privileged:' not in files.get('compose.yaml',''),
                          no_host_mounts='volumes:' not in files.get('compose.yaml',''))
            job['state'] = 'reviewed'
            return dict(checks=checks, checks_passed=all(checks.values()), digest=self.digest(job),
                        runtime_verified=False, security_audit=False, note='Static starter-bundle checks only. Run agreed acceptance checks before claiming completion.')
        if name == 'delivery':
            approval = job['approvals'].get('delivery')
            if job['state'] != 'reviewed' or not self.approval_valid(approval) or approval['digest'] != self.review_digest(job):
                raise ValueError('Owner must sign off this exact reviewed bundle first')
            job['state'] = 'packaged'
            job['package_digest'] = self.review_digest(job)
            return dict(download=f'/api/freelance/package?job_id={job["id"]}', sent=False,
                        note='Prepared ZIP, not submitted to the client; live validation remains unverified.')
        if name == 'earnings':
            with self.connect() as db:
                rows = db.execute('SELECT reference,gross,fee,time FROM payments WHERE job=? ORDER BY time', (job['id'],)).fetchall()
            return dict(currency=job['currency'], payments=[dict(reference=r,gross_cents=g,fee_cents=f,time=t) for r,g,f,t in rows],
                        net_cents=sum(g-f for _,g,f,_ in rows), source='owner-recorded; not bank or platform verified')
        raise ValueError('Unknown agent')

    def history(self, job_id):
        self.get(job_id)
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM revisions WHERE job=? ORDER BY revision DESC LIMIT 100',(job_id,))]

    def package(self, job_id):
        job = self.get(job_id)
        if job['state'] != 'packaged' or job.get('package_digest', self.review_digest(job)) != self.review_digest(job):
            raise ValueError('Review and sign off current artifacts and evidence before downloading')
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, contents in job['artifacts'].items():
                z.writestr(name, contents)
            validations = job.get('agency',{}).get('validations',[])
            if job.get('lab') or validations:
                z.writestr('EVIDENCE.json',json.dumps(dict(lab=job.get('lab',{}),validation_records=validations,
                    source='Owner records and practice evidence; not proof of customer acceptance'),indent=2))
        return buffer.getvalue()

    def summary(self):
        """Static safe HTML usable as n8n's form completion page (no script)."""
        state = self.state()
        esc = lambda v: html.escape(str(v), quote=True)
        cards = []
        for j in state['jobs']:
            details = ''.join(f'<details><summary>{esc(AGENTS[k][0])}</summary><pre>{esc(json.dumps(v["output"], indent=2))}</pre></details>' for k,v in j['agents'].items())
            details += ''.join(f'<details><summary>{esc(k)}</summary><pre>{esc(v)}</pre></details>' for k,v in j['artifacts'].items())
            details += '<details><summary>Project operations and evidence</summary><pre>'+esc(json.dumps(dict(records=j.get('agency',{}),finances=j['business_summary'],lab=j.get('lab',{})),indent=2))+'</pre></details>'
            f = j['business_summary']
            details = f'<p>Outstanding {esc(f["currency"])} {f["outstanding_cents"]/100:.2f} · Cash recorded {f["cash_received_cents"]/100:.2f}</p>'+details
            details += '<p>'+esc(' · '.join(f['alerts']))+'</p>'
            cards.append(f'<article><h2>{esc(j["title"])}</h2><p><strong>{esc(j["state"])}</strong> · ID {j["id"]} · Revision {j["revision"]}</p>{details}</article>')
        totals = ' · '.join(f'{t["currency"]} {t["net_cents"]/100:.2f} net recorded' for t in state['earnings']) or 'No payments recorded'
        return '<style>body{background:#101522;color:#e7eef9;font:15px system-ui}article{padding:20px;margin:16px 0;background:#1b2435;border:1px solid #344666;border-radius:16px}h1{color:#9bf6d3}summary{cursor:pointer;padding:10px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}p{line-height:1.7}</style><h1>Ops Pilot · Freelance desk</h1><p>9 local agent roles · '+str(len(state['jobs']))+' recent jobs · '+esc(totals)+'</p><p>Copy the job ID and current revision into the Control Desk form for the next action. This is a snapshot; submit Board again to refresh.</p>'+(''.join(cards) or '<p>No jobs yet. Use the Intake form to add a listing.</p>')+'<p>Connectors: not configured. Files are starter bundles. No live deployment, client messages or platform submission.</p>'
