# DR-014: The deglitch dwell filters `POR_RAW`, not `VDD` — a `VDD`-level glitch cannot be rejected by resizing it

- **Status**: proposed
- **Date**: 2026-08-02
- **Decided by**: Loom Builder agent, issue #56

## Context

`sim/por-glitch/records/20260801-233813-32fbaa0.md` (81-point PVT grid, full
four-cell assembly) applies a 300 ns / 0.2 V supply glitch — chosen as "well
under" `sim/por-output-chain-deglitch/`'s characterized deglitch dwell
(1.86–8.88 µs, cell level, idealised bias) — and measures `RESETn` drooping
during the glitch at every corner and, at a subset of corners, still low
5.5 ms after the glitch ends. 0/81 PASS.

Issue #56 hypothesised this shares #55's theme: the glitch collapses
`bias_core` below its own ~1.13–1.79 V operating floor
(`design/bias_core.md`, "Settling and dropout"), starving the deglitch
filter's own bias current so it cannot hold state.

`sim/por-glitch/control/run_glitch_probe.py` (a committed, re-runnable
control experiment, `sim/README.md` §"Control experiments") traces `VDD`,
`POR_RAW`, `PGDG`, `VREF`, `BIAS_OK`, `TIM`, `TRIP` and `RESETn` through the
glitch and the following tens of milliseconds at two PVT points that bracket
the record's own "recovers" / "stuck" split. It refutes the bias-collapse
hypothesis directly — `VREF` and `BIAS_OK` never drop out and `POR_RAW`/
`PGDG` are back at the rail within microseconds of `VDD` recovering, nothing
like the multi-hundred-µs restart `design/bias_core.md`'s starved-loop
window measures after a genuine sustained collapse — and finds the real
mechanism instead:

1. `PGDG` (por_output_chain's "deglitched power-good" node) is produced by
   two plain `VDD`-referenced ratioed inverters (`XMG1`/`XMG2`). The
   deglitch dwell capacitor `CDG` sits only on `POR_RAW`'s input side of the
   chain (node `NDG`). When `VDD` itself collapses, `PGDG` collapses with
   it, instantaneously, with **no RC lag** — measured diving to ~0.5 V
   during the 300 ns glitch at every point traced.
2. `XMDIS` (gated by `PGDGB`) discharges the one-shot timer `TIM` to `VSS`
   the instant `PGDG` falls — the same, deliberate mechanism that correctly
   regenerates a full pulse after a genuine brownout
   (`design/por_output_chain.md`, "The one-shot is a current-starved ramp").
   It cannot distinguish "`PGDG` fell because `POR_RAW` is genuinely bad"
   from "`PGDG` fell because `VDD` itself is what collapsed". Measured:
   `TIM` reads ~0.93 V (fully discharged) immediately after the glitch ends
   at every point traced.
3. `RESETn` then regenerates a complete, freshly-timed reset pulse — one
   low, then release, 5.08–6.11 ms later at the two points traced, the
   pulse width scaling with `VDD` exactly as
   `design/por_output_chain.md`'s "trip is `VDD − V_sg`" finding predicts.
   The record's "recovers" vs. "stuck" split is that pulse-width-vs-fixed-
   observation-window effect, not two different circuit behaviours or a
   filter that lost its state.

**The deglitch dwell (`CDG`) provides zero protection against a disturbance
on `VDD` itself, of any depth or duration**, because the node it protects
(`PGDG`) has no time constant on that path at all — there is nothing for a
longer or shorter `VDD`-level glitch to be compared against. This is
different in kind from the dwell's actual, correctly-characterized job:
rejecting a `POR_RAW`-only disturbance while `VDD` holds steady (which
`sim/por-output-chain-deglitch/` measures and passes). `por-glitch`'s own
300 ns choice, framed as "well under" the dwell, was never a testable
premise for a `VDD`-level glitch — "well under" only has meaning on the
`POR_RAW`-side path.

Full root-cause writeup: `design/por_output_chain.md`, "Why the deglitch
dwell cannot reject a VDD-level glitch". Full evidence:
`sim/por-glitch/control/results.md`.

## Decision

**This is recorded as an architecture-level finding, not a sizing defect in
`por_output_chain`, and no change is made to `CDG`, `XMDIS`, or any other
device in this issue.** Resizing the dwell capacitor cannot fix a mechanism
that has no dependence on it. `spec/target-spec.md`'s `por-brownout` row
(which currently carries the deglitch-rejection carve-out `por-glitch`
verifies against) is amended to note this distinction: the carve-out's
"dips shorter than the deglitch dwell are not guaranteed to assert reset"
language is about `POR_RAW`-only disturbances, and does not — and, on this
architecture, cannot — extend to a disturbance on `VDD` itself of any
duration. `por-glitch`'s own testbench and its 0/81 result stand as
correctly measuring an un-ratified, un-testable-as-written premise; no
target-spec row is added, removed, or relaxed by this record, per CLAUDE.md.

Two follow-on questions are handed to future work rather than answered
here, because both need judgment beyond a root-cause pass:

- **Is a `VDD`-level glitch even the right threat model for this check**,
  given the block has no dedicated brownout/glitch detector in wave 1
  (`por-brownout`'s own `[P]`: "No dedicated brownout detector … re-assertion
  is whatever the POR comparator itself provides")? If the answer is "yes,
  a real system can glitch `VDD` this way", the correct response is new
  circuit topology (a locally-reserved, rail-independent hold on `XMDIS`'s
  trigger, or a separate rail-collapse detector), which is real Iq- and
  area-costing work in the same family as the starved-loop window's
  `por-iq`-vs-`por-ramp-rate` tension `design/bias_core.md` already
  documents — not something to improvise inside this record.
- **If a `VDD`-level glitch immunity claim is wanted at all**, what is the
  representative depth/duration, and should the check be reframed from "must
  never move" to "must regenerate a single, correctly-shaped pulse and then
  stay released" (which is in fact what this design already does, and does
  correctly, on every point traced) — the same reframing #55 is weighing for
  `por-brownout`'s 1.0 V dip depth.

## Alternatives considered

- **Shrink `CDG` or otherwise resize the deglitch filter.** Rejected as a
  category error, not merely unhelpful: the mechanism has no dependence on
  `CDG` at all (§ Context, point 1), so no value of it changes the outcome.
  It would also directly regress `sim/por-output-chain-deglitch/`'s
  passing, correctly-characterized `POR_RAW`-side result.
- **Add a rail-collapse hold on `XMDIS` now, inside this issue.** Rejected
  as premature. It is real new topology (a hysteretic or capacitively-held
  gate on `XMDIS`, or an independent detector), it costs Iq/area against
  rows already under pressure (`por-iq` is 2.37× over budget per
  `design/bias_core.md`), and it needs its own stability/verification pass
  — the same reasoning issue #56 itself gives for not attempting the
  ramp-rate chatter fix inside a root-cause pass. Better done as sized,
  scoped follow-on work once the threat-model question above is answered.
- **Reframe `por-glitch`'s check now, inside this issue.** Rejected for the
  same reason: whether "must regenerate one clean pulse" is an acceptable
  replacement claim, and at what glitch depth, is a spec-level judgment call
  for #1, not a call this record should make unilaterally by editing a
  ratified carve-out's meaning.
- **Treat this as confirming issue #56's own bias-collapse hypothesis and
  file it as a #55 duplicate.** Rejected — the traced evidence refutes the
  bias-collapse hypothesis for this specific finding (§ Context): `VREF`/
  `BIAS_OK` never drop out, and `POR_RAW`/`PGDG` recover within microseconds.
  #55's mechanism (a sustained dip parking the rail below `bias_core`'s
  dropout for the dip's whole duration) and this one (an instantaneous,
  `VDD`-referenced logic-level fall with no bias dependence) are different
  root causes that happen to share a symptom family ("RESETn misbehaves
  during a supply excursion"), not one mechanism.

## Consequences

- **No design or testbench change lands with this record.** `CDG`, `XMDIS`
  and every other device in `design/por_output_chain.sch` are untouched;
  `design/netlist/por_output_chain.spice` is byte-identical.
- **`sim/por-glitch/`'s 0/81 result stands, correctly, as evidence of an
  un-testable-as-written premise, not as an open defect to chase with
  sizing changes.** No re-run is expected to move it without either a
  testbench/spec change (reframing the check, per the follow-on question
  above) or new circuit topology (a rail-collapse detector) — neither of
  which this record authorizes.
- **`spec/target-spec.md`'s `por-brownout` row** gets a citation to this
  record and to `design/por_output_chain.md`'s new section, clarifying that
  the deglitch-rejection carve-out is `POR_RAW`-scoped; the row's ratified
  value and `pending #1` status are unchanged.
- **#55 is separate, and has since closed on a different mechanism.** This
  record does not resolve, and is not a substitute for, #55's own
  investigation of the 1.0 V brownout dip. That investigation landed on
  `main` while this record was in flight, as
  [DR-011](DR-011-brownout-falling-slew-limit.md): it **refutes** the
  below-operating-floor hypothesis for `por-brownout` and root-causes that
  0/81 to the rail's **falling slew rate** driving `bias_core`'s PMOS mirror
  bank off. That is a third mechanism, distinct from both the hypothesis
  this record refutes and the `VDD`-referenced logic-level fall it
  identifies — the two records agree on the conclusion that reached them by
  different routes: `por-glitch`'s failure is not `por-brownout`'s.
- **What becomes possible.** A future architecture-level fix (a
  rail-collapse-independent hold on the one-shot) now has a precise,
  evidenced target rather than a vague "deglitch filter loses state under
  load" hypothesis — it needs to hold `XMDIS`'s trigger stable across a
  `VDD` excursion of the threat model's chosen depth/duration, not merely
  add more bias current to `por_output_chain`.
