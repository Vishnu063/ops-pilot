"""One explicit Docker application. No default production target."""
import json
import os
from pathlib import Path
import re
import tempfile
from triage.health import validate_health

DEFAULT_CONFIG = Path.home() / ".config/ops-pilot/config.json"
DEFAULT_STATE = Path.home() / ".local/state/ops-pilot"


def validate(value):
    allowed = {"name", "docker_context", "container", "health_url", "interval_seconds", "alert_url"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("Use only name, docker_context, container, health_url, interval_seconds and optional alert_url")
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
    health = {"url": value["health_url"], "attempts": 3, "successes": 2, "timeout": 3, "interval": 1}
    validate_health(health)
    if "alert_url" in value:
        url = value["alert_url"]
        if not isinstance(url, str) or not url or len(url) > 2000 or any(ord(c) < 33 for c in url):
            raise ValueError("Enter a valid alert_url or remove it to disable delivery")
        validate_health({**health, "url": url})
    return {**value, "interval_seconds": interval}, health


def load(path):
    path = Path(path).expanduser()
    if path.stat().st_size > 8192:
        raise ValueError("Configuration exceeds 8 KiB")
    return validate(json.loads(path.read_text()))


def save(path, value):
    value, _ = validate(value)
    path = Path(path).expanduser()
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
