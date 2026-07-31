# DR-002: Temp sensor interface (wave-1 deliverable + accuracy measurement point)

- **Date:** 2026-07-30
- **Decided by:** Builder agent, issue #7
- **Status:** proposed (ratification is issue #1's call — this record does not
  edit the README spec table)

## Context

The draft spec's "Temp interface" row lists **analog PTAT/CTAT out** as the
target and **digital out via SAR pairing** as stretch. Two things are
undecided: (1) what wave 1 actually delivers — analog only, and if so is
that one pad or the full PTAT+CTAT pair the target column implies — and
(2) where the ±3 °C accuracy line (untrimmed) is judged: at the analog pin
voltage, or at a post-conversion digital code (which requires the SAR
pairing that is currently stretch, not committed).

This decision gates #8's pinout (how many, and which, pads the temp sensor
needs) and #13's accuracy testbench (what signal it samples and how it
converts a sample into a temperature error). Neither #3 nor #4 has landed
artifacts in `spec/`/`sim/` as of this writing; per issue #7's Coordination
section this does not block the decision.

## Decision

**Wave 1 delivers analog-only, both pads.** The block exposes two analog
output pads — **PTAT** and **CTAT** — as the draft spec's target column
already implies by naming both signals; wave 1 commits to shipping both,
not just one. **Digital output via SAR pairing remains stretch and is not
attempted in wave 1** — it stays exactly where the draft table already put
it (Stretch column, unchanged), and this record makes that de-scope
explicit rather than leaving it ambiguous.

**Accuracy measurement point: pin voltage.** The ±3 °C (untrimmed) / ±1.5 °C
(1-pt trim, stretch) accuracy target is judged at the **analog output pin
voltage**, converted to an equivalent temperature via the sensor's published
V(T) transfer characteristic, and compared against the true (simulated
ambient/die) temperature — **not** at a post-conversion digital code. This
follows directly from the analog-only wave-1 scope: there is no ADC/code in
wave 1 to measure against.

## Alternatives Rejected

**Attempt digital-out via SAR pairing in wave 1 — rejected.** SAR pairing
requires an ADC/reference framework that does not yet exist in this repo's
design tree, and building it now would:
- consume area/Iq budget not accounted for anywhere in the draft spec (the
  Temp Iq target of <20 µA / stretch <5 µA and POR Iq target of <1 µA
  already constrain the block tightly);
- expand #8's pinout and config surface before #12's POR architecture (a
  harder, more load-bearing dependency) is even settled — this issue exists
  specifically to avoid that kind of premature scope expansion (see issue
  #7's framing: it is "the narrowest gate in the dependency graph").
No dedicated architecture/owner issue for SAR pairing exists yet; if it is
promoted out of stretch in a future wave, it should get one rather than
being folded silently into this block's wave-1 scope.

**Analog-only but single-pad (PTAT only) — rejected.** The draft spec's
target-column value is explicitly "analog PTAT/CTAT out" (both signals);
dropping CTAT to a single output pad would be a silent spec cut, which is
outside this issue's mandate (issue #7 makes interface/measurement
*decisions*, it does not unilaterally shrink the target spec — that is
ratification's job in #1). CTAT is also needed for ratiometric/differential
characterization in #13, so keeping both pads preserves testbench
flexibility at negligible incremental pad cost.

**Measurement point at post-conversion code — rejected.** Not viable given
the analog-only wave-1 decision above: there is no code to measure without
first committing to SAR pairing, which this record explicitly defers.

## Consequences (README spec-table rows touched)

- **Temp interface** row: commits the target column ("analog PTAT/CTAT out")
  as wave 1's actual deliverable, both pads; explicitly reaffirms the
  stretch column ("digital out via SAR pairing") is unchanged and deferred.
- **Temp accuracy (untrimmed)** row: adds the measurement-point clarification
  (pin voltage, via published V(T) transfer characteristic) that the value
  `±3 °C` was previously silent on.
- **#8 pinout consequence:** two analog output pads required for wave 1
  (PTAT, CTAT); no digital/SAR interface pins or config surface required.
- **#13 testbench consequence:** the accuracy testbench sweeps ambient
  temperature across the full −40…125 °C range (per the "Temp range" row),
  samples PTAT/CTAT pin voltage(s) at each point, converts via the sensor's
  V(T) transfer function, and asserts the resulting temperature error stays
  within ±3 °C (untrimmed target) / ±1.5 °C (1-pt-trim stretch) — at the
  supply bounds and steady-state condition fixed by DR-001.
