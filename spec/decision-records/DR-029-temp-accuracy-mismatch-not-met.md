# DR-029: Record both temperature-accuracy rows as measured-not-met rather than relaxing them

- **Status**: proposed
- **Date**: 2026-08-02
- **Decided by**: Loom Builder agent, issue #15 (Monte Carlo mismatch analysis)

## Context

`spec/target-spec.md` §2 (amendment A5, ratified by DR-008) defines **[3σ]**
as *process plus local mismatch, Monte Carlo, N ≥ 500, evaluated at the row's
binding corner*, and marks all five **[3σ]** rows `conditional #15` — "it can
be ratified now as a *target*, but it cannot be called evidenced, and #15's
Monte-Carlo mismatch data may force a re-cost of the number (a spec revision
through a new decision record, not a silent relaxation)."

Issue #15 has now run that Monte Carlo. Three of the five rows close; two do
not.

**The three POR rows close** —
[`por-vth-rise`](../target-spec.md#por-vth-rise),
[`por-vth-fall`](../target-spec.md#por-vth-fall) and
[`por-hysteresis`](../target-spec.md#por-hysteresis) meet their ratified
windows at 3σ at every one of their five named binding points
(`sim/por-threshold-mc/`). They need no decision record: measured evidence
simply resolves their `conditional #15` tag, exactly as #13's and #14's
deterministic evidence resolved the **[CWC]** rows.

**The two temperature-accuracy rows do not.** Measured at the four binding
points those rows name (−40 °C and +125 °C at 2.97 V and 3.63 V), N = 500
local-mismatch samples each, process held at the row's own deterministic
corner — `sim/temp-accuracy-mc/records/20260802-082345-989ce7a.md`:

| Row | Ratified | Measured mean ± 3σ | Empirical yield | Over budget by |
|---|---|---|---|---|
| [`temp-accuracy-untrimmed`](../target-spec.md#temp-accuracy-untrimmed) | ±3 °C **[3σ]** | −19.23 … +19.63 °C (worst point, `tt`/125 °C/2.97 V) | 33.4–40.4 % | **6.5×** |
| [`temp-accuracy-trimmed`](../target-spec.md#temp-accuracy-trimmed) | ±1.5 °C **[3σ]** (stretch) | −7.08 … +7.70 °C (same point) | 37.2–65.8 % | **4.9×** |

This is not a surprise so much as a confirmation. `design/temp_core.md`'s own
error budget already reduced both rows to a single question — "both targets
now reduce to the *same* question, random input-referred offset, and both
want it under about 0.5 mV at 3σ. That is not obviously achievable for a
plain (unchopped) pair, and it is precisely the number issue #15 has to
produce." The number is **3.07 mV at 3σ**, 6.7× the ≈0.46 mV the budget left
for it.

The attribution record
`sim/temp-accuracy-mc/records/20260802-082345-989ce7a-breakdown.md` splits the
untrimmed σ into the three physical terms exactly (the topology makes the
split algebraic, not fitted; the root-sum-square of the three lands within
2.1–5.0 % of the directly-measured σ):

| Term | Devices | σ | σ-contribution to the untrimmed error | 3σ against ±3 °C |
|---|---|---|---|---|
| Amplifier input offset `V_os` | `XMI1`/`XMI2` pair, `XML1`/`XML2` load mirror | 0.93–1.02 mV | 5.18–5.71 °C | **518–571 %** |
| Gain `A = R2/R1` × mirror ratio | `XR1` vs the `XR2*` ladder, `XMP1`/`XMP2`/`XMP3` | 0.54–1.05 % | 2.16–2.44 °C | **216–244 %** |
| PNP pair Δ`V_BE` | `XQ1` vs the 8× `XQ8A..H` array | 0.18–0.20 mV | 1.00–1.11 °C | **100–111 %** |

Three consequences of that table matter for the decision:

1. **Every one of the three terms busts ±3 °C on its own** at its worst
   binding point. Fixing the amplifier alone does not close the untrimmed row.
2. The one-point 25 °C **gain** trim removes the gain and Δ`V_BE` terms
   (both are gain errors) but not `V_os`, whose surviving lever the record
   measures at **−1.32/−1.34 °C/mV cold** and **+1.94/+2.02 °C/mV hot** —
   confirming `design/temp_core.md`'s published +1.21 / ±1.87 °C/mV on 500
   dice per point.
3. **A perfect amplifier would still not close the trimmed stretch.** With the
   `V_os` share removed, the ½-LSB trim quantisation (±0.48 °C at 125 °C) and
   a further 0.68–1.11 °C of curvature the linear attribution does not explain
   (most plausibly the `XMP1`/`XMP2`/`XMP3` mirror's own temperature-dependent
   V_th mismatch, which does not cancel across a 25 °C-referenced trim) leave
   ≈1.2 °C of σ, i.e. ≈3.6 °C at 3σ against a ±1.5 °C target.

## Decision

**Neither target is relaxed. Both rows are recorded as measured-and-not-met,
and the remedy is a design revision, not a spec revision.**

Concretely, in `spec/target-spec.md`:

- [`temp-accuracy-untrimmed`](../target-spec.md#temp-accuracy-untrimmed) keeps
  **±3 °C [3σ]**; its Status becomes **`pending #1`** ("measured; not met,
  re-design decision pending") in place of `conditional #15`, and its
  Conditions column publishes the measured mismatch-inclusive spread beside
  the systematic-only figure #13 already published.
- [`temp-accuracy-trimmed`](../target-spec.md#temp-accuracy-trimmed) keeps
  **±1.5 °C [3σ]** as a stretch, with the same Status change and the same
  published measurement.
- The three POR rows' `conditional #15` tags resolve to `ratifiable` on
  `sim/por-threshold-mc/`'s evidence.
- §8's Open TBD register entry "All **[3σ]** rows — Monte-Carlo mismatch
  evidence" is closed by #15 and replaced by the narrower, still-open item
  this record creates: the temp_core re-design.

This is the same shape the already-owned
[`por-iq`](../target-spec.md#por-iq) overrun follows — measured, published as
a miss, target untouched, re-cost routed through #1 — and it is what CLAUDE.md
requires ("agents do not relax the ratified spec to make results pass").

The re-design itself is **not** decided here (see Alternatives): this record
decides that the numbers stand and that the evidence needed to choose between
the remedies is now on file, and it hands the choice to #1 with the measured
sensitivities attached.

## Alternatives considered

- **Relax the rows to what the current sizing achieves (±19 °C untrimmed,
  ±7.7 °C trimmed).** Rejected outright. CLAUDE.md forbids relaxing a
  ratified spec to make results pass, and a ±19 °C temperature sensor is not
  the product this block exists to be — §2's whole purpose was to stop the
  ±3 °C figure quietly changing meaning by 2×; changing it by 6.5× instead is
  the same failure with a bigger number.
- **Re-define [3σ] to exclude local mismatch.** Rejected for the same reason,
  more directly: amendment A5 exists precisely to prevent this reading, and
  `sim/devchar/SUMMARY.md` warned in advance that mismatch "should not be
  assumed small just because the corner-only spread looks tractable".
- **Quote the trimmed row against a two-point or per-part calibration.**
  Rejected: DR-005 ratified a single 25 °C gain trim and DR-003 de-scoped
  programmability for wave 1. A per-part multi-point calibration is a
  different product with a different test cost, and adopting it silently to
  rescue a number would be exactly the relaxation this record refuses.
- **Choose the fix here and now (grow the pair / chop / re-ratio the trim).**
  Rejected as out of this record's and this issue's scope. #15 is chartered
  to *measure*; each candidate remedy changes area, Iq and the floorplan, so
  it lands in #16/#17's territory and needs its own record. What #15 can and
  does contribute is the sizing information that choice needs:
  - **Grow the input pair and load mirror.** σ(`V_os`) falls as 1/√(WL), so
    getting 3σ from 3.07 mV to ≈0.46 mV is a **6.7× σ reduction ⇒ ≈45× device
    area** on `XMI1`/`XMI2`/`XML1`/`XML2`. Not viable against
    [`area`](../target-spec.md#area) on its own.
  - **Chop or auto-zero the amplifier.** DR-005 rejected chopping for wave 1
    on Iq and complexity grounds and said explicitly to revisit it "if exactly
    this evidence appears". It has. Note finding (3) above: this closes the
    untrimmed row's dominant term but does **not** by itself close the
    trimmed stretch.
  - **Fix the gain term regardless.** At 216–244 % of the untrimmed budget the
    `XMP1`/`XMP2`/`XMP3` mirror + `XR1`/`XR2*` ratio needs its own attention
    (longer mirror devices and/or degeneration; common-centroid resistor
    layout is #17's job) whichever amplifier remedy is chosen.
  - **Re-balance the trim ladder.** `design/temp_core.md` already observes the
    ±23 °C trim range is far wider than needed; trading range for LSB shrinks
    the ±0.28/±0.48 °C quantisation term at no extra bits.

## Consequences

- **Wave-1 `temp_core` as netlisted does not meet its accuracy rows.** That is
  now a published, evidenced fact rather than an open risk. Anything
  downstream that assumed ±3 °C — datasheet copy, the `accuracy-window` row's
  framing, integrator-facing material — has to say "target, not met on
  schematic MC" until a revision lands.
- **#16/#17/#18 inherit a design change, not just a number.** #17's floorplan
  was to be driven by #15's mismatch breakdown; it now also has to accommodate
  whatever the amplifier remedy turns out to be. #18's post-layout re-run will
  re-measure a circuit that is expected to change first, so sequencing it
  behind the revision avoids characterising a netlist nobody intends to tape
  out.
- **The three POR rows are unblocked and fully evidenced**, so the POR half of
  the block is not held hostage to the temperature half's re-design.
- **The measurement infrastructure is reusable.** `sim/run_mc.py` +
  `sim/temp-accuracy-mc/` re-run against a revised netlist unchanged, and
  `analyze_breakdown.py` re-derives the same attribution, so the next
  iteration is a re-run rather than a re-build. The `V_os`-versus-area and
  `V_os`-versus-lever numbers above are the acceptance criteria a revision can
  be checked against before it is laid out.
- **Bad consequence, stated plainly**: this record leaves the block's headline
  specification unmet at the end of an issue whose charter was to measure it.
  It buys nothing except an honest number and the sensitivities to fix it, and
  it defers the actual fix. The alternative — a passing table — would have
  been worth less than nothing.
