# DR-020: The real-world `POR_RAW` chatter width `por_output_chain`'s 1.00 µs floor needs is not observable in any existing deterministic-corner deck — routed to #1

- **Status**: proposed
- **Date**: 2026-08-11
- **Decided by**: Loom Builder agent, issue #199

## Context

[`design/por_output_chain.md`](../../design/por_output_chain.md) measures the
deglitch filter's post-layout glitch-rejection **floor** at 1.00 µs against
the 1 µs `POR_RAW` chatter burst
[`sim/por-output-chain-deglitch/testbench/stimulus.spice`](../../sim/por-output-chain-deglitch/testbench/stimulus.spice)
applies — a **1.00× margin**, down from 1.75× at the schematic level (issue
#182). That 1 µs is stated there as a **design-chosen assumption**: nothing
in the ratified `spec/target-spec.md` bounds how narrow a `POR_RAW` excursion
this cell must reject, and the real number is a property of
`por_comparator`'s behaviour near its threshold on a live bring-up sequence —
#14's assembly-level territory, not something `por_output_chain` can measure
alone. Issue #199 asks whether #14's existing decks already contain that
measurement as a post-processing target, before any new testbench is
considered.

They do not, and the gap is structural rather than a missed post-processing
pass. Every full-assembly deck examined is a **deterministic-corner** record
(`design.ngspice` sets `sw_stat_mismatch=0`) driven by either a clean,
noiseless ramp or a single programmed dip — never anything resembling supply
ripple, EMI coupling, or comparator-side dither:

- [`sim/por-vth/`](../../sim/por-vth/) is explicitly a **quasi-static** ramp,
  built (per its own stimulus header) so the bias core is settled at every
  instant across the threshold band. Its `rise_chatter_mv` / `fall_chatter_mv`
  checks require the first and last threshold crossing to coincide within
  ±5 µV, and every recorded corner meets that — by construction, not by
  accident.
- [`sim/por-ramp-rate/`](../../sim/por-ramp-rate/) checks the same thing at
  all four ratified ramp rates (`chatter_*_us`, a ±1 ns band) and passes
  81/81 since [DR-016](DR-016-por-ramp-rate-chatter-release-latch.md). Its
  own control experiment states the reason directly:
  > "POR_RAW, PGDG, VREF and BIAS_OK cross the 1.0 V threshold at most once
  > at every point and in every arm, including the ones that show RESETn
  > chatter" ([`sim/por-ramp-rate/control/results.md`](../../sim/por-ramp-rate/control/results.md)).
  The release-edge chatter this repository did find and fix with `XMRLK` is
  a **`RESETn`-side** relaxation loop through the shared `IBIAS` node
  ([`design/por_output_chain.md`](../../design/por_output_chain.md), "The
  release-edge chatter"), not a `POR_RAW` excursion at all — `POR_RAW`
  itself never moves twice.
- [`sim/por-brownout/`](../../sim/por-brownout/) applies a 50 µs / 1.0 V
  qualifying dip — 5× `T_dip,min`, deliberately deep and unambiguous, not a
  narrow near-threshold toggle.
- [`sim/por-brownout-spurious/`](../../sim/por-brownout-spurious/)
  characterizes a genuine, previously-unrecognised falling-slew spurious
  **assert** ([DR-013](DR-013-por-brownout-spurious-assert.md)), but it
  measures only the assert *instant*, not an excursion *width*, and is a
  different mechanism (a ratiometric trip tracking `VDD` during a controlled
  recovery slew) from the near-threshold noise-driven "chatter" Question 1
  asks about.

In every full-assembly transient committed to `sim/` as of this record,
`POR_RAW` crosses its threshold cleanly, exactly once. There is no excursion
event anywhere in the existing evidence to extract a width from — reprocessing
these records cannot produce the measurement, because the underlying data
does not contain it.

## Decision

**Question 1 of issue #199 is not resolved, and is explicitly routed to
#1.** Producing the measurement it asks for — a real-world `POR_RAW`
excursion width near `por_comparator`'s threshold, to compare against the
1.00 µs post-layout floor — needs one of two things this record does not
manufacture unilaterally:

1. A **new noise-injection stimulus model** on a live bring-up sequence
   (supply ripple, digital switching noise, or another EMI-representative
   waveform coupled onto `VDD` or `POR_RAW`). Choosing its amplitude,
   spectral content and coupling path is a modeling-methodology judgment
   about what "real-world" means for this claim, not a `por_output_chain`
   -local design choice — the same class of judgment
   [DR-017](DR-017-por-glitch-representative-depth.md) reserved for the
   ratification pass on a parallel question (what glitch depth is
   representative).
2. **#15's Monte Carlo mismatch sweep**, read against the 1.00 µs floor once
   it exists for the near-threshold decision path. Mismatch-driven dither at
   the comparator's input is a real physical source of a narrow spurious
   excursion, but it is explicitly out of this issue's scope (`design/bias_core.md`
   and `design/por_output_chain.md` both defer local mismatch to #15) and is
   not the same mechanism as electrical noise on a real board, so it answers
   a related but not identical question.

**No ratified value is added, removed or relaxed by this record.**
`por-brownout`'s 10 µs `T_dip,min` ceiling and `design/por_output_chain.md`'s
measured 1.00 µs post-layout floor both stand exactly as currently drawn and
measured — this record changes the *evidentiary status* of the floor's
adequacy claim (from "unexamined design guard" to "examined, and not
verifiable with today's deterministic-corner harness"), not the number
itself.

## Alternatives considered

- **Build a new noise-injection testbench inside issue #199's own scope.**
  Rejected. The noise model itself is the open question — inventing an
  amplitude/spectrum/coupling choice here would produce a number that looks
  measured but is actually an unstated design assumption one level removed,
  exactly the failure mode CLAUDE.md's "no claim without a testbench"
  discipline exists to prevent. That choice belongs with whoever ratifies
  what "real-world chatter" means for this claim.
- **Run #15's Monte Carlo sweep now and substitute its near-threshold dither
  for Question 1's answer.** Rejected for this record, though it may be a
  reasonable path for #1/#15 to take later: mismatch and electrical noise are
  different physical mechanisms, and #15 is explicitly out of scope for
  #199's own acceptance criteria.
- **Treat the existing 0-chatter results as sufficient proof that 1.00 µs is
  safe.** Rejected — the absence of chatter in a noiseless, deterministic
  simulation says nothing about a physical rail carrying real ripple or
  digital switching noise; concluding "safe" from that evidence would be an
  unearned inference, not a measurement.
- **Widen `sim/por-output-chain-deglitch/`'s own chatter burst further and
  call that "the real width".** Rejected — that testbench's burst is a
  cell-level design guard by construction (`design/por_output_chain.md`
  already says so), and widening it does not make it a measurement of
  `por_comparator`'s real behaviour; it only restates the same assumption at
  a different number.

## Consequences

- **The 1.00 µs post-layout floor stands, unverified against the real-world
  quantity Question 1 asks about.** Anyone relying on it going forward is
  relying on a design-chosen guard whose margin is 1.00× post-layout, not a
  quantity confirmed adequate against a measured chatter distribution.
- **#1 inherits an explicit, numbered open question**, analogous to
  DR-017's `por-glitch` depth question: either commission a new
  noise-injection testbench (with its own scope and, if it changes any
  ratified row, its own decision record) or designate #15's mismatch result
  as the representative near-threshold uncertainty once it lands, and
  re-read it against the 1.00 µs floor.
- **No `sim/` testbench is added or changed by this record.** A genuinely
  new stimulus model is exactly the kind of new simulation work CLAUDE.md
  warns against inventing speculatively when the model boundary itself, not
  the circuit, is the open question.
- **`design/por_output_chain.md`'s `CDG` sizing is unaffected.** The cell
  stays at 11 µm × 11 µm, per its own "Whether `CDG` has to grow" finding —
  nothing in this record changes that arithmetic, since the ceiling and floor
  bounds it trades off are unchanged.
