#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
if [[ $(id -u) == 0 ]]; then
  echo 'Run as your ordinary Docker-enabled user, not sudo/root.' >&2
  exit 1
fi
if [[ ! -x .venv/bin/python || ! -f "$HOME/.config/ops-pilot/config.json" ]]; then
  echo 'Run bash start.sh setup first.' >&2
  exit 1
fi
service_file=$(mktemp)
trap 'rm -f -- "$service_file"' EXIT
.venv/bin/python - "$PWD" "$HOME" "$(id -un)" > "$service_file" <<'PY'
import sys
from ops_pilot.system_service import unit
print(unit(*sys.argv[1:]), end='')
PY
if [[ ${1:-} == --print ]]; then
  cat "$service_file"
  exit 0
fi
if [[ $# != 0 ]]; then echo 'Usage: bash scripts/install-service.sh [--print]' >&2; exit 1; fi
# Refuse to compete with a foreground server or silently replace an active unit.
.venv/bin/python - <<'PY'
import socket
from ops_pilot.config import DEFAULT_CONFIG, load
load(DEFAULT_CONFIG)
with socket.socket() as sock:
    try:
        sock.bind(('127.0.0.1', 8767))
    except OSError:
        raise SystemExit('Port 8767 is occupied. Stop the existing Ops Pilot process/service first.')
PY
sudo install -m 0644 "$service_file" /etc/systemd/system/ops-pilot.service
sudo systemctl daemon-reload
sudo systemctl enable --now ops-pilot.service
sudo systemctl is-active --quiet ops-pilot.service
echo 'Service started. Check status: sudo systemctl status ops-pilot --no-pager'
echo 'Read the private login link locally: sudo journalctl -u ops-pilot -n 15 --no-pager'
