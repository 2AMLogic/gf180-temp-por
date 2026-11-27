# Work Plan

Current workflow state, maintained by Guide.

<!-- guide:plan-body:start -->
_Generated: 2026-11-27T19:36:58Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — a human merge decision, or the prerequisite shown, is missing.

- **#615**: layout: draw the missing substrate and well taps DF.13/DF.14 need *(held: champion ratification hold)*
- **#560**: fix: correct drifted LVS prose counts and police them against committed reports *(held: champion ratification hold)*

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#336**: Live batch-fleet verification of a control grid via klt_batch (blocked: fleet runner klt 0.5.0 vs client 0.6.0) *(held)*

## Important

`loom:important`; taken before unlabelled work.

- **#388**: T1 item 5 phase 2: klt sim envelope with per-row limits over the 81-point grid, piloted on por-vth *(held)*
- **#400**: Bump klayout-tools pin 0.6.0, 0.7.0 → 0.8.0 *(held)*
- **#452**: temp_core: implement amplifier chop/auto-zero, gain mirror fix and trim re-balance (#415 step 2/3) *(held)*
- **#453**: temp-accuracy-mc: re-run Monte Carlo and klt yield grade on revised temp_core (#415 step 3/3) *(held)*

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues with an open linked PR (native admission `OPEN_PR`; listed under Issues with Open PRs).

_None._

## Issues with Open PRs (Not Dispatchable)

`loom:issue` issues an open linked PR already holds — native admission would refuse them (`OPEN_PR`); listed with the PR and its stage, not counted above.

- **#510**: LVS net and pin counts quoted in prose drifted from the committed lvs.json reports — open PR #560 (held)

## In Progress

Issues currently being built (`loom:building`).

- **#416**: POR threshold rows: N=500 cannot demonstrate the 99.73 % [3σ] yield; need a larger campaign
- **#532**: temp_core and por_comparator_bias_okb_inv have no substrate or well tap within 20 um of their MOS rows (DF.13_LV / DF.14_LV)
- **#696**: Consolidate duplicate DR-030 artifact-manifest validation onto sim/harness/evidence_store.py

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#697**: fix: validate artifact manifests before append-only installation

## Approved (Awaiting Merge)

PRs that passed review (`loom:pr`); unmarked PRs are queued for Champion auto-merge, PRs marked `*(held …)*` are not (the hold decides).

- **#615**: layout: draw the missing substrate and well taps DF.13/DF.14 need — closes #532 *(held: champion ratification hold)*
- **#560**: fix: correct drifted LVS prose counts and police them against committed reports — closes #510 *(held: champion ratification hold)*

## Proposed

Issues carrying `loom:curated`.

- **#321**: run_net_attribution.py's 60-deck grid has no off-host execution path, so the post-#314 re-run cannot be taken from a dispatch worker *(curated)* *(held)*
- **#324**: Regenerate the deglitch dwell sweep against the star extraction: the post-layout slowest crossing moved from 20.77 to 22.34 µs *(curated)* *(held)*
- **#331**: sim/harness/runner.py: batch (klt sim) execution path so control grids can run off dispatch workers (mechanism question from #321) *(curated)* *(held)*
- **#336**: Live batch-fleet verification of a control grid via klt_batch (blocked: fleet runner klt 0.5.0 vs client 0.6.0) *(curated)* *(held)*
- **#386**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers), items 5–7 *(curated)*
- **#388**: T1 item 5 phase 2: klt sim envelope with per-row limits over the 81-point grid, piloted on por-vth *(curated)* *(held)*
- **#400**: Bump klayout-tools pin 0.6.0, 0.7.0 → 0.8.0 *(curated)* *(held)*
- **#416**: POR threshold rows: N=500 cannot demonstrate the 99.73 % [3σ] yield; need a larger campaign *(curated)*
- **#417**: Item 6: sampled negative control for the Monte Carlo yield campaigns *(curated)* *(held)*
- **#452**: temp_core: implement amplifier chop/auto-zero, gain mirror fix and trim re-balance (#415 step 2/3) *(curated)* *(held)*
- **#508**: run_dwell_sweep.py's dwell_results.md carries no `- git:` provenance line (the fleet-scale fourth of the deglitch control set) *(curated)* *(held)*
- **#510**: LVS net and pin counts quoted in prose drifted from the committed lvs.json reports *(curated)*
- **#532**: temp_core and por_comparator_bias_okb_inv have no substrate or well tap within 20 um of their MOS rows (DF.13_LV / DF.14_LV) *(curated)*
- **#551**: Re-run temp_por_top PEX grid: pex.json still cites the pre-#518 GDS revision *(curated)* *(held)*

## Proposed (Architect / Hermit)

- **#633**: Drop the unused native yield dependency from headless CI *(hermit)*
- **#673**: Cite the archived brownout interpretation instead of reprinting its measurements *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 2 |
| Very important | 1 |
| Important | 4 |
| Ready (`loom:issue`, net of holds/building/open-linked-PRs) | 0 |
| In Progress (`loom:building`) | 3 |
| Held, no other bucket | 10 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 2 |
| Curated | 14 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
