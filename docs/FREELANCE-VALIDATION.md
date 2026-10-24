# Freelance workspace validation

Current agency additions, all 50 step statuses and subsequent evidence are in [AGENCY-ROADMAP.md](AGENCY-ROADMAP.md), [AGENCY-OPERATIONS.md](AGENCY-OPERATIONS.md) and [AGENCY-VALIDATION.md](AGENCY-VALIDATION.md). The foundation results below retain their original date.
Observed locally on 2026-10-23. All listings, acceptance records and artifacts used
in these checks were synthetic. No customer infrastructure or platform account
was accessed.

| Check | Observed result | Boundary |
| --- | --- | --- |
| Python unit and real local HTTP tests | 31 discovered: 28 passed, 3 Docker lab tests skipped | Docker is unavailable locally; skips are not passes |
| Installed CLI/setup smoke | Passed | User-local executable directory added to PATH for the check |
| Original dashboard browser acceptance | Passed desktop/mobile, approvals, recovery display, no replay, report download and session checks | Simulated Docker with real browser/HTTP/SQLite |
| Freelance browser acceptance | Passed all nine roles, separate approvals, ZIP download, no horizontal mobile overflow or JavaScript errors | Existing image is a placeholder; no image pull or deployment |
| Visual review | Reviewed synthetic desktop and mobile screenshots | Desktop screenshot is included in the setup guide |
| Python, shell and both dashboard JavaScript syntax checks | Passed | Syntax checks do not establish runtime correctness |
| Workflow structure and credential boundaries | Passed: 23 nodes, nine roles, separate owner credential | Structural assertions only |
| Actual n8n 2.44.6 CLI import | Successfully imported the workflow in a disposable local instance | Forms, HTTP nodes, credentials and file responses have not been exercised together in n8n |

The local browser used Chromium 153.0.8010.0 via the optional
`OPS_PILOT_CHROMIUM` executable setting. CI uses its installed Playwright Chromium
without that override. Docker and systemd integration checks remain separate CI
jobs; consult the pull request's actual check results before relying on them.

## Remaining setup and limits

- Configure three credentials and import the workflow into the owner's n8n.
- Exercise all five form routes there before using the n8n integration for work.
- No AI provider, job-platform discovery, messages, bidding, customer deployment
  or payment processing is connected. The worker generates Docker starter files.
- The reviewer performs static checks. Runtime validation and customer acceptance
  remain unverified in generated metadata.
- No credit reduction or business earnings were measured or promised.

See [FREELANCE.md](FREELANCE.md) for setup and the supported boundaries.
