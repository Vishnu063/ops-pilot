# Ecosystem component inventory and reuse decisions

Inspected all five repositories before implementation on 2026-10-24.

| Owner | Existing components reused | Integration boundary |
| --- | --- | --- |
| CloudLaunch | FastAPI Pharmacy app, `/health`, PostgreSQL, Dockerfile, Jenkins tests/deploy/rollback, database backup scripts | Emit versioned deployment facts; keep deployment execution here |
| DevOps Platform | Flask health/metrics, `devops_toolkit` Kubernetes collectors, report/topology evidence, Argo CD GitOps manifests, Helm chart, monitoring dashboards/rules, explicit recovery policies | Read-only release diagnostics, existing monitoring; forward alerts to Ops Pilot |
| Ops Pilot | Single-owner dashboard/session, Docker daemon/container identity binding, monitor, private SQLite runtime, maintenance, expiring plans, separate approve/apply, report download | Own authenticated ingestion, correlation and orchestration; never approve from webhooks |
| Triage Assistant | `ToolAdapter`, `ExperienceEngine`, `ToolEngine`, IncidentStore, rule catalog, bounded log signatures, Kubernetes events, health probes, optional Ollama | Own explanations, collection, approval persistence and verification reused by Pilot; no duplicated repair engine |
| Troubleshooting Labs | 100 evidence scenarios, 24 native faults, session/cleanup tooling, Prometheus metrics lab | Own disposable integrated failure acceptance runner and scenario instructions |

## Dependency direction

CloudLaunch deployment events and Platform Prometheus/Alertmanager → Ops Pilot → pinned Triage Assistant. Labs drives these interfaces. No reverse package dependency or broker. Shared wire contracts live in Ops Pilot; producers use its optional standard-library client. Each repository retains its standalone path. AI and Kubernetes remain optional.

## Gaps and constraints

Existing CloudLaunch Jenkins deployment targets a fixed host path and has an automatic rollback branch. Do not run it on customer infrastructure during this work. The separate ecosystem lab uses disposable project names and never invokes this legacy pipeline. Its rollback policy needs separate operational review before production integration. Platform is a release toolkit and small API, not an existing full Kubernetes dashboard; preserve honest disconnected behavior. Grafana is visualization, not log storage; reuse Triage bounded signature collection, no log backend invented.

Required checks: existing Python regressions, ingestion authentication/validation/deduplication/persistence, denied unapproved repair, expired/replayed approvals, disposable Docker outage and HTTP recovery, actual Prometheus alert firing/resolution. Optional integrations without available runtimes (Jenkins controller, Kubernetes/Argo/Helm, K8sGPT, Trivy) must be reported as unverified until exercised.

## Inspected revisions

- cloudlaunch: `2b788e8031747cb17b9b852e35b145a055914040`
- devops_platform: `d4ce8767366c7d728d72e3e7b805b0598177011e`
- ops-pilot: `66ef9f80a12db20f6d25f9f1bc4c2103c0e92f1d`
- devops-troubleshooting-labs: `7274875fc361317e5c9275b7a2fc9369099464c2`
- devops-triage-assistant: `e4b51f28bb3dcd8395ab5fbfe93d946f19156031`
