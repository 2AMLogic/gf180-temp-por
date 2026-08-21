# DR-007: Spec table reconstructed as an artifact, with the review's amendments

- **Status**: ratified (see [DR-008](DR-008-target-spec-ratification.md))
- **Date**: 2026-07-31
- **Decided by**: Loom Builder agent, issue #32

## Context

The pre-publication README rewrite (commit `3abcbd7`) removed the numeric
"Target specification" table and did not relocate it. The spec values
survived only as prose scattered across DR-001…DR-005 and issue #1's own
description, and #1's operator ratification checklist still instructed the
operator to "review each of the 8 draft rows in `README.md` → Target
specification" — a section that no longer exists. **The ratification object
was not written down anywhere**, so #1 was unratifiable as a matter of
mechanics, independent of whether the numbers were right.

The spec review posted on #1 (spec-review skill opinion, klayout-tools #124)
returned **ratify-with-amendments** and listed eight amendments, A1–A8. Issue
#32 is those amendments. Beyond the missing artifact, the review found: the
POR threshold named neither of its two edges; hysteresis was one-sided, so an
arbitrarily large value would pass while dragging the assert threshold toward
the downstream logic's floor; no ramp-rate envelope and no brownout statement
existed at all, though #14 is chartered to test both; no row stated its
statistical basis, which changes an accuracy target's meaning by roughly 2×;
the V(T) transfer characteristic through which DR-002 judges accuracy was
itself unspecified; the shared bias core's current was owned by neither Iq
row; the POR Iq stretch sat below the floor of DR-005's own estimate for the
ratified topology; and no row named a binding corner, nor did area or
self-heating rows exist.

None of that re-opens a topology decision. DR-001…DR-006 stand exactly as
recorded.

## Decision

**Create [`spec/target-spec.md`](../target-spec.md) as the single consolidated
target-spec table — the object #1 ratifies** — carrying every row of the
deleted README table plus the rows A2–A8 identified as missing, with
`target / stretch / conditions / binding corner / basis / source` columns and
a stable anchor ID per row. `README.md` links to it and carries no numbers
(the publication audit removed them deliberately; that boundary is
preserved). The specific rulings the table encodes:

1. **Threshold pair (A2).** "2.6 V ±5 %" is the **release (rising)**
   threshold, VPOR↑ = 2.47 / 2.60 / 2.73 V. The assert edge VPOR↓ becomes its
   own min/typ/max row, *constructed* from VPOR↑ and V_hys rather than
   independently specified, so the pair cannot drift apart under a later
   re-cost of either parent. Hysteresis gains an upper bound (250 mV) chosen
   as the largest value that keeps VPOR↓,min at 2.22 V, and a new row records
   the binding inequality VPOR↓,min ≥ V_DIG,min against the downstream
   digital domain's minimum operating VDD (integrator-supplied, so it is
   marked TBD with the self-consistency requirement V_DIG,min ≤ 2.22 V
   stated).
2. **Ramp envelope (A3).** Correct reset generation is guaranteed for
   monotonic ramps between **1 V/s and 1 V/µs**, with "correct" defined
   behaviorally (low from 0 V, released once, no glitch, no double pulse).
   Both limits bind at SS/−40 °C.
3. **Brownout (A4).** **No dedicated brownout detector in wave 1**;
   re-assertion is whatever the POR comparator provides, guaranteed for dips
   below VPOR↓,min = 2.22 V lasting ≥10 µs, with shallower/shorter dips
   explicitly *not* guaranteed (that rejection is #12's deglitch function,
   which DR-005 deliberately separates from hysteresis).
4. **Statistical basis (A5).** Accuracy and threshold rows are **3σ including
   local mismatch** (MC, N ≥ 500, at the binding corner); budget/limit rows
   are **corner-worst-case**. Since `sim/devchar` is deterministic-corners-only
   by its own admission and both row groups are mismatch-dominated, every 3σ
   row is marked **conditionally ratifiable pending #15**.
5. **Temp-sensor instrument rows (A6).** The V(T) transfer characteristic
   becomes an explicit row (slope/range TBD-#9/#13, with a headroom bound so
   the output stays observable at 2.97 V), the 1-point/25 °C/PTAT-gain trim
   strategy becomes a row rather than DR-005 prose, and resolution /
   conversion rate is explicitly **N/A (analog out)** rather than silent.
6. **Iq accounting (A7).** `por-iq` is quoted in the always-on state
   (`RESETn` asserted, sensor disabled) and **includes** whatever part of the
   shared bias core must be live for the threshold decision in that state;
   `temp-iq` is the **incremental** current above it; a new `iq-total` row
   makes them sum. Both bind at FF/+125 °C/3.63 V. The **<0.3 µA POR Iq
   stretch is withdrawn as "requires architecture revision"** — it is below
   the floor of DR-005's own 0.3–0.8 µA estimate for the chosen topology.
7. **Binding corners, area, self-heating, reset-valid floor (A8).** Every row
   names the corner that sets its hard edge; area gets a ≤0.05 mm² planning
   budget explicitly marked TBD-#17; self-heating gets a ≤0.1 °C
   budget-derived row; and the numeric reset-valid floor DR-004 requires #12
   to state ("`RESETn` valid-low for VDD ≥ X") gets a row to receive it,
   target 0 V.

Every number that did not previously exist is tagged **[P]** in the table and
indexed in its §7 worksheet, so ratification can rule on each one
individually rather than accepting a wall of text. No target value carried
from the deleted README table was loosened.

## Alternatives considered

- **Restore the numeric table to `README.md`** — rejected. The publication
  audit removed those numbers on purpose, and a link costs nothing and keeps
  both properties. (*2026-08-21 note: the operator has since ruled the numeric
  spec values public-safe; the link-not-table choice stands on its own merits
  — one source of truth in `spec/`, no duplicated table to drift.*)
- **Reconstruct the table only, and leave A2–A8 to later issues** — rejected.
  A table that still names neither threshold edge, still has no ramp or
  brownout row, and still states no statistical basis would be ratifiable in
  form only: #14 would go on testing ramps and brownout dips against nothing,
  which is the exact failure the review flagged.
- **Set the POR Iq stretch aside silently, or delete the row** — rejected.
  Deleting it destroys the audit trail of a target that was once stated;
  re-labelling it "requires architecture revision" keeps the history visible
  and names what restoring it would cost.
- **Charge the shared bias core to `temp-iq` (DR-005's implicit reading) and
  quote `por-iq` as the comparator's incremental current** — rejected. It
  makes the <1 µA number look comfortable by excluding current that is
  demonstrably flowing while `RESETn` is asserted (DR-005's own startup
  ordering brings the core up *before* release). The accounting chosen
  instead surfaces the conflict as a named risk owned by #11 rather than
  hiding it in a column definition.
- **Pick numbers for the TBD rows anyway** (V(T) slope, V_DIG,min, deglitch
  dwell, area) — rejected. Those belong to issues that own the underlying
  design or to the integrator; inventing them would create spec values with
  no basis, which is worse than a TBD with a named owner.

## Consequences

- **#1 becomes ratifiable.** The checklist points at a real artifact, and §7
  gives the operator a line-by-line worksheet of exactly what is new.
- **#14 gains numeric pass/fail bounds** for its ramp and brownout
  testbenches, which previously asserted against nothing; **#13** gains a
  supply-sensitivity target and a headroom bound on the sensor output;
  **#12** gains a numeric reset-valid floor and a ≤10 µs ceiling on its
  deglitch dwell; **#10/#11** inherit the Iq accounting risk explicitly.
- **#15 becomes load-bearing for ratification, not optional**: four rows
  (both accuracy rows, both threshold edges plus hysteresis) are conditional
  on its mismatch data, and it may force a re-cost — through a new decision
  record, not a silent edit.
- **`sim/` evidence records can now cite a real anchor.** `sim/README.md` and
  `sim/harness/README.md` previously used `spec/temp-por.md#…` as a
  placeholder path for a file that never landed; those references are
  repointed at `spec/target-spec.md#temp-accuracy-untrimmed`, which resolves.
  Per `sim/README.md`, every ratified row must map to a `sim/<slug>/`
  experiment, so this table also becomes the coverage map's left-hand column —
  and it now has more rows than there are experiments, i.e. the coverage holes
  are visible rather than absent.
- **Bad consequence, stated plainly**: the table's [P] values are engineering
  proposals made without block-level simulation evidence (none exists yet —
  every sub-circuit in `design/` is a placeholder). They are the review's
  requested numbers, argued from DR-005's estimates, the devchar data, and
  standard practice, but they are not measured. Ratifying them fixes targets
  that #11/#13/#14 may prove uncomfortable; the honest failure mode is a
  re-cost through a superseding record, and the alternative — leaving the
  lines blank — has already been tried and produced testbenches with nothing
  to assert against.
- No topology decision from DR-001…DR-006 is altered by this record.
