# DR-023: Narrow DR-011's "does not latch up or stay released" to what the recovery edge actually does at 8/81 corners

- **Status**: proposed
- **Date**: 2026-08-11
- **Decided by**: Loom Builder agent, issue #215

## Context

[DR-011](DR-011-brownout-falling-slew-limit.md)'s Consequences section
states, for dips falling faster than the ratified `dVDD/dt|fall,max`
envelope (2.30 mV/µs, [DR-019](DR-019-brownout-falling-slew-postlayout-recost.md)):

> The block recovers; it does not latch up or stay released.

That sentence is unqualified, and it is now measurably too broad.
`sim/por-brownout/`'s deck presents a ~1970 mV/µs falling edge — ~860× the
ratified bound, so nothing here violates a guarantee — but the *unguaranteed*
recovery-edge behaviour has moved between three otherwise-comparable runs:

| netlist | `t_reassert_us` | corners that never re-assert within the 55 ms run |
| --- | ---: | ---: |
| schematic, pre-`XMRLK` ([`20260801-233807-32fbaa0`](../../sim/por-brownout/records/20260801-233807-32fbaa0.md)) | 51.26–51.58 µs | 0 / 81 |
| schematic, today ([`20260811-112115-9807e3f`](../../sim/por-brownout/records/20260811-112115-9807e3f.md)) | 52.01–66.24 µs | **8 / 81** |
| extracted ([`20260811-065930-35a87a6`](../../sim/por-brownout/records/20260811-065930-35a87a6.md)) | 51.67–64.25 µs | 1 / 81 |

The 8 corners that never re-assert within the 55 ms run window are
`tt_-40c_2.97v`, `ss_-40c_{2.97,3.30}v`, `ss_27c_2.97v`,
`res_ff_-40c_2.97v`, `res_ss_-40c_2.97v`, `bjt_ff_-40c_2.97v`,
`bjt_ss_-40c_2.97v` — overwhelmingly the low-supply, mostly-cold corners.

**Root cause, already measured.** `sim/por-brownout/control/recovery_results.md`
runs the frozen pre-`XMRLK` deck beside today's schematic and extracted decks
at four representative points and finds `POR_RAW` still asserts on the
recovery edge in every arm, at **+46 to +53 µs** — the *decision* to
re-assert is unchanged. What has changed is *propagation*: `XMRLK`
([DR-016](DR-016-por-ramp-rate-chatter-release-latch.md), #56) now holds the
release one-way, which delays how quickly `POR_RAW`'s assertion reaches
`RESETn` — that is exactly the behaviour `XMRLK` was added to produce (a
one-way release, trading propagation latency for eliminating release-edge
chatter). `RESETn` ends every one of the control's 12 arms at the full rail
(2.970 V or 3.300 V, matching supply exactly), so nothing latches up
asserted; the 8/81 corners are recovery-window truncation (the deck's 55 ms
run ends before a delayed re-assertion completes), not a stuck or lost
decision.

This is a **known, deliberate trade whose second-order effect was never
written down** — not a defect discovered in the field. #215 asks that DR-011's
sentence be narrowed to say this positively rather than leaving an
unqualified "does not latch up" standing against a table that now shows 8/81
corners not re-asserting inside the run window it was measured against.

## Decision

**DR-011's Consequences sentence "The block recovers; it does not latch up or
stay released" is narrowed, by this record, to:**

For falling slews outside the ratified `dVDD/dt|fall,max` envelope, `RESETn`
re-asserts only on the **recovery** edge (never during the dip), and the
*decision* to re-assert is unaffected by `XMRLK` — `POR_RAW` asserts on the
recovery edge in every measured arm, at +46 to +53 µs after the dip begins.
What `XMRLK` costs is **propagation latency**, not the decision: at 8/81
corners (schematic, today's netlist) and 1/81 (extracted), that latency pushes
`RESETn`'s valid-low crossing past 55 ms of dip time, so the assertion —
present in `POR_RAW`, always — is not yet visible at `RESETn` within that
window. `RESETn` never latches up asserted at any corner in the control set:
every arm ends the run at the full supply rail. DR-011's claim is correct in
substance (the block does not latch up asserted, and the reset *decision*
is never lost) but was previously imprecise about propagation, which is not
unconditional across all corners within an arbitrary observation window.

This record does **not** modify DR-011's text in place — per this repo's
append-don't-rewrite convention (matching how [DR-019](DR-019-brownout-falling-slew-postlayout-recost.md)
handled the earlier falling-slew re-cost), DR-011 stands as originally
decided, and `spec/target-spec.md`'s `por-brownout` row now cites this record
alongside it.

## Alternatives considered

- **Edit DR-011's Consequences prose in place.** Rejected — this repo's
  decision-record convention (confirmed by DR-019, which added a new record
  rather than editing DR-011 when the falling-slew bound itself moved) is to
  supersede or narrow via a new record, keeping the original decision's
  context intact and auditable.
- **Treat this as a new defect and file a design fix.** Rejected — the
  control evidence shows `POR_RAW` asserting correctly in every arm; nothing
  is lost except propagation speed, and that speed cost is `XMRLK`'s known,
  deliberate trade ([DR-016](DR-016-por-ramp-rate-chatter-release-latch.md))
  for eliminating release-edge chatter. Re-litigating that trade is out of
  scope for a documentation-narrowing record and would need its own
  cost/benefit case.
- **Characterize the falling-slew rate at which `XMRLK` stops being crossed
  by the recovery edge (item (2) of #215's original body).** Explicitly
  deferred as a stretch goal by #215's own curation. It would need a new
  slew sweep (naturally landing in `sim/por-brownout-slew/` alongside
  DR-019's existing ladder) and is left to a follow-up issue rather than
  folded into this documentation-only change.
- **Leave the `por-brownout` row's placeholder ("routed to #215") standing
  until #1's overall ratification pass.** Rejected — the measurement and root
  cause are already complete (recorded in `recovery_results.md` before this
  issue was filed); there is no reason to defer writing down what is already
  known.

## Consequences

- DR-011's Consequences sentence is now understood, via this record, as
  scoped to *decision*, not to *observed propagation latency within a fixed
  run window* — a reader relying on the unqualified original sentence would
  wrongly conclude `RESETn` always reaches valid-low inside a 55 ms recovery
  window at every corner; it does not, at 8/81 corners on today's schematic
  netlist and 1/81 on the extracted netlist.
- `spec/target-spec.md`'s `por-brownout` row's placeholder text ("what
  narrows is DR-011's … routed to #215") is replaced with a citation to this
  record.
- No design change is made and no testbench bound is relaxed. `XMRLK` is
  unchanged; `sim/por-brownout/testbench/tb.json`'s bounds are unchanged; the
  0/81 (guaranteed-envelope) verdict for `sim/por-brownout/` is unaffected —
  that deck's edge remains ~860× outside the guaranteed falling-slew
  envelope, so none of this record's findings touch a ratified guarantee.
- **Follow-up left open, not resolved here**: at which falling slew does the
  recovery edge stop crossing `XMRLK` in time to reach `RESETn` within a
  practical window? DR-016 traded this deliberately for the release-edge
  chatter fix; #215's own body proposes this as a future characterization
  (naturally in `sim/por-brownout-slew/`) if an integrator's use case makes
  the answer load-bearing. It is not filed as a new issue by this record —
  #215 already names it as optional future work, and this record does not
  duplicate that routing.
