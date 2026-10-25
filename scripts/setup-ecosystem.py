"""Generate new private optional integration configuration; never overwrite existing keys."""
import argparse
import os
from pathlib import Path
import secrets
import shlex


def create(directory):
    root=Path(directory).expanduser().resolve();root.mkdir(mode=0o700,parents=False,exist_ok=False)
    values={name:secrets.token_urlsafe(32) for name in ('OPS_PILOT_EVENTS_CLOUDLAUNCH','OPS_PILOT_EVENTS_PLATFORM','OPS_PILOT_EVENTS_ALERTMANAGER','OPS_PILOT_EVENTS_LABS','OPS_PILOT_READ_TOKEN','GRAFANA_ADMIN_PASSWORD')}
    for name,key in [('alert','OPS_PILOT_EVENTS_ALERTMANAGER'),('read','OPS_PILOT_READ_TOKEN')]:
        path=root/(name+'.key');fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(values[key])
    for name in ('prometheus','alertmanager'):(root/name).mkdir(mode=0o700)
    values.update(OPS_PILOT_READ_TOKEN_FILE=str(root/'read.key'),OPS_PILOT_ALERT_TOKEN_FILE=str(root/'alert.key'),
                  OPS_PILOT_MONITORING_DIR=str(root),OPS_PILOT_MONITOR_UID=str(os.getuid()),OPS_PILOT_MONITOR_GID=str(os.getgid()),
                  OPS_PILOT_PROMETHEUS_URL='http://127.0.0.1:19090',OPS_PILOT_PROM_JOB='ecosystem-app')
    path=root/'integration.env';fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:stream.write('\n'.join(key+'='+shlex.quote(value) for key,value in values.items())+'\n')
    return path

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('new_directory',type=Path);args=p.parse_args()
    print('Private configuration created:',create(args.new_directory));print('No services, accounts or customer resources were configured or started.')
