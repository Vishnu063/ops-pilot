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

Observed results, exact CI links and scope are recorded below; prepared scenarios are never counted as successful runtime tests.

## Remaining acceptance gates

* Live EC2/account metrics and actual external ArgoCD/Helm/K8sGPT services: no credentials, accounts or customer authorization were supplied. Synthetic/native-profile tests do not prove access or production health.
* Trivy ingestion is tested, but no current image vulnerability clearance or scanner attestation is claimed. CloudLaunch Jenkins/Trivy/pharmacy deployment is distinct from the owned failing Jenkins lab job.
* Grafana dashboards/exporters and alert rules are configuration, with rule-engine tests; wider real resource/restart/error-rate behavior needs explicitly configured exporters and policy acceptance. No log backend is created.
* Internet-facing auth, hostile tenant isolation, multi-user permissions and public exposure are not accepted; these switches are absent/disabled. Installation through SSH/local owner sessions is the supported boundary.
* Full concurrent production capacity, long-term load, filesystem/encrypted backup policy, customer SLOs and human approval latency require deployment-specific evidence.
* Public redistribution still needs an owner license/attribution decision for Triage and Platform (no root license detected in the existing inventory). n8n retains its upstream Sustainable Use terms; model/provider rights remain separate. See [license screening](REPOSITORY-DECISIONS.md). This review does not assign a new license to those repositories.

No remaining PR is automatically merged. Merge recommendations and draft readiness depend on the actual latest code checks and these stated scopes.

## Verified implementation and measured run

Implementation `7e48a1619d0cb8d9908380a95c4e15ff116d75b1` passed all ten jobs: [seven standard jobs](https://github.com/Vishnu063/ops-pilot/actions/runs/40204417747), [two ecosystem jobs](https://github.com/Vishnu063/ops-pilot/actions/runs/40204417758), and [the constrained failure job](https://github.com/Vishnu063/ops-pilot/actions/runs/40204417788). [Machine-readable genuine results](evidence/public-readiness.json) preserve stage timings, source refs, cleanup and counters. The Python 3.11/3.12/3.13 matrix each ran 71 cases with four opt-in Docker skips; the separate real Docker job exercised those paths. Installed setup, actual owner HTTP authorization, four automated browser journeys, systemd and n8n passed. Browser collectors are synthetic and screenshots were not manually reviewed; service labs are separate real-runtime evidence.

The constrained run accepted CloudLaunch's actual Jenkinsfile through Jenkins' declarative linter, investigated an actual authenticated failing scripted pipeline, and detected five real owned Kind faults: repeated crash/backoff, missing image, OOMKilled, unschedulable Pending and failed rollout. The Docker path refused unapproved/replayed repair and source-role escalation, required actual HTTP/Prometheus/Alertmanager recovery, exported its report and verified Platform's read-only view. Both phases verified cleanup. Recovery took **19.739 seconds** with programmatic test-owner actions; the first phase took **46.115 seconds before cleanup**. The extended phase took **136.623 seconds including its cleanup**. These are disposable synthetic timings, not real human approval latency or customer MTTR.

Peak enclosing cgroup memory was **4,151,042,048 bytes (4.15 GB; about 3.87 GiB)** under the enforced **8,000,000,000-byte** ceiling and two-CPU limit. Enclosing `memory.events.local` `max`, `oom`, `oom_kill` and `oom_group_kill` were all zero before and after. Docker's parent `OOMKilled` flag was true while `Running=true` and `ExitCode=0`; hierarchical counters included the intentionally OOM-killed child workload. The local counters distinguish that injected workload fault from exhausting the enclosing budget. Image/layer caches are included in the cgroup peak. Service phases were sequential; Grafana, models/providers and the broader external services were excluded. This is not a full concurrent production capacity guarantee.

Earlier failed checks remain recorded: exact owned Git checkout trust in the nested runner; mobile navigation overflow; a JSON-only HTTP test helper; Kubernetes evidence missed between waiting states; a browser helper incompatible with CSP; and Jenkins multipart validation format. The source/harness fixes retained authentication, CSP, freshness and approval assertions. A local full-suite attempt hit sandbox socket PermissionErrors; CI ran the actual socket-dependent checks successfully.

## Final merge review

| PR | Review scope / merge recommendation |
| --- | --- |
| [CloudLaunch #4](https://github.com/Vishnu063/cloudlaunch/pull/4) | Ready for the optional adapter/sample scope: source tests, actual sample/recovery and Jenkins declarative lint passed. Actual pharmacy/DB/Trivy deployment remains a separate authorized runtime gate. |
| [Platform #13](https://github.com/Vishnu063/devops_platform/pull/13) | Ready for read-only LiveFlow/integration/configuration. Targets main with zero commits behind at review; includes required #12 LiveFlow. Source/security/concurrency, toolkit/docs and promtool synthetic-series tests passed. Review #12 overlap before subsequently merging it. |
| [Triage #5](https://github.com/Vishnu063/devops-triage-assistant/pull/5) | Ready for shared contracts/native evidence. Build/matrix/real Docker, browser/docs and consuming constrained Kind evidence passed. No external account/provider acceptance claim. |
| [Labs #1](https://github.com/Vishnu063/devops-troubleshooting-labs/pull/1) | Ready for explicitly owned practice/acceptance workflows after latest original repository/Docker/Kind checks; the actual expanded acceptance passed under the strict budget. No customer fault injection. |
| [Ops Pilot #6](https://github.com/Vishnu063/ops-pilot/pull/6) | Ready for optional single-owner self-hosted diagnostics/setup/hardening; all ten implementation jobs passed. Internet exposure, multi-user and broader external write operations remain disabled/unaccepted. |

Merge the shared Triage change and producer/viewer/lab PRs before the consuming Ops Pilot follow-on when practical. Immutable source pins keep integration deterministic meanwhile. PR #5 in Ops Pilot remains merged; #6 is new follow-on work. No PR was automatically merged and no branch was force-pushed. Current PR heads may add documentation-only commits beyond the tested implementation above.
