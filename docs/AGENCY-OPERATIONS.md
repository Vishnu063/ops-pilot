# Agency operating manual

This is a single-owner workspace and a prepared service offering, not an operating autonomous agency. All customer references, acceptance and receipts are owner-entered assertions. The example portfolio is synthetic. Nothing is submitted or charged automatically.

## Customer and service

Target: small teams with one stateless HTTP app in an existing trusted Docker image, running on an owned Linux/EC2 host with Docker Compose. The implemented worker generates configuration and instructions. An opt-in disposable practice lab exercises those generated files. Customer deployment remains a separately authorized manual service.

Eligibility checklist: known image provenance and immutable digest; container listens on a known port; simple readiness path returning HTTP 200; no persistence; no required private network; no unsupported configuration; adequate test-host capacity; written scope and rollback prerequisites. Decline or re-scope database/migration work, persistent storage, privileged containers, unsupported runtime configuration, unknown image provenance, unrestricted infrastructure access, guaranteed outcomes and default 24/7 support. Keyword evaluation only flags risk; it cannot establish suitability.

Prepared package: one image, one Compose service, one readiness endpoint, starter handover and review; one agreed revision and a proposed seven-calendar-day support window for delivered configuration. Confirm hours, dates, price and terms with each client. Application development, DNS/TLS, database recovery, cloud provisioning, security certification and ongoing operations are excluded unless separately assessed. Later CI/CD repair, Linux/nginx troubleshooting, monitoring setup and recurring maintenance are disabled as agency workers pending their own acceptance evidence.

## Intake and agreement template

Record the `brief` in Project operations before accepting scope:

- Client alias and external agreement reference, without identity documents or credentials.
- Exact target, owner authorization reference, access expiry, least-privilege access method, credential-store reference; never the credential.
- Image/version/digest, internal port, public/loopback port, health path and expected HTTP response (lab supports HTTP 200), runtime/configuration assumptions, resource requirements, constraints and existing network dependencies.
- Current immutable version for rollback; required backups and recovery responsibility. The worker cannot restore databases or external state.
- Deliverables, exclusions, milestone dates, price/currency, payment milestones, revision limit, acceptance process, confidentiality and responsibilities.
- Support hours/timezone, post-delivery support days, response expectation, escalation contact reference, access revocation and retention period.

These are checklist fields, not legal review or a signed contract. Missing image, permission, safe recovery or acceptance evidence is a stop condition for customer work. Never paste credentials into a listing, proposal, model prompt, project record or Git.

Suggested agreement text: “We will prepare the listed Docker configuration for the identified image and target. Customer authorizes only the listed actions during the listed window. Customer supplies an appropriately limited access mechanism and verifies backups. Price, revisions, acceptance checks, milestone dates, confidentiality, incident contact and support period are the explicitly recorded values. Additional work requires a new agreement reference.”

## Pricing worksheet

Quote = estimated hours × hourly rate × agreed complexity multiplier + hosting + tools + expected platform fees + agreed contingency. Hosting/tools are pass-through estimates only when agreed, never silently purchased. Round currency amounts to two decimal places. Record the final agreed quote and milestones in the brief; no default quote is customer-agreed. Record labor via `time_entry` (hours and hourly_rate), expenses via `expense`, invoices via `invoice`, payments using the existing payment gate after packaging. Each record has a duplicate-protected reference.

Example only: 2 hours × USD 20 × 1.25 + USD 0 hosting/tools + USD 5 expected fees = USD 55 proposed quote. This is not a market claim or an agreed price. Dashboard balances calculate invoice total minus gross payments **within the same project/currency**. Fees do not reduce the amount credited to the invoice. Cash received, fees, expenses, estimated labor and estimated profit remain separate. Credits never offset a different project. Ledger records do not verify a bank receipt. Overdue invoice alerts draft follow-up needs; allocation to individual milestones remains manual (project-level balance only).

## Lifecycle, changes and gates

Listing → scout → heuristic evaluation → tasks/questions → editable proposal → owner proposal approval → owner-recorded proposal acceptance → separate work approval → generation → static review → sign-off of artifact digest → package/download. Customer runtime validation, independent review, customer acceptance, payment recording, revocation/offboarding and closure are separate records.

The first three approvals expire after one hour; practice approval expires after 15 minutes. Revision checks and SQLite immediate transactions reject stale concurrent mutations. Generation consumes work approval. Practice execution consumes durable digest-bound approval before Compose side effects. Sign-off binds artifacts and validation/lab evidence; changed evidence clears delivery approval and invalidates the old download. Packages with evidence include EVIDENCE.json. Project operations can inspect up to 100 saved revisions; pre-upgrade content that was never saved cannot be reconstructed. Scope and brief edits clear approvals. Accepted brief changes are refused: record a `scope_change` with price/deadline impact and external agreement reference, then create a new project with separately agreed scope. Recording a scope change does not apply it or authorize more work. It prevents further work approval on that project.

A package is a download, never submission. A customer acceptance reference is separate from proposal acceptance and internal review. `validation` records distinguish static, sandbox, customer_runtime and independent_review, with passed/failed/unverified result and limitations. A recorded claim is not independently checked. Close requires customer acceptance, offboarding, completed tasks and a settled project invoice balance. Keep unpaid projects open for late payment recording. Closed records are read-only; owner-entered settlement is not independent receipt verification. Credit notes, refunds and invoice-level allocation are not automated.

## Owner desk and n8n

The desktop/mobile studio preserves the nine-role flow. Project operations shows financial state and alerts; advanced panels accept named JSON business records with examples. Use current job ID/revision. Owner-only business actions use the same authenticated dashboard or owner bridge as existing decisions. Models and workflow credentials cannot authorize owner actions.

n8n Form Ending needs persisted successful execution status, so this workflow saves executions. Keep n8n private, restrict administrator access and configure execution pruning (the optional Compose example uses seven days). Credentials belong in protected n8n credential records, never form fields. The bridge accepts bounded JSON on loopback, with separate workflow and owner header keys. No browser-origin bridge action is accepted. The generated n8n form supports manual intake/planning, starter generation/review, owner decisions, board and ZIP. Advanced business records use Owner decision with the Record JSON field; practice execution is kept on the owner desk because it may exceed form HTTP timeouts. No external discovery or messaging connector is configured.

Task fields: id, title, owner, status (todo/doing/blocked/done), optional due (ISO date), blocker and depends_on (existing task). A dependency must be done before its dependent can be marked done. Dashboard alerts show blocked/overdue tasks, outstanding overdue invoices and lab failures/interruption. Responses and escalation are proposed business terms, not background message delivery. One practice lab at a time; an unresolved running/cleanup-failed lab blocks new lab runs. Owner reviews capacity before accepting concurrent customer commitments; there is no automatic customer scheduler.

## Practice lab and recovery

Use only an owned disposable host with local Docker Unix socket. Set `OPS_PILOT_LAB=1` to opt in and `OPS_PILOT_LAB_IMAGES` to comma-separated, trusted immutable image references already present locally. Neither setting grants customer access. Lab code never pulls/builds images, mounts customer files, uses host networking, downloads models or obtains credentials. Do not allowlist untrusted images: containers are not a hostile-code security boundary.

Generate the bundle, confirm its exact job ID, choose Approve exact bundle for lab, then Run approved lab. The actual Compose file uses `${OPS_PILOT_HOST_PORT:-8080}`; lab substitutes `0` for an ephemeral loopback mapping. Normal starter default stays 8080. Memory is 256 MiB, CPU 0.5, PID limit 100, capabilities dropped and no-new-privileges enabled. This may be unsuitable for some images; re-scope instead of silently raising limits. Commands are fixed subprocess argument arrays. Compose config/start/inspect/cleanup have 30/60-second bounds, readiness retries stop after 30 seconds with two-second requests, redirects and proxies disabled. No automatic retries of deployment.

Interrupted runs retain `running` evidence and block edits/new labs. First inspect the owned host for an active process. After it has exited, choose Recover interrupted lab. A process lock refuses recovery while an active local lab holds it. Cleanup checks unique Compose project and job labels before removing containers, and project label/empty membership before removing the unique default network. Foreign resources are refused. A cleanup failure stays visible for owner investigation; never delete resources by broad name patterns. Recovery cleanup is not customer rollback. Recovery requires the recorded original Docker daemon identity and Unix endpoint. A different context/daemon is refused. If the original daemon cannot be reached, keep cleanup unresolved and inspect that host; do not infer old-host cleanup from a different daemon.

Sandbox HTTP success proves only the agreed practice endpoint returned HTTP 200 within bounds. It does not prove customer runtime behavior, security, load capacity, customer acceptance or production readiness. Lab evidence is stored in project state, revision history and audit; starter acceptance.json remains explicitly unverified for customer runtime. Re-sign the evidence after a new lab run. Approved ZIPs include EVIDENCE.json when evidence exists.

## Backup, restoration and retention

Use `python -m ops_pilot.backup backup /private/workspace /private/new-backup` to take a consistent SQLite snapshot. Artifacts and business records live in that database. The fresh backup directory and files are private (0700/0600); manifest records hash/integrity and exclusions. Never put client backups in Git. This command copies state without stopping reads; use a quiet period to simplify operational recovery.

Use `python -m ops_pilot.backup verify /private/new-backup` to check its SHA-256 and SQLite integrity before recovery. Hashes detect accidental corruption; they do not authenticate a backup against an attacker who can alter both files.

Use `python -m ops_pilot.backup restore /private/new-backup /private/new-workspace` to recover into a destination that does not exist. Existing destinations are refused. Restored approvals are cleared and revisions incremented; active labs become interrupted. This prevents replay of pre-backup approvals. Stop the old service, retain its private data, verify the recovered jobs/artifacts, inspect any original-host lab resources, configure new private bridge credentials, start the recovered service on loopback, and obtain new approvals only after review. Test recovery periodically. Backup location must have a private parent and adequate storage; copy off-host/encrypt using your approved mechanism.

Separately back up original monitoring state/config and n8n database/volumes plus its encryption key and credentials according to your installed n8n version. This tool excludes them and cannot recover encrypted n8n credentials without their key. It excludes lab scratch directories; ownership evidence in the database remains for recovery. No automated retention purge is implemented: record retention_until, review it, revoke access using the external reference and manually delete approved private records/backups per agreed policy. Never delete an active client's evidence without an agreed retention decision.

## Communication templates (draft only)

Requirements: “Please confirm the image digest, port, readiness path/response, runtime configuration, target, backup/rollback prerequisites, authorized actions and acceptance checks. We will confirm price/dates after suitability review.”

Progress: “Completed: [files/check evidence]. Pending: [dependency]. Risks: [limitations]. Next action: [owner/client action] by [agreed date]. No additional changes are authorized by this update.”

Incident: “Observed [time/symptom]. Impact currently established: [evidence]. Changes paused pending [safe recovery/approval]. Please use [agreed escalation contact]; no response-time guarantee beyond our recorded support terms.”

Scope change: “Requested [change] exceeds [scope version]. Proposed price/deadline impact: [values]. Current work remains paused at [safe point] until a new scope is agreed.”

Overdue/follow-up: “Our records show [invoice reference/project balance/currency] outstanding as of [date]. Please confirm your payment reference or any discrepancy. These are owner-maintained records.”

Handover: “Attached reviewed artifact version/digest [value], checks [references], known limitations [list], rollback [instructions], acceptance checklist [endpoint/expected response] and support window [dates]. Please confirm acceptance separately after the agreed checks.”

## Expansion gates and measurement

See the synthetic pilot evidence for observed local orchestration elapsed time and exact example financial calculations. There is no real profit or client-delivery benchmark. Optional Ollama advice has bounded input/context/output and identical-input caching, requires an explicitly selected already installed model, and has no tools or paid fallback. No running local service was observed during this implementation; no AI quality/cost comparison or RTK savings is claimed. Install/enable nothing automatically.

Enable later services only after a scoped fixture, implementation, independent review, failure/rollback evidence, service-specific acceptance and agreed support policy. A real paid pilot additionally needs a real customer, agreement, authorized access, reviewed customer delivery, actual acceptance, receipt and offboarding. None is supplied by a synthetic run.

## Saved estimates, intake inspection and client drafts

In **Project operations → Requirements and business records**, choose `quote`, `intake_check` or `draft_message`. The n8n **Owner decision** route exposes the same actions; enter their data in **Record JSON**, including `{}` for intake inspection. All three require the owner credential, use current revisions and persist in project history. None sends a message or changes infrastructure.

`quote` requires decimal strings `hours` and `hourly_rate`; optional `complexity` defaults to `1.00`. Optional `hosting`, `tools`, `platform_fees` and `contingency` are fixed estimated currency amounts, not fee percentages. For example, `{"hours":"2.00","hourly_rate":"20.00","complexity":"1.25","platform_fees":"5.00"}` estimates 55.00 in the project's existing currency. Hours are bounded to 0.01–240 and complexity to 0.01–5; labor rounds half-up to cents before adding costs. This stores an estimate without creating an invoice/payment or setting customer agreement. It clears proposal approval, so review/edit the proposal and obtain fresh approval before recording acceptance. Accepted projects refuse requoting; use the existing scope-change/new-project process. Replacing a brief invalidates its saved estimate and intake report; prior versions stay in revision history.

`intake_check` takes `{}` and records missing fields, unsupported assumptions and access-reference expiry. Extend the existing `brief` with these fields:

| Field group | Values / limits |
| --- | --- |
| Service context | `client_alias`, `target`, `scope`, `constraints`, `runtime_assumptions`, `environment` |
| App/readiness | Immutable `image` digest, canonical `port` string (1–65535), simple absolute `health_path`, `expected_status: "200"`, `configuration: "none"` |
| Suitability declarations | `stateless: "yes"`, `persistent_storage: "no"`, `private_network: "no"` |
| Authorization references | `access_reference`, future `access_expires` ISO timestamp with explicit timezone, `agreement_reference`; references only, never credentials |
| Recovery | `rollback_reference` plus `first_deployment: "no"` and previous immutable `rollback_image`; for a first deployment use `first_deployment: "yes"`, leave rollback_image empty and record an explicit initial-deployment recovery reference |

A complete result is **ready for manual review**, with `authorized_to_deploy` and `customer_runtime_verified` always false. It does not verify the target, image trust, agreement or access rights, and expires with the recorded access window. Recheck before customer work. Existing generic starter generation remains usable with incomplete intake and remains explicitly unverified. Explicitly unsupported configuration, HTTP response expectations, persistent storage or private networking are refused by the worker before file generation. No customer deployment worker is enabled.

`draft_message` accepts `kind` (`requirements`, `progress`, `incident`, `overdue`, `follow_up`) and optional owner-supplied `details`. Incident drafts require observations; the text labels them owner-reported and asks for fact review. Requirements drafts list intake blockers. Progress uses owner-recorded tasks and blockers. Overdue drafts use the selected project's balance only, with a reminder that invoice-level payment allocation is manual. Each draft stores its source revision, `sent: false` and `approved_to_send: false`; review facts and obtain separate sending authorization outside this tool. Prepare follow-up drafts before closing because closed project records are read-only. A project holds up to 100 drafts; old versions remain in its private history.
