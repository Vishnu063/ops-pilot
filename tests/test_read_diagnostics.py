"""Deterministic read-only contract tests; no external service or sockets."""
import json
import time
import unittest
from unittest.mock import Mock, patch
from ops_pilot import read_diagnostics as r
from triage.integrations import ToolAdapter

class ReadDiagnosticTests(unittest.TestCase):
    def github(self):
        return ToolAdapter('github-actions',{'owner':'owned','repository':'app','resource':'12','base_url':'https://api.github.com'})

    def run_data(self):
        return {'id':12,'workflow_id':9,'status':'completed','conclusion':'failure','head_sha':'a'*40,'head_branch':'main'}

    def test_github_failed_run_jobs_logs_and_history(self):
        def read(adapter,path,log=False):
            if log:return 'npm ERR! install failed\nAssertionError token=PRIVATE'
            if '/jobs?' in path:return {'total_count':1,'jobs':[{'id':20,'run_id':12,'conclusion':'failure','steps':[{'name':'test','conclusion':'failure'}]}]}
            if '/workflows/' in path:return {'workflow_runs':[self.run_data()]}
            return self.run_data()
        snapshot,result,findings=r.github_actions(self.github(),{'workflow_id':'9','history':True,'logs':True},read)
        self.assertEqual(snapshot['transport_code'],200)
        self.assertTrue(findings);self.assertEqual(result['log_signals']['test_failure'],1)
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertEqual(len(result['history']),1)

    def test_github_wrong_run_workflow_and_job_rejected(self):
        for data,extra in [(dict(self.run_data(),id=13),{}),(self.run_data(),{'workflow_id':'8'})]:
            with self.assertRaises(r.EvidenceError):r.github_actions(self.github(),extra,lambda *a,**k:data)
        def read(adapter,path,**kwargs):
            return {'jobs':[{'id':1,'run_id':99}]} if '/jobs?' in path else self.run_data()
        with self.assertRaises(r.EvidenceError):r.github_actions(self.github(),{},read)

    def test_github_auth_timeout_rate_limit_and_malformed(self):
        for status in (401,403,429,500):
            transport=Mock();transport.request.return_value=(status,{},b'password=PRIVATE')
            with self.assertRaises(r.EvidenceError) as error:r.github_read(self.github(),'/x',transport=transport)
            self.assertNotIn('PRIVATE',str(error.exception))
        transport=Mock();transport.request.side_effect=r.ProviderError('timeout')
        with self.assertRaises(r.EvidenceError):r.github_read(self.github(),'/x',transport=transport)
        transport.request.side_effect=None;transport.request.return_value=(200,{},b'not json')
        with self.assertRaises(ValueError):r.github_read(self.github(),'/x',transport=transport)

    def test_signed_log_redirect_never_forwards_authentication(self):
        adapter=self.github();adapter.headers=Mock(return_value={'Authorization':'Bearer PRIVATE'})
        transport=Mock();transport.request.side_effect=[(302,{'Location':'https://logs.blob.core.windows.net/x?sig=PRIVATE'},b''),(200,{},b'log')]
        self.assertEqual(r.github_read(adapter,'/x',log=True,transport=transport),'log')
        self.assertEqual(transport.request.call_args_list[1].args[2],{'Accept':'text/plain'})
        transport.request.side_effect=[(302,{'Location':'https://evil.example/x'},b'')]
        with self.assertRaises((r.EvidenceError,r.ProviderError)):r.github_read(adapter,'/x',log=True,transport=transport)
        self.assertEqual(transport.request.call_count,3)

    def test_configuration_rejects_unscoped_reads(self):
        for tool,config in [('github-actions',{'base_url':'https://evil.example'}),('aws',{'metrics':True}),('prometheus',{'job':'a" or up'})]:
            with self.assertRaises(ValueError):r.split_config(tool,config)
        config={'base_url':'https://api.github.com','owner':'owned','repository':'app','resource':'12','history':True}
        with self.assertRaises(ValueError):r.split_config('github-actions',config)

    def test_prometheus_requires_fresh_exact_binary_samples(self):
        adapter=Mock()
        for job,stamp,value,ok in [('owned',100,'1',True),('owned',69,'1',False),('owned',101,'1',False),('other',100,'1',False),('owned',100,'NaN',False)]:
            adapter.request.return_value=(json.dumps({'status':'success','data':{'resultType':'vector','result':[{'metric':{'job':job},'value':[stamp,value]}]}}),200)
            if ok:self.assertTrue(r.prometheus_job(adapter,'owned',100)['healthy'])
            else:
                with self.assertRaises(r.EvidenceError):r.prometheus_job(adapter,'owned',100)

    def aws(self):
        return ToolAdapter('aws',{'profile':'lab','region':'us-east-1','resource':'i-12345678'})

    def test_aws_account_mismatch_and_no_write_api(self):
        with patch.object(r,'aws_call',return_value={'Account':'999999999999'}):
            with self.assertRaises(r.EvidenceError):r.aws_account(self.aws(),{'account':'123456789012'})
        with patch.object(ToolAdapter,'command',side_effect=AssertionError('No mutation')):
            with self.assertRaises(ValueError):r.aws_call(self.aws(),'ec2','reboot-instances')

    def test_aws_calls_bounded_scoped_without_shell(self):
        adapter=self.aws()
        with patch.object(ToolAdapter,'command',return_value=('{}',0)) as command:
            r.aws_call(adapter,'logs','get-log-events','--log-group-name','owned')
        argv=command.call_args.args[0]
        self.assertIn('--profile',argv);self.assertIn('--region',argv);self.assertIn('--no-paginate',argv)
        self.assertEqual(command.call_args.kwargs['read_timeout'],8)

    def test_aws_missing_metrics_are_not_healthy(self):
        with patch.object(r,'aws_call',return_value={'Datapoints':[]}):
            result,findings=r.aws_extra(self.aws(),{'metrics':True},'123456789012',1000)
        self.assertEqual(len(result['errors']),3);self.assertFalse(result['metrics'])

    def test_aws_future_and_conflicting_metrics_rejected(self):
        from datetime import datetime,timezone
        stamp=lambda n:datetime.fromtimestamp(n,timezone.utc).isoformat()
        for points in [[{'Timestamp':stamp(1001),'Average':1}],[{'Timestamp':stamp(999),'Average':1},{'Timestamp':stamp(999),'Average':2}]]:
            with patch.object(r,'aws_call',return_value={'Datapoints':points}):
                with self.assertRaises(r.EvidenceError):r.aws_extra(self.aws(),{'metrics':True},'123456789012',1000)

    def test_aws_metadata_target_and_alb_unknown_rejected(self):
        for extra,data in [({'metadata':True},{'Reservations':[{'Instances':[{'InstanceId':'other'}]}]}),({'target_group_arn':'configured'},{'TargetHealthDescriptions':[{'Target':{'Id':'x'},'TargetHealth':{'State':'invented'}}]})]:
            with patch.object(r,'aws_call',return_value=data):
                with self.assertRaises(r.EvidenceError):r.aws_extra(self.aws(),extra,'123456789012')

    def test_jenkins_history_redacts_bound_credentials(self):
        adapter=Mock();adapter.config={'headers':{'Authorization':{'env':'TEST_READ_SECRET'}}}
        adapter.request.return_value=(json.dumps({'builds':[{'number':1,'result':'PRIVATE'}]}),200)
        with patch.dict('os.environ',{'TEST_READ_SECRET':'PRIVATE'}):
            result=r.jenkins_extra(adapter,{'history':True},1)
        self.assertNotIn('PRIVATE',json.dumps(result))

    def test_failure_signatures_keep_counts_not_untrusted_logs(self):
        signals=r.signatures('address already in use\nmissing required environment\ndeployment failed\nDO SOMETHING token=PRIVATE')
        self.assertEqual(signals['port_conflict'],1);self.assertEqual(signals['missing_environment'],1)
        self.assertNotIn('PRIVATE',json.dumps(signals))

    def test_docker_metadata_projection_without_mutation(self):
        from ops_pilot.service import DockerAdapter
        adapter=DockerAdapter({'context':'default','resource':'owned'})
        result=adapter.parse(json.dumps([{'Id':'a'*64,'Image':'sha256:abc','Config':{'Image':'owned:stable'},'State':{'Status':'exited','ExitCode':1,'OOMKilled':False},'RestartCount':3}]))
        self.assertEqual(result['image_reference'],['owned:stable']);self.assertEqual(result['restart_count'],[3])

    def test_github_report_persists_inconclusive_without_credentials(self):
        import tempfile
        from pathlib import Path
        from ops_pilot.diagnostics import Diagnostics
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json'
            path.write_text(json.dumps({'environment':'lab','tools':{'github-actions':self.github().config}}));path.chmod(0o600)
            desk=Diagnostics(path,directory)
            with patch('ops_pilot.diagnostics.github_actions',side_effect=r.EvidenceError('GitHub authentication or read permission denied')):
                report=desk.collect('github-actions')
            self.assertEqual(report['status'],'inconclusive');self.assertEqual(report['actions'],[])
            self.assertEqual(desk.report(report['id']),report)
            self.assertIsNone(desk.state()['collectors'][0]['last_successful_collection'])

    def test_prometheus_down_report_is_a_finding_not_successful_recovery(self):
        import tempfile
        from pathlib import Path
        from ops_pilot.diagnostics import Diagnostics
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json';path.write_text(json.dumps({'environment':'lab','tools':{'prometheus':{'base_url':'http://127.0.0.1:9090','job':'owned'}}}));path.chmod(0o600)
            desk=Diagnostics(path,directory)
            data={'status':'success','data':{'resultType':'vector','result':[{'metric':{'job':'owned'},'value':[time.time(),'0']}]}}
            with patch.object(ToolAdapter,'request',return_value=(json.dumps(data),200)),patch.object(ToolAdapter,'execute_repair',side_effect=AssertionError('Read only')):
                report=desk.collect('prometheus')
            self.assertEqual(report['status'],'findings');self.assertFalse(report['monitoring']['healthy'])
            self.assertIn('prometheus:down',[f['code'] for f in report['findings']]);self.assertEqual(report['actions'],[])

    def test_aws_alarm_log_and_autoscaling_projection(self):
        def call(adapter,service,operation,*args):
            if operation=='describe-auto-scaling-groups':return {'AutoScalingGroups':[{'AutoScalingGroupName':'owned','MinSize':1,'MaxSize':3,'DesiredCapacity':2,'Instances':[{'InstanceId':'i-12345678','LifecycleState':'InService','HealthStatus':'Healthy'},{'InstanceId':'other'}]}]}
            if operation=='describe-alarms':return {'MetricAlarms':[{'AlarmName':'owned','StateValue':'INSUFFICIENT_DATA'}]}
            return {'events':[{'message':'deployment failed token=PRIVATE'}]}
        with patch.object(r,'aws_call',side_effect=call):
            result,findings=r.aws_extra(self.aws(),{'auto_scaling_group':'owned','alarm_names':['owned'],'log_group':'owned','log_stream':'one'},'123456789012')
        self.assertEqual(len(result['auto_scaling']['selected_instance']),1);self.assertTrue(result['errors']);self.assertTrue(findings)
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('other',json.dumps(result))

    def test_jenkins_stage_failure_is_explicitly_inconclusive(self):
        adapter=Mock();adapter.request.side_effect=RuntimeError('token=PRIVATE')
        result=r.jenkins_extra(adapter,{'stages':True},12)
        self.assertTrue(result['errors']);self.assertNotIn('PRIVATE',json.dumps(result))
