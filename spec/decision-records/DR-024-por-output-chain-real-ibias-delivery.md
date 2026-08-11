# DR-024: The real, shared-node `IBIAS` delivered to `por_output_chain` is 0.18x-0.61x nominal, not the idealised 0.5x-3x envelope, and no cheap lever closes the gap inside `por-iq`

- **Status**: proposed
- **Date**: 2026-08-11
- **Decided by**: Loom Builder agent, issue #221

## Context

[`design/por_output_chain.md`](../../design/por_output_chain.md)'s "Hand-off
to #11" section derives the cell's own tolerance to `IBIAS` magnitude by
running two idealised-current DUTs side by side: 3x nominal for the
`por-reset-pulse` floor, 0.5x nominal (0.25 uA) for the `por-brownout`
deglitch ceiling. That 0.5x figure was always a stand-in — `bias_core` had
not landed when it was chosen — and the same document's "#199: the two
hand-offs, answered" section later closed the question using
`sim/bias-core-designer-check/`'s `ibias_na` measurement (0.594x-2.236x
nominal) as if it were the current delivered to `por_output_chain`
specifically. It is not: that testbench loads `bias_core`'s output with a
single 2 um / 2 um diode standing in for `por_comparator` alone
([`sim/bias-core-designer-check/testbench/stimulus.spice`](../../sim/bias-core-designer-check/testbench/stimulus.spice)),
never instantiates `por_output_chain`, and — per
[DR-010](DR-010-shared-ibias-disabled-consumer-contract.md) — the real shared
`IBIAS` node is loaded by up to *three* consumer diodes at once
(`temp_core`, `por_comparator`, `por_output_chain`), not one. Issue #199's own
sibling testbench,
[`sim/bias-core-ibias-sharing/`](../../sim/bias-core-ibias-sharing/), does
model the real multi-consumer node, but its own fragment header states
`por_output_chain` "is NOT instantiated" — it was #12's unbuilt placeholder
when that testbench was written and nobody returned to add it once #12
closed. So no committed testbench, before this record, measured the current
`por_output_chain` actually receives on the real assembly. Issue #221 (itself
a correction of a bot-filed issue that cited two files and a decision record
that never existed — see the issue's "Curator Enhancement" — but whose
underlying concern the Curator verified as real and unresolved) asks for that
measurement, a lever, and this record.

**The missing measurement, now taken.**
[`sim/por-output-chain-ibias-sharing/`](../../sim/por-output-chain-ibias-sharing/)
extends `sim/bias-core-ibias-sharing/`'s fragment-splicing pattern
(`sim/build_tb.py`) to instantiate all four cells —
`bias_core`+`temp_core`+`por_comparator`+`por_output_chain` — with a
zero-volt ammeter in series with *each* consumer's own `IBIAS` pin, in two
branches on the same rail: `RESETn` asserted (`temp_core.EN`=0, high-Z per
DR-010) and `RESETn` released (`temp_core.EN`=1, its own mirror diode
rejoins the node). Full 81-point PVT grid, both schematic
([`records/20260811-142426-a9cdd7f.md`](../../sim/por-output-chain-ibias-sharing/records/20260811-142426-a9cdd7f.md))
and post-layout
([`records/20260811-142901-d43c0db.md`](../../sim/por-output-chain-ibias-sharing/records/20260811-142901-d43c0db.md),
against `layout/postlayout/{bias_core,temp_core,por_comparator,por_output_chain}.spice`):

| | asserted (`ibias_por_asserted_na`) | released (`ibias_por_released_na`) |
| --- | ---: | ---: |
| min (schematic) | 172.246 nA = 0.344x (`ss_-40c_2.97v`) | 91.0761 nA = 0.182x (`ss_-40c_2.97v`) |
| max (schematic) | 577.375 nA = 1.155x (`ff_125c_3.63v`) | 304.144 nA = 0.608x (`ff_125c_3.63v`) |
| min (post-layout) | 172.149 nA = 0.344x (`ss_-40c_2.97v`) | 91.0251 nA = 0.182x (`ss_-40c_2.97v`) |
| max (post-layout) | 577.042 nA = 1.154x (`ff_125c_3.63v`) | 303.970 nA = 0.608x (`ff_125c_3.63v`) |

Both netlist levels agree to 4 significant figures — the extraction's parasitic
model adds no series impedance on this path, consistent with
`design/por_output_chain.md`'s existing "`XMBD`/`IBIAS` watch item" finding.
**Released is the tighter state at every corner**, exactly as
`design/bias_core.md`'s "The shared `IBIAS` net" predicts (`temp_core`'s
mirror diode rejoining the node steps it down), and the worst point,
`ss_-40c_2.97v` released, sits at **0.182x nominal — well under the 0.44x
floor** `design/por_output_chain.md` derived, at both netlist levels. **61 of
81 PVT points** fall under the 220 nA (0.44x) floor in the released state,
identically at both netlist levels; 11 of 81 fall under it in the asserted
state too.

**The stress DUT is re-cut.**
[`sim/por-output-chain-deglitch/`](../../sim/por-output-chain-deglitch/)'s
half-`IBIAS` stress leg (`xdut2`) moves from the idealised 250 nA (0.5x) to
91.0251 nA (0.182x) — the measured post-layout worst case above, applied as a
single fixed value across the whole grid exactly as the 250 nA it replaces
was (see `sim/por-output-chain-ibias-sharing/testbench/stimulus.spice` for
why a fixed worst-case value, not a per-corner-matched one, is the right
stress direction). At this current the filter is frequently too slow to trip
*at all* inside the 10 us qualifying dip — `PGDG` droops and recovers as
`POR_RAW` returns high before `NDG` reaches the trip point — so the
crossing-time measurement the deck used to publish (`dwell_pgdg_halfib_us`,
a `.meas ... WHEN ... fall=1` directive) errors "out of interval" on most
corners instead of reporting a number. The check is restated as a voltage
floor instead (`pgdg_min_during_halfib_dip_v`, `max: 1.0`) so a corner that
never trips reports a clean FAIL rather than aborting the run; the
crossing-time measurement is kept, unchanged, for the DR-005-nominal DUT
(`xdut1`), which still resolves everywhere. The floor is sampled over the
qualifying dip **itself** (12.000–12.010 ms), not over a wider window, so
"`PGDG` below 1.0 V somewhere in this window" is exactly "dwell ≤ 10 µs" and
borrows no slack from after `POR_RAW` returns high.

**Result** (both new records, superseding
[`20260811-110622-d5b0168`](../../sim/por-output-chain-deglitch/records/20260811-110622-d5b0168.md)
and
[`20260811-110752-d5b0168`](../../sim/por-output-chain-deglitch/records/20260811-110752-d5b0168.md)):
[`20260811-150038-58e15a8`](../../sim/por-output-chain-deglitch/records/20260811-150038-58e15a8.md)
(schematic) is **79/81 FAIL**;
[`20260811-150342-0c44407`](../../sim/por-output-chain-deglitch/records/20260811-150342-0c44407.md)
(post-layout) is **57/81 FAIL**, on `pgdg_min_during_halfib_dip_v` alone —
every other check in both records is unaffected (still passing, per
`design/por_output_chain.md`'s unrelated results). On the schematic netlist
only **two** points resolve inside the qualifying dip at all (`ff_125c_2.97v`
at 0.161 V and `ff_125c_3.30v` at 0.615 V); the extracted netlist clears 24,
all of them at 125 °C or on the `ff`/`fs` process corners, because its own
drawn `XCDG`/`XCTIM` parasitics make the filter faster — the two levels do
**not** disagree about the delivered current, which they measure identically
to four significant figures. This is a real, structural finding, not a
margin miss: at the real delivered current, `por_output_chain`'s deglitch
filter rejects a qualifying `T_dip,min` brownout dip outright across most of
the PVT grid, exactly as the (fabricated-citation, correct-substance) original
filing of #221 described.

## Decision

**No lever from the acceptance criteria's menu of four is implemented by
this record.** The evidence above is enough to show why, with numbers rather
than argument, for three of the four; the fourth is explicitly reserved for a
human ratification pass. This record's decision is therefore: *publish the
real measurement, re-cut the stress DUT to it, and route the fix — not
invent one that does not survive its own arithmetic.*

**1. Scale `bias_core`'s output leg (`XMPIB`) — infeasible inside the
`por-iq` ceiling, by the numbers.** `XMPIB`'s delivered current already
spans **297-1119 nA (a 3.77x hot/cold ratio)** across the grid
(`sim/bias-core-designer-check/`), a property of the bandgap-referenced
mirror's own temperature coefficient, not of this cell's loading. Scaling
`XMPIB`'s width scales that whole curve, hot end included: to lift the
released-state floor from 91 nA to the required 220 nA needs roughly a 2.42x
widening (`220/91.08`), which would put the *hot*-corner leg current at
roughly `1119 * 2.42 = 2708 nA` — on top of `design/bias_core.md`'s own
apportionment at that corner (929 nA core + 292 nA `por_comparator` + 31.6 nA
`por_output_chain` own draw = 1252.6 nA before the `IBIAS` leg), for a total
around **3.96 uA against DR-018's 3.0 uA ceiling**, a 32% overrun. The same
arithmetic rules out a same-topology **dedicated second output leg** for
`por_output_chain` (candidate 3, taken literally): DR-018's own remaining
headroom at the binding corner is 615.4 nA (`3000 - 2384.6`), and the
297/1119 nA hot/cold ratio measured on the existing leg means *any*
same-topology leg sized to clear 220 nA at the cold corner needs at least
`220 / (297/1119) = 828` nA at the hot corner — already 213 nA over the
*entire* remaining budget, before `bias_core`'s core or either consumer's own
draw is even added back in. **The hot/cold ratio of this reference current is
worse than the ratio `por-iq`'s headroom can absorb; no proportional scaling
of the existing mirror closes both ends at once.** This is a genuine finding
about the reference architecture, not a sizing miss on any one device.

**2. Re-ratio the consumer mirror diodes — reopens two closed cells' own
internal sizing, not a local resize.** `por_output_chain`'s `XMBD` is not a
passive tap on the shared node: every internal reference current in the cell
(`XMN1`'s 10 nA leg, the 50 nA deglitch tails, the 2.5 nA timer charge
current) is *mirrored off `XMBD`'s own gate*, at ratios
`design/por_output_chain.md`'s "Device sizing" table states as fixed numbers
(1:50, 1:4, ...) derived against the *current* `XMBD` geometry and the *node
voltage that geometry produces at 500 nA nominal*. Widening `XMBD` to draw a
larger share of the shared current also re-tunes those ratios — the entire
"IBIAS envelope 0.5x-3x nominal" analysis this document (and this record)
lean on assumes `por_output_chain`'s *own* internal ratios are fixed while
only the *external* current varies; resizing `XMBD` breaks that assumption
outright and would require re-deriving the deglitch dwell bounds, the
one-shot pulse width and the trip detector from scratch — a re-spin of
issue #12's closed design, not a parameter tweak. The same objection applies
symmetrically to `por_comparator`'s `XMBD` (2 um / 2 um, `MTAIL` is "1:20
against `MBD`" per `design/por_comparator.md`'s "Device sizing" table):
resizing it to divert current elsewhere re-tunes `por_comparator`'s own tail
bias, threshold accuracy and Iq, reopening issue #10's closed, ratified
threshold-accuracy result. Doing this correctly needs its own
scoped issue against #10 and/or #12, not a device-value edit inside this
record.

**3. Re-cost `T_dip,min` at the spec level — explicitly not this record's
call.** The curator-revised Implementation Guidance for #221 is direct: this
lever is spec-level and belongs to whoever ratifies `spec/target-spec.md`
changes, filed as a new spec-change issue since #1 is closed — not decided
inside a Builder-authored decision record. CLAUDE.md's "agents do not relax
the ratified spec to make results pass" governs exactly this case: raising
`T_dip,min` would make today's FAIL a PASS by asking the block to tolerate a
*shorter* real brownout dip than 10 us, a product-behavior change a human
should make deliberately, with this record's numbers in hand, not one this
record makes unilaterally to close its own finding.

**What this record does do:**

- Publishes the real measurement (`sim/por-output-chain-ibias-sharing/`, two
  netlist levels, 81-point grid, both `RESETn` states) as the answer to
  #221's first acceptance criterion, replacing the fabricated citation the
  original bot-filed issue body relied on.
- Re-cuts `sim/por-output-chain-deglitch/`'s stress DUT to that real number
  and records the (expected, per #221's acceptance criteria) FAIL.
- States, with arithmetic rather than assertion, why the two cheapest levers
  do not close inside the `por-iq` budget DR-018 already ratified, and why
  the third needs a scoped redesign of one or both of two closed cells
  rather than a value edit here.
- Leaves the fourth lever — the only one that could close the gap without
  new analog design or a `por-iq` renegotiation — explicitly to a human via a
  new spec-change issue, per CLAUDE.md and the curator's own routing.

**No ratified row in `spec/target-spec.md` is added, removed or relaxed by
this record.** `por-brownout`'s `T_dip,min` = 10 us stands exactly as
ratified.

## Alternatives considered

- **Implement lever 1 or 3 anyway, accepting the `por-iq` overrun and filing
  a second re-cost record alongside this one.** Rejected. DR-018 re-cost
  `por-iq` to 3.0 uA from measured reality just one issue ago; re-costing it a
  second time in the same change that creates the new overrun, purely to make
  that overrun disappear, is exactly the "relax the spec to make the result
  pass" pattern CLAUDE.md forbids, dressed up as two separate decisions. If
  `por-iq` needs to move again, it needs its own measured justification
  independent of this record's convenience.
- **Implement lever 2 (re-ratio) with a "best-effort" resize of
  `por_output_chain`'s `XMBD` alone, without touching `por_comparator`.**
  Rejected for this record. It is the least-bad physical lever, and a real
  candidate for a follow-up — but landing it responsibly means re-deriving
  this cell's own dwell/pulse/trip sizing against the new internal ratios and
  re-running its full three-testbench suite (`por-output-chain-pulse`,
  `-deglitch`, `-floor`) plus a full re-extraction and DRC/LVS pass
  (`layout/build_cells.py`, `layout/run_checks.sh`), none of which this
  record's evidence-gathering scope reaches. Landing a resize without that
  work would be exactly the "claim without a testbench" CLAUDE.md forbids,
  just one cell removed from where the claim is made.
- **Decide lever 4 (re-cost `T_dip,min`) here, since the arithmetic above
  already makes the other three look unattractive.** Rejected outright — see
  Decision, item 3. The curator's own routing for #221 is explicit that this
  belongs to a human via a new issue, and CLAUDE.md's spec-relaxation rule
  does not bend because the alternative levers are all expensive.
- **Leave the idealised 0.5x stress DUT in place and only publish the
  measurement.** Rejected — #221's acceptance criteria are explicit that the
  stress DUT must be re-cut to the real delivered current "so the 81-point
  grid measures the real ceiling rather than an assumed one," and an
  unchanged 0.5x DUT would keep publishing a PASS record
  (`20260811-110622-d5b0168` / `20260811-110752-d5b0168`) that this record's
  own measurement shows is not representative of what the assembly delivers.

## Consequences

**`design/por_output_chain.md`'s "#199: the two hand-offs, answered" section
is wrong and needs correcting.** Its claim that #11's envelope "closes
cleanly in this cell's favor" rests on `sim/bias-core-designer-check/`'s
single-consumer `ibias_na` measurement, which this record shows is not what
`por_output_chain` receives on the real assembly. A follow-up documentation
pass should replace that section's table with this record's numbers and its
"favorable, no ratified value moves" conclusion with a pointer to this
record.

**`sim/por-output-chain-deglitch/`'s committed record now FAILS its own
`por-brownout` check** (`pgdg_min_during_halfib_dip_v`, 79/81 schematic,
57/81 post-layout FAIL) where the prior committed record
(`20260811-110622-d5b0168` / `20260811-110752-d5b0168`) PASSED 81/81. This is
the expected, correct outcome per #221's acceptance criteria — the prior
record measured an idealised stress condition the assembly does not actually
produce. Both new records supersede the ones they replace; neither prior
record is edited or deleted, per the append-only rule.

**`por-iq` is untouched.** No circuit changes accompany this record, so
DR-018's 3.0 uA ceiling, `sim/bias-core-designer-check/`,
`sim/temp-por-top-release/` and every other `por-iq`/`iq-total` evidence file
stand exactly as last measured — the regression re-run #221's acceptance
criteria conditions on "if the lever chosen changes `por-iq`" does not apply,
because no lever lands here.

**Two follow-up issues are the concrete path forward**, filed alongside this
record:

1. **[#235](https://github.com/2AMLogic/gf180-temp-por/issues/235)** — a
   scoped redesign issue against `por_output_chain` (#12) and
   `por_comparator` (#10) to re-ratio the shared node's consumer diodes
   (lever 2), including the full re-derivation and re-verification work item
   2 above describes — the only lever of the four that can close the gap
   without either a `por-iq` renegotiation or a human spec-level call.
2. **[#236](https://github.com/2AMLogic/gf180-temp-por/issues/236)** — a
   spec-change issue proposing `T_dip,min`'s re-cost (lever 4), carrying
   this record's measured 0.182x-0.608x delivered-current range and the
   arithmetic above showing why the circuit-level levers are each
   expensive, for whoever holds spec-ratification authority to weigh against
   the block's actual brownout-immunity requirement. It is labelled
   `loom:operator-decision` rather than left in the agent queue, for the
   reason Decision item 3 gives.

**The friction-protocol trigger does not apply here.** No klayout-tools gap
was hit — no layout work was attempted in this record, by design (see
Decision, items 1-2).
