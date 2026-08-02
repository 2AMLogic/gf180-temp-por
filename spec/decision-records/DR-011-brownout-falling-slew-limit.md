# DR-011: `por-brownout` is bounded by the rail's falling *slew rate*, not by dip depth or duration

- **Status**: proposed
- **Date**: 2026-08-02
- **Decided by**: Loom Builder agent, issue #55

## Context

`sim/por-brownout/records/20260801-233807-32fbaa0.md` measured **0/81 PASS**
against [`por-brownout`](../target-spec.md#por-brownout): `resetn_floor_in_dip_mv`
pinned at **999.959–1000 mV** at every corner (bound: max 100 mV), i.e. `RESETn`
never leaves the dip rail during the dip, and `t_reassert_us` at
**51.26–51.58 µs** against a 50 µs bound. #55 hypothesised the cause was the
1.0 V dip target sitting below `bias_core`'s own DC operating floor
(`vdd_ref90_v` = 1.127–1.788 V).

**That hypothesis is refuted.** `sim/por-brownout/control/` sweeps the three
variables the hypothesis depends on, one at a time, at `tt`/27 °C/3.30 V — the
one point being justified by the parent record's 0.0045 % spread across all
81 corners:

- **Depth is not the discriminator (A).** A dip to **2.30 V** — above
  `vdd_ref90_v`'s 1.788 V worst case at *every* corner, and only 90 mV below
  VPOR↓,min — fails identically (`min RESETn/VDD in dip` = 0.9993), and
  `POR_RAW` never asserts at all.
- **Duration is not the discriminator (E).** At the parent deck's own 1 µs
  edge, the rail can sit below VPOR↓,min for **5001 µs** — 500× the ratified
  `T_dip,min` of 10 µs — and `RESETn` *still* does not assert during the dip
  (`min RESETn/VDD` = 0.9990 at every dwell from 50 µs to 5 ms). This is not a
  latency a longer `T_dip,min` could absorb; the block is latched out for as
  long as the rail stays down.
- **Falling slew rate is the discriminator (B).** The transition is sharp and
  everything downstream is slaved to it:

  | falling slew | `min BIAS_OK/VDD` in dip | `min POR_RAW/VDD` | `min RESETn/VDD` | verdict |
  |---|---|---|---|---|
  | 2300 / 23.00 / 15.33 / 11.50 mV/µs | **0.9990** (false valid) | 0.9990 | 0.9990 | reset never asserts in the dip |
  | 7.67 / 2.30 / 0.77 mV/µs | ~0 | ~0 | ~0 | reset asserts and reaches a true 0 V |

  The measured boundary lies between **7.67 and 11.50 mV/µs**, which
  independently corroborates `design/bias_core.md`'s separately *derived*
  `PG` slew capability of **~21 mV/µs** (`C(PG)` ≈ 0.45 pF + 0.8 pF Miller,
  second stage sourcing ~26 nA).

The mechanism is therefore `design/bias_core.md`'s already-owned **starved-loop
window**, appearing on the *falling* edge. `V_sg` (= VDD − `PG`, the overdrive
on the PMOS mirror bank) measures **776.2 mV pre-dip → −74.4 mV** 8 µs into a
1 µs edge: the mirror bank is driven fully off, every bias derived from it
dies, and — because the settle comparator is itself biased from the loop —
`BIAS_OK` reads a **false valid** (0.9990, riding the rail high) throughout the
collapse that starves it. Holding `PG` to the rail removes the effect: with a
control-only 20 pF VDD-referenced cap on `PG`, `POR_RAW` asserts *inside* the
dip (+19.6 µs), and given a dwell long enough for the bias-starved deglitch to
finish, `RESETn` reaches a true 0 V inside the dip (+52.3 µs) (D).

**`por_output_chain` is not the limiter and is fully exonerated (C).** At the
1.0 V dip rail with `POR_RAW` driven low, the cell reaches valid-low in
**3.70–7.30 µs** and sinks **+71.1 µA** against a clamp held at the 100 mV
valid-low bound — *unchanged from 500 nA `IBIAS` all the way down to zero
`IBIAS`*. This answers #55's first acceptance criterion directly: below-floor
pull-down capability is retained in full. The failure is entirely upstream, in
whether the *decision* ever arrives.

This also corrects DR-005, which anticipated the right failure but named the
wrong variable: its survey table says the bandgap-referenced comparator
"catches brownout cleanly and immediately … *provided the dip does not itself
collapse the shared core below its own operating floor*". The collapse is real,
but it is **dynamic, not static** — it is set by how fast the rail falls, not
by how far.

## Decision

1. **`por-brownout`'s guarantee is qualified by a falling-slew envelope, not
   only by depth and duration.** The row's conditions gain a third clause: the
   dip's falling edge must be no faster than a `dVDD/dt|fall,max` for
   re-assertion to be guaranteed. Dips falling faster than that bound are
   **explicitly not guaranteed** to assert reset, at any depth and for any
   duration.

2. **`dVDD/dt|fall,max` is not ratified by this record.** The measured
   boundary (7.67…11.50 mV/µs) is a **one-corner** number, and the mechanism
   behind it — `bias_core`'s second-stage current — is strongly
   corner-dependent. The row therefore stays `pending #1`, and ratification
   requires a full 81-point characterization of the boundary in a new
   experiment slug — filed as **#60**. An agent may not ratify a spec
   relaxation on one corner.

3. **`por-reset-valid-floor`'s brownout-dip result is re-attributed, not
   accepted as a floor failure.** `resetn_floor_in_dip_mv` is a **dependent**
   measurement: it samples `RESETn` at a fixed instant inside the dip, so it
   reads the floor only if re-assertion has already happened. At 999.96–1000 mV
   it is reading `RESETn` still in its *released* state, tracking the rail —
   which is correct behaviour for an un-asserted output, not a floor miss. The
   row's floor claim is substantiated by #12's single-cell 0 V-ramp record and
   now additionally by control C at the 1.0 V dip rail with zero `IBIAS`. Its
   `pending #1` status is carried by the `por-brownout` defect it depends on,
   not by any deficiency in the output stage.

4. **No design change is made, and no testbench check is relaxed.**
   `sim/por-brownout/testbench/tb.json` keeps its 50 µs `t_reassert_us` and
   100 mV `resetn_floor_in_dip_mv` bounds exactly as ratified, and the 0/81
   record stands as evidence. The deck's 1 µs edge (2.3 V/µs) is retained as a
   deliberately out-of-envelope stress case.

## Alternatives considered

- **Fix it in `bias_core` (path (a) of #55's acceptance criteria)** — not
  chosen. `design/bias_core.md` already carries the arithmetic for why a
  starved-loop detector independent of the core's own bias is not buildable
  here: the only nA-cost rail-referenced element in this PDK is a subthreshold
  MOS stack measuring **12.6 pA … 17.5 nA** across corners, a **1390:1**
  spread, which cannot satisfy the two inequalities such a detector needs. The
  same conclusion binds this failure, because it is the same mechanism.
- **Add a `PG` hold capacitor, as control D probes** — not chosen, and D is
  explicitly labelled a hypothesis probe rather than a proposal. It needs
  **20 pF ≈ 10 000 µm² of MIM**, three times the entire one-shot capacitor,
  to buy one corner; and even then it only restores `POR_RAW`, with `RESETn`
  still missing a 50 µs dwell. The area is not affordable and the result is
  not sufficient.
- **Add a dedicated brownout detector** — out of scope for wave 1 by DR-005,
  and it is a new always-on branch charged to
  [`por-iq`](../target-spec.md#por-iq), which `design/bias_core.md` already
  records as overrunning. Re-opening it is a wave-2 architecture decision, not
  a fix inside this issue.
- **Raise `T_dip,min` until the measurement passes** — rejected on evidence,
  not on principle: control E shows a 5 ms dwell (500× the ratified minimum)
  does not help. There is no `T_dip,min` that makes the fast-edge case pass.
- **Slow the testbench's dip edge until it passes** — rejected. That is
  relaxing the stimulus to make a result pass, which CLAUDE.md forbids. The
  slow-edge cases are added as *additional* controls, not as replacements.

## Consequences

- `por-brownout` and `por-reset-valid-floor` both stay `pending #1`, but for a
  **root-caused** reason with a named mechanism and a measured boundary,
  rather than for an unexplained 0/81 result.
- The block's brownout behaviour is now stated honestly: for dips falling
  slower than the (to-be-characterized) envelope it behaves as specified —
  control B's 0.77 mV/µs row asserts `POR_RAW` at **2.3828 V**, inside the
  ratified 2.22–2.63 V VPOR↓ band. For faster dips, `RESETn` re-asserts only
  on the *recovery* edge (51.26–51.58 µs across all 81 corners) and does not
  reach a valid low during the dip.
- What still works, and is not retracted: the full ≥1 ms pulse **is**
  regenerated after the dip at every corner (`t_pulse_regen_ms` =
  4.74–16.28 ms, 81/81 PASS). The block recovers; it does not latch up or
  stay released.
- A new full-grid experiment slug is required before #1 can ratify
  `dVDD/dt|fall,max` — filed as **#60**. Until it lands, the envelope clause
  in `por-brownout` carries `[TBD-#60]` rather than a number.
- **New finding surfaced by this work, not resolved by it**: control B's
  intermediate rows assert `POR_RAW` at **2.9941 V** (7.67 mV/µs) and
  **3.1385 V** (2.30 mV/µs) — both *above* VPOR↑,max = 2.73 V, i.e. spurious
  resets at a rail still well inside the ratified operating range. Note these
  are at slews *below* this record's boundary, in the region it otherwise
  describes as behaving as specified. This is a distinct defect from the one
  this record decides and needs its own corner evidence; filed as **#61** so
  it is not lost.
- `design/bias_core.md`'s starved-loop window section grows a falling-edge
  counterpart, and its "worst observed" figures now have a second, independent
  corroboration from a different stimulus.
