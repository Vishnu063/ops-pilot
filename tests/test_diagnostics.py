import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ops_pilot.diagnostics import Diagnostics, configuration, wizard
from triage.integrations import ToolAdapter


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'config.json'
        self.write({'environment':'lab','tools':{'jenkins':{'resource':'owned-job','base_url':'http://127.0.0.1:18080'}}})
        self.desk = Diagnostics(self.path, self.temp.name)

    def write(self, value):
        self.path.write_text(json.dumps(value));self.path.chmod(0o600)

    def test_configuration_refuses_broad_scope_permissions_and_literal_credentials(self):
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):configuration(self.path)
        for tool, conf in [('kubernetes',{'context':'prod','namespace':'*','resource':'app'}),('aws',{'profile':'default','region':'us-east-1','resource':'all'}),('jenkins',{'resource':'app','base_url':'http://remote','password':'secret'}),('shell',{})]:
            self.write({'environment':'lab','tools':{tool:conf}})
            with self.assertRaises(ValueError):configuration(self.path)
        import os
        fifo=Path(self.temp.name)/'not-a-file'
        os.mkfifo(fifo,0o600)
        with self.assertRaises(ValueError):configuration(fifo)

    def test_wizard_creates_private_validated_profile_without_overwrite_or_connection(self):
        p=Path(self.temp.name)/'new.json'
        with patch('builtins.input',side_effect=['lab','kubernetes','kind-owned','owned','app']),patch.object(ToolAdapter,'collect',side_effect=AssertionError('No connection during setup')):
            wizard(p)
        self.assertEqual(configuration(p)['environment'],'lab')
        self.assertEqual(p.stat().st_mode&0o777,0o600)
        with self.assertRaises(ValueError):wizard(p)

    def test_numbered_jenkins_failure_logs_are_projected_and_cannot_repair(self):
        def request(adapter, path, *args):
            if path == adapter.profile['endpoint']:
                return json.dumps({'number':7,'result':'FAILURE','building':False}),200
            self.assertEqual(path,'/job/$resource/7/logText/progressiveText?start=0')
            return 'permission denied token=PRIVATE first failing stage deploy',200
        with patch.object(ToolAdapter,'request',request),patch.object(ToolAdapter,'execute_repair',side_effect=AssertionError('Mutation forbidden')):
            report=self.desk.collect('jenkins')
        self.assertEqual(report['status'],'findings')
        self.assertEqual(report['deep_evidence']['log_signals']['authorization'],1)
        self.assertEqual(report['actions'],[])
        self.assertNotIn('PRIVATE',json.dumps(report))
        self.assertNotIn('first failing stage deploy',json.dumps(report))
        self.assertEqual(self.desk.report(report['id']),report)
        self.assertEqual(self.desk.path.stat().st_mode & 0o777,0o600)

    def test_failed_collection_is_inconclusive_and_sanitized(self):
        with patch.object(ToolAdapter,'collect',side_effect=RuntimeError('password=SECRET')):
            r=self.desk.collect('jenkins')
        self.assertEqual(r['status'],'inconclusive');self.assertNotIn('SECRET',json.dumps(r))
        with self.assertRaises(ValueError):self.desk.collect('aws')
        with self.desk.connect() as db:
            with self.assertRaises(Exception):db.execute("DELETE FROM audit")
        for error in (TypeError('invalid API shape'),KeyError('unavailable field'),IndexError('empty response')):
            with patch.object(ToolAdapter,'collect',side_effect=error):
                self.assertEqual(self.desk.collect('jenkins')['status'],'inconclusive')

    def test_jenkins_missing_build_identity_fails_closed_without_reading_a_console(self):
        with patch.object(ToolAdapter,'request',return_value=('{"building":false}',200)) as requests:
            r=self.desk.collect('jenkins')
        self.assertEqual(r['status'],'inconclusive')
        self.assertEqual(requests.call_count,1)

    def test_busy_collector_refuses_queued_execution(self):
        self.desk.lock.acquire()
        try:
            with self.assertRaises(ValueError):self.desk.collect('jenkins')
        finally:self.desk.lock.release()

    def test_import_has_exact_artifact_scope_and_no_secret_body(self):
        raw={'SchemaVersion':2,'Results':[{'Vulnerabilities':[{'VulnerabilityID':'CVE-test','Severity':'CRITICAL','Description':'token=SECRET'}]}]}
        r=self.desk.trivy({'artifact_digest':'sha256:'+'a'*64,'report':raw})
        self.assertEqual(r['counts']['CRITICAL'],1);self.assertNotIn('SECRET',json.dumps(r));self.assertEqual(r['actions'],[])
        with self.assertRaises(ValueError):self.desk.trivy({'artifact_digest':'latest','report':raw})
        with self.assertRaises(ValueError):self.desk.trivy({'artifact_digest':'sha256:'+'a'*64,'report':{}})
        with self.assertRaises(ValueError):self.desk.trivy({'artifact_digest':'sha256:'+'a'*64,'report':{'SchemaVersion':2,'Results':[{'Secrets':[{'Title':'sensitive'}]}]}})
        with self.assertRaises(ValueError):self.desk.trivy({'artifact_digest':'sha256:'+'a'*64,'report':{'SchemaVersion':2,'Results':[{'Vulnerabilities':{}}]}})

    def test_environment_report_isolation(self):
        r=self.desk.trivy({'artifact_digest':'sha256:'+'a'*64,'report':{'SchemaVersion':2,'Results':[]}})
        self.write({'environment':'other','tools':{'jenkins':{'resource':'other-job','base_url':'http://127.0.0.1:18080'}}})
        other=Diagnostics(self.path,self.temp.name)
        with self.assertRaises(ValueError):other.report(r['id'])
        self.assertEqual(other.state()['reports'],[])

    def test_ec2_impaired_instance_and_helm_history_reuse_native_profiles(self):
        for tool,config,raw in [
            ('aws',{'profile':'lab','region':'us-east-1','resource':'i-1234567890abcdef0'},{'InstanceStatuses':[{'InstanceId':'i-1234567890abcdef0','InstanceState':{'Name':'running'},'SystemStatus':{'Status':'ok'},'InstanceStatus':{'Status':'impaired'}}]}),
            ('helm',{'context':'lab','namespace':'lab','resource':'app'},{'name':'app','version':2,'namespace':'lab','info':{'status':'failed'}})]:
            self.write({'environment':'lab','tools':{tool:config}});desk=Diagnostics(self.path,self.temp.name)
            def command(adapter,argv,**kw):
                if argv[:2]==['helm','history']:
                    self.assertEqual(argv[-3:],['10','--output','json']);return '[{"revision":1,"status":"superseded"}]',0
                return json.dumps(raw),0
            with patch.object(ToolAdapter,'command',command):r=desk.collect(tool)
            self.assertEqual(r['status'],'findings')
            if tool=='aws':self.assertIn('aws:instance-check',{f['code'] for f in r['findings']})
            else:self.assertEqual(r['release_history'][0]['revision'],1)


if __name__=='__main__':unittest.main()
