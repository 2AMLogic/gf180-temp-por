# Work Plan

Current workflow state, maintained by Guide.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#457**: feat(temp_core): chop the amplifier, widen the gain mirror, halve the trim ladder (DR-031)

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#336**: Live batch-fleet verification of a control grid via klt_batch (blocked: fleet runner klt 0.5.0 vs client 0.6.0)

## Important

`loom:important`; taken before unlabelled work.

- **#388**: T1 item 5 phase 2: klt sim envelope with per-row limits over the 81-point grid, piloted on por-vth
- **#400**: Bump klayout-tools pin 0.6.0, 0.7.0 → 0.8.0
- **#452**: temp_core: implement amplifier chop/auto-zero, gain mirror fix and trim re-balance (#415 step 2/3)
- **#496**: sim harness: build a klt sim request with per-row spec limits for one experiment (dry-run half of #388)
- **#497**: Classify the DRC violations the committed cells show under klt 0.8.0 and later (unblocks #400)

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#497**: Classify the DRC violations the committed cells show under klt 0.8.0 and later (unblocks #400)
- **#499**: Assert temp_core's drawn track list equals its manifest ports — the one leaf cell missing the sibling guard
- **#500**: Dedupe the golden-netlist read and the MiM-cap test block in layout/tests/test_lvs_reference.py
- **#502**: Remove four dead arguments threaded into control-script deck composers and job tuples
- **#505**: Three independent implementations of one Via1-with-landing-pads primitive in layout/build_cells.py

## In Progress

Issues currently being built (`loom:building`).

- **#452**: temp_core: implement amplifier chop/auto-zero, gain mirror fix and trim re-balance (#415 step 2/3)
- **#491**: README's T1 verdict count drifts from signoff/tier-report.json, and the docs-PR path cannot carry the fix
- **#493**: Three control-script helpers are duplicated within one experiment directory; consolidate per the _rung_record.py precedent
- **#496**: sim harness: build a klt sim request with per-row spec limits for one experiment (dry-run half of #388)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#494**: docs: roadmap as of 2026-11-13
- **#504**: feat: build klt sim requests with per-row spec limits, without submitting

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#457**: feat(temp_core): chop the amplifier, widen the gain mirror, halve the trim ladder (DR-031)
- **#501**: refactor(sim): give three duplicated control helpers one definition per directory

## Proposed

Issues carrying `loom:curated`.

- **#321**: run_net_attribution.py's 60-deck grid has no off-host execution path, so the post-#314 re-run cannot be taken from a dispatch worker *(curated)*
- **#324**: Regenerate the deglitch dwell sweep against the star extraction: the post-layout slowest crossing moved from 20.77 to 22.34 µs *(curated)*
- **#331**: sim/harness/runner.py: batch (klt sim) execution path so control grids can run off dispatch workers (mechanism question from #321) *(curated)*
- **#336**: Live batch-fleet verification of a control grid via klt_batch (blocked: fleet runner klt 0.5.0 vs client 0.6.0) *(curated)*
- **#386**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers), items 5–7 *(curated)*
- **#388**: T1 item 5 phase 2: klt sim envelope with per-row limits over the 81-point grid, piloted on por-vth *(curated)*
- **#400**: Bump klayout-tools pin 0.6.0, 0.7.0 → 0.8.0 *(curated)*
- **#416**: POR threshold rows: N=500 cannot demonstrate the 99.73 % [3σ] yield; need a larger campaign *(curated)*
- **#417**: Item 6: sampled negative control for the Monte Carlo yield campaigns *(curated)*
- **#452**: temp_core: implement amplifier chop/auto-zero, gain mirror fix and trim re-balance (#415 step 2/3) *(curated)*
- **#491**: README's T1 verdict count drifts from signoff/tier-report.json, and the docs-PR path cannot carry the fix *(curated)*
- **#496**: sim harness: build a klt sim request with per-row spec limits for one experiment (dry-run half of #388) *(curated)*
- **#497**: Classify the DRC violations the committed cells show under klt 0.8.0 and later (unblocks #400) *(curated)*
- **#499**: Assert temp_core's drawn track list equals its manifest ports — the one leaf cell missing the sibling guard *(curated)*
- **#507**: run_deglitch_asym_probe.py's results.md carries no `- git:` provenance line, unlike its five peers *(curated)*
- **#510**: LVS net and pin counts quoted in prose drifted from the committed lvs.json reports *(curated)*

## Proposed (Architect / Hermit)

- **#470**: Give run_por_edge_check.py its own results file: remove the §7 splice into net_attribution_results.md *(hermit)*
- **#474**: Remove tolerated pre-pin card shapes from layout/postlayout.py's extracted-netlist reader *(hermit)*
- **#506**: _m2_h/_m2_v re-derive _cap_wire's straight-wire branches — the wire counterpart to #505's via drift *(hermit)*
- **#509**: Remove ramp_rate_probe.spice's two dead .params, and assert the por-vth control fragments' cards agree *(hermit)*
- **#511**: Remove _TopRoutes.via1/via2's inline via-square arithmetic: the only via drawer that bypasses CellBuilder.via *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 1 |
| Important | 5 |
| Ready (`loom:issue`) | 5 |
| In Progress (`loom:building`) | 4 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 2 |
| Curated | 16 |
| Architect / Hermit proposals | 5 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
