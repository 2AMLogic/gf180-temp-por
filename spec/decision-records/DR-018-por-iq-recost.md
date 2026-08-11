# DR-018: Re-cost `por-iq` to <3.0 µA to match the measured apportionment overrun

- **Status**: proposed
- **Date**: 2026-08-11
- **Decided by**: Loom Builder agent, issue #189

## Context

`spec/target-spec.md#por-iq` ratifies **<1 µA** for the block's quiescent
current in the always-on state (`RESETn` asserted, temperature sensor
disabled, per §5 rule 1). The full four-cell assembly has never met it, and
the miss is architecture-level, not a sizing slip:

- **`design/bias_core.md`'s "Iq apportionment"** sums the binding-corner
  (FF / +125 °C / 3.63 V) draw of every branch that must conduct for the POR
  decision in the reset-asserted state: `bias_core` core 929 nA +
  `bias_core`'s `IBIAS` output leg 1119 nA + `por_comparator` 292 nA +
  `por_output_chain` 31.6 nA = **2371 nA, 2.37× the 1 µA budget**, from
  per-cell records.
- **Schematic-level, measured on the real assembled block**
  (`sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md`, derived
  from `sim/temp-accuracy-vt/`'s raw per-point measurements on
  `design/netlist/temp_por_top.spice`): **0.656667–2.384647 µA** over the
  full 81-point grid, binding corner `ff_125c_3.63v` (2.384647 µA), **27/81
  PASS, 54/81 FAIL** against the ratified 1.0 µA ceiling. This is independent
  corroboration of the apportionment sum above (2371 nA vs. 2384.6 nA
  measured — a 0.6 % difference attributable to real loading interactions
  across the assembled netlist that a per-cell sum cannot capture).
- **Post-layout, measured on the klt-extracted assembly** (#87,
  `sim/temp-por-top-release/records/20260811-064427-564950b.md`, against
  `layout/postlayout/temp_por_top.spice` — 238 drawn devices, 136/159 nets
  carrying real parasitic R/C, per `layout/postlayout/AUDIT.md`):
  **0.656367–2.38347 µA**, binding corner `ff_125c_3.63v` (2.38347 µA), same
  **54/81 FAIL**, same binding corner. The extracted netlist reads
  **uniformly ~0.05 % lower** than the schematic record at every one of the
  81 points and fails at exactly the same corners. This closes off "layout
  might absorb some of it" as a live possibility: the overrun is a design
  magnitude problem, not a parasitic or layout one, confirmed at both
  netlist levels.

`target-spec.md`'s own row text has carried this as `pending #1 (measured;
re-cost decision pending)` since it was first published (DR-010's record),
and CLAUDE.md / `target-spec.md` §5 forbid closing the gap by silently
relaxing the ratified number — a decision record is required. This record is
that decision, and it is authorized to act now, without waiting on any
further layout work: the evidence above already rests on both netlist
levels and both agree.

**Scope note.** `design/bias_core.md` also documents a *second*,
independent conflict under "The starved-loop window" / "Why it cannot be
fixed inside this cell's Iq budget": at the ratified fast end of
`por-ramp-rate` (1 V/µs), the amplifier cannot slew fast enough to keep the
loop's bias valid, and a rail-referenced fix for *that* would need
additional Iq this budget does not have either. That document frames three
options for resolving *that* tension, the same three options named in this
issue. This record resolves **only** the static apportionment overrun above
(design/bias_core.md's "conflict 1") — the number the block already draws
today, with no new device and no additional starved-loop-detector current
folded in. The starved-loop window ("conflict 2") remains open and
unaffected; see Consequences.

## Decision

**`spec/target-spec.md#por-iq`'s target moves from <1 µA to <3.0 µA**,
[CWC], binding corner unchanged (FF / +125 °C / 3.63 V). The <0.3 µA stretch
stays withdrawn (`design/bias_core.md`'s arithmetic in "Why it cannot be
fixed inside this cell's Iq budget" shows no rail-referenced nA-class
detector exists in this PDK at this scale; nothing here changes that).

**Margin, computed against the measured worst case, not asserted:**

| | Value |
| --- | --- |
| Measured max, schematic (`ff_125c_3.63v`) | 2.384647 µA |
| Measured max, post-layout (`ff_125c_3.63v`) | 2.383470 µA |
| New ceiling | **3.0 µA** |
| Margin at the ceiling, schematic worst case | (3.0 − 2.384647) / 3.0 = **20.5 %** |
| Ceiling as a multiple of measured worst case | 3.0 / 2.384647 = **1.258×** |
| Ceiling as a multiple of the withdrawn 1.0 µA target | **3×** |

20.5 % margin at the new ceiling matches the convention already in use
elsewhere in this table for corner-worst-case budget rows measured against a
[CWC] ceiling — `temp-iq`'s <20 µA ceiling carries 20.5 % margin over its own
measured 15.90 µA max ((20−15.90)/20 = 20.5 %). Setting the ceiling at
exactly the measured max (2.385 µA) was rejected: it would leave zero margin
for re-runs against a slightly different tool or PDK point release, and
every other CWC row in this table carries real margin over its own measured
worst case.

**`spec/target-spec.md#iq-total`'s ratified <21 µA target is unchanged.**
Full reasoning and the arithmetic that shows why it is unaffected is in
Consequences below. §5 rule 3's description of `iq-total` as "the sum" of
`por-iq` and `temp-iq`'s targets is amended: after this record, 3.0 µA +
20 µA = 23 µA ≠ 21 µA, so `iq-total`'s ceiling is no longer the literal
algebraic sum of the two sub-row targets. It stands from here on as an
**independently-ratified ceiling**, still directly verified against measured
evidence (`sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md`'s
`iq_total_ua` column), not reconstructed from the two sub-budgets.

## Alternatives considered

- **Re-cost `por-ramp-rate`'s fast limit down to the measured 0.36 V/µs**
  (option 2 in `design/bias_core.md`'s "Why it cannot be fixed inside this
  cell's Iq budget", and in issue #189). **Rejected for this decision — it
  does not address the problem this record exists to close.** The measured
  2.385 µA `por-iq` already includes the full apportionment of the *current,
  already-built* circuit: `bias_core`'s core and `IBIAS` leg,
  `por_comparator`, and `por_output_chain`, exactly as built today. No
  rail-referenced starve detector exists in that circuit and none of its
  current is folded into the 2.385 µA figure. Lowering `por-ramp-rate`'s
  fast limit, on its own, frees budget for a *future* detector that has not
  been designed or built — it does not reduce the 2.385 µA measured today by
  one nanoamp. Recasting that row now, with no accompanying design change,
  would be a spec change with no measurement behind the number it would
  enable and no effect on the miss this record addresses. It remains a live,
  separate option for the starved-loop window (`design/bias_core.md`'s
  "conflict 2"), to be decided if and when that tension is actually taken
  up — see Consequences.
- **A different architecture change (option 3)** — specifically, gating
  `bias_core`'s `IBIAS` output on `RESETn` to recover the ~1 µA leg.
  **Already ruled out by [DR-010](DR-010-shared-ibias-disabled-consumer-contract.md)**:
  `por_comparator` and `por_output_chain` consume `IBIAS` precisely while
  `RESETn` is asserted, so gating the source there would starve the POR
  decision itself rather than the sensor. No other architecture change is
  proposed anywhere in this repo's design documents that reduces the
  apportionment without new circuit design: `design/bias_core.md`'s own
  arithmetic shows even a "free" `IBIAS` leg (929 nA core + 292 nA comparator
  + 31.6 nA output chain = 1252.6 nA) would still be over budget, and halving
  the core's own draw again costs quadratic resistor area (`R2` would grow
  to 12.6 MΩ, ~16 400 µm² of poly, roughly a third of the whole block's
  ≤0.05 mm² planning budget on one resistor) while slowing the settling loop
  further and worsening the starved-loop window. No such redesign is
  in-scope for this decision record, which documents an accounting
  correction against an already-measured, already-closed design (`bias_core`
  #11, `por_comparator` #10, `por_output_chain` #12 are all closed), not a
  new design effort.
- **Setting the new ceiling higher than 3.0 µA (e.g. 4–5 µA) "to be safe."**
  **Rejected as unjustified inflation.** 3.0 µA already carries 20.5 %
  margin over the measured worst case at both netlist levels and matches the
  margin convention this table already uses for `temp-iq`; a larger number
  would not be backed by any measurement and would invite the budget to
  drift further from what the circuit actually needs.
- **Declining to re-cost and leaving the row `pending #1` indefinitely.**
  **Rejected.** CLAUDE.md requires verification with no claim left dangling,
  and the row has already carried `pending #1 (measured; re-cost decision
  pending)` since 2026-08-01 across two independent netlist-level
  confirmations (schematic, then post-layout). The evidence needed to decide
  is exhaustive and repeatedly confirmed; deferring further adds no
  information.

## Consequences

**`por-iq` moves from "not met" to "met."** Against the new 3.0 µA ceiling,
all 81 points of both the schematic record
(`sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md`, max
2.384647 µA) and the post-layout record
(`sim/temp-por-top-release/records/20260811-064427-564950b.md`, max
2.38347 µA) pass, with 20.5 % margin at the binding corner on both. The
underlying `sim/` evidence files are append-only and are **not** edited —
their own recorded PASS/FAIL columns are against the checks their own
`tb.json` encoded at the time they ran (the pre-DR-018 1.0 µA bound) and
stand exactly as measured. `spec/target-spec.md`'s prose is what changes,
to state the row against its newly-ratified ceiling.

**A known follow-up, explicitly not done here.** Several `sim/` testbenches
(`sim/bias-core-designer-check/`, `sim/temp-por-top-release/`, and the
`por-iq`/`iq-total` derivation itself) still encode the withdrawn 1.0 µA
bound in their own `tb.json` check thresholds. This record does not edit
any `tb.json` file or re-run any simulation — per issue #189 this is a
spec/design decision, not a simulation-running task, and no `sim/` evidence
is touched. A future mechanical follow-up should move those check bounds to
3.0 µA so that new runs report PASS/FAIL against the currently-ratified
target directly, rather than against a value this record has superseded.
Until that lands, a reader comparing a fresh `sim/` run's own verdict
against `target-spec.md`'s prose should trust the prose (which cites this
record), not the testbench's own bound.

**`iq-total`'s <21 µA target is unaffected, and here is the check the
acceptance criteria for this record require:** no circuit changes as a
result of this record — only the recorded `por-iq` ceiling moves to match
already-measured reality. `iq-total`'s own measured range
(6.456521–18.287860 µA, binding corner `ff_125c_3.63v`,
`sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md`) is
unchanged, so its margin against <21 µA stays exactly what it was:
(21 − 18.28786) / 21 = **12.9 %** at the binding corner, 81/81 PASS. This
record does not touch that evidence or that row's ratified value.

**But the *definitional* relationship between the two rows does change, and
that is a real, not merely cosmetic, consequence.** Before this record,
`iq-total`'s <21 µA ceiling was constructed as the literal sum of `por-iq`'s
(<1 µA) and `temp-iq`'s (<20 µA) own ceilings — by design, any circuit
individually meeting both sub-ceilings was structurally guaranteed to meet
`iq-total` too. After this record, 3.0 µA + 20 µA = 23 µA > 21 µA: that
structural guarantee is gone. A future revision to either `bias_core`,
`por_comparator`, or `por_output_chain` that stays within `por-iq`'s new
3.0 µA ceiling and within `temp-iq`'s existing 20 µA ceiling is **not**
automatically guaranteed to keep `iq-total` under 21 µA — the two rows'
binding corners happen to coincide today (both bind at `ff_125c_3.63v`), and
today's actual measured sum (18.288 µA) has real headroom, but that headroom
is now an empirical fact about the current design, not a consequence of the
two ceilings by construction. Any future design change to either cell
must re-verify `iq-total` directly against its own <21 µA ceiling rather
than assuming compliance with the two sub-ceilings suffices. `§5 rule 3` in
`target-spec.md` is amended to say this explicitly.

**`temp-self-heating`'s power-budget derivation is unaffected.** It is
computed from `iq-total`'s *ratified ceiling* (≈76 µW at 3.63 V), which this
record does not change, so no re-derivation is needed.

**The starved-loop window remains open, and this record does not touch it.**
`design/bias_core.md`'s "The starved-loop window" documents a measured,
separate defect (false-valid `BIAS_OK` during a fast ramp or brownout
collapse, because the loop cannot slew fast enough) whose fix — a
rail-referenced starve detector — would need *additional* Iq beyond what
this record ratifies. Options 2 (re-cost `por-ramp-rate`'s fast limit) and 3
(a different architecture change) remain live for that separate tension;
this record neither adopts nor forecloses either. If that window is
addressed by adding a detector, the resulting Iq draw must be checked
against `por-iq`'s new 3.0 µA ceiling (and `iq-total`'s <21 µA ceiling,
per the note above) at that time — it is not pre-approved by this record.

**`design/bias_core.md`'s "Iq apportionment" and "Why it cannot be fixed
inside this cell's Iq budget" sections are updated to cite this record** as
the disposition of the static overrun they describe, distinguishing it from
the still-open starved-loop tension.
