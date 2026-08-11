# DR-027: Re-cost `por-brownout`'s `T_dip,min` to the deglitch dwell the cell actually achieves at the real delivered `IBIAS` — the last standing lever after DR-024 and DR-026 close the circuit ones

- **Status**: proposed — ratification is the operator's (issue #1's process, the same one DR-001, DR-008 and DR-024 went through). **Nothing in this record is in force until an operator ratifies it.** What is *not* conditional on ratification is the evidence: every measurement cited is a committed, unmodified testbench run recorded under `sim/por-output-chain-deglitch/` and `sim/por-brownout/`.
- **Date**: 2026-08-11
- **Decided by**: Loom agent, issue #236 (recommendation only) — the ruling itself is a spec-authority preference, not a derivable fact (see §4).
- **Supersedes**: the `T_dip,min = 10 µs` value in [`spec/target-spec.md#por-brownout`](../target-spec.md#por-brownout) and the parts of DR-008 / DR-024 that carry it, **only if ratified and only after the confirming sweep in §5 lands.**
- **Relates to**: DR-005 (deglitch is the cell's time-domain mechanism), DR-011 (the falling-slew gate on the same row), DR-024 (real `IBIAS` = 0.182×–0.608× nominal; closes levers 1 & 2), DR-026 (the #235 consumer-mirror re-ratio — lever 3 — attempted and rejected for a startup regression).

## Context

`por-brownout` (target-spec) guarantees the POR re-asserts `RESETn` for a dip that (a) goes below `VPOR↓,min = 2.22 V`, (b) stays below for **≥ `T_dip,min` = 10 µs**, and (c) falls no faster than `2.30 mV/µs` (DR-011). Wave 1 ships **no dedicated brownout detector** — re-assertion is "whatever the POR comparator itself provides," and the 10 µs figure was set as the internal deglitch-dwell target (`T_dip,min` must exceed #12's deglitch dwell), not derived from a downstream digital-domain requirement.

DR-024 measured the `IBIAS` actually delivered to `por_output_chain` on the shared node — **0.182×–0.608× nominal (91.03 nA worst case)**, not the idealised 0.5× the cell was costed against. At that current the deglitch one-shot is too slow: across most of the 81-point grid `PGDG` does not reach its 1.0 V trip inside the 10 µs qualifying dip. Head evidence `sim/por-output-chain-deglitch/records/20260811-150342-0c44407.md` (post-layout, extracted): **FAIL at the cold/slow corners**, `pgdg_min_during_halfib_dip_v` pinned at 2.5–3.6 V (well above trip) at every SS and −40 °C point; PASS only at hot/fast corners.

## 1. The mechanism — this is a dwell-length limit, not a floor

Per DR-024, at the real current the filter "is frequently too slow to trip *at all* inside the 10 µs qualifying dip — `PGDG` droops and recovers as `POR_RAW` returns high **before `NDG` reaches the trip point**." `NDG` is discharging monotonically toward trip; the **dip ends first**. This is decisive for the lever: the failing corners are not sitting on an asymptotic floor above trip — they are still on their way down when the 10 µs window closes. **A longer qualifying dip lets `NDG` reach trip and the block re-asserts.** Raising `T_dip,min` is therefore a *real* lever here, not a relabelling of an unreachable target.

## 2. The circuit levers are exhausted

- **Lever 1 — `bias_core` output scaling** and **Lever 2 — a dedicated second output leg**: both ruled out by DR-024's arithmetic against the ratified `por-iq` ceiling (a 3.77× hot/cold reference-current ratio means no proportional scaling clears 220 nA cold without blowing 3.0 µA hot).
- **Lever 3 — #235 consumer-mirror re-ratio**: attempted and **rejected** (DR-026) — it regresses `por_output_chain`'s basic release behaviour even at the *nominal idealised* `IBIAS`, a larger failure than the one it set out to fix.

Lever 4 (this record) is the only one left that does not open a closed cell or spend ratified headroom.

## 3. The decision

Re-cost `T_dip,min` from **10 µs** to the deglitch dwell the cell actually achieves at the real worst-case delivered `IBIAS` (91.03 nA), measured across the full PVT grid. The block's advertised brownout immunity narrows accordingly: it guarantees re-assertion for qualifying dips **at least `T_dip,min(new)`** long, and no longer claims the 10 µs figure the real bias cannot honour.

**Estimated new value (pending the §5 sweep): ≈ 25–30 µs.** Physical basis: the cell was costed to a ≤ 10 µs dwell at 0.5× nominal (0.25 µA); the deglitch node is a capacitor discharged by that bias, so trip time scales inversely with current (`t_trip ≈ C·ΔV/I`). At the worst real 0.182× (91.03 nA) the dwell scales by ≈ 0.5/0.182 ≈ 2.75× → ≈ 27 µs. **This is an estimate, not the ratified value** — the current records error "out of interval" at 10 µs because `NDG` never crosses trip inside the window, so the exact worst-corner trip time must be *measured*, not extrapolated (§5).

## 4. Why this is `operator-decision` and not agent work

Per CLAUDE.md, "agents do not relax the ratified spec to make results pass." This lever changes what the product *promises*, not what it *does*, and it is a **preference, not a derivable fact**: two well-informed people can disagree on the axis of *how much real-world brownout immunity a POR with no dedicated detector owes its downstream digital domain*. One holds 10 µs as a hard requirement and pays for it with new analog design or `por-iq` headroom; the other judges a ≈ 27 µs floor acceptable for wave 1's role — a best-effort re-assertion already gated to slow dips (< 2.30 mV/µs, DR-011). No measurement settles that axis; only spec-ratification authority does. The evidence merely establishes that the choice is *available* and *effective* (§1–§2).

## 5. What ratification requires (per issue #236's acceptance criteria)

- [ ] **A dwell sweep** on `sim/por-output-chain-deglitch/` at the real 91.03 nA worst-case bias that finds the actual `T_dip,min(new)` at which the worst PVT corner's `NDG` reaches trip — replacing the §3 estimate with a measured value + margin. (The present fixed-10 µs deck cannot report it; the crossing-time `.meas` errors out of interval.)
- [ ] **Re-run** `sim/por-output-chain-deglitch/` and `sim/por-brownout/` at the new bound and show a clean pass at `T_dip,min(new)` across the full 81-point grid, both netlist levels.
- [ ] Confirm the falling-slew gate (DR-011) and the reset-pulse regeneration on re-assert (`por-reset-pulse`) are unchanged by the re-cost.
- [ ] On ratification, edit `spec/target-spec.md#por-brownout`'s `T_dip,min` to the measured value and flip this record to `ratified`.

## 6. Consequences

- **Zero silicon change.** `design/` is untouched; only the advertised bound moves. This is the cheapest of the four levers by a wide margin, and the only one that survives DR-024/DR-026.
- **Immunity narrows: 10 µs → ≈ 27 µs (to be pinned by §5).** The block catches slow brownout dips of ≈ 27 µs or longer; dips between 10 µs and ≈ 27 µs that previously fell inside the advertised envelope no longer do. Downstream integrators must budget for this — a POR without a dedicated brownout detector is a best-effort re-assert, not a fast brownout guardian.
- **If the §5 sweep shows any corner never trips at any dwell** (an asymptotic floor above trip, contradicting §1's monotonic reading), this record does **not** apply to that corner and the block has no spec-only path there — surface it, do not silently widen `T_dip,min` to hide it.
