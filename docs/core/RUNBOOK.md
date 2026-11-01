# Read-only core diagnostics configuration and acceptance

Keep the existing single-owner loopback installation and installation guide. Use the existing diagnostics wizard for basic profiles; optional flags can be added to the private JSON file. Do not submit credentials through dashboard forms. Configuration must be a regular, non-symlink file with permissions 0600 and at most 16 KiB. See existing diagnostics CLI help for paths and commands.

Example `tools` entries (inside the existing `environment`/`tools` object):

```json
{
  "github-actions": {
    "base_url": "https://api.github.com", "owner": "YOUR_OWNER", "repository": "YOUR_REPOSITORY",
    "resource": "123", "workflow_id": "456", "history": true, "logs": true,
    "headers": {"Authorization": {"env": "OPS_GITHUB_TOKEN", "prefix": "Bearer "}}, "service": "app"
  },
  "jenkins": {"base_url": "https://jenkins.example.org", "resource": "owned-job", "history": true, "stages": true},
  "prometheus": {"base_url": "http://127.0.0.1:9090", "job": "owned-app"},
  "aws": {
    "profile": "ops-readonly", "region": "us-east-1", "resource": "i-12345678", "account": "123456789012",
    "metadata": true, "metrics": true, "alarm_names": ["owned-app-health"],
    "log_group": "/owned/app", "log_stream": "owned-stream", "auto_scaling_group": "owned-app"
  }
}
```

Validate native header binding shape against the pinned adapter before use; no credential value belongs in JSON. A target group is optional: `target_group_arn` must be its exact ARN with matching account and region. Omit every extension you do not authorize. CloudWatch native EC2 metrics do not measure memory or filesystem consumption. Missing samples or insufficient alarm data remain unknown/inconclusive.

Required AWS reads for selected options: `sts:GetCallerIdentity`, native `ec2:DescribeInstanceStatus`, optional `ec2:DescribeInstances`, `cloudwatch:GetMetricStatistics`, `cloudwatch:DescribeAlarms`, `elasticloadbalancing:DescribeTargetHealth`, `autoscaling:DescribeAutoScalingGroups`, `logs:GetLogEvents`. Use resource/condition restrictions where the service supports them; describe APIs may require wildcard IAM resources. Ops Pilot always requests configured IDs rather than account-wide discovery. Do not attach any write permission for diagnostics. Kubernetes/EKS uses the existing exact context/namespace with read-only namespace-scoped RBAC; no new authentication/provisioning flow is introduced.

Run in a disposable socket-capable development environment after safely integrating onto real history:

```bash
$ python -m unittest discover -s tests -v
$ python tests/browser_acceptance.py
$ python tests/freelance_browser.py
$ python tests/ecosystem_browser.py
$ python tests/diagnostics_browser.py
$ python tests/coolify_browser.py
$ python -m bandit -r ops_pilot -ll
$ python -m pip_audit
```

Install test tools through the existing documented development/CI setup. Review security output; do not suppress findings to obtain green status. Existing opt-in Docker acceptance requires an isolated authorized daemon and its documented flags; never point fault-injection scripts at production. Inspect browser screenshots. Check CI against the actual newly published commit, not old branch checks. Measure combined resource use on an 8 GB constrained disposable host.

For Coolify v4.5.3: record disposable instance version evidence; privately configure a least-privilege read token and exact app allowlist; run connection/discovery, invalid-token, timeout and malformed-response cases; preserve redacted API responses and timestamps. Do not restart/redeploy. Request separate authorization naming the exact application UUID and action before one recovery test. Then match deployment UUID and application identity, require sustained endpoint health, and preserve timeout/failure receipts. Until that authorized test passes, recovery compatibility is NOT VERIFIED. Existing `docs/coolify/ACCEPTANCE.md` remains the detailed acceptance checklist.

## Optional Docker resource evidence

Add `"docker": {"context":"owned-context","resource":"owned-container","metrics":true}` to the private `tools` object to authorize one read-only Docker collector. Without `metrics`, the extra stats call is omitted. The collector pins the current immutable container ID and daemon, limits stats to a single non-streaming sample with an eight-second command deadline, and checks identity again afterwards. Missing/malformed stats are inconclusive. The diagnostic report never authorizes a restart. Use the separate existing owner approval workflow for repairs.

## State permissions and troubleshooting

The monitor, agency, diagnostics and fleet state paths must be owned by the running POSIX user, with no symlink components, hard-linked files or FIFOs. Existing state contents are retained while leaf directory/database permissions become 0700/0600. Journal/WAL/SHM files receive the same checks. A rejection is a security error: inspect the path offline; do not bypass the checks or automatically delete evidence. The host owner and root remain trusted. The pinned native engine retains its own storage controls.

## Backup and code rollback boundaries

Stop all Ops Pilot writers in an owner-controlled maintenance window before an offline archive of the entire private state directory; do not copy only a live SQLite database and omit its WAL/journal. Protect backup directories/files as 0700/0600 and keep credential environment files outside Git. Use the existing agency backup/verify/restore workflow for agency data only; that tool does not cover fleet or native Docker state. Validate an archive privately on a disposable machine before relying on it.

An old state archive can contain valid-looking pending/executing approvals. Do not restore it into an active repair installation. Keep recovered fleet/native databases offline for historical inspection; use fresh operational state and create new plans/approvals only after reconciling outstanding remote operations. There is no generic safe fleet/native approval-restoration tool. Do not clear an executing latch merely to retry an ambiguous operation.

Rollback of application deployments is separate from Ops Pilot code rollback and is not automatic. For a code rollback, preserve the private state archive and select a reviewed commit from real GitHub ancestry in a separate checkout; validate compatibility against a disposable copy of state before changing the operating installation. No downgrade/reconciliation of approval state is supplied. These are procedures, not evidence that a production restore has been tested.

## Docker Compose boundary

No new tested Compose deployment package is supplied by this continuation. The supported installation remains the existing native loopback process (or its documented trusted-host service). Publishing a container port does not make a service bound to the container's loopback reachable through bridge NAT. A Linux host-network diagnostic-only container can retain the loopback bind, but has not been accepted here. Do not solve connectivity by changing the default bind to public, exposing a Docker TCP endpoint or mounting an unrestricted Docker socket into a public dashboard. Compose packaging and a restricted Docker execution boundary require separate disposable acceptance before being advertised as supported.
