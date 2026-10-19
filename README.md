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
No customer/EC2 application has been connected or changed.

## Get started on your Linux server

Requires **Python 3.11+, Python venv, Git and Docker CLI/daemon**. Your existing
Docker context must already have access to the application. Ops Pilot does not
install Docker, modify groups, provision EC2, or change firewall rules.

```bash
git clone https://github.com/Vishnu063/ops-pilot.git
cd ops-pilot
bash start.sh setup
bash start.sh
```

The first command downloads the project; setup asks four short questions:
application name, explicit Docker context, exact container name/ID and health URL.
The launcher creates a Python environment and installs the project and its pinned
Triage dependency. Later starts reuse the installation. Stop with **Ctrl+C**.

If Ubuntu says venv is missing:

```bash
sudo apt install python3-venv
```

Use the venv package matching your Python version if your distribution requires
it. To select another supported interpreter, set `OPS_PILOT_PYTHON=python3.12`.

### Open the dashboard

On the same computer, open the **private login link printed in the terminal**.
It starts with `http://127.0.0.1:8767/login?token=...`. Keep that link private.

For EC2, run this on your computer, using your existing SSH configuration:

```bash
ssh -L 8767:127.0.0.1:8767 ubuntu@YOUR_SERVER
```

Then open the terminal's login link in your computer's browser. Do not open port
8767 in your security group. On a phone, use an SSH client with local forwarding;
GitHub's mobile app alone cannot run this server or establish that tunnel.

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
