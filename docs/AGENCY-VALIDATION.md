# Agency continuation validation

Current continuation is on `feat/freelance-agency-studio`, PR #4, not main. Inspection confirmed the clean remote feature head `fe83251a20ce8c42843c111222a183573010743a`, open/unmerged PR and the prior successful [foundation run](https://github.com/Vishnu063/ops-pilot/actions/runs/40023644211). That run proves only the prior foundation. Historical untracked drafts were absent; new modules implement their stated requirements.

Local continuation checks (2026-10-24): initial full suite 40 discovered / 36 passed / four Docker skips; added interruption/expiry tests and final rerun results will be recorded below. Financial tests cover project isolation, duplicate references, exact cents, fees, labor rounding and unauthorized mutations. Backup tests cover consistency/artifact recovery, private modes, hash tampering and refusal to overwrite. Lab-control tests use simulated subprocess failures and must not be described as Docker execution.

Installed CLI/setup smoke passed with the virtual environment on PATH. Python/shell/dashboard JavaScript syntax and generated n8n structural/credential-boundary checks passed before workspace recovery; rerun required on recovered checkout.

Local Playwright downloaded successfully, but Chromium launch was refused by the macOS sandbox (`bootstrap_check_in ... Permission denied`). No new local visual/browser pass is claimed. Linux browser CI remains required. Local Docker and systemd are unavailable. An Ollama executable is present; localhost:11434 refused connection. No model was downloaded or started; real advice quality/usage comparison remains unverified.

The workspace directory unexpectedly disappeared during validation, including uncommitted source and a disposable n8n install. Its cause was not established. Authoring commands were recovered from this chat's local command log, replayed against a fresh clone, and checkpointed in Git. Final checks apply to the recovered tree. This incident is not a successful n8n import/acceptance result.

## Required checks and their purpose

- `python -m unittest discover -s tests -v` tests persistence, authentication, approvals, business/accounting, backup and simulated failure behavior. Opt-in Docker tests explicitly skip without a disposable host.
- `python scripts/installation_smoke.py` tests the installed command entry point and private setup/cancellation. Activate the repository virtual environment first so `ops-pilot` is on PATH.
- `python -m compileall -q ops_pilot scripts tests` checks Python syntax; `bash -n start.sh scripts/install-service.sh` parses shell scripts without executing them.
- Extract each dashboard's script and run `node --check` to parse JavaScript without a browser. This does not establish visual correctness.
- `python scripts/build-freelance-workflow.py` regenerates the credential-free inactive workflow; `python scripts/check-freelance-workflow.py` checks structure and owner/worker boundaries. Neither establishes n8n runtime behavior.
- `python tests/browser_acceptance.py` and `python tests/freelance_browser.py` exercise real desktop/mobile Chromium against local HTTP/SQLite; original monitoring uses simulated Docker.
- `OPS_PILOT_GENERATED_LAB=1 python -m unittest discover -s tests -p test_generated_bundle_lab.py -v` pulls a public practice image as test setup, then validates the actual generated Compose artifact with an immutable allowlist, real start/readiness/unhealthy endpoint and owned cleanup. Run only on an owned disposable Docker host; the worker itself never pulls images.
- `python scripts/synthetic-pilot.py` exercises nine roles, explicit owner gates, synthetic business/financial records and backup restoration; saves a labelled report and example starter bundle. It deploys nothing and collects no money.

## Remaining external actions

No customer infrastructure, cloud account, signed agreement, verified authorization, actual acceptance, bank receipt, paid pilot or platform account was supplied. No proposals/messages were sent, services publicly exposed, payments collected or customer changes performed. External acceptance cannot be marked complete by an owner checkbox or a synthetic test. Optional repositories remain deferred as described in the decision inventory. n8n credentials/volumes require their own backup; this repository's snapshot tool cannot replace it.

## Verified continuation evidence

[Run 40032826085](https://github.com/Vishnu063/ops-pilot/actions/runs/40032826085) passed all six existing jobs on commit `54faba2946b080626abb877932fa4c7773776044`: Python 3.11/3.12/3.13 tests and installation/syntax/workflow checks, desktop/mobile browser journeys, original and generated-bundle real Docker labs, and actual systemd start/crash recovery. Mobile overflow and an incompatible privileged nginx fixture were corrected before this pass. The compatible unprivileged practice image uses port 8080; see [upstream image documentation](https://github.com/nginx/docker-nginx-unprivileged). Healthy readiness passed, unhealthy readiness failed within its bound, and both cleanups were verified. This is practice acceptance only.

Browser artifacts were downloaded from that run and visually inspected at desktop/mobile sizes. The synthetic screenshot and browser result are saved under docs/images/agency-studio.png and docs/evidence/agency-browser.json. Later evidence/history/daemon protections have local regression tests and require the final CI result below.

Local disposable n8n installation failed following network errors, then exhausted available disk on retry. Only task-owned runtime/cache files were removed; no existing n8n installation was modified. The real n8n journey is being run in an isolated Linux CI job with Node 24 (required by n8n 2.44.6). The first attempt could not reach a ready form; sanitized runtime diagnostics were added. No n8n end-to-end success is claimed from that failure.

The real n8n run exposed a foundation runtime error that import/structural checks had missed: Form Trigger responseMode=responseNode requires a Respond to Webhook node and conflicts with the Form Ending design. The generator now uses lastNode (Workflow Finishes); actual acceptance is rerun after this correction.

The next real form test reached submission and exposed another runtime requirement: n8n completion polling needs successful execution persistence. The workflow retains the foundation setting to save executions, with private n8n access and bounded retention required. Disabling payload persistence broke completion and was reverted; keeping secrets out of forms remains essential.

Real n8n intake/planning and owner approvals then passed. The generated-file route exposed an adjacent `}}` object closure inside its expression; those braces are separated so they cannot be read as the expression terminator. Runtime acceptance continues beyond that fix.
