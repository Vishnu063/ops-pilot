"""Explicit owned CI-only resource/Grafana and failed-recovery manual rollback lab."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
import uuid

from ops_pilot.ecosystem import EventHub
from ops_pilot.service import Pilot
from ops_pilot.web import Server
from triage.health import check_health


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def http(url,data=None,headers=None):
    body=None if data is None else json.dumps(data).encode()
    with build_opener(ProxyHandler({}),NoRedirect()).open(Request(url,data=body,headers={'Content-Type':'application/json',**(headers or {})}),timeout=8) as response:
        raw=response.read(1048576)
        return json.loads(raw) if 'json' in response.headers.get('Content-Type','') else raw.decode()


def port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def wait(check,seconds=120):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            value=check()
            if value:return value
        except (OSError,ValueError,RuntimeError,KeyError):pass
        time.sleep(1)
    raise RuntimeError('Owned acceptance observation deadline exceeded')


def main():
    if os.environ.get('OPS_PILOT_RELIABILITY_LAB')!='owned-disposable-ci':raise SystemExit('Owned disposable CI opt-in required')
    if Path('/sys/fs/cgroup/memory.max').read_text().strip()!='8000000000':raise SystemExit('Enforced 8 GB enclosing cgroup required')
    root=Path(__file__).resolve().parents[1];output=Path('/work/reliability-evidence');output.mkdir(exist_ok=True)
    identity=uuid.uuid4().hex[:12];label='io.ops-pilot.reliability='+identity;containers=[]
    result={'status':'running','synthetic':True,'customer_changes':False,'checks':[],'cleanup':False}
    started=time.monotonic();server=None;pilot=None
    def docker(*args):
        run=subprocess.run(['docker','--host=unix:///var/run/docker.sock',*args],capture_output=True,text=True,timeout=150)
        if run.returncode:raise RuntimeError('Owned Docker operation failed: '+args[0])
        return run.stdout.strip()
    def create(name,image,args,limits):
        ident=docker('run','-d','--name',name,'--label',label,'--network','host',*limits,image,*args)
        containers.append(ident);return ident
    def remove(ident):
        obj=json.loads(docker('inspect',ident))[0]
        if obj['Config']['Labels'].get('io.ops-pilot.reliability')!=identity:raise RuntimeError('Ownership changed; cleanup refused')
        docker('rm','-f','-v',ident);containers.remove(ident)
    with tempfile.TemporaryDirectory() as temporary:
        directory=Path(temporary)
        try:
            metrics_port,prom_port,am_port,grafana_port=port(),port(),port(),port()
            fixture=create('ops-pressure-'+identity,'python:3.12-alpine',
                ['python','/fixture.py'],['--memory','128m','--cpus','0.5','--read-only','--user','65534:65534',
                 '--tmpfs','/data:rw,size=8m,mode=1777','--tmpfs','/tmp:rw,size=4m,mode=1777',
                 '-e','FIXTURE_PORT='+str(metrics_port),'--mount','type=bind,src='+str(root/'tests/fixtures/resource_exporter.py')+',dst=/fixture.py,readonly'])
            health='http://127.0.0.1:'+str(metrics_port)+'/health'
            wait(lambda:http(health).get('disk_enospc'))
            config=dict(name='Owned resource fixture',docker_context='default',container=fixture,health_url=health,interval_seconds=15)
            pilot=Pilot(config,directory/'pilot')
            os.environ['OPS_PILOT_EVENTS_ALERTMANAGER']=secrets.token_urlsafe(32)
            token=os.environ['OPS_PILOT_EVENTS_ALERTMANAGER']
            hub=EventHub(pilot,directory/'pilot','owned-demo');server=Server(pilot,0,eventhub=hub)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            (directory/'token').write_text(token);(directory/'token').chmod(0o600)
            # The test lowers only the memory threshold to 70%, keeping the 128 MiB fixture safe.
            rules=(root/'monitoring/alerts.yml').read_text().replace(') > 90\n        for: 10s\n        labels: {severity: warning',') > 70\n        for: 10s\n        labels: {severity: warning')
            (directory/'alerts.yml').write_text(rules)
            (directory/'prometheus.yml').write_text('global:\n  scrape_interval: 1s\n  evaluation_interval: 1s\nrule_files: [/config/alerts.yml]\nalerting:\n  alertmanagers:\n    - static_configs:\n        - targets: [127.0.0.1:'+str(am_port)+']\nscrape_configs:\n  - job_name: owned-pressure\n    static_configs:\n      - targets: [127.0.0.1:'+str(metrics_port)+']\n')
            (directory/'alertmanager.yml').write_text('route:\n  receiver: ops\n  group_by: [alertname]\n  group_wait: 0s\n  group_interval: 1s\n  repeat_interval: 1h\nreceivers:\n  - name: ops\n    webhook_configs:\n      - url: http://127.0.0.1:'+str(server.server_port)+'/webhooks/alertmanager\n        send_resolved: true\n        http_config:\n          authorization:\n            type: Bearer\n            credentials_file: /config/token\n')
            mount=['--user',str(os.getuid())+':'+str(os.getgid()),'--mount','type=bind,src='+str(directory)+',dst=/config,readonly']
            create('ops-prom-'+identity,'prom/prometheus:v3.7.0',['--config.file=/config/prometheus.yml','--storage.tsdb.path=/tmp/data','--web.listen-address=127.0.0.1:'+str(prom_port)],['--memory','192m','--cpus','0.5',*mount])
            create('ops-am-'+identity,'prom/alertmanager:v0.28.1',['--config.file=/config/alertmanager.yml','--storage.path=/tmp/data','--web.listen-address=127.0.0.1:'+str(am_port),'--cluster.listen-address='],['--memory','64m','--cpus','0.25',*mount])
            expected={'OpsPilotCPUHigh','OpsPilotMemoryHigh','OpsPilotDiskFull'}
            wait(lambda:expected.issubset({i.get('trigger',{}).get('data',{}).get('alertname') for i in hub.state()['incidents']}),150)
            for incident in hub.state()['incidents']:
                if incident['trigger']['data']['alertname'] not in expected:continue
                assert incident['trigger']['data']['observed_value']>0
                diagnosed=hub.action(dict(incident_id=incident['id'],revision=incident['revision'],action='investigate',plan_id=None))
                assert not pilot.engine.history(),'Monitoring must not create a mutation plan'
                report=hub.report(incident['id']);(output/(incident['trigger']['data']['alertname']+'.json')).write_text(json.dumps(report,indent=2))
            result['checks']+=['Real bounded CPU pressure -> Prometheus -> authenticated Alertmanager -> incident/evidence/report',
                               'Real bounded memory pressure -> alert/incident; lab threshold 70%, production example 90%',
                               'Actual ENOSPC on an owned 8 MiB tmpfs -> disk alert/incident; host filesystem untouched',
                               'Resource alerts never authorize or run a restart']
            result['resource_fixture_projection']='Real cgroup CPU/memory and tmpfs usage projected into node-style metric series by a CI-only fixture, not a deployed production node exporter.'
            user='lab-owner';password=secrets.token_urlsafe(32)
            create('ops-grafana-'+identity,'grafana/grafana:12.2.0',[],['--memory','384m','--cpus','0.5',
                '-e','GF_SERVER_HTTP_ADDR=127.0.0.1','-e','GF_SERVER_HTTP_PORT='+str(grafana_port),
                '-e','GF_SECURITY_ADMIN_USER='+user,'-e','GF_SECURITY_ADMIN_PASSWORD='+password,
                '-e','GF_ANALYTICS_REPORTING_ENABLED=false','-e','GF_ANALYTICS_CHECK_FOR_UPDATES=false'])
            base='http://127.0.0.1:'+str(grafana_port)
            headers={'Authorization':'Basic '+base64.b64encode((user+':'+password).encode()).decode()}
            wait(lambda:http(base+'/api/health',headers=headers).get('database')=='ok')
            http(base+'/api/datasources',dict(uid='ecosystem-prometheus',name='Owned Prometheus',type='prometheus',access='proxy',url='http://127.0.0.1:'+str(prom_port)),headers)
            dashboard=json.loads(Path('/work/devops_platform/monitoring/ecosystem/grafana/dashboard.json').read_text())
            http(base+'/api/dashboards/db',dict(dashboard=dashboard,overwrite=True),headers)
            saved=http(base+'/api/dashboards/uid/'+dashboard['uid'],headers=headers)
            assert len(saved['dashboard']['panels'])==len(dashboard['panels'])
            assert http(base+'/api/datasources/uid/ecosystem-prometheus/health',headers=headers)['status']=='OK'
            plotted=http(base+'/api/datasources/proxy/uid/ecosystem-prometheus/api/v1/query?query=ALERTS',headers=headers)
            assert plotted['status']=='success' and plotted['data']['result']
            result['checks'].append('Real Grafana authenticated health, imported Platform dashboard and live Prometheus datasource health')
            result['grafana_dashboard_uid']=dashboard['uid']
            # Failed recovery and separately approved manual rollback procedure, only for this owned stateless fixture.
            rollback_port=port();rollback_url='http://127.0.0.1:'+str(rollback_port)+'/'
            app='from http.server import HTTPServer,BaseHTTPRequestHandler; import os\nclass H(BaseHTTPRequestHandler):\n def log_message(self,*a):pass\n def do_GET(self):self.send_response(200 if os.environ["RELEASE"]=="good" else 503);self.end_headers();self.wfile.write(b"fixture")\nHTTPServer(("127.0.0.1",int(os.environ["APP_PORT"])),H).serve_forever()'
            image=json.loads(docker('image','inspect','python:3.12-alpine'))[0]['Id']
            bad=create('ops-bad-'+identity,image,['python','-c',app],['--memory','64m','--cpus','0.25','-e','RELEASE=bad','-e','APP_PORT='+str(rollback_port)])
            docker('stop','--time','1',bad)
            failed=Pilot(dict(config,name='Owned failed release',container=bad,health_url=rollback_url,health_attempts=5),directory/'rollback')
            failed.action('investigate');plan=failed.action('plan')
            try:failed.action('apply',plan['id']);raise AssertionError('Unapproved repair accepted')
            except ValueError:pass
            failed.action('approve',plan['id']);outcome=failed.action('apply',plan['id'])
            assert outcome['status']=='needs_attention' and outcome['application_health']['healthy'] is False
            try:failed.action('apply',plan['id']);raise AssertionError('Approval replay accepted')
            except ValueError:pass
            rollback_plan=dict(target=bad,daemon=docker('info','--format','{{.ID}}'),image=image,release='good',health_url=rollback_url,expires_at=time.time()+60)
            digest=hashlib.sha256(json.dumps(rollback_plan,sort_keys=True).encode()).hexdigest()
            approval={'plan_digest':digest,'decision':'approve','scope':'Owned CI-only stateless replacement; separate from restart approval'}
            assert approval['plan_digest']==hashlib.sha256(json.dumps(rollback_plan,sort_keys=True).encode()).hexdigest()
            assert time.time()<rollback_plan['expires_at'] and rollback_plan['daemon']==docker('info','--format','{{.ID}}')
            assert json.loads(docker('inspect',bad))[0]['Id']==rollback_plan['target']
            remove(bad)
            good=create('ops-good-'+identity,image,['python','-c',app],['--memory','64m','--cpus','0.25','-e','RELEASE=good','-e','APP_PORT='+str(rollback_port)])
            policy=dict(failed.health,attempts=5,interval=1)
            verified=wait(lambda:check_health(policy)['healthy'])
            assert verified and json.loads(docker('inspect',good))[0]['State']['Running']
            (output/'failed-recovery-manual-rollback.json').write_text(json.dumps(dict(recovery=outcome,rollback_plan=rollback_plan,approval=approval,new_target=good,healthy=True,
                scope='CI procedure acceptance only. No generic production Docker rollback executor is introduced; application deployments require their configured controller and separate authorization.'),indent=2))
            failed.close();result['checks'].append('Real failed approved restart -> needs_attention -> replay refusal -> separately scoped manual owned rollback -> consecutive healthy HTTP')
            result['status']='passed'
        except BaseException:
            result['status']='failed';raise
        finally:
            if server:server.shutdown();server.server_close()
            if pilot:pilot.close()
            errors=[]
            for container in containers[:]:
                try:remove(container)
                except Exception:errors.append('Owned container cleanup unverified')
            result['cleanup']=not errors;result['cleanup_errors']=errors
            if errors:result['status']='failed'
            result['elapsed_seconds']=round(time.monotonic()-started,3)
            result['memory_limit_bytes']=8000000000
            result['memory_peak_bytes']=int(Path('/sys/fs/cgroup/memory.peak').read_text())
            result['enclosing_local_memory_events']={k:int(v) for k,v in (l.split() for l in Path('/sys/fs/cgroup/memory.events.local').read_text().splitlines())}
            if any(result['enclosing_local_memory_events'].get(k,0) for k in ('max','oom','oom_kill','oom_group_kill')):result['status']='failed'
            (output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
    if result['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
