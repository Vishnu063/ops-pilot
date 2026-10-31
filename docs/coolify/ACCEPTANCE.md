# Validation and a future controlled instance test

All Coolify tests in this PR use deterministic mocked responses or an explicitly labelled local mock HTTP server. They do not prove an installed Coolify release or real Telegram delivery. No production application, AWS resource or billing was accessed.

Baseline before edits: 79 cases, 54 passed, 21 socket-permission errors and four opt-in Docker skips in this sandbox. New deterministic tests initially pass (32 cases); current CI evidence is recorded below when available. Full local HTTP/browser tests cannot run because local TCP/Unix socket creation is denied. Existing source/shell/JS checks must remain enabled in CI.

Acceptance coverage:

| Scenario | Automated check | External gate |
| --- | --- | --- |
| A healthy | Mock discovery + real mock HTTP endpoint, runtime and endpoint distinguished; browser card | Real version/network/readiness |
| B failure | Consecutive thresholds, one incident, deployments/evidence/log redaction | Real deployment and provider logs |
| C approved recovery | Separate plan/approve/execute; exact POST and sustained readiness; browser review | Real disposable app interruption authorization |
| D recovery failure | Accepted operation but persistent HTTP 503 => needs_attention; consumed approval rejects replay | Actual release receipt/runtime behavior |
| E disconnection | API outage marks connection stale; cached app health not converted to app failure | Real network/TLS/token revocation |
| F existing Docker | Original unchanged native tests and real disposable Docker CI | Independent remote Docker-context acceptance |
| G security | Owner cookie, Host/Origin, unknown-app rejection; no tenant mode | Deployment security/isolation review |
| H existing features | Existing agency/CLI/browser/n8n/systemd CI | Customer workflows remain operator-owned |

## Exact future controlled Coolify test

These are **operator steps requiring authorization before infrastructure changes**, not operations performed by this PR.

1. Choose a new disposable or explicitly authorized nonproduction Coolify **v4.5.3** instance. Record its version, installation provenance, URL, TLS chain and team scope. Do not install on the existing EC2 or expose new public ports as part of this test.
2. Provision a disposable stateless test application and a dedicated team with no production resources. Record its exact application UUID and server association, immutable commit, expected readiness URL/status and tested recovery/rollback procedure. Record source/build/migration effects before enabling redeploy.
3. Install this PR's exact reviewed commit in a separate single-owner state directory. Create the private profile using OPERATIONS.md; begin with actions empty and no deploy binding. Load a read-only token privately. Verify valid TLS/DNS/SSRF policy; add only exact authorized private IP exceptions if necessary. Never disable TLS validation.
4. Run `$ ops-pilot check-fleet --fleet-config <private-profile>`; record redacted version, discovery/status, servers, five recent deployments and connection status. Verify the UUID and association against the instance. A single check does not satisfy all monitoring thresholds.
5. Start `$ ops-pilot fleet --fleet-config <private-profile> --state-dir <isolated-state>`. Use the fresh owner login through SSH forwarding. Confirm API connectivity, endpoint health and unknown states. Verify discovery does not auto-enroll resources or probe metadata-provided URLs.
6. On the disposable app only, inject a reversible HTTP 503 or stop it via your separately approved test procedure. Wait for the configured failure threshold. Verify one incident with timestamps/evidence; fetch bounded logs only with the separately granted read:sensitive permission. Validate redaction locally before sharing.
7. Confirm unauthorized/no-cookie reads, wrong Origin, source/bridge keys and unknown app IDs are rejected. Verify the browser has no API token. Test a wrong read token and revoked token: connection fails without incorrectly declaring all cached applications down. Restore read access.
8. Only after explicit authorization for this exact app/action, bind a different deploy token and enable `restart` in the profile, then restart Ops Pilot to reload. Propose; inspect exact instance/UUID/revision, health/deployment preconditions, impact and expiry. Confirm execution before approval is refused. Confirm an expired or superseded plan cannot execute.
9. Generate a fresh plan, approve it, then execute separately. Record the redacted queued deployment UUID, actual receipt deployment terminal status, runtime, consecutive readiness samples and incident history. Confirm a second execution with the same approval is refused. A request returning 200 is not recovery proof.
10. Repeat with the disposable app configured to remain HTTP 503 after restart. Verify needs_attention, no autonomous retry and five-minute cooldown. Restore via your previously authorized manual test procedure. Test redeploy only against the configured immutable commit, with separate approval; never against a moving branch/tag.
11. Configure a dedicated test Telegram bot/chat if authorized. Trigger each event, verify actual provider message IDs and received messages, then test invalid credentials and rate limiting. Mock confirmation is insufficient. Check maintenance suppression and notifications remaining free of app secrets/logs.
12. Run original Docker/studio smoke paths in the isolated installation. Measure memory/CPU and polling latency on the intended host, with application count/endpoints recorded. The prior 8 GB lab does not prove this fleet's concurrent capacity. Export every audit page using next_after until complete; preserve private evidence and record failures. Remove only explicitly owned test resources using your separately approved cleanup procedure. Revoke test tokens.

Ready for real testing means mock/CI assertions passed and documentation is accurate, not production readiness. Production rollout and any merge require the owner's separate decision.


## Observed local result and publication blocker

The final local suite attempted **115 tests: 86 passed, 25 socket-permission errors, four opt-in Docker skips, zero assertion failures**. The original baseline had 21 socket errors; the four additional errors are the new mock-HTTP acceptance tests blocked at server creation. All **32 new deterministic tests passed**. Python compileall, bash syntax, all five dashboard JavaScript syntax checks, CLI help exposing fleet commands, and an offline wheel build/package-content check passed. [Machine-readable local evidence](local-evidence.json).

New Playwright/browser, real local HTTP, Docker, Bandit/dependency vulnerability results and actual 8 GB fleet sizing are **not verified here**. Existing CI jobs are preserved and extended, not claimed as passing. GitHub read access confirmed the remote development branch still at the baseline after several write operations stalled and were interrupted without a result. No remote implementation commit or PR is confirmed. Local commits and a patch series preserve the work; publishing and CI must be completed before marking the PR ready. Main was not changed or merged. Real Coolify and Telegram require the separate controlled procedure above.
