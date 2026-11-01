# Optional Coolify and multi-application operation

This release is a single trusted local-owner integration, not a hosted multi-customer service. Existing Docker configuration, CLI commands, routes, agency studio, n8n and native approval engine are preserved. Coolify is optional. No Redis, queue service, extra database server, Kubernetes requirement, model or paid API is added.

## Install and configure

Use the existing [self-hosting guide](../SELF-HOSTING.md) to install Ops Pilot on a supported Linux host. Keep the web server on loopback, use SSH forwarding, and keep Docker sockets off public ports. Docker access can grant host-level privileges. Run with an OS account and explicit Docker contexts restricted to infrastructure you own; no general shell/action endpoint exists.

Create `~/.config/ops-pilot/fleet.json` with mode 0600 inside a private directory. Example (nonsecret):

```json
{
  "instances": [{
    "id": "staging",
    "base_url": "https://coolify.example.com",
    "token_env": "OPS_PILOT_COOLIFY_READ",
    "repair_token_env": "OPS_PILOT_COOLIFY_DEPLOY",
    "timeout": 3,
    "log_lines": 100
  }],
  "applications": [{
    "id": "example-staging",
    "instance": "staging",
    "uuid": "REPLACE_EXACT_APPLICATION_UUID",
    "name": "Example staging",
    "health_url": "https://app.example.com/ready",
    "expected_status": 200,
    "timeout": 3,
    "interval": 60,
    "failure_threshold": 3,
    "recovery_threshold": 2,
    "actions": [],
    "notify": true,
    "maintenance_until": 0
  }],
  "docker_applications": []
}
```

Begin read-only: omit `repair_token_env`, leave `actions: []`. Read bindings need Coolify `read`; retrieving logs separately needs `read:sensitive`. Use a **different**, narrowly scoped team token with `deploy` only when a real controlled test has been authorized. Load token values through your OS secret manager/private service environment; do not paste them into CLI arguments, JSON, source code or screenshots. Ops Pilot stores only binding names; it never returns environment credentials to the browser or an AI model. Environment variables remain readable to the same OS owner/root; this is not a managed secret vault. Rotation invalidates pending fleet approvals. Restart Ops Pilot to reload configuration.

Configured origins must use HTTPS with certificate validation; no userinfo/query/fragment or `/api/v1` suffix. Redirects are refused. DNS is resolved, every result checked, and the connection pins a validated IP while retaining TLS hostname verification. Global addresses are allowed; metadata, link-local and unspecified destinations are blocked. Private networks require an explicit per-instance `private_ips` list of exact private addresses, which also applies to its configured health endpoint. No CIDRs or web-input URL editor. Loopback HTTP is available only with `allow_loopback: true` and a literal loopback host/localhost, for owned local testing. No remote HTTP, disabled TLS or certificate bypass. Networking uses direct configured destinations (no ambient credential-bearing proxy); managed environments may require authorized TCP/VPN access. DNS resolution depends on the host resolver.

Commands (the `$` is a display prompt):

```sh
$ chmod 600 ~/.config/ops-pilot/fleet.json
$ ops-pilot check-fleet --fleet-config ~/.config/ops-pilot/fleet.json
$ ops-pilot fleet --fleet-config ~/.config/ops-pilot/fleet.json
```

Open the printed private login link, then Applications & Coolify. The fleet command works without a default Docker target. Add `--fleet-config` to existing `serve`/`freelance` operation to share its original pages. `check-fleet` performs one bounded observation (not enough by itself to satisfy several consecutive thresholds). Exit 2 denotes a provider connection problem, 1 an active incident, 0 no active detected incident; this does not prove complete readiness.

Discovery does not enroll or execute anything. Copy exact UUIDs into the private profile. Limits: four Coolify instances, twenty configured Coolify apps and four additional native Docker profiles. Polling is sequential across Coolify apps with one fleet operation lock; native Docker monitors have independent existing locks/intervals. Manual Coolify checks have a five-second minimum; connection outages respect app intervals. Allow longer monitoring latency when several endpoints time out. Response bodies/logs/audit exports and persisted records are capped; archive privately when retention is reached. No deletion automation is introduced. Start with long intervals on modest hosts and size your own workload before scaling.

For independent additional Docker apps, reuse the existing original target config format in separate private files:

```json
{"instances": [], "applications": [], "docker_applications": [
  {"id": "docker-staging", "config_file": "/home/operator/.config/ops-pilot/docker-staging.json"}
]}
```

Each profile has an exact Docker context/container, name and health URL, and isolated state under `fleet-docker/<id>`. Investigation/planning/approval/apply delegate to the existing native engine. The original default Docker dashboard and configuration are unchanged. Fleet-specific thresholds/Telegram currently apply to Coolify; native Docker retains its original health policy and webhook alerts. Do not run two independent controllers against the same Docker target.

## Daily operation and incident review

Application state separates runtime, provider health, configured endpoint and recent deployment. An API outage marks the connection unavailable and cached app evidence stale; it does not assert all apps failed. Consecutive-failure thresholds open one incident for an ongoing app failure. Consecutive healthy observations resolve it. A deploying app is shown as deploying; deployment history is retained. No diagnosis asserts memory/disk root cause without trustworthy metrics. Coolify resource-metric diagnosis is not implemented; use the existing separately scoped diagnostics/monitoring desk.

Review what failed, timestamps, evidence, confidence/missing evidence, recent deployments and recommended next steps. Retrieve bounded logs on demand. Logs/metadata are untrusted and HTML-escaped; the executor never interprets log content. Redaction is best effort beyond known credentials and common patterns: review sensitive evidence locally before sharing. Do not include customer PII in notification text.

To allow a tested operation, add `restart` or `redeploy` to that app's `actions`. Restart/redeploy can interrupt users; configured deploy commands/migrations are Coolify-side effects requiring operator review. Redeploy requires an immutable full git commit in Coolify config; floating tags/branches are refused. Plans require a current incident, available deployment history, no active deployment and an explicit readiness URL. Plans expire after 120 seconds. Review target UUID/instance, evidence, impact and verification criteria; approve, then separately execute. A new plan supersedes previous pending approvals. Exact policy/credential binding rotation, revision, observed state, endpoint or deployment changes invalidate execution. The remote API offers no atomic compare-and-swap: stop competing deployment controllers during recovery; a remote change after the last check is a remaining race risk.

Execution consumes approval durably before I/O and locks out conflicting app execution across processes. Five-minute persisted cooldown follows an outcome. POST requests are not retried. A timeout or malformed receipt is **unknown**, not failure proof and not safe to repeat automatically. Verification requires exact app UUID running, exact receipt deployment `finished`, and consecutive expected endpoint responses within five bounded checks. Remaining unhealthy/queued is `needs_attention`. The incident resolves only after subsequent sustained monitor observations. No generic rollback is provided. Use your separately tested deployment rollback procedure with separate authorization.

Planned maintenance: set an epoch `maintenance_until` in the app profile, restart to reload, and verify the deadline in the private config. Detection continues, new incidents/notifications and repairs are suppressed during the window. Existing incidents remain reviewable. Docker profiles retain their existing native maintenance controls through the original workflow.

## Notifications

Optional Telegram configuration:

```json
{"provider":"telegram","token_env":"OPS_PILOT_TELEGRAM_BOT","chat_id":"123456789","min_severity":"warning"}
```

Place this under `notification` in the profile; load the bot token privately. Telegram is an external service with its own terms; creating a bot/account is an operator action, not performed here. Events include detected incident, approval needed, recovery completed/failed, restored application and lost monitoring connection. Messages contain an event name only, no logs, credentials, targets or login URLs. Provider `ok:true` and a message ID are needed for `confirmed`. Delivery failures/timeouts remain failed-or-unknown; no crash replay. Deduplication is persisted; a global 30-second rate cap explicitly records suppressed events. Known Telegram 429 retry-after up to two seconds is retried once; ambiguous network errors are never retried. Current Coolify app incidents use warning severity; `critical` threshold suppresses these warnings until a future trustworthy critical classifier exists. Suppression during maintenance is explicit. No live Telegram delivery is claimed by mock tests.

## Reports, retention and recovery

The dashboard downloads the first bounded report page. `/api/fleet/report?after=<next_after>` requires the owner cookie and pages through the audit in batches of 100. Inspect `complete`/`next_after`; one page is not advertised as the whole archive. State snapshots are not transactionally frozen across pages. SQLite data is private; audit rows are append-only with a hash chain. Root/owner can still alter files. Archive the fleet directory using an offline consistent SQLite backup and protect that backup like credentials. The existing agency backup command covers the agency database, **not** fleet/Docker/native state. Do not restore old approvals into service. A process crash during execution leaves `executing` and blocks further repairs: inspect the remote receipt/deployments and database offline, preserve audit, then ask a maintainer for explicit reconciliation; never clear this automatically. No production recovery tool is supplied for that state.

## Security review and release gates

Existing local owner session, SameSite cookie, exact Host and Origin checks cover fleet reads/actions. Bridge/read/source credentials cannot operate fleet APIs. No public bind/signup/multi-user UI is added. Local single-owner sessions are not role/tenant isolation. Cross-tenant security is not claimed because tenant mode is disabled. New tests cover session/CSRF, wrong target, expiry/replay, credential rotation, changed preconditions, concurrency, unavailable services, redaction and SSRF. TLS/DNS transport tests are mocked; real deployment needs certificate/network validation. Source Bandit and immutable dependency checks are scoped checks, not vulnerability clearance. Coolify/server/container dependency CVEs and Docker socket isolation require deployment-specific review.

Future tenant entities: organization owns users/roles, servers/connections, encrypted credential bindings, apps, incidents, actions and audit. Every lookup must enforce tenant scope; add cross-tenant tests, per-tenant secrets/sessions/RBAC, retention/deletion and scoped exports before hosting unrelated customers. No tenant selector, billing or shared customer installation is enabled now.

Quality-review note: regenerate pending plans after upgrading the identity projection. Receipt verification requires the exact returned deployment UUID and its application_id matching the target's id; explicit provider unhealthy prevents verified success. Unavailable evidence resets consecutive counters. Known receipts are persisted before subsequent checks so a verification timeout can be reconciled manually. [Audit and validation limits](QUALITY-REVIEW.md).
