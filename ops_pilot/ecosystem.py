"""Optional incident event ledger around Pilot's existing approval/repair engine."""
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from triage.ecosystem import validate, envelope, diagnose, verify
from triage.integrations import redact, ToolAdapter


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


class EventHub:
    def __init__(self,pilot,directory,service):
        if not pilot:raise ValueError('Ecosystem requires an explicitly configured Pilot target')
        if not isinstance(service,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',service):raise ValueError('Use one explicit service ID')
        self.prom_url=os.environ.get('OPS_PILOT_PROMETHEUS_URL')
        self.prom_job=os.environ.get('OPS_PILOT_PROM_JOB','ecosystem-app')
        self.pilot=pilot;self.service=service;self.root=Path(directory)/'ecosystem'
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True);self.root.chmod(0o700)
        self.path=self.root/'events.sqlite3';self.lock=threading.RLock()
        self.binding=digest({'config':pilot.config,'health':pilot.health,'prometheus_url':self.prom_url,'prometheus_job':self.prom_job,'service':self.service})
        self.keys={name:os.environ.get('OPS_PILOT_EVENTS_'+name.upper(),'') for name in ('cloudlaunch','platform','alertmanager','labs')}
        self.read_key=os.environ.get('OPS_PILOT_READ_TOKEN','')
        for value in [*self.keys.values(),self.read_key]:
            if value and (len(value)<32 or len(value)>512 or any(ord(c)<33 for c in value)):raise ValueError('Use private tokens of at least 32 characters')
        configured=[v for v in [*self.keys.values(),self.read_key] if v]
        if len(configured)!=len(set(configured)):raise ValueError('Source and read tokens must be distinct')
        self.rate={}
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS incoming(id TEXT PRIMARY KEY,hash TEXT,incident TEXT,payload TEXT,at REAL);
            CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY,service TEXT,fingerprint TEXT,status TEXT,revision INTEGER,payload TEXT);
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY,incident TEXT,time REAL,actor TEXT,action TEXT,payload TEXT,previous TEXT,hash TEXT);
            CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'audit is append only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'audit is append only'); END;''')
        self.path.chmod(0o600)
    def connect(self):return sqlite3.connect(self.path,timeout=10)
    def authorized(self,header,read=False):
        supplied=header.removeprefix('Bearer ') if header.startswith('Bearer ') else ''
        keys={'reader':self.read_key} if read else self.keys
        for source,key in keys.items():
            if key and secrets.compare_digest(supplied,key):return source
        return None
    def _audit(self,db,incident,actor,action,payload):
        raw=json.dumps(redact(payload),sort_keys=True)
        old=db.execute('SELECT hash FROM audit ORDER BY seq DESC LIMIT 1').fetchone();previous=old[0] if old else 'genesis'
        at=time.time();hash_value=digest([previous,incident,at,actor,action,raw])
        db.execute('INSERT INTO audit(incident,time,actor,action,payload,previous,hash) VALUES (?,?,?,?,?,?,?)',(incident,at,actor,action,raw,previous,hash_value))
    def ingest(self,event,source):
        validate(event)
        if event['type'] not in ('DeploymentEvent','MonitoringAlert') or event['source']!=source or event['service']!=self.service:
            raise ValueError('Source, service or event capability is not allowlisted')
        # Replay/late-event window; resolved notifications never establish recovery.
        when=datetime.fromisoformat(event['timestamp'].replace('Z','+00:00')).timestamp()
        if not time.time()-7*86400<=when<=time.time()+300:raise ValueError('Event timestamp outside ingestion window')
        key=digest([source,event['id']]);hashed=digest(event);data=event['data']
        failure=data['status']=='firing' if event['type']=='MonitoringAlert' else data['status'] in ('failed','rollback_failed','security_failed')
        fingerprint=str(data.get('fingerprint') or event['correlation_id'])[:200]
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            seen=db.execute('SELECT hash,incident FROM incoming WHERE id=?',(key,)).fetchone()
            if seen:
                if seen[0]!=hashed:raise ValueError('Event id was reused with changed content')
                return {'accepted':True,'duplicate':True,'incident_id':seen[1]}
            if db.execute('SELECT COUNT(*) FROM incoming').fetchone()[0]>=10000:raise ValueError('Event retention limit reached; archive private evidence before continuing')
            old=db.execute("SELECT payload FROM incidents WHERE service=? AND fingerprint=? AND status NOT IN ('verified','rejected') ORDER BY rowid DESC LIMIT 1",(self.service,fingerprint)).fetchone()
            incident=json.loads(old[0]) if old else None
            duplicate=bool(incident and failure and time.time()-incident['last_seen']<300)
            if not incident and failure:
                ident=digest([self.service,fingerprint,event['id']])[:24]
                incident=dict(id=ident,service=self.service,correlation_id=event['correlation_id'],fingerprint=fingerprint,status='detected',revision=0,
                    binding=self.binding,created=time.time(),last_seen=time.time(),event_ids=[],plan_id=None,busy=False,external_resolved=False)
            if incident:
                incident['event_ids']=(incident['event_ids']+[event['id']])[-100:];incident['last_seen']=time.time()
                if data['status']=='resolved':incident['external_resolved']=True
                self._save(db,incident)
            ident=incident['id'] if incident else None
            db.execute('INSERT INTO incoming VALUES (?,?,?,?,?)',(key,hashed,ident,json.dumps(redact(event)),time.time()))
            self._audit(db,ident,source,'event_received',{'id':event['id'],'type':event['type'],'status':data['status'],'duplicate_fingerprint':duplicate})
        return {'accepted':True,'duplicate':duplicate,'incident_id':ident}
    def alertmanager(self,payload):
        if not isinstance(payload,dict) or not isinstance(payload.get('alerts'),list) or not 1<=len(payload['alerts'])<=100:raise ValueError('Use a bounded Alertmanager webhook')
        results=[]
        for alert in payload['alerts']:
            labels=alert.get('labels',{});fingerprint=alert.get('fingerprint')
            if not isinstance(fingerprint,str) or not fingerprint or labels.get('service')!=self.service:raise ValueError('Alert service/fingerprint required')
            status=alert.get('status')
            data={'fingerprint':fingerprint,'status':status,'alertname':str(labels.get('alertname','unknown'))[:100],
                  'labels':{k:str(labels[k])[:200] for k in ('severity','job','service') if k in labels}}
            # Stable id across Alertmanager retries/restarts, but changes on new firing cycle.
            ident=digest([fingerprint,status,alert.get('startsAt'),alert.get('endsAt') if status=='resolved' else None])
            event=envelope('MonitoringAlert','alertmanager',self.service,data,correlation_id='alert-'+fingerprint,event_id=ident)
            event['timestamp']=alert.get('endsAt') if status=='resolved' else alert.get('startsAt')
            results.append(self.ingest(event,'alertmanager'))
        return {'accepted':True,'results':results}
    def monitor_check(self):
        url=self.prom_url
        if not url:return None
        from urllib.parse import urlencode
        job=self.prom_job
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',job):raise ValueError('Select one explicit Prometheus scrape job')
        try:
            selector='probe_success{job="'+job+'",service="'+self.service+'"}'
            query=selector+' and ((time() - timestamp('+selector+')) < 30)'
            raw,_=ToolAdapter('prometheus',{'base_url':url}).request('/api/v1/query?'+urlencode({'query':query}))
            values=json.loads(raw).get('data',{}).get('result',[])
            if not values:return None
            return all(float(v['value'][1])==1 and time.time()-float(v['value'][0])<30 for v in values)
        except (ValueError,TypeError,KeyError,OSError,RuntimeError):return None
    def _save(self,db,incident):
        incident['revision']+=1
        db.execute('INSERT INTO incidents VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,revision=excluded.revision,payload=excluded.payload',
          (incident['id'],incident['service'],incident['fingerprint'],incident['status'],incident['revision'],json.dumps(incident)))
    def get(self,ident):
        if not isinstance(ident,str) or len(ident)!=24:raise ValueError('Select a current incident')
        with self.connect() as db:row=db.execute('SELECT payload FROM incidents WHERE id=?',(ident,)).fetchone()
        if not row:raise ValueError('Incident missing')
        return json.loads(row[0])
    def state(self):
        with self.connect() as db:
            incidents=[json.loads(r[0]) for r in db.execute('SELECT payload FROM incidents ORDER BY rowid DESC LIMIT 30')]
            audits=[dict(seq=s,incident=i,time=t,actor=a,action=act,payload=json.loads(p),previous=prev,hash=h) for s,i,t,a,act,p,prev,h in db.execute('SELECT * FROM audit ORDER BY seq DESC LIMIT 100')]
        return dict(connected=True,service=self.service,read_only_default=True,incidents=incidents,audit=audits,
          limits='One configured Docker target. Webhooks never execute or approve. Audit hashes detect changes, not compromise by the local owner/root.')
    def action(self,payload,actor='local-owner'):
        if not isinstance(payload,dict) or set(payload)!={'incident_id','revision','action','plan_id'} or payload['action'] not in ('investigate','plan','approve','reject','apply','verify'):
            raise ValueError('Select a bounded existing incident operation')
        import fcntl
        with (self.root/'operation.lock').open('a') as process_lock:
            try:fcntl.flock(process_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Another incident operation is running') from None
            return self._action(payload,actor)
    def _action(self,payload,actor):
        action=payload['action'];incident=self.get(payload['incident_id'])
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE');fresh=self.get(incident['id'])
            if type(payload['revision']) is not int or fresh['revision']!=payload['revision'] or fresh['binding']!=self.binding or fresh['busy']:
                raise ValueError('Incident/configuration changed or operation interrupted; inspect saved state')
            if incident['status'] in ('verified','rejected'):raise ValueError('Terminal incident is read-only')
            if action in ('approve','apply','reject') and (not incident.get('plan_id') or payload['plan_id']!=incident['plan_id']):raise ValueError('Review the exact incident plan first')
            if action=='apply' and incident['status']!='approved':raise ValueError('Explicit incident approval is required before execution')
            incident.update(busy=True,operation=action)
            if action=='apply':incident['status']='executing'
            self._save(db,incident);self._audit(db,incident['id'],actor,action+'_requested',{'plan_id':incident.get('plan_id')})
        try:
            if action=='investigate':
                report=self.pilot.action('investigate');incident['evidence']=redact(report)
                from triage.ecosystem import k8sgpt
                incident['k8sgpt']=k8sgpt(os.environ.get('OPS_PILOT_K8SGPT_CONTEXT',''),os.environ.get('OPS_PILOT_K8SGPT_NAMESPACE',''),os.environ.get('OPS_PILOT_K8SGPT')=='1')
                with self.connect() as db:raw=db.execute('SELECT payload FROM incoming WHERE incident=? ORDER BY at DESC LIMIT 1',(incident['id'],)).fetchone()[0]
                with self.connect() as db:
                    recent=[json.loads(r[0]) for r in db.execute('SELECT payload FROM incoming WHERE at>? ORDER BY at DESC LIMIT 50',(time.time()-86400,))]
                incident['recent_deployments']=[e for e in recent if e['type']=='DeploymentEvent'][:5]
                incident['diagnosis']=diagnose(json.loads(raw),report)
                incident['diagnosis']['data']['evidence_refs'] += [e['id'] for e in incident['recent_deployments']]
                incident['diagnosis']['data']['deployment_correlation']='Recent same-service events are context, not proof of causation.'
                incident['status']='diagnosed'
            elif action=='plan':
                if incident['status']!='diagnosed':raise ValueError('Investigate before planning')
                plan=self.pilot.action('plan');incident['plan_id']=plan['id']
                incident['proposal']=envelope('RemediationProposal','ops-pilot',self.service,dict(incident_id=incident['id'],plan_id=plan['id'],
                    action={'operation':'docker.restart','argv':plan['command'],'target':plan['target']},risk=plan.get('risk'),
                    rollback=plan.get('rollback'),verification={'native':plan.get('verification'),'http_policy':self.pilot.health,'monitoring':'Fresh service-scoped Prometheus application probe and authenticated Alertmanager resolution'},evidence_refs=incident['event_ids']),incident['correlation_id'])
                incident['status']='pending_approval'
            elif action in ('approve','reject'):
                if incident['status'] not in ('pending_approval','approved'):raise ValueError('Approval is not pending')
                self.pilot.action('approve' if action=='approve' else 'cancel',incident['plan_id'])
                incident['approval']=envelope('ApprovalDecision','ops-pilot',self.service,dict(incident_id=incident['id'],plan_id=incident['plan_id'],decision=action,actor=actor),incident['correlation_id'])
                incident['status']='approved' if action=='approve' else 'rejected'
            elif action=='apply':
                if not incident.get('approval') or incident['approval']['data']['decision']!='approve':raise ValueError('Explicit incident approval is required')
                outcome=self.pilot.action('apply',incident['plan_id']);incident['execution']=redact(outcome)
                state_good=outcome.get('infrastructure_status')=='verified';http_good=outcome.get('application_health',{}).get('healthy')
                # Monitoring notification resolution is also required before incident closure.
                incident['verification']=verify({'container':state_good,'prometheus':self.monitor_check() if incident['external_resolved'] else None,'error_rate':None})
                incident['verification']['checks']['http']=http_good
                incident['status']='awaiting_monitoring' if state_good and http_good is True else 'needs_attention'
            elif action=='verify':
                report=self.pilot.action('investigate');health=self.pilot.probe(self.pilot.health)
                container_ok=not report.get('findings') and not report.get('snapshot',{}).get('errors')
                # Only explicitly supplied metrics are required. Error-rate criterion remains unknown if configured externally without evidence.
                checks={'container':bool(container_ok),'prometheus':self.monitor_check() if incident['external_resolved'] else None}
                result=verify(checks);result['checks']['http']=health.get('healthy')
                if health.get('healthy') is not True:result['status']='failed' if health.get('healthy') is False else 'inconclusive'
                incident['verification']=result;incident['status']='verified' if result['status']=='verified' else 'needs_attention'
                if incident['status']=='verified':incident['recovery_seconds']=round(time.time()-incident['created'],3)
        except (ValueError,RuntimeError,OSError) as exc:
            incident['last_error']='Operation refused or failed: '+type(exc).__name__;incident['status']='needs_attention'
            raise
        finally:
            incident['busy']=False
            with self.lock,self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                # Ingestion may append events while the operation is external; never drop those updates.
                latest=self.get(incident['id']);incident['revision']=latest['revision'];incident['event_ids']=latest['event_ids'];incident['external_resolved']=latest['external_resolved']
                self._save(db,incident);self._audit(db,incident['id'],actor,action+'_finished',{'plan_id':incident.get('plan_id'),'status':incident['status'],'error':incident.get('last_error'),'evidence_refs':incident.get('diagnosis',{}).get('data',{}).get('evidence_refs',[])})
        return incident
    def report(self,ident):
        incident=self.get(ident)
        with self.connect() as db:timeline=[dict(time=t,actor=a,action=act,evidence=json.loads(p),hash=h) for t,a,act,p,h in db.execute("SELECT time,actor,action,payload,hash FROM audit WHERE incident=? OR (incident IS NULL AND actor='cloudlaunch' AND time>=?) ORDER BY seq LIMIT 150",(ident,incident['created']-3600))]
        unresolved=[] if incident['status']=='verified' else ['Required live recovery/monitoring criteria have not all passed.']
        return envelope('IncidentReport','ops-pilot',self.service,dict(incident_id=ident,timeline=timeline,unresolved=unresolved,incident=incident),incident['correlation_id'])
    def metrics(self):
        state=self.state();active=sum(i['status'] not in ('verified','rejected') for i in state['incidents']);resolved=sum(i['status']=='verified' for i in state['incidents'])
        with self.connect() as db:count=db.execute('SELECT COUNT(*) FROM incoming').fetchone()[0]
        return f'# TYPE ops_pilot_events_total counter\nops_pilot_events_total {count}\n# TYPE ops_pilot_incidents_active gauge\nops_pilot_incidents_active {active}\n# TYPE ops_pilot_incidents_verified gauge\nops_pilot_incidents_verified {resolved}\n'
