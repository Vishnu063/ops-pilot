# Architecture and reuse

Ops Pilot is a small Python-standard-library orchestrator/UI on top of a pinned
first-party dependency, DevOps Triage Assistant. Its immutable source reference
is declared in pyproject.toml. It is a dependency, not a fork or vendored copy.
No third-party code/models have been copied into this repository.

The monitor requests only read-only endpoint checks and incident collection.
An outage edge triggers one deep scan; repeated failed probes do not flood the
incident store. Manual investigation permits a new snapshot. A process-local
lock serializes monitoring and user actions. Only one Ops Pilot process should
manage a given state directory/target; there is no distributed leader election.

The existing ExperienceEngine and ToolEngine preserve exact plans, five-minute
expiry, approval/application separation, state fingerprint validation, consumed
approvals and state-plus-application verification. The Docker adapter includes
observed daemon identity in the fingerprint and executes against the captured
immutable container ID rather than a mutable container name. Final verification
checks that same ID/daemon. There is still a race if an operator retargets a Docker
context between identity validation and dispatch; freeze context configuration
and use one incident owner. No claim of atomic distributed transactions is made.

Restart is a fixed operation with bounded timeout, never AI-written shell code.
Timeout/interruption does not trigger a retry. An executing plan remains consumed;
inspect Docker state and history before issuing another authorization. No UI
button overrides this latch.

Health is two consecutive HTTP 200 probes out of three, with three-second request
timeouts and one-second intervals. Redirects are rejected. This can reject a slow
startup and does not test business transactions. Post-repair verification now permits a bounded 30-second readiness window (configurable 1–60 seconds), while keeping one repair attempt; see docs/ecosystem/INTEGRATION.md. HTTP and Docker may fail for
different reasons; the UI keeps evidence and hypotheses separate.

Optional upstream AI receives only filtered codes/metrics/signature counts and
health flags through numeric loopback HTTP, not raw logs or topology. This limits
its reasoning and does not establish root cause. Its output never enters the
command router. New AI providers must not silently change these data boundaries.

The dashboard is loopback-only with a fresh random startup token, HttpOnly
SameSite cookie, strict Host checks and Origin checks on mutations. It serves no
external scripts, styles or tracking. Configuration changes are local file/setup
operations, not web API input. One owner's processes are trusted; this is not a
multi-tenant authentication boundary. Browser reconnect/restart requires a new
login link. A leaked terminal link grants local/tunnel dashboard access.

Only approved, supported repairs may execute. There is no Uptime Kuma integration,
HolmesGPT integration, queue infrastructure or system service in this milestone.
Adding them would require real integration tests, permission/data-boundary review
and scope-specific documentation rather than broad compatibility claims.

## Daily operations (0.2)

`runtime.py` stores monitor controls and bounded alert delivery history in private
`monitor.sqlite3`, keyed by context/container/health URL. Timed maintenance probes
health but suppresses automatic investigation/alerts and blocks repair actions;
entering it cancels an outstanding pending/approved plan. Pause is persistent.
Webhook attempts commit before I/O, send only source/event, reject redirects and
proxies, and never retry automatically. A process crash can lose a delivery;
`attempting` is ambiguous. No delivery guarantee is claimed.

`/api/report` is an authenticated attachment built from the same filtered state.
No webhook destination, login token, raw inspect payload or raw log content is
included. The Docker parser adds RestartCount to the existing filtered projection.

`system_service.py` renders a fixed nonroot systemd entrypoint, with path/user
validation; the explicit installer refuses an occupied default port. It never
runs package installation at boot or alters an app container's startup policy.
Systemd restarts the monitor on failure; it does not approve/replay application
repairs. A full host reboot and production deployment still require host-specific
validation. See README for private journal/tunnel access and removal.
