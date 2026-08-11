# DR-027: Re-cost `por-brownout`'s `T_dip,min` to the deglitch dwell the cell actually achieves at the real delivered `IBIAS` — the last standing lever after DR-024 and DR-026 close the circuit ones

- **Status**: **ratified 2026-08-11** (operator, issue #236). Ratification scope is the **requirement**: `T_dip,min` moves off the 10 µs internal-target value to the deglitch dwell the cell achieves at the real delivered bias (the "~30 µs, ultra-low-power-BOR class" design point, §7), and the block advertises a **best-effort brownout re-assert**, not a fast dedicated detector. The **exact numeric value** and the `spec/target-spec.md` edit are **not yet pinned** — they follow the confirming dwell sweep (§5), which is now ordinary dispatchable work, not a ratification gate. Superseded status of the old 10 µs value takes effect when the sweep lands and target-spec is edited.
  - *History*: proposed 2026-08-11 (Loom agent, #236, recommendation only) → ratified same day after an operator review that included a competitive benchmark of the field (§7).
- **Date**: 2026-08-11
- **Decided by**: operator (spec-ratification authority), issue #236. Drafted by Loom agent as recommendation.
- **Supersedes**: the `T_dip,min = 10 µs` value in [`spec/target-spec.md#por-brownout`](../target-spec.md#por-brownout) and the parts of DR-008 / DR-024 that carry it — **effective once §5's sweep pins the value and target-spec is edited.**
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

Per CLAUDE.md, "agents do not relax the ratified spec to make results pass." This lever changes what the product *promises*, not what it *does*, and it is a **preference, not a derivable fact**: two well-informed people can disagree on the axis of *how much real-world brownout immunity a POR with no dedicated detector owes its downstream digital domain*. One holds 10 µs as a hard requirement and pays for it with new analog design or `por-iq` headroom; the other judges a ≈ 30 µs floor acceptable for wave 1's role — a best-effort re-assertion already gated to slow dips (< 2.30 mV/µs, DR-011). No measurement settles that axis; only spec-ratification authority does — which is why this record was operator-gated, and why §7's field benchmark (not a simulation) is what the operator weighed to ratify.

## 5. What pinning the value requires (now dispatchable work, not a ratification gate)

The requirement is ratified (§ Status). The following pins the number and lands it in the spec:

- [ ] **A dwell sweep** on `sim/por-output-chain-deglitch/` at the real 91.03 nA worst-case bias that finds the actual `T_dip,min(new)` at which the worst PVT corner's `NDG` reaches trip — replacing the §3 estimate with a measured value + margin. (The present fixed-10 µs deck cannot report it; the crossing-time `.meas` errors out of interval.)
- [ ] **Re-run** `sim/por-output-chain-deglitch/` and `sim/por-brownout/` at the new bound and show a clean pass at `T_dip,min(new)` across the full 81-point grid, both netlist levels.
- [ ] Confirm the falling-slew gate (DR-011) and the reset-pulse regeneration on re-assert (`por-reset-pulse`) are unchanged by the re-cost.
- [ ] Edit `spec/target-spec.md#por-brownout`'s `T_dip,min` to the measured value, citing this record and §7.
- [ ] **Contingency:** if the sweep shows any corner *never* trips at any dwell (an asymptotic floor above trip, contradicting §1's monotonic reading), this record does **not** apply to that corner and the block has no spec-only path there — surface it, do not silently widen `T_dip,min` to hide it. Ratification of the *requirement* does not pre-authorise papering over a genuinely unreachable corner.

## 6. Consequences

- **Zero silicon change.** `design/` is untouched; only the advertised bound moves. This is the cheapest of the four levers by a wide margin, and the only one that survives DR-024/DR-026.
- **Immunity narrows: 10 µs → ≈ 30 µs (to be pinned by §5).** The block catches slow brownout dips of ≈ 30 µs or longer; dips between 10 µs and ≈ 30 µs that previously fell inside the advertised envelope no longer do. Downstream integrators must budget for this — a POR without a dedicated brownout detector is a best-effort re-assert, not a fast brownout guardian.
- **`#236` closes on this ratification.** The remaining work is the §5 sweep-and-pin, filed as ordinary dispatchable work.

## 7. Competitive context — why a ≈ 30 µs floor is a deliberate, benchmarked requirement, not a shortfall

The operator ratified against a survey of how the field specifies brownout detection, not against the simulation alone. Two findings frame the choice:

- **Our spec *structure* is the industry-standard convention.** Every MCU brownout detector specifies a **minimum pulse width for detection (`t_BOD`)** — the BOD trips only if the supply stays below threshold *longer than* `t_BOD` — plus hysteresis "to ensure spike-free BOD." That is exactly this row's `T_dip,min` + the DR-011 slew gate + the comparator hysteresis. We are using the standard brownout-detection contract, not carving out an exception. (Microchip AVR/SAM BOD documentation.)
- **A ≈ 30 µs floor at ~90 nA is a recognised, shipped design tier.** The field ships **ultra-low-power BORs that trade a slower response time for a few hundred nanoamps of current** — precisely this block's regime (~91 nA delivered bias). Commercial voltage supervisors go further and deliberately **ignore sub-10 µs supply dips as glitch immunity** (down to ~70 % of rated V), with reset *delays* of 0.3–0.4 ms. So a 30 µs guaranteed-detection floor is squarely inside normal practice for this current class — sub-10 µs events are widely treated as glitches to reject, not brownouts to catch. (Ersa Electronics supervisor overview; Analog Devices supervisory-circuits note; low-power-BOD patent US20120187985.)

**Requirement statement (ratified):** wave 1's POR is a **low-Iq, best-effort brownout re-assert in the ultra-low-power-BOR class** — guaranteed re-assertion for slow (< 2.30 mV/µs), deep (< 2.22 V) dips lasting **≥ `T_dip,min(new)` ≈ 30 µs** (exact value per §5). An integrator requiring fast (sub-30 µs) brownout detection adds a dedicated supervisor; this is documented in the datasheet, not implied. This is the performance point wave 1 is designed to, chosen deliberately against the field — not a spec relaxed to make a simulation pass.

*Benchmark sources (accessed 2026-08-11):* Microchip AVR/SAM Brown-out Detector documentation (`t_BOD` minimum-pulse-width convention); Ersa Electronics, "Voltage Supervisor & Reset ICs: Brownout Immunity" (sub-10 µs glitch immunity, 0.3–0.4 ms reset timing); Analog Devices, "Supervisory Circuits Keep Your Microprocessor Under Control"; patent US20120187985 (low-power BOD, response-time/Iq tradeoff).
