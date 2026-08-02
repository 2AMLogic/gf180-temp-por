# DR-017: `por-glitch`'s 0.2 V "full depth" is past the block's own supply floor, not a representative glitch — the measured `VDD`-glitch immunity boundary is 0.5–0.65 V

- **Status**: proposed
- **Date**: 2026-08-02
- **Decided by**: Loom Builder agent, issue #56
- **Extends**: [DR-014](DR-014-por-glitch-vdd-level-immunity.md) (mechanism), which
  left this question open

## Context

`sim/por-glitch/` applies one glitch shape — 300 ns total, down to 0.2 V —
and is **0/81 PASS**. [DR-014](DR-014-por-glitch-vdd-level-immunity.md)
root-caused that to a `VDD`-level mechanism with no dependence on the
deglitch dwell (1.86–8.88 µs) the 300 ns duration was chosen against, and
then explicitly deferred the question issue #56 asks third: **is 0.2 V the
right representative depth at all?** DR-014 also made a strong unbounded
claim — that the block has "**zero** protection against a disturbance on
`VDD` itself, of any depth or duration". Both are now measured rather than
argued.

`sim/por-glitch/control/run_depth_sweep.py` sweeps two axes, one variable per
run, at two PVT points (`tt`/27 °C/3.30 V and `ss`/125 °C/2.97 V), in two
circuit arms (`asbuilt`, and `nokeeper` = the committed netlist with
[DR-016](DR-016-por-ramp-rate-chatter-release-latch.md)'s `XMRLK` release
latch deleted by an asserted single-line edit — i.e. the circuit record
`20260801-233813-32fbaa0` measured). "Assert" = `RESETn` fell below 1.65 V at
any time from 100 µs after the rail recovered to the end of the run.

**Depth axis** (300 ns total, rail floor swept). Both PVT points give the
identical boundary in each arm:

| Rail floor | `asbuilt` | `nokeeper` |
| --- | --- | --- |
| 0.2 V (the testbench's own choice) | assert | assert |
| 0.35 V | assert | assert |
| 0.5 V | assert | assert |
| **0.65 V** | **no assert** | assert |
| 0.8 V | no assert | assert |
| 1.4 V | no assert | assert |
| **2.0 V** | no assert | **no assert** |
| 2.4 V, 2.8 V | no assert | no assert |

**Duration axis** (0.2 V floor, hold swept from 10 ns to 30 µs — spanning and
overshooting the whole 1.86–8.88 µs dwell). **Every** run asserts, in **both**
arms, at **both** points. The response is flat across three decades of
duration.

Two things follow, and they are different in kind:

1. **DR-014's duration claim is confirmed exactly as stated.** A 10 ns
   collapse to 0.2 V and a 30 µs one produce the same outcome. The dwell
   (`CDG`, 242 fF on `NDG`) sits on `POR_RAW`'s input side and is not in this
   path at all, so "300 ns is well under the dwell" was never a testable
   premise on this axis.
2. **DR-014's depth claim ("any depth") is refuted, and by a wide margin.**
   There *is* a sharp `VDD`-glitch immunity boundary, it is reproducible to
   within one sweep step at two very different PVT points, and
   [DR-016](DR-016-por-ramp-rate-chatter-release-latch.md)'s `XMRLK` moves it
   by more than a volt: from between **1.4 and 2.0 V** without the latch to
   between **0.5 and 0.65 V** with it.

The `min POR_RAW` column in `depth_results.md` shows why the `asbuilt` arm
stops responding where it does. Above the boundary the rail's collapse is a
*ratiometric* one — `POR_RAW` simply follows the rail down as a still-valid
logic high, or dips briefly and is swallowed by the deglitch dwell doing
precisely its designed job (visible at `ss`/125 °C/0.65 V, where `POR_RAW`
touches −23 mV for 100 ns and `RESETn` never moves). Below the boundary the
rail is too low for the block's own logic to hold any state: `POR_RAW`
genuinely deasserts, `PGDG` follows `VDD`, the push-pull `RESETn` output has
no supply to hold high, and the reset regenerates. **That is the rail
collapsing, not the POR mis-deciding.**

## Decision

**Recorded conclusion for issue #56's third acceptance question: 0.2 V is
*not* a representative glitch depth for a deglitch-rejection claim.** It sits
a factor of ~3 below the measured `VDD`-glitch immunity boundary and below
the level at which the block's own output stage still has a supply, so the
0/81 result measures the rail's collapse rather than anything the deglitch
function could be asked to reject. A check written at that depth cannot pass
on any topology that powers its output from the glitched rail, which
`por-glitch`'s own `tb.json` already half-concedes by leaving
`resetn_droop_during_glitch_v` unchecked.

Three concrete consequences are ratified here; the fourth is explicitly *not*
decided by this record:

1. **`spec/target-spec.md`'s `por-brownout` deglitch carve-out gains a
   measured `VDD`-level number.** The carve-out remains `POR_RAW`-scoped per
   DR-014, and this record adds: on the `VDD` axis the block is measured
   immune to a 300 ns excursion to **≥ 0.65 V** and measured to regenerate a
   full reset pulse at **≤ 0.5 V**, at both PVT points swept, with no
   duration dependence anywhere on that axis. No ratified value is added,
   removed or relaxed — this is a characterization citation, in the same
   shape as `por-brownout`'s falling-slew boundary.
2. **DR-014's "any depth" wording is corrected**, not by editing that record
   but by this one, which supersedes it on that single point. Its mechanism
   analysis stands.
3. **`XMRLK` is recorded as improving `VDD`-glitch immunity by >1 V of rail
   floor**, as a side effect of making the release one-way. That was not its
   purpose and is not why it landed, but it is measured, so it is recorded:
   without it the block re-asserts on a 300 ns dip to 1.4 V — a dip that
   never takes the rail below `VPOR↓,max` and that no spec row asks it to
   respond to.
4. **Whether `por-glitch`'s testbench should be re-cut at a depth above the
   boundary — and whether its criterion should change from "must never move"
   to "must regenerate exactly one correctly-shaped pulse" — is NOT decided
   here.** Both are spec-level judgments on a ratified row, which CLAUDE.md
   reserves for the ratification pass (#1). This record supplies the number
   that judgment needs and stops there. `sim/por-glitch/` is left exactly as
   written and its 0/81 result stands, correctly, as evidence about the depth
   it actually tests.

## Alternatives considered

- **Re-cut `por-glitch`'s glitch to 0.65 V (or 1.0 V) now and record a
  PASS.** Rejected, firmly. Changing a failing testbench's stimulus until it
  passes is the exact move CLAUDE.md forbids ("agents do not relax the
  ratified spec to make results pass"), and it would destroy the one thing
  the 0/81 result is good evidence *of*. The boundary belongs in a
  characterization record; moving the check belongs to #1.
- **Declare the 0/81 result a non-defect and close it on DR-014's mechanism
  alone.** Rejected — DR-014's own "any depth" claim turned out to be wrong,
  which is precisely the risk of closing a question on an unmeasured
  argument. The sweep was cheap (56 runs, ~6 min) and changed the conclusion.
- **Sweep depth only, not duration.** Rejected — the duration axis is the one
  DR-014 staked its strongest claim on, and it is the axis the testbench's
  own "well under the dwell" framing rests on. Confirming it costs 20 runs
  and converts an assertion into a measurement.
- **Extend the sweep to the full 81-point grid.** Rejected as the wrong tool:
  a control experiment characterises a mechanism at a few points, and the
  boundary already reproduces to within one step at two corners as far apart
  as `tt`/27 °C/3.30 V and `ss`/125 °C/2.97 V. If #1 decides to *claim* a
  `VDD`-glitch immunity depth, that claim needs its own testbench and its own
  full-grid record — which is exactly what this record does not pre-empt.

## Consequences

- **`sim/por-glitch/` stays 0/81 and stays failing.** That is the intended
  outcome of this record, not a shortfall of it: issue #56's acceptance
  criterion for this half was that *a conclusion be reached* on the depth,
  and the conclusion is that the depth is wrong for the claim — a spec
  question, not a design one.
- **A new control experiment is committed**
  (`sim/por-glitch/control/run_depth_sweep.py` + `depth_results.md`),
  re-runnable in ~6 minutes, alongside the existing mechanism probe. It is
  the first `control/` directory in this repo holding two independent
  controls; `sim/README.md` gains the rule that makes that legitimate.
- **What becomes harder.** Anyone re-cutting `por-glitch` now has to justify a
  depth against a measured boundary rather than against intuition, and has to
  say which side of it they mean to be on. That is the point, but it is more
  work than picking "full depth" was.
- **What is still unknown.** The boundary is bracketed to one sweep step
  (0.5 → 0.65 V) at two points, not resolved by bisection and not mapped over
  the grid, and the sweep holds the 100 ns rail edge fixed. Given
  [DR-011](DR-011-brownout-falling-slew-limit.md)'s finding that the *falling
  slew rate* is the discriminator for `por-brownout`, an edge-rate axis on
  this glitch is a plausible and unexamined third dimension.
