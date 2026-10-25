"""Actual HTTP authorization around the read-only desk; no real infrastructure."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
from unittest.mock import patch
from ops_pilot.diagnostics import Diagnostics
from ops_pilot.web import Server
from triage.integrations import ToolAdapter


class DiagnosticHTTPTests(unittest.TestCase):
    def test_owner_origin_scope_import_and_private_report(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'config.json';p.write_text(json.dumps({'environment':'lab','tools':{'jenkins':{'resource':'owned','base_url':'http://127.0.0.1:18080'}}}));p.chmod(0o600)
            desk=Diagnostics(p,root);server=Server(None,0,diagnostics=desk)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
            base='http://127.0.0.1:'+str(server.server_port)
            opener=build_opener(ProxyHandler({}))
            def request(path,data=None,owner=False,origin=True,headers=None):
                h={'Content-Type':'application/json',**(headers or {})}
                if owner:h['Cookie']='ops_pilot='+server.token
                if origin:h['Origin']=base
                try:
                    with opener.open(Request(base+path,headers=h,data=None if data is None else json.dumps(data).encode()),timeout=5) as r:return r.status,json.load(r)
                except HTTPError as e:return e.code,json.load(e)
            with patch.object(ToolAdapter,'collect',side_effect=AssertionError('Denied callers cannot reach a collector')):
                self.assertEqual(request('/api/diagnostics/collect',{'tool':'jenkins'})[0],403)
                self.assertEqual(request('/api/diagnostics/collect',{'tool':'jenkins'},headers={'Authorization':'Bearer '+'a'*40})[0],403)
                self.assertEqual(request('/api/diagnostics/collect',{'tool':'jenkins'},True,False)[0],403)
            self.assertEqual(request('/api/diagnostics/state')[0],401)
            self.assertEqual(request('/api/diagnostics/collect',{'tool':'shell','command':'rm'},True)[0],409)
            value={'artifact_digest':'sha256:'+'b'*64,'report':{'SchemaVersion':2,'Results':[]}}
            code,report=request('/api/diagnostics/trivy',value,True);self.assertEqual(code,200)
            self.assertEqual(request('/api/diagnostics/report?id='+report['id'])[0],401)
            code,exported=request('/api/diagnostics/report?id='+report['id'],owner=True);self.assertEqual(code,200);self.assertEqual(exported['actions'],[])
            self.assertFalse(request('/api/diagnostics/state',owner=True)[1]['multi_user'])
