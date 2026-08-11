# DR-018: `por-hysteresis` is a quasi-static row — 45 % of the full-assembly deck's 261 mV reading is ramp-rate displacement, not hysteresis

- **Status**: proposed
- **Date**: 2026-08-11
- **Decided by**: Loom Builder agent, issue #187
- **Scopes**: [`por-hysteresis`](../target-spec.md#por-hysteresis). Ratified
  values unchanged.

## Context

`sim/por-vth/`'s post-layout record
[`20260811-073945-12473c3`](../../sim/por-vth/records/20260811-073945-12473c3.md)
is **80/81 PASS**: `v_hys_mv` measures **261.092 mV** at `ss_-40c_3.63v`,
11.1 mV over the ratified 250 mV ceiling. Its schematic-level predecessor
[`20260801-233802-32fbaa0`](../../sim/por-vth/records/20260801-233802-32fbaa0.md)
measures 248.740 mV at the same point — inside, by 1.26 mV. Issue #187 asks
which of two things that +12.35 mV is: a genuine design-margin problem in the
divider ratio, or the divider's drawn interconnect R/C.

**It is neither.** `sim/por-vth/control/run_ramp_rate_probe.py` (results:
[`sim/por-vth/control/results.md`](../../sim/por-vth/control/results.md))
re-measures that corner across a six-step ramp-rate ladder on both netlists,
and separately probes each of the comparator's two inputs against the value a
static rail would put it at. Three findings:

1. **The parent deck's supply axis is also a ramp-rate axis.** It traverses
   `vdd_val − 2.0 V` in a fixed 4 ms, so `dVDD/dt` is **242.5 / 325 /
   407.5 V/s** at 2.97 / 3.30 / 3.63 V — a 1.68× spread that no measurement in
   that grid can separate from the supply. Re-run with the *rate* held at
   242.5 V/s instead, the same corner's `V_hys` goes 211.4 / 215.7 /
   215.7 mV across the whole ±10 % window (spread 4.3 mV, against 49.7 mV in
   the parent record), and `VPOR↑` is identical at all three supplies.
2. **`V_hys` is proportional to the ramp rate, and its static limit is
   mid-window.** Extracted netlist, same corner: 261.092 mV at 407.5 V/s →
   204.717 → 175.069 → 159.497 → 151.450 → **147.354 mV at 12.7 V/s**,
   extrapolating to **143.3 mV** on a static rail. The schematic netlist
   extrapolates to **143.3 mV** as well. Independently, the cell-level record
   [`20260811-073514-eb36e2c`](../../sim/por-comparator-designer-check/records/20260811-073514-eb36e2c.md)'s
   own supply trend at this corner (154.778 / 156.019 / 157.249 mV at 297 /
   330 / 363 V/s — that deck's supply axis is a rate axis too) extrapolates to
   **143.7 mV**. Three routes, same number.
3. **What moves is `bias_core`'s reference, not the divider.** Sampled at a
   fixed rail voltage clear of both thresholds, at the parent deck's own rate:
   `VREF` sits **+19.0 mV** above its settled value on the up-ramp and
   **−20.8 mV** below it on the down-ramp, while the sense divider's tap is
   within **1.9 mV** of the static value its drawn resistor lengths give. The
   displacement is proportional to the rate through the origin (≈49 µs of
   equivalent time constant), reverses sign with ramp direction, and is
   present on the down-ramp several ms after the deck's own
   `vref_settle_drift_mv` guard reads zero — so it is a *displacement by* the
   moving rail, not a reference that has not settled. Referred out through the
   divider's ~2.1× ratio it accounts for **97.7 mV** of the 261.092 mV
   reading.

Decomposing the reading at `ss_-40c_3.63v` / 407.5 V/s on the extracted
netlist:

| Term | Schematic | Extracted | Δ |
|---|---:|---:|---:|
| **Total measured `V_hys`** | 248.741 mV | 261.092 mV | **+12.351 mV** |
| Static `V_hys` (zero-rate limit) — *the quantity this row bounds* | 143.300 mV | 143.258 mV | −0.042 mV |
| Rate excess at the comparator's input (`VREF` displacement × divider ratio) | 97.423 mV | 97.708 mV | +0.285 mV |
| Rate excess, comparator + output chain | 8.018 mV | 20.126 mV | **+12.108 mV** |

So **55 % of the reading is hysteresis, 37 % is reference displacement and
8 % is comparator/output-chain delay**, and the regression the issue reports
is, to 98 %, the last of those three: the extraction's interconnect
capacitance on the comparator's own internal nodes (`xcmp__VDDA`, `NA`,
`CMPO`, `N1`, `TN`, `NBG` — 13.6–21.3 fF each) slowing it down while the rail
keeps moving. The divider's drawn parasitics (25.9 fF on `SNS`, 17.5 fF on
`SNSB`, ~0.15 µs against its ~5.9 MΩ source) are three orders of magnitude too
small to be the mechanism, and the divider ratio's own static hysteresis is
unchanged by the extraction to within 0.05 mV.

## Decision

1. **The ratified `por-hysteresis` window is unchanged: 100 / 150 / 250 mV.**
   No value is re-cost. Nothing measured requires it: the quantity the row
   bounds measures 143.3 mV, mid-window, on the drawn-and-extracted netlist.
2. **`por-hysteresis` is scoped as a quasi-static row.** `V_hys` is the
   difference the *divider ratio* implements, on a rail slow enough that
   `bias_core`'s reference is not being displaced by the ramp. On a moving
   rail the measured value is
   `V_hys(dVDD/dt) ≈ V_hys,static + k · dVDD/dt`, with **k = 0.32 mV per (V/s)
   measured at the binding corner** (`ss`/−40 °C, extracted; 0.27 on the
   schematic). This mirrors the caveat convention
   [DR-013](DR-013-por-brownout-spurious-assert.md) already established on the
   same row and on [`por-vth-fall`](../target-spec.md#por-vth-fall).
3. **The `ss_-40c_3.63v` excursion in record `20260811-073945-12473c3` is
   ratified as a measured, understood, rate-scoped excursion — not a design
   defect and not a spec relaxation.** The record stands, overall FAIL and
   all, as append-only evidence of what the block does at 407.5 V/s.
4. **No re-ratio of `RTOP`/`RBOT`/`RHYS`, and no change to
   `design/por_comparator.sch`.** See Alternatives.
5. **The ceiling's own stated rationale is independently satisfied and
   separately checked.** `target-spec.md` §4.1 derives the 250 mV maximum as
   "the largest value that keeps `VPOR↓,min` at 2.22 V". On the same
   post-layout grid [`por-vth-fall`](../target-spec.md#por-vth-fall) passes
   **81/81** with `VPOR↓,min = 2.37928 V` — **159 mV above the 2.22 V floor**,
   and that floor is the binding physical constraint of which the 250 mV
   ceiling is a derived `[P]` proxy. The consequence the ceiling exists to
   prevent does not occur at any point of the grid.
6. **The deck's supply/ramp-rate confound is a testbench defect and is routed,
   not fixed here** — see Consequences. This record deliberately changes no
   testbench, so the two parent records stay comparable and no reader has to
   wonder whether the deck was altered until it passed.

## Alternatives considered

- **Re-ratio the divider (the issue's own suggested fix).** Rejected on the
  measurement. The reading is only 55 % static, so removing the 11.1 mV of
  excursion means removing 11.1 mV of *static* hysteresis — taking it from
  143.3 mV to ~132 mV, off the ratified 150 mV typ and toward the 100 mV floor
  that exists to guarantee chatter rejection, in exchange for margin against a
  term that is not hysteresis. And it does not hold: the same 1.68× of ramp
  rate that the parent deck's own supply axis spans would put the re-ratioed
  divider back over the ceiling. Spending a real margin to buy a nominal one
  is the wrong trade.
- **Re-cost the 250 mV ceiling.** Rejected. CLAUDE.md is explicit that agents
  do not relax the ratified spec to make results pass, and here there is not
  even a case for it on the merits: the quantity the ceiling bounds is
  mid-window, and the floor the ceiling protects has 159 mV of margin.
- **Speed the comparator up** (raise the 25 nA tail, or resize the output
  inverters) to shrink the 20.1 mV comparator/output-chain term. Rejected.
  It buys the smallest of the three terms with the scarcest budget in the
  block: [`por-iq`](../target-spec.md#por-iq) has 208 nA of headroom at its
  binding corner and `design/bias_core.md` already records a shortfall against
  it. No ratified row asks for a faster comparator — [`por-ramp-rate`](../target-spec.md#por-ramp-rate)
  passes 81/81 at all four rates including the 1 V/µs fast limit.
- **Stiffen `VREF` against a ramping rail**, which is the *largest* of the
  three terms. Not rejected on the merits — but it is `bias_core`'s design
  (#11), not this cell's, it is a term this row is now explicitly scoped to
  exclude, and no ratified row currently binds on it. Routed rather than
  taken; see Consequences.
- **Re-cut `sim/por-vth/` at a rate-matched, genuinely quasi-static ramp and
  mint new records.** Not taken *in this record*. It is the right fix for the
  deck, but it changes the evidence base of three spec rows at once and it
  would be filed under this record's own conclusion — better reviewed on its
  own merits, against this record's already-committed reasoning, than folded
  into the record that argues for it.

## Consequences

- **`sim/por-vth/`'s post-layout record stays overall FAIL**, and the
  `por-hysteresis` row now says why rather than flagging it. That is the
  precedent this repo already set for
  [`por-brownout`](../target-spec.md#por-brownout) (0/81, root-caused,
  ratified with rationale) rather than a new one.
- **`por-vth-rise`'s reported maximum is inflated by the same term.** The
  2.64873 V it records at `ss_-40c_3.63v` becomes **2.62809 V** at 242.5 V/s
  and 2.59652 V at 12.7 V/s — the row passes either way, and by more real
  margin than it claims. Its "max binds at SS / −40 °C" prediction is
  unaffected in direction. Nothing in that row is changed by this record.
- **`sim/por-comparator-designer-check/` and `sim/por-threshold-mc/` are
  unaffected.** Both idealise `VREF` as a fixed source, so the dominant term
  here cannot appear in them — which is exactly why they read 150.7–158.0 mV
  where the assembly reads 169–261 mV, and why #85 was right to call the
  regression full-assembly-specific.
- **Two follow-ups are routed, both out of scope here:**
  - The parent deck's fixed-*duration* ramp confounds supply with rate on
    every one of its 81 points, and its `vref_settle_drift_mv` guard cannot
    catch it (the reference is settled; it is being displaced). Re-cutting the
    deck at a fixed `dVDD/dt`, with a quasi-staticity guard on the measurand
    itself, is filed separately.
  - `design/bias_core.md`'s `VREF` ramp-feedthrough coefficient is quoted at
    ≈2.4 µs; measured here at **≈49 µs** at `ss`/−40 °C, i.e. ~20× larger at
    the slow/cold corner. That is a **lead, not a conclusion**, for
    [DR-013](DR-013-por-brownout-spurious-assert.md)'s explicitly unidentified
    spurious-assert mechanism: DR-013 ruled the 2.4 µs coefficient out because
    it predicted 5.5–18.4 mV against 81–467 mV measured, and the measured
    0.0486 mV/(V/s) over the same 770–7670 V/s band predicts 37–373 mV
    instead. Different corner set
    and a dip-shaped rather than monotonic profile, so it is filed for someone
    to test, not asserted here.
- **What this record does not license.** It scopes the row to quasi-static
  rails; it does not claim the block's dynamic behaviour is good, or that a
  fast ramp's wider effective hysteresis is harmless. The rows that own the
  dynamic axis — [`por-ramp-rate`](../target-spec.md#por-ramp-rate),
  [`por-brownout`](../target-spec.md#por-brownout) and DR-013's caveat on
  [`por-vth-fall`](../target-spec.md#por-vth-fall) — keep their own evidence
  and their own open status.
