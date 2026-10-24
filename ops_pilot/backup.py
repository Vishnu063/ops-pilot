"""Consistent private SQLite snapshots; artifacts are stored inside job payloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile


def verify(directory):
    root = Path(directory)
    manifest = json.loads((root/'manifest.json').read_text())
    path = root/'workspace.sqlite3'
    if root.is_symlink() or path.is_symlink() or manifest.get('version') != 1:
        raise ValueError('Unsupported backup or symlink')
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('Backup hash mismatch')
    with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup integrity check failed')
        for (payload,) in db.execute('SELECT payload FROM jobs'):
            json.loads(payload)
    return manifest


def backup(workspace, destination):
    dest = Path(destination)
    dest.mkdir(mode=0o700,parents=False,exist_ok=False)
    path = dest/'workspace.sqlite3'
    try:
        with workspace.lock, workspace.connect() as source, sqlite3.connect(path) as target:
            source.backup(target)
        path.chmod(0o600)
        manifest = dict(version=1,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            includes='SQLite jobs, artifacts, business records, approvals, events, payments and audit',
            excludes='Login/bridge credentials, monitoring workspace, n8n volumes/credentials, disposable lab directories')
        (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        (dest/'manifest.json').chmod(0o600)
        verify(dest)
        return manifest
    except Exception:
        shutil.rmtree(dest)
        raise


def restore(source, destination):
    manifest = verify(source)
    dest = Path(destination)
    dest.mkdir(mode=0o700,parents=False,exist_ok=False)
    try:
        root = dest/'freelance'; root.mkdir(mode=0o700)
        shutil.copyfile(Path(source)/'workspace.sqlite3',root/'workspace.sqlite3')
        (root/'workspace.sqlite3').chmod(0o600)
        if hashlib.sha256((root/'workspace.sqlite3').read_bytes()).hexdigest() != manifest['sha256']:
            raise ValueError('Backup changed during restore')
        # Old approvals must never authorize side effects following recovery.
        with sqlite3.connect(root/'workspace.sqlite3') as db:
            for ident,payload in db.execute('SELECT id,payload FROM jobs').fetchall():
                job = json.loads(payload); job['approvals'] = {}; job['revision'] += 1
                if job.get('lab',{}).get('status') == 'running':
                    job['lab']['status'] = 'interrupted'
                db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(job),ident))
        return dest
    except Exception:
        shutil.rmtree(dest)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('backup','verify','restore'))
    parser.add_argument('source'); parser.add_argument('destination',nargs='?')
    args = parser.parse_args()
    if args.operation == 'verify':
        verify(args.source)
    elif args.operation == 'restore':
        if not args.destination: parser.error('Fresh destination required')
        restore(args.source,args.destination)
    else:
        from .freelance import Workspace
        if not args.destination: parser.error('Fresh destination required')
        if not (Path(args.source)/'freelance/workspace.sqlite3').is_file():
            parser.error('Source workspace database does not exist')
        backup(Workspace(args.source),args.destination)
    print('Completed:',args.operation)


if __name__ == '__main__':
    main()
