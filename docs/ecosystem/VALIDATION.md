# Observed ecosystem validation

Executed on 2026-10-24 in a disposable managed cloud machine. These are local development results, not production certification or screenshots.

| Check | Observed outcome |
| --- | --- |
| CloudLaunch pytest | 32 passed, plus 16 passing subtests. An initial combined run exposed fixture leakage, insecure test transport and a stale imported owner-password binding; those test-fixture defects were corrected without relaxing production authorization. |
| Platform unittest | 98 passed, including explicit offline/disconnected connection status. |
| Triage unittest | 247 total: 243 passed, 4 existing opt-in skips. New diagnosis/K8sGPT transport and bounded readiness tests passed. Live Kubernetes/K8sGPT skipped/unrun, not inferred. |
| Ops Pilot local HTTP/unittest | 28 total: 25 passed, 3 Docker opt-in skips in the ordinary suite. |
| Ops Pilot separate real Docker lab | All 3 passed: outage/recovery/replay, running-but-failed-HTTP recovery, stale-state approval rejection. |
| Labs unittest / catalog validation | 33 tests passed; 100 cases, 24 existing native scenarios + 3 existing compounds and Markdown links validated. New guard refuses failure injection without explicit disposable authorization. |
| Packaging | Clean Ops Pilot installation fetched the new Triage immutable GitHub archive; installed CLI/setup smoke passed from an unrelated temporary directory. Platform package/CLI installed. |
| Syntax | Python compile, shell scripts, extracted Jenkins shell blocks and dashboard JavaScript syntax passed. |
| Monitoring configuration | Actual promtool/amtool config validation passed before launching the monitoring services. |
| Disposable CloudLaunch/monitoring acceptance | Live PostgreSQL/app readiness, authenticated deployment receipt and duplicate suppression, real Prometheus firing alert, real Alertmanager delivery, Triage evidence/diagnosis, denied unapproved execution, explicit approval, one restart, HTTP/database readiness, refused replay and actual resolved webhook all passed. |
| Jenkins | Temporary authenticated loopback Jenkins 2.528.1 **freestyle** builds 1 and 2 both SUCCESS. Build 2 ran the final explicit-profile acceptance with Grafana. Declarative production/Jenkinsfile plugin behavior was not exercised. |
| Grafana | Grafana 12.2.0 provisioned all six panels; authenticated Prometheus datasource queries returned actual healthy CloudLaunch before failure and after recovery. This is API-level acceptance, not browser visual acceptance. |
| Wire contracts | Eleven actual exported records validated against the canonical JSON Schema with date-time format checks. Original incident timeline contained nine steps, alongside engine action history, receipts and owner audit. |
| Trivy gate | Exact app image scanned with Trivy 0.67.2: exit 1, 44 HIGH Debian findings, no CRITICAL findings in the selected severity set, no fixed versions listed. No findings suppressed. See CloudLaunch `integrations/validation/trivy-summary.json`. This image is not a clean security-gate result. |
| Browser acceptance | Unrun: Chromium download received explicit HTTP 403 Domain forbidden for cdn.playwright.dev. The domain addition was saved in the environment configuration draft; saving does not apply the policy. No synthetic screenshots or visual acceptance claimed. |

## Failure diagnosis and recovery evidence

An early monitor startup wait mishandled an initially empty Prometheus query result; the readiness loop now treats that as not ready. The first real approved CloudLaunch restart passed Docker identity/state but failed its initial short HTTP check window, and was truthfully recorded `needs_attention`. Bounded readiness polling was added to the reused Triage verifier, not a repair retry. Subsequent real runs and the separate wrong-endpoint test demonstrate both successful and unsuccessful application verification.

The full private incident report remains in the task workspace under `/workspace/ecosystem-final-run/incident-report.json`. Its state database and generated runtime configuration were not added to Git. The public [acceptance summary](evidence/acceptance.json) contains only disposable identifiers, versions, assertions and measurements; the lab removed its temporary ingestion token and all its app/database resources.

## Resources and limits

The final app sample used **62.25MiB / 192MiB** and **0.44% CPU**. App and PostgreSQL were each limited to 192 MiB / 0.5 CPU. The full final acceptance took 48.16 seconds. Individual monitoring-process peak RSS samples (not a simultaneous total) were 36576 kB, 74108 kB, 253432 kB. Jenkins used one executor with a 512 MiB JVM heap ceiling. These observations do not establish that the complete stack plus Kubernetes/AI fits in 8 GB. No model or Kubernetes cluster was started.

Kubernetes/Argo CD/Helm live status, live K8sGPT compatibility, resource/restart alert controlled triggers, browser visual acceptance, production rollback and production release are not verified. Existing native Labs scenarios and Platform diagnostics remain the documented path for Kubernetes failures; Pilot still coordinates one Docker application and one local owner, rather than a multi-tenant cluster control plane. The vulnerability gate remains failing until the underlying findings are resolved or an operator separately evaluates policy; no exceptions were invented.
