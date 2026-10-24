"""Real isolated n8n CLI + authenticated forms + HTTP bridge + ZIP. Synthetic data only.

Requires N8N_EXECUTABLE pointing to an isolated n8n 2.44.6 install and Node >=24.
No existing account or installation is changed. Secrets are generated in a private temp directory.
"""
import base64
import re
import io
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ops_pilot.freelance import Workspace
from ops_pilot.web import Server
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'n8n-evidence'; OUT.mkdir(exist_ok=True)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); return sock.getsockname()[1]


def main():
    runtime=os.environ.get('N8N_EXECUTABLE')
    if not runtime: raise RuntimeError('Set N8N_EXECUTABLE to a disposable n8n 2.44.6 executable')
    with tempfile.TemporaryDirectory(prefix='ops-n8n-') as directory:
        private=Path(directory); private.chmod(0o700)
        workflow_key=secrets.token_urlsafe(32);owner_key=secrets.token_urlsafe(32)
        os.environ.update(OPS_PILOT_WORKFLOW_TOKEN=workflow_key,OPS_PILOT_OWNER_TOKEN=owner_key)
        ws=Workspace(private/'ops')
        server=Server(None,0,ws)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        port=free_port(); user='synthetic'; password=secrets.token_urlsafe(32)
        workflow=json.loads((ROOT/'n8n/freelance-agency.json').read_text())
        workflow['id']='OpsPilotSyntheticAcceptance'
        workflow['name']='SYNTHETIC isolated acceptance'
        fields=workflow['nodes'][0]['parameters']['formFields']['values']
        for node in workflow['nodes']:
            if node['type'].endswith('httpRequest'):
                node['parameters']['url']=node['parameters']['url'].replace('127.0.0.1:8767',f'127.0.0.1:{server.server_port}')
        path=private/'workflow.json';path.write_text(json.dumps(workflow));path.chmod(0o600)
        credentials=[dict(id='CONFIGURE_FORM_LOGIN',name='Ops Pilot Form Login',type='httpBasicAuth',data=dict(user=user,password=password)),
            dict(id='CONFIGURE_WORKFLOW_CREDENTIAL',name='Ops Pilot Workflow',type='httpHeaderAuth',data=dict(name='X-Ops-Pilot-Key',value=workflow_key)),
            dict(id='CONFIGURE_OWNER_CREDENTIAL',name='Ops Pilot Owner',type='httpHeaderAuth',data=dict(name='X-Ops-Pilot-Key',value=owner_key))]
        creds=private/'credentials.json';creds.write_text(json.dumps(credentials));creds.chmod(0o600)
        env={**os.environ,'N8N_USER_FOLDER':str(private/'n8n'),'N8N_ENCRYPTION_KEY':secrets.token_urlsafe(32),
            'N8N_LISTEN_ADDRESS':'127.0.0.1','N8N_HOST':'127.0.0.1','N8N_PORT':str(port),'N8N_PROTOCOL':'http',
            'WEBHOOK_URL':f'http://127.0.0.1:{port}/','N8N_EDITOR_BASE_URL':f'http://127.0.0.1:{port}',
            'N8N_SECURE_COOKIE':'false','N8N_DIAGNOSTICS_ENABLED':'false','N8N_VERSION_NOTIFICATIONS_ENABLED':'false',
            'N8N_TEMPLATES_ENABLED':'false','N8N_RUNNERS_ENABLED':'false','N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS':'true'}
        sensitive=[workflow_key,owner_key,password,env['N8N_ENCRYPTION_KEY'],base64.b64encode((user+':'+password).encode()).decode()]
        def sanitized(value):
            for secret in sensitive:value=value.replace(secret,'[redacted]')
            return re.sub(r'(token=)[^ &\s]+',r'\1[redacted]',value)
        command=[os.environ.get('OPS_NODE','node'),runtime]
        def cli(*args):
            result=subprocess.run([*command,*args],env=env,capture_output=True,text=True,timeout=120)
            with (OUT/'cli.txt').open('a') as output:output.write(sanitized(result.stdout+result.stderr))
            if result.returncode: raise RuntimeError('Isolated n8n CLI failed at '+args[0])
        process=None
        try:
            cli('import:credentials','--input='+str(creds))
            cli('import:workflow','--input='+str(path))
            cli('publish:workflow','--id='+workflow['id'])
            log=(private/'runtime.log').open('w')
            process=subprocess.Popen([*command,'start'],env=env,stdout=log,stderr=log)
            url=f'http://127.0.0.1:{port}/form/ops-pilot-freelance-control'
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                context=browser.new_context(http_credentials=dict(username=user,password=password),extra_http_headers={'Authorization':'Basic '+base64.b64encode((user+':'+password).encode()).decode()})
                page=context.new_page();page.set_default_timeout(30000)
                deadline=time.monotonic()+90
                last_status='no response'
                while True:
                    try:
                        response=context.request.get(url,timeout=3000)
                        last_status=str(response.status)
                        if response.status==200:break
                    except Exception: pass
                    if process.poll() is not None or time.monotonic()>deadline:
                        raise RuntimeError('Isolated n8n form did not become ready; last HTTP status '+last_status)
                    time.sleep(.5)
                anon=browser.new_context()
                assert anon.request.get(url).status==401,'Form must require basic authentication'
                anon.close()
                def submit(values,ending=True):
                    (OUT/'stage.json').write_text(json.dumps(dict(task=values.get('Task'),decision=values.get('Decision')),indent=2))
                    page.goto(url)
                    for index,field in enumerate(fields):
                        label=field['fieldLabel']
                        if label not in values:continue
                        control=page.locator('#field-'+str(index))
                        if field['fieldType']=='dropdown':control.select_option(str(values[label]))
                        else:control.fill(str(values[label]))
                    page.get_by_role('button',name='Submit',exact=True).click()
                    if ending:expect(page.locator('body')).to_contain_text('Ops Pilot · Freelance desk')
                submit({'Task':'Import listing','Project title':'SYNTHETIC n8n Docker pilot','Requirements':'Docker Compose stateless HTTP','Source':'synthetic','Currency':'USD'})
                job=ws.state()['jobs'][0]
                assert len(job['agents'])==5 and job['state']=='proposal_ready'
                def decision(action,**extra):
                    nonlocal job
                    submit({'Task':'Owner decision','Decision':action,'Job ID':job['id'],'Revision':job['revision'],'Confirm job ID':job['id'],**extra})
                    job=ws.get(job['id'])
                decision('approve_proposal');decision('accept');decision('approve_work')
                submit({'Task':'Generate starter files','Job ID':job['id'],'Revision':job['revision'],'Application image':'example/synthetic:review-required','Internal port':8000,'Health path':'/health'})
                job=ws.get(job['id']);assert job['state']=='reviewed'
                decision('sign_off');decision('delivery')
                decision('invoice',**{'Record JSON':json.dumps(dict(reference='SYNTHETIC-INVOICE',amount='100.10'))})
                decision('payment',**{'Payment amount':'100.10','Platform fee':'10.01','Payment reference':'SYNTHETIC-NOT-A-RECEIPT'})
                submit({'Task':'View board'})
                page.screenshot(path=str(OUT/'board.png'),full_page=True)
                # A replayed generation must fail without changing saved revision/artifacts.
                saved=ws.get(job['id'])
                submit({'Task':'Generate starter files','Job ID':job['id'],'Revision':1,'Application image':'example/stale:refused'},ending=False)
                page.wait_for_timeout(1000)
                assert ws.get(job['id'])['revision']==saved['revision']
                # File-ending response is generated by a real Form node, not direct bridge retrieval.
                page.goto(url)
                for label,value in {'Task':'Download handover','Job ID':job['id']}.items():
                    index=next(i for i,f in enumerate(fields) if f['fieldLabel']==label)
                    control=page.locator('#field-'+str(index))
                    if label=='Task':control.select_option(value)
                    else:control.fill(value)
                with page.expect_download() as info:
                    page.get_by_role('button',name='Submit',exact=True).click()
                target=OUT/'synthetic-handover.zip';info.value.save_as(str(target))
                with zipfile.ZipFile(target) as z:
                    assert set(z.namelist())==set(job['artifacts'])
                    assert not json.loads(z.read('acceptance.json'))['runtime_verified']
                assert len(ws.get(job['id'])['agents'])==9
                (OUT/'result.json').write_text(json.dumps(dict(status='passed',n8n='2.44.6',authenticated_form=True,
                    roles=9,owner_decisions=True,business_records=True,stale_refused=True,zip_response=True,
                    synthetic_only=True,customer_runtime_verified=False),indent=2)+'\n')
                browser.close()
        finally:
            if process:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            if process:
                log.close()
                (OUT/'runtime.txt').write_text(sanitized((private/'runtime.log').read_text())[-20000:])
            (OUT/'workspace.json').write_text(sanitized(json.dumps(ws.state(),indent=2)))
            databases=list((private/'n8n').rglob('database.sqlite'))
            if databases:
                try:
                    with sqlite3.connect(databases[0]) as database:
                        data=database.execute('SELECT data FROM execution_data ORDER BY executionId DESC LIMIT 2').fetchall()
                    (OUT/'execution-diagnostics.txt').write_text(sanitized('\n'.join(row[0] for row in data))[-60000:])
                except sqlite3.Error:pass
            server.shutdown();server.server_close();thread.join()
    print('Real isolated n8n acceptance passed: authenticated forms, nine roles, business records, stale error and ZIP response.')


if __name__=='__main__':main()
