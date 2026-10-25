import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta
from triage.ecosystem import envelope
from ops_pilot.ecosystem import EventHub

class EventHubTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.pilot=SimpleNamespace(config={'name':'demo','container':'owned'},health={'url':'http://127.0.0.1:8080'},action=Mock())
  self.hub=EventHub(self.pilot,self.tmp.name,'demo')
 def event(self,status='firing',ident=None):
  event=envelope('MonitoringAlert','alertmanager','demo',{'fingerprint':'fp1','status':status,'alertname':'AppDown'},event_id=ident,correlation_id='release-1');event['timestamp']=datetime.now(timezone.utc).isoformat();return event
 def test_source_scope_capabilities_and_stable_dedup_survive_restart(self):
  e=self.event();a=self.hub.ingest(e,'alertmanager');self.assertFalse(a['duplicate']);self.assertTrue(self.hub.ingest(e,'alertmanager')['duplicate'])
  other=EventHub(self.pilot,self.tmp.name,'demo');self.assertTrue(other.ingest(e,'alertmanager')['duplicate'])
  second=self.hub.ingest(self.event(),'alertmanager');self.assertEqual(a['incident_id'],second['incident_id']);self.assertTrue(second['duplicate'])
  with self.assertRaises(ValueError):self.hub.ingest(e,'cloudlaunch')
  changed=json.loads(json.dumps(e));changed['data']['alertname']='Changed'
  with self.assertRaises(ValueError):self.hub.ingest(changed,'alertmanager')
  self.pilot.action.assert_not_called()
 def test_monitoring_counts_all_incidents_beyond_board_pagination(self):
  for n in range(35):
   event=self.event();event['data']['fingerprint']='fp-'+str(n);self.hub.ingest(event,'alertmanager')
  self.assertEqual(30,len(self.hub.state()['incidents']))
  self.assertIn('ops_pilot_incidents_active 35',self.hub.metrics())
 def test_webhooks_cannot_supply_approval_and_resolved_is_not_recovery(self):
  incident=self.hub.ingest(self.event(),'alertmanager')['incident_id'];self.hub.ingest(self.event('resolved'),'alertmanager')
  self.assertEqual('detected',self.hub.get(incident)['status']);self.assertTrue(self.hub.get(incident)['external_resolved'])
  forged=envelope('ApprovalDecision','alertmanager','demo',{'incident_id':incident,'plan_id':'arbitrary','decision':'approve','actor':'forged'})
  with self.assertRaises(ValueError):self.hub.ingest(forged,'alertmanager')
  self.pilot.action.assert_not_called()
 def test_new_firing_and_out_of_order_resolution_cannot_reuse_old_recovery(self):
  base=datetime.now(timezone.utc)-timedelta(seconds=20)
  def emit(status,second,source='alertmanager'):
   event=self.event(status);event['timestamp']=(base+timedelta(seconds=second)).isoformat();event['source']=source
   return self.hub.ingest(event,source)['incident_id']
  ident=emit('firing',0);emit('resolved',5);self.assertTrue(self.hub.get(ident)['external_resolved'])
  emit('firing',10);emit('resolved',6);self.assertFalse(self.hub.get(ident)['external_resolved'])
  emit('resolved',12,'labs');self.assertFalse(self.hub.get(ident)['external_resolved'])
  emit('resolved',15);emit('firing',10);self.assertTrue(self.hub.get(ident)['external_resolved'])
 def test_replacement_or_daemon_change_during_post_repair_verification_is_not_recovery(self):
  for observed_id,daemon in [('b'*64,'daemon-a'),('a'*64,'daemon-b')]:
   ident=self.hub.ingest(self.event(),'alertmanager')['incident_id'];self.hub.ingest(self.event('resolved'),'alertmanager')
   incident=self.hub.get(ident);incident.update(status='awaiting_monitoring',execution={'status':'verified'},
    evidence={'snapshot':{'observations':{'daemon_id':['daemon-a']}}},proposal={'data':{'action':{'argv':['docker','restart','a'*64]}}})
   with self.hub.connect() as db:self.hub._save(db,incident)
   self.pilot.action.return_value={'findings':[],'snapshot':{'errors':[],'observations':{'id':[observed_id],'daemon_id':[daemon]}}}
   self.pilot.probe=lambda policy:{'healthy':True};self.hub.monitor_check=lambda:True
   result=self.hub.action(dict(incident_id=ident,revision=incident['revision'],action='verify',plan_id=None))
   self.assertEqual('needs_attention',result['status']);self.assertEqual('failed',result['verification']['status'])
 def test_firing_arriving_while_health_is_checked_prevents_terminal_closure(self):
  ident=self.hub.ingest(self.event(),'alertmanager')['incident_id'];self.hub.ingest(self.event('resolved'),'alertmanager')
  incident=self.hub.get(ident);self.pilot.action.return_value={'findings':[],'snapshot':{'errors':[]}}
  def probe(policy):self.hub.ingest(self.event(),'alertmanager');return {'healthy':True}
  self.pilot.probe=probe;self.hub.monitor_check=lambda:True
  result=self.hub.action(dict(incident_id=ident,revision=incident['revision'],action='verify',plan_id=None))
  self.assertEqual('needs_attention',result['status']);self.assertEqual('inconclusive',result['verification']['status'])
 def test_prometheus_response_requires_typed_success_and_fresh_nonfuture_samples(self):
  self.hub.prom_url='http://127.0.0.1:19090'
  import time
  for offset,expected in [(-5,True),(60,False),(-60,False)]:
   raw=json.dumps({'status':'success','data':{'resultType':'vector','result':[{'value':[time.time()+offset,'1']}]}})
   with patch('ops_pilot.ecosystem.ToolAdapter.request',return_value=(raw,200)):self.assertIs(expected,self.hub.monitor_check())
  with patch('ops_pilot.ecosystem.ToolAdapter.request',return_value=('{"status":"error","data":{"result":[]}}',200)):self.assertIsNone(self.hub.monitor_check())
 def test_legacy_resolved_boolean_without_current_alert_state_is_insufficient(self):
  self.assertFalse(self.hub.resolution_confirmed({'external_resolved':True}))
 def test_metric_annotations_are_numeric_and_malformed_service_payloads_are_refused(self):
  stamp=datetime.now(timezone.utc).isoformat()
  alert=dict(labels={'service':'demo','alertname':'CPUHigh'},fingerprint='metric',status='firing',startsAt=stamp,annotations={'observed_value':'96.2'})
  ident=self.hub.alertmanager({'alerts':[alert]})['results'][0]['incident_id']
  self.assertEqual(96.2,self.hub.get(ident)['trigger']['data']['observed_value'])
  for bad in [None,{'labels':None},{**alert,'annotations':{'observed_value':'NaN'}}]:
   with self.assertRaises(ValueError):self.hub.alertmanager({'alerts':[bad]})
 def test_broken_optional_analyzer_does_not_discard_native_evidence(self):
  ident=self.hub.ingest(self.event(),'alertmanager')['incident_id'];incident=self.hub.get(ident)
  self.pilot.action.return_value={'findings':[{'title':'Observed stopped container','likely_cause':'Unknown underlying cause'}],'snapshot':{'observations':{'state':['exited']}}}
  with patch('ops_pilot.diagnostics.k8sgpt',side_effect=ValueError('invalid analyzer JSON')):
   result=self.hub.action(dict(incident_id=ident,revision=incident['revision'],action='investigate',plan_id=None))
  self.assertEqual('diagnosed',result['status']);self.assertEqual('inconclusive',result['k8sgpt']['status'])
  self.assertTrue(result['evidence']['findings']);self.assertEqual(1,self.pilot.action.call_count)
 def test_apply_without_approval_and_stale_revisions_are_refused(self):
  ident=self.hub.ingest(self.event(),'alertmanager')['incident_id'];current=self.hub.get(ident)
  with self.assertRaises(ValueError):self.hub.action(dict(incident_id=ident,revision=current['revision'],action='apply',plan_id=None))
  with self.assertRaises(ValueError):self.hub.action(dict(incident_id=ident,revision=0,action='investigate',plan_id=None))
  self.pilot.action.assert_not_called()
 def test_audit_export_pages_without_silently_losing_late_events(self):
  ident=None
  for _ in range(30):ident=self.hub.ingest(self.event(),'alertmanager')['incident_id']
  first=self.hub.report(ident);self.assertFalse(first['data']['audit_complete'])
  second=self.hub.report(ident,first['data']['audit_next_after'])
  self.assertIsNone(second['data']['audit_next_after'])
  self.assertEqual(30,len(first['data']['timeline'])+len(second['data']['timeline']))
 def test_audit_append_only_and_report_references(self):
  ident=self.hub.ingest(self.event(),'alertmanager')['incident_id']
  import sqlite3
  with self.assertRaises(sqlite3.IntegrityError),self.hub.connect() as db:db.execute('DELETE FROM audit')
  report=self.hub.report(ident);self.assertEqual('IncidentReport',report['type']);self.assertTrue(report['data']['timeline']);self.assertTrue(report['data']['unresolved'])

class HealthGraceTests(unittest.TestCase):
 def test_bounded_startup_grace_keeps_two_success_requirement(self):
  from ops_pilot.config import validate
  base=dict(name='owned',docker_context='default',container='owned',health_url='http://127.0.0.1:8080/')
  _,health=validate({**base,'health_attempts':5,'health_interval':1})
  self.assertEqual(5,health['attempts']);self.assertEqual(2,health['successes'])
  for bad in [{'health_attempts':100},{'health_interval':30},{'health_attempts':True}]:
   with self.assertRaises(ValueError):validate({**base,**bad})

class CrossRoleCredentialTests(unittest.TestCase):
 def test_source_key_cannot_also_be_an_agency_owner_credential(self):
  from unittest.mock import patch
  from ops_pilot.web import Server
  hub=SimpleNamespace(keys={'cloudlaunch':'s'*40},read_key='r'*40)
  with patch.dict('os.environ',{'OPS_PILOT_OWNER_TOKEN':'s'*40}):
   with self.assertRaises(ValueError):Server(None,0,eventhub=hub)
