# Security boundaries

Early single-owner preview. Keep the dashboard on loopback and use an existing SSH
tunnel. Do not expose it with 0.0.0.0, a public proxy or an open EC2 security group.
The startup login link is a capability: keep it private. Configuration and history
are private local files, not independently encrypted or tamper-proof against the
owner/root. Docker access can grant host-root-equivalent authority.

Use exact Docker contexts and application-owned health endpoints. Do not run two
instances against the same target/state directory. Configuration is trusted at
startup; stop the process before changing contexts. A read scan does not prove
repair permission. Connection failures remain incomplete evidence, not success.

A repair requires a new exact plan, explicit approval and separate execution.
Approval expires, is bound to state/configuration and is consumed before dispatch.
No auto retry or rollback. Interrupted plans require manual inspection. The
application endpoint and matching container state must pass to record recovery.
This is scoped verification, not proof of all customer operations.

No raw logs are persisted by the diagnostic adapter; signature counts and selected
metadata are retained. Reports can still identify systems. History has no automatic
rotation yet. Protect the state directory and remove it only after stopping the
process and preserving required incident records. Never commit config.json, state,
credentials, signed policies, environment files or customer evidence.

Optional local AI is untrusted advice. No model/download is enabled by default.
Do not paste secrets into model prompts or reports. No full security audit or
production acceptance has been performed. Report sensitive issues privately to the
repository owner rather than placing customer data in public issues.

## Daily operation boundaries

The optional systemd service runs as the installing user, who already has Docker
access. It is not a sandbox against a compromised Docker daemon/account. Treat
service journals as private because they contain the login capability. Source
updates affect that user's next service start. Keep the repository trusted.
Maintenance is a server-enforced block on planning/approval/execution, not just
a UI switch. Downloaded JSON contains target identifiers and filtered evidence.
Review it before sharing. Outgoing webhooks are opt-in; keep private path tokens
in local configuration only. Network timeouts do not provide guaranteed alert
delivery. Do not configure untrusted receivers.
