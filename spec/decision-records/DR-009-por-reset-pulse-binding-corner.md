# DR-009: Correct two POR rows' binding-corner parentheticals to the measured full-grid minima

- **Status**: ratified
- **Date**: 2026-08-01
- **Decided by**: Loom Builder agent, issue #39 (filed during review of #38,
  closes #12)

## Context

DR-007's table (ratified by DR-008) named a binding corner for every row as a
*prediction* — a corner reasoned from the topology's generic behaviour, ahead
of any full-grid simulation. Two of those predictions did not survive #38's
measured data:

- [`por-reset-pulse`](../target-spec.md#por-reset-pulse) stated the ≥1 ms
  minimum "binds at the fastest-timer corner: FF / +125 °C / 3.63 V (highest
  bias current, lowest capacitance)". That reasoning holds for a *generic*
  current-starved one-shot with a **fixed** trip voltage. The one-shot that
  `design/por_output_chain.md` actually implements (PR #38) does not have a
  fixed trip: its timer node `TIM` is compared against `VDD − V_sg(2.5 nA)`
  — i.e. the pull-up trip is set by how far below the *rail* the PMOS can
  still source 2.5 nA, not by an absolute voltage. A cold, low rail shortens
  that ramp on two counts at once (lower starting headroom, and `V_sg` rising
  at cold), rather than the hot/high-bias corner the fixed-trip reasoning
  named. Measured over the full 81-point grid in
  `sim/por-output-chain-pulse/records/20260801-031819-fce635f.md`:
  `tpulse_1x_ms` minimum is **4.21535 ms at `ff_-40c_2.97v`**, while the
  previously-named corner `ff_125c_3.63v` reads 6.44129 ms — not even close
  to the grid minimum.
- [`por-reset-valid-floor`](../target-spec.md#por-reset-valid-floor) stated
  the row "binds at FF / +125 °C ... with an SS / −40 °C cross-check", as a
  single sentence that did not distinguish which sub-quantity binds where.
  Measured in `sim/por-output-chain-floor/records/20260801-032940-d59d7c4.md`,
  the two sub-quantities split cleanly: `floor_ratio_porlow` (the floor
  relative to VDD) maxes at **0.548 % at `sf_125c_2.97v`** — SF, not FF, at
  hot — while `floor_mv_porlow` (the absolute floor in mV) maxes at
  **1.699 mV at `ss_-40c_2.97v`**, confirming the cold/SS half of the
  original sentence but not its hot/FF half.

Neither row's actual spec *value* is in question — the ≥1 ms minimum and the
0 V / ≤0.4 V floor target are met with margin at all 81 points in both
records (`Overall: PASS`). This is a correction to a row's *binding-corner
parenthetical*, not a re-cost of the target itself, and per CLAUDE.md
("agents do not relax the ratified spec to make results pass") no value is
being relaxed here — nothing was failing.

## Decision

Amend the binding-corner text of two rows in `spec/target-spec.md`, values
unchanged:

1. **`por-reset-pulse`**: binding corner corrected from `FF / +125 °C /
   3.63 V` to the measured **`FF / −40 °C / 2.97 V`**, with the rationale
   that this one-shot's trip is rail-referenced
   (`TIM = VDD − V_sg(2.5 nA)`), not fixed, so a cold low rail — not a hot
   high-bias one — produces the shortest ramp. Cited evidence:
   `sim/por-output-chain-pulse/records/20260801-031819-fce635f.md`.
2. **`por-reset-valid-floor`**: binding-corner note rewritten to state the
   split explicitly — **the ratio binds at `SF / +125 °C`** (0.548 % at
   `sf_125c_2.97v`) and **the absolute floor binds at `SS / −40 °C`**
   (1.699 mV at `ss_-40c_2.97v`) — rather than a single sentence that
   conflated the two. Cited evidence:
   `sim/por-output-chain-floor/records/20260801-032940-d59d7c4.md`.

A general note is also added to the table's "How to read this table" §
stating that binding-corner parentheticals are predictions until a `sim/`
record measures the full grid, and that a corrected parenthetical is not a
spec relaxation because it does not change the row's required value.

## Alternatives considered

- **Leave the parentheticals as filed and let #14 discover the mismatch on
  its own** — rejected. #14 is chartered to build the ramp/pulse testbench
  suite directly from these rows; a parenthetical that names the wrong
  stress corner would lead #14 to anchor a targeted sweep on the wrong point
  even though the full-grid check (which #38 already runs) would still
  catch a real failure. Fixing the documentation now is cheaper than #14
  re-deriving the same correction independently.
- **Delete the binding-corner column/text entirely rather than correct it**
  — rejected. The column is genuinely useful (it is where later,
  narrower-than-full-grid checks should focus), and the failure mode here is
  a wrong prediction, not that the concept is useless. DR-007 itself argues
  every row should name one; removing it would be a bigger structural change
  than this issue's scope.
- **Re-cost the ≥1 ms or 0 V/≤0.4 V *values*** — not applicable. Both
  records show `Overall: PASS` at every one of the 81 points; there is
  nothing to re-cost.

## Consequences

- **#14's ramp/pulse testbench suite** should treat `FF / −40 °C / 2.97 V`
  as the stress point for `por-reset-pulse`'s minimum, and should check both
  `SF / +125 °C` (ratio) and `SS / −40 °C` (absolute) for
  `por-reset-valid-floor`, rather than the previously-named FF/hot corners.
- **No design work is invalidated.** `design/por_output_chain.md` (#38) and
  the two cited `sim/` records already measured the full grid; this record
  only corrects the spec table's prose to match evidence that already
  exists and already passes.
- **General note added to the table's how-to-read section**: future rows'
  binding-corner text should be read as a prediction, upgraded to measured
  fact only once a `sim/` record exists for that row and a full-grid sweep
  has run — this is a documentation practice, not a new spec obligation on
  any row.
