# Reliability completion and deployment scope

This review continues PR #6 on top of main `3a634efd6bed00fc721db84f916d9c613d6d32bb`. It preserves the existing native Docker engine, agency workflows, read-only collectors and exact source pins. No other repository PR is merged by this task. The merge is conditional on every current reported check passing and the exact reviewed head remaining unchanged; branch-protection settings are not readable through this GitHub connection, and server-enforced protections are never bypassed.

## Fixed recovery boundaries

* Alertmanager state is monotonic by fingerprint/timestamp. New firing clears resolution, old retries cannot resolve a newer cycle, tied timestamps fail closed, and non-Alertmanager producers cannot satisfy monitoring resolution. Legacy resolution booleans without current alert state are insufficient.
* A new firing received while health/metrics are being checked prevents terminal closure. Prometheus responses must be successful vectors with recent, nonfuture samples.
* Post-repair verification checks the planned immutable container ID and observed daemon against investigation evidence. A healthy replacement under the same name does not complete the prior repair.
* Unavailable/incompatible optional K8sGPT output remains explicitly inconclusive while valid native evidence is retained. Malformed provider responses do not become healthy reports. Private diagnostics configuration must be a regular file, not a pipe/device/symlink.
* The UI includes original trigger/metric evidence and optional-analysis status. Running containers with resource-only alerts are not offered an unsupported restart. Audit downloads follow cursor pages and record `complete` and `next_after`; a 400-page export bound is explicit. This archive contains filtered incident audit pages, not a transactionally frozen full database backup or protection against a compromised local owner.

## Requested failure coverage

| Scenario | Actual verification and boundary |
| --- | --- |
| Application down | Existing real sample → failed HTTP → native evidence → authenticated alert → exact plan → refusal before approval → approved restart → HTTP/metrics/resolution → report/cleanup. |
| Container crash | Owned Docker fixtures receive SIGKILL. Exit 137 is checked separately from `OOMKilled`; the signal alone is not called OOM. |
| CrashLoopBackOff | Owned Kind repeated-exit/backoff scenario and native explicit-waiting/recent-exit regressions; old/single failures are not classified as a current loop. |
| ImagePullBackOff | Owned Kind missing-image scenario; native ErrImagePull/ImagePullBackOff evidence is projected without raw event bodies. |
| High CPU | Actual fixed cgroup CPU load in a 0.5-CPU/128-MiB container → Prometheus expression → authenticated Alertmanager → incident/metric evidence/report. |
| High memory | Actual bounded allocation in that fixture; test threshold 70%, example policy 90%, avoiding host memory exhaustion. The separate Kind OOM case has its own 16-MiB workload cap. |
| Disk exhaustion | Actual ENOSPC on an owned 8-MiB tmpfs; host root/customer storage is never filled. |
| Failed deployment | Existing authenticated Jenkins failed pipeline and a deliberately bad stateless application configuration; actual pharmacy/DB deployment is outside this lab. |
| Unhealthy endpoint | Native Docker state can verify while HTTP remains 503; overall recovery must remain `needs_attention`. |
| Failed recovery/rollback | Restart needs separate approval, unsuccessful HTTP prevents recovery, consumed approval cannot replay. An explicitly scoped manual owned replacement restores the previously verified fixture configuration and passes consecutive HTTP checks. This validates a manual procedure; it does not add an automatic/generic production Docker replacement executor. |

The CI-only resource exporter projects real cgroup CPU/memory and tmpfs measurements into node-style series. It is not a production node exporter. CPU is normalized to the fixture's explicit quota. The production example expects properly scoped existing exporter series, service labels and an explicitly selected filesystem. Review thresholds/durations for the target; do not copy a ten-second demonstration policy blindly. No alert authorizes a repair, deletes files or kills processes. Resource warnings on an otherwise running app may have no safe executable repair; collecting evidence and escalating is the correct outcome.

## Verified integrations and acceptance artifacts

The existing constrained workflow checks all five source repositories and runs a real private nested daemon under `memory.max=8000000000`, with two CPUs and no host Docker socket mount. Jenkins, Kind, resource/Grafana and rollback phases run sequentially. It exports cgroup peak, hierarchical and local memory counters, cleanup and result JSON. The intentional child OOM may set Docker's hierarchical OOM flag while the controller remains running; enclosing local `max`/`oom`/`oom_kill` counters must remain zero.

The resource extension tests authenticated Grafana health, imports the existing Platform dashboard, verifies its Prometheus datasource and reads metric data through Grafana's authenticated proxy. It does not claim every dashboard panel has a production exporter. Some panels need separately configured deployment/application/incident series.

Raw genuine result data and exact source/run references are stored in [reliability evidence](evidence/reliability.json). Earlier verified evidence remains in [public-readiness.json](evidence/public-readiness.json). Follow the exact commit in each record; later documentation-only commits do not change a historical test's source. The final report lists the final commit/check outcomes.

## Security and checks

The standard suite covers native plan expiry, stale target/state, replay, owner/source/read credentials, session/Origin/Host, no arbitrary shell input, persistence, desktop/mobile browser behavior, real Docker and systemd/n8n. New regressions cover stale alert resolution, verification races, identity replacement, malformed services, regular-file configuration and optional-analyzer failure. Source security CI runs Bandit 1.8.6 against production Python with medium-or-higher severity/confidence as the failure threshold, and checks the immutable native-engine source pin. This is a scoped source check, not image vulnerability clearance or a comprehensive penetration test.

Local TCP/Unix sockets are denied by this execution sandbox. A local full-suite attempt therefore produced socket PermissionErrors; focused non-socket tests and syntax run locally, and actual HTTP/browser/Docker checks run in disposable CI without weakening their assertions.

## Genuine deployment readiness

Supported: an engineer-controlled, single-owner Linux deployment, loopback/SSH access, private state/credentials, one exact Docker target with approved restart and required endpoint checks, optional scoped read-only diagnosis, and explicitly configured monitoring. Keep models and optional heavyweight services off a modest host unless independently sized.

Not accepted: public Internet/multi-user/hostile-tenant isolation, arbitrary recovery, generic Docker replacement/volume/schema rollback, Kubernetes write operations, long-term load/SLOs or full concurrent production sizing. Use the existing deployment controller for deployment rollback and review migrations/data impacts separately. Real customer/production changes still need explicit scoped approval.

External AWS/account diagnostics, live ArgoCD/Helm, actual configured K8sGPT/provider/model use, production exporters and actual pharmacy/Trivy runtime need their own credentials/infrastructure and acceptance. No configured K8sGPT binary/provider was available for genuine runtime proof; disabled/unavailable/malformed behavior is tested without claiming an installed integration. Existing root-license gaps and n8n/model/provider terms still require owner distribution review before a public bundled release. No purchase, paid API or model download is introduced.
