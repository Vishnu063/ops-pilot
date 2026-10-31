# Future service packaging and onboarding

These are proposed service boundaries, not paid products already delivered. No billing gateway, subscription, customer signup, outbound sales message or payment is implemented.

| Package | Proposed scope | Release prerequisites |
| --- | --- | --- |
| Starter | Basic explicitly configured monitoring, incident alerts, health dashboard | Customer-owned installation, verified alert delivery, endpoint/SLO agreement |
| Professional | Optional Coolify discovery/deployment diagnostics and separately approved recovery | Supported real-instance acceptance, explicit permissions, tested runbook |
| Managed Operations | Several applications, periodic incident reports and operational reviews | Per-client isolated installation, access/retention agreements, defined support hours and escalation |

Onboarding: inventory authorized apps/servers and owners; record exact UUID/context, health meaning, acceptable disruption, maintenance windows, notification destination and escalation contacts. Use least-privilege tokens delivered through a private secret channel; agree how they are revoked. Start read-only. Demonstrate a controlled incident and report before enabling any app action. Keep evidence/PII retention and customer acceptance separate from software configuration. The existing freelance studio remains planning/records tooling; it does not grant infrastructure authorization.

Support boundaries: no promise that all failures are repairable, no autonomous production repair, no database/volume deletion, no host/IAM/security-group mutation, no guaranteed uptime from a health probe. Failed or ambiguous changes escalate to the owner. Any rollback requires an independently tested mechanism and separate scoped approval. Define response hours and after-hours escalation explicitly; this repository provides no staffed SLA.

Costs: standard-library Python + SQLite adds no database/queue service. Existing Docker and optional Coolify run on customer-selected infrastructure. Budget host RAM/CPU/storage, backups, network transfer, operational time and any existing service/provider terms. Telegram requires an operator-managed bot and external account. There are no paid API/model dependencies introduced, but no assertion that all hosting or third-party services are free. Do not co-locate every optional component on an 8 GB host without measurement.

Commercial roadmap: first prove per-client isolated installs. Before shared hosting, implement organization/user roles, tenant-scoped authorization on every app/server/incident/action/audit lookup, per-tenant secrets, hardened sessions, cross-tenant negative tests, retention/deletion and scoped backups. Keep public signup/tenant selection disabled until verified. Review all native-engine/component distribution licenses before bundling services. Billing needs separate product approval.
