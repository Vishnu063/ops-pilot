# Ops Pilot

[![Validate Ops Pilot](https://github.com/Vishnu063/ops-pilot/actions/workflows/checks.yml/badge.svg)](https://github.com/Vishnu063/ops-pilot/actions/workflows/checks.yml)

**Know what failed. Review a repair. Check that your application responds again.**

Ops Pilot watches **one Docker application**, investigates a failed endpoint,
shows the collected evidence and a supported restart option, and verifies the
Docker state **and** application endpoint after an explicitly approved restart.

**Early preview, v0.1.** One owner, one app, one loopback dashboard. No paid AI
API, model, Kubernetes cluster, n8n or separate monitoring server is required for
this first flow. Optional local AI explanations are advisory only. This is not a
production-certified autonomous DevOps engineer.

**Verified:** Python 3.11/3.12/3.13 checks, installed setup smoke, desktop/mobile
Chromium dashboard acceptance and three real disposable Docker tests passed. [Evidence and remaining limits](docs/VALIDATION.md).
On 19 October 2026, the owner also reported a successful manual EC2 demo: nginx
returned HTTP 200, stopping `ops-pilot-demo` triggered findings, and the dashboard
reported **Recovery checks passed** after the repair flow. This is user-reported
demo evidence, not an independently captured production test. CloudLaunch/PharmaCare
was not involved.

## Setup on Ubuntu / EC2

Run the server commands below in your **EC2 SSH terminal**. Run only the SSH
forwarding command in your **Mac/computer terminal**. Open login links in your
**browser**, never as shell commands. Keep AWS SSH access restricted to your IP.

Requires **Python 3.11+, Python venv, Git, curl and Docker CLI/daemon**. No GPU,
paid AI API or AI model is required. The launcher installs Python dependencies;
Docker and system packages are installed separately below. Existing working
Docker users can skip step 1.

### 1. Install prerequisites and enable Docker access

```bash
sudo apt update
sudo apt install -y git curl python3 python3-venv docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Disconnect and reconnect SSH so the Docker group takes effect. Alternatively,
run `newgrp docker` to open a shell with the new group. Start Ops Pilot from this
new shell too; a setup/server process already running in an older terminal keeps
its old permissions. Docker group membership grants powerful host access.

Check access without sudo:

```bash
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

An empty table means Docker works but there are no containers on this server.
If venv creation fails, install the venv package matching your Python version.
Select another supported interpreter with `OPS_PILOT_PYTHON=python3.12` if needed.

### 2. Choose your application (or create the demo)

For an existing owned app, use its exact container name from the table and its
actual readiness URL. Do not assume a container from another EC2 is present here.
For a first test on an empty server, create this separate nginx demo:

```bash
docker run -d --name ops-pilot-demo -p 127.0.0.1:8080:80 nginx:alpine
curl -I http://127.0.0.1:8080/
```

This downloads a small web-server image and serves its default welcome page only
on EC2 loopback port 8080. It is not CloudLaunch/PharmaCare. If the first curl
gets a connection reset while nginx starts, wait a few seconds and retry curl.
Continue only after **HTTP 200**; persistent failures need investigation.
If the container name already exists, inspect it with `docker ps -a` instead of
creating it again. If port 8080 is occupied, select a free host port and use that
same port in the health URL. Do not open 8080 in the security group for this demo.

### 3. Download and configure Ops Pilot

Clone once into your chosen parent directory:

```bash
git clone https://github.com/Vishnu063/ops-pilot.git
cd ops-pilot
bash start.sh setup
```

If already cloned, enter the existing directory containing `start.sh`; do not
clone again inside it. The launcher creates `.venv` and installs this project and
its pinned Triage dependency. Setup connects one target and performs no repair.
For our demo, enter these four answers (paste plain text, without Markdown links):

| Setup prompt | Demo answer |
| --- | --- |
| Application name | `Demo App` |
| Docker context [default] | Press Enter |
| Exact container name or ID | `ops-pilot-demo` |
| Health URL (HTTPS, or local HTTP) | `http://127.0.0.1:8080/` |

For your own app, substitute its real name, Docker context, container and health
URL. If configuration already exists, setup asks you to type `replace` before
changing it. Stop an existing Ops Pilot server before changing configuration.

Start the dashboard and leave this terminal running:

```bash
bash start.sh
```

It prints a private login URL beginning with
`http://127.0.0.1:8767/login?token=...`. Copy the **complete actual URL**, including
the token. The dots are a placeholder, not a usable login. Do not share the URL,
commit it, or paste it into the EC2 shell. **Ctrl+C stops monitoring**; closing
SSH can also end this foreground process. No background service is installed.

### 4. Open it on your Mac/computer

Leave the server terminal open. Open a **second terminal on your Mac/computer**
and run your usual SSH command with local forwarding added:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 8767:127.0.0.1:8767 -i /path/to/key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

Replace the key path and public IP with your existing connection details. If
your normal SSH connection uses an SSH alias or a different username, reuse it.
With `-N`, the terminal stays open without a shell prompt; this is expected.
Keep this tunnel terminal open too.

Open **Safari/your browser on the same computer** and paste the full login URL
from step 3 into its address bar. `127.0.0.1` now reaches EC2 through SSH.
**Do not open port 8767 in the AWS security group.** Opening it alone cannot
reach this loopback-only preview. Public hosting is not supported in this version.

For a Linux computer running Ops Pilot locally, open the printed link directly;
no tunnel is needed. On a phone, use an SSH client supporting local forwarding.
GitHub's mobile app alone cannot run the server or establish the tunnel.

### 5. Test a failure and recovery (demo only)

First confirm the dashboard identifies `ops-pilot-demo` and shows **Endpoint
checks passed**. In another EC2 shell, deliberately stop only our demo:

```bash
docker stop ops-pilot-demo
```

On the dashboard:

1. Click **Investigate now**. Expect the stopped-container and failed-endpoint findings.
2. Click **Review restart option**. Inspect the exact command and confirm its
   immutable container ID belongs to `ops-pilot-demo`.
3. Paste the **current complete plan ID** into the field and click **Approve this plan**.
4. Click **Run approved restart** separately. Approval alone does not restart it.
5. Look for **Recovery checks passed** in repair history and a passing current
   endpoint check. If either fails, inspect the evidence before trying again.

Plans expire after five minutes. Review a fresh plan if expired; never reuse an
old example ID. This test deliberately interrupts only the disposable demo.
It proves this stopped-container flow, not general failure repair or AI quality.
For independent confirmation after recovery, run in an EC2 shell:

```bash
docker ps --filter name=ops-pilot-demo
curl -I http://127.0.0.1:8080/
```

If abandoning the test with the demo still stopped, restore it manually with
`docker start ops-pilot-demo`. This manual fallback is not an Ops Pilot repair.

### Setup troubleshooting

| What you see | What to do |
| --- | --- |
| `docker: command not found` | Complete step 1. |
| Docker socket `permission denied` | Reconnect SSH or run `newgrp docker`; restart setup/server from that shell. Do not make the socket world-writable. |
| No Docker containers listed | Use the demo in step 2 or deploy your own app first. |
| nginx connection reset immediately after creation | Retry curl after startup; if persistent, inspect `docker logs --tail 50 ops-pilot-demo` locally. Redact secrets before sharing logs. |
| A URL gives shell `No such file or directory` | Paste the login URL into your computer's browser address bar. |
| `Use the fresh login link printed in your server terminal` | Copy the complete current URL. If needed, Ctrl+C in the server terminal, run `bash start.sh`, and use its newly printed URL. Every server restart changes the token. Keep the tunnel open. |
| Browser cannot connect | Check both server and tunnel are running and use the same port. The public EC2 IP is for SSH, not the dashboard URL. |
| SSH says local port 8767 is already in use | Close the old tunnel if it is yours. Otherwise choose `bash start.sh --port 8768` and change both tunnel ports to 8768; use the newly printed login URL. |
| Repair action refused or expired | Refresh, investigate current state and review a new plan. Used approvals cannot run twice. |

## The first complete flow

1. **Monitor:** Ops Pilot checks the configured endpoint every 30 seconds by
   default. A check needs two consecutive HTTP 200 responses within three attempts.
2. **Investigate:** a failed check triggers Docker metadata and bounded log-signature
   collection once per observed outage. Manual investigation is also available.
3. **Review:** choose **Review restart option**, inspect the exact command,
   immutable container ID, risks and expiry. A running-but-unhealthy app has no
   restart option in this preview; investigate its code/configuration instead.
4. **Approve:** type the complete plan ID. Approval does not execute anything.
5. **Run:** choose **Run approved restart**. The plan expires after five minutes;
   changed state/identity and reused approvals are rejected.
6. **Verify:** the same container must be running and its configured endpoint
   must pass. A running container with failed HTTP checks is **needs attention**.

The restart option can also apply to a supported restarting/dead container, and
may interrupt traffic or repeat the original fault. An intentional stop can look
like a failure: the owner must confirm that restarting is appropriate. No restart
rollback is available. Database migrations, image/configuration edits, deletion
and arbitrary shell commands are not supported repairs.

The health label is the latest endpoint check; the investigation is a separate,
timestamped snapshot. Recheck after external changes. Monitoring can be paused
without removing the saved incident. Restarting Ops Pilot resumes monitoring and
restores the latest stored plan for review; it **never replays an action**.

## What we reused

Ops Pilot depends on [DevOps Triage Assistant](https://github.com/Vishnu063/devops-triage-assistant)
at immutable commit `e4b51f28bb3dcd8395ab5fbfe93d946f19156031`.
It reuses the Docker collector, filtered evidence, persistent approval engine,
incident history and endpoint verification instead of copying or rebuilding them.
Ops Pilot adds a focused monitor, dashboard, config wizard, and stronger
container-ID/daemon-ID binding for this flow. Both repositories are maintained
by Vishnu063; see [dependency notes](docs/ARCHITECTURE.md).

Uptime Kuma, HolmesGPT, SigNoz and your Kubernetes toolkit are possible future
adapters, **not installed integrations**. The built-in endpoint watcher keeps
this first version smaller. HolmesGPT and customer accounts will be evaluated
separately, after the Docker flow is proven.

## Optional local AI

AI is **off by default**. A separately installed Ollama model can explain filtered
evidence; it cannot approve, generate or execute a repair. No model is downloaded
automatically. With an installed local model, pass its exact name:

```bash
bash start.sh --ai-model YOUR_INSTALLED_LOCAL_MODEL
```

The reused adapter requests CPU inference, a small context and immediate model
unloading. RAM, speed and answer quality depend on the model/host. The upstream
0.5B model failed answer-quality checks; this project does not recommend it as a
reliable investigator. Known contradictions may be withheld, but that filter is
not a general factual validator. Read the evidence first. No AI quality benchmark
has been completed for Ops Pilot.

## Configuration and daily commands

By default configuration is private at `~/.config/ops-pilot/config.json` and
state/history is at `~/.local/state/ops-pilot/`. The settings are read at startup;
restart after editing. Choose exact owned targets only. Example:

```json
{
  "name": "My application",
  "docker_context": "default",
  "container": "my-app",
  "health_url": "http://127.0.0.1:8080/health",
  "interval_seconds": 30
}
```

Use HTTPS for remote endpoints; HTTP is accepted only on loopback. The endpoint
has no authentication configuration in this first version. Choose a small,
side-effect-free readiness endpoint belonging to this application. An unrelated
HTTP 200 page can give misleading confidence. External Docker contexts require
existing authorized configuration; Docker privileges can be equivalent to root.

```bash
# Investigate once and print the filtered report; no repair
bash start.sh check

# Use a different dashboard port (update the SSH tunnel too)
bash start.sh --port 8768

# Update project first, then refresh its installation
git pull --ff-only
bash start.sh --update
```

`check` exits 0 for no supported findings, 1 for findings, 2 for setup/collection
failure. It is a bounded diagnostic result, not a universal health certification.
Monitoring runs only while the process runs. No systemd unit, unattended restart,
email delivery or webhook receiver is installed yet.

## Test before using on customer systems

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

The default suite simulates Docker and uses real local HTTP endpoints. The actual
Docker lab is explicitly enabled, creates uniquely labelled disposable containers,
introduces outages, tests approval/replay/state drift and failed HTTP recovery,
then removes its own containers. Run only on a development host with local Docker:

```bash
OPS_PILOT_DOCKER_LAB=1 .venv/bin/python -m unittest discover -s tests -p test_docker_lab.py -v
```

The lab downloads a Python container image. CI records its resolved digest and
Docker version. It never targets your configured application. See [validation](docs/VALIDATION.md)
for observed results, [architecture](docs/ARCHITECTURE.md) for boundaries, and
[security](SECURITY.md) before connecting production systems.

### Optional browser checks for contributors

Browser dependencies are for development/CI only; users do not need them to run
Ops Pilot. The browser flow uses simulated Docker plus real HTTP/SQLite. The
separate Docker lab above tests actual container operations.

```bash
source .venv/bin/activate
.venv/bin/python -m pip install playwright==1.58.0
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_acceptance.py
.venv/bin/python scripts/installation_smoke.py
```

On Linux, Playwright may need system browser libraries. CI installs them with
`python -m playwright install --with-deps chromium`. Synthetic screenshots and
`result.json` are written to ignored `browser-evidence/`; never put customer data
in this fixture. CI uploads the evidence for review. See [observed browser results](docs/VALIDATION.md#desktopmobile-browser-and-installed-setup-acceptance).

## Business/product roadmap

First prove this complete flow on disposable infrastructure. Next evaluate one
external alert adapter, better investigation quality, then customer separation,
authentication, audit retention and hosted deployment. The current local cookie
session is not customer RBAC. There is no public SaaS, billing or multi-customer
support yet. Hosting and optional AI still consume resources even when software
has no subscription fee. No production changes have been made by building this repo.
