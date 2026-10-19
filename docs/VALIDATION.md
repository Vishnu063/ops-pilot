# Validation

## Local checks, 19 October 2026

- Python 3.12.14, Linux.
- Initial 12 unit/local-HTTP tests passed. Docker behavior is simulated there;
  HTTP endpoints, SQLite approvals and the loopback web server are real.
- Python compilation and launcher shell syntax passed.
- Cases: outage deduplication, read-only monitoring, explicit separate approval,
  replay rejection, target/state/daemon drift, expiry, cancellation, timeout
  consumption, permission failures, missing health evidence, failed HTTP recovery,
  restored plans, bounded/private configuration and web session/Host/Origin checks.

Docker is not installed in the editing workspace. Three separate opt-in real
Docker acceptance cases and a three-version Python CI matrix are supplied.
Their results must be recorded from actual CI before claiming Docker acceptance.
AI inference quality and customer/production infrastructure are not tested.

## Publication status

Initial GitHub attempts were not executed because automatic approval review
could not run (model capacity). A later retry initialized the repository with
README commit `7abd2c8b5ef784b9b4e3d18a34fd316b52c3d06a`.
Implementation publication and real Docker CI results are being verified;
workflow presence alone is not evidence of passing tests.

Final local result: 15 discovered cases, 12 passed, 3 real-Docker cases skipped.
Package wheel build passed. Python compilation, shell syntax and dashboard
JavaScript syntax passed. A local headless browser was unavailable, so visual
and interactive browser acceptance remain pending.
