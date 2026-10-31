"""Deterministic official-contract mocks; no installed Coolify or production proof."""
import copy
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from ops_pilot.coolify import Coolify, ProviderError, Transport, clean, destination
from ops_pilot.fleet import Fleet, configuration
from ops_pilot.notifications import telegram

INSTANCE=dict(id='lab',base_url='https://coolify.example.com',token_env='OPS_PILOT_TEST_READ',repair_token_env='OPS_PILOT_TEST_DEPLOY')
APP=dict(id='app-a',instance='lab',uuid='uuid-a',name='Example',health_url='https://app.example.com/ready',interval=30,failure_threshold=2,actions=['restart','redeploy'])
RAW=dict(id=17,uuid='uuid-a',name='Example',status='running:healthy',updated_at='2026-10-29',destination_id=1,destination={'server':{'uuid':'server-a'}})


class Responses:
    def __init__(self,*results): self.results=list(results);self.calls=[]
    def request(self,*args):
        self.calls.append(args)
        result=self.results.pop(0)
        if isinstance(result,Exception): raise result
        return result


def response(value,status=200,headers=None): return status,headers or {},json.dumps(value).encode()


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'OPS_PILOT_TEST_READ':'read-token-not-for-output','OPS_PILOT_TEST_DEPLOY':'deploy-token-not-for-output'});self.env.start()
    def tearDown(self): self.env.stop()
    def client(self,*results):
        t=Responses(*results);return Coolify(INSTANCE,t,sleep=lambda _:None),t
    def test_auth_discovery_normalization_and_projection(self):
        c,t=self.client(response('4.5.3'),response([dict(RAW,password='do-not-collect',envs=['secret'])]))
        self.assertEqual(['restart','redeploy'],c.connection()['actions'])
        apps=c.discover();self.assertEqual('running',apps[0]['runtime']);self.assertNotIn('password',str(apps))
        self.assertEqual('Bearer read-token-not-for-output',t.calls[0][2]['Authorization'])
        self.assertEqual('unknown',c.project(dict(RAW,status='running:unknown'))['provider_health'])
        self.assertEqual('unhealthy',c.project(dict(RAW,status='running:unhealthy'))['provider_health'])
    def test_invalid_auth_raw_error_never_exposed(self):
        c,t=self.client(response({'Authorization':'secret'},401))
        with self.assertRaises(ProviderError) as cm:c.connection()
        self.assertEqual('authentication',cm.exception.code);self.assertNotIn('secret',str(cm.exception));self.assertEqual(1,len(t.calls))
    def test_timeout_retries_bounded_and_mutation_never_retried(self):
        c,t=self.client(*[ProviderError('timeout')]*3)
        with self.assertRaises(ProviderError): c.connection()
        self.assertEqual(3,len(t.calls))
        c,t=self.client(ProviderError('timeout'));c.version='4.5.3'
        with self.assertRaises(ProviderError):c.execute('uuid-a','restart')
        self.assertEqual(1,len(t.calls));self.assertEqual('POST',t.calls[0][0]);self.assertIn('deploy-token',t.calls[0][2]['Authorization'])
    def test_rate_limit_unavailable_and_unexpected_responses(self):
        for result,code,count in [(response({},429,{'Retry-After':'90'}),'rate_limit',1),(response({},500),'api',3),(response({'bad':'shape'}),'response',1)]:
            c,t=self.client(*([result]*count))
            with self.assertRaises(ProviderError) as cm:c.discover()
            self.assertEqual(code,cm.exception.code)
        c,t=self.client(response({},429,{'Retry-After':'1'}),response([RAW]));self.assertEqual(1,len(c.discover()))
    def test_deployment_wrapped_and_list_contracts(self):
        d={'deployment_uuid':'dep-a','status':'failed'}
        for raw in [[d],{'count':1,'deployments':[d]}]:
            c,t=self.client(response(raw));self.assertEqual('failed',c.deployments('uuid-a')[0]['status'])
    def test_targets_duplicate_and_unexpected_identity_rejected(self):
        for raw in [[RAW,RAW],[dict(RAW,uuid='../escape')],{'applications':[RAW]}]:
            c,t=self.client(response(raw))
            with self.assertRaises(ProviderError):c.discover()
        c,t=self.client(response(dict(RAW,uuid='other')))
        with self.assertRaises(ProviderError):c.inspect('uuid-a')
    def test_unknown_version_disables_mutations(self):
        c,t=self.client(response('4.0.0-beta.1'));self.assertEqual([],c.connection()['actions'])
        with self.assertRaises(ProviderError):c.execute('uuid-a','restart')
    def test_restart_and_redeploy_use_documented_exact_posts(self):
        c,t=self.client(response({'deployment_uuid':'dep-a'}),response({'deployments':[{'resource_uuid':'uuid-a','deployment_uuid':'dep-b'}]}));c.version='4.5.3'
        self.assertEqual('dep-a',c.execute('uuid-a','restart')['deployment_uuid']);self.assertEqual('dep-b',c.execute('uuid-a','redeploy')['deployment_uuid'])
        self.assertTrue(t.calls[0][1].endswith('/applications/uuid-a/restart'));self.assertTrue(t.calls[1][1].endswith('/deploy'))
        self.assertEqual({'uuid':'uuid-a'},json.loads(t.calls[1][3]))
    def test_receipt_matches_exact_application_not_only_token_team(self):
        for appid,ok in [(18,False),(None,False),(True,False),('17',True)]:
            c,t=self.client(response(dict(deployment_uuid='dep-a',application_id=appid,status='finished')),response(RAW))
            if ok:self.assertEqual('uuid-a',c.deployment('dep-a','uuid-a')['application_uuid'])
            else:
                with self.assertRaises(ProviderError):c.deployment('dep-a','uuid-a')
        c,t=self.client(response(dict(deployment_uuid='wrong',application_id=17,status='finished')))
        with self.assertRaises(ProviderError):c.deployment('dep-a','uuid-a')

    def test_logs_redacted_before_truncation(self):
        secret='read-token-not-for-output'
        logs='Authorization: Bearer '+secret+'\npassword=bad\nCookie: session=private\n'+secret+'\n<script>alert(1)</script>\n'+('z'*10000)
        c,t=self.client(response({'logs':logs}));value=c.logs('uuid-a')
        for s in [secret,'password=bad','session=private']:self.assertNotIn(s,value)
        self.assertIn('[truncated]',value);self.assertLess(len(value),8300)
    def test_dns_ssrf_tls_policy_and_no_redirects(self):
        for url in ['http://remote.example','https://user:pass@example.com','https://example.com/?token=x']:
            with self.assertRaises(ValueError):destination(url)
        for ip in ['169.254.169.254','127.0.0.1','::1','10.0.0.1','::ffff:127.0.0.1','fd00:ec2::254']:
            with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]):
                with self.assertRaises(ProviderError) as cm:Transport().request('GET','https://example.com',{},None,1)
                self.assertEqual('destination',cm.exception.code)
        c,t=self.client(response({},302,{'Location':'https://evil.test'}))
        with self.assertRaises(ProviderError):c.discover()
        self.assertEqual(1,len(t.calls))
    def test_pinned_dns_and_tls_hostname_validation(self):
        class Connection:
            def __init__(self,*a,**kw):self.sock=None
            def request(self,*a,**kw):pass
            def getresponse(self):
                class R:
                    status=200
                    done=False
                    def read1(self,n):
                        if self.done:return b''
                        self.done=True;return b'{}'
                    def getheaders(self):return []
                return R()
            def close(self):pass
        with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]),patch('socket.create_connection') as connect,patch('ssl.create_default_context') as context,patch('http.client.HTTPConnection',Connection):
            Transport().request('GET','https://example.com/api/v1/version',{},None,3)
            connect.assert_called_once_with(('93.184.216.34',443),3)
            self.assertEqual('example.com',context.return_value.wrap_socket.call_args.kwargs['server_hostname'])


class FakeProvider:
    def __init__(self):
        self.raw=copy.deepcopy(RAW);self.history=[];self.calls=[];self.disconnected=False;self.deployment_status='finished';self.version='4.5.3';self.fail_execute=False
    def connection(self):
        if self.disconnected:raise ProviderError('unreachable')
        return dict(version=self.version,actions=['restart','redeploy'] if self.version=='4.5.3' else [],documented_contract=self.version=='4.5.3',runtime_acceptance=False)
    def discover(self):return [self.inspect('uuid-a')]
    def servers(self):return [dict(uuid='server-a',name='Owned server')]
    def inspect(self,target):
        if self.disconnected:raise ProviderError('timeout')
        return Coolify(INSTANCE).project(self.raw)
    def deployments(self,target):return copy.deepcopy(self.history)
    def logs(self,target):return 'sanitized untrusted logs'
    def execute(self,target,action):
        self.calls.append((target,action))
        if self.fail_execute:raise ProviderError('timeout')
        self.raw['status']='running:healthy'
        return dict(deployment_uuid='dep-owned',status='queued')
    def deployment(self,dep,target):return dict(uuid=dep,application_uuid=target,status=self.deployment_status)


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'fleet.json';self.now=1000;self.healthy=False
        self.config=dict(instances=[INSTANCE],applications=[APP]);self.save()
        self.provider=FakeProvider();self.fleet=Fleet(self.path,self.temp.name,providers={'lab':self.provider},probe=lambda _:self.healthy,clock=lambda:self.now,sleep=lambda _:None)
    def tearDown(self):self.fleet.close();self.temp.cleanup()
    def save(self):self.path.write_text(json.dumps(self.config));self.path.chmod(0o600)
    def tick(self):self.now+=31;self.fleet.poll()
    def incident(self):self.tick();self.tick();return self.fleet.state()['incidents'][0]
    def plan(self):self.incident();return self.fleet.action(dict(action='plan',app='app-a',operation='restart'))
    def test_healthy_requires_endpoint_not_running_alone(self):
        self.healthy=None;self.tick();self.assertEqual('unknown',self.fleet.state()['applications'][0]['health'])
        self.healthy=True;self.tick();self.assertEqual('healthy',self.fleet.state()['applications'][0]['health']);self.assertFalse(self.fleet.state()['incidents'])
    def test_threshold_dedup_and_sustained_restore(self):
        self.tick();self.assertFalse(self.fleet.state()['incidents']);self.tick();self.tick();self.assertEqual(1,len(self.fleet.state()['incidents']))
        self.healthy=True;self.tick();self.assertEqual('open',self.fleet.state()['incidents'][0]['status']);self.tick();self.assertEqual('resolved',self.fleet.state()['incidents'][0]['status'])
    def test_disconnection_preserves_last_app_not_false_failure(self):
        self.healthy=True;self.tick();self.provider.disconnected=True;self.tick()
        state=self.fleet.state();self.assertEqual('disconnected',state['instances'][0]['status']);self.assertEqual('healthy',state['applications'][0]['health']);self.assertTrue(state['applications'][0]['connection_stale']);self.assertFalse(state['incidents'])
    def test_failed_deployment_and_maintenance_suppression(self):
        self.healthy=True;self.provider.history=[dict(uuid='d1',status='failed')];self.incident()
        self.assertEqual('failed_deployment',self.fleet.state()['incidents'][0]['classification'])
    def test_approved_recovery_requires_separate_steps_and_verification(self):
        plan=self.plan()
        with self.assertRaises(ValueError):self.fleet.action(dict(action='execute',app='app-a',plan_id=plan['id']))
        self.fleet.action(dict(action='approve',app='app-a',plan_id=plan['id']))
        # The precondition read remains unhealthy; only action changes health.
        original=self.provider.execute
        def recover(*args):self.healthy=True;return original(*args)
        self.provider.execute=recover
        result=self.fleet.action(dict(action='execute',app='app-a',plan_id=plan['id']))
        self.assertEqual('verified',result['status']);self.assertEqual([('uuid-a','restart')],self.provider.calls)
        with self.assertRaises(ValueError):self.fleet.action(dict(action='execute',app='app-a',plan_id=plan['id']))
    def test_missing_application_id_refuses_plan_before_mutation(self):
        self.incident();self.provider.raw.pop('id')
        with self.assertRaises(ValueError):self.fleet.plan('app-a','restart')
        self.assertFalse(self.provider.calls)

    def test_explicit_provider_unhealthy_overrides_http_200_during_verification(self):
        self.provider.raw['status']='running:unhealthy'
        self.healthy=True
        result=self.fleet.verify(APP,dict(deployment_uuid='dep-owned'))
        self.assertEqual('needs_attention',result['status'])
    def test_nonconsecutive_successes_cannot_claim_recovery(self):
        values=iter([True,False,True,False,True]);self.fleet.probe=lambda _:next(values)
        result=self.fleet.verify(APP,dict(deployment_uuid='dep-owned'))
        self.assertEqual('needs_attention',result['status'])
    def test_connection_gap_resets_consecutive_observations(self):
        self.incident();self.healthy=True;self.tick()
        self.provider.disconnected=True;self.tick();self.provider.disconnected=False
        self.tick();self.assertEqual('open',self.fleet.state()['incidents'][0]['status'])
        self.tick();self.assertEqual('resolved',self.fleet.state()['incidents'][0]['status'])
    def test_collection_error_resets_consecutive_observations(self):
        self.incident();self.healthy=True;self.tick()
        original=self.provider.inspect
        self.provider.discover=lambda:[original('uuid-a')]
        self.provider.inspect=lambda _:(_ for _ in ()).throw(ProviderError('timeout'))
        self.tick();self.provider.inspect=original
        self.tick();self.assertEqual('open',self.fleet.state()['incidents'][0]['status'])
    def test_poll_cannot_commit_evidence_collected_across_an_execution(self):
        self.incident();self.healthy=True;self.tick()
        def during_probe(_):
            with self.fleet.connect() as db:self.fleet.put(db,'execution','app-a',dict(status='executing',plan_id='concurrent',at=self.now))
            return True
        self.fleet.probe=during_probe;self.tick()
        self.assertEqual('open',self.fleet.state()['incidents'][0]['status'])
    def test_pending_approval_beyond_ui_history_limit_is_superseded(self):
        plan=self.plan();self.fleet.approve('app-a',plan['id'])
        with self.fleet.connect() as db:
            for i in range(201):self.fleet.put(db,'plan','history-'+str(i),dict(id='history-'+str(i),app='other',status='consumed'))
        self.fleet.plan('app-a','restart')
        with self.assertRaises(ValueError):self.fleet.execute('app-a',plan['id'])
        self.assertFalse(self.provider.calls)

    def test_known_receipt_is_durable_when_verification_times_out(self):
        plan=self.plan();self.fleet.approve('app-a',plan['id'])
        self.provider.deployment=lambda *_:(_ for _ in ()).throw(ProviderError('timeout'))
        result=self.fleet.execute('app-a',plan['id'])
        self.assertEqual('unknown',result['status']);self.assertEqual('dep-owned',result['receipt']['deployment_uuid'])
        with self.fleet.connect() as db:
            saved=self.fleet.get(db,'plan',plan['id']);self.assertEqual('dep-owned',saved['receipt']['deployment_uuid'])
        self.assertTrue(any(row['kind']=='deployment_receipt' for row in self.fleet.report()['audit']))
        with self.assertRaises(ValueError):self.fleet.execute('app-a',plan['id'])

    def test_failed_readiness_never_reports_recovery(self):
        p=self.plan();self.fleet.approve('app-a',p['id']);r=self.fleet.execute('app-a',p['id']);self.assertEqual('needs_attention',r['status'])
        self.assertEqual('open',self.fleet.state()['incidents'][0]['status'])
    def test_unfinished_deployment_cannot_verify_healthy_endpoint(self):
        p=self.plan();self.fleet.approve('app-a',p['id']);self.provider.deployment_status='in_progress'
        original=self.provider.execute
        def recover(*a):self.healthy=True;return original(*a)
        self.provider.execute=recover;self.assertEqual('needs_attention',self.fleet.execute('app-a',p['id'])['status'])
    def test_expiry_wrong_target_changed_revision_and_unknown_action(self):
        p=self.plan()
        with self.assertRaises(ValueError):self.fleet.approve('other',p['id'])
        self.now+=121
        with self.assertRaises(ValueError):self.fleet.approve('app-a',p['id'])
        p=self.fleet.plan('app-a','restart');self.fleet.approve('app-a',p['id']);self.provider.raw['updated_at']='changed'
        with self.assertRaises(ValueError):self.fleet.execute('app-a',p['id'])
        self.assertFalse(self.provider.calls)
        with self.assertRaises(ValueError):self.fleet.action(dict(action='shell',app='app-a'))
    def test_timeout_consumes_approval_and_persists_unknown(self):
        p=self.plan();self.fleet.approve('app-a',p['id']);self.provider.fail_execute=True
        self.assertEqual('unknown',self.fleet.execute('app-a',p['id'])['status'])
        with self.assertRaises(ValueError):self.fleet.execute('app-a',p['id'])
        with self.assertRaises(ValueError):self.fleet.plan('app-a','restart')
        self.assertEqual(1,len(self.provider.calls))
    def test_concurrent_execution_persisted_guard_across_instances(self):
        p=self.plan();self.fleet.approve('app-a',p['id']);other=Fleet(self.path,self.temp.name,providers={'lab':self.provider},probe=lambda _:False,clock=lambda:self.now,sleep=lambda _:None)
        entered=threading.Event();release=threading.Event();original=self.provider.execute
        def blocked(*args):entered.set();release.wait(2);return original(*args)
        self.provider.execute=blocked
        t=threading.Thread(target=lambda:self.fleet.action(dict(action='execute',app='app-a',plan_id=p['id'])));t.start();self.assertTrue(entered.wait(1))
        with self.assertRaises(ValueError):other.action(dict(action='execute',app='app-a',plan_id=p['id']))
        release.set();t.join();self.assertEqual(1,len(self.provider.calls))
    def test_restart_persistence_audit_append_only_and_export(self):
        self.incident();r=self.fleet.report();self.assertTrue(r['audit']);self.assertEqual('genesis',r['audit'][0]['previous'])
        with self.fleet.connect() as db:
            import sqlite3
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM audit')
        other=Fleet(self.path,self.temp.name,providers={'lab':self.provider},probe=lambda _:False,clock=lambda:self.now,sleep=lambda _:None)
        self.assertEqual(1,len(other.state()['incidents']))
    def test_config_refuses_secrets_plaintext_and_unsafe_targets(self):
        for update in [dict(token='secret'),dict(base_url='http://remote'),dict(token_env='SECRET')]:
            self.config['instances']=[dict(INSTANCE,**update)];self.save()
            with self.assertRaises(ValueError):configuration(self.path)
    def test_floating_redeploy_refused_and_pinned_commit_accepted(self):
        self.incident()
        with self.assertRaises(ValueError):self.fleet.plan('app-a','redeploy')
        self.provider.raw['git_commit_sha']='a'*40
        self.assertEqual('redeploy',self.fleet.plan('app-a','redeploy')['action'])
    def test_new_plan_supersedes_old_approval_and_rotation_invalidates(self):
        p=self.plan();self.fleet.approve('app-a',p['id']);new=self.fleet.plan('app-a','restart')
        with self.assertRaises(ValueError):self.fleet.execute('app-a',p['id'])
        with patch.dict(os.environ,{'OPS_PILOT_TEST_DEPLOY':'rotated-token-never-report'}):
            with self.assertRaises(ValueError):self.fleet.approve('app-a',new['id'])
    def test_connection_retry_interval_and_no_notification_outage_replays(self):
        self.config['notification']=dict(provider='telegram',token_env='OPS_PILOT_BOT',chat_id='123',min_severity='warning');self.save()
        sent=[];self.provider.disconnected=True
        self.fleet=Fleet(self.path,self.temp.name,providers={'lab':self.provider},probe=lambda _:False,clock=lambda:self.now,sleep=lambda _:None,notifier=lambda c,e:sent.append(e) or True)
        self.tick();self.tick();self.tick();self.assertEqual(['monitoring_connection_lost'],sent)
        self.now+=1;self.fleet.poll();self.assertEqual(1,len(self.fleet.state()['notifications']))
    def test_planned_maintenance_suppresses_incidents_and_repairs(self):
        self.fleet.apps['app-a']['maintenance_until']=self.now+1000
        self.tick();self.tick();self.assertFalse(self.fleet.state()['incidents'])
        with self.assertRaises(ValueError):self.fleet.plan('app-a','restart')
    def test_multiple_apps_thresholds_are_independent(self):
        second=dict(APP,id='app-b',uuid='uuid-b',failure_threshold=3)
        self.fleet.apps['app-b']=second
        # A second configured provider target is projected by the mock, not auto-enrolled.
        self.fleet.probe=lambda app:app['id']=='app-b'
        self.tick();self.tick();state=self.fleet.state()
        self.assertEqual(['app-a'],[i['app'] for i in state['incidents']])
        self.assertEqual('healthy',next(a['health'] for a in state['applications'] if a['id']=='app-b'))
    def test_additional_docker_uses_original_plan_approval_engine(self):
        config=Path(self.temp.name)/'docker.json'
        config.write_text(json.dumps(dict(name='Docker one',docker_context='default',container='owned-app',health_url='http://127.0.0.1:9999/ready',interval_seconds=30)));config.chmod(0o600)
        self.config=dict(instances=[],applications=[],docker_applications=[dict(id='docker-a',config_file=str(config))]);self.save()
        calls=[]
        class Native:
            def __init__(self,c,d):self.config=c
            def state(self):return dict(name=self.config['name'],monitor={'healthy':None})
            def action(self,name,planid=None):calls.append((name,planid));return {'native':True}
            def close(self):pass
        f=Fleet(self.path,self.temp.name,docker_factory=Native)
        self.assertEqual('Docker one',f.state()['docker_applications'][0]['state']['name'])
        f.action(dict(action='approve',app='docker-a',plan_id='native-plan'));self.assertEqual([('approve','native-plan')],calls)
        with self.assertRaises(ValueError):f.action(dict(action='shell',app='docker-a'))
    def test_notifications_dedup_failure_delivery_confirmation(self):
        self.config['notification']=dict(provider='telegram',token_env='OPS_PILOT_BOT',chat_id='123',min_severity='warning');self.save()
        delivered=[]
        def notifier(config,event):delivered.append(event);raise OSError('failure')
        self.fleet=Fleet(self.path,self.temp.name,providers={'lab':self.provider},probe=lambda _:False,clock=lambda:self.now,sleep=lambda _:None,notifier=notifier)
        self.incident();self.tick();self.assertEqual(['incident_detected'],delivered)
        self.assertEqual('failed_or_unknown',self.fleet.state()['notifications'][0]['status'])
    def test_polling_interval_and_no_autonomous_repair(self):
        self.tick();self.now+=1;self.fleet.poll();self.assertFalse(self.fleet.state()['incidents']);self.assertFalse(self.provider.calls)


class TelegramTests(unittest.TestCase):
    def test_provider_confirmation_required_and_payload_minimal(self):
        config=dict(token_env='OPS_PILOT_BOT',chat_id='123')
        with patch.dict(os.environ,{'OPS_PILOT_BOT':'123456:abcdefghijklmnopqrstuvwxyz'}):
            for value,expected in [({'ok':True,'result':{'message_id':3}},True),({'ok':False},False),({'ok':True},False)]:
                t=Responses(response(value));self.assertEqual(expected,telegram(config,'incident_detected',t));self.assertNotIn('logs',t.calls[0][3].decode())
