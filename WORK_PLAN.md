# Work Plan

Current workflow state, maintained by Guide.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#336**: Live batch-fleet verification of a control grid via klt_batch (blocked: fleet runner klt 0.5.0 vs client 0.6.0)
- **#400**: Bump klayout-tools pin 0.6.0, 0.7.0 → 0.8.0

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

_None._

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#321**: run_net_attribution.py's 60-deck grid has no off-host execution path, so the post-#314 re-run cannot be taken from a dispatch worker
- **#324**: Regenerate the deglitch dwell sweep against the star extraction: the post-layout slowest crossing moved from 20.77 to 22.34 µs
- **#331**: sim/harness/runner.py: batch (klt sim) execution path so control grids can run off dispatch workers (mechanism question from #321)
- **#384**: T1 item 6 (Monte Carlo): klt yield reports for temp-accuracy-mc and por-threshold-mc
- **#386**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers), items 5–7
- **#388**: T1 item 5 phase 2: klt sim envelope with per-row limits over the 81-point grid, piloted on por-vth
- **#400**: Bump klayout-tools pin 0.6.0, 0.7.0 → 0.8.0

## Proposed (Architect / Hermit)

- **#353**: CI: mechanically enforce the append-only rule for sim/ evidence records *(architect)*
- **#409**: Remove layout/postlayout_smoke.py and SMOKE.md: superseded by full-PVT post-layout re-runs *(hermit)*
- **#411**: Remove the unused cell-freeze mechanism (FROZEN_CELLS is empty; its tests skip) *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 2 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 0 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 0 |
| Curated | 7 |
| Architect / Hermit proposals | 3 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
