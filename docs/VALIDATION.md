# Validation

## Daily operations 0.2 — 19 October 2026

Application/test source commit: `ec375ecbef55a8dada9c2a395e865d67f117489c`.
[Passing six-job workflow](https://github.com/Vishnu063/ops-pilot/actions/runs/39215664960).
This section records observed results; earlier sections below are historical.

- Python 3.11/3.12/3.13 each passed 22 unit/local-HTTP tests, installed CLI/setup
  smoke and Python/shell/dashboard syntax. Three actual Docker cases were skipped
  in unit jobs and all three passed in the separate Docker lab.
- Daily tests cover maintenance cancellation and server-side repair blocks,
  maintenance expiry/restart persistence, pause/target scoping, outage deduplication,
  crash during webhook delivery, failed delivery preserving a repair result,
  failed HTTP recovery alerts, honest OOM/restart diagnosis, authenticated report
  export, minimal HTTP webhook payloads and redirect rejection.
- Real systemd CI installed the service as a nonroot user, checked boot enablement,
  observed a detached service start, restarted it, verified persisted maintenance,
  killed the main process with SIGKILL and observed systemd restart it with a new
  session. No application repair was run. The test removed its own unit afterward.
  **A full host reboot was not performed.** This is Ubuntu 24.04 runner acceptance,
  not validation of the owner's Ubuntu 26.04 background-service installation.
- Chromium desktop/mobile acceptance again passed: exact approval, explicit repair,
  reload without replay, maintenance controls/reload, authenticated JSON download,
  local alert display, escaped labels and no overflow or JavaScript errors.
  Desktop and phone recovery screenshots from the preceding all-green run
  [39215569386](https://github.com/Vishnu063/ops-pilot/actions/runs/39215569386)
  were visually reviewed. The final run retains the same UI; its subsequent code
  change persists outage transitions before webhook I/O and adds the crash test.
- [Final browser artifact](https://github.com/Vishnu063/ops-pilot/actions/runs/39215664960/artifacts/12169830550).
- [Real systemd evidence](https://github.com/Vishnu063/ops-pilot/actions/runs/39215664960/artifacts/12169666455).
- [Actual Docker evidence](https://github.com/Vishnu063/ops-pilot/actions/runs/39215664960/artifacts/12169432785).

The first service test run [39215451466](https://github.com/Vishnu063/ops-pilot/actions/runs/39215451466)
failed because the test fixture shadowed Python's `http` module with a local
variable. That fixture was corrected; its temporary home was also moved outside
`/tmp` so systemd PrivateTmp could not hide the configuration. No repair/approval
checks were relaxed. The next and final code runs passed all six jobs.

Locally, 22 tests passed with three actual Docker skips; shell/Python/dashboard
syntax and README command-block syntax passed. Docker/systemd acceptance was run
in CI, not against a customer host. No external alert recipient was contacted:
webhook tests use a disposable loopback receiver. Real email/phone delivery,
long-running monitoring, full reboot and production operation remain unverified.

The owner separately reported a manual nginx demo recovery on EC2 earlier that
day: HTTP 200 before the outage, stopped-container/endpoint findings after
`docker stop ops-pilot-demo`, and dashboard **Recovery checks passed** afterward.
This user-reported result did not involve CloudLaunch/PharmaCare and does not
validate the new background service on that EC2.

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

A local headless browser was unavailable; the later CI browser acceptance below
passed. AI inference quality, long-running monitoring, remote Docker contexts,
production/customer systems, audit retention and multi-customer controls remain
unverified. Passing this lab does not establish production readiness or the ability
to diagnose arbitrary failures. The configured HTTP endpoint is scoped verification,
not a complete business transaction test.

## Publication history

Initial uploads were not executed because the automatic approval-review model was
at capacity. A later retry initialized GitHub and the complete implementation was
published in PR #1. The earlier ZIP is a pre-CI snapshot; use the GitHub source and
this validation record for the corrected version.

## Desktop/mobile browser and installed setup acceptance

Test/workflow source commit: `d8bed409a4a9b1765acf15b377b2ab8b14aed051`.
[Passing five-job workflow](https://github.com/Vishnu063/ops-pilot/actions/runs/39210004948).
Documentation added afterward records the observed results.

- Chromium through Playwright 1.58.0 passed the dashboard flow at 1280×900 and
  390×844 viewport sizes. No horizontal phone overflow or JavaScript page errors
  were reported. Desktop-approved, desktop-recovered and phone-recovered captures
  were produced; desktop-approved and phone-recovered were visually reviewed.
- Browser checks verified login is required; a wrong plan ID cannot approve;
  correct approval alone performs no mutation; execution displays verified
  recovery; reload cannot replay the action; monitoring pause/resume works;
  hostile labels remain inert text and a second browser has no inherited session.
- This browser flow uses the existing simulated Docker fixture with real HTTP,
  SQLite and dashboard server. It does not replace actual container acceptance.
- The separate three-case actual Docker lab also passed in this workflow.
- Installed CLI/setup smoke passed on Python 3.11, 3.12 and 3.13 from an isolated
  working directory. It verified the installed entry point, wizard configuration,
  file mode 0600 and cancellation without overwriting the existing file.
- All 12 unit/local-HTTP tests and Python, shell and JavaScript syntax checks
  passed on each Python version.
- [Browser evidence and synthetic screenshots](https://github.com/Vishnu063/ops-pilot/actions/runs/39210004948/artifacts/12167725229).
  Artifact ZIP SHA-256:
  `ea5df4eac8b720627484bc3b69b80e26b3d8a431d85f0c5028072207c3df6628`.

This is Chromium viewport acceptance, not testing on a physical Android phone,
all browser engines, assistive technologies or customer infrastructure. No full
accessibility audit or live AI inference benchmark is claimed.


## Freelance studio

[PR #4](https://github.com/Vishnu063/ops-pilot/pull/4) adds bounded freelance
roles and the n8n canvas. [Initial CI run](https://github.com/Vishnu063/ops-pilot/actions/runs/40023426878)
passed Python checks on 3.11/3.12/3.13 and the systemd lab. Its browser job failed
before running tests because Playwright 1.58.0 does not support the new Ubuntu
26.04 runner. The browser job is now pinned to Ubuntu 24.04; consult PR checks
for the subsequent result. The local original and freelance browser flows passed.
Detailed limits are recorded in [FREELANCE-VALIDATION.md](FREELANCE-VALIDATION.md).


## Self-hosted diagnostics follow-on — 2026-10-25

Implementation `7e48a1619d0cb8d9908380a95c4e15ff116d75b1` passed [all seven standard jobs](https://github.com/Vishnu063/ops-pilot/actions/runs/40204417747), [both ecosystem jobs](https://github.com/Vishnu063/ops-pilot/actions/runs/40204417758) and [strict 8 GB real Jenkins/Kind acceptance](https://github.com/Vishnu063/ops-pilot/actions/runs/40204417788). The Python matrix ran 71 cases per version (3.11/3.12/3.13), with four explicit Docker skips tested separately in the real Docker job. The installed Docker and read-only setup wizards, owner/session/Origin boundaries, Trivy import, original/new automated browsers, n8n and systemd passed. No manual review of new browser screenshots is claimed.

Peak enclosing memory was 4,151,042,048 bytes with zero local enclosing limit/OOM events under the enforced 8,000,000,000-byte ceiling. The intentionally OOM-killed child workload raised hierarchical/Docker OOM indicators; the controller remained running. Both practice phases verified cleanup. Sequential phases exclude Grafana/models/providers and do not establish full concurrent production capacity. [Genuine result JSON](evidence/public-readiness.json) and [full review/limitations](PUBLIC-READINESS.md) distinguish these outcomes from prepared or external features. Local socket-dependent tests were blocked by this execution sandbox; their real CI outcomes are linked above.
