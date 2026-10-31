# Release review — PR #7

The preserved local snapshot `32e8ae8364e431f8ad7e994d72a35f35fc91e324` was published on real GitHub ancestry as `d6853cf9c1d773205a5aa9a5121b973b1d6bb8ed` in [draft PR #7](https://github.com/Vishnu063/ops-pilot/pull/7). Its four original workflows and 11 jobs passed. Historical local socket/scanner blockers in the older evidence files describe that environment, not those successful CI runs. Always inspect [checks for the current PR head](https://github.com/Vishnu063/ops-pilot/pull/7/checks); previous-head green checks do not validate follow-up commits.

## Dependency and source security coverage

The Security boundaries workflow now audits a freshly installed runtime in its own virtual environment. Every installed indexed distribution, including bootstrap tooling, is pinned in the generated inventory and submitted to strict pip-audit without vulnerability suppressions. Missing packages, duplicate normalized names, malformed inventory and unexpected first-party provenance fail the job. Scanner/build-isolation tooling is outside that installed runtime inventory.

The two first-party packages are explicitly recorded separately. Ops Pilot's installed version/dependency must match the reviewed project; the native engine's installed provenance must match the immutable GitHub archive pin. Their absence from public CVE lookup is not a security clearance. The configured Bandit scan covers both Ops Pilot and the pinned native engine; it is a source-analysis check, not an independent comprehensive security review. Artifacts include the exact inventory and vulnerability results. A passing job means only that its recorded scope completed successfully at that time.

## Outstanding release gates

The owner confirmed that no authorized disposable Coolify v4.5.3 instance is available. Therefore real API/token/TLS/application/discovery compatibility remains **NOT VERIFIED**, and live recovery is not authorized. Do not provision on existing infrastructure, use production credentials, or claim that mocked tests establish live compatibility. Follow `coolify/ACCEPTANCE.md` when an authorized disposable instance and privately configured credentials become available. Any recovery still requires separate authorization naming the exact application UUID and action.

Real AWS/EKS/configured-provider validation, independent human/security review and concurrent production sizing are also unverified. Existing constrained CI acceptance is isolated and sequential. Keep one owner, loopback binding, exact scopes, private state and separate approval/execution. Public/shared-customer deployment is not supported by this review.

## Installation, backup and rollback

Use the existing README native installation and `core/RUNBOOK.md`. That runbook contains private configuration, read-only IAM/RBAC scope, state permissions and acceptance commands. It also documents offline whole-state backup and why historical fleet/native approvals must not be restored into active operation. Generic infrastructure rollback and safe restoration of outstanding approvals are not implemented. Compose packaging is not certified by this change.

Status: **HOLD** for production release. Repository CI work can be completed independently; live Coolify validation requires access that is currently unavailable. No automatic merge or deployment is authorized.
