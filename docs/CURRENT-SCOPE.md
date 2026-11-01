# Supported scope and remaining validation

This inventory was reviewed against PR #7 at
`ad05d403c9f080d65aa6bc5dc65bbeee86515b67` and its focused file/backup-hardening
follow-up. It supersedes status claims in historical continuation notes; those
older evidence files remain records of their original runs. Check the current PR
head's CI, not a prior commit. Implementation is distinct from live acceptance.

| Area | Implementation status | Evidence and boundary |
| --- | --- | --- |
| Startup/configuration | Complete for supported Linux single-owner CLI/foreground operation | Setup/check/serve, private config and bounded file reads; no default production target. Service lab tests start/crash; full host reboot remains unverified. |
| Dashboard/API | Complete within local owner scope | Five browser runners exercise real HTTP/SQLite and desktop/mobile viewports; provider mocks where labelled. Host/Origin/cookie and payload bounds; no public user accounts. |
| Controller health/readiness | Partial | Authenticated state/freshness and CLI diagnostics exist; no separate public healthz/readyz endpoint or business-transaction certification. |
| Docker | Complete for exact configured container monitoring and approved restart | Immutable container/daemon identity, expiry, single-use approval, no arbitrary command endpoint; real disposable failure/negative recovery acceptance. No daemon restart/cleanup or generic rollback. |
| CPU/memory/disk | Partial | Optional pinned single-sample Docker stats, EC2 fixed metrics and trustworthy monitoring evidence. No general host/disk agent or comprehensive capacity predictor. |
| Kubernetes/EKS | Partial | Exact context/namespace/workload, crash/image/OOM/pending/rollout/event/log diagnostics; Kind faults tested. Configured EKS and broad cluster resource metrics remain unverified/unsupported respectively. No writes. |
| Helm/ArgoCD | Implemented read-only; external acceptance deferred | Scoped native status/history/sync evidence; no upgrade/sync/prune/rollback. Credentials may themselves be sensitive/privileged. |
| Jenkins/GitHub Actions | Partial | Exact job/run/workflow, bounded history/stages/jobs/log signature counts. Isolated Jenkins CI plus deterministic GitHub contracts; no broad discovery or pipeline mutations. Plugin/API and customer connections need acceptance. |
| AWS/CloudWatch | Implemented selected read-only diagnostics; live deferred | Exact EC2/account/region, fixed metrics/alarms/log stream and optional ALB/ASG. IAM/missing-data errors fail inconclusively. No write calls or complete network root-cause diagnosis. |
| Prometheus/Grafana | Partial | Authenticated/deduplicated events, fresh scoped probes and read-only health evidence; isolated monitoring/Grafana labs. No general Grafana dashboard management or guaranteed cross-domain causal correlation. |
| Incidents/reports/storage | Complete within bounded stores | SQLite persistence, projected/redacted reports, audit records, restart-safe plans and history. Trusted UID/root can alter files; no tamper-proof remote audit. No general versioned migration/downgrade framework. |
| Backup/restore | Complete for agency-only snapshot; partial whole platform | Agency snapshots verify hash/integrity, clear restored approvals and reject unsafe paths. Offline whole-state archive procedures exist; native/fleet approval restoration into active operation is unsupported. |
| Coolify v4.5.3 | Disabled by default; live validation deferred | Preserved API/receipt/approval/sustained-health contracts are mocked. Disabled unit/browser tests require zero provider/recovery/external requests. No disposable live instance; no real recovery authorized. |
| Notifications | Partial | Local history, optional webhook/Telegram with bounded calls and delivery state; deterministic provider failures. Real external delivery unverified. |
| Freelance/n8n | Complete for existing bounded assistance scope | Nine local roles, explicit decisions, starter-file package and isolated n8n acceptance. No customer deployment, payment processing or autonomous agency claim. |
| Authentication/authorization | Complete only for documented trusted-owner boundary | Random rotating local owner capability, separate bridge/source/read roles, allowlisted repairs. Public exposure, multi-user RBAC and tenant isolation are unsupported. |
| Security/CI | Implemented checks; not independent certification | Python matrix, browser/Docker/service/resource labs, app/native Bandit and strict installed-runtime audit. Action tags/build tooling and first-party CVE coverage limits are documented. |

## Focused defects corrected in the follow-up

- Backup verification interpolated an unescaped path into a SQLite URI. A real
  path containing `?`/`#` reproduced verification against the wrong database.
  Percent-escaped read-only URIs now select the exact file.
- Backup manifest links/special files and symlinked source/destination components
  were not consistently refused. No-follow regular/owner/single-link checks and
  bounded manifests now precede reading. Database hashes stream in 64 KiB chunks;
  connections close explicitly and snapshot/restore files start with mode 0600.
- The original Docker config loader followed links and could block on a FIFO;
  reads now require a bounded private owner regular file with no symlink components.
  Atomic saves refuse unsafe existing files/paths. Same UID/root remain trusted.
- The optional event ledger bypassed shared private-file validation and left SQLite connections open. It now reuses owner-only no-follow storage, closes connections and validates the operation lock before locking. Five regressions preserve audit state and reject linked paths without modifying victims.
- Installation notes still referenced PR #6 and mixed historical local blockers
  with current published CI. Current scope and the owner runbook now explain the
  distinction without rewriting historical test evidence.

Eighteen focused regressions cover real SQLite backup/restore and configuration
files without infrastructure access. Full CI must pass on the published follow-up.

## Separate release verdicts

The owner handles deployment. No production deployment, provisioning, integration
enablement or real recovery is part of this review. Coolify stays disabled and live
compatibility UNVERIFIED. Production verification is absent.

Development can be complete for this bounded scope after current-head tests and
security checks pass; missing broader capabilities above are not advertised.
Merge remains blocked while external deployment automation cannot be independently
ruled out: owner reports no connection, but connector administration reads are
unavailable. See the PR validation report for current counts and exact SHA.
Deployment prerequisites are documented in [OWNER-RUNBOOK.md](OWNER-RUNBOOK.md);
host access, credentials and actual operational acceptance are owner responsibilities.
