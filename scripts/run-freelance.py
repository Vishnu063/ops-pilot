"""Load only bridge keys from the private file, then launch the loopback workspace."""
import os
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
path=root/'n8n/.env'
if not path.exists():
    raise SystemExit('First run python scripts/setup-freelance.py to create private bridge keys.')
if path.stat().st_mode & 0o077:
    raise SystemExit('n8n/.env must be private. Run chmod 600 n8n/.env to remove group/other access.')
for line in path.read_text().splitlines():
    key,sep,value=line.partition('=')
    if sep and key in ('OPS_PILOT_WORKFLOW_TOKEN','OPS_PILOT_OWNER_TOKEN'):
        os.environ[key]=value
sys.path.insert(0,str(root))
from ops_pilot.cli import main
sys.argv=[sys.argv[0],'freelance',*sys.argv[1:]]
raise SystemExit(main())
