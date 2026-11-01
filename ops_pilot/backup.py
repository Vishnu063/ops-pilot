"""Consistent private SQLite snapshots; artifacts are stored inside job payloads."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat


def checked_path(value):
    path = Path(value).expanduser().absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('Backup paths cannot contain symlinks')
    return path


def open_source(path):
    """Reject links/special files before reading; same UID/root remain trusted."""
    path = checked_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
            raise ValueError('Backup files must be regular, single-link files owned by this user')
        return os.fdopen(descriptor, 'rb')
    except BaseException:
        os.close(descriptor)
        raise


def digest(path):
    result = hashlib.sha256()
    with open_source(path) as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            result.update(chunk)
    return result.hexdigest()


def verify(directory):
    root = checked_path(directory)
    with open_source(root/'manifest.json') as stream:
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise ValueError('Backup manifest exceeds 8 KiB')
    manifest = json.loads(raw)
    path = root/'workspace.sqlite3'
    if (not isinstance(manifest, dict) or type(manifest.get('version')) is not int
            or manifest['version'] != 1 or not isinstance(manifest.get('sha256'), str)
            or len(manifest['sha256']) != 64 or any(c not in '0123456789abcdef' for c in manifest['sha256'])):
        raise ValueError('Unsupported backup manifest')
    if digest(path) != manifest['sha256']:
        raise ValueError('Backup hash mismatch')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup integrity check failed')
        for (payload,) in db.execute('SELECT payload FROM jobs'):
            json.loads(payload)
    return manifest


def backup(workspace, destination):
    dest = checked_path(destination)
    dest.mkdir(mode=0o700,parents=False,exist_ok=False)
    path = dest/'workspace.sqlite3'
    try:
        # Create privately before SQLite opens the file, rather than chmod afterwards.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        with workspace.lock, workspace.connect() as source, closing(sqlite3.connect(path)) as target:
            source.backup(target)
        path.chmod(0o600)
        manifest = dict(version=1,sha256=digest(path),
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
    source = checked_path(source)
    manifest = verify(source)
    dest = checked_path(destination)
    dest.mkdir(mode=0o700,parents=False,exist_ok=False)
    try:
        root = dest/'freelance'; root.mkdir(mode=0o700)
        path = root/'workspace.sqlite3'
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as target, open_source(source/'workspace.sqlite3') as original:
            shutil.copyfileobj(original, target, length=65536)
        if digest(path) != manifest['sha256']:
            raise ValueError('Backup changed during restore')
        # Old approvals must never authorize side effects following recovery.
        with closing(sqlite3.connect(path)) as db:
            with db:
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
