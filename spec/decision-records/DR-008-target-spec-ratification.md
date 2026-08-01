# DR-008: Target spec ratification

- **Status**: ratified
- **Date**: 2026-07-31
- **Decided by**: Robb (operator), via comment on issue #1, 2026-07-31T22:14:47Z

## Context

Issue #1 has carried the standing 2026-07-28 delegation that design/sim work
may proceed against the DRAFT spec, but that formal ratification by Robb is
required before layout work locks to it. That delegation could not be
exercised until the ratification object itself existed: the pre-publication
README rewrite (`3abcbd7`) deleted the numeric "Target specification" table
issue #1's checklist pointed at, leaving nothing in one place to rule on.

[DR-007](DR-007-spec-table-amendments.md) closed that gap. It reconstructed
the deleted table as [`spec/target-spec.md`](../target-spec.md) — the
block's single consolidated target-spec table — and folded in eight
amendments (A1–A8) from the spec-review skill opinion posted on issue #1
(spec-review skill opinion, klayout-tools #124: ratify-with-amendments).
DR-007 explicitly declined to ratify anything itself, reserving that call to
the operator.

The operator ratified on issue #1, via comment posted 2026-07-31T22:14:47Z:
"Robb ratified the target spec conditional on the amendments in #32
(spec-review opinion accepted) ... This issue closes when the amended table
merges." The amended table merged via PR #33 on 2026-07-31, satisfying that
condition. This record transcribes that ratification into `spec/`; it does
not itself make any new ruling on a row's value.

## Decision

`spec/target-spec.md` is **ratified** as the block's single consolidated
target-spec table, **conditional on the amendments in DR-007 exactly as
tabled** — nothing about the table's content changes as part of this
ratification.

In particular, ratification of the table as a whole does **not** upgrade any
individual row beyond what its own per-row status column already states:

- Rows tagged **`conditional #15`** (both accuracy rows, both POR threshold
  edges VPOR↑/VPOR↓, and hysteresis — the mismatch-dominated 3σ rows per
  DR-007 amendment A5) remain conditionally ratifiable pending #15's
  mismatch/MC data. Ratifying the table ratifies these as *targets*, not as
  evidenced results.
- Rows tagged **`TBD-#n`** (e.g. `por-digital-min-vdd`, the externally-owned
  downstream digital domain minimum VDD; `por-reset-valid-floor`; the V(T)
  transfer slope/range; the area budget) remain open and unratified pending
  their named owning issue.

These carve-outs are the table's own §7/§8 per-row status tags and survive
this ratification unchanged; this record ratifies the table as the spec
object, not any TBD value it has not yet received.

## Alternatives considered

- **Ratify only the rows without a `conditional`/`TBD` tag, and leave the
  table's overall status as DRAFT** — rejected. The table's own per-row tags
  already carry that distinction; a second, coarser ratified/unratified line
  at the table level would either duplicate or contradict the row-level
  truth. Flipping the table's Status line to RATIFIED while leaving the
  row-level tags untouched keeps a single source of truth per row.
- **Wait for #15 (mismatch/MC data) before ratifying at all** — rejected.
  The operator's ratification comment is explicit that the condition was
  DR-007's amendments merging, not #15 landing; #15 is scoped as its own
  follow-on that resolves specific rows, not a precondition for ratifying
  the table as an object. The layout-lock gate needs the table ratified now;
  the conditional rows stay conditional either way.

## Consequences

- **The layout-lock gate (2026-07-28 delegation) is satisfied.** Formal
  ratification by the operator, required before layout work locks to the
  spec, has occurred.
- **Layout-stage issues (#16, #17, #18) may unblock** once this record
  lands, subject to whatever row-level conditions (`conditional #15`,
  `TBD-#n`) still apply to the specific rows each of them depends on.
- **#10–#14 still need their own dependency-checkbox follow-up pass.** Each
  lists `#1: ratified spec` as an open dependency and cross-references issue
  #1; closing #1 does not by itself update those checkboxes, and at least
  one (#10) has already been flagged as needing more than a checkbox flip
  since DR-007's split VPOR↑/VPOR↓ rows and bounded hysteresis materially
  change its stated targets. That pass is out of scope for this record —
  noted here only as a forward pointer.
- No numeric value, per-row status tag, or DR-007 ruling changes as a result
  of this record.
