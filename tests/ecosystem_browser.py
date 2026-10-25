"""Synthetic UI fixture with real browser/HTTP/SQLite. Not a Docker recovery test."""
from pathlib import Path
import json
import sys
import tempfile
import threading
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from triage.ecosystem import envelope
from ops_pilot.ecosystem import EventHub
from ops_pilot.web import Server

class Fixture:
 config={'name':'SYNTHETIC UI','docker_context':'synthetic','container':'synthetic-owned-app'}
 health={'url':'http://127.0.0.1:18080/'}
 running=False
 mutations=0
 def probe(self,policy):return {'healthy':self.running}
 def action(self,name,plan_id=None):
  if name=='investigate':return {'snapshot':{'observations':{'id':['synthetic-owned-id'],'daemon_id':['synthetic-daemon'],'state':['running' if self.running else 'exited']}},'actions':[] if self.running else [{'id':'restart'}],'findings':[] if self.running else [{'title':'Synthetic stopped state','likely_cause':'UI fixture only; no real Docker evidence'}]}
  if name=='plan':return {'id':'synthetic-plan','command':['docker','--context','synthetic','restart','synthetic-owned-id'],'target':'synthetic-owned-id','risk':'Synthetic UI only','rollback':'No automatic rollback','verification':'Synthetic browser fixture; separate real recovery lab required'}
  if name=='apply':self.running=True;self.mutations+=1;return {'status':'verified','infrastructure_status':'verified','application_health':{'healthy':True}}
  return {'status':'approved' if name=='approve' else 'cancelled'}

root=Path(__file__).resolve().parents[1];out=root/'browser-evidence';out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as directory:
 fixture=Fixture();hub=EventHub(fixture,directory,'demo');hub.monitor_check=lambda:True
 event=envelope('MonitoringAlert','alertmanager','demo',{'fingerprint':'ui-demo','alertname':'SyntheticAppDown','status':'firing'},correlation_id='synthetic-ui')
 ident=hub.ingest(event,'alertmanager')['incident_id']
 server=Server(fixture,0,eventhub=hub);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1366,'height':900})
   context.add_cookies([dict(name='ops_pilot',value=server.token,url=base,httpOnly=True,sameSite='Strict')])
   page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(base+'/ecosystem')
   page.get_by_role('button',name='Collect evidence',exact=True).click()
   expect(page.locator('#evidence')).to_contain_text('SyntheticAppDown')
   page.get_by_role('button',name='Create restart plan',exact=True).click()
   page.get_by_role('button',name='Approve exact plan',exact=True).wait_for()
   expect(page.locator('#proposal')).to_contain_text('synthetic-owned-id')
   page.screenshot(path=str(out/'ecosystem-pending-desktop.png'),full_page=True)
   page.get_by_role('button',name='Approve exact plan',exact=True).click()
   page.get_by_role('button',name='Execute approved repair',exact=True).click()
   expect(page.locator('#message')).to_have_text('Saved: apply')
   expect(page.locator('#status')).to_contain_text('awaiting_monitoring')
   resolved=envelope('MonitoringAlert','alertmanager','demo',{'fingerprint':'ui-demo','alertname':'SyntheticAppDown','status':'resolved'},correlation_id='synthetic-ui')
   resolved['timestamp']=datetime.now(timezone.utc).isoformat()
   hub.ingest(resolved,'alertmanager');page.get_by_role('button',name='Refresh',exact=True).click()
   page.get_by_role('button',name='Verify recovery',exact=True).click();expect(page.locator('#status')).to_contain_text('verified')
   with page.expect_download() as download:
    page.get_by_role('link',name='Download incident report',exact=True).click()
   archive=json.loads(Path(download.value.path()).read_text())
   assert archive['complete'] and archive['pages'][0]['type']=='IncidentReport'
   page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(out/'ecosystem-mobile.png'),full_page=True)
   resource=envelope('MonitoringAlert','alertmanager','demo',{'fingerprint':'resource-ui','alertname':'SyntheticCPUHigh','status':'firing','observed_value':98},correlation_id='synthetic-resource')
   resource_id=hub.ingest(resource,'alertmanager')['incident_id']
   page.get_by_role('button',name='Refresh',exact=True).click();page.locator('#incident').select_option(resource_id)
   page.get_by_role('button',name='Collect evidence',exact=True).click()
   expect(page.locator('#criteria')).to_contain_text('No allowlisted repair')
   expect(page.get_by_role('button',name='Create restart plan',exact=True)).to_have_count(0)
   expect(page.get_by_role('button',name='Verify recovery',exact=True)).to_be_visible()
   assert fixture.mutations==1,'A resource-only incident must not run an additional repair'
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors
   (out/'ecosystem-result.json').write_text(json.dumps(dict(status='passed',synthetic=True,real_docker=False,owner_controls=True,mobile_overflow=False,page_errors=errors),indent=2)+'\n')
   browser.close()
 finally:server.shutdown();server.server_close();thread.join()
print('Synthetic incident desk browser/HTTP/SQLite flow passed; real Docker/metrics remain a separate acceptance path.')
