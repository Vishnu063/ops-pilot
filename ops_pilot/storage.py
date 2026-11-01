"""Private owner-only SQLite files; no shared-host or tenant isolation claim."""
import os
from pathlib import Path
import sqlite3
import stat


class PrivateConnection(sqlite3.Connection):
    """SQLite's transaction context alone does not close the connection."""
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def private_database(path):
    """Prepare/recheck private storage before SQLite opens it.

    A private parent prevents replacement by another OS user between this check
    and SQLite opening the path. This cannot defend against the same UID, root,
    or a malicious filesystem; run only under the documented trusted owner.
    """
    path = Path(path).expanduser().absolute()
    for parent in (path.parent, *path.parent.parents):
        if parent.is_symlink():
            raise ValueError('State directory cannot contain symlinks')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = path.parent.stat()
    if parent.st_uid != os.getuid() or not stat.S_ISDIR(parent.st_mode):
        raise ValueError('State directory must belong to the current owner')
    # Inspect all database files before changing any existing file's permissions.
    paths = [path, *(Path(str(path)+suffix) for suffix in ('-journal', '-wal', '-shm'))]
    for candidate in paths:
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
            raise ValueError('State files must be regular files with one link belonging to the current owner')
    path.parent.chmod(0o700)
    for candidate in paths:
        flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if candidate == path:
            flags |= os.O_CREAT
        try:
            descriptor = os.open(candidate, flags, 0o600)
        except FileNotFoundError:
            continue
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                raise ValueError('State file changed during private preparation')
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
    return path
