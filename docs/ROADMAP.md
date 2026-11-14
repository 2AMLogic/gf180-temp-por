# Roadmap

`gf180-temp-por` is a temperature sensor plus power-on-reset pair on the open
gf180mcu PDK, built with an open-source flow and used to find and report gaps
in [klayout-tools](https://github.com/2AMLogic/klayout-tools).

Status as of 2026-11-14, `main` @ `daa202a4`. Queue state lives in
[`WORK_PLAN.md`](../WORK_PLAN.md); the verdict of record is
[`signoff/tier-report.json`](../signoff/tier-report.json), not this prose.

## Where it stands

Position on the klayout-tools T1 ("sim-validated") checklist, read from
`signoff/tier-report.json` (`klt 0.9.1`): **`tier: null`, `t1_met_count: 8` of 11.**

| # | Item | Verdict | Evidence or gap |
|---|---|---|---|
| 1 | Design sources | met | 5 schematics + 5 netlists, hash-bound (`signoff/evidence/`) |
| 2 | Layout | met | `layout/cells/temp_por_top.gds`, 4 sub-cells + top |
| 3 | DRC clean | met | `layout/reports/temp_por_top/drc.json`; skipped rules disclosed in `signoff/README.md` |
| 4 | LVS clean | met | 239/239 devices, 143/143 nets; body terminals not independently verified |
| 5 | Corner verification | unmet, `partial_coverage` | 81-point records exist as Markdown only; no `klt sim` envelope (#383, #388, #389) |
| 6 | Monte Carlo | unmet, `check_failed` | temperature rows fail yield (#415); POR rows under-sampled at N=500 (#416); no negative control (#417) |
| 7 | Post-layout | unmet, `check_failed` | `klt pex` report has 48 errored `por-brownout` rows at 8 corners; cause measured in `sim/por-brownout/control/schematic-nonreassert.md` (#405, closed) |
| 8 | Characterization report | met | `spec/target-spec.md`, 29 rows; two temperature rows recorded not met (DR-029) |
| 9 | Testbenches shipped | met | 24 `sim/` experiments inventoried |
| 10 | Repo hygiene | met | hash-bound inventory |
| 11 | Power delivery | met | `erc_supply.json`, zero findings |

- The target spec is ratified (DR-008); decisions are in `spec/decision-records/`.
- The assembled footprint is 1.059 mm² against a 0.05 mm² planning bound,
  recorded as not met and not relaxed (DR-022).
- The temperature-accuracy rows miss their `[3σ]` targets (DR-029). DR-031
  (merged, #454) chooses the fix: chop the `temp_core` amplifier, widen the
  gain mirror, halve the trim ladder. The schematic change is PR #457.
- The sim harness has a batch backend (`sim/harness/klt_batch.py`), but no
  control grid has yet been reproduced on it in enforce mode (#336).
- This is the first roadmap. The committed report has said 8, with item 7
  also unmet, since the `klt pex` extension in `72685113`. `README.md` was
  corrected to match in `d21f266e` (merged as #490); `signoff/README.md` still
  says 9 of 11 in two places, which is the drift Now item 1 below covers.

## Now

Can start today; none needs a multi-corner simulation run.

1. **Make the prose match the verdict.** `README.md` is already corrected;
   `signoff/README.md` still says 9 of 11. Done when neither document carries a
   hand-written aggregate T1 count — leaving `signoff/tier-report.json` as the
   only place the verdict is written — a `signoff/check.py` check fails if one
   reappears, and `python3 signoff/check.py` passes. **#491**
   (`loom:building`, PR #498) owns the mechanism; **#495** is the same drift,
   parked on it.
2. **Request builder with per-row limits, dry-run only.** Filed as **#496**
   (`loom:building`) — the first half of #388, which its own Dependencies line
   says can proceed without the batch backend. Done when a harness command
   emits a `klt sim` request for `por-vth` with 81 units and the three ratified
   row limits, covered by unit tests in `sim/tests/` that need neither ngspice
   nor the backend. The pilot run stays in #388.
3. **Triage the DRC result under a newer klt.** Filed as **#497**
   (`loom:issue`). #400 stopped because `layout/run_checks.sh --regen-all` on
   klt 0.8.0 turned all six committed cells from clean to violating
   (`contact.ongrid.1`, `comp.coverage.1` and others). Done when a committed
   note classifies each violated rule as a layout defect or a deck change, with
   an example location, and each deck-side finding is filed at klayout-tools.
   No pin moves.

## Next

Unblocked by a named item above or by an upstream change.

- **#336, live batch verification of a control grid.** Done when one
  enforce-mode batch run reproduces the newest local dwell-sweep record.
  Blocked on batch backend capacity: the 2026-11-05 and 2026-11-13 attempts
  were refused before any deck ran. It gates #331, #388, #389 and #417.
- **Item 5 chain: #388 pilot, then #389, then #383.** Done when every
  expressible row has a committed, passing `klt sim` envelope cited in
  `signoff/block-manifest.json`. Needs Now item 2 and #336.
- **Temperature accuracy: #452, then #453, then #458 and #459.** #452 is done
  when the four `temp_core` benches have PVT records on the DR-031 schematic;
  #453 when `klt yield` regrades `temp-accuracy-mc`. Needs PR #457 merged and
  batch capacity. #458 (layout redraw) follows only if #453 passes.
- **POR yield at N ≥ 1365 (#416).** Done when a new `por-threshold-mc` record
  and regenerated yield report exist. Blocked on
  [klayout-tools#4902](https://github.com/2AMLogic/klayout-tools/issues/4902)
  (batch backend drops derived measurements), open today.
- **Negative control (#417).** The known-bad variants are defined; done when
  sampled runs make `klt yield` report `detected`. Needs #336.
- **klt pin bump (#400).** Done when every pin moves together and DRC/LVS
  evidence is regenerated clean. Needs Now item 3.
- **Post-layout control refresh (#321, #324).** Done when both results files
  are regenerated on the star extraction. Needs #331 and #336.
- **Item 7 errored rows.** No open issue. The `por-brownout` deck's 1 µs dip
  edge is outside the row's own slew clause, so the schematic leg never
  re-asserts at eight corners. Done when a decision record states whether
  those six measurements belong in the cited report and the report is
  regenerated to match. Needs a maintainer ruling first.

## Later

Direction, each with the question to answer first.

- **Area.** What limits the layout: device sizing, routing, or cell assembly
  (the sub-cells sum to about 0.34 mm² inside a 1.059 mm² box)? DR-031 adds an
  output-filter capacitor of about 10 000 µm² (#458, item 4).
- **Cross-domain IR drop and crosstalk.** Unanswered by any record in `sim/`.
  Which extraction features (distributed route resistance, lateral coupling)
  must klayout-tools provide before the question can be put?
- **DRC and LVS coverage.** Five rules skipped, three deck layers unchecked,
  body ties unverified. Which of these can the deck cover, and which need a
  second engine?
- **5.0 V rail.** `docs/chipalooza/challenge-3-proposal.md` marks its rows
  not yet characterized at 5.0 V. Is 5.0 V operation required, given DR-001?
- **Beyond T1.** The grader reports later tiers as `tier_not_supported`, and
  `measurements/` is empty until there is silicon. What does T2 require here?

## Blocked and waiting

- **PR #457** (DR-031 schematic): approved, held for a human check of the two
  moved bench windows against DR-031, and now conflicting with `main`.
- **#470, #474:** each reverses a deliberate choice and waits on a maintainer
  decision recorded in the issue.
- **#338:** audit-host Python/klt capability; stays blocked until its runtime
  owner is identified.
- **Batch backend capacity** (#336) and **klayout-tools#4902** (#416), above.

Every item under **Next** is blocked, in progress or awaiting a decision.
Only the three Now items can start today, and each one is filed: #491 with
#495 (item 1), #496 (item 2), #497 (item 3).

## Not planned

- Relaxing or re-quoting a ratified spec row to make a result pass (CLAUDE.md).
- Growing the pair about 45x to meet temperature accuracy (#415: it breaks
  the area row).
