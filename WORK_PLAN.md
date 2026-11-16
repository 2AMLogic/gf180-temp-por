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
- **#453**: temp-accuracy-mc: re-run Monte Carlo and klt yield grade on revised temp_core (#415 step 3/3)
- **#516**: MOS source/drain and guard-ring COMP are drawn with no Nplus/Pplus implant (DF.12, all six cells)

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#452**: temp_core: implement amplifier chop/auto-zero, gain mirror fix and trim re-balance (#415 step 2/3)
- **#500**: Dedupe the golden-netlist read and the MiM-cap test block in layout/tests/test_lvs_reference.py
- **#505**: Three independent implementations of one Via1-with-landing-pads primitive in layout/build_cells.py
- **#506**: _m2_h/_m2_v re-derive _cap_wire's straight-wire branches — the wire counterpart to #505's via drift
- **#510**: LVS net and pin counts quoted in prose drifted from the committed lvs.json reports
- **#517**: Poly resistors draw SAB coincident with Poly2: zero extension where SB.10 requires 0.22 um
- **#521**: Move run_mc.py's four byte-identical argparse flags into cliutil, and stop hardcoding the timeout default
- **#531**: Via3/Via4 are drawn at VIA_SIDE_UM, a constant whose own comment cites only DRM V1.1/V2.1
- **#533**: Regenerate the three deglitch control files against the star extraction: one script is broken, two files' numbers (and one verdict) moved
- **#543**: signoff: the grader-pin warning reads as a blocker, so drift-only failures get deferred to CI
- **#546**: Control-script argv contract is pinned by hand-maintained lists, so script #21 is uncovered by construction

## In Progress

Issues currently being built (`loom:building`).

- **#502**: Remove four dead arguments threaded into control-script deck composers and job tuples
- **#516**: MOS source/drain and guard-ring COMP are drawn with no Nplus/Pplus implant (DF.12, all six cells)
- **#518**: temp_core resistor tile: neighbouring SAB markers 0.2 um apart where SB.2 requires 0.42 um
- **#525**: Remove three dead report.py imports from sim/harness/mc_report.py, and the docstring claim they fossilise

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#541**: refactor(layout): delegate _m2_h/_m2_v to _cap_wire, the one fixed-width-wire primitive
- **#554**: refactor: drop four dead arguments from control deck composers and job tuples

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#457**: feat(temp_core): chop the amplifier, widen the gain mirror, halve the trim ladder (DR-031)
- **#498**: feat(signoff): forbid hand-written T1 verdict counts in prose
- **#539**: refactor(sim): drop dead report.py imports from mc_report and correct its reuse docstring
- **#544**: control scripts: drop arguments their workers never read

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
- **#508**: run_dwell_sweep.py's dwell_results.md carries no `- git:` provenance line (the fleet-scale fourth of the deglitch control set) *(curated)*
- **#510**: LVS net and pin counts quoted in prose drifted from the committed lvs.json reports *(curated)*
- **#516**: MOS source/drain and guard-ring COMP are drawn with no Nplus/Pplus implant (DF.12, all six cells) *(curated)*
- **#517**: Poly resistors draw SAB coincident with Poly2: zero extension where SB.10 requires 0.22 um *(curated)*
- **#518**: temp_core resistor tile: neighbouring SAB markers 0.2 um apart where SB.2 requires 0.42 um *(curated)*
- **#519**: temp_core PNP array: centre emitter 30 um from the Nwell tap ring where DF.13_LV allows 20 um *(curated)*
- **#528**: signoff/README.md cites a tier-report.json 'blocking_item' field that does not exist, next to a hand-written 'first unmet item is now 5' *(curated)*
- **#531**: Via3/Via4 are drawn at VIA_SIDE_UM, a constant whose own comment cites only DRM V1.1/V2.1 *(curated)*
- **#533**: Regenerate the three deglitch control files against the star extraction: one script is broken, two files' numbers (and one verdict) moved *(curated)*
- **#543**: signoff: the grader-pin warning reads as a blocker, so drift-only failures get deferred to CI *(curated)*
- **#546**: Control-script argv contract is pinned by hand-maintained lists, so script #21 is uncovered by construction *(curated)*
- **#550**: test_por_vth_control_fragment_sync asserts card-identity over a directory glob, which sim/README.md:291 permits to be false *(curated)*
- **#553**: Guard the manufacturing-grid invariant end-to-end: assert every committed GDS vertex is on-grid *(curated)*

## Proposed (Architect / Hermit)

- **#470**: Give run_por_edge_check.py its own results file: remove the §7 splice into net_attribution_results.md *(hermit)*
- **#474**: Remove tolerated pre-pin card shapes from layout/postlayout.py's extracted-netlist reader *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 1 |
| Important | 5 |
| Ready (`loom:issue`) | 11 |
| In Progress (`loom:building`) | 4 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 4 |
| Curated | 24 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
