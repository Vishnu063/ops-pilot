# Official API contract and version capability matrix

Research: 2026-10-29. Latest published release observed: **v4.5.3** (2026-10-28). Contract source pinned to [`70c1bcb1381de7d42fd290e6cd50bf9a5bcf714d`](https://github.com/coollabsio/coolify/tree/70c1bcb1381de7d42fd290e6cd50bf9a5bcf714d).

The documentation website was unreachable from this execution sandbox. The official project's [OpenAPI document](https://github.com/coollabsio/coolify/blob/v4.5.3/openapi.yaml), [API routes](https://github.com/coollabsio/coolify/blob/v4.5.3/routes/api.php) and [deployment controller](https://github.com/coollabsio/coolify/blob/v4.5.3/app/Http/Controllers/Api/DeployController.php) were inspected instead. API reference: https://coolify.io/docs/api-reference/api/operations/list-applications . No installed instance was accessed. Version-contract support below is **not live compatibility certification**.

All paths below are prefixed by `/api/v1`. Bearer authentication; tokens are team scoped by Coolify. No environment/secrets/private-key endpoint is requested.

| Capability | v4.5.3 contract | Ops Pilot support | Permission / constraints |
| --- | --- | --- | --- |
| Version | GET /version | Detect exact version | read; accepts documented plain version or JSON string |
| Applications | GET /applications | Bounded discovery, no auto-enrollment | read; max 200, response max 256 KiB |
| Application | GET /applications/{uuid} | Exact identity/status projection | read; UUID equality enforced |
| Servers | GET /servers | Inventory only, no inferred host health | read; max 200 |
| Deployment history | GET /deployments/applications/{uuid}?take=5&skip=0 | Five most recent, filtered fields | read |
| Deployment status | GET /deployments/{uuid} | Verify exact receipt ID | read |
| Logs | GET /applications/{uuid}/logs?lines=N | On-demand incident logs, 1–200 lines, 8 KiB output | read:sensitive; use only when necessary |
| Restart | POST /applications/{uuid}/restart | Separate scoped plan/approve/execute | deploy token; explicit app policy; deployment receipt + endpoint verification |
| Redeploy | POST /deploy with JSON {uuid} | Same gates; immutable configured 40-hex git commit only | deploy; moving branch/tag unsupported |
| Rollback | Documented upstream separately | **Unsupported in this connector** | No untested rollback or destructive fallback |
| Host/resource mutation | Not used | **Unsupported** | No arbitrary commands, deletes, daemon/host actions or AWS mutation |

The history OpenAPI schema says array, while the release controller returns an object containing `deployments`; both bounded forms are accepted and tested. Responses are projected, never copied wholesale. Restart and deploy must return a deployment UUID; otherwise outcome remains unknown with approval consumed. POST requests are never retried, including 429 and timeout. Read retries: at most three attempts with 0.25/0.5-second backoff, numeric Retry-After honored only up to two seconds; longer or nonnumeric limits defer to a later monitoring interval.

Other versions, including legacy v4 beta/nightly, are **unverified read-only candidates**: version, discovery/status calls can be attempted, unavailable endpoints become inconclusive, and mutations are disabled. Do not relabel all v4 releases supported. A configured deploy-token binding indicates intended capability, not proof that remote permission is granted. No write permission probe mutates applications during connection validation.

Application runtime, Coolify-reported health, endpoint readiness and deployment status are separate evidence. Runtime `running` alone is never healthy. Endpoint success does not prove all business functions. Failed/unknown deployment and connection states are displayed explicitly. No app-provided URL or shell instruction is followed automatically.

Quality correction: verification also binds deployment `application_id` to the numeric `id` from GET of the exact target application. Team scope alone is insufficient. Both fields are present in the inspected v4.5.3 serializer/model contract; missing IDs disable planning/verification. Known receipt evidence is persisted before health verification. [Source references and remaining assumptions](QUALITY-REVIEW.md).
