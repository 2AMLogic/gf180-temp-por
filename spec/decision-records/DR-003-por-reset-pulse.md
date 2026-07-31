# DR-003: POR reset pulse width (fixed vs. programmable)

- **Date:** 2026-07-30
- **Decided by:** Builder agent, issue #7
- **Status:** proposed (ratification is issue #1's call — this record does not
  edit the README spec table)

## Context

The draft spec's "POR reset pulse" row lists **≥ 1 ms** as the target and
**programmable** as stretch. Programmability is not a cosmetic add-on here:
it changes the *architecture class* of #12's output-logic design (a simple
nA-charged-capacitor timer vs. a low-power oscillator + counter with a
configuration interface), so it has to be settled before #12 can commit to
a topology. This record also feeds #8, since a programmable pulse implies
additional config pins/trim bits that a fixed pulse does not.

Neither #3 nor #4 has landed artifacts in `spec/`/`sim/` as of this writing;
per issue #7's Coordination section this does not block the decision. (#3's
memo is directed, per its curation, to take a reset-pulse-generation stance
compatible with < 1 µA Iq — if/when it lands, it should be checked against
this record's architecture consequence below and reconciled if it disagrees
while both remain `proposed`/unratified.)

## Decision

**Wave 1 implements a fixed reset pulse width, ≥ 1 ms, with no
configuration interface.** Programmable pulse width remains **stretch and
is explicitly de-scoped for wave 1** — not merely unaddressed, but a
deliberate decision so #12 can commit to a topology without re-litigating
this later.

**Architecture consequence for #12:** a fixed pulse width can be generated
with a simple **nA-current-charged-capacitor timer** (current-starved RC
style: a small bias current charges a capacitor from the POR release edge;
a comparator/Schmitt trigger compares against a fixed fraction of the rail
or a bandgap-independent reference and releases reset once the cap voltage
crosses it). This topology has no oscillator, no counter, and no
configuration/trim register, which keeps #12 compatible with the draft
spec's POR Iq target (< 1 µA, stretch < 0.3 µA) — an oscillator + counter
architecture (the topology programmability would require) burns
meaningfully more quiescent current and adds area/pin count that nothing
in this repo currently requires.

## Alternatives Rejected

**Commit to programmable pulse width for wave 1 — rejected.**
- No consumer issue in this repository currently requires field-adjustable
  reset pulse width; committing to it now would be speculative scope.
- It forces an oscillator/counter architecture in #12, which costs
  quiescent current the draft POR Iq row (< 1 µA / stretch < 0.3 µA) cannot
  obviously absorb without further characterization data that doesn't exist
  yet (#4 has not landed).
- It expands #8's pinout/config surface (trim bits or a config protocol —
  e.g. a one-wire or register interface) with no protocol defined anywhere
  in this repo, and no owner issue exists yet to define one. If
  programmability is promoted out of stretch in a later wave, it should get
  its own dedicated issue (config protocol + #12 architecture rework)
  rather than being folded into this issue's decision or into #12 by
  implication.

No other pulse-width architecture (e.g. digital counter clocked from an
always-on low-power oscillator sized only for #12, without exposing
programmability externally) was considered in scope for this record — that
is an implementation detail #12 owns once the fixed-vs-programmable
decision is made, not a decision this record needs to make.

## Consequences (README spec-table rows touched)

- **POR reset pulse** row: commits the target column (`≥ 1 ms`) as wave 1's
  actual deliverable, fixed (not adjustable); reaffirms the stretch column
  (`programmable`) is unchanged and explicitly deferred, with no owner issue
  yet — one should be filed before promotion out of stretch.
- **POR Iq** row (< 1 µA target / < 0.3 µA stretch): the fixed-pulse
  architecture choice above is what makes this Iq budget achievable without
  further negotiation; a programmable/oscillator-based architecture would
  put this row at risk.
- **#12 architecture consequence:** current-starved-capacitor timer, no
  oscillator, no counter, no config interface — #12 can commit to this
  topology without waiting on a programmability ruling.
- **#8 pinout consequence:** no additional trim/config pins required for
  the reset-pulse function in wave 1.
