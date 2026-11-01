# Coolify v4.5.3 final quality review

Reviewed local implementation `6f646892d5b2c1c9811b9b72914abfb631f6ed13` on feature/coolify-integration. Remote branch/main were both `349aa13e4d3be33665bd8335636fc315e71b5ee2`; no open PR existed at inspection. No production infrastructure was accessed. No disposable Coolify URL/credential is configured in this environment. No real restart/redeploy is authorized or attempted by this review.

## Confirmed defects and focused corrections

| Defect | Correction / regression |
| --- | --- |
| A returned deployment UUID was checked, but the target argument was unused and another application's deployment in the same team could be accepted | Fetch exact UUID and compare its application_id with the numeric id of the exact target UUID. Missing/malformed IDs fail closed. Plans require the ID before any mutation. |
| A running application with explicit provider-health unhealthy and HTTP 200 could pass post-action verification | Explicit unhealthy overrides endpoint success; consecutive health checks remain mandatory. |
| Success/failure counters survived connection/evidence gaps | Reset both counters on unavailable evidence, preserving stale cached health without declaring app failure. |
| A poll started before another process's execution could overwrite evidence or resolve its incident afterward | Compare persisted execution generation again under BEGIN IMMEDIATE before committing collected evidence. |
| Supersession inspected only the 200 records shown by the UI | Inspect all retained plans transactionally; older pending approvals are superseded too. |
| A known receipt disappeared when subsequent verification timed out | Persist its filtered UUID receipt and audit entry before verification; unknown outcome keeps the receipt, and approval stays consumed. |
| Standard test matrix had no job timeout and checkout retained a repository credential unnecessarily | Bound matrix jobs to 15 minutes and disable persisted checkout credentials throughout the standard workflow. No test is disabled. |

Seven targeted regressions were run against the previous committed implementation in an isolated temporary package: six assertion failures and one missing-receipt-field error reproduced the defects. The updated deterministic suite passes, including additional nonconsecutive-readiness and missing-ID checks. Other public behavior/routes/config formats are retained; old plans whose identity projection differs must be regenerated rather than silently trusted.

## Official v4.5.3 evidence

Upstream source pinned to [70c1bcb1381de7d42fd290e6cd50bf9a5bcf714d](https://github.com/coollabsio/coolify/tree/70c1bcb1381de7d42fd290e6cd50bf9a5bcf714d), tag v4.5.3. Read on 2026-10-30 through the official GitHub repository:

- [ApplicationsController](https://github.com/coollabsio/coolify/blob/v4.5.3/app/Http/Controllers/Api/ApplicationsController.php): restart queues restart_only and returns deployment_uuid. A skipped operation can return only a message; it is not accepted as a valid receipt. No mutation retries.
- [DeployController](https://github.com/coollabsio/coolify/blob/v4.5.3/app/Http/Controllers/Api/DeployController.php): deployment_by_uuid enforces token team membership, not the caller's application target. Therefore Ops Pilot must enforce application binding too.
- [ApplicationDeploymentQueue](https://github.com/coollabsio/coolify/blob/v4.5.3/app/Models/ApplicationDeploymentQueue.php): application_id is serialized as a string; hidden fields are logs/configuration snapshots/diffs. Numeric strings and positive JSON integer IDs are accepted, booleans are refused.
- [API serializer](https://github.com/coollabsio/coolify/blob/v4.5.3/bootstrap/helpers/api.php): explicitly retains non-null id. [Application model](https://github.com/coollabsio/coolify/blob/v4.5.3/app/Models/Application.php) scopes deployment history by application_id and supports newest ordering.

This is source-contract validation, not installed-instance validation. Assumptions still needing real proof: reverse-proxy/base-URL behavior, actual token abilities/team policies, serialization on the installed build, receipt/runtime progression, server associations, TLS/network reachability and readiness meaning. The documented [controlled test procedure](ACCEPTANCE.md#exact-future-controlled-coolify-test) requires authorized disposable infrastructure. First test only read-only discovery/authentication/timeouts/malformed data. Ask for separate explicit authorization for exactly one application and action before any real recovery. Record actual redacted responses and timestamps then; none are invented here.

## Broader audit and remaining risks

CI workflows retain contents:read, no pull_request_target, disposable lab boundaries and existing Docker/Kubernetes/Jenkins/resource regression jobs. The privileged nested Docker daemon is CI-only; it must not become a production web privilege. Docker native approval/daemon/container/endpoint checks remain unchanged. Kubernetes, AWS and monitoring collectors remain scoped read-only; no external account/cluster was contacted. Exact native dependency pin is preserved. No confirmed additional defect in those paths was established by this review; that is not vulnerability clearance.

Owner session/Host/Origin checks still gate fleet routes; source/read credentials do not authorize actions. TLS validation, DNS/IP pinning, metadata denial, bounded response/log data, redaction, explicit action allowlists and consumed-before-I/O approvals remain. Public/multi-tenant mode stays disabled. Root/owner can alter local SQLite; a hash chain is not protection from a compromised owner. Coolify does not provide atomic compare-and-swap between preflight and POST; stop competing controllers during recovery. Environment credentials are not a vault. Redaction cannot guarantee discovery of arbitrary unknown secrets. Floating-source redeploy and generic rollback remain unsupported.

Local Bandit/pip-audit are unavailable, and the proxy cannot be reached for installation. No CVE clearance or successful source-scanner run is claimed. Existing CI scanner remains enabled. Browser and HTTP tests hit the sandbox's socket PermissionError; they are not skipped or weakened. Real-instance, browser, CI, Docker/cluster integration and measured full-fleet capacity remain release gates. Read the machine-readable quality evidence for observed commands/results and distinguish this review from historical main CI.

## Observed local validation

Final suite: **124 attempted, 95 passed, 25 socket-permission errors, four opt-in Docker skips; zero assertion failures**. All **41 deterministic Coolify tests passed**. The baseline had the same 25 blocked tests. Python/shell/all-five-JavaScript syntax, workflow structure/permissions, immutable native dependency and diff checks passed. The new browser test was attempted and blocked at mock HTTP server creation. Bandit was unavailable and offline installation had no distribution; no scanner success is claimed. [Machine-readable evidence](quality-evidence.json). New published-head CI and real-instance validation remain pending; historical main checks are not evidence for this code.

Publication check: the GitHub tree write returned no result within a 15-second bound; no branch update was attempted. A subsequent read confirmed feature/coolify-integration remains at `349aa13e4d3be33665bd8335636fc315e71b5ee2` with no open PR. Its eight historical checks are green, but no new-head CI exists for these fixes. All five browser scripts were attempted and each exited 1 on the same socket PermissionError. No test was disabled. Fixes are preserved as local commits and applicable patches; publication, PR creation and new-head CI remain blocked.
