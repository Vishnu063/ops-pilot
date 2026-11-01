"""The default application cannot construct, poll or execute the optional provider."""
from contextlib import ExitStack
import io
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from ops_pilot import cli, web
from ops_pilot.coolify import Coolify, Transport
from ops_pilot.fleet import Fleet

RUN_SIGNATURE=inspect.signature(web.run)


class DisabledCoolifyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        # Even an existing default-location profile and token bindings cannot opt in.
        profile=self.root/'.config/ops-pilot/fleet.json';profile.parent.mkdir(parents=True)
        profile.write_text(json.dumps({'must_not_be_loaded':True}));profile.chmod(0o600)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('pathlib.Path.home',return_value=self.root))
        self.stack.enter_context(patch.dict(os.environ,{'OPS_PILOT_COOLIFY_READ':'disabled-fixture-read-value','OPS_PILOT_COOLIFY_DEPLOY':'disabled-fixture-deploy-value'}))
        self.guards=[]
        for owner,name in [(Coolify,'__init__'),(Coolify,'request'),(Coolify,'execute'),(Transport,'request'),(Fleet,'start')]:
            self.guards.append(self.stack.enter_context(patch.object(owner,name,side_effect=AssertionError('Optional provider invoked while disabled'))))
        self.guards.append(self.stack.enter_context(patch('ops_pilot.fleet.Fleet',side_effect=AssertionError('Fleet constructed without explicit opt-in'))))

    def tearDown(self):
        for guard in self.guards:guard.assert_not_called()

    def run_cli(self,command):
        config={'name':'Owned Docker app','docker_context':'default','container':'owned','health_url':'http://127.0.0.1:9000/health','interval_seconds':30}
        with patch('sys.argv',['ops-pilot',command,'--state-dir',str(self.root/'state')]),patch.object(cli,'load',return_value=(config,{})) as load,patch('ops_pilot.service.Pilot') as pilot,patch('ops_pilot.freelance.Workspace') as workspace,patch('ops_pilot.web.run') as run,patch('sys.stdout',new_callable=io.StringIO):
            code=cli.main()
            return code,load,pilot,workspace,run

    def test_default_serve_ignores_profile_and_tokens_without_opt_in(self):
        code,load,pilot,workspace,run=self.run_cli('serve')
        self.assertEqual(code,0);load.assert_called_once();pilot.assert_called_once();run.assert_called_once()
        call=RUN_SIGNATURE.bind(*run.call_args.args,**run.call_args.kwargs);call.apply_defaults()
        self.assertIsNone(call.arguments['fleet'])
        self.assertIs(call.arguments['pilot'],pilot.return_value)

    def test_freelance_mode_preserves_workspace_with_provider_disabled(self):
        code,load,pilot,workspace,run=self.run_cli('freelance')
        self.assertEqual(code,0);workspace.assert_called_once();load.assert_not_called();pilot.assert_not_called()
        call=RUN_SIGNATURE.bind(*run.call_args.args,**run.call_args.kwargs);call.apply_defaults()
        self.assertIsNone(call.arguments['fleet']);self.assertIsNone(call.arguments['pilot'])

    def test_fleet_commands_without_explicit_profile_fail_before_any_provider(self):
        for command in ('fleet','check-fleet'):
            with self.subTest(command=command):
                code,load,pilot,workspace,run=self.run_cli(command)
                self.assertEqual(code,2);load.assert_not_called();pilot.assert_not_called();workspace.assert_not_called();run.assert_not_called()

    def handler(self,path):
        handler=object.__new__(web.Handler)
        token='H'*48
        handler.server=SimpleNamespace(fleet=None,token=token,origins={'http://127.0.0.1:8767'})
        handler.path=path
        handler.headers={'Host':'127.0.0.1:8767','Origin':'http://127.0.0.1:8767','Cookie':'ops_pilot='+token,'Content-Type':'application/json','Content-Length':'100'}
        handler.rfile=Mock();handler.rfile.read.side_effect=AssertionError('Disabled action must not read/execute a payload')
        handler.send=Mock()
        return handler

    def test_disabled_state_and_report_do_not_collect_or_disclose_provider_data(self):
        for path in ('/api/fleet/state','/api/fleet/report','/api/fleet/report?after=not-a-number'):
            with self.subTest(path=path):
                handler=self.handler(path);handler.do_GET()
                code,data=handler.send.call_args.args[:2]
                self.assertEqual(code,200);self.assertIs(data['enabled'],False)
                self.assertNotIn('applications',data);self.assertNotIn('token',json.dumps(data));handler.rfile.read.assert_not_called()

    def test_disabled_recovery_route_rejects_before_reading_any_action(self):
        for action in ('plan','approve','execute','restart','redeploy','rollback'):
            with self.subTest(action=action):
                handler=self.handler('/api/fleet/action')
                handler.rfile.read.return_value=json.dumps({'action':action,'app':'owned'}).encode()
                handler.do_POST()
                self.assertEqual(handler.send.call_args.args[0],404);handler.rfile.read.assert_not_called()

    def test_disabled_actions_still_require_owner_host_and_origin(self):
        for field,value in [('Cookie',''),('Origin','https://untrusted.invalid'),('Host','untrusted.invalid')]:
            with self.subTest(field=field):
                handler=self.handler('/api/fleet/action');handler.headers[field]=value;handler.do_POST()
                self.assertEqual(handler.send.call_args.args[0],403);handler.rfile.read.assert_not_called()

    def test_server_without_fleet_never_starts_background_provider(self):
        server=Mock(server_port=8767,token='not-a-real-session')
        server.serve_forever.side_effect=KeyboardInterrupt
        with patch.object(web,'Server',return_value=server) as constructor,patch('sys.stdout',new_callable=io.StringIO):
            web.run(None,8767)
        self.assertIsNone(constructor.call_args.args[-1]);server.server_close.assert_called_once()
