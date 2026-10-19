# Validation

## Verified CI — 19 October 2026

Application/test source commit: `4aeae618df48b1ef3d204aca65d56c2df33c08b6`.
Documentation added afterward records this observed result without changing the
application or test code.

[Passing workflow](https://github.com/Vishnu063/ops-pilot/actions/runs/39208429071)
— all four jobs passed:

- Python 3.11, 3.12 and 3.13: package/dependency installation, 12 unit/local-HTTP
  tests, Python compilation, launcher shell syntax and dashboard JavaScript syntax.
  Three opt-in Docker cases were skipped in each unit job, then run separately.
- Actual disposable Docker lab: all three tests passed in 34.662 seconds.
  Docker 28.0.4 on GitHub's Ubuntu 24.04 runner, Python 3.12.15.
- Lab image resolved to
  `python@sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4`.
- [Docker lab evidence](https://github.com/Vishnu063/ops-pilot/actions/runs/39208429071/artifacts/12166617437).
  GitHub artifact ZIP SHA-256:
  `8abd8336f9e326ff094914ea41e5ae25a1dd02a70add3ef8a9b21c42fac32bec`.

### What the real Docker tests proved

1. Stop an owned, uniquely labelled HTTP container; detect its outage and collect
   evidence. Execution without approval is refused; approval alone leaves the
   container stopped. An explicitly executed restart passes Docker and consecutive
   HTTP checks. Reusing that approval is refused.
2. Restart with an intentionally wrong application endpoint: Docker becomes
   running, but the result is `needs_attention`, not verified recovery.
3. Externally start the stopped container after planning: stale approval is refused.

Only disposable CI containers were affected and removed. No customer or EC2
application was connected, restarted or changed.

### Initial failure and correction

[The initial run](https://github.com/Vishnu063/ops-pilot/actions/runs/39208300793)
passed the Python matrix but failed two real Docker cases: a dynamically published
host port changed after restart, invalidating the lab's health URL. The lab now
selects a free port and explicitly publishes that same port for the container's
lifetime. Cleanup is registered before readiness checks so failed setup also
removes the owned container. The passing run above includes these corrections;
no approval or application verification checks were weakened.

## Local checks

Python 3.12.14, Linux. Twelve unit/local-HTTP tests passed, three actual Docker
cases skipped because Docker is absent locally. Package wheel build, Python
compilation, shell syntax and dashboard JavaScript syntax passed. The tests use
real local HTTP, SQLite plans and web-session controls; their Docker adapter is
simulated. CI separately supplies the actual Docker evidence above.

## Boundaries still pending

A local headless browser was unavailable. Visual and interactive browser
acceptance, AI inference quality, long-running monitoring, remote Docker contexts,
production/customer systems, audit retention and multi-customer controls remain
unverified. Passing this lab does not establish production readiness or the ability
to diagnose arbitrary failures. The configured HTTP endpoint is scoped verification,
not a complete business transaction test.

## Publication history

Initial uploads were not executed because the automatic approval-review model was
at capacity. A later retry initialized GitHub and the complete implementation was
published in PR #1. The earlier ZIP is a pre-CI snapshot; use the GitHub source and
this validation record for the corrected version.
