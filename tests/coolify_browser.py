"""Desktop/mobile acceptance with REAL browser and MOCK Coolify HTTP, never production."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from test_coolify_http import fixture


def main():
    out=Path('coolify-evidence');out.mkdir(exist_ok=True)
    with fixture() as f,sync_playwright() as p:
        f['tick']()
        browser=p.chromium.launch()
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
        (out/'result.json').write_text(json.dumps(dict(status='passed',synthetic=True,api='Mock Coolify HTTP, not installed Coolify',scenarios=['healthy','failure','separate approval','verified recovery','disconnected connection','escaped metadata','report export','desktop/mobile'],mutations=f['remote'].mutations,page_errors=errors),indent=2)+'\n')


if __name__=='__main__':main()
