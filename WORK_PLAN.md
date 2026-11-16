# Work Plan

Current workflow state, maintained by Guide.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#457**: feat(temp_core): chop the amplifier, widen the gain mirror, halve the trim ladder (DR-031)
- **#560**: fix: correct drifted LVS prose counts and police them against committed reports

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#336**: Live batch-fleet verification of a control grid via klt_batch (blocked: fleet runner klt 0.5.0 vs client 0.6.0)

## Important

`loom:important`; taken before unlabelled work.

- **#388**: T1 item 5 phase 2: klt sim envelope with per-row limits over the 81-point grid, piloted on por-vth
- **#400**: Bump klayout-tools pin 0.6.0, 0.7.0 → 0.8.0
- **#452**: temp_core: implement amplifier chop/auto-zero, gain mirror fix and trim re-balance (#415 step 2/3)
- **#453**: temp-accuracy-mc: re-run Monte Carlo and klt yield grade on revised temp_core (#415 step 3/3)

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#452**: temp_core: implement amplifier chop/auto-zero, gain mirror fix and trim re-balance (#415 step 2/3)
- **#518**: temp_core resistor tile: neighbouring SAB markers 0.2 um apart where SB.2 requires 0.42 um
- **#527**: signoff/tests/test_check.py: ProseCountTest sits after the __main__ guard, so direct execution reports OK on 39 of 57 tests
- **#528**: signoff/README.md cites a tier-report.json 'blocking_item' field that does not exist, next to a hand-written 'first unmet item is now 5'
- **#532**: temp_core and por_comparator_bias_okb_inv have no substrate or well tap within 20 um of their MOS rows (DF.13_LV / DF.14_LV)
- **#538**: lvs_reference: the declared-net-set derivation is now spelled out twice, and the guard's message omits bjt_well
- **#543**: signoff: the grader-pin warning reads as a blocker, so drift-only failures get deferred to CI
- **#546**: Control-script argv contract is pinned by hand-maintained lists, so script #21 is uncovered by construction
- **#550**: test_por_vth_control_fragment_sync asserts card-identity over a directory glob, which sim/README.md:291 permits to be false
- **#553**: Guard the manufacturing-grid invariant end-to-end: assert every committed GDS vertex is on-grid
- **#555**: sim/selftest.sh PVT smoke fails on PDK-equipped hosts: grid spread checks read n/a
- **#558**: A third straight-Metal2-wire site still re-derives _cap_wire inline: the divider trunk in build_cells.py
- **#563**: run_glitch_width_sweep.py's docstring cites a pre-star record figure without naming the generation
- **#565**: Remove hand-typed T1_ITEM_COUNT from signoff/check.py: read it from tier-report.json
- **#568**: SAB-overhang invariant from #517 is thinner than its own comments claim: no SB.2 assert in _resistor_string(), a duplicated grid literal, and no unit test
- **#569**: Remove the inline guard-ring copy in por_comparator: reuse _draw_guard_ring
- **#573**: ci: the GDS staleness chain is gated only at its last link — neither postlayout.py --check nor build_cells.py --check runs in CI

## In Progress

Issues currently being built (`loom:building`).

- **#510**: LVS net and pin counts quoted in prose drifted from the committed lvs.json reports

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#457**: feat(temp_core): chop the amplifier, widen the gain mirror, halve the trim ladder (DR-031)
- **#560**: fix: correct drifted LVS prose counts and police them against committed reports

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
- **#508**: run_dwell_sweep.py's dwell_results.md carries no `- git:` provenance line (the fleet-scale fourth of the deglitch control set) *(curated)*
- **#510**: LVS net and pin counts quoted in prose drifted from the committed lvs.json reports *(curated)*
- **#518**: temp_core resistor tile: neighbouring SAB markers 0.2 um apart where SB.2 requires 0.42 um *(curated)*
- **#527**: signoff/tests/test_check.py: ProseCountTest sits after the __main__ guard, so direct execution reports OK on 39 of 57 tests *(curated)*
- **#528**: signoff/README.md cites a tier-report.json 'blocking_item' field that does not exist, next to a hand-written 'first unmet item is now 5' *(curated)*
- **#532**: temp_core and por_comparator_bias_okb_inv have no substrate or well tap within 20 um of their MOS rows (DF.13_LV / DF.14_LV) *(curated)*
- **#538**: lvs_reference: the declared-net-set derivation is now spelled out twice, and the guard's message omits bjt_well *(curated)*
- **#543**: signoff: the grader-pin warning reads as a blocker, so drift-only failures get deferred to CI *(curated)*
- **#546**: Control-script argv contract is pinned by hand-maintained lists, so script #21 is uncovered by construction *(curated)*
- **#550**: test_por_vth_control_fragment_sync asserts card-identity over a directory glob, which sim/README.md:291 permits to be false *(curated)*
- **#553**: Guard the manufacturing-grid invariant end-to-end: assert every committed GDS vertex is on-grid *(curated)*
- **#555**: sim/selftest.sh PVT smoke fails on PDK-equipped hosts: grid spread checks read n/a *(curated)*
- **#558**: A third straight-Metal2-wire site still re-derives _cap_wire inline: the divider trunk in build_cells.py *(curated)*
- **#563**: run_glitch_width_sweep.py's docstring cites a pre-star record figure without naming the generation *(curated)*
- **#568**: SAB-overhang invariant from #517 is thinner than its own comments claim: no SB.2 assert in _resistor_string(), a duplicated grid literal, and no unit test *(curated)*
- **#573**: ci: the GDS staleness chain is gated only at its last link — neither postlayout.py --check nor build_cells.py --check runs in CI *(curated)*

## Proposed (Architect / Hermit)

- **#470**: Give run_por_edge_check.py its own results file: remove the §7 splice into net_attribution_results.md *(hermit)*
- **#474**: Remove tolerated pre-pin card shapes from layout/postlayout.py's extracted-netlist reader *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 2 |
| Very important | 1 |
| Important | 4 |
| Ready (`loom:issue`) | 17 |
| In Progress (`loom:building`) | 1 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 2 |
| Curated | 26 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
