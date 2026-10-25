"""Synthetic collector + real owner HTTP/browser; separate from actual service labs."""
import json
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright
from ops_pilot.diagnostics import Diagnostics
from ops_pilot.web import Server
from triage.integrations import ToolAdapter


def main():
    output=Path('diagnostic-evidence');output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as root:
        config=Path(root)/'config.json';config.write_text(json.dumps({'environment':'owned-demo','tools':{'jenkins':{'base_url':'http://127.0.0.1:18080','resource':'owned'}}}));config.chmod(0o600)
        desk=Diagnostics(config,root);server=Server(None,0,diagnostics=desk)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def request(adapter,path,*args):
            return (json.dumps({'number':42,'result':'FAILURE','building':False}) if 'api/json' in path else 'permission denied token=NEVER_PERSIST'),200
        try:
            with patch.object(ToolAdapter,'request',request),sync_playwright() as p:
                browser=p.chromium.launch()
                page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/login?token='+server.token);page.goto(base+'/diagnostics')
                page.get_by_role('button',name='Collect evidence',exact=True).click()
                page.wait_for_function("document.getElementById('report').textContent.includes('jenkins:result')")
                assert 'NEVER_PERSIST' not in page.locator('#report').inner_text()
                assert page.locator('#download').get_attribute('href').startswith('/api/diagnostics/report?id=')
                page.locator('#digest').fill('sha256:'+'a'*64)
                page.locator('#scan').set_input_files({'name':'scan.json','mimeType':'application/json','buffer':json.dumps({'SchemaVersion':2,'Results':[{'Vulnerabilities':[{'VulnerabilityID':'<img src=x onerror="window.bad=true">','Severity':'HIGH'}]}]}).encode()})
                page.get_by_role('button',name='Import report',exact=True).click()
                page.wait_for_function("document.getElementById('report').textContent.includes('VulnerabilityID')")
                assert not page.evaluate('Boolean(window.bad)')
                for name,width in [('desktop',1440),('mobile',390)]:
                    page.set_viewport_size({'width':width,'height':1000})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'Diagnostics horizontal overflow'
                    page.screenshot(path=str(output/(name+'.png')),full_page=True)
                assert not errors,errors
                browser.close()
            (output/'result.json').write_text(json.dumps({'status':'passed','synthetic_collectors':True,'real_http_browser':True,'customer_changes':False,'checks':['owner-session','configured collector','projected Jenkins findings','Trivy import','XSS text escaping','report download link','desktop/mobile no overflow']},indent=2))
        finally:
            server.shutdown();server.server_close();worker.join(timeout=2)
    print('Diagnostic owner-session, collection/import, XSS and desktop/mobile browser checks passed (synthetic collectors).')


if __name__=='__main__':main()
