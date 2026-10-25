# Install and operate one trusted-owner instance

Ops Pilot is installable software for one trusted local engineer. It is not a hosted service or a verified multi-tenant system. The HTTP server binds only to `127.0.0.1`; there is no public bind or multi-user switch. Use a separate OS account, process, private state directory and native credential profile for each trust boundary. An environment ID separates report storage, not hostile users sharing one account. Docker access is effectively host administration: never publish its socket or mount customer sockets into a public web service.

## Install and connect

Use Linux with Python 3.11+, Git, the venv package for your Python, and the native tools you explicitly need. Docker monitoring requires access to your selected local/SSH Docker context. No Kubernetes cluster, Jenkins, cloud account, scanner, Grafana or model is installed automatically.

```sh
git clone https://github.com/Vishnu063/ops-pilot.git
cd ops-pilot
# Until PR #6 is merged, review and check out feat/public-selfhosted-readiness.
bash start.sh setup
bash start.sh serve
```

The existing wizard records one exact container and its application HTTP/HTTPS endpoint, writes configuration with mode `0600`, and performs no repair. Open the private login link printed by `serve`. The random owner session rotates when the server restarts. Do not share the link or expose the port through a public tunnel. Sessions are local owner capabilities, not individual user accounts. Access a remote self-hosted instance through an authenticated SSH tunnel:

```sh
ssh -N -L 8767:127.0.0.1:8767 your-authorized-host
```

Use the forwarded `127.0.0.1:8767` URL and private login token. Retain SSH authentication and network firewall controls. TLS/public proxy deployments, federated login, tenant administration and hostile-user isolation have not been accepted. Multi-user operation stays disabled.

## Optional diagnostics wizard

```sh
bash start.sh setup-diagnostics --diagnostics-config "$HOME/.config/ops-pilot/diagnostics.json"
bash start.sh diagnostics --diagnostics-config "$HOME/.config/ops-pilot/diagnostics.json" --tool kubernetes
bash start.sh serve --diagnostics-config "$HOME/.config/ops-pilot/diagnostics.json"
```

Choose an environment ID, a collector and exact scope names. The wizard neither connects nor overwrites an existing file. CLI exit codes are `0` for no findings in the collector's scope, `1` for findings and `2` for inconclusive/configuration errors. No-findings does not establish end-to-end application health. The dashboard's **Read-only diagnostics** link collects and downloads reports; it never exposes a shell, context selector, arbitrary endpoint or repair API. Missing/partial evidence is inconclusive. Only the separately configured application monitor/incident desk can propose an allowlisted Docker repair.

Expand the private file locally to select more collectors. Example with no credentials:

```json
{
  "environment": "owned-staging",
  "tools": {
    "kubernetes": {"context": "owned-staging", "namespace": "app", "resource": "web", "service": "web"},
    "jenkins": {"base_url": "http://127.0.0.1:18080", "resource": "owned-job", "basic_auth": {"username_env": "OPS_JENKINS_USER", "password_env": "OPS_JENKINS_TOKEN"}},
    "aws": {"profile": "ops-readonly", "region": "us-east-1", "resource": "i-0123456789abcdef0"},
    "helm": {"context": "owned-staging", "namespace": "app", "resource": "web"},
    "argocd": {"server": "argocd.example.internal", "resource": "web"},
    "prometheus": {"base_url": "http://127.0.0.1:19090"},
    "grafana": {"base_url": "http://127.0.0.1:13000"}
  }
}
```

Do not paste cloud credentials, tokens, kubeconfigs, Helm manifests or scanner descriptions into incident text. Set Jenkins environment bindings through a private service environment file, or your existing credential manager. Native AWS profiles, kubeconfig contexts and ArgoCD CLI credential stores remain on the operator host. HTTPS is required for remote HTTP collectors; loopback HTTP supports SSH forwarding. HTTP credentials do not follow redirects or environment proxies. Keep a distinct native read-only context/profile for diagnostics; the application repair credential is a separate privilege.

## Permissions and collection limits

| Collector | Fixed reads and actual scope | Permission/limit |
| --- | --- | --- |
| Kubernetes | One Deployment, owned ReplicaSets/pods, bounded events/log signature counts; scheduling, image, crash, OOM, rollout and probe evidence | Namespaced get/list for deployments/replicasets/pods/events/services and get pods/log. Secret/ConfigMap existence checks can be denied; those checks then remain incomplete. Kubernetes RBAC cannot grant value-free `get secret`; do not grant secret access just to remove a warning. Up to 20 pods, 40-second deep evidence budget; no cluster-wide repair. |
| Jenkins | Latest build number/result, then console signature counts for that exact numbered build | Read access to one job/build/log. Logs are discarded, not retained. No build trigger/retry/configuration write. Nested folder jobs are not supported by this exact-name Ops profile. |
| EC2 | `DescribeInstanceStatus` for one explicit instance ID and profile/region, instance/system reachability | IAM allow only the required read action and region. AWS may require `Resource: "*"` for describe calls; a collector's instance filter is not an IAM isolation boundary. No start/stop/reboot/SSM, CloudTrail attribution or guest CPU/memory collection. |
| Helm | Exact release status and latest ten history entries | Dedicated namespace/context credentials; release storage may require sensitive Secret access. No `upgrade`, `rollback`, hooks or manifest export. Migration safety and a known-good revision require engineer review. |
| ArgoCD | Exact application's native health/sync/operation metadata | Existing CLI login with read-only application policy. No login automation, sync, prune or rollback. Desired/live drift alone does not identify its cause. |
| Prometheus/Grafana | Native health/status profiles | Read-only private endpoints; no datasource, alert or dashboard mutation from Ops Pilot. |

The read-only desk does not have approval/apply endpoints. Runtime collection is single-flight; the HTTP server allows eight concurrent requests with bounded input/read timeouts. Reports are private SQLite files (`0600`) under `diagnostics/<environment>`, latest eight shown, exact stored IDs downloadable, with a 2,000-report admission ceiling. Archive private evidence before the ceiling; do not silently delete audit history. Local audit hashes/triggers do not protect against root or a compromised owner account.

## Trivy and optional AI

Run Trivy separately against an immutable image through your reviewed build pipeline. In the diagnostics desk, import a Trivy schema-2 JSON file and exact `sha256:` artifact digest. Input is limited to 256 KiB; the browser allows 250,000 bytes to leave envelope space. Reports project only vulnerability ID/package/version/severity, severity counts, truncation and declared artifact identity. Descriptions/secret scan results/raw files are not retained. Import does not execute a scan, attest the image association, prove exploitability, or fix the image. Rebuild and review the source dependency/image change through normal CI.

The existing optional installed Ollama explanation remains advisory. Set `OPS_PILOT_K8SGPT=1` only for an already installed K8sGPT executable; its fixed scoped analysis does not request provider inference (`--explain` is absent), download models, or execute generated commands. Provider/weight licensing and actual K8sGPT runtime acceptance remain separate. No paid fallback exists.

## Monitoring and approved recovery

Follow [ecosystem configuration](ECOSYSTEM.md) for distinct CloudLaunch/Alertmanager/source/read tokens and the optional Prometheus/Blackbox/Alertmanager/Grafana profiles. `scripts/setup-ecosystem.py` creates a fresh private directory and does not launch servers. Deployments use the existing CloudLaunch reporting adapter; failed/security/rollback outcomes are evidence. Read-only integration access uses `/integration/state`, `/integration/diagnostics` and `/metrics` with the separate reader bearer token. Source/read credentials cannot collect diagnostics, approve or repair. Owner writes require the local session, expected Host and Origin.

Detection → native evidence → hypotheses → exact Docker restart proposal → owner approval → separate apply → exact container/daemon/state + consecutive HTTP successes + fresh service-scoped Prometheus probe and Alertmanager resolution → report. Stale target/configuration/state, expired or consumed approval, maintenance and uncertain evidence refuse execution. Webhooks cannot approve. A restart cannot undo code/configuration/data changes; no automatic retry or rollback is invented. The existing generated practice bundle and CloudLaunch pipeline have their own explicit rollback/health gates. Helm/Kubernetes/GitOps write operations remain disabled in the new desk.

## Troubleshooting and recovery of the controller

* **Login/403:** use the fresh private token and loopback hostname/port; preserve Origin/Host. API source/read keys are not owner sessions.
* **Inconclusive:** confirm native CLI, exact context/profile/resource, read permissions, HTTPS certificate and response schema. Unsupported or missing evidence is not healthy.
* **Jenkins logs unavailable:** confirm read-log permission and build number. Oversized logs exceed the upstream 1 MiB read bound; inspect them locally without uploading credentials.
* **No metrics:** confirm scrape job/service labels and exporter configuration. Grafana does not store logs. Missing exporters are disconnected, not zero resource use.
* **Busy/interrupted repair:** inspect the persisted exact plan, audit and actual target before creating any new plan; never reset an operation to replay it.
* **Reports/retention:** keep state and backups private and encrypted as appropriate. The agency backup command does not automatically include the separate diagnostic/ecosystem databases. Stop the instance before a consistent whole-state filesystem backup and restore into an isolated destination for verification.

For a modest host, start only the controller and native collectors. Monitoring, Grafana, Jenkins, Kind and models are optional. See the [readiness record](PUBLIC-READINESS.md) for actual constrained lab measurements and what was excluded. An isolated sequential lab is not a production capacity promise.
