# Repository audit before Coolify changes

Base: main and feature/coolify-integration both `349aa13e4d3be33665bd8335636fc315e71b5ee2`; no open PRs observed 2026-10-29. Development uses a separate snapshot, retaining unrelated older checkouts. Main is not modified.

| Capability | Existing | Working evidence | Needs improvement | Proposed change |
| --- | --- | --- | --- | --- |
| Docker monitoring | service.Pilot / native pinned engine | Previous main CI; current local socket tests blocked | One target | Keep native workflow; independent fleet inventory |
| Failure detection | monitor + EventHub | 16 local EventHub tests passed previously; baseline includes them | Provider status distinct from health | Per-app consecutive thresholds and connection incidents |
| Recovery approval | native persisted plans | Main CI; baseline HTTP tests blocked | Separate provider-specific identity | Add exact Coolify plan/approve/execute; never share approvals |
| Restart verification | daemon/container + endpoint/metrics | Existing Docker CI evidence | Queued Coolify action is not recovery | Deployment terminal status plus sustained endpoint verification |
| Dashboard | legacy + studio/ecosystem/diagnostics | Main CI browsers; local sockets blocked | Fleet view missing | Add optional authenticated /coolify page |
| Freelance studio | Workspace / agency / n8n | Baseline non-socket tests; historical main CI | Preserve | No changes to workflows |
| Coolify | Absent in inspected modules | None | New connector | Documented API, mocks first, real instance gate |
| Multi-server | Single Docker target; read-only environment profiles | Scoped collector tests | No fleet scheduler | Explicit bounded app/instance inventory, no host provisioning |
| Multi-tenant security | Explicitly disabled, one local owner | Existing session/Origin/Host tests in CI | No customer isolation | Keep disabled; document tenant roadmap |

Baseline command: `$ PYTHONPATH=/workspace/public-pilot/devops-triage-assistant /workspace/ops-venv/bin/python -m unittest discover -s tests -v`.
79 cases: 21 errors, 4 opt-in Docker skips. Each error is socket creation denied (`PermissionError: Operation not permitted`), before functional assertions; not represented as passing. Remaining 54 passed. CI will rerun unchanged legacy tests plus new tests with real local HTTP. The baseline predates all new implementation changes. No live Coolify/AWS credentials configured.

Architecture: standard-library threaded loopback HTTP with bounded workers, same-site owner cookie, exact Host/Origin checks, optional private bridge roles; native engine pinned to immutable source; private SQLite for monitor/studio/events/reports. CLI and setup are retained. Existing webhook notification is optional best effort. No dependency/database replacement is necessary.

Security observations: Docker access is host-privileged; existing execution is exact-target allowlisted. Single-owner local sessions are not tenant auth. API evidence is untrusted. New outbound provider destinations require URL/DNS restrictions, verified TLS, no redirects, bounded data, no mutation retries and secret projection/redaction. Config edits remain local-owner operations. Hash-chained audit records are tamper-evident to an offline verifier, not protection against a compromised owner. Current sandbox prevents direct HTTP/proxy sockets; official upstream source was read through GitHub.

Plan: add provider contract/client, private fleet state, thresholds/diagnostics/notifications, exact approvals with consumed-before-I/O execution, optional UI/CLI; mocked API tests and CI real HTTP/browser regressions. Real Coolify testing remains separately authorized on a disposable instance.
