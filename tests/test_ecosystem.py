import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from triage.ecosystem import envelope
from ops_pilot.ecosystem import EventHub

class EventHubTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.pilot=SimpleNamespace(config={'name':'demo','container':'owned'},health={'url':'http://127.0.0.1:8080'},action=Mock())
  self.hub=EventHub(self.pilot,self.tmp.name,'demo')
 def event(self,status='firing',ident=None):return envelope('MonitoringAlert','alertmanager','demo',{'fingerprint':'fp1','status':status,'alertname':'AppDown'},event_id=ident,correlation_id='release-1')
 def test_source_scope_capabilities_and_stable_dedup_survive_restart(self):
  e=self.event();a=self.hub.ingest(e,'alertmanager');self.assertFalse(a['duplicate']);self.assertTrue(self.hub.ingest(e,'alertmanager')['duplicate'])
  other=EventHub(self.pilot,self.tmp.name,'demo');self.assertTrue(other.ingest(e,'alertmanager')['duplicate'])
  second=self.hub.ingest(self.event(),'alertmanager');self.assertEqual(a['incident_id'],second['incident_id']);self.assertTrue(second['duplicate'])
  with self.assertRaises(ValueError):self.hub.ingest(e,'cloudlaunch')
  changed=json.loads(json.dumps(e));changed['data']['alertname']='Changed'
  with self.assertRaises(ValueError):self.hub.ingest(changed,'alertmanager')
  self.pilot.action.assert_not_called()
 def test_webhooks_cannot_supply_approval_and_resolved_is_not_recovery(self):
  incident=self.hub.ingest(self.event(),'alertmanager')['incident_id'];self.hub.ingest(self.event('resolved'),'alertmanager')
  self.assertEqual('detected',self.hub.get(incident)['status']);self.assertTrue(self.hub.get(incident)['external_resolved'])
  forged=envelope('ApprovalDecision','alertmanager','demo',{'incident_id':incident,'plan_id':'arbitrary','decision':'approve','actor':'forged'})
  with self.assertRaises(ValueError):self.hub.ingest(forged,'alertmanager')
  self.pilot.action.assert_not_called()
 def test_apply_without_approval_and_stale_revisions_are_refused(self):
  ident=self.hub.ingest(self.event(),'alertmanager')['incident_id'];current=self.hub.get(ident)
  with self.assertRaises(ValueError):self.hub.action(dict(incident_id=ident,revision=current['revision'],action='apply',plan_id=None))
  with self.assertRaises(ValueError):self.hub.action(dict(incident_id=ident,revision=0,action='investigate',plan_id=None))
  self.pilot.action.assert_not_called()
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
