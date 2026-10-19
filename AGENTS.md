# Working agreement

Work step by step. Reuse existing code, keep changes focused, test real failures,
and never claim success without evidence. Make routine decisions yourself; ask
only when essential. Do not delegate work unless the user requests it.

## Project scope

Ops Pilot 0.1 manages one explicit Docker application for one trusted local owner.
Reuse the pinned DevOps Triage Assistant engine for collection, persisted plans,
expiry, approval consumption, incident history and application-health checks.
Do not replace the engine with arbitrary shell execution or AI-generated commands.
Monitoring may investigate; approval and repair must remain separate user actions.
No customer infrastructure, credential setup, cloud provisioning or public exposure
is authorized by repository development alone.

## Checks

Run `python -m unittest discover -s tests -v`, Python/shell syntax and dashboard
JavaScript syntax checks. Unit tests simulate Docker but use real local HTTP.
Run the three opt-in disposable Docker tests through CI when Docker is unavailable
locally; report skips distinctly. Keep actual CI links in docs/VALIDATION.md.
Never describe a running container as a fully recovered application without its
configured endpoint passing. Do not claim production readiness from lab tests.

CI also runs `python scripts/installation_smoke.py` against the installed CLI and
`python tests/browser_acceptance.py` with Playwright/Chromium for the dashboard.
Browser acceptance reuses simulated Docker and real HTTP/SQLite; never describe
it as a replacement for the separate real Docker lab. Review its synthetic
desktop/mobile screenshots before claiming visual acceptance.
