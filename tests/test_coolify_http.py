"""Real HTTP/SQLite against a MOCK Coolify server. Not installed Coolify acceptance."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor

from ops_pilot.fleet import Fleet
from ops_pilot.web import Server
from ops_pilot.freelance import Workspace


class MockCoolify(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,status,value):
        raw=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/ready':return self.reply(200 if self.server.healthy else 503,{'ready':self.server.healthy})
        if self.server.disconnected:return self.reply(503,{'message':'simulated provider outage'})
        if self.headers.get('Authorization')!='Bearer read-token-mock-only':return self.reply(401,{'message':'unauthorized'})
        raw={'id':17,'uuid':'owned-a','name':'Owned mock <script>alert(1)</script>','status':'running:healthy','updated_at':'fixed','git_commit_sha':'a'*40,'destination':{'server':{'uuid':'owned-server'}}}
        if path=='/api/v1/version':return self.reply(200,'4.5.3')
        if path=='/api/v1/applications':return self.reply(200,[raw])
        if path=='/api/v1/applications/owned-a':return self.reply(200,raw)
        if path=='/api/v1/servers':return self.reply(200,[dict(uuid='owned-server',name='Mock server')])
        if path=='/api/v1/deployments/applications/owned-a':return self.reply(200,{'count':0,'deployments':[]})
        if path=='/api/v1/deployments/receipt-a':return self.reply(200,dict(deployment_uuid='receipt-a',application_id='17',status='finished'))
        if path=='/api/v1/applications/owned-a/logs':return self.reply(200,dict(logs='Authorization: Bearer read-token-mock-only\npassword=private\n<script>untrusted</script>'))
        self.reply(404,{})
    def do_POST(self):
        if self.headers.get('Authorization')!='Bearer deploy-token-mock-only':return self.reply(403,{})
        self.rfile.read(int(self.headers.get('Content-Length','0')))
        if self.path not in ('/api/v1/applications/owned-a/restart','/api/v1/deploy'):return self.reply(404,{})
        self.server.mutations+=1
        if self.server.recover:self.server.healthy=True
        if self.path.endswith('/deploy'):return self.reply(200,dict(deployments=[dict(resource_uuid='owned-a',deployment_uuid='receipt-a')]))
        self.reply(200,dict(deployment_uuid='receipt-a',message='queued'))


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'OPS_PILOT_HTTP_READ':'read-token-mock-only','OPS_PILOT_HTTP_DEPLOY':'deploy-token-mock-only'}):
        remote=ThreadingHTTPServer(('127.0.0.1',0),MockCoolify);remote.healthy=True;remote.recover=True;remote.disconnected=False;remote.mutations=0
        thread=threading.Thread(target=remote.serve_forever,daemon=True);thread.start()
        origin='http://127.0.0.1:'+str(remote.server_port)
        config=dict(instances=[dict(id='mock',base_url=origin,token_env='OPS_PILOT_HTTP_READ',repair_token_env='OPS_PILOT_HTTP_DEPLOY',allow_loopback=True,timeout=1)],
                    applications=[dict(id='owned',instance='mock',uuid='owned-a',name='Owned application',health_url=origin+'/ready',interval=30,failure_threshold=2,actions=['restart','redeploy'])])
        path=Path(root)/'fleet.json';path.write_text(json.dumps(config));path.chmod(0o600)
        now=[1000];fleet=Fleet(path,root,clock=lambda:now[0],sleep=lambda _:None)
        # Mock API outage tests avoid backoff sleeps, keeping all response assertions intact.
        fleet.providers['mock'].sleep=lambda _:None
        server=Server(None,0,workspace=Workspace(root),fleet=fleet);webthread=threading.Thread(target=server.serve_forever,daemon=True);webthread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def tick():now[0]+=31;return fleet.poll()
        try:yield dict(remote=remote,fleet=fleet,base=base,server=server,tick=tick,now=now,root=root)
        finally:
            fleet.close();server.shutdown();server.server_close();webthread.join();remote.shutdown();remote.server_close();thread.join()


class HTTPAcceptance(unittest.TestCase):
    def test_auth_origin_scope_and_private_reports(self):
        with fixture() as f:
            opener=build_opener(HTTPCookieProcessor())
            with self.assertRaises(HTTPError) as cm:opener.open(f['base']+'/api/fleet/state')
            self.assertEqual(401,cm.exception.code)
            opener.open(f['base']+'/login?token='+f['server'].token).close()
            req=Request(f['base']+'/api/fleet/action',data=b'{"action":"check","app":"owned"}',headers={'Content-Type':'application/json','Origin':'http://evil.test'},method='POST')
            with self.assertRaises(HTTPError) as cm:opener.open(req)
            self.assertEqual(403,cm.exception.code)
            req.add_header('Origin',f['base']);self.assertEqual(200,opener.open(req).status)
            req=Request(f['base']+'/api/fleet/action',data=b'{"action":"plan","app":"other","operation":"restart"}',headers={'Content-Type':'application/json','Origin':f['base']},method='POST')
            with self.assertRaises(HTTPError) as cm:opener.open(req)
            self.assertEqual(409,cm.exception.code);self.assertEqual(0,f['remote'].mutations)
            report=json.load(opener.open(f['base']+'/api/fleet/report'));self.assertNotIn('read-token-mock-only',json.dumps(report));self.assertNotIn('deploy-token-mock-only',json.dumps(report))
    def test_A_B_C_healthy_failure_approved_recovery_real_mock_http(self):
        with fixture() as f:
            self.assertEqual('healthy',f['tick']()['applications'][0]['health'])
            f['remote'].healthy=False;f['tick']();state=f['tick']();self.assertEqual(1,len(state['incidents']))
            fleet=f['fleet'];p=fleet.action(dict(action='plan',app='owned',operation='restart'))
            with self.assertRaises(ValueError):fleet.action(dict(action='execute',app='owned',plan_id=p['id']))
            fleet.action(dict(action='approve',app='owned',plan_id=p['id']))
            self.assertEqual('verified',fleet.action(dict(action='execute',app='owned',plan_id=p['id']))['status'])
            f['tick']();self.assertEqual('resolved',f['tick']()['incidents'][0]['status']);self.assertEqual(1,f['remote'].mutations)
    def test_D_failed_recovery_and_logs_remain_untrusted(self):
        with fixture() as f:
            f['remote'].healthy=False;f['remote'].recover=False;f['tick']();f['tick']();fleet=f['fleet']
            logs=fleet.action(dict(action='logs',app='owned'))['logs'];self.assertNotIn('password=private',logs);self.assertNotIn('read-token-mock-only',logs)
            p=fleet.action(dict(action='plan',app='owned',operation='redeploy'));fleet.action(dict(action='approve',app='owned',plan_id=p['id']))
            self.assertEqual('needs_attention',fleet.action(dict(action='execute',app='owned',plan_id=p['id']))['status'])
            with self.assertRaises(ValueError):fleet.action(dict(action='execute',app='owned',plan_id=p['id']))
    def test_E_provider_down_is_not_all_apps_down(self):
        with fixture() as f:
            f['tick']();f['remote'].disconnected=True;state=f['tick']();self.assertEqual('disconnected',state['instances'][0]['status']);self.assertEqual('healthy',state['applications'][0]['health']);self.assertTrue(state['applications'][0]['connection_stale']);self.assertEqual([],state['incidents'])
