# Owner-managed installation and operations

These instructions are for the owner to execute later on an authorized host. They
were not executed against production. PR #7 remains draft while the external
auto-deployment safety gate is unknown. Do not merge merely to try installation.
The supported boundary is one trusted POSIX owner and a loopback HTTP process,
not a public SaaS or multi-tenant service. Coolify stays disabled.

## Prerequisites and sizing

- Linux with POSIX file ownership, no-follow file opens and local SQLite locking.
  CI exercises Ubuntu runners; Ubuntu 24.04 with Python 3.12 is the recommended
  starting point. Python 3.11, 3.12 and 3.13 are CI-tested. Other operating systems
  and newer Python versions are not accepted by this review.
- Git, Python's venv support and trusted access to PyPI/GitHub for installation.
  The only application dependency is the immutable native-engine source archive
  in `pyproject.toml`. No model, GPU, Kubernetes, Redis or separate database is required.
- Docker CLI/context access is needed only for the configured Docker flow. Treat
  daemon access as host administration. Never publish its socket or use an
  unrestricted Docker TCP endpoint. Other collectors need their explicitly
  selected native CLI and least-privilege profile; no tool/account is auto-installed.
- There is no measured minimum hardware specification. A planning estimate for
  controller-only evaluation is one CPU, 1 GB RAM and 1 GB free disk, excluding
  monitored applications, images, evidence growth, backups and optional services.
  This is an estimate, not load-test evidence. Sequential CI labs fit an enforced
  8 GB budget; concurrent Jenkins/Kubernetes/monitoring/models need separate sizing.
- Use an owner-only local state filesystem, not an unvalidated network share.
  Budget backup space for the entire state tree and SQLite journals. Reports have
  admission/retention limits; archive evidence before reaching them.

## Install an exact reviewed revision

The `$` characters below are shell prompts, not part of the commands. Set the
commit to the exact reviewed PR/release SHA; do not substitute a moving branch
for a verified release. These commands install software only, with no server start.

```sh
$ set -euo pipefail
$ umask 077
$ OPS_PILOT_COMMIT='REPLACE_WITH_REVIEWED_40_CHARACTER_SHA'
$ [[ "$OPS_PILOT_COMMIT" =~ ^[0-9a-f]{40}$ ]]
$ git clone https://github.com/Vishnu063/ops-pilot.git ops-pilot-reviewed
$ cd ops-pilot-reviewed
$ git switch --detach "$OPS_PILOT_COMMIT"
$ test "$(git rev-parse HEAD)" = "$OPS_PILOT_COMMIT"
$ python3.12 -m venv .venv
$ .venv/bin/python -m pip install .
$ .venv/bin/python -m pip check
$ .venv/bin/python -m ops_pilot.cli --help
```

Record the commit, Python version and installed dependency inventory privately.
The install is from the selected working tree with a pinned native source;
build tools and index downloads are not a reproducible locked/offline supply chain.

## Private configuration and local startup

No environment variable is required for the ordinary deterministic Docker flow.
Default configuration is `~/.config/ops-pilot/config.json`; default state is
`~/.local/state/ops-pilot`. Override only with explicit `--config`/`--state-dir`.
Configuration must be an owner-controlled regular file, mode 0600, with one hard
link and no symlink components. The Docker target file is bounded to 8 KiB.
Do not place tokens in it. The wizard creates it privately; inspect an existing
file before using the wizard's explicit replacement option.

This first command records one exact authorized target and a side-effect-free
application health endpoint. Setup does not connect, restart or deploy anything.

```sh
$ .venv/bin/python -m ops_pilot.cli setup
```

Example shape, with placeholders rather than a real target:

```json
{"name":"Owned evaluation app","docker_context":"owned-readonly-context","container":"owned-app","health_url":"http://127.0.0.1:8080/health","interval_seconds":30,"health_attempts":3,"health_interval":1}
```

Use native context permissions appropriate to the selected operation. The
application cannot reduce privileges already granted to a Docker credential.
Start the foreground loopback dashboard only when ready for permitted reads:

```sh
$ .venv/bin/python -m ops_pilot.cli serve
```

Open the printed private login link in a local browser. The random HttpOnly,
SameSite=Strict owner cookie is a bearer capability, not a user account. It
rotates on restart; there is no independently verified public TLS proxy, user
RBAC or multi-tenant isolation. No public bind flag is provided. Keep the login
link out of shared terminals, logs and reports. Ctrl+C ends the foreground server.
Do not install a system service until the foreground setup has been reviewed;
the existing service guide describes that separate owner action.

## Controller and application health checks

This unauthenticated probe should return HTTP 401. It verifies the loopback
listener and authentication boundary only; it does not prove monitor readiness.

```sh
$ curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' --max-time 5 http://127.0.0.1:8767/api/state
```

After private browser login, inspect `/api/state`: wait for `busy: false`, a fresh
`monitor.checked_at`, `monitor.error: null` and the configured endpoint result.
An authenticated state response alone is not proof of application recovery.
There is no public `/healthz` or `/readyz` API; do not configure a load balancer
to interpret a 401 as application health.

For one read-only Docker investigation, the following command persists a report
and returns 0 for no findings, 1 for findings or 2 for collection/configuration
failure. Preserve nonzero results for investigation instead of retrying repairs.

```sh
$ .venv/bin/python -m ops_pilot.cli check
```

Only the separate reviewed plan → approve → apply controls can restart the exact
eligible target. Approval is not execution. Missing evidence, stale identity,
expiry, replay, maintenance or uncertainty must refuse execution. A successful
restart request is insufficient: runtime identity and consecutive endpoint health
must pass. Timeouts can leave an unknown remote outcome; inspect before any new plan.

## Optional settings: keep disabled unless explicitly configured

| Setting | Purpose and safe default |
| --- | --- |
| `--diagnostics-config` | Optional private 16 KiB read-only collector profile; absent by default. See `SELF-HOSTING.md` and `core/RUNBOOK.md`. |
| Native AWS/kube/ArgoCD profiles | Owner-selected exact account/context/namespace; use read-only IAM/RBAC. No provisioning/login automation. |
| Header/basic-auth environment bindings | Token variable **names** in diagnostic JSON; values only in a private environment/credential manager. Never echo them. |
| `OPS_PILOT_K8SGPT` | Leave unset; `1` opts into an already installed scoped analyzer, not model download or shell execution. |
| `--ai-model` | Leave absent; installed local Ollama advice is optional and untrusted. |
| `--ecosystem-service` | Leave absent; explicit service opts into authenticated event ingestion. Source/read keys must be distinct from owner/worker keys. |
| `OPS_PILOT_WORKFLOW_TOKEN`, `OPS_PILOT_OWNER_TOKEN` | Optional distinct agency bridge capabilities, each at least 32 characters. Leave unset without n8n. |
| `--fleet-config` | **Do not pass.** This is the opt-in for Coolify/fleet; a token variable or default-location file alone does not enable it. |
| `OPS_PILOT_LAB` and Docker/generated/service acceptance flags | Leave unset on operational installations. These are explicit disposable-development test gates. |

Coolify v4.5.3 is the documented contract, not live-verified compatibility.
Default-off tests require no provider requests, recovery calls or external browser
requests, and reject action routes. Live discovery needs a disposable instance,
exact authorized app UUID and privately configured read-only token. Recovery needs
separate exact-application/action authorization. Do not enable it based on mocks.

## Backup, restore and upgrades

Stop **all** Ops Pilot writers before an offline whole-state archive. Exported
incident JSON is not a full backup. Include fleet, diagnostics, monitor and native
SQLite files plus journals; keep credentials separately encrypted and outside Git.
These commands only archive an already stopped private state tree:

```sh
$ umask 077
$ OPS_PILOT_STATE="$HOME/.local/state/ops-pilot"
$ OPS_PILOT_BACKUPS="$HOME/ops-pilot-private-backups"
$ mkdir -p "$OPS_PILOT_BACKUPS"
$ chmod 700 "$OPS_PILOT_BACKUPS"
$ tar --create --gzip --file "$OPS_PILOT_BACKUPS/state-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" --directory "$(dirname "$OPS_PILOT_STATE")" -- "$(basename "$OPS_PILOT_STATE")"
```

The existing agency-only backup uses SQLite's consistent snapshot API and
includes agency artifacts/business records, **not** monitor/native/fleet state,
credential files or n8n volumes. The destination must be fresh and have an existing
non-symlink parent. Verification bounds the manifest, rejects linked/special files,
streams hashes and opens the exact percent-escaped database read-only.

```sh
$ .venv/bin/python -m ops_pilot.backup backup "$OPS_PILOT_STATE" "$OPS_PILOT_BACKUPS/agency-snapshot"
$ .venv/bin/python -m ops_pilot.backup verify "$OPS_PILOT_BACKUPS/agency-snapshot"
$ .venv/bin/python -m ops_pilot.backup restore "$OPS_PILOT_BACKUPS/agency-snapshot" "$OPS_PILOT_BACKUPS/agency-restored-review"
```

Agency restore creates a fresh destination, clears recovered job approvals and
marks an in-progress lab interrupted. Validate the result privately before use.
Whole-state archives can contain pending/executing native/fleet approvals: restore
them only for offline historical inspection, never into an active repair process.
Use fresh operational state and reconcile actual outstanding remote operations.
There is no generic safe native/fleet approval-restoration or schema-downgrade tool.

Before upgrading, record the old exact code/dependency versions, stop writers and
back up. Install the reviewed new commit in a separate checkout/venv and validate
against disposable state first. Existing stores use additive table/compatibility
initialization; this is not a versioned general migration framework. Do not run
old and new processes against the same state during an upgrade. For code rollback,
return to the reviewed old checkout only after state compatibility is established
offline. Application/data/Helm rollback is separate and never automatic here.

## Troubleshooting and release limits

- Startup failure: confirm supported Python/venv, selected native CLI and an exact
  target; no default production target exists. Recheck config permissions privately.
  A symlink, FIFO, hard link, broad mode or oversized config file is refused. The event ledger and operation lock also enforce private owner-controlled paths. Inspect and
  deliberately replace an unsafe file; do not bypass security checks.
- HTTP 401/403: use the fresh private login, correct loopback Host and Origin.
  Reader/source/worker credentials do not confer owner repair authority.
- Busy or stale state: wait for bounded collection; inspect native access and
  last-success timestamps. Unavailable/stale metrics are unknown, not healthy.
- SQLite/retention error: check owner, free space, file/journal modes and admission
  limits. Preserve evidence; do not delete or reset approval/audit databases to retry.
- Unknown repair result: inspect saved receipt and actual target health. Do not
  clear an executing latch or replay a consumed approval.
- A successful lab does not certify customer integrations, remote notification
  delivery, reboot recovery, concurrent production load or public exposure.

Before owner-managed use, verify the reviewed commit/CI, private local OS account,
loopback-only exposure, read-only provider scopes, separate approval/execution,
backup/restore exercise, resource budget and secret handling. Inspect GitHub
Settings → Webhooks, Environments and Integrations → GitHub Apps, including any
provider repository/branch subscriptions, to clear the separate merge-safety gate.
No deployment or production acceptance is claimed by this document.
