# DR-026: A uniform-width-scale re-ratio of `por_output_chain`'s `XMBD` family clears the `IBIAS`-delivery floor but reopens the release-edge relaxation loop DR-016 closed — lever 2 needs a real re-derivation, not a multiplier

- **Status**: proposed
- **Date**: 2026-08-11
- **Decided by**: Loom Builder agent, issue #235

## Context

[DR-024](DR-024-por-output-chain-real-ibias-delivery.md) measured
`por_output_chain`'s real, shared-node `IBIAS` delivery at 0.182x-0.608x
nominal (91.0-304.0 nA), well under the 220 nA (0.44x) floor
`design/por_output_chain.md`'s "Hand-off to #11" section derives for the
deglitch dwell to stay under `spec/target-spec.md#por-brownout`'s
`T_dip,min` = 10 µs, at 61 of 81 PVT points in the `RESETn`-released state.
DR-024 declined to implement lever 2 (re-ratioing the shared node's consumer
mirror diodes) itself, citing that widening `por_output_chain`'s `XMBD`
"reopens ... this cell's own internal sizing ... a re-spin of issue #12's
closed design, not a parameter tweak," and filed issue #235 to do that
re-spin properly, with a full re-derivation and re-verification checklist.

This record documents a first attempt at #235, why it was **not** landed,
and what it establishes about the shape of the correct fix.

## What was tried

`XMBD` (4 µm / 4 µm) and every device in `design/netlist/por_output_chain.spice`
whose current is a fixed ratio *against* `XMBD`'s own gate voltage — `XMN1`,
`XMPD`, `XMP2`, `XMND`, `XMDGPT`, `XMDGNT`, `XMPT`, `XMDANT`, `XMDBPT` (the
"long-`L` bias legs" `design/por_output_chain.md`'s "Device sizing" table
lists at 1:50, 1:4, 5x-the-10 nA-leg, etc.) — had their width scaled by a
uniform factor of 10x (e.g. `XMBD` 4 µm → 40 µm, `XMN1` 0.5 µm → 5 µm,
`XMDGPT`/`XMDGNT` 10 µm → 100 µm), holding every device's `L` fixed. This
preserves every `W/L` *ratio* in the table exactly (both the numerator and
denominator of each ratio scale by the same 10x), which is the textbook way
to widen a current-mirror family without touching its internal current
apportionment — square-law devices sharing a common gate node keep
`I_leg / I_XMBD = (W/L)_leg / (W/L)_XMBD` exactly, independent of the scale
factor, as long as every device stays in the same conduction regime it was
in before. Devices whose role is switching or gain rather than
current-ratio-setting — `XMDGPI`/`XMDGNI` (deglitch input pair), `XMDAPI`/
`XMDBNI` (trip-detector inputs), `XMRLK` (the DR-016 release latch),
`XMTSW`/`XMDIS`, the restoring inverters, the output pair — were left
untouched, since they are sized for switching behavior or leakage ratio, not
for a share of the shared `IBIAS` node.

**The intended effect landed.** Re-running
[`sim/por-output-chain-ibias-sharing/`](../../sim/por-output-chain-ibias-sharing/)
against this change (81-point grid, both netlist levels, both `RESETn`
states, `--no-write` exploratory run) moved the released-state worst corner
(`ss_-40c_2.97v`) from **91.03 nA (0.182x)** to **247.81 nA (0.496x)** —
comfortably above the 220 nA (0.44x) floor, with ~13% margin, and the
asserted-state minimum moved correspondingly higher too. In isolation, this
number is exactly what #235 asks for.

## What broke

Re-running [`sim/por-output-chain-deglitch/`](../../sim/por-output-chain-deglitch/)
(schematic and post-layout, 81-point grid, `--no-write`) against the resized
netlist did **not** produce a clean pass/fail on the brownout-dwell check the
resize targets. Instead, most PVT points (roughly two-thirds) FAILED to
resolve the `tasrt1` measurement (`RESETn`'s re-assertion crossing after the
qualifying dip) at all — `ngspice` reports `measure tasrt1 when(WHEN): out
of interval` because `resetn1` (the DUT fed the idealised 500 nA nominal
`IBIAS`, unaffected by the shared-node sharing question this resize
targets) is **already low going into the search window**, with no falling
edge left to find.

Tracing one representative failing corner (`tt_-40c_2.97v`, schematic,
un-recorded debug run) against the raw `ngspice` transient log shows why:
`RESETn` releases once, around **6.01 ms** (`trel1`), consistent with the
cell's normal power-on behavior — but by the `vmin_hold1` window
(10.99-11.25 ms, well before the qualifying dip at 12.0 ms and with no
external stimulus applied in between) `RESETn` has already fallen back to
~0 V on its own. The cell is re-asserting `RESETn` spontaneously, with
nothing driving it to.

This is the same failure mode `design/por_output_chain.md`'s "[The
release-edge chatter](../../design/por_output_chain.md#the-release-edge-chatter--a-relaxation-loop-through-the-shared-ibias-node-not-a-local-instability)"
section and [DR-016](DR-016-por-ramp-rate-chatter-release-latch.md) diagnosed
and fixed for issue #56: the trip detector's release decision balances two
nA-scale currents (`XMDANT` sinking against `XMDAPI`'s supply, `XMDBPT`
sourcing against `XMDBNI`'s sink) at a node (`ND1`/`TRIP`) whose margin is a
few hundred mV, and `XMRLK` — a **fixed-size**, unscaled 1 µm / 1 µm
transistor — depends on that margin staying wide enough, after release, that
its own leakage-scale conduction keeps winning. This resize widened
`XMDANT`/`XMDBPT` (the current-*setting* legs feeding that balance) 10x while
leaving `XMDAPI`/`XMDBNI` (the gain devices) and `XMRLK` itself untouched —
which is the right call for preserving the ratio table's *current* values,
but it also changes the trip detector's node-voltage operating point in a
way the ratio-preservation argument does not account for, exactly as DR-024
warned. The uniform width scale keeps the leg **currents** correct at a
given delivered `IBIAS`, but the deglitch/one-shot/trip-detector timing this
cell was tuned against depends on **node voltages**, not just current
ratios — and DR-016's fix, sized against the *unscaled* geometry's leakage
margins, does not necessarily carry over unchanged.

## Decision

**This attempt is not landed.** No netlist, layout, or testbench change from
this attempt is committed by this record — `design/netlist/por_output_chain.spice`
and every derived artifact (layout, extracted netlists, testbench snapshots)
are unchanged from `origin/main`. Landing the 10x-scale netlist as evidenced
above would violate CLAUDE.md's "no claim without a testbench": the resize
*regresses* `por_output_chain`'s own basic release behavior at the nominal
(idealised) `IBIAS` DUT, which is a different and larger failure than the
brownout-dwell shortfall it was meant to fix, on the majority of the PVT
grid.

**Issue #235 is not closed by this record.** It is left `loom:blocked`,
with this record as the diagnostic evidence for the next attempt, per
`builder-complexity.md`'s guidance that discovering an issue exceeds one
session's safe scope is documented and handed off, not forced to a
green checkmark.

**What the next attempt needs, based on this evidence:**

1. **Do not treat the resize as "scale `XMBD`'s family, done."** The
   trip-detector's own devices (`XMDAPI`/`XMDANT`, `XMDBNI`/`XMDBPT`,
   `XMRLK`) need to be re-derived as a *system* against the new `IBIAS`
   node operating point, not assumed safe because their current ratios are
   individually preserved. This likely means re-deriving `ND1`/`TRIP`'s
   balance margin (the same nA-scale analysis DR-016's "The mechanism, in
   the order the trace shows it" section walks through) at the new node
   voltage, and re-checking whether `XMRLK`'s fixed 1 µm / 1 µm still beats
   the (now different) leakage/sub-threshold legs it has to beat by DR-016's
   "three decades of margin."
2. **A smaller widening factor may avoid the regime change entirely.**
   10x was chosen to give comfortable floor margin (0.496x vs. the 0.44x
   floor) in one step; DR-024's own back-of-envelope arithmetic for a
   comparable lever (widening `bias_core`'s `XMPIB`) estimated ~2.42x as the
   minimum needed (`220/91.08`). A smaller `XMBD` widening, verified
   against the full three-testbench suite at each step rather than jumping
   straight to a large multiplier, is more likely to stay inside the
   conduction regime (subthreshold vs. strong inversion) the original
   design and DR-016's fix were both tuned against, and is worth trying
   before concluding a full trip-detector re-derivation is unavoidable.
3. **The regression surfaces on the *idealised nominal* DUT, not only the
   stress DUT.** Any candidate resize must be checked against
   `sim/por-output-chain-pulse/`'s and `-deglitch/`'s nominal-`IBIAS` points
   first — a resize that cannot even release `RESETn` cleanly at 1x nominal
   is not a candidate worth taking to the PVT grid.

## Alternatives considered

- **Land the 10x resize anyway, since the targeted metric
  (`sim/por-output-chain-ibias-sharing/`) passes.** Rejected — the acceptance
  criteria for #235 explicitly require the three-testbench suite (pulse,
  deglitch, floor) to be re-run and pass, and this resize fails the
  deglitch suite outright (release-behavior regression) rather than merely
  missing the specific brownout-dwell margin it targets.
- **Debug and fix the trip-detector regression within this same session by
  further trial-and-error on device sizes.** Rejected for this attempt —
  the regression traces to the same relaxation-loop mechanism DR-016 spent
  a dedicated root-cause investigation on (four-arm isolation, nA/mV-level
  node tracing) before landing a one-transistor fix; reproducing that rigor
  for the new operating point needs its own focused pass rather than
  further guesses layered onto an already-large diff.
- **Decompose #235 into parallel sub-issues.** Considered and rejected —
  the acceptance checklist (re-derive sizing, re-run three testbenches,
  re-check the comparator, re-check `por-iq`, re-extract layout, write the
  decision record) is one sequentially-coupled analog design task, not
  independently parallelizable work; `builder-complexity.md`'s own
  decomposition criteria call this case out ("Do NOT decompose if ...
  breaking it up would create tight coupling/dependencies").

## Consequences

**No ratified row in `spec/target-spec.md` is added, removed, or relaxed by
this record**, and no device sizing on `origin/main` changes — this is a
diagnostic record only.

**Issue #235 moves to `loom:blocked`**, not closed, with this record and the
"What the next attempt needs" list above as its starting point. The
`sim/por-output-chain-ibias-sharing/` and `sim/por-output-chain-deglitch/`
runs this record describes were exploratory (`--no-write`, against a working
tree that is discarded, not committed) and are cited here as evidence only —
they are not `sim/` records and carry no record IDs, per the harness
convention that only committed, reproducible runs mint evidence files.

**DR-024's routing stands.** This record does not change DR-024's
conclusion that levers 1 and 3 are arithmetically ruled out and lever 4 is a
human spec-ratification call (#236); it narrows what lever 2 (#235) actually
requires to close.
