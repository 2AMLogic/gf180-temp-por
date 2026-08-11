# Target specification — gf180-temp-por (wave 1)

- **Status**: RATIFIED (see [DR-008](decision-records/DR-008-target-spec-ratification.md)).
  Ratified by the operator on issue #1, conditional on the amendments in
  DR-007 exactly as tabled; per-row `conditional #15` / `TBD-#n` tags below
  remain in force and are not upgraded by this ratification. The
  `conditional #15` tags have since been discharged by #15's Monte Carlo —
  three rows pass, two are recorded as measured misses under
  [DR-011](decision-records/DR-011-temp-accuracy-mismatch-not-met.md); see §2.
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
`conditional #15` (mismatch-dominated; the deterministic-corners-only evidence
could ratify the row only *conditionally*, pending #15's Monte-Carlo data), or
`pending #n` (no evidence at all yet, or evidence showing the row is not met;
#n owns it). **No row carries `conditional #15` any more** — #15's Monte Carlo
has run and every one of the five is now either `ratifiable` on
mismatch-inclusive evidence or `pending #1` as a measured miss; see §2.

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
not be assumed small". Every **[3σ]** row was therefore marked
`conditional #15`: it could be ratified as a *target*, but it could not be
called evidenced, and #15's Monte-Carlo mismatch data might force a re-cost of
the number (a spec revision through a new decision record, not a silent
relaxation).

**Resolved by #15 (2026-08-02).** The Monte Carlo has been run — N = 500
local-mismatch samples per binding point, at each row's own named binding
point, `sw_stat_mismatch=1`, process held at the row's own deterministic
corner (`sim/run_mc.py`; see `sim/harness/README.md` § "Monte Carlo mismatch"
for why global spread is left to the deterministic sweep rather than
double-counted). The five rows split:

- **The three POR rows close.** [`por-vth-rise`](#por-vth-rise),
  [`por-vth-fall`](#por-vth-fall) and [`por-hysteresis`](#por-hysteresis) are
  inside their ratified windows at 3σ at all five of their binding points,
  with 100 % empirical yield — `sim/por-threshold-mc/records/20260802-083749-3b9b414.md`.
  Their `conditional #15` tag is discharged; they are `ratifiable` on
  mismatch-inclusive evidence.
- **The two temperature-accuracy rows do not.**
  [`temp-accuracy-untrimmed`](#temp-accuracy-untrimmed) misses ±3 °C by 6.5×
  and [`temp-accuracy-trimmed`](#temp-accuracy-trimmed) misses ±1.5 °C by
  4.9× — `sim/temp-accuracy-mc/records/20260802-082345-989ce7a.md`. Per
  CLAUDE.md neither number is relaxed: both rows keep their target and move to
  `pending #1` as measured-and-not-met, with the remedy routed to a design
  revision. That is the re-cost this section anticipated, taken as
  [DR-011](decision-records/DR-011-temp-accuracy-mismatch-not-met.md) rather
  than as a silent edit to the numbers.

The **[3σ]** basis itself is unchanged by any of this — the definition above
is what was measured against.

---

## 3. Temperature sensor

| ID | Parameter | Target | Stretch | Conditions / binding corner | Basis · Status | Source · Evidence |
|---|---|---|---|---|---|---|
| <a id="temp-range"></a>`temp-range` | Operating temperature range | **−40…+125 °C** | — | Is the temperature axis; the condition column for every row below. | — · `ratifiable` | **[DR-002, DR-005]** · #13 |
| <a id="temp-accuracy-untrimmed"></a>`temp-accuracy-untrimmed` | Temperature error, untrimmed | **±3 °C** | — | Judged at the `PTAT`/`CTAT` **pin voltage**, converted through the published V(T) characteristic ([`temp-vt-transfer`](#temp-vt-transfer)) and compared against true die temperature. Window per [`accuracy-window`](#accuracy-window). **Binds at the temperature extremes (−40 °C and +125 °C), at both rail extremes.** **Measured (assembled path, systematic/corner share only)**: **−0.335…+0.099 °C** over the full 108-point grid (`ff_25c_2.97v` / `bjt_ss_125c_3.63v`), **11 % of budget** — well inside ±3 °C, comfortably in the neighborhood of `temp-core-designer-check`'s idealised-source −0.230…+0.422 °C. **Measured (Monte Carlo, local mismatch on, N = 500 per binding point at each of the four named binding points)**: mean ± 3σ worst point **−19.23…+19.63 °C** (`tt`/125 °C/2.97 V; σ = 6.08–6.48 °C across the four), empirical yield **33.4–40.4 %** — **6.5× over budget. Not met.** Attribution (`…-breakdown`): amplifier offset σ(`V_os`) = 0.93–1.02 mV → 5.18–5.71 °C, gain `R2/R1`×mirror 2.16–2.44 °C, PNP Δ`V_BE` 1.00–1.11 °C; **all three bust ±3 °C individually**. Target **not relaxed** — see [DR-011](decision-records/DR-011-temp-accuracy-mismatch-not-met.md). Evidence: [`sim/temp-accuracy-mc/records/20260802-082345-989ce7a.md`](../sim/temp-accuracy-mc/records/20260802-082345-989ce7a.md), [`…-breakdown.md`](../sim/temp-accuracy-mc/records/20260802-082345-989ce7a-breakdown.md). | **[3σ]** · `pending #1` (measured, not met; re-design decision pending per DR-011) | **[DR-002, DR-005, DR-011]**, measured `sim/temp-accuracy-vt/` (record `20260801-121458-660d016`) + `sim/temp-accuracy-mc/` (record `20260802-082345-989ce7a`) · #13, #15 |
| <a id="temp-accuracy-trimmed"></a>`temp-accuracy-trimmed` | Temperature error, 1-point trim | — | **±1.5 °C** | As above, after the [`temp-trim-strategy`](#temp-trim-strategy) trim. **Binds at the temperature extremes** (a 25 °C trim leaves the residual curvature at the ends of the span). **Measured (derived, systematic/corner + quantisation share only)**: **−0.346…+0.847 °C** across all 81 non-25 °C (corner, supply, temperature) points (`ff_-40c_3.63v` / `res_ff_125c_3.63v`), **56 % of budget**, 81/81 within bound — the wave-1 `100000b` metal-strap trim already baked into `design/netlist/temp_core.spice`, no schematic re-simulation needed. **Measured (Monte Carlo, local mismatch on, N = 500 per binding point, per-die 25 °C trim reference)**: mean ± 3σ worst point **−7.08…+7.70 °C** (`tt`/125 °C/2.97 V; σ = 1.49–2.46 °C across the four), empirical yield **37.2–65.8 %** — **4.9× over budget. Not met.** The trim removes the gain and Δ`V_BE` terms but not the amplifier offset, whose surviving lever measures **−1.32/−1.34 °C/mV cold, +1.94/+2.02 °C/mV hot** (confirming `design/temp_core.md`'s +1.21 / ±1.87 °C/mV). Even with `V_os` = 0 the ½-LSB quantisation plus the unexplained curvature residue leave ≈3.6 °C at 3σ. Target **not relaxed** — see [DR-011](decision-records/DR-011-temp-accuracy-mismatch-not-met.md). Evidence: [`sim/temp-accuracy-mc/records/20260802-082345-989ce7a.md`](../sim/temp-accuracy-mc/records/20260802-082345-989ce7a.md), [`…-breakdown.md`](../sim/temp-accuracy-mc/records/20260802-082345-989ce7a-breakdown.md). | **[3σ]** · `pending #1` (measured, not met; re-design decision pending per DR-011) | **[DR-002, DR-005, DR-011]**, derived `sim/temp-accuracy-vt/analyze_derived.py` (record `20260801-121458-660d016-derived`) + `sim/temp-accuracy-mc/` (record `20260802-082345-989ce7a`) · #13, #15 |
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
| <a id="por-vth-rise"></a>`por-vth-rise` | **VPOR↑** — release threshold, rising VDD | **2.47 V** | **2.60 V** | **2.73 V** | **Max binds at SS / −40 °C**; min binds at FF / +125 °C. **Measured (assembled path, deterministic corner-worst-case, full 81-point grid)**: **2.58384–2.64453 V**, 81/81 within [2.47, 2.73] V — max at `ss_-40c_3.63v` (2.64453 V), min at `bjt_ff_125c_2.97v` (2.58384 V), confirming the predicted binding corners. **Measured (Monte Carlo, local mismatch on, N = 500 at each of the five named binding points)**: σ = **12.2–14.3 mV**, mean ± 3σ spanning **2.5583–2.6470 V** across all five points, **100 % empirical yield**, parametric 3σ inside [2.47, 2.73] V at every point — **met, with ≈83 mV of margin at the nearer edge.** Evidence: [`sim/por-vth/records/20260801-233802-32fbaa0.md`](../sim/por-vth/records/20260801-233802-32fbaa0.md), [`sim/por-threshold-mc/records/20260802-083749-3b9b414.md`](../sim/por-threshold-mc/records/20260802-083749-3b9b414.md). | **[3σ]** · `ratifiable` (mismatch-inclusive; #15's MC closes the `conditional` tag) |
| <a id="por-vth-fall"></a>`por-vth-fall` | **VPOR↓** — assert threshold, falling VDD | **2.22 V [P]** | **2.45 V [P]** | **2.63 V [P]** | Derived edge-by-edge from VPOR↑ and V_hys (see below); min binds at FF / +125 °C with maximum hysteresis. **Measured (assembled path, full 81-point grid)**: **2.38722–2.45092 V**, 81/81 within [2.22, 2.63] V — min at `res_ss_-40c_3.63v` (2.38722 V), max at `bjt_ss_125c_2.97v` (2.45092 V). **Measured (Monte Carlo, local mismatch on, N = 500 at each of the five named binding points)**: σ = **11.4–13.4 mV**, mean ± 3σ spanning **2.4002–2.4807 V**, **100 % empirical yield**, parametric 3σ inside [2.22, 2.63] V at every point — **met, with ≈180 mV of margin at the nearer edge.** **Scope caveat (#61, [DR-013](decision-records/DR-013-por-brownout-spurious-assert.md)):** the above is measured against a continuous, quasi-static ramp (~243–408 V/s falling); a *dip/recovery* falling profile inside the same ratified `por-ramp-rate` envelope but at a faster rate (770–7670 V/s) is confirmed to **violate** this row's own assert-threshold band at up to 91 % of the grid — see [`por-brownout`](#por-brownout)'s amendment. That finding is not silently absorbed here: this row's `ratifiable` status stands on the monotonic-ramp evidence that supports it, not on the dip-shaped condition DR-013 measures. Evidence: [`sim/por-vth/records/20260801-233802-32fbaa0.md`](../sim/por-vth/records/20260801-233802-32fbaa0.md), [`sim/por-threshold-mc/records/20260802-083749-3b9b414.md`](../sim/por-threshold-mc/records/20260802-083749-3b9b414.md). | **[3σ]** · `ratifiable` (mismatch-inclusive; #15's MC closes the `conditional` tag; scoped to continuous-ramp falling rates only — see caveat) |
| <a id="por-hysteresis"></a>`por-hysteresis` | **V_hys** = VPOR↑ − VPOR↓ | **100 mV** | **150 mV [P]** | **250 mV [P]** | Both edges measured **at the same corner point** (hysteresis is a same-die difference, not a corner-to-corner one). **Measured (assembled path, full 81-point grid)**: **164.633–248.74 mV**, 81/81 within [100, 250] mV — min at `ff_125c_2.97v`, max at `ss_-40c_3.63v`. **Measured (Monte Carlo, local mismatch on, N = 500 at each of the five named binding points; both edges taken from one triangle ramp on the same die, so the figure stays a same-die difference under mismatch)**: σ = **0.77–0.97 mV**, mean ± 3σ spanning **150.48–166.51 mV**, **100 % empirical yield**, parametric 3σ inside [100, 250] mV at every point — **met, with ≈50 mV of margin above the 100 mV floor.** Mismatch is a far weaker term here than on the absolute thresholds because both edges share the same divider and the same comparator offset, which largely cancels in the difference. **Scope caveat (#61, [DR-013](decision-records/DR-013-por-brownout-spurious-assert.md)):** as with `por-vth-fall` above, this row's evidence is a continuous quasi-static ramp; the dip-shaped falling condition DR-013 measures produces a `VPOR↓` violation at up to 91 % of the grid at a faster (but still envelope-inside) falling rate, which correspondingly moves the *measured* hysteresis at those points — not absorbed into this row's own verdict, which stands on its own (different-topology) evidence. Evidence: [`sim/por-vth/records/20260801-233802-32fbaa0.md`](../sim/por-vth/records/20260801-233802-32fbaa0.md), [`sim/por-threshold-mc/records/20260802-083749-3b9b414.md`](../sim/por-threshold-mc/records/20260802-083749-3b9b414.md). **Post-layout finding (#85, not yet a ratified spec change):** the composite/extracted full-assembly netlist (`layout/postlayout/temp_por_top.spice`, #82/PR #180) reproduces 80/81 grid points inside [100, 250] mV but the single worst-case corner, `ss_-40c_3.63v`, measures **261.092 mV** — 11.1 mV over the 250 mV ceiling (vs. 248.74 mV on the schematic-level record above, which itself had only 1.26 mV of margin there) — both edges move apart (VPOR↑ +4.2 mV, VPOR↓ −8.16 mV at that corner) once the real drawn-and-extracted `ppolyf_u_1k` divider and `bias_core`'s real corner-dependent VREF/IBIAS replace the schematic-ideal/idealised-stimulus pair. Not silently absorbed: routed to [#187](https://github.com/2AMLogic/gf180-temp-por/issues/187) rather than revised here — a ratified-value change needs its own decision record, and #85 is verification-only. This row's `ratifiable` status stands on the schematic-level evidence cited above pending #187's resolution. Post-layout evidence: [`sim/por-vth/records/20260811-073945-12473c3.md`](../sim/por-vth/records/20260811-073945-12473c3.md). | **[3σ]** · `ratifiable` (mismatch-inclusive; #15's MC closes the `conditional` tag; scoped to continuous-ramp falling rates only — see caveat; post-layout regression at 1/81 points routed to #187, not yet reflected in this verdict) |

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
| <a id="por-ramp-rate"></a>`por-ramp-rate` | Supply ramp-rate envelope | Correct reset generation guaranteed for **monotonic 0 → VDD ramps with average rate between 1 V/s (slow limit) and 1 V/µs (fast limit) [P]** | "Correct" = `RESETn` low from 0 V throughout the ramp, released once and only once, after VDD crosses VPOR↑ and the [`por-reset-pulse`](#por-reset-pulse) has elapsed — no early release, no glitch, no double pulse. **Both limits bind at SS / −40 °C** (weakest startup-assist leg — devchar measures the native device's Vt turning slightly *positive* at `ss` — and slowest bias-core settling). #14 asserts at both endpoints plus one decade inside each, over the full grid. Outside the envelope behaviour is unspecified, not guaranteed-wrong. **Measured (assembled path, full 81-point grid, all four rates: 1 V/s, 10 V/s, 0.1 V/µs, 1 V/µs)**: **81/81 PASS** — `RESETn` releases **once and only once** at every corner and every rate (`chatter_* = 0` everywhere against a ≤1 ns bound; `vddrel_*` ≥ 2.572 V at every point, above VPOR↑,min; `t_release_*` live at every point). **This row's own criterion is now met at all four rates; its `pending #1` status is carried solely by `design/bias_core.md`'s starved-loop window, which is a separate, architecture-level question.** ¶ *History (superseded record `20260802-000004-32fbaa0`, 21/81):* the same grid previously showed release-edge chatter at up to **60/81 points per rate**, to **109.6 µs**, at **all four rates including the two slow ones** where `bias_core`'s starved-loop window (a slew-limited effect specific to the fast 1 V/µs limit) cannot apply. [DR-015](decision-records/DR-015-por-ramp-rate-chatter-root-cause.md) correctly excluded the starved-loop window but mislocalised the mechanism inside `por_output_chain`; **[DR-016](decision-records/DR-016-por-ramp-rate-chatter-release-latch.md) supersedes it with the measured root cause and the fix**. The loop ran *outside* that cell: `RESETn`'s own release enables `temp_core` (whose `EN` pin **is** `RESETn`), adding a mirror diode to the **shared `IBIAS` node** and stepping it down 34.4 mV, which walks `por_output_chain`'s nA trip detector back across its decision point until `RESETn` re-asserts — disabling `temp_core` again and restarting the cycle. Loop-break control arms (`temp_core.EN` tied to either rail) remove the chatter with no device change; the shipped fix is one device, `XMRLK`, latching the release. This is the **dynamic** counterpart to [DR-010](decision-records/DR-010-shared-ibias-disabled-consumer-contract.md)'s static shared-node contract. Evidence: [`sim/por-ramp-rate/records/20260802-205904-bdc077d.md`](../sim/por-ramp-rate/records/20260802-205904-bdc077d.md) (supersedes [`20260802-000004-32fbaa0`](../sim/por-ramp-rate/records/20260802-000004-32fbaa0.md)), root cause [`sim/por-ramp-rate/control/results.md`](../sim/por-ramp-rate/control/results.md). | **[CWC]** · `pending #1` (chatter sub-issue **closed by measurement** — 81/81 at all four rates; the row still awaits the separate, architecture-level starved-loop window and #1's ratification pass) | this amendment, root-caused and fixed by **[DR-016]** (superseding **[DR-015]**) · #14, #56 |
| <a id="por-brownout"></a>`por-brownout` | Brownout re-assertion | **No dedicated brownout detector in wave 1 [P]** — re-assertion is whatever the POR comparator itself provides. Guaranteed for a dip that (a) takes VDD **below VPOR↓,min = 2.22 V**, (b) **stays below VPOR↓ for ≥ T_dip,min = 10 µs [P]**, and (c) **falls no faster than `dVDD/dt`\|fall,max = 2.30 mV/µs** ([DR-011](decision-records/DR-011-brownout-falling-slew-limit.md), characterized by #60 on the schematic netlist at 3.40 mV/µs and **re-cost to 2.30 mV/µs against the extracted netlist** by [DR-019](decision-records/DR-019-brownout-falling-slew-postlayout-recost.md), #188) | Dips shallower than VPOR↓,max or shorter than the deglitch dwell are **explicitly not guaranteed** to assert reset — that rejection is DR-005's deliberate deglitch function, owned by #12. **That carve-out is `POR_RAW`-scoped, not `VDD`-scoped**: `sim/por-glitch/control/` shows the deglitch dwell has no dependence at all on a disturbance applied to `VDD` itself (as opposed to `POR_RAW` while `VDD` holds steady) — see [DR-014](decision-records/DR-014-por-glitch-vdd-level-immunity.md) and `design/por_output_chain.md`, "Why the deglitch dwell cannot reject a VDD-level glitch". T_dip,min must exceed #12's deglitch dwell time (**[TBD-#12]**, required ≤10 µs for this row to hold). On re-assertion the full [`por-reset-pulse`](#por-reset-pulse) is regenerated. **Binds at SS / −40 °C** (slowest comparator response). **Measured (assembled path, full 81-point grid, 1.0 V dip / 10 µs dwell)**: **0/81 PASS.** `resetn_floor_in_dip_mv` is pinned at **999.959–1000 mV** at every corner (bound: max 100 mV) — `RESETn` essentially does not drop from the dip rail during the dip at any corner. `t_reassert_us` also misses its 50 µs bound by a small, near-PVT-independent margin (**51.26–51.58 µs**) at every corner. **Root-caused by #55 ([DR-011](decision-records/DR-011-brownout-falling-slew-limit.md)), and the below-operating-floor hypothesis is refuted**: the discriminator is the rail's **falling slew rate**, not the dip's depth or its duration. A dip to 2.30 V — above `vdd_ref90_v`'s 1.788 V worst case at every corner — fails identically, and a dip held below VPOR↓,min for **5001 µs** (500× `T_dip,min`) at the deck's 1 µs edge still does not assert. The measured boundary is between **7.67 and 11.50 mV/µs**, corroborating `design/bias_core.md`'s independently derived ~21 mV/µs `PG` slew capability: above it the PMOS mirror bank is driven fully off (`V_sg` 776.2 mV → **−74.4 mV**), every downstream bias dies, and `BIAS_OK` reads a **false valid** throughout — `design/bias_core.md`'s starved-loop window on the falling edge. **#60 characterized this across the full 81-point grid** (`sim/por-brownout-slew/`, a falling-slew ladder refined by bisection): the boundary **binds at SS/−40 °C/2.97 V**, confirming the corner this row already named. PASS (81/81, robust margins) is confirmed at **3.40 mV/µs**; FAIL (that corner, plus its 3.30 V/3.63 V siblings) is confirmed from **3.4795 mV/µs** — the transition is a knife-edge, non-monotonic in slew rather than a single clean threshold (see [`sim/por-brownout-slew/records/20260802-120940-3c3e728-boundary.md`](../sim/por-brownout-slew/records/20260802-120940-3c3e728-boundary.md)), so the ratified bound sits on the safe side of the whole transition band rather than at a bisected midpoint. `dVDD/dt|fall,max = 3.40 mV/µs` was ratified against this evidence, satisfying DR-011 decision 2 at the schematic level. **Post-layout re-cost (#188, [DR-019](decision-records/DR-019-brownout-falling-slew-postlayout-recost.md)):** that bracket was measured on the schematic export, and it does not survive the extraction. Re-running the ladder against `layout/postlayout/temp_por_top.spice` (#82/PR #180) puts the **ratified 3.40 mV/µs rung at 76/81** — failing at `ss_-40c_{2.97,3.30,3.63}v` and `res_ss_-40c_{2.97,3.30}v`, this row's own binding family — and locates the extracted netlist's transition edge between **2.45 and 2.50 mV/µs** (2.30 / 2.40 / 2.45 mV/µs all 81/81; 2.50 mV/µs 80/81; 3.46 mV/µs 75/81). It is the same mechanism, deeper, not a second one: at the ratified slew the extraction drives `V_sg` on `bias_core`'s mirror bank from −116.1 mV to **−297.5 mV** at `ss_-40c_3.63v` and `por_output_chain`'s deglitch ramp never starts at all (peak `NDG`/VDD 0.706 → **0.000**), so the failure is DR-011's *no decision* mode. **The bound therefore moves to 2.30 mV/µs**, chosen so the extracted netlist carries at least the dip-window margin the outgoing bound had on the schematic one (+209.8 µs vs. +108.8 µs at the binding point) rather than sitting one bisection step below a FAIL; it passes 81/81 at **both** netlist levels. Not absorbed silently — a weakened guarantee, argued and costed in DR-019. **Separately re-attributed (#188):** the `t_reassert_us` slip and lost `ss_-40c_2.97v` re-assert that #87's post-layout `por-brownout` record reported against the 2026-08-01 schematic baseline are **`XMRLK`'s ([DR-016](decision-records/DR-016-por-ramp-rate-chatter-release-latch.md)), not the extraction's** — that baseline predates the latch by one device, and re-running the schematic grid on today's netlist is *worse* on both counts (8 lost re-asserts, 52.01–66.24 µs) than the extracted one. Both numbers sit ~580× outside this row's guaranteed falling-slew envelope; what narrows is DR-011's "the block recovers; it does not latch up or stay released", routed to [#215](https://github.com/2AMLogic/gf180-temp-por/issues/215). `por_output_chain` is **exonerated**: at the 1.0 V dip rail with zero `IBIAS` it still reaches valid-low in 3.70–7.30 µs and sinks +71.1 µA at the 100 mV bound. Below the boundary `POR_RAW` does assert during the dip, but sub-boundary behaviour is **not** established as conforming: **#61 confirmed, on the full 81-point grid, that an intermediate falling-slew band asserts `POR_RAW` above VPOR↑,max = 2.73 V — a spurious reset at a rail still inside the ratified operating range** ([DR-013](decision-records/DR-013-por-brownout-spurious-assert.md)). At the control's own three Part-B rates (7.67 / 2.30 / 0.77 mV/µs), the full grid fails at **45/81 (56 %)**, **74/81 (91 %)**, and even the control's own "correct" 0.77 mV/µs reference point at **15/81 (19 %)** of corners — the last group overwhelmingly `−40 °C` combined with the two higher supplies. The assert rail **tracks `VDD`** (within 9 mV of a constant ~160 mV undershoot as supply varies 660 mV at fixed process/temperature) rather than sitting at a fixed absolute threshold. DR-013's arithmetic check **rules out** `design/bias_core.md`'s ≈2.4 µs × ramp-rate `VREF` feedthrough coefficient as the explanation (predicts 5.5–18.4 mV of `VREF` offset; measured offset is 81–467 mV, and in the wrong direction for the static VREF·ratio algebra to explain a *higher* assert rail) — the true dynamic mechanism remains **unidentified**, an open item for follow-up. **A distinct `VDD`-level-glitch failure, root-caused by #56**: `sim/por-glitch/`'s full-depth (0.2 V) 300 ns `VDD` glitch is its own, separately-recorded **0/81** result, and [DR-014](decision-records/DR-014-por-glitch-vdd-level-immunity.md) traces it to the `POR_RAW`-vs-`VDD` scoping gap above rather than to the falling-slew collapse this row is root-caused to (or to the below-operating-floor hypothesis #55 refuted): the deglitch dwell can only reject a disturbance presented at `POR_RAW`, so it neither rejects — nor is specified to reject — a glitch on `VDD` itself. Note the ≥1 ms pulse **is** regenerated at every corner (see [`por-reset-pulse`](#por-reset-pulse)). **The `VDD` axis is now characterized rather than merely disclaimed ([DR-017](decision-records/DR-017-por-glitch-representative-depth.md), #56)**: a two-axis sweep (`sim/por-glitch/control/depth_results.md`, 56 runs, two PVT points, two circuit arms) measures a **sharp `VDD`-glitch immunity boundary between 0.5 V and 0.65 V** of rail floor for a 300 ns excursion — identical at `tt`/27 °C/3.30 V and `ss`/125 °C/2.97 V — and **no duration dependence at all** from 10 ns to 30 µs at a 0.2 V floor, i.e. right across the 1.86–8.88 µs deglitch dwell, confirming DR-014's duration claim while **refuting its "any depth" wording**. Above the boundary the dwell is visibly doing its designed job (at `ss`/125 °C/0.65 V, `POR_RAW` touches −23 mV for 100 ns and `RESETn` never moves); below it the rail is simply too low for the block's own logic and push-pull output to hold state. **`por-glitch`'s 0.2 V therefore sits ~3× below the boundary and measures the rail collapsing rather than a deglitch decision** — whether to re-cut that check above the boundary, and whether "must never move" should become "must regenerate exactly one correctly-shaped pulse", is a ratification judgment left to #1, not taken by DR-017. Separately measured and recorded there: #56's `XMRLK` release latch (`por-ramp-rate`, [DR-016](decision-records/DR-016-por-ramp-rate-chatter-release-latch.md)) **moves that boundary by more than a volt** (from 1.4–2.0 V to 0.5–0.65 V) as a side effect of making the release one-way. Evidence: [`sim/por-brownout/records/20260801-233807-32fbaa0.md`](../sim/por-brownout/records/20260801-233807-32fbaa0.md), root cause [`sim/por-brownout/control/results.md`](../sim/por-brownout/control/results.md), falling-slew boundary characterization [`sim/por-brownout-slew/records/20260802-120940-3c3e728-boundary.md`](../sim/por-brownout-slew/records/20260802-120940-3c3e728-boundary.md) (#60, schematic) and [`sim/por-brownout-slew/records/20260811-111437-88888f3-boundary.md`](../sim/por-brownout-slew/records/20260811-111437-88888f3-boundary.md) (#188, extracted, with [`control/postlayout_margin_results.md`](../sim/por-brownout-slew/control/postlayout_margin_results.md) behind the chosen margin), post-`XMRLK` schematic re-run and its three-arm re-attribution [`sim/por-brownout/records/20260811-112115-9807e3f.md`](../sim/por-brownout/records/20260811-112115-9807e3f.md) + [`sim/por-brownout/control/recovery_results.md`](../sim/por-brownout/control/recovery_results.md) (#188), spurious-assert confirm/refute [`sim/por-brownout-spurious/records/20260802-122414-3c3e728.md`](../sim/por-brownout-spurious/records/20260802-122414-3c3e728.md) (#61, [DR-013](decision-records/DR-013-por-brownout-spurious-assert.md)), `VDD`-level-glitch scoping gap [`sim/por-glitch/records/20260802-205904-bdc077d.md`](../sim/por-glitch/records/20260802-205904-bdc077d.md) (supersedes [`20260801-233813-32fbaa0`](../sim/por-glitch/records/20260801-233813-32fbaa0.md); still 0/81, unchanged by DR-016's release latch exactly as predicted) and [`sim/por-glitch/control/results.md`](../sim/por-glitch/control/results.md) (#56, [DR-014](decision-records/DR-014-por-glitch-vdd-level-immunity.md)), `VDD`-glitch depth/duration boundary [`sim/por-glitch/control/depth_results.md`](../sim/por-glitch/control/depth_results.md) (#56, [DR-017](decision-records/DR-017-por-glitch-representative-depth.md)). | **[CWC]** · `pending #1` (measured and root-caused; falling-slew envelope's numeric bound characterized across the full 81-point grid by #60 and **re-cost post-layout by #188/DR-019 to `dVDD/dt|fall,max = 2.30 mV/µs`**, binding at SS/−40 °C/2.97 V, satisfying DR-011 decision 2 at both netlist levels — but the sub-boundary regime confirmed defective by #61/DR-013, mechanism unidentified; separately, the `VDD`-level-glitch scoping gap root-caused by #56/DR-014; row awaits #1's overall ratification pass) | this amendment, **[DR-005]**, root-caused by **[DR-011]**, falling-slew envelope characterized by **#60** and re-cost post-layout by **[DR-019]**, sub-boundary spurious assert confirmed by **[DR-013]**, deglitch-carve-out scoping clarified by **[DR-014]** and quantified on the `VDD` axis by **[DR-017]** · #12, #14, #55, #56, #60, #61, #188 |
| <a id="por-reset-pulse"></a>`por-reset-pulse` | Reset pulse width | **≥1 ms**, fixed; **no maximum specified in wave 1 [P]** | Measured on the `RESETn` **deassertion** edge (DR-004), starting when both release conditions of DR-005's startup ordering are satisfied. Programmability is stretch and explicitly de-scoped (DR-003). Measurement load **[TBD-#8/#12]** (provisional: 5 pF, no DC load **[P]**). **The ≥1 ms minimum binds at FF / −40 °C / 2.97 V**, measured (`tpulse_1x_ms` min **4.2172 ms**, `sim/por-output-chain-pulse/records/20260802-205904-bdc077d.md`, re-run on the post-#56 cell; `20260801-031819-fce635f` measured 4.21535 ms before `XMRLK`) — **not** the fixed-trip fastest-timer corner (FF / +125 °C / 3.63 V) a generic current-starved one-shot would predict. This one-shot's trip is rail-referenced (`TIM = VDD − V_sg(2.5 nA)`, not a fixed voltage), so a cold, low rail shortens the ramp more than a hot, high-bias rail does; see [DR-009](decision-records/DR-009-por-reset-pulse-binding-corner.md). "No maximum" is a decision, not an omission: an RC/current-starved one-shot spreads several× across corners; #14 records the observed max so a maximum can be added later on evidence. **Measured (assembled path, brownout-regeneration path, full 81-point grid)**: pulse regeneration after a qualifying dip (`t_pulse_regen_ms`) observed at **4.74–16.28 ms** — the ≥1 ms minimum holds at every corner (81/81), min at `ff_125c_2.97v`, max at `ss_-40c_3.63v`; no maximum bound to violate. Evidence: [`sim/por-brownout/records/20260801-233807-32fbaa0.md`](../sim/por-brownout/records/20260801-233807-32fbaa0.md). | **[CWC]** · `ratifiable` (≥1 ms minimum confirmed on assembly at both the fresh-startup and brownout-regeneration paths; no maximum specified) | **[DR-003]**, this amendment, binding corner corrected by **[DR-009]** · #14 |

### 4.3 Output interface (from DR-004)

| ID | Parameter | Value | Conditions / binding corner | Basis · Status | Source · Evidence |
|---|---|---|---|---|---|
| <a id="por-polarity"></a>`por-polarity` | Reset polarity | **`RESETn`, active low** | Degrades to *asserted* under loss of drive near 0 V — the property active-high cannot provide on a single-rail block. | — · `ratifiable` | **[DR-004]** · #12 |
| <a id="por-drive"></a>`por-drive` | Reset drive style | **Push-pull** (not open-drain) | Both states driven from within the block; no external pull-up in the specified interface. | — · `ratifiable` | **[DR-004]** · #12 |
| <a id="por-reset-valid-floor"></a>`por-reset-valid-floor` | Reset-valid floor, V_RSTVALID | **Target 0 V** — `RESETn` guaranteed valid-low for **all** VDD ≥ 0 V. Valid-low := V(`RESETn`) ≤ min(0.1 × VDD, 0.3 V) into the [`por-reset-pulse`](#por-reset-pulse) load. Acceptance fallback: **≤0.4 V [P]** if #12 demonstrates 0 V is unreachable, with the achieved floor stated. | This is the numeric row DR-004 requires #12 to fill ("`RESETn` guaranteed valid-low for VDD ≥ X"). The ratio and the absolute floor **bind at different corners, measured** (`sim/por-output-chain-floor/records/20260802-205904-bdc077d.md`, re-run on the post-#56 cell; `20260801-032940-d59d7c4` measured it before `XMRLK`): **the ratio binds at SF / +125 °C** (`floor_ratio_porlow` max 0.551 % at `sf_125c_2.97v` — maximum off-state leakage through the output pull-up relative to VDD, which the below-floor pull-down must overpower), while **the absolute floor binds at SS / −40 °C** (`floor_mv_porlow` max 1.74 mV at `ss_-40c_2.97v` — weakest pull-down drive; 1.699 mV before `XMRLK`, i.e. the latch costs 0.04 mV of a 300 mV budget). See [DR-009](decision-records/DR-009-por-reset-pulse-binding-corner.md). **This single-cell, slow-ramp-from-0V characterization stands unchanged and PASSES.** #14's charter was to additionally confirm the floor at the brownout dip rail (1.0 V) on the full assembly, with `bias_core`'s real dynamics in the loop — this is a **different, dynamic** condition (a sudden dip from live operation, not a static ramp from 0 V) and it reads `resetn_floor_in_dip_mv` = 999.959–1000 mV at every one of 81 corners against a 100 mV bound. **#55 re-attributes that number ([DR-011](decision-records/DR-011-brownout-falling-slew-limit.md)): it is not a floor failure.** `resetn_floor_in_dip_mv` samples `RESETn` at a fixed instant inside the dip, so it reads the floor only *if re-assertion has already happened* — a dependent measurement. At ~1000 mV it is reading `RESETn` still in its **released** state, correctly tracking the rail, because the [`por-brownout`](#por-brownout) decision never arrived at the deck's 2.3 V/µs falling edge. The floor claim itself is substantiated by #12's single-cell 0 V-ramp record and additionally by #55's cell-level control at the 1.0 V dip rail, where `por_output_chain` reaches valid-low in **3.70–7.30 µs** and sinks **+71.1 µA** against a clamp at the 100 mV bound — unchanged from 500 nA `IBIAS` down to **zero** `IBIAS` ([`sim/por-brownout/control/results.md`](../sim/por-brownout/control/results.md) § C). This row's `pending #1` is therefore carried by the `por-brownout` defect it depends on, not by any deficiency in the output stage. | **[CWC]** · `pending #1` (0V-ramp claim ratifiable per #12's own record; the brownout-dip number re-attributed to `por-brownout` by DR-011, and the below-floor drive it was meant to test independently confirmed) | **[DR-004]**, this amendment, binding corner corrected by **[DR-009]**, re-attributed by **[DR-011]** · #10, #12, #14, #55 |

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
   rows. **Amended by [DR-018](decision-records/DR-018-por-iq-recost.md):**
   this was true by construction only while `por-iq` (<1 µA) + `temp-iq`
   (<20 µA) summed exactly to `iq-total`'s 21 µA. DR-018 re-costs `por-iq` to
   <3.0 µA without changing `temp-iq` or `iq-total`, so 3.0 + 20 = 23 µA no
   longer equals 21 µA: a design that individually meets both sub-ceilings is
   **not** structurally guaranteed to meet `iq-total`. `iq-total` is now an
   independently-ratified ceiling, verified directly against its own measured
   evidence rather than reconstructed from the two sub-budgets — any future
   change to either contributing cell must re-check it directly.

| ID | Parameter | Target | Stretch | State / binding corner | Basis · Status |
|---|---|---|---|---|---|
| <a id="por-iq"></a>`por-iq` | POR quiescent current | **<3.0 µA [DR-018]** (was <1 µA — re-costed by [DR-018](decision-records/DR-018-por-iq-recost.md)) | ~~<0.3 µA~~ — **withdrawn: requires architecture revision [P]** | `RESETn` asserted, temperature sensor disabled, per rule 1 above. **Binds at FF / +125 °C / 3.63 V.** **Measured (assembled path, schematic, published)**: **0.656667–2.384647 µA** over the full 81-point grid, binding corner `ff_125c_3.63v` (2.384647 µA) — **81/81 within the DR-018-recosted 3.0 µA ceiling, 20.5 % margin at the binding corner.** Evidence: [`sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md`](../sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md). **Measured (assembled path, post-layout, #87)**: **0.656367–2.38347 µA**, same binding corner (2.38347 µA, uniformly ~0.05 % lower than the schematic reading at every one of the 81 points) — **81/81 within the 3.0 µA ceiling**, confirming the re-cost holds on the real klt-extracted netlist, not only the schematic. Evidence: [`sim/temp-por-top-release/records/20260811-064427-564950b.md`](../sim/temp-por-top-release/records/20260811-064427-564950b.md). **This row's own named publishing experiment (`sim/por-iq/`) now carries its own post-layout-derived record too (#207)**: **0.656367–2.383469 µA**, same binding corner (2.383469 µA) — **81/81 within the DR-018-recosted 3.0 µA ceiling (this record checks only against the currently-ratified ceiling — see #207)**, matching `temp-por-top-release`'s independent post-layout reading to within 1 nA at the binding corner. Evidence: [`sim/por-iq/records/20260811-084152-68c0017-por-iq-derived.md`](../sim/por-iq/records/20260811-084152-68c0017-por-iq-derived.md). Against the withdrawn 1.0 µA ceiling the first two records still read 27/81 and 27/81 PASS respectively (54/81 FAIL) — this is the already-owned, already-tracked architecture-level overrun `design/bias_core.md`'s "Iq apportionment" predicted (2.37× from summed per-cell numbers: 929 nA `bias_core` core + 1119 nA `IBIAS` leg + 292 nA `por_comparator` + 31.6 nA `por_output_chain` = 2371 nA), now confirmed on the real assembly at both netlist levels — see [DR-018](decision-records/DR-018-por-iq-recost.md) for the margin arithmetic and why 3.0 µA rather than the bare measured maximum. **The separate starved-loop window** (`design/bias_core.md`, "The starved-loop window") is a distinct, still-open tension between this row and [`por-ramp-rate`](#por-ramp-rate) that DR-018 explicitly does not resolve — see that record's Consequences. | **[CWC]** · `pending #1` (re-costed to 3.0 µA and met per DR-018, measured on both netlist levels; DR-018 itself awaits #1's overall ratification pass) |
| <a id="iq-total"></a>`iq-total` | Total block quiescent current | **<21 µA [P]** — **independently ratified as of [DR-018](decision-records/DR-018-por-iq-recost.md)**, no longer the literal sum of `por-iq` + `temp-iq`'s own ceilings (3.0 + 20 = 23 µA ≠ 21 µA); see §5 rule 3 | — | Normal operation: `RESETn` released, sensor enabled. **Binds at FF / +125 °C / 3.63 V.** Feeds [`temp-self-heating`](#temp-self-heating). **Measured (assembled path, published)**: **6.457–18.288 µA** over the full 81-point grid, binding corner `ff_125c_3.63v` (18.288 µA), **81/81 PASS**, 13 % margin at the binding corner — `por-iq`'s published 0.657–2.385 µA (`sim/por-iq/`) summed with `temp-iq`'s measured 5.80–15.90 µA (`sim/temp-accuracy-vt/`) at matching grid points. **`<21 µA` target: met**, ratifiable on this evidence even though `por-iq` alone was not (pre-DR-018) / is now met against its own re-costed 3.0 µA ceiling (post-DR-018). **DR-018 confirmed this row's evidence and margin are unaffected by the `por-iq` re-cost** — no circuit changed, only the recorded `por-iq` ceiling moved to match already-measured reality — but a future design change to either contributing cell must re-verify this row directly rather than assume compliance with the two sub-ceilings suffices (see §5 rule 3). Evidence (schematic): [`sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md`](../sim/por-iq/records/20260801-121458-660d016-por-iq-derived.md). **Measured (assembled path, post-layout, #207)**: **6.445774–18.249150 µA**, same binding corner (18.249150 µA) — **81/81 PASS**, 13.1 % margin at the binding corner, confirming the schematic reading holds on the real klt-extracted netlist. Evidence (post-layout): [`sim/por-iq/records/20260811-084152-68c0017-por-iq-derived.md`](../sim/por-iq/records/20260811-084152-68c0017-por-iq-derived.md). | **[CWC]** · `ratifiable` (measured; target met) |

**Why the <0.3 µA stretch is withdrawn rather than carried.** It sits *below
the floor of DR-005's own 0.3–0.8 µA estimate* for the precision path alone,
before the ~0.1 µA assist leg and the pulse timer are added. The published
designs that do reach nA class are VTH-referenced/subthreshold or duty-cycled
— precisely the architecture classes DR-005 rejected (correctly, on threshold
accuracy) and which nothing in this repo proposes. Withdrawing it is **not** a
relaxation of a target: it removes a stretch goal that the ratified
architecture cannot reach by construction. Restoring it requires a new
decision record naming the mechanism that pays for it.

**Known accounting risk — owned by #11, resolved by [DR-018](decision-records/DR-018-por-iq-recost.md).**
DR-005 charges the shared core's 1–5 µA/branch to its *temperature-sensor*
estimate, while its startup ordering has that same core live and settled
**before** POR releases. Under rule 1 that current lands in
[`por-iq`](#por-iq). #11 measured that the shared core's reset-asserted-state
current does **not** fit inside <1 µA (`design/bias_core.md`, "Iq
apportionment": 2371 nA at the binding corner, 2.37× over), so per this
amendment's own instruction #1 has re-costed the row: DR-018 moves `por-iq`
to <3.0 µA rather than relax the arithmetic to fit the original number. The
conflict this amendment flagged is now closed by a decision record, not by a
silent edit.

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
| ~~All **[3σ]** rows~~ | ~~Monte-Carlo mismatch evidence (they are `conditional` until it lands)~~ — **closed by #15**: `sim/temp-accuracy-mc/` and `sim/por-threshold-mc/`, N = 500 per binding point at every row's own binding point. Three POR rows pass; the two temperature-accuracy rows miss and are recorded as such under [DR-011](decision-records/DR-011-temp-accuracy-mismatch-not-met.md) | ~~#15~~ |
| [`temp-accuracy-untrimmed`](#temp-accuracy-untrimmed), [`temp-accuracy-trimmed`](#temp-accuracy-trimmed) | A `temp_core` revision that meets them. #15 measured the miss and published the per-term sensitivities a fix has to be sized against ([DR-011](decision-records/DR-011-temp-accuracy-mismatch-not-met.md), "Alternatives considered"); choosing between growing the input pair, chopping/auto-zeroing, fixing the mirror ratio and re-balancing the trim ladder is a design decision, not a measurement | #1, #17 |

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
| `por-brownout`'s falling-slew qualification clause, and the re-attribution of `por-reset-valid-floor`'s brownout-dip number away from the output stage | DR-011 (brownout falling-slew limit) |
| `temp-vt-transfer` published measured value, `temp-accuracy-untrimmed`/`temp-accuracy-trimmed` systematic/corner share, `temp-supply-sensitivity`, `temp-iq` — all on the real assembled path (`design/netlist/temp_por_top.spice`, post-#41/DR-010) | #13 (`sim/temp-accuracy-vt/`) |
| The **local-mismatch** share of all five **[3σ]** rows, at each row's own binding point (N = 500 each): the three POR rows' measured pass, and the two temperature-accuracy rows' measured miss with its per-device attribution | #15 (`sim/por-threshold-mc/`, `sim/temp-accuracy-mc/`) |
| `temp-accuracy-untrimmed`/`temp-accuracy-trimmed` recorded as not-met with the targets left intact | DR-011 (temperature-accuracy mismatch outcome) |
| `por-brownout`'s deglitch-rejection carve-out clarified as `POR_RAW`-scoped, not `VDD`-scoped (root cause of `por-glitch`'s 0/81 result) | DR-014 (por-glitch VDD-level immunity), #56 |
| `por-ramp-rate`'s release-edge chatter root-caused to `por_output_chain`'s trip detector (not the starved-loop window); value/status unchanged | DR-015 (ramp-rate chatter root cause), #56 — **superseded by DR-016** |
| `por-ramp-rate`'s measured result replaced with **81/81 PASS at all four rates**: the chatter re-root-caused to a relaxation loop through the **shared `IBIAS` node** (`RESETn` → `temp_core.EN` → `IBIAS` → `por_output_chain`'s starve bias) and fixed by one device, `XMRLK`. Ratified value and `pending #1` status unchanged; the row's `pending` is now carried by the starved-loop window alone | DR-016 (ramp-rate chatter release latch), #56 |
| `por-brownout`'s deglitch carve-out gains a **measured `VDD`-axis boundary** (300 ns excursion: immune ≥0.65 V, regenerates ≤0.5 V, no duration dependence 10 ns–30 µs), and the conclusion that `por-glitch`'s 0.2 V is not a representative depth. No ratified value added, removed or relaxed | DR-017 (por-glitch representative depth), #56 |
| `por-iq` re-costed from <1 µA to <3.0 µA against the measured 2.37–2.38× apportionment overrun (schematic and post-layout); `iq-total` decoupled from being the literal sum of `por-iq` + `temp-iq`'s own ceilings, retained at <21 µA as an independently-ratified value on unchanged measured evidence | DR-018 (por-iq re-cost), #189, #87 |
| `por-brownout`'s falling-slew clause (c) re-cost from 3.40 mV/µs to **2.30 mV/µs** against the klt-extracted netlist, where the ratified rung measures 76/81 and the transition edge sits between 2.45 and 2.50 mV/µs; the `t_reassert_us`/lost-re-assert deltas #87 reported for `sim/por-brownout/` re-attributed from the extraction to `XMRLK` (DR-016) | DR-019 (brownout falling-slew post-layout re-cost), #188, #87 |
| `bias_core`'s measured `IBIAS` PVT tolerance (0.594×–2.236× nominal, post-layout) confirmed inside `por_output_chain`'s 0.44×–4.7× safe envelope; `por_output_chain`'s own 1.00 µs post-layout `POR_RAW` chatter-rejection floor found unverifiable against a real-world excursion width with any existing deterministic-corner deck, and routed onward. No ratified value added, removed or relaxed | DR-020 (por_raw chatter width out of reach), #199 |

The eight rows of the deleted README draft table are all present here:
temp range → [`temp-range`](#temp-range); temp accuracy →
[`temp-accuracy-untrimmed`](#temp-accuracy-untrimmed) +
[`temp-accuracy-trimmed`](#temp-accuracy-trimmed); temp interface →
[`temp-interface`](#temp-interface); temp Iq → [`temp-iq`](#temp-iq); POR
threshold → [`por-vth-rise`](#por-vth-rise) + [`por-vth-fall`](#por-vth-fall);
POR hysteresis → [`por-hysteresis`](#por-hysteresis); POR Iq →
[`por-iq`](#por-iq); POR reset pulse → [`por-reset-pulse`](#por-reset-pulse).
No target value carried from those rows was loosened.
