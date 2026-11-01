"""One explicit Docker application. No default production target."""
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from triage.health import validate_health

DEFAULT_CONFIG = Path.home() / ".config/ops-pilot/config.json"
DEFAULT_STATE = Path.home() / ".local/state/ops-pilot"


def validate(value):
    allowed = {"name", "docker_context", "container", "health_url", "interval_seconds", "alert_url", "health_attempts", "health_interval"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("Use only documented target, interval, alert and bounded health-policy fields")
    for key in ("name", "docker_context", "container", "health_url"):
        item = value.get(key)
        if not isinstance(item, str) or not item.strip() or len(item) > 500 or any(ord(c) < 32 for c in item):
            raise ValueError("Enter a valid " + key)
    for key in ("docker_context", "container"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value[key]):
            raise ValueError(key + " must be one exact name or ID, without wildcards or options")
    interval = value.get("interval_seconds", 30)
    if type(interval) is not int or not 15 <= interval <= 3600:
        raise ValueError("interval_seconds must be an integer between 15 and 3600")
    attempts=value.get("health_attempts",3); probe_interval=value.get("health_interval",1)
    if type(attempts) is not int or not 3<=attempts<=5 or type(probe_interval) is not int or not 0<=probe_interval<=2:
        raise ValueError("health_attempts must be 3–5 and health_interval 0–2 seconds")
    health = {"url": value["health_url"], "attempts": attempts, "successes": 2, "timeout": 3, "interval": probe_interval}
    validate_health(health)
    if "alert_url" in value:
        url = value["alert_url"]
        if not isinstance(url, str) or not url or len(url) > 2000 or any(ord(c) < 33 for c in url):
            raise ValueError("Enter a valid alert_url or remove it to disable delivery")
        validate_health({**health, "url": url})
    return {**value, "interval_seconds": interval}, health


def load(path):
    path = configuration_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError("Configuration must be a private, owner-controlled regular file")
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read(8193)
        if len(raw) > 8192:
            raise ValueError("Configuration exceeds 8 KiB")
        return validate(json.loads(raw))
    finally:
        os.close(descriptor)


def configuration_path(path):
    path = Path(path).expanduser().absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Configuration paths cannot contain symlinks")
    return path


def save(path, value):
    value, _ = validate(value)
    path = configuration_path(path)
    if path.exists():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
            raise ValueError("Existing configuration must be an owner-controlled regular file with one link")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".ops-pilot-")
    try:
        with os.fdopen(descriptor, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, indent=2)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

