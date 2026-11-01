"""Exact-target Docker stats contract tests; no Docker daemon contacted."""
import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock,patch
from ops_pilot.read_diagnostics import docker_metrics,EvidenceError
from ops_pilot.service import DockerAdapter
from ops_pilot.diagnostics import Diagnostics

class DockerMetricsTests(TestCase):
    def adapter(self):
        adapter=Mock();adapter.container_id='a'*64;adapter.daemon='owned-daemon'
        adapter.command.return_value=(json.dumps({'ID':'a'*64,'CPUPerc':'92.50%','MemPerc':'95.0%','MemUsage':'950MiB / 1GiB'}),0)
        adapter.collect.return_value={'observations':{'id':['a'*64]}}
        return adapter

    def test_fixed_scoped_bounded_stats_and_pressure_findings(self):
        adapter=self.adapter();resources,findings=docker_metrics(adapter)
        self.assertEqual(resources['cpu_percent'],92.5);self.assertEqual(resources['memory_percent'],95)
        self.assertEqual({f['code'] for f in findings},{'docker:cpu','docker:memory'})
        argv=adapter.command.call_args.args[0]
        self.assertEqual(argv[-1],'a'*64);self.assertIn('--no-stream',argv);self.assertIn('--no-trunc',argv)
        self.assertEqual(adapter.command.call_args.kwargs['read_timeout'],8)

    def test_wrong_identity_and_ambiguous_target_rejected(self):
        adapter=self.adapter();adapter.command.return_value=(json.dumps({'ID':'b'*64}),0)
        with self.assertRaises(EvidenceError):docker_metrics(adapter)
        adapter.container_id=None;adapter.command.reset_mock()
        with self.assertRaises(EvidenceError):docker_metrics(adapter)
        adapter.command.assert_not_called()

    def test_target_replacement_and_daemon_change_rejected(self):
        for field,value in [('container_id','b'*64),('daemon','different')]:
            adapter=self.adapter()
            def change():
                setattr(adapter,field,value)
                return {'observations':{'id':[adapter.container_id]}}
            adapter.collect.side_effect=change
            with self.assertRaises(EvidenceError):docker_metrics(adapter)

    def test_missing_or_malformed_metrics_never_report_healthy(self):
        for field,value in [('CPUPerc','NaN%'),('MemPerc','101%'),('MemUsage','token=PRIVATE'),('CPUPerc',None)]:
            adapter=self.adapter();data={'ID':'a'*64,'CPUPerc':'1%','MemPerc':'2%','MemUsage':'1MiB / 1GiB'};data[field]=value
            adapter.command.return_value=(json.dumps(data),0)
            with self.assertRaises(EvidenceError) as error:docker_metrics(adapter)
            self.assertNotIn('PRIVATE',str(error.exception))

    def test_collector_unavailable_stats_persists_inconclusive_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'config.json';config.write_text(json.dumps({'environment':'lab','tools':{'docker':{'context':'owned','resource':'app','metrics':True}}}));config.chmod(0o600)
            desk=Diagnostics(config,directory)
            with patch.object(DockerAdapter,'collect',return_value={'observations':{'id':['a'*64],'state':['running']},'errors':[]}),patch('ops_pilot.diagnostics.deep_evidence',return_value={'errors':[]}),patch('ops_pilot.diagnostics.docker_metrics',side_effect=OSError('token=PRIVATE')),patch.object(DockerAdapter,'execute_repair',side_effect=AssertionError('Read only')):
                report=desk.collect('docker')
            self.assertEqual(report['status'],'inconclusive');self.assertEqual(report['actions'],[])
            self.assertNotIn('PRIVATE',json.dumps(report));self.assertEqual(desk.report(report['id']),report)
