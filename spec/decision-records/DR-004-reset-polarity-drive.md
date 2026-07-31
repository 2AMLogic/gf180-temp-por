# DR-004: Reset polarity, drive style, and below-floor behavior

- **Date:** 2026-07-30
- **Decided by:** Builder agent, issue #7
- **Status:** proposed (ratification is issue #1's call — this record does not
  edit the README spec table)

## Context

The draft spec specifies the POR reset **pulse width** (`≥ 1 ms`, DR-003)
but says nothing about reset **polarity** (active-low vs. active-high),
**drive style** (push-pull vs. open-drain), or — the subtlest and most
load-bearing part — what state the reset pin must hold while VDD is below
the comparator's *own* operating floor (the comparator that generates the
POR threshold decision cannot itself function arbitrarily close to 0 V, so
something else has to define the reset pin's state in that regime). This
record is what #10 (comparator floor behavior) and #12 (output stage) must
satisfy, and what #14 (slow-ramp testbench) asserts against.

Neither #3 nor #4 has landed artifacts in `spec/`/`sim/` as of this writing;
per issue #7's Coordination section this does not block the decision.

## Decision

**Polarity: active-low (`RESETn`).** **Drive: push-pull** (not open-drain).

**Below-floor requirement (the part #10/#12/#14 inherit):** `RESETn` must be
**actively held at a valid logic-low (reset asserted) for every VDD value
from 0 V up to and including the comparator's own minimum operating
voltage**, using a mechanism that itself works correctly below that floor —
e.g. a simple pull-down device biased directly off the ramping rail, not a
mechanism gated by the comparator's own output (which is undefined below
its floor). Control of `RESETn` transfers to the comparator-driven
threshold/hysteresis/pulse-timer logic (DR-003) only once VDD exceeds the
comparator's floor. This is a testable requirement: #10 must show the
comparator floor and the pull-down handoff do not overlap in a way that
leaves `RESETn` undefined, #12's output stage must hold this state down to
the lowest holdable rail, and #14's slow-ramp testbench must assert
`RESETn` stays low for all VDD below both the comparator floor and the POR
threshold (DR-001/README's `2.6 V ±5 %` row).

## Alternatives Rejected

**Active-high polarity — rejected.** An active-high reset must be actively
driven *high* to signal "asserted," but near 0 V rail (exactly the regime
the below-floor requirement covers) there is no headroom to drive anything
high without an independent, always-available supply — which this
single-rail block does not have (DR-001 pins one 3.3 V rail, no separate
always-on domain). Active-low naturally degrades to "asserted" (logic 0)
under loss of drive/charge near 0 V, which is achievable with a passive or
minimally-active pull-down; the active-high equivalent is not achievable by
passive means. This is the deciding factor, not convention alone (though
active-low is also the near-universal industry convention for POR/reset).

**Open-drain drive — rejected.** Open-drain requires an external pull-up
resistor to a defined rail to reach the deasserted (high) state; for a
self-contained single-supply block with no separate always-on rail
described anywhere in this repo, that pull-up's availability and value are
outside this block's specified interface — the deasserted state could not
be guaranteed reachable under all system integrations, and any current
drawn through an external pull-up while reset is asserted (for however long
the DR-003 pulse holds) is not accounted for in the POR Iq budget. Push-pull
drives both states deterministically from within the block and gives sharp
edges useful for #14's ramp-timing assertions.
(**Assumed external termination, for completeness, had open-drain been
chosen:** a pull-up resistor from `RESETn` to VDD, value chosen by the
system integrator per downstream digital load — not specified by this
block. Recorded here per issue #7's guidance to document the assumed
termination even though open-drain is the rejected option.)

## Consequences (README spec-table rows touched)

- **POR reset pulse** row: clarifies that pulse timing (`≥ 1 ms`, DR-003) is
  measured on the `RESETn` active-low **deassertion** edge (the transition
  from asserted/low back to released/high), not on assertion.
- **New rows needed:** the draft table has no row for polarity or drive
  style at all; the ratified table (#1) should add explicit **"POR reset
  polarity"** (`RESETn`, active-low) and **"POR reset drive"** (`push-pull`)
  rows alongside ratifying the existing rows.
- **#10 consequence:** must define and demonstrate the comparator's own
  floor voltage and show the below-floor pull-down hands off to
  comparator-driven control without leaving `RESETn` undefined at any VDD.
- **#12 consequence:** output stage must implement push-pull drive and hold
  `RESETn` low down to the lowest holdable rail (0 V ideally, or the lowest
  voltage at which any active device in the block can still hold a defined
  state — #12 must state that floor if it cannot reach 0 V).
- **#14 consequence:** slow-ramp testbench asserts `RESETn` stays low for
  all VDD below `min(comparator floor, 2.6 V × 0.95 threshold band)`, and
  releases only after VDD clears the DR-001 margin and the DR-003 pulse has
  elapsed.
