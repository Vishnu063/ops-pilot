"""Desktop/mobile acceptance with REAL browser and MOCK Coolify HTTP, never production."""
import json
import threading
from unittest.mock import patch
from urllib.parse import urlsplit
from ops_pilot.web import Server
from ops_pilot.coolify import Coolify, Transport
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_coolify_http import fixture


def disabled_browser_flow(browser,out):
    """Default server has no provider, even with owner access to fleet routes."""
    with patch.object(Coolify,'request',side_effect=AssertionError('Disabled provider request')) as request,patch.object(Coolify,'execute',side_effect=AssertionError('Disabled recovery')) as execute,patch.object(Transport,'request',side_effect=AssertionError('Disabled transport')) as transport:
        server=Server(None,0)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base='http://127.0.0.1:'+str(server.server_port)
        page=browser.new_page(viewport={'width':1280,'height':900})
        external=[];errors=[]
        page.on('request',lambda r:external.append(urlsplit(r.url).netloc) if urlsplit(r.url).netloc!=urlsplit(base).netloc else None)
        page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            page.goto(base+'/login?token='+server.token);page.goto(base+'/coolify')
            page.get_by_text('Configure a private --fleet-config to opt in',exact=True).wait_for()
            assert page.get_by_role('button',name='Propose restart',exact=True).count()==0
            assert page.get_by_role('button',name='Execute approved plan',exact=True).count()==0
            assert page.request.get(base+'/api/fleet/state').json()['enabled'] is False
            assert page.request.get(base+'/api/fleet/report').json()['enabled'] is False
            for action in ('plan','approve','execute'):
                response=page.request.post(base+'/api/fleet/action',headers={'Origin':base},data={'action':action,'app':'not-configured'})
                assert response.status==404
            page.screenshot(path=str(out/'disabled-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(out/'disabled-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not external and not errors
            request.assert_not_called();execute.assert_not_called();transport.assert_not_called()
            return {'enabled':False,'provider_requests':0,'recovery_calls':0,'external_browser_requests':0,'owner_actions':'404','desktop_mobile':'passed'}
        finally:
            page.close();server.shutdown();server.server_close();worker.join(timeout=5)


def main():
    out=Path('coolify-evidence');out.mkdir(exist_ok=True)
    with fixture() as f,sync_playwright() as p:
        f['tick']()
        browser=p.chromium.launch()
        disabled=disabled_browser_flow(browser,out)
        page=browser.new_page(viewport={'width':1280,'height':900})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f['base']+'/login?token='+f['server'].token);page.goto(f['base']+'/coolify')
        page.get_by_role('heading',name='Applications & Coolify',exact=True).wait_for()
        page.get_by_text('healthy',exact=True).first.wait_for()
        f['remote'].healthy=False;f['tick']();f['tick']();page.get_by_role('button',name='Refresh view',exact=True).click()
        page.get_by_role('button',name='Propose restart',exact=True).click()
        page.get_by_role('button',name='Approve this exact plan',exact=True).wait_for()
        assert f['remote'].mutations==0
        page.get_by_role('button',name='Approve this exact plan',exact=True).click()
        page.get_by_role('button',name='Execute approved plan',exact=True).click()
        page.get_by_text('Verification: verified',exact=True).wait_for();assert f['remote'].mutations==1
        page.get_by_role('button',name='Retrieve bounded logs',exact=True).click()
        # Untrusted metadata/log HTML is rendered as text; no injected script executes.
        assert not errors
        with page.expect_download() as download:page.get_by_role('button',name='Download report page',exact=True).click()
        report=json.loads(Path(download.value.path()).read_text());assert report['complete'] is True
        assert 'read-token-mock-only' not in json.dumps(report)
        page.screenshot(path=str(out/'desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(out/'mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        f['remote'].disconnected=True;f['tick']();page.get_by_role('button',name='Refresh view',exact=True).click()
        page.get_by_text('Unknown · connection stale',exact=True).wait_for()
        browser.close()
        (out/'result.json').write_text(json.dumps(dict(status='passed',synthetic=True,disabled_default=disabled,api='Mock Coolify HTTP, not installed Coolify',scenarios=['healthy','failure','separate approval','verified recovery','disconnected connection','escaped metadata','report export','desktop/mobile'],mutations=f['remote'].mutations,page_errors=errors),indent=2)+'\n')


if __name__=='__main__':main()
