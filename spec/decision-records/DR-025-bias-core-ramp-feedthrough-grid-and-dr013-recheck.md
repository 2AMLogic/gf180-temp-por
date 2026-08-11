# DR-025: `bias_core`'s ramp-rate feedthrough coefficient is a measured, corner/direction-dependent surface — re-testing DR-013's arithmetic check

- **Status**: proposed
- **Date**: 2026-08-11
- **Decided by**: Loom Builder agent, issue #208

## Context

`design/bias_core.md`'s "Ramp-rate feedthrough" note quoted a single
coefficient — **≈ 2.4 µs** times the ramp rate, sign always toward more loop
current — for how much a moving `VDD` displaces `bias_core`'s `VREF`. Issue
#208 was filed because a *different* measurement,
[`sim/por-vth/control/results.md`](../../sim/por-vth/control/results.md)
(issue #187/#218,
[DR-021](DR-021-por-hysteresis-quasi-static-scope.md)), found the same
mechanism running at **~49 µs** — ~20× the quoted figure — at `ss`/-40 °C on
the full four-cell assembly. Neither measurement disputed the other's
corner; nothing had swept the coefficient across the grid to see how it
moves between them, or checked whether the single figure was wrong more
broadly than just at one cold/slow corner.

Separately, [DR-013](DR-013-por-brownout-spurious-assert.md) used the
≈2.4 µs figure to test whether ramp-rate feedthrough could explain an
intermediate falling-slew band asserting `POR_RAW` above `VPOR-uparrow,max`
(issue #61). At `tt`/27 °C/3.30 V it predicted 5.5–18.4 mV of `VREF` offset
against a measured 81–467 mV — one to two orders of magnitude short — and in
the **wrong direction** relative to the static divider algebra (a depressed
`VREF` should predict a *lower* assert threshold, not the measured higher
one). DR-013 concluded the coefficient does not explain the effect and left
the true mechanism **unidentified**.

## Measurement

[`sim/bias-core-designer-check/control/run_ramp_feedthrough.py`](../../sim/bias-core-designer-check/control/run_ramp_feedthrough.py)
measures `dVREF/d(dVDD/dt)` directly on `bias_core` alone — diode-loaded
`IBIAS`, open `VREF`, no `por_comparator`/output-chain downstream — rather
than inferring it from a downstream POR threshold. A triangle-wave rail (0 →
2.0 V pre-ramp, quasi-static ramp to `vdd_val`, hold, quasi-static ramp back
down — the same shape `sim/por-vth/control/rate_ladder.spice` uses) at two
`tramp` values chosen to reproduce that control's own two end rungs at
`vdd_val` = 3.63 V (4 ms → 407.5 V/s, 16 ms → 101.9 V/s), across the full
81-point PVT grid, on both the schematic and extracted netlists — 324
ngspice runs, ~70 s wall time at `-j 8`. Full results:
[`sim/bias-core-designer-check/control/ramp_feedthrough_results.md`](../../sim/bias-core-designer-check/control/ramp_feedthrough_results.md).

**Cross-check.** At the one point the two controls share (`ss`/-40 °C/3.63 V,
407.5/101.9 V/s), this control reads 46.6/-51.1 µs (schematic) and
46.5/-51.3 µs (extracted) up/down — within ~1 µs of `sim/por-vth/control/`'s
independently-measured ~49 µs, two different methodologies (standalone cell
vs. full assembly) agreeing at the one corner both cover.

**The single ≈2.4 µs figure undershoots the measured coefficient at every
corner in the grid, not only `ss`/-40 °C:**

| | Up-ramp (`VREF` high) | Down-ramp (`VREF` low) |
| --- | --- | --- |
| Schematic | 17.31…47.45 µs | 17.54…51.08 µs |
| Extracted | 17.31…47.40 µs | 17.59…51.27 µs |

The best corner (`ff`/125 °C) is still ~7× the quoted figure; the worst
(`ss`/-40 °C) is ~20×. **The coefficient's sign reverses with ramp
direction** — toward more loop current (`VREF` high) rising, toward less
(`VREF` low) falling — rather than "always toward more loop current" as the
note previously stated on the strength of a rising-ramp-only check
(`err_at_relv_mv`).

## Re-testing DR-013's arithmetic check

DR-013's check applied the single, rising-edge-sign ≈2.4 µs figure to a
falling event at `tt`/27 °C/3.30 V. The corner- and direction-matched value
this record measures at that exact point (schematic) is **-30.7 µs**, not
+2.4 µs:

| falling slew | DR-013's ≈2.4 µs prediction | this record's -30.7 µs prediction | DR-013's own measurement |
| ---: | ---: | ---: | ---: |
| 7.67 mV/µs | +18.4 mV | **-235.4 mV** | **-467 mV** |
| 2.30 mV/µs | +5.5 mV | **-70.6 mV** | **-81 mV** |

The corner/direction-matched coefficient closes to within a factor of ~2 at
the faster rate and within 13 % at the slower one — not one to two orders of
magnitude off — and now carries the **same sign** as the measurement (`VREF`
depressed on both sides) instead of the opposite one.

**This resolves two of DR-013's three objections** ("wrong order of
magnitude" and "wrong sign of the `VREF` offset itself") but **not the
third**. DR-013's separate paradox stands: `design/por_comparator.md`'s
static `VPOR-downarrow = VREF · (RTOP+RBOT+RHYS)/(RBOT+RHYS)` algebra says a
depressed `VREF` should produce a *lower* assert threshold, yet the assert
rail measures *above* `VPOR-uparrow,max`. Nothing in this record's
measurement of `bias_core`'s own feedthrough term touches that — it is a
property of the comparator/divider's dynamic response during a fast dip, a
different sub-circuit's behaviour, and it remains genuinely unidentified.

The residual factor-of-~2 gap at the faster (7.67 mV/µs) branch is
consistent with that branch sitting closer to the large-signal, slew-limited
regime this record's own methodology deliberately avoids (it uses rates in
the 12.7–407.5 V/s = 0.0127–0.4075 mV/µs range, two to three orders below
DR-013's 770–7670 V/s = 0.77–7.67 mV/µs falling-slew band, and well below
`design/bias_core.md`'s documented ~21 mV/µs `PG`-slew-off boundary) plus the
event itself being a dip/recovery rather than a monotonic ramp. A linear,
quasi-static coefficient calibrated on monotonic ramps is not expected to
reproduce a large-signal transient exactly; DR-013's slower branch, further
from that boundary, closes to 13 %.

## Decision

1. **`design/bias_core.md`'s "Ramp-rate feedthrough" note is updated** to
   state the coefficient as the measured surface above (both directions,
   full grid, both netlists), replacing the single ≈2.4 µs figure. The
   underlying mechanism description (Miller injection into the amplifier's
   stage-1 output, `(Cc/gm1)·dVDD/dt`) is unchanged — only the coefficient's
   value and the "always toward more loop current" sign claim were wrong.
2. **DR-013's "mechanism unidentified" item is narrowed, not closed.** The
   feedthrough-coefficient hypothesis, corner- and direction-matched, is now
   a *major* component of the observed `VREF` displacement — quantitatively
   close at the slower confirmed-spurious rate and within a factor of ~2 at
   the faster one, with the correct sign at both. The comparator/divider's
   own dynamic sign paradox (depressed `VREF` predicting a *lower* threshold
   yet measuring a *higher* assert rail) is untouched by this record and
   remains open — a distinct mechanism in a different sub-circuit, not ruled
   in or out here.
3. **`sim/bias-core-designer-check/testbench/tb.json` and
   `testbench-postlayout/tb.json`'s `err_at_relv_mv` check descriptions are
   corrected** to cite the measured surface instead of the single ≈2.4 µs
   estimate they previously quoted (prose only; the check's numeric bound is
   unchanged).
4. **No spec value in `spec/target-spec.md` changes.** This is
   characterisation and a re-test of existing arithmetic; any resulting
   design change (e.g. stiffening `bias_core` against a moving rail) is out
   of scope here, per issue #208's own acceptance criteria, and is a
   follow-up decision.

## Alternatives considered

- **Treat DR-013 as fully resolved** — not chosen. The corner/direction-match
  closes the magnitude and sign of the `VREF` displacement itself, but
  DR-013's assert-threshold-sign paradox is a claim about a *different*
  sub-circuit's (the comparator/divider's) dynamic behaviour that this
  record's `bias_core`-alone measurement cannot speak to either way. Calling
  it closed would overstate what was measured.
- **Edit DR-013 in place** — not chosen; `spec/decision-records/`'s own
  convention (and `sim/README.md`'s append-only evidence rule this record's
  measurement follows) is to supersede via a new record rather than rewrite
  a decided one, so DR-013's original — now-corrected — arithmetic stays on
  the record as filed.
- **Run the full DR-013 falling-slew band (770–7670 V/s) directly on
  `bias_core` alone, rather than reasoning from the linear coefficient** —
  future work, not this record. That would need a dip/recovery stimulus
  matching `sim/por-brownout-spurious/`'s profile rather than this record's
  monotonic quasi-static ramp, and is the natural next step for closing the
  residual factor-of-~2 gap at the faster branch — noted as follow-up scope,
  not taken up here.

## Consequences

- `design/bias_core.md`'s "Ramp-rate feedthrough" section and its "An
  intermediate falling-slew band with a different symptom (#61)" subsection
  both cite the measured surface and this record instead of the single
  ≈2.4 µs figure.
- `#14`'s ramp-rate/release-timing work now has a corner-dependent
  coefficient to predict against, rather than one number that undershot by
  7–20× depending on corner.
- The comparator/divider's dynamic sign paradox DR-013 raised remains a
  genuinely open item — a candidate follow-up issue, not resolved by this
  record.
