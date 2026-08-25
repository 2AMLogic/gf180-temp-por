# Chipalooza Challenge #3 proposal — temperature sensor + POR/brownout supervisor

Analog-IP proposal for [Open Circuit Design's Chipalooza Challenge #3](https://opencircuitdesign.com/chipalooza/challenge-3.html)
(GF180MCU / Wafer.Space). This document is written to be sent verbatim; it
contains no personal or institutional identifiers. Designer CVs and the
test-equipment list are separate email attachments outside this repository,
per the challenge's submission process.

Every numeric claim below is re-derived from this repository's own `sim/`
evidence at the challenge rails (or explicitly marked as not yet
characterized there — no number in this document is copied from
`spec/target-spec.md` without being re-checked against that file's cited
`sim/` records). `spec/target-spec.md` remains the authoritative,
decision-record-backed target spec for this block; this document is a
rails-specific extract of it for the purposes of this proposal, not a
replacement for it.

---

## 1. Type of IP block

A combined SoC housekeeping macro: an analog PTAT/CTAT temperature sensor
integrated with a power-on-reset and brownout supervisor, sharing one
on-chip bias/reference core.

## 2. I/O list, including test ports

### 2.1 Rails

| Rail | Use in this proposal |
|---|---|
| 3.3 V digital | This block's **only** supply rail (`VDD`, `VSS`). The block is a single-supply design: `VDD` powers the digital output driver, the analog bias/reference core, and the sensing/comparator amplifiers alike. Ratified range 3.3 V ±10 % (2.97–3.63 V steady state), per [DR-001](../../spec/decision-records/DR-001-supply-flavor.md). |
| 5.0 V analog | **Not consumed by this block.** See §4's rail-gap note — the block's active devices are gf180mcu's 3.3 V-core flavor (`nfet_03v3`/`pfet_03v3`) only; DR-001 explicitly rejected the 5 V-flavor alternative because 3.3 V-core devices cannot sit directly on a 5 V rail without Vgs/Vds overstress. If the test board provides a shared 5.0 V analog rail to every block, this block's pad for it (if the harness requires one to be present) should be left unconnected or tied to the 3.3 V rail — it is not used internally. |

### 2.2 Bandgap-referenced bias voltage / current sources

Not consumed from the harness. This block already carries its own internal
reference and bias generator (`bias_core`, always-on): an internal 1.20 V
reference (`VREF`) and a 0.5 µA (nominal) shared bias current (`IBIAS`),
both generated on-die and distributed internally to the sensing core and the
POR comparator/output chain (`design/README.md` → "Internal nets";
[`design/bias_core.md`](../../design/bias_core.md)). No harness-supplied
bandgap voltage or current source is required. Both nodes are, however,
useful bring-up/debug test points and are offered as shared analog lines
below rather than left fully internal.

### 2.3 Digital control inputs — 6 of 24 used

| Signal | Width | Purpose | Status |
|---|---|---|---|
| `TRIM<5:0>` | 6 | Repurposes the existing 6-bit binary-weighted PTAT-gain trim ladder (`design/temp_core.md` § "Trim: single 25 °C gain trim", switches `XSW5..XSW0`) from a wave-1 metal-strap option into bonded digital pins, so the 1-point 25 °C trim can be measured and swept per packaged die instead of being fixed at mask time. `spec/target-spec.md#temp-trim-strategy` already anticipates this ("the drop-in hook-up point for a fuse/OTP bit-cell array in a later wave"). | **Schematic change not yet made** — the switch gates today strap to `VDD`/`VSS`, not to pads. Rewiring six gates to pads is small and does not touch the trim mechanism itself; it needs to land before the Oct 5 schematic review if trim sweeping is wanted on the packaged part. |

18 control-input slots remain unused; no other digital control input exists
in the current wave-1 design (`design/README.md` § "Top-level pinout
(ratified)": "No trim/config/programming pins").

### 2.4 Digital test outputs — 2 of 12 used (plus the functional `RESETn` output)

| Signal | Purpose | Status |
|---|---|---|
| `POR_RAW` | `por_comparator`'s raw hysteretic threshold decision, active high, **before** the deglitch filter and one-shot timer (`design/por_comparator.md`, `design/README.md` internal-nets table). Bonding this out lets a bench measurement separate the comparator's threshold behavior from the output chain's timing behavior — directly useful for the VPOR↑/VPOR↓/hysteresis measurements in §5. | Internal net today; would need to be routed to a pad. |
| `BIAS_OK` | `bias_core`'s "reference/bias core is up and settled" flag, active high, rail-to-rail (`design/bias_core.md`). Useful at bring-up to confirm the always-on core is alive independent of the POR decision. | Internal net today; would need to be routed to a pad. |

`RESETn` (§2.5) is the block's one *functional* digital output and doubles
as the primary test output; it is not double-counted against this 12-slot
budget. 10 test-output slots remain unused — headroom for a future addition
(e.g. the deglitch-filter node `PGDG` or the one-shot timer node `TIM`,
both named in `design/por_output_chain.md`) if a specific bring-up need
justifies it; none is proposed here to keep the schematic-review change
small.

### 2.5 Dedicated (non-shared, low-resistance) pads — 3 of 4 used

| Signal | Why dedicated, not shared/multiplexed |
|---|---|
| `PTAT`, `CTAT` | Existing analog outputs ([DR-002](../../spec/decision-records/DR-002-temp-interface.md)). The temperature-accuracy budget these feed is already tight at the pin — `spec/target-spec.md#temp-accuracy-untrimmed`/`temp-accuracy-trimmed` are currently **not met** at 3σ (§4) with *zero* added series impedance. Any shared-bus multiplexer's Ron/leakage/charge-injection would add offset error on top of an already-blown budget, so these must stay dedicated, low-resistance pads, not multiplexed analog lines. |
| `RESETn` | Existing reset output ([DR-004](../../spec/decision-records/DR-004-reset-polarity-drive.md)), push-pull, deliberately asymmetric drive (`XMON` 10 µm/0.5 µm pull-down, 20:1 against the pull-up `XMOP`, per `design/por_output_chain.md`) sized to source/sink a real downstream logic load and to hold valid-low from 0 V (`spec/target-spec.md#por-reset-valid-floor`). A multiplexer in this path would degrade `V_OL`/`V_OH` and risk missing a glitch or an early-release event during bring-up — it must be a dedicated pad. |

1 dedicated-pad slot remains unused.

### 2.6 Shared (multiplexed) analog lines — 2 of 4 used

| Signal | Purpose |
|---|---|
| `VREF` | `bias_core`'s internal 1.20 V reference — the value `por_comparator`'s divider is ratioed against (`design/bias_core.md`, `design/por_comparator.md`). Bonding it out as a shared/muxed test point (not a dedicated pad, since it does not feed the accuracy-critical path directly) lets bring-up verify the reference independently of the threshold decision it drives. |
| `IBIAS` | `bias_core`'s internal 0.5 µA (nominal) shared bias node, distributed to all three consumer cells (`design/README.md` internal-nets table; [DR-010](../../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md) governs its disabled-consumer contract). Probing a sub-µA current node through a shared/muxed pad changes its own loading, so this tap should be treated as coarse/qualitative (presence/rough magnitude), not as a precision current-source output — an open item for the schematic-review stage to size correctly (e.g. a buffered current mirror copy rather than a direct tap on the shared node, so the mux does not perturb the node DR-010 constrains). |

2 shared-analog-line slots remain unused.

### 2.7 Pinout summary

| Bucket | Used | Budget |
|---|---:|---:|
| Rails | 1 (3.3 V digital; 5.0 V analog unused) | 3.3 V + 5.0 V |
| Bandgap bias voltage (harness-supplied) | 0 (internal reference used instead) | n/a |
| Bandgap current sources (harness-supplied) | 0 (internal bias used instead) | ≤2 |
| Digital control inputs | 6 (`TRIM<5:0>`) | ≤24 |
| Digital test outputs | 2 (`POR_RAW`, `BIAS_OK`), + `RESETn` functional | ≤12 |
| Dedicated pads | 3 (`PTAT`, `CTAT`, `RESETn`) | ≤4 |
| Shared analog lines | 2 (`VREF`, `IBIAS`) | ≤4 |

Total new pads proposed beyond the ratified wave-1 five (`VDD`, `VSS`,
`PTAT`, `CTAT`, `RESETn`): 6 digital control inputs + 2 digital test outputs
+ 2 shared analog lines = 10, all inside the challenge's slot budget with
substantial headroom (18/24, 10/12, 1/4, 2/4 unused respectively). None of
the wave-1 ratified pads is dropped.

## 3. Functional description

This block provides two closely coupled SoC housekeeping functions from one
shared bias/reference core (`design/README.md` → "Hierarchy";
[DR-005](../../spec/decision-records/DR-005-temp-por-architecture-survey.md)):

- **Temperature sensing** (`temp_core`): a PTAT/CTAT sensing core that
  outputs two ratiometric analog voltages, `PTAT` (positive-temperature-
  coefficient, nominally +4.3 mV/K through the origin) and `CTAT`
  (negative-temperature-coefficient, nominally −1.86 mV/°C), over
  −40…+125 °C. A one-point, 25 °C gain trim (6-bit binary-weighted ladder on
  the PTAT gain resistor) corrects gain/offset; residual curvature over the
  span is not corrected in this wave. `temp_core` is enabled only after POR
  releases (`RESETn` also drives `temp_core.EN`), which keeps it out of the
  startup ordering problem.
- **Power-on reset / brownout supervision** (`por_comparator` +
  `por_output_chain`): a precision comparator measures `VDD` against the
  shared 1.20 V reference through a resistive divider with built-in
  hysteresis, producing a raw threshold decision (`POR_RAW`). A deglitch
  filter, a fixed-width (≥1 ms) one-shot timer, and a push-pull output stage
  turn that decision into `RESETn` — active low, guaranteed valid-low from
  0 V, released once and only once after `VDD` crosses the release threshold
  and the reset pulse has elapsed. The same comparator path re-asserts
  `RESETn` on a sufficiently deep, sufficiently long, sufficiently slow
  supply dip (brownout), without a second, separate detector circuit.
- **Shared core** (`bias_core`): always-on, generates the 1.20 V reference,
  the 0.5 µA shared bias current, and a "core settled" flag (`BIAS_OK`)
  that gates the comparator's decision until the reference itself is valid.
  Sharing this core across both functions is a deliberate area/Iq
  optimization (§6) rather than an accident of reuse.

The block's electrical interface in this repository today is five pads:
`VDD`, `VSS`, `PTAT`, `CTAT`, `RESETn` — no trim/config/programming pins, no
digital temperature interface (analog-only in wave 1). §2 proposes the
additions needed to make it a well-instrumented packaged test part without
changing that ratified interface.

## 4. Target specification at the challenge rails

**Rail-gap disclosure, stated once here rather than repeated on every row:**
this block's ratified, characterized operating range is **2.97–3.63 V**
(3.3 V ±10 %, [DR-001](../../spec/decision-records/DR-001-supply-flavor.md)),
using gf180mcu's 3.3 V-core device flavor exclusively. That range covers the
challenge's 3.3 V digital rail. **No row in this table has been simulated at
5.0 V, and DR-001 explicitly rejected running 3.3 V-core devices on a 5 V
rail** (Vgs/Vds overstress) — a genuine 5.0 V analog-rail requirement would
need a device-flavor redesign (`05v0`/`06v0` thick-oxide throughout the
analog signal path), which is out of wave-1 scope and not achievable by the
Oct 5 schematic review on the evidence in this repository today. Every row
below is therefore marked **not yet characterized at 5.0 V** rather than
extrapolated; closing it before Oct 5 needs an explicit decision (with the
challenge organizers, not something this repository can resolve
unilaterally) on whether this block may run purely off the 3.3 V digital
rail for its analog core, or whether 5.0 V operation is mandatory.

All numbers below are the schematic/post-layout `sim/` evidence at 2.97 V,
3.30 V and 3.63 V, over the full 81-point PVT grid (9 process corners × 3
temperatures × 3 supplies) unless noted otherwise.

**Every row's Evidence column is independently reproducible with a single
command.** Each cited `sim/<slug>/records/<record-id>.md` path names the
experiment slug (the path component right after `sim/`) that
`make characterize` (repository root) regenerates from scratch — the exact
record-id will differ on a fresh run (`sim/`'s append-only convention mints
a new one every time), but the slug and the claim it substantiates do not.
See the repository [`README.md`](../../README.md)'s "Independent
verification (Chipalooza)" section for prerequisites, the three `make`
targets (`check`/`smoke`/`characterize`), measured wall-clock, and the exact
slug-to-row mapping — written for a reviewer who has never seen this
repository before.

### 4.1 Temperature sensor

| Parameter | Min | Typ | Max | Absolute limit | Status @ 3.3 V rail | Status @ 5.0 V rail | Evidence |
|---|---|---|---|---|---|---|---|
| Temperature error, untrimmed | — | — | — | ±3 °C (3σ) | **Not met** — measured 3σ **−19.23…+19.63 °C** (6.5× over budget), N=500 mismatch MC at each binding point, 33.4–40.4 % empirical yield; deterministic-corner-only share is small (−0.335…+0.099 °C, 11 % of budget) — the miss is mismatch-dominated. Plan to close before Oct 5: [DR-029](../../spec/decision-records/DR-029-temp-accuracy-mismatch-not-met.md) records the target as not relaxed and routes the remedy (grow the input pair / chop-auto-zero / fix the mirror ratio / rebalance the trim ladder) to a design revision owned by #1/#17 — **not yet started**; this is the single largest open technical risk for the schematic review. | Not yet characterized | `sim/temp-accuracy-mc/records/20260802-082345-989ce7a.md`, breakdown `…-breakdown.md`; [DR-029](../../spec/decision-records/DR-029-temp-accuracy-mismatch-not-met.md) |
| Temperature error, 1-point trim (stretch) | — | — | — | ±1.5 °C (3σ) | **Not met** — measured 3σ **−7.08…+7.70 °C** (4.9× over budget), 37.2–65.8 % empirical yield; systematic/quantization-only share is smaller (−0.346…+0.847 °C, 56 % of budget). Same DR-029 disposition and open remedy as above. | Not yet characterized | Same as above |
| PTAT slope (nominal +4.3088 mV/K, ratiometric through origin) | — | 4.304–4.30756 mV/K (measured, K₂₅ across the grid) | — | — | **Met** — matches design intent to within 0.1 % | Not yet characterized | `sim/temp-accuracy-vt/records/20260801-121458-660d016.md` |
| CTAT slope (nominal −1.86 mV/°C) | −1.88424 mV/°C | — | −1.82384 mV/°C | — | **Met** — measured range brackets design intent | Not yet characterized | Same as above |
| PTAT/CTAT output headroom | 0.2 V above `VSS` | — | `VDD` − 0.2 V | — | **Met** — worst-case margin +260 mV at `bjt_ff_125c_2.97v` | Not yet characterized (headroom bound is defined relative to the operating rail; a 5.0 V rail would need its own re-check) | Same as above |
| Supply sensitivity of reported temperature | — | — | — | ≤0.5 °C/V (≤0.33 °C over the ±10 % window) | **Met** — measured full-window peak-to-peak ≤0.1216 °C at every (corner, temperature) group, 37 % of budget at the worst point | Not yet characterized | Same as above |
| Quiescent current, temperature sensor (incremental) | — | — | 15.90 µA | <20 µA target, <5 µA stretch | **Target met** (20 % margin at `ff_125c_3.63v`); **stretch not met** (floor 5.80 µA, needs low-power amplifier work not attempted in wave 1 — already anticipated by DR-005, not a new gap) | Not yet characterized | Same as above |

### 4.2 Power-on reset / brownout supervisor

| Parameter | Min | Typ | Max | Absolute limit | Status @ 3.3 V rail | Status @ 5.0 V rail | Evidence |
|---|---|---|---|---|---|---|---|
| VPOR↑ — release threshold, rising `VDD` | 2.47 V | 2.60 V | 2.73 V | — | **Met** — deterministic-corner 2.58384–2.63001 V (schematic) / 2.58574–2.63222 V (post-layout); mismatch-inclusive 3σ 2.5583–2.6470 V, 100 % empirical yield across five binding points | Not yet characterized — the divider's absolute-voltage threshold is set for a 2.6 V decision on a 3.3 V rail; a 5.0 V rail would need the divider re-ratioed, not done | `sim/por-vth/records/20260811-125410-c8a41a4.md` (schematic), `…20260811-131325-c23be4a.md` (post-layout), `sim/por-threshold-mc/records/20260802-083749-3b9b414.md` |
| VPOR↓ — assert threshold, falling `VDD` | 2.22 V | 2.45 V | 2.63 V | — | **Met**, scoped to continuous (quasi-static) falling ramps only — deterministic 2.40536–2.45092 V (schematic) / 2.40102–2.44714 V (post-layout); mismatch-inclusive 3σ 2.4002–2.4807 V, 100 % yield. **A separate, unresolved defect exists at intermediate falling *slew rates* on a dip-shaped waveform** ([DR-013](../../spec/decision-records/DR-013-por-brownout-spurious-assert.md)): `POR_RAW` can assert while `VDD` is still above `VPOR↑,max`, at up to 91 % of the grid on one branch, root cause unidentified. This row's own `ratifiable` status stands on the continuous-ramp evidence; the dip-shaped condition is a separate, still-open finding (see the brownout row below) | Not yet characterized | `sim/por-vth/records/20260811-125410-c8a41a4.md`, `…20260811-131325-c23be4a.md`, `sim/por-threshold-mc/records/20260802-083749-3b9b414.md` |
| Hysteresis, `V_hys` | 100 mV | 150 mV | 250 mV | — | **Met**, quasi-static scope ([DR-021](../../spec/decision-records/DR-021-por-hysteresis-quasi-static-scope.md)) — rate-corrected deck (#206) measures 164.633–206.847 mV (schematic), 169.340–215.655 mV (post-layout), 81/81 within bound at both netlist levels | Not yet characterized | `sim/por-vth/records/20260811-125410-c8a41a4.md`, `…20260811-131325-c23be4a.md` |
| Supply ramp-rate envelope | 1 V/s (slow) | — | 1 V/µs (fast) | Monotonic ramps only; behavior outside the envelope is unspecified, not guaranteed-wrong | **Met** — 81/81 PASS at all four tested rates (1 V/s, 10 V/s, 0.1 V/µs, 1 V/µs), zero chatter, `RESETn` releases once at every corner, both netlist levels | Not yet characterized | `sim/por-ramp-rate/records/20260811-081726-9b421f6.md` (post-layout), `…20260802-205904-bdc077d.md` (schematic) |
| Brownout dip depth (clause a) | rail must fall below VPOR↓,min = 2.22 V | — | — | — | Definitional (paired with dwell/slew below) | Not yet characterized | — |
| Brownout dip dwell, `T_dip,min` (clause b) | 30 µs | — | — | Re-cost from 10 µs, [DR-027](../../spec/decision-records/DR-027-por-brownout-tdip-recost.md) | **Met** at the re-cost bound — 81/81 PASS both netlist levels; measured cell-level dwell to trip is 6.14–23.11 µs, and 30 µs is +29.8 % over the slowest measured corner | Not yet characterized | `sim/por-output-chain-deglitch/records/20260811-210054-613ccb0.md` (schematic), `…20260811-210344-5ea1df3.md` (post-layout) |
| Brownout falling-slew limit, `dVDD/dt`\|fall,max (clause c) | — | — | 2.30 mV/µs | Re-cost from 3.40 mV/µs, [DR-019](../../spec/decision-records/DR-019-brownout-falling-slew-postlayout-recost.md) | **Met** at the re-cost bound — 81/81 PASS both netlist levels | Not yet characterized | `sim/por-brownout-slew/records/20260811-111437-88888f3.md` |
| Brownout, combined all-three-clauses deck (`sim/por-brownout/`) | — | — | — | — | **Not met** — this specific testbench's own dip edge (~1000× outside clause (c)) fails; the individual clauses above are separately validated by the decks that measure them in isolation. **A genuinely open defect survives regardless**: the DR-013 spurious-assert condition above is still unresolved. Plan to close before Oct 5: needs either the DR-013 root cause found and fixed, or an explicit, disclosed scope narrowing accepted at the schematic review | Not yet characterized | `sim/por-brownout/records/20260811-065930-35a87a6.md`; `sim/por-brownout-spurious/records/20260811-071019-9aaf2b8.md` |
| Reset pulse width, `t_pulse` | ≥1 ms | — | no maximum specified | 5 pF measurement load (provisional) | **Met** — 4.2172–16.9585 ms schematic minimum-corner-to-maximum-corner span (fresh-startup path); post-layout lengthens ~2 % uniformly, no ratified corner cost; brownout-regeneration path 4.74–16.28 ms | Not yet characterized | `sim/por-output-chain-pulse/records/20260802-205904-bdc077d.md`; `sim/por-brownout/records/20260801-233807-32fbaa0.md` |
| Reset-valid floor, `V_RSTVALID` | target 0 V (fallback ≤0.4 V) | — | achieved 1.74 mV | ≤0.4 V acceptance fallback | **Met** — measured floor 1.74 mV max (`ss_-40c_2.97v`), leakage ratio 0.551 % max (`sf_125c_2.97v`), both well inside bound, from a static 0 V ramp | Not yet characterized | `sim/por-output-chain-floor/records/20260802-205904-bdc077d.md` |

### 4.3 Quiescent current

| Parameter | Min | Typ | Max | Absolute limit | Status @ 3.3 V rail | Status @ 5.0 V rail | Evidence |
|---|---|---|---|---|---|---|---|
| POR quiescent current (`RESETn` asserted, sensor disabled) | 0.656367 µA | — | 2.384647 µA | <3.0 µA (re-cost, [DR-018](../../spec/decision-records/DR-018-por-iq-recost.md)) | **Met** — 81/81 PASS, both netlist levels, 20.5 % margin at binding corner | Not yet characterized | `sim/por-iq/records/20260811-084152-68c0017-por-iq-derived.md` (post-layout), `…20260801-121458-660d016-por-iq-derived.md` (schematic) |
| Total block quiescent current (`RESETn` released, sensor enabled) | 6.445774 µA | — | 18.288 µA | <21 µA | **Met** — 81/81 PASS, both netlist levels, 13 % margin at binding corner | Not yet characterized | Same as above |

### 4.4 Physical

| Parameter | Value | Absolute limit | Status | Evidence |
|---|---|---|---|---|
| Total assembled footprint (`temp_por_top`, post-layout, DRC-clean, LVS-matched) | **1.059 mm²** (1334 × 794 µm) | ≤0.05 mm² wave-1 planning budget | **Not met** (21.2× over) — recorded, not relaxed, per [DR-022](../../spec/decision-records/DR-022-area-post-layout-measurement.md). For this proposal, the fab-relevant number is the measured 1.059 mm² footprint (QFN-compatible), not the pre-layout aspirational planning bound; recommend the planning bound be dropped from any binding submission claim rather than treated as a gap to close by Oct 5 | `layout/reports/temp_por_top/stats.json` |

## 5. Test-plan outline (measurement on the packaged part)

Assumes the block is bonded out per §2 on a QFN package on a daughterboard,
itself on a test board that can source/sweep `VDD`, apply controlled dips,
and provide a temperature-controlled environment for the die.

1. **Bring-up.** Power `VDD` at nominal (3.3 V) via a bench supply. Confirm
   `BIAS_OK` (digital test output) asserts before `RESETn` releases —
   validates the shared core is alive independently of the POR decision.
2. **POR threshold sweep (`VPOR↑`/`VPOR↓`/hysteresis).** Ramp `VDD` at a
   controlled, constant `dVDD/dt` (matching the rate-corrected stimulus in
   `sim/por-vth/testbench/stimulus.spice`) across the 2.97–3.63 V window and,
   separately, across whatever the schematic review resolves for the 5.0 V
   question. Capture both `POR_RAW` (digital test output — the raw
   comparator decision, no deglitch/timer in the way) and `RESETn` (dedicated
   pad) so the threshold measurement and the output-chain timing measurement
   are separable, exactly as the two testbenches (`sim/por-vth/`,
   `sim/por-output-chain-pulse/`) are separable in simulation. Repeat at the
   temperature extremes (−40 °C, +125 °C) in a chamber.
3. **Reset pulse width.** Oscilloscope on `RESETn`; verify ≥1 ms minimum at
   nominal `VDD`/25 °C and at the PVT extremes reachable on the bench, and
   after a triggered brownout dip (below).
4. **Brownout / dip response.** Using a programmable supply or a
   pass-transistor dip injector, sweep dip depth, dwell, and falling slew
   rate (matching the ladders in `sim/por-brownout-slew/` and
   `sim/por-output-chain-deglitch/`). Because §4.2 discloses an unresolved
   intermediate-slew spurious-assert defect (DR-013), this sweep is expected
   to be diagnostic, not merely confirmatory — silicon data here either
   reproduces the simulated defect (motivating the same design fix DR-013
   already calls for) or narrows it.
5. **Temperature accuracy and trim.** In a temperature chamber, sweep
   −40…+125 °C at fixed `VDD`; measure `PTAT`/`CTAT` (dedicated pads) with a
   precision DAQ referenced against a calibrated RTD/thermocouple on the
   package. Run the 25 °C 1-point gain trim using `TRIM<5:0>` (digital
   control inputs) and re-measure, reproducing the derivation in
   `sim/temp-accuracy-vt/analyze_derived.py`. Because §4.1 discloses this
   row as the block's largest known miss (6.5×/4.9× over budget by
   simulation), this measurement is the most consequential one in the plan —
   it either confirms the simulated mismatch model or shows it was
   pessimistic, and either result is actionable evidence for the design
   revision DR-029 already calls for.
6. **Supply sensitivity.** At fixed temperature, sweep `VDD` across
   2.97–3.63 V and re-measure `PTAT`/`CTAT`, matching
   `sim/temp-accuracy-vt/`'s supply axis.
7. **Quiescent current.** Source-meter on `VDD`, measured separately in the
   `RESETn`-asserted/sensor-disabled state and the `RESETn`-released/sensor-
   enabled state, cross-checked against §4.3.
8. **Multi-die statistics.** Repeat steps 2 and 5 across every packaged die
   available to build an empirical threshold/accuracy distribution
   comparable to the recorded Monte Carlo predictions
   (`sim/temp-accuracy-mc/`, `sim/por-threshold-mc/`) — the first real
   silicon check of whether this repository's local-mismatch simulation
   model is calibrated correctly.
9. **Fault localization.** For any bench discrepancy against the `sim/`
   predictions, use `POR_RAW`, `BIAS_OK`, and `VREF`/`IBIAS` (shared analog
   lines) to localize it to the bias core, the comparator, or the output
   chain, rather than only observing the packaged `RESETn` pin.

## 6. Category note — differentiation from Challenge #2's split entries

Challenge #2 fielded a "PVT sensor" and a "voltage supervisor (POR+BOR)" as
two separate blocks. This proposal is one combined block by design, not by
grouping: the temperature sensor and the POR/brownout supervisor share a
single always-on bias/reference core (`bias_core`), which supplies the
sensing amplifier's bias current, the comparator's tail current, and the
absolute 1.20 V reference the threshold divider is ratioed against, plus a
"core settled" gate (`BIAS_OK`) that both the comparator's decision and the
temperature sensor's enable ordering depend on
([DR-005](../../spec/decision-records/DR-005-temp-por-architecture-survey.md);
`spec/target-spec.md` §5's quiescent-current accounting rules exist
specifically because this sharing makes the two functions' current budgets
non-separable by construction). That sharing is the source of this block's
area/Iq efficiency case — one reference and one bias generator instead of
two — and it is also, disclosed rather than hidden, entangled with one of
its two currently-unmet spec rows: the shared core's loading and settling
behavior is part of what the temperature-accuracy Monte Carlo measures
(`sim/temp-accuracy-mc/`), so a future fix to close that gap has to be sized
against the shared-core interaction, not against the sensing amplifier in
isolation. A split-block submission would decouple that interaction at the
cost of duplicating the reference/bias generator; this proposal keeps them
coupled and states the coupling's cost explicitly.

## Licensing

This repository is Apache License 2.0 (`LICENSE`), matching the challenge's
stated preference for a standard open license. All modifiable sources —
schematics (`design/*.sch`), exported netlists (`design/netlist/`),
testbenches and simulation harness (`sim/`), layout and DRC/LVS reports
(`layout/`), and the decision-record history behind every ratified value
(`spec/decision-records/`) — are public in this repository under that same
license. No separate licensing action is needed for this submission.

## Verification flow (open-source EDA)

- **Schematic entry / simulation**: [xschem](https://xschem.sourceforge.io/)
  (≥3.4.7) + [ngspice](https://ngspice.sourceforge.io/), against the open
  [gf180mcu](https://github.com/google/gf180mcu-pdk) PDK. `PDK_ROOT`/`PDK`
  (or `GF180_PDK_PATH`) are resolved by `sim/harness/pdk.py`, the same
  resolver both the schematic-export (`design/netlist.py`) and the
  corner-sweep harness (`sim/run_corners.py`) use — no PDK path is ever
  hard-coded, and the flow is compatible with an IIC-OSIC-TOOLS- or
  ciel-provisioned PDK install.
- **Layout / DRC / LVS**: [klayout-tools](https://github.com/2AMLogic/klayout-tools)
  (`klt`), a headless, scriptable KLayout-based flow — no GUI and no PDK
  install required for the DRC/LVS checks themselves
  (`layout/run_checks.sh`).
- **One-command full characterization**: `make characterize` at the
  repository root reproduces the entire §4 spec table from a clean clone
  (plus `make check`/`make smoke` for a fast environment/toolchain check and
  a quick end-to-end proof the flow runs) — see the repository
  [`README.md`](../../README.md)'s "Independent verification (Chipalooza)"
  section for prerequisites, wall-clock, and the spec-row-to-output-file
  mapping, per the review's own stated bar (2AMLogic/2am#542).
- No proprietary EDA tool is used anywhere in this design's flow.

---

*Full evidence trail: [`spec/target-spec.md`](../../spec/target-spec.md)
(the block's authoritative target-spec table),
[`spec/decision-records/`](../../spec/decision-records/) (every ratified
value's decision history), [`design/`](../../design/) (schematics and
per-cell design rationale), [`sim/`](../../sim/) (append-only PVT-corner and
Monte Carlo evidence), [`layout/`](../../layout/) (GDS, DRC/LVS reports).*
