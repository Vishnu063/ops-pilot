"""Actual generated Compose deployment. Opt in only on a disposable owned Docker host."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from ops_pilot.freelance import Workspace


@unittest.skipUnless(os.environ.get('OPS_PILOT_GENERATED_LAB')=='1' and shutil.which('docker'), 'requires explicit disposable Docker host opt-in')
class GeneratedBundleLab(unittest.TestCase):
    def test_generated_bundle_readiness_cleanup_and_unhealthy_path(self):
        # Pulling this practice image is a CI setup action, never performed by the worker.
        subprocess.run(['docker','pull','nginxinc/nginx-unprivileged:alpine'],check=True,capture_output=True,timeout=120)
        image = json.loads(subprocess.check_output(['docker','image','inspect','nginxinc/nginx-unprivileged:alpine']))[0]['RepoDigests'][0]
        with tempfile.TemporaryDirectory() as directory:
            ws = Workspace(directory)
            previous = {k:os.environ.get(k) for k in ('OPS_PILOT_LAB','OPS_PILOT_LAB_IMAGES')}
            os.environ.update(OPS_PILOT_LAB='1',OPS_PILOT_LAB_IMAGES=image)
            try:
                results=[]
                for health in ('/','/does-not-exist'):
                    job=ws.import_job(dict(title='SYNTHETIC Docker '+health,description='Docker stateless HTTP'))
                    def act(action,data=None):
                        nonlocal job
                        job=ws.act(dict(action=action,job_id=job['id'],revision=job['revision'],data=data or {}),owner=True)['job']
                    for a in ('scout','evaluator','manager','client','proposal','approve_proposal'): act(a)
                    act('accept',dict(confirmation=job['id']));act('approve_work',dict(confirmation=job['id']))
                    act('worker',dict(image=image,port=8080,health_path=health))
                    act('approve_lab',dict(confirmation=job['id']));act('lab_run')
                    print(json.dumps(job['lab'],sort_keys=True),flush=True)
                    self.assertEqual('verified',job['lab']['cleanup'])
                    self.assertEqual('passed' if health=='/' else 'failed',job['lab']['status'])
                    self.assertEqual(health=='/',job['lab']['runtime_verified'])
                    self.assertFalse(job['lab']['customer_runtime_verified'])
                    results.append(job['lab'])
                from pathlib import Path
                Path('generated-lab-evidence.json').write_text(json.dumps(results,indent=2))
            finally:
                for k,v in previous.items():
                    if v is None: os.environ.pop(k,None)
                    else: os.environ[k]=v
