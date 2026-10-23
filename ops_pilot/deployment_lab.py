"""Opt-in, single-owner disposable Compose lab; never a customer deployment worker."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Lab:
    def __init__(self, workspace):
        self.ws = workspace
        self.env = {k:v for k,v in os.environ.items() if not k.startswith(('DOCKER_', 'COMPOSE_'))}

    def docker(self, args, timeout=30):
        result = subprocess.run(['docker', *args], env=self.env, capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            # Docker logs can contain app secrets. Retain error class only.
            raise ValueError('Docker command failed: '+args[0])
        return result.stdout

    def preflight(self, job):
        if os.environ.get('OPS_PILOT_LAB') != '1':
            raise ValueError('Practice lab is disabled; opt in on an owned test host')
        context = json.loads(self.docker(['context', 'inspect']))
        endpoint = context[0]['Endpoints']['docker']['Host']
        if not endpoint.startswith('unix://') or not endpoint[7:].startswith('/'):
            raise ValueError('Lab requires a local Unix Docker endpoint')
        self.env['DOCKER_HOST'] = endpoint
        acceptance = json.loads(job['artifacts']['acceptance.json'])
        image = acceptance['image']
        allowed = os.environ.get('OPS_PILOT_LAB_IMAGES','').split(',')
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/:-]*@sha256:[a-f0-9]{64}',image) or image not in allowed:
            raise ValueError('Lab image must be immutable and explicitly allowlisted')
        inspected = json.loads(self.docker(['image','inspect',image]))
        if inspected[0].get('Config',{}).get('Volumes'):
            raise ValueError('Practice image must not declare persistent volumes')
        expected = self.ws.digest(job)
        return acceptance, expected

    def save(self, job, action):
        from .freelance import now
        with self.ws.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if action == 'lab_approval_consumed':
                active = [json.loads(r[0]) for r in db.execute('SELECT payload FROM jobs')]
                if any(x.get('lab',{}).get('status') in ('running','interrupted','cleanup_failed') for x in active):
                    raise ValueError('Another lab needs recovery; capacity is one')
            current = json.loads(db.execute('SELECT payload FROM jobs WHERE id=?',(job['id'],)).fetchone()[0])
            if current['revision'] != job['revision']:
                raise ValueError('Job changed while recording lab evidence')
            job['revision'] += 1; job['updated'] = now()
            db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(job),job['id']))
            db.execute('INSERT INTO events(job,time,action,revision) VALUES (?,?,?,?)',(job['id'],now(),action,job['revision']))
            db.execute('INSERT INTO audit(job,time,action,revision,actor,evidence) VALUES (?,?,?,?,?,?)',
                (job['id'],now(),action,job['revision'],'owner',json.dumps(job.get('lab',{}))))

    def owned(self, job):
        lab = job['lab']
        ids = self.docker(['ps','-aq','--filter','label=com.docker.compose.project='+lab['project']]).split()
        if not ids:
            return []
        containers = json.loads(self.docker(['inspect',*ids]))
        for c in containers:
            labels = c['Config'].get('Labels',{})
            if labels.get('io.ops-pilot.job') != job['id'] or labels.get('com.docker.compose.project') != lab['project']:
                raise ValueError('Ownership mismatch; cleanup refused')
        return ids

    def cleanup(self, job):
        ids = self.owned(job)
        if ids:
            self.docker(['rm','-f',*ids])
        # Only the uniquely named default network, checked by its Compose ownership label.
        name = job['lab']['project']+'_default'
        networks = self.docker(['network','ls','-q','--filter','name=^'+name+'$']).split()
        for ident in networks:
            n = json.loads(self.docker(['network','inspect',ident]))[0]
            if n.get('Labels',{}).get('com.docker.compose.project') != job['lab']['project'] or n.get('Containers'):
                raise ValueError('Network ownership mismatch or still in use')
            self.docker(['network','rm',ident])
        if self.owned(job):
            raise ValueError('Containers remain after cleanup')

    def run(self, payload, recover=False):
        import fcntl
        lock_path = self.ws.directory / '.lab.lock'
        fd = os.open(lock_path,os.O_CREAT | os.O_RDWR,0o600)
        with os.fdopen(fd,'w') as lock:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError('A lab process is active; wait before recovery') from exc
            return self._run(payload,recover)

    def _run(self, payload, recover=False):
        with self.ws.lock:
            job = self.ws.get(payload.get('job_id'))
            if payload.get('revision') != job['revision']:
                raise ValueError('Job changed; refresh the revision')
            acceptance, digest = self.preflight(job)
            if recover:
                if job.get('lab',{}).get('status') not in ('running','interrupted','cleanup_failed'):
                    raise ValueError('No interrupted lab to recover')
                job['lab']['status'] = 'interrupted'
                self.save(job,'lab_recovery_started')
                try:
                    self.cleanup(job)
                    job['lab'].update(status='recovered',cleanup='verified')
                except (ValueError, OSError, subprocess.TimeoutExpired):
                    job['lab'].update(status='cleanup_failed',cleanup='unverified')
                self.save(job,'lab_recovery_finished')
                return dict(job=job,summary_html=self.ws.summary())
            approval = job['approvals'].get('lab')
            if not approval or approval['digest'] != digest or datetime.fromisoformat(approval['expires']) <= datetime.now(timezone.utc):
                raise ValueError('Approve this exact bundle for the practice lab first')
            with self.ws.connect() as db:
                active = [json.loads(r[0]) for r in db.execute('SELECT payload FROM jobs')]
            if any(x.get('lab',{}).get('status') in ('running','interrupted','cleanup_failed') for x in active):
                raise ValueError('Lab capacity is one; recover outstanding runs first')
            run_id = secrets.token_hex(6)
            root = self.ws.directory / ('lab-'+run_id)
            root.mkdir(mode=0o700)
            for name in ('compose.yaml','acceptance.json'):
                (root/name).write_text(job['artifacts'][name]); (root/name).chmod(0o600)
            # Let Docker choose the loopback ephemeral host port (0), avoiding a bind race.
            self.env['OPS_PILOT_HOST_PORT'] = '0'
            project = 'opslab-'+job['id']+'-'+run_id
            job['approvals'].pop('lab')
            job['approvals'].pop('delivery',None)
            job['lab'] = dict(status='running',project=project,digest=digest,cleanup='pending',runtime_verified=False,
                customer_runtime_verified=False,started=datetime.now(timezone.utc).isoformat())
            self.save(job,'lab_approval_consumed')  # durable BEFORE Compose side effects
            compose = ['compose','-p',project,'-f',str(root/'compose.yaml')]
            try:
                config = json.loads(self.docker([*compose,'config','--format','json']))
                app = config['services']['app']
                if set(config['services']) != {'app'} or app.get('volumes') or app.get('privileged') or app.get('network_mode'):
                    raise ValueError('Unsafe generated Compose configuration')
                if app['image'] != acceptance['image'] or app.get('labels',{}).get('io.ops-pilot.job') != job['id']:
                    raise ValueError('Configuration identity mismatch')
                self.docker([*compose,'up','-d','--pull','never','--no-build'],timeout=60)
                mapping = self.docker([*compose,'port','app',str(acceptance['internal_port'])]).strip()
                if not re.fullmatch(r'127\.0\.0\.1:[0-9]+',mapping):
                    raise ValueError('Unexpected port mapping')
                opener = build_opener(NoRedirect,ProxyHandler({}))
                deadline = time.monotonic()+30
                while True:
                    try:
                        with opener.open(Request('http://'+mapping+acceptance['health_path']),timeout=2) as response:
                            if response.status != 200:
                                raise ValueError('Readiness expected HTTP 200')
                            response.read(4096)
                        break
                    except Exception:
                        if time.monotonic() >= deadline:
                            raise ValueError('Readiness deadline exceeded')
                        time.sleep(.5)
                job['lab'].update(status='passed',runtime_verified=True,endpoint=mapping+acceptance['health_path'],expected_status=200)
            except (ValueError, OSError, subprocess.TimeoutExpired, KeyError, json.JSONDecodeError) as exc:
                job['lab'].update(status='failed',error=type(exc).__name__)
            finally:
                try:
                    self.cleanup(job)
                    job['lab']['cleanup'] = 'verified'
                except (ValueError,OSError,subprocess.TimeoutExpired):
                    job['lab'].update(status='cleanup_failed',cleanup='unverified')
                job['lab']['finished'] = datetime.now(timezone.utc).isoformat()
                self.save(job,'lab_finished')
            return dict(job=job,summary_html=self.ws.summary())
