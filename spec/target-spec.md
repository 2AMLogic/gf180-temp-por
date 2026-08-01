# Target specification — gf180-temp-por (wave 1)

- **Status**: RATIFIED (see [DR-008](decision-records/DR-008-target-spec-ratification.md)).
  Ratified by the operator on issue #1, conditional on the amendments in
  DR-007 exactly as tabled; per-row `conditional #15` / `TBD-#n` tags below
  remain in force and are not upgraded by this ratification.
- **Date**: 2026-07-31
- **Assembled by**: Loom Builder agent, issue #32 (amendments A1–A8 of the
  spec review posted on #1)
- **Decision record**: [DR-007](decision-records/DR-007-spec-table-amendments.md)
  — what this table adds beyond DR-001…DR-006 and why.

This file is the block's single consolidated target-spec table: **the object
issue #1 ratifies.** Before it existed, the numbers lived only as prose
scattered across `spec/decision-records/DR-001…DR-005` plus #1's own
description, and #1's operator checklist pointed at a README section that the
pre-publication audit (commit `3abcbd7`) had already deleted. Nothing about
the block's *topology* is decided here — DR-001…DR-006 stand exactly as
recorded, and where this table restates one of their values it is a carry, not
a re-decision.

The numeric table deliberately lives here and not in `README.md`: the
publication audit removed the numbers from the README on purpose, and
`README.md` only links to this file.

---

## How to read this table

**Value tags** — every value carries one, so the operator can tell a carried
decision from a new proposal at a glance:

| Tag | Meaning |
|---|---|
| **[DR-n]** | Carried unchanged from decision record `n`. Ratifying it here ratifies the number, not a new decision. |
| **[P]** | **Proposed by this amendment** — a number that existed nowhere before. Needs an explicit operator ruling. All of them are indexed in [§7](#7-provisional-value-index-operator-worksheet). |
| **[TBD-#n]** | Deliberately unset; issue `#n` owns producing the number. Listed in [§8](#8-open-tbd-register). |

**Status** — `ratifiable` (evidence exists or the row is a definition),
`conditional #15` (mismatch-dominated; the current `sim/devchar` evidence is
deterministic-corners-only by its own admission, so the row can only be
*conditionally* ratified pending #15's Monte-Carlo data), or `pending #n`
(no evidence at all yet; #n owns it).

**Binding corner** — the corner at which the row's *hard edge* is set. Two
adjacent rows routinely bind at opposite corners (accuracy at the temperature
extremes, Iq at FF/hot, release-threshold max at SS/cold), which is why a
single "worst corner" for the block does not exist and every row names its
own. Every row is nonetheless swept over the full 81-point grid
([§1](#1-global-operating-conditions)); the binding corner says where the
number is *set*, not where it is the only one measured.

Binding-corner text is a **prediction until a `sim/` record measures it** —
before a full-grid sweep exists, the named corner is reasoned from the
topology's *generic* behaviour (e.g. "highest bias current, lowest
capacitance" for a current-starved timer), which can be wrong for a
topology-specific reason a full grid catches and a single-corner check does
not. [DR-009](decision-records/DR-009-por-reset-pulse-binding-corner.md) is a
concrete instance: two POR rows' predicted binding corners did not match the
measured 81-point grid. A binding-corner parenthetical is not itself a
target — it does not change what value the row requires — so a corrected
parenthetical is not a spec relaxation. Once a `sim/` record exists for a
row, its full-grid minimum/maximum supersedes the prediction; a reviewer
should not treat an unmeasured parenthetical as evidence.

**Row IDs** are stable anchors. A `sim/` evidence record's **Claim** field
references a row as `spec/target-spec.md#<row-id>` (see `sim/README.md` §
*Summary record format*), and per that document every ratified row must map to
a `sim/<experiment-slug>/` directory — the **Evidence** column names the
owning issue.

---

## 1. Global operating conditions

These are the condition columns for every row below; they are not themselves
performance targets.

| ID | Parameter | Value | Notes | Source |
|---|---|---|---|---|
| <a id="supply-voltage"></a>`supply-voltage` | Supply voltage, VDD | 3.3 V nominal, ±10 % → **2.97–3.63 V** | Steady state (rail settled, not slewing). Single rail; no separate always-on domain. | **[DR-001]** |
| <a id="operating-temperature"></a>`operating-temperature` | Operating temperature | **−40…+125 °C** | Simulated die/ambient temperature. This is the axis every accuracy row is judged across. | **[DR-002, DR-005]** |
| <a id="corner-grid"></a>`corner-grid` | PVT grid for every recorded claim | 9 process corners (`tt, ff, ss, fs, sf, res_ff, res_ss, bjt_ff, bjt_ss`) × 3 temperatures (−40/27/125 °C) × 3 supplies (2.97/3.30/3.63 V) = **81 points** | Harness default is `full`; passive (resistor/BJT) corners are not optional here because they move the PTAT resistor ratio and the POR divider. | **[DR-006]** |
| <a id="accuracy-window"></a>`accuracy-window` | Validity window for the accuracy rows | Post-POR-release, rail settled, 2.97–3.63 V | Accuracy is **not** specified while the rail is ramping or below POR release — that regime is governed by the POR rows in [§4](#4-power-on-reset-por). | **[DR-001]** |
| <a id="pinout"></a>`pinout` | Electrical interface | `VDD`, `VSS`, `PTAT`, `CTAT`, `RESETn` (5 pads) | No trim/config/programming pins in wave 1. Asserted by `design/netlist.py --check`. | **[DR-001, DR-002, DR-004]** |

---

## 2. Statistical basis (amendment A5)

A target with no stated statistical basis changes meaning by roughly 2×
depending on the reader, so every performance row below carries one of:

- **[3σ]** — process **plus local mismatch**, Monte Carlo, N ≥ 500, reported
  at ±3σ, evaluated at the row's binding corner (i.e. an MC run at each of the
  temperature/rail extremes named, not at nominal only). Applies to the rows
  whose error is mismatch-dominated: untrimmed and trimmed temperature
  accuracy, and both POR threshold edges with their hysteresis.
- **[CWC]** — corner-worst-case: the worst single point of the deterministic
  81-point grid, mismatch not modelled. Applies to budget/limit rows (Iq,
  pulse width, ramp envelope, self-heating, area) where the corner spread, not
  device-to-device mismatch, is the dominant term.

**Consequence — conditional ratification.** `sim/devchar/SUMMARY.md` states
outright that it ran with `sw_stat_mismatch=0` and that local mismatch "should
not be assumed small". Every **[3σ]** row is therefore marked
`conditional #15`: it can be ratified now as a *target*, but it cannot be
called evidenced, and #15's Monte-Carlo mismatch data may force a re-cost of
the number (a spec revision through a new decision record, not a silent
relaxation).

---

## 3. Temperature sensor

| ID | Parameter | Target | Stretch | Conditions / binding corner | Basis · Status | Source · Evidence |
|---|---|---|---|---|---|---|
| <a id="temp-range"></a>`temp-range` | Operating temperature range | **−40…+125 °C** | — | Is the temperature axis; the condition column for every row below. | — · `ratifiable` | **[DR-002, DR-005]** · #13 |
| <a id="temp-accuracy-untrimmed"></a>`temp-accuracy-untrimmed` | Temperature error, untrimmed | **±3 °C** | — | Judged at the `PTAT`/`CTAT` **pin voltage**, converted through the published V(T) characteristic ([`temp-vt-transfer`](#temp-vt-transfer)) and compared against true die temperature. Window per [`accuracy-window`](#accuracy-window). **Binds at the temperature extremes (−40 °C and +125 °C), at both rail extremes.** **Measured (assembled path, systematic/corner share only)**: **−0.335…+0.099 °C** over the full 108-point grid (`ff_25c_2.97v` / `bjt_ss_125c_3.63v`), **11 % of budget** — well inside ±3 °C, comfortably in the neighborhood of `temp-core-designer-check`'s idealised-source −0.230…+0.422 °C. | **[3σ]** · `conditional #15` | **[DR-002, DR-005]**, measured `sim/temp-accuracy-vt/` (record `20260801-121458-660d016`) · #13, #15 |
| <a id="temp-accuracy-trimmed"></a>`temp-accuracy-trimmed` | Temperature error, 1-point trim | — | **±1.5 °C** | As above, after the [`temp-trim-strategy`](#temp-trim-strategy) trim. **Binds at the temperature extremes** (a 25 °C trim leaves the residual curvature at the ends of the span). **Measured (derived, systematic/corner + quantisation share only)**: **−0.346…+0.847 °C** across all 81 non-25 °C (corner, supply, temperature) points (`ff_-40c_3.63v` / `res_ff_125c_3.63v`), **56 % of budget**, 81/81 within bound — the wave-1 `100000b` metal-strap trim already baked into `design/netlist/temp_core.spice`, no schematic re-simulation needed. | **[3σ]** · `conditional #15` | **[DR-002, DR-005]**, derived `sim/temp-accuracy-vt/analyze_derived.py` (record `20260801-121458-660d016-derived`) · #13, #15 |
| <a id="temp-trim-strategy"></a>`temp-trim-strategy` | Trim strategy | **1-point, at +25 °C, on the PTAT gain** (equivalently the PTAT bias current) | — | Corrects gain/offset only; residual curvature over the 165 °C span is **not** corrected (that needs 2-point or curvature compensation — out of wave 1). Trim **mechanism** (filled by #9): **6-bit binary-weighted short-out ladder on the PTAT gain resistor `R2`, switch gates strapped by metal-1 mask option in wave 1**; measured LSB 0.229–0.242 % of `R2` (= 0.71 °C at the trim point, so ±0.35 °C quantisation) and full range ±7.80…7.85 % (= ±23 °C, equivalently ±4.2 mV of amplifier input offset). No trim pad — the strap is the entire interface, and it is the drop-in hook-up point for a fuse/OTP bit-cell array in a later wave. No POR trim node in wave 1. | — · `ratifiable` | **[DR-005]**, mechanism from #9 (`design/temp_core.md`) · #9 |
| <a id="temp-vt-transfer"></a>`temp-vt-transfer` | Nominal V(T) transfer characteristic at the pads | Slope (design intent, filled by #9): `PTAT` = **+4.3088 mV/K** (`V(PTAT) = K₀·T`, `K₀ = 4.308842 mV/K`, i.e. a ratiometric-to-absolute-temperature output through the origin, **not** an offset-and-slope line); `CTAT` = **−1.86 mV/°C**, 0.6533 V at 27 °C. **Published measured (assembled path, #13)**: `PTAT` K₂₅ = **4.304–4.30756 mV/K** at the 25 °C reference across the 9-corner × 3-supply grid (matches design intent to within 0.1 %); `CTAT` slope = **−1.88424…−1.82384 mV/°C** over −40…125 °C (matches design intent). Output range (design intent, filled by #9): `PTAT` **1.004…1.717 V**, `CTAT` **0.461…0.782 V** over the full 216-point PVT grid; worst headroom margin **+260 mV** (`bjt_ff_125c_2.97v`), so the bound at right holds with margin. **Measured (assembled path)**: `PTAT` **1.00329…1.71599 V**, `CTAT` **0.460507…0.782332 V**; worst headroom margin **+260.507 mV**, same binding corner (`bjt_ff_125c_2.97v`) — the idealised-500 nA-source design-intent numbers hold on the real `bias_core`-driven path. | — | **Load-bearing**: DR-002 judges [`temp-accuracy-untrimmed`](#temp-accuracy-untrimmed) *through* this function, so an unfilled slope makes that row unverifiable. Headroom bound **[P]**: the output must stay within **0.2 V ≤ V(out) ≤ VDD − 0.2 V at every corner**, evaluated at VDD = 2.97 V and both temperature extremes, so the signal remains observable at the worst-case rail. Informative physics anchors from `sim/devchar/SUMMARY.md`: un-amplified ΔVBE(8:1) = +0.179 mV/°C, single-PNP VBE = −1.83 mV/°C at 10 µA — the PTAT slope is the former times the chosen gain. | **[CWC]** (headroom bound) · `ratifiable` (measured, assembled path) | **[DR-002]**, this amendment, slope/range design intent from #9 (`design/temp_core.md`, `sim/temp-core-designer-check/`), published measured value from #13 (`sim/temp-accuracy-vt/records/20260801-121458-660d016.md`) · #9, #13 |
| <a id="temp-supply-sensitivity"></a>`temp-supply-sensitivity` | Supply sensitivity of the reported temperature | **≤0.5 °C/V [P]** (≤0.33 °C across the ±10 % window) | — | Budgeted **inside** [`temp-accuracy-untrimmed`](#temp-accuracy-untrimmed), not additive to it. **Binds at the rail extremes (2.97 V and 3.63 V), evaluated at the temperature extremes.** #13 was chartered to sweep supply with no target to assert against; this row is that target. **Measured**: per-point rail-extreme shift **−0.089…+0.034 °C** (108/108 points within ±0.33 °C); stricter full-window (2.97→3.63 V) peak-to-peak **≤0.1216 °C** at every one of 36 (corner, temperature) groups (worst: `res_ss_125c`) — **37 %** of the 0.33 °C budget at its worst point. | **[CWC]** · `ratifiable` (measured) | this amendment, measured `sim/temp-accuracy-vt/` (record `20260801-121458-660d016`, derived full-window reading in `-derived`) · #13 |
| <a id="temp-iq"></a>`temp-iq` | Temperature-sensor quiescent current | **<20 µA** | **<5 µA** | **Incremental** current above [`por-iq`](#por-iq), measured with `RESETn` released and the sensor enabled — see the accounting rules in [§5](#5-quiescent-current-accounting-amendment-a7). **Binds at FF / +125 °C / 3.63 V.** DR-005's bottom-up estimate is 5–15 µA, i.e. the stretch needs the low-power amplifier work DR-005 defers to #9. **Measured (assembled path, incremental)**: **5.80…15.90 µA** over the full 108-point grid, binding corner `ff_125c_3.63v` (15.90 µA) exactly as predicted. **`<20 µA` target: met**, 20 % margin at the binding corner. **`<5 µA` stretch: not met** (floor observed 5.80 µA at `ss_-40c_2.97v`) — consistent with, and not a new miss beyond, DR-005's own bottom-up estimate that the stretch needs low-power amplifier work not attempted in wave 1. | **[CWC]** · `ratifiable` (measured; target met, stretch not reached as already anticipated) | **[DR-002, DR-005]**, measured `sim/temp-accuracy-vt/` (record `20260801-121458-660d016`) · #13 |
| <a id="temp-interface"></a>`temp-interface` | Output interface | **Analog `PTAT` + `CTAT` out, both pads** | Digital out via SAR pairing | Stretch is explicitly deferred out of wave 1. **Promoting it requires adding three rows that do not exist today**: reference source/accuracy, resolution, and conversion rate. | — · `ratifiable` | **[DR-002]** · #8 |
| <a id="temp-resolution-rate"></a>`temp-resolution-rate` | Resolution / conversion rate | **N/A (continuous analog output)** | Becomes required with the SAR stretch | Stated explicitly rather than left silent, so the omission reads as a decision rather than an oversight. | — · `ratifiable` | this amendment · — |
| <a id="temp-self-heating"></a>`temp-self-heating` | Self-heating error contribution | **≤0.1 °C [P]** | — | By power budget: worst-case block power = [`iq-total`](#iq-total) × 3.63 V ≈ **76 µW**, which stays under 0.1 °C for any local thermal resistance ≤ 1300 °C/W — comfortable for a block of this size in any packaged part. Included within [`temp-accuracy-untrimmed`](#temp-accuracy-untrimmed). **Binds at FF / +125 °C / 3.63 V** (maximum dissipation). Re-derive if [`iq-total`](#iq-total) moves. | **[CWC]** · `ratifiable` (budget), confirm with #13/#17 | this amendment · #13, #17 |

---

## 4. Power-on reset (POR)

### 4.1 Threshold pair (amendment A2)

The pre-amendment spec carried a single "2.6 V ±5 %" band that named neither
edge. It is **the release (rising) threshold**; the assert (falling) edge is
now its own row, and the hysteresis row ties the two together *and is bounded
above*, because an unbounded "≥100 mV" silently drags the assert threshold
toward the downstream digital domain's floor.

| ID | Parameter | Min | Typ | Max | Binding corner | Basis · Status |
|---|---|---|---|---|---|---|
| <a id="por-vth-rise"></a>`por-vth-rise` | **VPOR↑** — release threshold, rising VDD | **2.47 V** | **2.60 V** | **2.73 V** | **Max binds at SS / −40 °C**; min binds at FF / +125 °C. | **[3σ]** · `conditional #15` |
| <a id="por-vth-fall"></a>`por-vth-fall` | **VPOR↓** — assert threshold, falling VDD | **2.22 V [P]** | **2.45 V [P]** | **2.63 V [P]** | Derived edge-by-edge from VPOR↑ and V_hys (see below); min binds at FF / +125 °C with maximum hysteresis. | **[3σ]** · `conditional #15` |
| <a id="por-hysteresis"></a>`por-hysteresis` | **V_hys** = VPOR↑ − VPOR↓ | **100 mV** | **150 mV [P]** | **250 mV [P]** | Both edges measured **at the same corner point** (hysteresis is a same-die difference, not a corner-to-corner one). | **[3σ]** · `conditional #15` |

- **VPOR↑ [DR-001, DR-005]**: 2.60 V ±5 % → 2.47/2.60/2.73 V. Release margin
  against the worst-low rail is preserved exactly as DR-001 argued it:
  2.97 V − 2.73 V = **240 mV**.
- **VPOR↓ [P]** is *constructed*, not independently specified:
  VPOR↓,max = VPOR↑,max − V_hys,min = 2.73 − 0.10 = **2.63 V**;
  VPOR↓,min = VPOR↑,min − V_hys,max = 2.47 − 0.25 = **2.22 V**;
  typ = 2.60 − 0.15 = **2.45 V**. Specifying it this way keeps the pair
  self-consistent under any future re-cost of either parent row.
- **V_hys upper bound [P]**: 250 mV is chosen as the largest value that keeps
  VPOR↓,min at 2.22 V, i.e. that leaves the downstream digital domain a
  ≥2.22 V floor. It is a *bound*, not a target — the design is free to sit at
  the 100–150 mV end.

| ID | Parameter | Value | Notes | Basis · Status |
|---|---|---|---|---|
| <a id="por-digital-min-vdd"></a>`por-digital-min-vdd` | V_DIG,min — minimum operating VDD of the downstream digital domain | **[TBD]** — integrator-supplied | The binding inequality is **VPOR↓,min ≥ V_DIG,min**: reset must re-assert *before* the rail falls below what the logic it gates can run on. Wave-1 self-consistency therefore requires **V_DIG,min ≤ 2.22 V [P]**. If the integrating design's number is higher, `por-hysteresis` max or `por-vth-rise` min must be re-ratified through #1 — not silently violated. | — · `pending integrator input` |

### 4.2 Dynamic behaviour (amendments A3, A4)

| ID | Parameter | Target | Conditions / binding corner | Basis · Status | Source · Evidence |
|---|---|---|---|---|---|
| <a id="por-ramp-rate"></a>`por-ramp-rate` | Supply ramp-rate envelope | Correct reset generation guaranteed for **monotonic 0 → VDD ramps with average rate between 1 V/s (slow limit) and 1 V/µs (fast limit) [P]** | "Correct" = `RESETn` low from 0 V throughout the ramp, released once and only once, after VDD crosses VPOR↑ and the [`por-reset-pulse`](#por-reset-pulse) has elapsed — no early release, no glitch, no double pulse. **Both limits bind at SS / −40 °C** (weakest startup-assist leg — devchar measures the native device's Vt turning slightly *positive* at `ss` — and slowest bias-core settling). #14 asserts at both endpoints plus one decade inside each, over the full grid. Outside the envelope behaviour is unspecified, not guaranteed-wrong. | **[CWC]** · `pending #14` | this amendment · #14 |
| <a id="por-brownout"></a>`por-brownout` | Brownout re-assertion | **No dedicated brownout detector in wave 1 [P]** — re-assertion is whatever the POR comparator itself provides. Guaranteed for a dip that (a) takes VDD **below VPOR↓,min = 2.22 V** and (b) **stays below VPOR↓ for ≥ T_dip,min = 10 µs [P]** | Dips shallower than VPOR↓,max or shorter than the deglitch dwell are **explicitly not guaranteed** to assert reset — that rejection is DR-005's deliberate deglitch function, owned by #12. T_dip,min must exceed #12's deglitch dwell time (**[TBD-#12]**, required ≤10 µs for this row to hold). On re-assertion the full [`por-reset-pulse`](#por-reset-pulse) is regenerated. **Binds at SS / −40 °C** (slowest comparator response). | **[CWC]** · `pending #12, #14` | this amendment, **[DR-005]** · #12, #14 |
| <a id="por-reset-pulse"></a>`por-reset-pulse` | Reset pulse width | **≥1 ms**, fixed; **no maximum specified in wave 1 [P]** | Measured on the `RESETn` **deassertion** edge (DR-004), starting when both release conditions of DR-005's startup ordering are satisfied. Programmability is stretch and explicitly de-scoped (DR-003). Measurement load **[TBD-#8/#12]** (provisional: 5 pF, no DC load **[P]**). **The ≥1 ms minimum binds at FF / −40 °C / 2.97 V**, measured (`tpulse_1x_ms` min 4.21535 ms, `sim/por-output-chain-pulse/records/20260801-031819-fce635f.md`) — **not** the fixed-trip fastest-timer corner (FF / +125 °C / 3.63 V) a generic current-starved one-shot would predict. This one-shot's trip is rail-referenced (`TIM = VDD − V_sg(2.5 nA)`, not a fixed voltage), so a cold, low rail shortens the ramp more than a hot, high-bias rail does; see [DR-009](decision-records/DR-009-por-reset-pulse-binding-corner.md). "No maximum" is a decision, not an omission: an RC/current-starved one-shot spreads several× across corners; #14 records the observed max so a maximum can be added later on evidence. | **[CWC]** · `pending #14` | **[DR-003]**, this amendment, binding corner corrected by **[DR-009]** · #14 |

### 4.3 Output interface (from DR-004)

| ID | Parameter | Value | Conditions / binding corner | Basis · Status | Source · Evidence |
|---|---|---|---|---|---|
| <a id="por-polarity"></a>`por-polarity` | Reset polarity | **`RESETn`, active low** | Degrades to *asserted* under loss of drive near 0 V — the property active-high cannot provide on a single-rail block. | — · `ratifiable` | **[DR-004]** · #12 |
| <a id="por-drive"></a>`por-drive` | Reset drive style | **Push-pull** (not open-drain) | Both states driven from within the block; no external pull-up in the specified interface. | — · `ratifiable` | **[DR-004]** · #12 |
| <a id="por-reset-valid-floor"></a>`por-reset-valid-floor` | Reset-valid floor, V_RSTVALID | **Target 0 V** — `RESETn` guaranteed valid-low for **all** VDD ≥ 0 V. Valid-low := V(`RESETn`) ≤ min(0.1 × VDD, 0.3 V) into the [`por-reset-pulse`](#por-reset-pulse) load. Acceptance fallback: **≤0.4 V [P]** if #12 demonstrates 0 V is unreachable, with the achieved floor stated. | This is the numeric row DR-004 requires #12 to fill ("`RESETn` guaranteed valid-low for VDD ≥ X"). The ratio and the absolute floor **bind at different corners, measured** (`sim/por-output-chain-floor/records/20260801-032940-d59d7c4.md`): **the ratio binds at SF / +125 °C** (`floor_ratio_porlow` max 0.548 % at `sf_125c_2.97v` — maximum off-state leakage through the output pull-up relative to VDD, which the below-floor pull-down must overpower), while **the absolute floor binds at SS / −40 °C** (`floor_mv_porlow` max 1.699 mV at `ss_-40c_2.97v` — weakest pull-down drive). See [DR-009](decision-records/DR-009-por-reset-pulse-binding-corner.md). | **[CWC]** · `pending #10, #12, #14` | **[DR-004]**, this amendment, binding corner corrected by **[DR-009]** · #10, #12, #14 |

---

## 5. Quiescent-current accounting (amendment A7)

DR-005 makes the bias/reference core **shared** between the temperature sensor
and the POR precision comparator. At a <1 µA scale that shared core is not a
rounding error, and before this amendment no row said which budget owned it or
what the sensor's enable state was when POR Iq was quoted. The rules:

1. **[`por-iq`](#por-iq) is quoted in the always-on state** — `RESETn`
   asserted, temperature sensor **disabled** — because that is the state the
   block occupies from the first millivolt of rail onward, and it **includes
   every branch that must conduct for the POR threshold decision in that
   state**, i.e. the startup-assist leg, the precision comparator, the pulse
   timer, *and* whatever part of the shared bias/reference core has to be live
   for the comparator's decision to be valid.
2. **[`temp-iq`](#temp-iq) is the incremental current above that**, measured
   with `RESETn` released and the sensor enabled. Shared-core branches that
   only need to conduct when the sensor is enabled are charged here.
3. **[`iq-total`](#iq-total)** is the sum, so nothing can fall between the two
   rows.

| ID | Parameter | Target | Stretch | State / binding corner | Basis · Status |
|---|---|---|---|---|---|
| <a id="por-iq"></a>`por-iq` | POR quiescent current | **<1 µA** | ~~<0.3 µA~~ — **withdrawn: requires architecture revision [P]** | `RESETn` asserted, temperature sensor disabled, per rule 1 above. **Binds at FF / +125 °C / 3.63 V.** **Measured (assembled path, published)**: **0.657–2.385 µA** over the full 81-point grid, binding corner `ff_125c_3.63v` (2.385 µA, **2.4× over budget**) — 27/81 points PASS (every process corner at −40 °C, plus `ss` and `res_ss` at +27 °C), 54/81 FAIL. **Not met.** Evidence: [`sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md`](../sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md). This is the already-owned, already-tracked architecture-level overrun `design/bias_core.md`'s "Iq apportionment" predicted (2.37× from summed per-cell numbers) — now confirmed on the real assembly rather than relaxed to pass, pending a re-cost decision record through #1 (see that document, "The starved-loop window", options 1–3). | **[CWC]** · `pending #1` (measured; re-cost decision pending) |
| <a id="iq-total"></a>`iq-total` | Total block quiescent current | **<21 µA [P]** = `por-iq` + `temp-iq` | — | Normal operation: `RESETn` released, sensor enabled. **Binds at FF / +125 °C / 3.63 V.** Feeds [`temp-self-heating`](#temp-self-heating). **Measured (assembled path, published)**: **6.457–18.288 µA** over the full 81-point grid, binding corner `ff_125c_3.63v` (18.288 µA), **81/81 PASS**, 13 % margin at the binding corner — `por-iq`'s published 0.657–2.385 µA (`sim/por-iq/`) summed with `temp-iq`'s measured 5.80–15.90 µA (`sim/temp-accuracy-vt/`) at matching grid points. **`<21 µA` target: met**, ratifiable on this evidence even though `por-iq` alone is not. Evidence: [`sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md`](../sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md). | **[CWC]** · `ratifiable` (measured; target met) |

**Why the <0.3 µA stretch is withdrawn rather than carried.** It sits *below
the floor of DR-005's own 0.3–0.8 µA estimate* for the precision path alone,
before the ~0.1 µA assist leg and the pulse timer are added. The published
designs that do reach nA class are VTH-referenced/subthreshold or duty-cycled
— precisely the architecture classes DR-005 rejected (correctly, on threshold
accuracy) and which nothing in this repo proposes. Withdrawing it is **not** a
relaxation of a target: it removes a stretch goal that the ratified
architecture cannot reach by construction. Restoring it requires a new
decision record naming the mechanism that pays for it.

**Known accounting risk — owned by #11.** DR-005 charges the shared core's
1–5 µA/branch to its *temperature-sensor* estimate, while its startup ordering
has that same core live and settled **before** POR releases. Under rule 1 that
current lands in [`por-iq`](#por-iq). #11 must therefore either show the shared
core's reset-asserted-state current fits inside <1 µA, or #1 must re-cost the
row. This amendment deliberately does **not** relax the <1 µA target to make
the arithmetic work; it makes the conflict visible and assigns it an owner.

---

## 6. Physical (amendment A8)

| ID | Parameter | Target | Conditions / binding corner | Basis · Status | Evidence |
|---|---|---|---|---|---|
| <a id="area"></a>`area` | Total block area (both sub-blocks, excluding pads) | **[TBD-#17]** — wave-1 planning budget **≤0.05 mm² (≤50 000 µm²) [P]** | The block's stated reason to exist is that "tiny area rides along on any shuttle seat"; that claim had no number anywhere. The budget is a planning bound to be **replaced** by the measured post-layout number, not a substitute for it. | **[CWC]** · `pending #17` | #17 |
| <a id="self-heating"></a>`self-heating` | Self-heating | See [`temp-self-heating`](#temp-self-heating) | — | — | #13, #17 |

---

## 7. Provisional-value index (operator worksheet)

Every **[P]** value in this file — the complete list of numbers that did not
exist before this amendment and that ratification must rule on individually.
Each is a *new* line, not a change to an existing one.

| # | Row | Proposed value | One-line rationale |
|---|---|---|---|
| 1 | [`temp-vt-transfer`](#temp-vt-transfer) | Output headroom 0.2 V ≤ V(out) ≤ VDD − 0.2 V at every corner | Keeps the analog output observable at the 2.97 V worst-low rail. |
| 2 | [`temp-supply-sensitivity`](#temp-supply-sensitivity) | ≤0.5 °C/V, inside the accuracy budget | Gives #13's chartered supply sweep a pass/fail bound; ≤0.33 °C over the ±10 % window is a small slice of ±3 °C. |
| 3 | [`temp-self-heating`](#temp-self-heating) | ≤0.1 °C | Falls straight out of the ≈76 µW power budget; costs one line and closes a required always-on-sensor row. |
| 4 | [`por-vth-fall`](#por-vth-fall) | 2.22 / 2.45 / 2.63 V | Constructed from VPOR↑ and V_hys so the pair stays self-consistent. |
| 5 | [`por-hysteresis`](#por-hysteresis) | typ 150 mV, **max 250 mV** | The ≥100 mV floor was one-sided; the max is what stops V_hys dragging VPOR↓ into the digital domain's floor. |
| 6 | [`por-digital-min-vdd`](#por-digital-min-vdd) | Self-consistency requires V_DIG,min ≤ 2.22 V | Makes the interface assumption explicit and falsifiable by the integrator. |
| 7 | [`por-ramp-rate`](#por-ramp-rate) | 1 V/s … 1 V/µs, monotonic | #14 is chartered to test ramps against nothing today; slow-ramp early release is the classic POR field failure. |
| 8 | [`por-brownout`](#por-brownout) | No dedicated detector; guaranteed for dips < 2.22 V lasting ≥10 µs | Silence is not ratifiable — downstream digital assumes detection unless told otherwise. |
| 9 | [`por-reset-pulse`](#por-reset-pulse) | "No maximum" stated explicitly; provisional 5 pF measurement load | A one-sided minimum with no measurement load is untestable as written. |
| 10 | [`por-reset-valid-floor`](#por-reset-valid-floor) | Target 0 V; acceptance ≤0.4 V with the achieved floor stated | The numeric row DR-004 explicitly requires #12 to fill. |
| 11 | [`por-iq`](#por-iq) | **<0.3 µA stretch withdrawn** ("requires architecture revision") | Below the floor of DR-005's own estimate for the ratified topology. |
| 12 | [`iq-total`](#iq-total) | <21 µA | Makes the two Iq rows sum, so no current is unowned. |
| 13 | [`area`](#area) | ≤0.05 mm² planning budget | The "tiny area" claim needs a number until #17 measures one. |
| 14 | §2 statistical basis | **[3σ]** incl. mismatch on the accuracy and threshold rows; **[CWC]** elsewhere | ±3 °C untrimmed is conventionally a 3σ figure; reading it as corner-worst-case would change its meaning by ~2×. |

---

## 8. Open TBD register

| Row | What is missing | Owner |
|---|---|---|
| ~~[`temp-vt-transfer`](#temp-vt-transfer)~~ | ~~Nominal slope and output range (design intent)~~ — **filled by #9** (`design/temp_core.md`). ~~Published *measured* value~~ — **filled by #13** (`sim/temp-accuracy-vt/records/20260801-121458-660d016.md`) | ~~#9~~, ~~#13~~ |
| ~~[`temp-trim-strategy`](#temp-trim-strategy)~~ | ~~Trim *mechanism* (fuse/OTP/…)~~ — **closed by #9**: metal-strapped 6-bit short-out ladder, fuse/OTP-ready | ~~#9~~ |
| [`por-digital-min-vdd`](#por-digital-min-vdd) | The integrating design's minimum operating VDD | integrator / #1 |
| [`por-brownout`](#por-brownout) | Deglitch dwell time (must be ≤10 µs) | #12 |
| [`por-reset-pulse`](#por-reset-pulse) | `RESETn` measurement load | #8, #12 |
| [`por-reset-valid-floor`](#por-reset-valid-floor) | Achieved floor if 0 V is unreachable | #12 |
| [`area`](#area) | Measured post-layout area | #17 |
| All **[3σ]** rows | Monte-Carlo mismatch evidence (they are `conditional` until it lands) | #15 |

---

## 9. Provenance

| Row group | Where the numbers came from |
|---|---|
| Supply, accuracy window | DR-001 (supply flavor) |
| Interface, accuracy measurement point | DR-002 (temp interface) |
| Reset pulse, fixed-vs-programmable | DR-003 (POR reset pulse) |
| Polarity, drive, below-floor requirement | DR-004 (reset polarity/drive) |
| Topology, Iq estimates, trim stance, deglitch/hysteresis split | DR-005 (architecture survey) |
| Corner grid | DR-006 (sim-harness port) |
| Everything tagged **[P]**, plus the row structure, binding corners and statistical basis | DR-007 (this amendment) |
| `por-reset-pulse` and `por-reset-valid-floor` binding-corner correction (measured, not predicted) | DR-009 (binding-corner correction) |
| `temp-vt-transfer` published measured value, `temp-accuracy-untrimmed`/`temp-accuracy-trimmed` systematic/corner share, `temp-supply-sensitivity`, `temp-iq` — all on the real assembled path (`design/netlist/temp_por_top.spice`, post-#41/DR-010) | #13 (`sim/temp-accuracy-vt/`) |

The eight rows of the deleted README draft table are all present here:
temp range → [`temp-range`](#temp-range); temp accuracy →
[`temp-accuracy-untrimmed`](#temp-accuracy-untrimmed) +
[`temp-accuracy-trimmed`](#temp-accuracy-trimmed); temp interface →
[`temp-interface`](#temp-interface); temp Iq → [`temp-iq`](#temp-iq); POR
threshold → [`por-vth-rise`](#por-vth-rise) + [`por-vth-fall`](#por-vth-fall);
POR hysteresis → [`por-hysteresis`](#por-hysteresis); POR Iq →
[`por-iq`](#por-iq); POR reset pulse → [`por-reset-pulse`](#por-reset-pulse).
No target value carried from those rows was loosened.
