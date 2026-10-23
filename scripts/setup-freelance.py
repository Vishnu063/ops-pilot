"""Create private local bridge secrets. Never commits or installs a service."""
import argparse
import os
from pathlib import Path
import secrets

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--show-credentials',action='store_true',help='Display secrets locally for copying into n8n; never share the output')
args=parser.parse_args()
path=Path(__file__).resolve().parents[1]/'n8n/.env'
if not path.exists():
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f:
        for name in ('OPS_PILOT_WORKFLOW_TOKEN','OPS_PILOT_OWNER_TOKEN','N8N_ENCRYPTION_KEY'):
            f.write(name+'='+secrets.token_urlsafe(40)+'\n')
    print('Created private n8n/.env. Keep it and the n8n data volume backed up securely.')
else:
    print('Kept existing n8n/.env; no secrets changed.')
if args.show_credentials:
    print('PRIVATE: copy locally into n8n credentials; do not share this output.')
    for line in path.read_text().splitlines():
        if line.startswith(('OPS_PILOT_WORKFLOW_TOKEN=','OPS_PILOT_OWNER_TOKEN=')):
            print(line)
