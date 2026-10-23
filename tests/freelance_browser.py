"""Real browser + local HTTP/SQLite; synthetic listings, no platform/customer access."""
import json
import os
from pathlib import Path
import tempfile
import threading
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from ops_pilot.freelance import Workspace
from ops_pilot.web import Server

root=Path(__file__).resolve().parents[1]
output=root/'freelance-evidence';output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as directory:
    workspace=Workspace(directory)
    server=Server(None,0,workspace)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            options=dict(headless=True)
            if os.environ.get('OPS_PILOT_CHROMIUM'):
                options.update(executable_path=os.environ['OPS_PILOT_CHROMIUM'],args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-zygote','--single-process','--use-gl=angle','--use-angle=swiftshader','--disable-features=Vulkan'])
            browser=p.chromium.launch(**options)
            page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/login?token={server.token}')
            page.get_by_role('button',name='Load demo',exact=True).click()
            page.get_by_role('button',name='Run planning team',exact=True).wait_for()
            page.get_by_role('button',name='Run planning team',exact=True).click()
            page.get_by_role('button',name='Approve proposal',exact=True).wait_for()
            page.screenshot(path=str(output/'desktop.png'),full_page=True)
            job=workspace.state()['jobs'][0]
            page.get_by_role('button',name='Approve proposal',exact=True).click()
            page.get_by_role('button',name='Record client acceptance',exact=True).wait_for()
            page.locator('#confirmation').fill(job['id'])
            page.get_by_role('button',name='Record client acceptance',exact=True).click()
            page.get_by_role('button',name='Approve work',exact=True).wait_for()
            page.get_by_role('button',name='Approve work',exact=True).click()
            page.get_by_role('button',name='Generate starter files',exact=True).wait_for()
            page.locator('#image').fill('example/demo:review-required')
            page.get_by_role('button',name='Generate starter files',exact=True).click()
            page.get_by_role('button',name='Check starter files',exact=True).wait_for()
            page.get_by_role('button',name='Check starter files',exact=True).click()
            page.get_by_role('button',name='Sign off reviewed files',exact=True).wait_for()
            page.get_by_role('button',name='Sign off reviewed files',exact=True).click()
            page.get_by_role('button',name='Package handover',exact=True).wait_for()
            page.get_by_role('button',name='Package handover',exact=True).click()
            page.get_by_role('link',name='Download handover ZIP',exact=True).wait_for()
            with page.expect_download() as info:
                page.get_by_role('link',name='Download handover ZIP',exact=True).click()
            info.value.save_as(str(output/'synthetic-handover.zip'))
            page.get_by_role('button',name='Refresh earnings',exact=True).click()
            expect(page.locator('#message')).to_have_text('Saved: earnings')
            page.get_by_text('Requirements and business records',exact=True).click()
            page.locator('#record-action').select_option('invoice')
            page.locator('#record-data').fill(json.dumps(dict(reference='SYNTHETIC-INVOICE',amount='100.10')))
            page.get_by_role('button',name='Save owner record',exact=True).click()
            expect(page.locator('#message')).to_have_text('Saved: invoice')
            expect(page.locator('#business-status')).to_contain_text('Outstanding USD 100.10')
            page.screenshot(path=str(output/'packaged.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile overflow'
            assert not errors,errors
            assert len(workspace.get(job['id'])['agents'])==9
            (output/'result.json').write_text(json.dumps(dict(status='passed',roles=9,zip_downloaded=True,mobile_overflow=False,page_errors=errors,chromium=browser.version),indent=2))
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
print('Freelance browser flow passed: all 9 roles, separate approvals, ZIP download, desktop/mobile.')
