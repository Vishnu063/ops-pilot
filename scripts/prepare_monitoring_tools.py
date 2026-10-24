#!/usr/bin/env python3
"""Extract pinned official monitoring binaries without starting any service."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

IMAGES = {
    'prom/prometheus:v3.7.0@sha256:29c1e0b48ad816750245dea3d65ac3ce57dda30547e67b1e9a5176e2953cc4dc': ('prometheus', 'promtool'),
    'prom/alertmanager:v0.28.1@sha256:27c475db5fb156cab31d5c18a4251ac7ed567746a2483ff264516437a39b15ba': ('alertmanager', 'amtool'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools', type=Path, required=True)
    args = parser.parse_args()
    args.tools.mkdir(parents=True, exist_ok=True)
    manifest_path = args.tools / 'monitoring-sources.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    docker = ['docker', '--host=unix:///var/run/docker.sock']
    for image, names in IMAGES.items():
        if all((args.tools/name).is_file() and manifest.get(name)=={'image':image,'sha256':sha(args.tools/name)} for name in names):
            continue
        subprocess.run(docker+['pull',image], check=True)
        container = subprocess.check_output(docker+['create','--label','ecosystem.tools=true',image],text=True).strip()
        try:
            with tempfile.TemporaryDirectory(dir=args.tools.parent) as temporary:
                for name in names:
                    downloaded = Path(temporary)/name
                    subprocess.run(docker+['cp',container+':/bin/'+name,str(downloaded)],check=True)
                    destination = args.tools/name
                    if destination.exists() and sha(destination)!=sha(downloaded):
                        raise RuntimeError('Refusing to overwrite a different existing tool: '+name)
                    if not destination.exists(): downloaded.replace(destination)
                    manifest[name] = {'image':image,'sha256':sha(destination)}
        finally:
            subprocess.run(docker+['rm',container],check=True,stdout=subprocess.DEVNULL)
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    print('Verified reusable monitoring tools; no service started')


if __name__ == '__main__': main()
