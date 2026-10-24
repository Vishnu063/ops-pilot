# Five-project reuse audit

Inspected 2026-10-24. This inventory precedes integration changes. Source revisions:

```json
{
  "cloudlaunch": {
    "sha": "2b788e8031747cb17b9b852e35b145a055914040",
    "tree": "95a124e8e0a1cdbe6fce1d7f917e13db75c5414b",
    "ref": "main"
  },
  "devops_platform": {
    "sha": "94c4d7c699f643972b9911694dabb4c2aea7c0f8",
    "tree": "22f6c94e9fd054dad67a7dc068c34ee74f1bd3cd",
    "ref": "feature/liveflow-readonly-topology-20261023"
  },
  "ops-pilot": {
    "sha": "48b73ead296c72597a215765ef92743742b5564a",
    "tree": "0f1289519f9c230c59e6b18afde4424bfe65032e",
    "ref": "feat/freelance-agency-studio"
  },
  "devops-troubleshooting-labs": {
    "sha": "7274875fc361317e5c9275b7a2fc9369099464c2",
    "tree": "0f402c90e59b9855c23bebd6a46fa03a9d169ca7",
    "ref": "main"
  },
  "devops-triage-assistant": {
    "sha": "e4b51f28bb3dcd8395ab5fbfe93d946f19156031",
    "tree": "4dda5b08ddc29a5ce812a05eceb59ab50eff6b94",
    "ref": "main"
  }
}
```

| Capability | Owner and existing component | Integration decision |
| --- | --- | --- |
| Application builds/releases | CloudLaunch Jenkinsfile, Dockerfile, Compose, existing DB-aware /health | Preserve pharmacy deployment and rollback. Add optional structured release reporting and a separate stateless disposable demo. |
| Cluster/GitOps visualization | Platform LiveFlow feature, Helm/Argo manifests, read-only diagnostics toolkit | Continue from existing LiveFlow branch. Keep disconnected mode; add optional evidence sources and read-only incident visibility. |
| Metrics/alerts | Platform bounded Prometheus/Grafana stack, alert rules and application /metrics; CloudLaunch host exporters | Reuse configuration concepts. Add opt-in Alertmanager routing, correlated service labels, rules and dashboard. No second log store; log backend remains optional. |
| Diagnosis and evidence | Triage ToolAdapter, Kubernetes/deep collectors, deterministic catalog, health probes | Add a versioned structured diagnostic/verification/event client interface to this existing package; preserve native collectors. |
| Approval and execution | Ops Pilot Pilot + pinned ExperienceEngine/ToolEngine | Preserve target identity, exact command, expiry, separate approval/apply, consume-before-dispatch and health verification. Integration webhooks never authorize repairs. |
| Incident history | Triage IncidentStore, Ops Pilot SQLite/agency audit | Add bounded source/correlation/dedup event ledger and links to existing plans. Do not replace original incident history. |
| Controlled failures | Labs native Docker/Kind runners, evidence catalog, cleanup and session grading | Add ecosystem scenario catalog and end-to-end driver; reuse owned disposable resources. Never inject into customer infrastructure. |
| Authentication | CloudLaunch session/RBAC; Ops Pilot loopback owner session and origin validation; Platform read-only loopback | Keep existing controls. Source-scoped bearer tokens for webhooks; read-only integration credentials cannot approve. |
| Rollback | Existing CloudLaunch rollback and Triage scoped Kubernetes rollback | Report outcomes, never add automatic rollback authorization. Existing CloudLaunch behavior is preserved and documented. |

Dependency direction: producers and read-only views use optional Triage integration helpers; Ops Pilot consumes the same versioned package. No dependency points back from Triage into Ops Pilot. Ops Pilot owns approval semantics. Canonical wire contracts ship with the reusable package and are documented by Ops Pilot. All five projects remain usable without the new integrations.

No root AGENTS.md was present in the other four audited trees; Ops Pilot's working agreement was read. CloudLaunch and Platform have unrelated open PRs; these are not merged or overwritten. Ops Pilot integration branches from the agency continuation and Platform branches from LiveFlow, with their existing ancestry preserved.
