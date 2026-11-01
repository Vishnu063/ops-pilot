"""Single-owner bounded application fleet. No tenants or autonomous mutations."""
import hashlib
import json
import os
from pathlib import Path
import re
from .storage import private_database, PrivateConnection
import sqlite3
import stat
import threading
import time
import uuid

from .coolify import Coolify, ProviderError, Transport, clean, destination, identifier
from .providers import Provider


def configuration(path):
    path = Path(path).expanduser()
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_mode & 0o077 or path.stat().st_size > 32768:
        raise ValueError('Fleet config must be a private regular file of at most 32 KiB')
    value = json.loads(path.read_text())
    if not isinstance(value,dict) or set(value)-{'instances','applications','notification','docker_applications'}:
        raise ValueError('Use instances, applications and optional notification only; single owner only')
    instances, apps = value.get('instances',[]), value.get('applications',[])
    if not isinstance(instances,list) or not 0 <= len(instances) <= 4 or not isinstance(apps,list) or len(apps)>20:
        raise ValueError('Configure 1–4 instances and at most 20 monitored apps')
    ids=set()
    for instance in instances:
        if not isinstance(instance,dict) or set(instance)-{'id','base_url','token_env','repair_token_env','timeout','private_ips','allow_loopback','log_lines'}:
            raise ValueError('Unsupported instance configuration')
        key=identifier(instance.get('id'))
        if key in ids: raise ValueError('Duplicate instance ID')
        ids.add(key)
        if type(instance.get('allow_loopback',False)) is not bool: raise ValueError('allow_loopback must be boolean')
        ips=instance.get('private_ips',[])
        if not isinstance(ips,list) or len(ips)>8 or any(not isinstance(ip,str) for ip in ips): raise ValueError('Use explicit private IP exceptions')
        if not {'id','base_url','token_env'} <= set(instance): raise ValueError('Instance requires id, base_url and token_env')
        Coolify(instance)
        for field in ('token_env','repair_token_env'):
            if field=='repair_token_env' and field not in instance: continue
            if not isinstance(instance.get(field),str) or not re.fullmatch(r'OPS_PILOT_[A-Z0-9_]{1,60}',instance[field]):
                raise ValueError('Credentials must reference named OPS_PILOT_ environment bindings')
        if instance.get('repair_token_env') == instance['token_env']: raise ValueError('Use separate read and deploy credential bindings')
        if type(instance.get('timeout',3)) is not int or not 1<=instance.get('timeout',3)<=5: raise ValueError('Timeout must be 1–5 seconds')
        if type(instance.get('log_lines',100)) is not int or not 1<=instance.get('log_lines',100)<=200: raise ValueError('Log limit must be 1–200')
    appids=set(); targets=set()
    for app in apps:
        if not isinstance(app,dict) or set(app)-{'id','instance','uuid','name','health_url','expected_status','timeout','interval','failure_threshold','recovery_threshold','actions','notify','maintenance_until'}:
            raise ValueError('Unsupported application configuration')
        appid=identifier(app.get('id')); identifier(app.get('uuid'))
        if appid in appids or app.get('instance') not in ids or (app['instance'],app['uuid']) in targets: raise ValueError('Duplicate/unknown app target')
        appids.add(appid);targets.add((app['instance'],app['uuid']))
        if not isinstance(app.get('name'),str) or not 1<=len(app['name'])<=120: raise ValueError('Choose a bounded application name')
        instance=next(i for i in instances if i['id']==app['instance'])
        if app.get('health_url'): destination(app['health_url'],instance.get('private_ips',()),instance.get('allow_loopback',False))
        for key,default,low,high in [('interval',60,30,3600),('failure_threshold',3,1,10),('recovery_threshold',2,2,5),('timeout',3,1,5),('expected_status',200,200,299)]:
            if type(app.get(key,default)) is not int or not low<=app.get(key,default)<=high: raise ValueError('Invalid bounded '+key)
        if not isinstance(app.get('actions',[]),list) or set(app.get('actions',[]))-{'restart','redeploy'}: raise ValueError('Only explicit restart/redeploy actions are supported')
        if type(app.get('notify',True)) is not bool: raise ValueError('notify must be boolean')
        if type(app.get('maintenance_until',0)) not in (int,float) or not 0<=app.get('maintenance_until',0)<1e12: raise ValueError('Invalid maintenance deadline')
    docker_apps=value.get('docker_applications',[])
    if not isinstance(docker_apps,list) or len(docker_apps)>4: raise ValueError('At most four additional native Docker profiles')
    docker_ids=set();docker_targets=set()
    for app in docker_apps:
        if not isinstance(app,dict) or set(app)!={'id','config_file'}: raise ValueError('Docker profiles require id and private config_file')
        key=identifier(app['id'])
        if key in docker_ids or key in appids: raise ValueError('Duplicate Docker/application ID')
        docker_ids.add(key)
        config=Path(app['config_file']).expanduser()
        if config.is_symlink() or not stat.S_ISREG(config.stat().st_mode) or config.stat().st_mode & 0o077: raise ValueError('Docker profile must be a private regular file')
        from .config import load
        docker_config,_=load(config)
        target=(docker_config['docker_context'],docker_config['container'])
        if target in docker_targets: raise ValueError('Do not configure the same Docker target twice')
        docker_targets.add(target)
    if not instances and not docker_apps: raise ValueError('Configure at least one optional provider')
    notification=value.get('notification')
    if notification is not None:
        if not isinstance(notification,dict) or set(notification)!={'provider','token_env','chat_id','min_severity'} or notification['provider']!='telegram':
            raise ValueError('Use the documented Telegram notification profile')
        if not re.fullmatch(r'OPS_PILOT_[A-Z0-9_]{1,60}',notification['token_env']) or not re.fullmatch(r'-?[0-9]{1,20}',notification['chat_id']) or notification['min_severity'] not in ('warning','critical'):
            raise ValueError('Invalid Telegram notification profile')
    return value


class Fleet:
    def __init__(self, config, directory, providers: dict[str, Provider] | None=None, probe=None, clock=time.time, sleep=time.sleep, notifier=None,docker_factory=None):
        self.config=configuration(config)
        self.clock,self.sleep=clock,sleep
        self.instances={i['id']:i for i in self.config.get('instances',[])}
        self.providers=providers or {key:Coolify(i) for key,i in self.instances.items()}
        self.apps={a['id']:a for a in self.config.get('applications',[])}
        from .config import load
        from .service import Pilot
        self.dockers={app['id']:(docker_factory or Pilot)(load(app['config_file'])[0],Path(directory)/'fleet-docker'/app['id']) for app in self.config.get('docker_applications',[])}
        self.probe=probe or self.http_health
        self.notifier=notifier
        root=Path(directory)/'fleet'
        if root.is_symlink(): raise ValueError('Fleet state cannot be a symlink')
        self.path=root/'fleet.sqlite3'
        if self.path.is_symlink(): raise ValueError('Fleet database cannot be a symlink')
        private_database(self.path)
        self.lock=threading.Lock();self.stop_event=threading.Event();self.thread=None
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS records(kind TEXT,key TEXT,payload TEXT,PRIMARY KEY(kind,key));
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY,at REAL,kind TEXT,key TEXT,payload TEXT,previous TEXT,hash TEXT);
            CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'append only'); END;''')

    def connect(self): return sqlite3.connect(private_database(self.path),timeout=5,factory=PrivateConnection)

    def get(self,db,kind,key,default=None):
        row=db.execute('SELECT payload FROM records WHERE kind=? AND key=?',(kind,key)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self,db,kind,key,value):
        raw=json.dumps(value,sort_keys=True)
        if len(raw)>65536: raise ValueError('Record exceeds evidence bound')
        if not self.get(db,kind,key) and db.execute('SELECT count(*) FROM records').fetchone()[0]>=4000: raise ValueError('Fleet retention reached; archive private state')
        db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?)',(kind,key,raw))

    def audit(self,db,kind,key,value):
        if db.execute('SELECT count(*) FROM audit').fetchone()[0]>=20000: raise ValueError('Fleet audit retention reached; archive privately before continuing')
        raw=json.dumps(value,sort_keys=True);at=self.clock()
        previous=db.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone();previous=previous[0] if previous else 'genesis'
        digest=hashlib.sha256(json.dumps([at,kind,key,raw,previous],separators=(',',':')).encode()).hexdigest()
        db.execute('INSERT INTO audit(at,kind,key,payload,previous,hash) VALUES (?,?,?,?,?,?)',(at,kind,key,raw,previous,digest))

    def all(self,db,kind): return [json.loads(r[0]) for r in db.execute('SELECT payload FROM records WHERE kind=? ORDER BY rowid DESC LIMIT 200',(kind,))]

    def http_health(self,app):
        if not app.get('health_url'): return None
        instance=self.instances[app['instance']]
        try:
            status,_,_=Transport(instance.get('private_ips',()),instance.get('allow_loopback',False)).request('GET',app['health_url'],{'Accept':'application/json'},None,app.get('timeout',3))
            return status==app.get('expected_status',200)
        except ProviderError:
            return False

    def state(self):
        with self.connect() as db:
            apps=[]
            for key,app in self.apps.items():
                stored=self.get(db,'app',key,{})
                connection=self.get(db,'connection',app['instance'],{})
                apps.append(dict(id=key,name=clean(app['name'],limit=120),provider='coolify',instance=app['instance'],
                    target=app['uuid'],available_actions=[a for a in app.get('actions',[]) if a in connection.get('actions',[]) and (a!='redeploy' or stored.get('observed',{}).get('pinned_release'))],**stored,connection_stale=connection.get('status')!='connected'))
            return dict(enabled=True,single_owner=True,instances=[dict(id=k,**self.get(db,'connection',k,{'status':'unchecked'})) for k in self.instances],
                applications=apps,docker_applications=[dict(id=key,provider='docker',state=pilot.state()) for key,pilot in self.dockers.items()],incidents=self.all(db,'incident'),plans=self.all(db,'plan'),notifications=self.all(db,'notification'),
                maintenance='Set maintenance_until in the private local configuration; restart reloads it',
                audit_tail=[dict(seq=s,at=a,kind=k,key=key,hash=h) for s,a,k,key,h in db.execute('SELECT seq,at,kind,key,hash FROM audit ORDER BY seq DESC LIMIT 30')])

    def _notify(self,event,key,app=None,severity='warning'):
        config=self.config.get('notification')
        if not config or app and (not app.get('notify',True) or app.get('maintenance_until',0)>self.clock()): return
        if config['min_severity']=='critical' and severity!='critical': return
        nid=event+':'+key
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if self.get(db,'notification',nid): return
            previous=self.all(db,'notification')
            if any(self.clock()-p['at']<30 for p in previous):
                self.put(db,'notification',nid,dict(id=nid,event=event,at=self.clock(),status='suppressed_rate_limit'));return
            # Before I/O: no replay after restart or an ambiguous delivery timeout.
            self.put(db,'notification',nid,dict(id=nid,event=event,at=self.clock(),status='attempting'))
        try:
            if self.notifier: receipt=self.notifier(config,event)
            else:
                from .notifications import telegram
                receipt=telegram(config,event)
            status='confirmed' if receipt else 'failed_or_unknown'
        except (OSError,RuntimeError,ValueError): status='failed_or_unknown'
        with self.connect() as db:
            self.put(db,'notification',nid,dict(id=nid,event=event,at=self.clock(),status=status))
            self.audit(db,'notification',nid,{'status':status})

    def connection(self,key):
        provider=self.providers[key]
        try:
            details=provider.connection();apps=provider.discover()
            try: servers=provider.servers()
            except (ProviderError,ValueError): servers=[]
            result=dict(status='connected',checked_at=self.clock(),servers=servers,discovered=apps,**details)
        except (ProviderError,ValueError) as exc:
            result=dict(status='disconnected',checked_at=self.clock(),error=exc.code if isinstance(exc,ProviderError) else 'response')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=self.get(db,'connection',key,{})
            # Keep inventory during an outage; mark it stale, never convert every app to down.
            if result['status']=='disconnected':
                result['outage_id']=old.get('outage_id') if old.get('status')=='disconnected' else uuid.uuid4().hex
                result['discovered']=old.get('discovered',[]);result['servers']=old.get('servers',[])
            self.put(db,'connection',key,result)
            if old.get('status')!=result['status']: self.audit(db,'connection',key,{'status':result['status']})
        if result['status']=='disconnected':
            monitored=[a for a in self.apps.values() if a['instance']==key]
            if not monitored or not all(a.get('maintenance_until',0)>self.clock() for a in monitored):
                self._notify('monitoring_connection_lost',key+':'+result['outage_id'])
        return result

    def _snapshot(self,app):
        provider=self.providers[app['instance']];observed=provider.inspect(app['uuid'])
        try:
            deployments=provider.deployments(app['uuid']);deployment_error=None
        except (ProviderError,ValueError): deployments=[];deployment_error='Deployment history unavailable'
        return dict(observed=observed,deployments=deployments,deployment_error=deployment_error,endpoint_healthy=self.probe(app))

    def _reason(self,snapshot):
        runtime=snapshot['observed']['runtime'];deployments=snapshot['deployments'];endpoint=snapshot['endpoint_healthy']
        latest=deployments[0]['status'] if deployments else 'unknown'
        if latest in ('in_progress','queued','pending','building'): return None,'deploying'
        if latest in ('failed','cancelled-by-user'): return 'failed_deployment','failed'
        if runtime in ('stopped','exited'): return 'container_stopped','stopped'
        if runtime=='restarting': return 'container_restarting','unhealthy'
        if snapshot['observed'].get('provider_health')=='unhealthy': return 'provider_health_failure','unhealthy'
        if endpoint is False: return 'health_check_failure','unhealthy'
        if runtime=='running' and endpoint is True: return None,'healthy'
        return None,'unknown'

    def poll(self,only=None,force=False):
        if only is not None and only not in self.apps: raise ValueError('Unknown configured application')
        if not self.lock.acquire(blocking=False): raise ValueError('Fleet operation already running')
        try:
            due=[]
            with self.connect() as db:
                for key,app in self.apps.items():
                    stored=self.get(db,'app',key,{})
                    if (only is None or only==key) and (force or self.clock()-stored.get('attempted_at',stored.get('checked_at',0))>=app.get('interval',60)): due.append((key,app))
            with self.connect() as db:
                for key,_ in due:
                    stored=self.get(db,'app',key,{})
                    if force and self.clock()-stored.get('attempted_at',0)<5: raise ValueError('Wait five seconds before another manual check')
                    stored['attempted_at']=self.clock();self.put(db,'app',key,stored)
            connection_ids={app['instance'] for _,app in due}
            if not self.apps: connection_ids=set(self.instances) if force else {key for key in self.instances if self.clock()-self.get_connection_time(key)>=60}
            connections={i:self.connection(i) for i in connection_ids}
            for key,app in due:
                if connections[app['instance']]['status']!='connected':
                    with self.connect() as db:
                        stored=self.get(db,'app',key,{})
                        stored.update(failures=0,successes=0);self.put(db,'app',key,stored)
                    continue
                with self.connect() as db:
                    execution_before=self.get(db,'execution',key,{})
                    if execution_before.get('status')=='executing': continue
                try: snapshot=self._snapshot(app)
                except (ProviderError,ValueError):
                    # Connection/evidence loss never becomes proof of application failure.
                    with self.connect() as db:
                        stored=self.get(db,'app',key,{})
                        stored.update(checked_at=self.clock(),health='unknown',failures=0,successes=0,evidence_error='Application evidence unavailable')
                        self.put(db,'app',key,stored)
                    continue
                reason,health=self._reason(snapshot)
                with self.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if self.get(db,'execution',key,{})!=execution_before: continue
                    stored=self.get(db,'app',key,{})
                    failures=stored.get('failures',0)+1 if reason else 0
                    successes=stored.get('successes',0)+1 if health=='healthy' else 0
                    current=dict(snapshot,attempted_at=self.clock(),checked_at=self.clock(),health=health,failures=failures,successes=successes,incident_id=stored.get('incident_id'))
                    active=self.get(db,'incident',current['incident_id']) if current['incident_id'] else None
                    maintained=app.get('maintenance_until',0)>self.clock()
                    created=False;restored=False
                    if reason and failures>=app.get('failure_threshold',3) and not active and not maintained:
                        incident_id=uuid.uuid4().hex
                        active=dict(id=incident_id,app=key,status='open',severity='warning',detected_at=self.clock(),classification=reason,
                            confidence='observed failure; root cause unconfirmed',missing_evidence=['Production resource metrics and business transaction checks'],
                            recommendation='Inspect recent deployments and bounded logs; compare the configured readiness endpoint before approving a disruptive action.',
                            evidence=snapshot,events=[dict(at=self.clock(),event='detected')])
                        current['incident_id']=incident_id;created=True
                    if active:
                        active['evidence']=snapshot;active['last_checked']=self.clock()
                        if successes>=app.get('recovery_threshold',2):
                            active.update(status='resolved',resolved_at=self.clock());active['events'].append(dict(at=self.clock(),event='sustained_health_observed'))
                            current['incident_id']=None;restored=True
                        self.put(db,'incident',active['id'],active)
                        if created or restored: self.audit(db,'incident',active['id'],{'status':active['status'],'classification':active['classification']})
                    self.put(db,'app',key,current)
                if created: self._notify('incident_detected',active['id'],app)
                if restored: self._notify('application_restored',active['id'],app)
            return self.state()
        finally: self.lock.release()

    def _policy(self,app):
        instance=self.instances[app['instance']]
        # Rotation or endpoint/config edits invalidate pending permissions, without storing tokens.
        secrets=[os.environ.get(instance.get(k,''),'') for k in ('token_env','repair_token_env')]
        return hashlib.sha256(json.dumps([app,instance,secrets],sort_keys=True).encode()).hexdigest()

    def fingerprint(self,app,snapshot):
        return hashlib.sha256(json.dumps([self._policy(app),snapshot],sort_keys=True).encode()).hexdigest()

    def incident_event(self,db,incident_id,event,plan_id):
        incident=self.get(db,'incident',incident_id)
        if incident:
            incident['events']=(incident.get('events',[])+[dict(at=self.clock(),event=event,plan_id=plan_id)])[-64:]
            self.put(db,'incident',incident_id,incident)

    def plan(self,key,action):
        app=self.apps[key];provider=self.providers[app['instance']]
        if action not in app.get('actions',[]) or not app.get('health_url') or app.get('maintenance_until',0)>self.clock(): raise ValueError('Action not explicitly enabled or readiness/maintenance policy disallows it')
        connection=provider.connection()
        if action not in connection['actions']: raise ValueError('Unsupported provider version or deploy permission binding')
        snapshot=self._snapshot(app)
        if not snapshot['observed'].get('application_id') or self._reason(snapshot)[0] is None or snapshot['deployment_error']: raise ValueError('Need a current evidenced failure and deployment history; do not conflict with an active/unknown deployment')
        if action=='redeploy' and not snapshot['observed'].get('pinned_release'): raise ValueError('Redeploy requires a configured immutable commit; floating branches/tags are unsupported')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');stored=self.get(db,'app',key,{})
            if not stored.get('incident_id'): raise ValueError('Investigate a current incident before planning')
            execution=self.get(db,'execution',key,{})
            if execution.get('status')=='executing' or self.clock()-execution.get('at',0)<300: raise ValueError('Execution in progress or five-minute cooldown')
            for (payload,) in db.execute("SELECT payload FROM records WHERE kind='plan'").fetchall():
                old=json.loads(payload)
                if old['app']==key and old['status'] in ('proposed','approved'):
                    old['status']='superseded';self.put(db,'plan',old['id'],old)
            plan=dict(id=uuid.uuid4().hex,app=key,instance=app['instance'],target=app['uuid'],action=action,
                incident_id=stored['incident_id'],created_at=self.clock(),expires_at=self.clock()+120,status='proposed',
                reason='Owner-requested response to observed incident; root cause remains unconfirmed',
                expected_impact='Application interruption; redeploy may use current upstream source and run configured migrations',
                required_permission='Separate Coolify deploy token and fresh Ops Pilot owner approval',
                preconditions=snapshot,fingerprint=self.fingerprint(app,snapshot),
                verification='Exact target running, receipt deployment finished, configured endpoint sustained healthy')
            self.put(db,'plan',plan['id'],plan);self.audit(db,'plan',plan['id'],plan)
            self.incident_event(db,plan['incident_id'],'plan_proposed',plan['id'])
        self._notify('recovery_approval_required',plan['id'],app)
        return plan

    def approve(self,key,planid):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');plan=self.get(db,'plan',planid)
            if not plan or plan['app']!=key or plan['status']!='proposed' or plan['expires_at']<=self.clock() or plan['fingerprint']!=self.fingerprint(self.apps[key],plan['preconditions']): raise ValueError('Plan missing, changed, expired or not proposed')
            if self.apps[key].get('maintenance_until',0)>self.clock(): raise ValueError('Maintenance blocks approval')
            plan.update(status='approved',approved_at=self.clock());self.put(db,'plan',planid,plan);self.audit(db,'approval',planid,{'decision':'approve','app':key,'fingerprint':plan['fingerprint']})
            self.incident_event(db,plan['incident_id'],'owner_approved',planid)
        return plan

    def execute(self,key,planid):
        app=self.apps[key];provider=self.providers[app['instance']]
        with self.connect() as db:
            plan=self.get(db,'plan',planid)
        if not plan or plan['app']!=key or plan['status']!='approved' or plan['expires_at']<=self.clock(): raise ValueError('Fresh separate approval required')
        if app.get('maintenance_until',0)>self.clock(): raise ValueError('Maintenance blocks execution')
        capabilities=provider.connection()
        current=self._snapshot(app)
        if plan['target']!=app['uuid'] or plan['action'] not in app.get('actions',[]) or plan['action'] not in capabilities['actions'] or plan['fingerprint']!=self.fingerprint(app,current): raise ValueError('Exact target, deployment, policy or health evidence changed; replan')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');latest=self.get(db,'plan',planid);execution=self.get(db,'execution',key,{})
            stored=self.get(db,'app',key,{})
            if latest['status']!='approved' or latest['expires_at']<=self.clock() or stored.get('incident_id')!=plan['incident_id'] or execution.get('status')=='executing' or self.clock()-execution.get('at',0)<300: raise ValueError('Approval consumed, incident changed or conflicting operation/cooldown')
            plan.update(status='consumed',consumed_at=self.clock());self.put(db,'plan',planid,plan)
            self.put(db,'execution',key,dict(plan_id=planid,at=self.clock(),status='executing'))
            self.audit(db,'execution_started',planid,{'app':key,'action':plan['action'],'target':plan['target']})
            self.incident_event(db,plan['incident_id'],'execution_started',planid)
        receipt=None
        try:
            receipt=provider.execute(app['uuid'],plan['action'])
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                plan['receipt']=receipt;self.put(db,'plan',planid,plan)
                self.audit(db,'deployment_receipt',planid,receipt)
            result=self.verify(app,receipt)
        except (ProviderError,ValueError,OSError): result=dict(status='unknown',receipt=receipt,reason='Action/verification failed or timed out; approval remains consumed. Inspect remote deployment before any further action.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');plan['result']=result;self.put(db,'plan',planid,plan)
            self.put(db,'execution',key,dict(plan_id=planid,at=self.clock(),status=result['status']))
            self.audit(db,'execution_result',planid,result)
            self.incident_event(db,plan['incident_id'],'verification_'+result['status'],planid)
        self._notify('recovery_completed' if result['status']=='verified' else 'recovery_failed',planid,app)
        return result

    def verify(self,app,receipt):
        provider=self.providers[app['instance']];successes=0;checks=[]
        for attempt in range(5):
            deployment=provider.deployment(receipt['deployment_uuid'],app['uuid'])
            observed=provider.inspect(app['uuid']);endpoint=self.probe(app)
            ok=(deployment.get('uuid')==receipt['deployment_uuid'] and deployment.get('application_uuid')==app['uuid']
                and observed['uuid']==app['uuid'] and observed['runtime']=='running'
                and observed.get('provider_health')!='unhealthy' and endpoint is True and deployment['status']=='finished')
            checks.append(dict(runtime=observed['runtime'],endpoint_healthy=endpoint,deployment=deployment['status']))
            successes=successes+1 if ok else 0
            if successes>=app.get('recovery_threshold',2): return dict(status='verified',receipt=receipt,checks=checks)
            if attempt<4: self.sleep(1)
        return dict(status='needs_attention',receipt=receipt,checks=checks,reason='Queued API acceptance is not proof of recovery; inspect deployment and endpoint')

    def action(self,data):
        if isinstance(data,dict) and data.get('app') in self.dockers:
            if set(data)-{'action','app','plan_id'} or data.get('action') not in ('investigate','plan','approve','apply'): raise ValueError('Choose an existing native Docker action')
            if not self.lock.acquire(blocking=False): raise ValueError('Another fleet operation is running')
            try:
                return self.dockers[data['app']].action(data['action'],data.get('plan_id'))
            finally:
                self.lock.release()
        if not isinstance(data,dict) or set(data)-{'action','app','plan_id','operation'} or data.get('app') not in self.apps: raise ValueError('Choose one configured application')
        action=data.get('action');key=data['app']
        if action=='check': return self.poll(key,force=True)
        if action not in ('plan','approve','execute','logs'): raise ValueError('Unsupported fleet action')
        if not self.lock.acquire(blocking=False): raise ValueError('Fleet operation already running')
        try:
            if action=='plan': return self.plan(key,data.get('operation'))
            if action=='approve': return self.approve(key,data.get('plan_id'))
            if action=='execute': return self.execute(key,data.get('plan_id'))
            app=self.apps[key];logs=self.providers[app['instance']].logs(app['uuid'])
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE');stored=self.get(db,'app',key,{})
                incident=self.get(db,'incident',stored.get('incident_id'))
                if not incident: raise ValueError('Collect incident evidence before fetching logs')
                incident['logs']=logs;self.put(db,'incident',incident['id'],incident);self.audit(db,'logs_collected',incident['id'],{'app':key,'bounded':True})
            return dict(logs=logs,untrusted=True)
        finally: self.lock.release()

    def get_connection_time(self,key):
        with self.connect() as db: return self.get(db,'connection',key,{}).get('checked_at',0)

    def report(self,after=0):
        if type(after) is not int or after<0: raise ValueError('Invalid audit cursor')
        with self.connect() as db:
            rows=db.execute('SELECT seq,at,kind,key,payload,previous,hash FROM audit WHERE seq>? ORDER BY seq LIMIT 100',(after,)).fetchall()
            more=bool(rows and db.execute('SELECT 1 FROM audit WHERE seq>?',(rows[-1][0],)).fetchone())
        return dict(format='ops-pilot-fleet-v1',single_owner=True,complete=not more,next_after=rows[-1][0] if rows else after,state=self.state(),audit=[dict(zip(('seq','at','kind','key','payload','previous','hash'),r)) for r in rows],
                    limitations='Local owner controls storage. Filtered evidence; no customer/tenant isolation, no root-cause guarantee, no generic rollback.')

    def start(self):
        for pilot in self.dockers.values(): pilot.start()
        def loop():
            while not self.stop_event.is_set():
                try: self.poll()
                except (ValueError,OSError,RuntimeError): pass
                self.stop_event.wait(5)
        self.thread=threading.Thread(target=loop,daemon=True);self.thread.start()

    def close(self):
        self.stop_event.set()
        for pilot in self.dockers.values(): pilot.close()
        if self.thread: self.thread.join(timeout=1)
