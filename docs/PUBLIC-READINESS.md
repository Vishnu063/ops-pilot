# Self-hosted readiness review — 2026-10-25

This follows the merged five-project work. Ops Pilot PR #5 is merged into main (`3a634efd6bed00fc721db84f916d9c613d6d32bb`); it was neither reopened nor duplicated. New PR #6 contains only follow-on diagnostics, setup, hardening and acceptance work. No main branch or customer infrastructure was mutated by this review.

## Branch and dependency review

| Repository | PR | Review finding |
| --- | --- | --- |
| cloudlaunch | #4 | Based on current main; adapter CI green at inspected head. Pharmacy application/DB and existing pipeline preserved. Actual pharmacy deployment remains outside this lab. |
| devops_platform | #13 | Originally stacked on unmerged LiveFlow #12 and 20 commits behind main. A normal two-parent merge brings main into the feature branch, preserving its pipeline/security/monitoring changes; #13 now targets main and includes the required LiveFlow implementation. #12 remains open and overlapping; do not merge it blindly after #13. No force push or unrelated PR merge. |
| ops-pilot | #6 | New branch starts from merged main; original engine, agency and owner sessions remain. #5 stays closed/merged. |
| devops-troubleshooting-labs | #1 | Existing Docker/Kind fault tooling preserved; adds explicitly owned extended acceptance. |
| devops-triage-assistant | #5 | Existing pinned native collectors/contracts reused. Latest inspected build/browser/docs runs passed; an older failed run is retained, not relabeled. |

The Platform merge changed only files changed by main since the common ancestor; none overlapped the feature additions. This preserves ancestry rather than copying a main snapshot over unrelated work. Follow-on source checks test authenticated transport bounds and monitor expressions.

## Features and limits

The new optional read-only desk exposes native Kubernetes, numbered Jenkins failed-build/log-signature analysis, one EC2 instance's reachability diagnostics, Helm status/history/rollback guidance, ArgoCD health/drift, Prometheus/Grafana health and bounded Trivy report import. Kubernetes crash/image/OOM/scheduling/rollout logic is reused from Triage. A private setup wizard and guide, report isolation by environment ID, no arbitrary shell input, single-flight collection, eight HTTP workers and bounded bodies/timeouts improve self-hosted operation. Environment IDs do not constitute verified hostile multi-tenancy; separate OS users/processes/credentials are required. Multi-user/public binding remain disabled.

Only the existing exact-target Docker engine can repair through Ops Pilot's UI. Owner approval/apply remain separate, expire, bind exact target/state/policy and refuse replay. Reports distinguish observations, uncertainty and limitations. No model or web request can invent/approve a mutation. Helm rollback analysis is advice, not an executable rollback. CloudLaunch retains its own health-checked pipeline rollback. K8sGPT is opt-in installed deterministic analysis; provider inference/model installation was not enabled.

## Acceptance evidence

The new `Public self-hosted readiness` workflow encloses the nested Docker daemon and all tested descendants in an actual 8 GB cgroup (`memory.max=8000000000`, swap ceiling equal to memory), with two CPUs. It publishes cgroup peak/events and actual result artifacts. It mounts the owned disposable runner checkout, never the host Docker socket, and publishes no nested daemon or Jenkins port. The privileged nested daemon is lab-only and is removed after the run; it is not the install architecture.

The five-project scenario runs first (real sample, failed HTTP, actual Prometheus/Alertmanager, refused preapproval, approved exact restart, HTTP/metrics/resolution verification, report, read-only Platform and cleanup). Jenkins then exercises an authenticated failing scripted pipeline and numbered log evidence. Kind then injects crash-loop, missing image, memory-limit OOM, unschedulable request and failed rollout into uniquely owned workloads. Service phases are sequential inside one enclosing budget; this is not a concurrent production stack capacity measurement. Kubernetes intentionally kills a workload at its own 16 MiB limit; distinguish that from exhausting the enclosing budget.

Measured results and exact CI links are appended after execution. Until that evidence is present, a prepared workflow is not a successful runtime test. Local unit/installation/syntax checks run where possible; local socket-dependent tests fail under this execution sandbox and are checked in real CI without weakening assertions.

## Remaining acceptance gates

* Live EC2/account metrics and actual external ArgoCD/Helm/K8sGPT services: no credentials, accounts or customer authorization were supplied. Synthetic/native-profile tests do not prove access or production health.
* Trivy ingestion is tested, but no current image vulnerability clearance or scanner attestation is claimed. CloudLaunch Jenkins/Trivy/pharmacy deployment is distinct from the owned failing Jenkins lab job.
* Grafana dashboards/exporters and alert rules are configuration, with rule-engine tests; wider real resource/restart/error-rate behavior needs explicitly configured exporters and policy acceptance. No log backend is created.
* Internet-facing auth, hostile tenant isolation, multi-user permissions and public exposure are not accepted; these switches are absent/disabled. Installation through SSH/local owner sessions is the supported boundary.
* Full concurrent production capacity, long-term load, filesystem/encrypted backup policy, customer SLOs and human approval latency require deployment-specific evidence.

No remaining PR is automatically merged. Merge recommendations and draft readiness depend on the actual latest code checks and these stated scopes.
