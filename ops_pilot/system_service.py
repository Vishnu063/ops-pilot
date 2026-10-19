"""Render a fixed systemd service; installation is an explicit shell command."""
from pathlib import Path
import re


def unit(root, home, user):
    root, home = str(Path(root).absolute()), str(Path(home).absolute())
    # Refuse systemd expansion/specifier injection; simple Linux install paths only.
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*[$]?', user) or user == 'root':
        raise ValueError('Install as the ordinary Linux user with Docker access')
    if any(not re.fullmatch(r'/[A-Za-z0-9_./-]+', p) or '..' in Path(p).parts for p in (root, home)):
        raise ValueError('Use absolute install/home paths with letters, numbers, slash, dot, dash or underscore')
    return f'''[Unit]
Description=Ops Pilot private application monitor
After=network-online.target docker.service
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User={user}
Environment=HOME={home}
Environment=PYTHONUNBUFFERED=1
WorkingDirectory={root}
ExecStart={root}/.venv/bin/python -m ops_pilot.cli
Restart=on-failure
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

[Install]
WantedBy=multi-user.target
'''
