# `por_comparator` — POR threshold comparator with hysteresis

Sizing rationale, error budget and Iq budget for `design/por_comparator.sch`
(issue #10). Topology per
[DR-005](../spec/decision-records/DR-005-temp-por-architecture-survey.md);
device choices per [`sim/devchar/SUMMARY.md`](../sim/devchar/SUMMARY.md)
(issue #4, PR #22); targets per
[`spec/target-spec.md`](../spec/target-spec.md), ratified via DR-008 on #1.
This document does not change any ratified value.

Every number below that is not a device dimension comes from a recorded
evidence run, not from an estimate:

| Evidence | What it substantiates |
| --- | --- |
| [`sim/por-comparator-designer-check/`](../sim/por-comparator-designer-check/) — record `20260801-015413-5dfccf2` | VPOR↑, VPOR↓, V_hys (both edges at the same corner point), single-transition/no-chatter on both edges, fractional threshold sensitivity to VREF, settled Iq in the released and the BIAS_OK-low states, and the observed below-operating-floor behaviour of `POR_RAW` — 81-point PVT grid (9 corners × 3 temperatures × 3 supplies) |

It is a **deterministic corner** record: `design.ngspice` sets
`sw_stat_mismatch=0`, so everything below bounds the **systematic + corner**
error only. The random/mismatch share was issue #15's Monte Carlo job — the
three threshold rows were tagged `[3σ] conditional #15` in `target-spec.md`
for exactly that reason — and the budget below is written so #15 knew how
much room was left. Full ramp-rate / brownout / reset-pulse-interaction
evidence against a real (non-idealised) startup sequence is #14's.

> **#15 has now run it, and all three rows close.**
> [`sim/por-threshold-mc/`](../sim/por-threshold-mc/) — record
> `20260802-083749-3b9b414`, N = 500 local-mismatch samples at each of the
> five binding points these rows name, `sw_stat_mismatch=1`, 2500/2500 samples
> ok. Measured: comparator input-referred offset **σ = 5.47–6.62 mV** at the
> sense node, VPOR↑ **σ = 12.2–14.3 mV**, VPOR↓ **σ = 11.4–13.4 mV**, V_hys
> **σ = 0.77–0.97 mV**. Every row is inside its ratified window at 3σ at every
> binding point, with 100 % empirical yield, and no chatter on either edge at
> any of the 2500 samples. The `conditional #15` tags are discharged; the
> three rows are `ratifiable` on mismatch-inclusive evidence.

## What this cell is and is not

- It is the **precision threshold decision**: is VDD above (hysteretic)
  VPOR↑? Its output `POR_RAW` is a raw decision, not `RESETn`.
- Hysteresis (chatter rejection for a *slowly varying* rail near threshold)
  lives here. **Deglitch** (rejecting a *fast transient* dip that a
  hysteretic comparator would still trip on) is a separate, additional
  mechanism owned by `por_output_chain` (#12). Per DR-005's ownership split
  the two are not substitutable, and this cell makes no attempt to satisfy
  deglitch with hysteresis.
- Below the comparator's own operating floor its output is **undefined by
  construction**. Holding `RESETn` low from 0 V is `por_output_chain`'s
  below-floor pull-down (DR-004). What this cell actually *does* down there
  is measured and recorded — see [Below the operating
  floor](#below-the-operating-floor) — rather than left unobserved.

## Interface

Unchanged from the ports-only placeholder committed in PR #29; this issue
replaced the internals only, so `design/por_comparator.sym` is untouched.

| Pin | Dir | Meaning |
| --- | --- | --- |
| `VDD`, `VSS` | inout | 3.3 V core-flavor supply pair (DR-001) |
| `IBIAS` | in | shared bias-mirror node from `bias_core` (#11). Same convention as `temp_core`: `bias_core` **sources** 0.5 µA into this pin. This cell's `XMDIB` clamp on the pin is **kept** under [DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md), unlike `temp_core`'s: it is gated on `BIAS_OKB`, and `BIAS_OK` is generated inside `bias_core` with no dependence on `IBIAS` compliance, so it is self-releasing and is not a member of the bias-vs-POR lockup loop DR-010 cut. It holds the node down only until the bias core is up, which is correct — nothing downstream should be deciding before then. |
| `VREF` | in | absolute reference from `bias_core`. Assumed bandgap-scale, **1.2 V**, in this cell's sizing — see [Error budget](#error-budget) for what happens if #11 lands on a different number. |
| `BIAS_OK` | in | shared-core-valid flag. Gates this cell's bias and clamps its output, so `POR_RAW` reads a safe not-released before the shared core is valid (DR-005 startup step 4). |
| `POR_RAW` | out | raw threshold decision, **active high**: 1 means VDD is above the hysteretic release threshold. |

## Topology

```
          VDD ─┬───────────────┬──────────┬─────────┬──────
               │            ┌──┴──┐    ┌──┴──┐   ┌──┴──┐
             ┌─┴─┐   BIAS_OKB┤MENSRC   ┤MI1P │   ┤MI2P │
             │RTOP│          └──┬──┘    └──┬──┘   └──┬──┘
             │12.1M│           VDDA        │         │
             └─┬─┘        ┌─────┴─────┐    ├── N1 ───┼── POR_RAW
               │      ┌───┴──┐    ┌───┴──┐ │         │
       SNS ────┼──────┤ MLA  ├────┤ MLB  │ │      ┌──┴──┐
               │      └───┬──┘    └───┬──┘ │      │MI2N │
             ┌─┴─┐        │ NA        │ CMPO      └──┬──┘
             │RBOT│    ┌──┴──┐     ┌──┴──┐  ├──┐    VSS
             │10.4M│ SNS┤MINA │VREF─┤MINB │  │  │
             └─┬─┘    └──┬──┘     └──┬──┘  │ ┌┴─────┐
          SNSB │         └─────┬─────┘     │ │MDCMPO│ BIAS_OKB
               ├──────┐        │ TN        │ └┬─────┘
             ┌─┴─┐  ┌─┴──┐  ┌──┴──┐        │  VSS
             │RHYS│  │MHSW│  │MTAIL│ NBG    └── (to MI1N, VSS)
             │1.19M│ │    │  │     │
             └─┬─┘  └─┬──┘  └──┬──┘
          VSS ─┴──────┴────────┴────────────────────────────
                   ▲
                   └── gate = N1 = POR_RAW-bar
```

Bias generation (`IBIAS` → `NBG`) uses the same `MPASS` / `MBD` / `MDNB` /
`MDIB` pattern as `design/temp_core.sch`, so the two consumers of the shared
mirror behave identically when `bias_core` is not yet valid; see
[Disabled state](#disabled-state-bias_ok-low).

### Why the hysteresis is a resistor ratio

The mechanism is the load-bearing choice in this cell, so it is worth stating
what it replaced. DR-005 calls for "hysteresis from resistor-network positive
feedback". The obvious reading — inject a fixed, bias-referenced current
`I_HYS` into the sense node while `POR_RAW` is high — gives

```
V_hys = I_HYS · RTOP
```

which is a **current times a resistance**. `I_HYS` comes from a MOS mirror
and `RTOP` is a `ppolyf_u_3k`, and neither one tracks the other, so the two
spreads multiply:

- `ppolyf_u_3k` sheet-rho corner spread is **±25 %** (3000 Ω/sq nominal,
  3750/2250 at `res_ss`/`res_ff` — `sim/devchar/SUMMARY.md`), and
- its TC is **−1545 ppm/°C**, i.e. −25 % of absolute R across the
  −40…+125 °C span, on top of the mirror's own temperature coefficient.

An earlier iteration of this cell was built exactly that way. Measured over
the same 81-point grid it produced **V_hys = 106.6…236.8 mV** — inside the
ratified 100…250 mV window, but with **6.6 mV** of margin to the floor and
**13.2 mV** to the ceiling, on a row whose statistical basis is `[3σ]` and
whose mismatch share has not been simulated yet. That is a design that passes
a corner sim and fails #15.

**Vindicated in hindsight**: #15's Monte Carlo measures the comparator's own
input-referred offset at **σ = 5.47–6.62 mV**. The discarded
current-injection variant's 6.6 mV of margin to the hysteresis floor was
therefore roughly *one sigma* of the comparator's offset — it would have
failed the `[3σ]` row outright. The ratio-feedback scheme this cell ships
instead measures **σ(V_hys) = 0.77–0.97 mV**, an order of magnitude tighter,
because both edges see the same offset and it cancels in the difference
(record `20260802-083749-3b9b414`).

Feeding `POR_RAW` back into the **divider ratio** instead removes the term
entirely. `MHSW` shorts the `RHYS` segment out whenever `POR_RAW` is low:

```
POR_RAW low  (reset asserted, RHYS shorted):
    VPOR↑ = VREF · (RTOP + RBOT) / RBOT

POR_RAW high (released, RHYS in circuit):
    VPOR↓ = VREF · (RTOP + RBOT + RHYS) / (RBOT + RHYS)

    V_hys = VREF · RTOP · RHYS / (RBOT · (RBOT + RHYS))
```

All three expressions are `VREF` times a **ratio of same-flavor, same-width
resistors**. The body-resistor model's temperature factor `r_temp(T)` is a
pure multiplicative function of flavor only, so it divides out of every ratio
— the same cancellation argument `sim/devchar/SUMMARY.md` makes for the
sensing core's gain pair — and so does the sheet-rho corner. Measured
V_hys spread collapses from **78.5 %** to **4.8 %**, and it is now
`POR_RAW`-referenced positive feedback in the literal DR-005 sense: the
comparator's own decision changes the divider ratio, which is what makes the
transition regenerative.

### Why `MHSW` sits at the VSS end of the string

`RHYS` is the **bottom** segment, so the switch across it has its source at
`VSS` and its gate at a full-rail `N1`. It therefore has ~2.6 V of gate drive
with no body effect, and its `Ron` (a few hundred ohms at
W/L = 10 µm/0.5 µm, well under 1 kΩ at every corner) appears in series with
the 10.4 MΩ `RBOT` — under 0.01 % of the ratio that sets VPOR↑.

The alternative placements are worse for a reason that only shows up at the
binding corner:

- **Shorting a segment of `RTOP`** puts the switch between two mid-rail taps
  (~1.35 V and ~1.20 V). Its gate drive is then only `VDD − V(tap)`, which at
  the SS / −40 °C / 2.97 V corner — where `nfet_03v3` Vt is highest and,
  with the body effect from a 1.2 V source, higher still — leaves barely
  0.2 V of overdrive. `Ron` would go soft precisely at the corner where the
  release threshold's maximum binds.
- **Paralleling an `RHYS` across `RTOP`** needs `RHYS ≈ 33 kΩ/sq-equivalent
  × 33 000 squares` for the same 150 mV, i.e. an ~80× larger resistor than
  the series segment. Same electrical answer, absurd area.

## Device sizing and why

### Sense divider — `ppolyf_u_3k`, W = 2 µm

`sim/devchar/SUMMARY.md` recommends `ppolyf_u_3k` for the POR divider:
highest sheet resistance of the eight flavors measured (~3 kΩ/sq), which is
what makes a 20-plus-MΩ divider affordable at all, with same-flavor legs for
the TC-in-ratio cancellation above. W = 2 µm matches `temp_core`'s resistor
convention and the geometry `sim/devchar` characterised.

| Device | Drawn L | Squares | R at tt/25 °C | Sets |
| --- | ---: | ---: | ---: | --- |
| `RTOP` | 7897.44 µm | 4040.0 | 12.120 MΩ | with `RBOT`, VPOR↑ = 2.600 V for VREF = 1.2 V |
| `RBOT` | 6769.23 µm | 3462.8 | 10.389 MΩ | ratio `RTOP/RBOT` = 1.16667 → `(RTOP+RBOT)/RBOT` = 2.16667 |
| `RHYS` | 775.00 µm | 396.5 | 1.190 MΩ | V_hys ≈ 150 mV |

Total 23.70 MΩ in the released state, i.e. **139 nA at 3.3 V** — see the
[Iq budget](#iq-budget). The divider is the dominant Iq item in this cell and
sizing it is a direct area/current trade, not a free parameter.

**Sizing the string.** Two ratios and one absolute value fix all three
resistors:

```
(RTOP+RBOT)/RBOT              = VPOR↑,typ / VREF  = 2.600 / 1.2 = 2.16667
(RTOP+RBOT+RHYS)/(RBOT+RHYS)  = VPOR↓,typ / VREF  = 2.450 / 1.2 = 2.04167
RTOP + RBOT + RHYS            = VDD / I_div       ≈ 23.7 MΩ
```

The ideal-switch algebra predicts VPOR↑ = 2.600 V, VPOR↓ = 2.456 V and
V_hys = 143.9 mV; the built cell measures 2.597 / 2.446 / 151.0 V at
tt/27 °C/3.30 V. The −3 mV on VPOR↑ is the OTA's systematic input offset
referred through the divider; the extra −7 mV on VPOR↓ (and hence +7 mV on
V_hys) is the loop term the two-state algebra cannot see — finite comparator
gain, the inverter chain's own trip level, and `MHSW` turning off gradually
rather than instantaneously as `N1` sweeps. `RHYS` was therefore set from
simulation (775.0 µm) rather than from the algebra's 812.3 µm, which is why
V_hys lands on its 150 mV typ instead of 5 % above it. The result is
timestep-converged: re-running tt/27 °C at 1 µs and 0.2 µs maximum transient
step reproduces all three numbers to six significant figures, so they are
circuit behaviour and not integration artefacts.

### Comparator core — NMOS input pair, 25 nA tail

`sim/devchar/SUMMARY.md` recommends an `nfet_03v3` input pair for this
comparator: on the pinned 3.3 V rail its lower |Vt| (0.644 V vs 0.843 V for
`pfet_03v3`) leaves more headroom for an input common mode at bandgap scale,
which is where `SNS` and `VREF` both sit (`SNS` measures **1.451…1.774 V**
across the whole grid in the released state — comfortably above the pair's
`Vgs + Vds,sat` and below the mirror's compliance).

| Device | W/L | Role |
| --- | --- | --- |
| `MBD` | 2 µm / 2 µm | diode-connected NMOS off `IBIAS`, generates the local mirror gate `NBG` |
| `MTAIL` | 1 µm / 10 µm | tail mirror, **1:20** against `MBD` → 25 nA from the 0.5 µA `IBIAS` |
| `MINA`, `MINB` | 2 µm / 1 µm | input pair; `MINA` gate = `SNS`, `MINB` gate = `VREF` |
| `MLA`, `MLB` | 4 µm / 1 µm | PMOS mirror load, diode reference on the `SNS` branch |
| `MENSRC` | 4 µm / 0.5 µm | gates the load mirror's own supply node `VDDA` from `VDD` |

The 25 nA tail is the Iq/speed trade. It is enough for the 1 V/µs fast limit
of `por-ramp-rate` because the divider ratio feedback makes the transition
regenerative rather than gain-limited — but that is #14's claim to make on a
real ramp sweep, not this record's, and this record's own evidence for
"the transition is clean" is the chatter guard below, not a speed number.

The load mirror is diode-referenced on the `SNS` branch so that `CMPO`
follows `SNS` **positively**: `SNS` rising steers current from `MINB` to
`MINA`, `NA` falls, `MLB` sources more into a branch drawing less, `CMPO`
rises. Two inverting output stages then preserve that polarity, so
`POR_RAW` high = above threshold, with `N1` = `POR_RAW`-bar available as the
`MHSW` gate drive at no extra cost. Measured `VDD − V(POR_RAW)` in the
released state is **0 mV** at every one of the 81 points: `POR_RAW` is a hard
rail-to-rail logic level for #12, not a partially resolved analog one.

### `MHSW` — 10 µm / 0.5 µm

Sized for `Ron` ≪ `RHYS` (≈1 kΩ against 1.19 MΩ) with the full-rail gate
drive described above. Its off-state leakage shunts `RHYS` in the released
state; the measured V_hys at the hot binding corner (146.6 mV at
ff/125 °C/2.97 V, against 151.0 mV at tt/27 °C) already contains that term.

### Enable path

`BIAS_OK` low is the pre-`bias_core`-valid state, and the cell has to be
quiet **and** safe in it:

| Device | W/L | Role when `BIAS_OK` is low |
| --- | --- | --- |
| `MENP` / `MENN` | 2/0.5, 1/0.5 µm | local inverter producing `BIAS_OKB` |
| `MDNB` | 2 µm / 0.5 µm | clamps `NBG` to `VSS` → tail off |
| `MDIB` | 1 µm / 1 µm | clamps the `IBIAS` **pin** to `VSS` |
| `MENSRC` | 4 µm / 0.5 µm | disconnects the load mirror's supply node `VDDA` |
| `MDCMPO` | 2 µm / 1 µm | clamps `CMPO` to `VSS` → `POR_RAW` low, no floating node |

`MDIB` mirrors `temp_core`'s own `XMDIB`: without it, a testbench (or a real
system moment where every `IBIAS` consumer disables at once) forcing current
into a pin with no live sink has nowhere defined to go.

`MENSRC` is the non-obvious one, and it is not redundant with cutting the
tail. With `CMPO` clamped low by `MDCMPO` and `VREF` still a live,
always-present ~1.2 V input, `MINB`'s *effective source* becomes whichever of
`{TN, CMPO}` is lower — `CMPO`, once clamped — so its Vgs is measured against
that clamp rather than against a correctly-off tail, and it conducts hard.
Gating `VDDA` is what actually silences the branch. Measured disabled-state
draw with `MENSRC` present is **0.594…0.747 µA including the 0.5 µA
reference**, i.e. **94…247 nA** of the cell's own current, essentially all of
it the sense divider (which is unconditionally across the rail by design).

## Results against the ratified targets

Record `20260801-015413-5dfccf2`, 81 points, all PASS. Rows quoted from
[`spec/target-spec.md` §4.1](../spec/target-spec.md#41-threshold-pair-amendment-a2).

| Spec row | Window | Measured min | Measured max | Worst-case margin |
| --- | --- | --- | --- | --- |
| [`por-vth-rise`](../spec/target-spec.md#por-vth-rise) VPOR↑ | 2.47 / 2.60 / 2.73 V | 2.59311 V (`ff_125c_2.97v`) | 2.60057 V (`ss_-40c_3.63v`) | +123 mV / +129 mV |
| [`por-vth-fall`](../spec/target-spec.md#por-vth-fall) VPOR↓ | 2.22 / 2.45 / 2.63 V | 2.44380 V (`res_ss_125c_3.63v`) | 2.44803 V (`res_ff_-40c_2.97v`) | +224 mV / +182 mV |
| [`por-hysteresis`](../spec/target-spec.md#por-hysteresis) V_hys | 100 / 150 / 250 mV | 146.564 mV (`ff_125c_2.97v`) | 153.750 mV (`ss_-40c_3.63v`) | +46.6 mV / +96.3 mV |
| [`por-iq`](../spec/target-spec.md#por-iq) | < 1 µA | 0.646 µA (`ss_-40c_2.97v`) | 0.792 µA (`ff_125c_3.63v`) | 208 nA |

> **Deck fixed, #206.** Like `sim/por-vth/`, this deck's own ramp held
> duration fixed (10 ms), so `dVDD/dt` was a function of `vdd_val`
> (297/330/363 V/s) — the same confound, with a much smaller coefficient here
> because `VREF`/`IBIAS` are idealised fixed sources with no output impedance
> for a moving rail to displace. Fixed for consistency at a constant
> `dvdd_dt_v_per_s` (297 V/s, this deck's own 2.97 V corner). Re-run:
> [`20260811-132202-9f48a3d`](../sim/por-comparator-designer-check/records/20260811-132202-9f48a3d.md)
> (schematic, `v_hys_mv` 146.564–151.885 mV, 81/81 PASS) and
> [`20260811-132502-1a28d73`](../sim/por-comparator-designer-check/records/20260811-132502-1a28d73.md)
> (post-layout, 150.728–155.467 mV, 81/81 PASS) — materially unchanged from
> the record below, as expected given the small coefficient. That record
> stays the one this section's binding-corner and same-die tables below
> quote from; it is not superseded, only complemented.

**The measured binding corners are the ones the ratified table names.**
VPOR↑,max lands at SS / −40 °C and VPOR↑,min at FF / +125 °C exactly as
`por-vth-rise` predicts, and `por-iq` binds at FF / +125 °C / 3.63 V as its
row states. That agreement is not decoration: it means the table's binding
corners can be trusted for the rows this cell owns, and #14/#15 can sweep
against them rather than re-deriving them.

**Both edges of every hysteresis pair come from the same corner point.**
The rising and falling ramps are two DUT instances in one deck, at one corner,
one `.temp`, one rail. `V_hys` is therefore a same-die difference, which is
what `por-hysteresis` requires — never a subtraction of a max at one corner
from a min at another. Concretely, at the two binding corners:

| Corner | VPOR↑ | VPOR↓ | V_hys |
| --- | ---: | ---: | ---: |
| `ss_-40c_3.63v` (V_hys max, VPOR↑ max) | 2.60057 V | 2.44682 V | 153.750 mV |
| `ff_125c_2.97v` (V_hys min, VPOR↑ min) | 2.59311 V | 2.44655 V | 146.564 mV |

**No chatter on either edge.** `rise_chatter_mv` and `fall_chatter_mv`
compare the *last* crossing of `POR_RAW = VDD/2` on a ramp with the *first*.
Both read exactly **0** at all 81 points, on both edges. Without this guard a
`when … rise=1` measurement happily reports the first of several crossings
and a mis-signed or under-sized feedback loop reads as a pass.

**Self-consistency against `por-digital-min-vdd`.** Measured VPOR↓,min is
**2.444 V**, 224 mV above the 2.22 V floor that `target-spec.md`'s
self-consistency requirement (V_DIG,min ≤ 2.22 V) is built on. Nothing in
this cell's sizing pushes VPOR↓ toward that floor, and the `[TBD]`
integrator-supplied V_DIG,min row is not in conflict with anything measured
here. If #15's mismatch data or a revised VREF moves VPOR↓ down by more than
224 mV, that is a re-ratification through #1, not something to absorb here.
**#15's data does not**: the mismatch-inclusive VPOR↓ 3σ minimum is
**2.4002 V** (`sim/por-threshold-mc/`), still 180 mV above the 2.22 V floor.
A revised `VREF` remains the only way this margin gets spent.

## Error budget

The threshold is `VREF` times a resistor ratio, so the error decomposes
cleanly into a part this cell owns and a part `bias_core` (#11) owns.

**Measured sensitivity to VREF: 0.995…0.999 (unity, as the topology
requires).** A third rising ramp in the testbench runs with `VREF` 5 % high
and reports `(ΔVPOR/VPOR)/(ΔVREF/VREF)` directly, so this is evidence rather
than algebra. Every part-per-thousand of reference error is a
part-per-thousand of threshold error, with no attenuation to hide behind.

| Term | Owner | Size |
| --- | --- | --- |
| Divider ratio + comparator offset, over the full 81-point deterministic grid | this cell | **±0.144 %** (2.59311…2.60057 V about a 2.59684 V mean) |
| Reference accuracy `VREF` | `bias_core`, #11 | whatever is left of the ratified ±5 % window: **±4.85 %** |
| Local mismatch (divider segment matching, input-pair offset) | this cell, **measured by #15** (`sw_stat_mismatch=0` in *this* record) | **±1.58 %** — VPOR↑ σ = 12.2–14.3 mV, i.e. 3σ ≈ ±41 mV about a ~2.598 V mean; comparator input-referred offset σ = 5.47–6.62 mV at the sense node, referred to VDD through the ~2.17× divider ratio. `sim/por-threshold-mc/` record `20260802-083749-3b9b414` |

In other words: **this cell spends 3 % of the ratified threshold window and
hands 97 % of it to #11's reference**, before mismatch. That is the intended
outcome of choosing an absolute-reference topology over a rail-fraction one
(DR-005) — the accuracy problem is deliberately concentrated in one place —
but it is also the number #11 has to design against, and it is stated here so
it cannot be discovered late.

**After mismatch, that split is 34/66, not 3/97.** #15's ±1.58 % is ~32 % of
the ratified ±5 % window on its own; with the ±0.144 % systematic on top this
cell owns **≈34 %** and hands **≈66 %** — about ±3.3 % — to `VREF`. The row
still closes with margin (3σ spans 2.5583–2.6470 V inside [2.47, 2.73] V), and
the concentration argument still holds directionally, but **#11 has ±3.3 %,
not ±4.85 %, to work with.** Anyone sizing `bias_core`'s reference against the
pre-mismatch number would be over by half a per cent of rail.

**If #11 lands on a VREF other than 1.2 V**, the fix is a divider re-ratio,
not a re-architecture: `RTOP/RBOT` scales as `VPOR↑/VREF − 1` and `RHYS`
follows from the V_hys equation. The absolute value of the string (and hence
the area and the divider current) is unchanged. This document should get a
one-line reconciliation at that point.

`V_hys` is second-order in all of this: it is a *ratio of ratios* times
`VREF`, so it moves with VREF fractionally (±5 % of 150 mV = ±7.5 mV) and
with the resistor corners not at all. Measured corner spread is ±2.4 %.

## Iq budget

[`por-iq`](../spec/target-spec.md#por-iq) is **< 1 µA**, quoted in the
always-on state, and per DR-007's accounting rule 1 it includes whatever
share of the shared bias/reference core has to be live for this comparator's
decision to be valid. The `<0.3 µA` stretch is **withdrawn** by DR-007 and is
not a design target here.

The testbench splits the two so the accounting is explicit rather than
argued: `iq_run_ua` sources the idealised 0.5 µA `IBIAS` from the *measured*
rail (rule 1's conservative number), and `iq_own_ua` sources it from a
separate rail (this cell's own consumption).

At the binding corner **FF / +125 °C / 3.63 V**:

| Item | Current | Note |
| --- | ---: | --- |
| Sense divider | ~235 nA | unconditionally across the rail; `res_ff` sheet plus the −1545 ppm/°C TC make this the hot/fast corner's worst case |
| Comparator tail + mirror + output inverters | ~57 nA | 25 nA tail, the rest leakage and switching-free static current |
| **`por_comparator` own draw** | **292 nA** | measured `iq_own_ua` |
| Idealised `IBIAS` reference (bias_core's branch) | 500 nA | charged to `por-iq` by rule 1 |
| **Total against `por-iq`** | **792 nA** | measured `iq_run_ua`, **208 nA under the 1 µA budget** |

Across the whole grid: own draw **146…292 nA**, rule-1 total
**646…792 nA**.

**Both reachable divider configurations are bounded at full rail.** The
released state has `RHYS` in circuit (higher resistance, less current); the
`BIAS_OK`-low state clamps `CMPO` low, so `N1` is high, so `MHSW` shorts
`RHYS` out — the divider's *low*-resistance configuration — and that branch
is measured too (`iq_dis_ua`, 594…747 nA including the reference). The
physically unreachable third combination, `POR_RAW` low at 3.63 V with
`BIAS_OK` high, cannot occur: at 3.63 V the comparator is released.

**Headroom left for #11.** 208 nA at the binding corner. `target-spec.md`
§5 already flags, as a known accounting risk owned by #11, that DR-005
charges the shared core's 1–5 µA/branch to the *temperature-sensor* estimate
while its startup ordering has that core live before POR releases — under
rule 1 that current lands in `por-iq`. This cell's contribution is now a
measured 292 nA; if #11's reset-asserted-state core current does not fit in
the remaining ~708 nA, that is the re-cost `target-spec.md` §5 already
assigns to #11 and #1, and this document deliberately does not pre-absorb it
by relaxing anything here.

## Below the operating floor

DR-004/DR-005 leave this regime **explicitly undefined** for this cell, and
`por_output_chain` (#12) owns holding `RESETn` low from 0 V. That is a reason
to *measure* what happens, not a reason to skip it. Sampled on the rising
ramp with `BIAS_OK` tied high throughout:

| VDD | `POR_RAW`, worst point of the grid | Reading |
| ---: | ---: | --- |
| 2.0 V | 0.067 µV (`ff_125c_3.63v`) | above the floor, below VPOR↑: solid not-released everywhere |
| 1.0 V | 0.144 µV (`sf_125c_3.63v`) | below the floor: still solidly low |
| 0.5 V | **319 mV** (`sf_-40c_2.97v`) | below the floor: **not** a defined logic level |

The 0.5 V row is the honest one. At the slow-NMOS/fast-PMOS cold corner the
output inverter's PMOS is comparatively strong and its NMOS comparatively
weak while neither is properly on, and `POR_RAW` floats up to ~64 % of a
0.5 V rail. In absolute terms 319 mV is still below `nfet_03v3` Vt at every
corner in `sim/devchar/SUMMARY.md`, so it cannot turn a downstream gate on —
but it is emphatically not a driven low, and **nothing downstream may treat
`POR_RAW` as valid below ~1 V**. This is exactly the case DR-004 assigns to
#12's below-floor pull-down; it is recorded here so #12 sizes that pull-down
against a measured number instead of an assumption.

At the very bottom of a *falling* ramp (VDD ≈ 1 % of nominal) `POR_RAW`
measures **−85…+24 mV**: both output devices are far below Vt, so the node is
high-impedance and dominated by capacitive coupling to the collapsing rail,
which is why it reads slightly negative at the cold corners. Same conclusion,
same owner.

On re-assertion the cell is clean where it is specified to be: at VDD = 2.0 V
on the falling ramp — below VPOR↓ but above the floor — `POR_RAW` is
**< 0.6 µV** at every corner.

### That clean result holds only on a *slow* falling ramp (#55)

Every number above is sampled on a quasi-static ramp, where `VREF` and the
divider tap are both valid at each point. On a fast brownout they are not,
and this cell stops deciding altogether —
`sim/por-brownout/records/20260801-233807-32fbaa0.md` is 0/81 because
`POR_RAW` never asserts during the dip.

The cause is **not** in this cell. `sim/por-brownout/control/results.md`
measures `bias_core` driving its PMOS mirror bank fully off on a fast falling
edge (`V_sg` 776.2 mV → −74.4 mV), which starves this comparator's tail while
`BIAS_OK` — also biased from that loop — keeps reading valid. Restoring the
mirror gate in a control-only counterfactual restores `POR_RAW` assertion
inside the dip, with nothing in this cell changed. The boundary is a falling
slew between **7.67 and 11.50 mV/µs** at `tt`/27 °C/3.30 V.

The consequence for this cell's own documentation: the sampled table above is
valid for falling rails **below that boundary**, and says nothing about
faster ones. See
[DR-011](../spec/decision-records/DR-011-brownout-falling-slew-limit.md) and
`design/bias_core.md` § "The same window on a *falling* rail".

## Area — flagged for #17

Not a target this issue owns ([`area`](../spec/target-spec.md#area) is
`[TBD-#17]` with a ≤0.05 mm² wave-1 planning budget), but the number is large
enough that #17 should not discover it during floorplanning:

- Drawn poly in the divider: 15 441.67 µm × 2 µm = **30 883 µm²**, which with
  realistic serpentine folding overhead is of order **0.045 mm²** — essentially
  the whole block's planning budget, for one sub-cell's divider.
- The driver is the Iq budget, not the topology: a <1 µA POR needs a
  20-plus-MΩ divider, and 20 MΩ of 3 kΩ/sq poly is 7 000 squares however it
  is drawn. Lowering R to save area spends Iq directly.
- **The lever is width, and it is quadratic.** At fixed R, length scales with
  width, so area scales as W². Redrawing the string at W = 1 µm instead of
  2 µm gives the same resistances, the same ratios (all three segments share
  the width, so the `r_dw` width bias still cancels), and ~1/4 the area. What
  it costs is matching — narrower resistors have a larger relative width
  bias, which is a mismatch term, i.e. #15's axis — and it is a DRC/layout
  call this issue is not the right place to make.

W = 2 µm is kept here because it matches `temp_core`'s resistor convention
and the geometry `sim/devchar` characterised, so the electrical evidence in
this record rests on characterised ground. The width decision belongs with
#17's floorplan and #15's mismatch data, and re-ratioing the string is not
required to change it.

## Layout — partially drawn (#69)

> **Update (#91, #82/#180, #85):** the sense divider this section describes
> as "deliberately not drawn" was drawn for real in #91 and is now extracted,
> LVS-verified and simulated post-layout as of #82/#180/#85 — see
> [`layout/README.md` § `por_comparator`](../layout/README.md#por_comparator--the-por-threshold-comparator-69-sense-divider-91)
> for the current layout state and this document's new
> [Post-layout re-run](#post-layout-re-run-issue-85) section below for the
> resulting evidence. The account below is preserved for the
> deferred-drawing rationale it documents; its "not drawn" layout-status
> claims are superseded.

The MOS portion of this cell is drawn and verified:
[`layout/cells/por_comparator.gds`](../layout/cells/por_comparator.gds), with
the recorded DRC/extract/LVS reports under
[`layout/reports/por_comparator/`](../layout/reports/por_comparator/). All
**18** MOS devices in the tables above are present, DRC-clean against `klt`'s
curated `gf180mcu` deck, and LVS-clean (18/18 devices, 18/18 nets, 8/8 pins)
against a reference derived mechanically from
`design/netlist/por_comparator.spice` — so every `W`/`L` in this document that
belongs to a MOS device is now compared against drawn polygons rather than only
simulated. The `BIAS_OKB` inverter is the already-verified
`por_comparator_bias_okb_inv` cell, instanced rather than re-drawn.

**Nothing above about the sense divider is checked by that run.** `RTOP`,
`RBOT` and `RHYS` are `ppolyf_u_3k` poly resistors, outside the deck's device
coverage (klayout-tools#219/#222), and are deliberately **not drawn** — drawing
their bodies would extract as interconnect and short `SNS`/`SNSB` onto the
rails, which is worse than leaving them out. So the `RTOP/RBOT` = 1.16667
ratio, the 23.70 MΩ string and V_hys itself remain schematic-and-simulation
claims only. Their area is reserved in the layout as a floorplan rectangle
instead, and that rectangle is where the estimate below turns into a number:

- **222.0 × 219.5 µm = 0.0487 mm²**, folded from this document's own
  15 441.67 µm of drawn 2 µm-wide poly at a 3 µm serpentine pitch (72 active
  legs plus one end-of-string dummy at each end), computed by
  `layout/build_cells.py` from the golden netlist rather than retyped. That
  confirms the "of order 0.045 mm²" estimate in [Area](#area--flagged-for-17)
  to within ~8 %, and confirms it as the block's single largest area item.
- `W = 2 µm` is kept, per `layout/floorplan.md`'s rank-4 conclusion. The
  quadratic-in-width lever described above is therefore still unspent.

The matching plan actually drawn is `layout/floorplan.md`'s rank 4 as
floorplanned — standard practice, not common-centroid, for both `MINA`/`MINB`
and the divider, on #15's measured 100 % yield. The guard ring and well ties
drawn there are a design-review claim, not a checked one
(klayout-tools#281); [`layout/README.md`](../layout/README.md) § "The cells
under test" states the full boundary.

## Post-layout re-run (issue #85)

The three testbenches this document cites were re-run against the
**composite/extracted** netlists
[`layout/postlayout/por_comparator.spice`](../layout/postlayout/por_comparator.spice)
and [`layout/postlayout/temp_por_top.spice`](../layout/postlayout/temp_por_top.spice)
(#82/PR #180's direct-extraction flow: `klt extract --parasitics` plus
`klt lvs`'s net-correspondence map, `klt 0.2.0`) instead of the schematic
exports, via the `testbench-postlayout/` convention #86 established:

| Evidence | Netlist provenance | DUT |
| --- | --- | --- |
| [`sim/por-comparator-designer-check/records/20260811-073514-eb36e2c.md`](../sim/por-comparator-designer-check/records/20260811-073514-eb36e2c.md) | extracted | `por_comparator` alone, idealised `VREF`/`IBIAS` |
| [`sim/por-threshold-mc/records/20260811-083530-4f0693a.md`](../sim/por-threshold-mc/records/20260811-083530-4f0693a.md) | extracted | `por_comparator` alone, Monte Carlo local mismatch |
| [`sim/por-vth/records/20260811-073945-12473c3.md`](../sim/por-vth/records/20260811-073945-12473c3.md) | extracted | `temp_por_top`, real `bias_core`-driven `VREF`/`IBIAS` |

It does not replace the schematic-level section above — both stand as
independent evidence, per `sim/README.md`'s append-only convention.

The Monte Carlo row cites
[`20260811-083530-4f0693a`](../sim/por-threshold-mc/records/20260811-083530-4f0693a.md),
which supersedes `20260811-074902-e3e220f` (the record originally linked
here). The two carry the same measured data — nothing was re-simulated; the
superseded record's `Netlist provenance` field said `schematic` because of a
renderer defect in `sim/harness/mc_report.py`, fixed under #194.

**The `VDD`–`SNS`–`SNSB`–`VSS` divider string is connected correctly in the
extracted netlist.** `SNS`/`SNSB` extract as anonymous nets (no drawn label
reaches them), so this is not something a name match alone proves; `klt
lvs`'s `net_correspondence` output (klayout-tools#311) reattaches the
correct name from its own LVS-verified device/net match, and PR #180's smoke
table reproduces the schematic's exact `sns_v`/`snsb_v` (1.61228 V /
0.165661 V, 0.00 % delta) as a result. The cell-level record above measures
`sns_released_v` directly across the full grid (1.45091–1.77351 V, tracking
the corner-dependent `VREF` gain exactly as the schematic predicts) — the
connectivity the threshold numbers below rely on.

**The resistor ratio as physically drawn holds up, not just "parasitics
don't move the threshold".** `RTOP`/`RBOT`/`RHYS` are **not** schematic-ideal
splices in this netlist: #91 drew the divider for real, and
`layout/postlayout/AUDIT.md` confirms all 3 `ppolyf_u_1k` resistors extract
as real two-terminal devices (`por_comparator`: 21/21 devices drawn, no ideal
device; `temp_por_top`: 238/239, the one exception — `temp_core`'s `XCC` MiM
cap — sitting outside this cell's own signal path). So a clean result below
is a claim about the divider **as physically drawn**, not merely that
MOS-side parasitic loading leaves an assumed-ideal ratio unmoved.

### Cell-level (idealised `VREF`/`IBIAS`, `por_comparator` alone)

**All PASS**, same 81-point PVT grid as the schematic-level record:

| Spec row | Window | Measured min | Measured max | Worst-case margin |
| --- | --- | --- | --- | --- |
| [`por-vth-rise`](../spec/target-spec.md#por-vth-rise) VPOR↑ | 2.47 / 2.60 / 2.73 V | 2.59461 V (`ff_125c_2.97v`) | 2.60219 V (`ss_-40c_3.63v`) | +125 mV / +128 mV |
| [`por-vth-fall`](../spec/target-spec.md#por-vth-fall) VPOR↓ | 2.22 / 2.45 / 2.63 V | 2.44087 V (`res_ss_125c_3.63v`) | 2.44649 V (`res_ff_-40c_2.97v`) | +221 mV / +184 mV |
| [`por-hysteresis`](../spec/target-spec.md#por-hysteresis) V_hys | 100 / 150 / 250 mV | 150.728 mV (`ff_125c_2.97v`) | 158.014 mV (`ss_125c_3.63v`) | +50.7 mV / +92.0 mV |
| [`por-iq`](../spec/target-spec.md#por-iq) | < 1 µA | 0.646 µA (`ss_-40c_2.97v`) | 0.792 µA (`ff_125c_3.63v`) | 208 nA |

Every measured value tracks the schematic-level cell record to within a few
mV — expected, since a DC/quasi-static operating point is close to
parasitic-invariant by construction (`layout/README.md`, "The DC quantities
agree with the schematic to five or six digits"). Iq is reproduced to
sub-nA precision (146–292 nA own draw, 646–792 nA rule-1 total — identical
to the schematic-level numbers in [Iq budget](#iq-budget) above).

**Local mismatch, Monte Carlo (N = 500 per binding point).** Same
drawn-and-extracted `por_comparator` netlist, `sw_stat_mismatch=1` at
each of the five ratified binding points. **2500/2500 samples, overall
PASS.** Comparator input-referred offset σ = 6.02–6.51 mV, VPOR↑ σ =
13.1–14.1 mV, VPOR↓ σ = 12.1–13.1 mV, V_hys σ = 1.00–1.18 mV — all within a
few tenths of the schematic-level MC record's own spread, and every
mean ± 3σ band stays inside its ratified window at 100 % empirical yield
(worst case: V_hys 3σ = 173.674 mV at `vth-rise-max`, 76.3 mV of margin to
the 250 mV ceiling).

### Full-assembly (`bias_core`-driven `VREF`/`IBIAS`, `temp_por_top`)

**80/81 PASS, 1 FAIL**, same 81-point PVT grid as the schematic-level
full-assembly record:

| Spec row | Window | Measured min | Measured max | Worst-case margin |
| --- | --- | --- | --- | --- |
| [`por-vth-rise`](../spec/target-spec.md#por-vth-rise) VPOR↑ | 2.47 / 2.60 / 2.73 V | 2.58574 V (`bjt_ff_125c_2.97v`) | 2.64873 V (`ss_-40c_3.63v`) | +116 mV / +81.3 mV |
| [`por-vth-fall`](../spec/target-spec.md#por-vth-fall) VPOR↓ | 2.22 / 2.45 / 2.63 V | 2.37928 V (`res_ss_-40c_3.63v`) | 2.44714 V (`bjt_ss_125c_2.97v`) | +159 mV / +183 mV |
| [`por-hysteresis`](../spec/target-spec.md#por-hysteresis) V_hys | 100 / 150 / 250 mV | 169.34 mV (`ff_125c_2.97v`) | **261.092 mV (`ss_-40c_3.63v`)** | +69.3 mV / **−11.1 mV (FAIL)** |

**Regression: `por-hysteresis` fails at the single worst-case corner,
`ss_-40c_3.63v`.** The schematic-level full-assembly record already left
only 1.26 mV of margin there (248.74 mV measured against the 250 mV
ceiling — see [Results against the ratified targets](#results-against-the-ratified-targets)
above). Post-layout, both edges move apart at that corner (VPOR↑ +4.20 mV,
VPOR↓ −8.16 mV against the schematic-level record), widening V_hys by
12.35 mV — just enough to cross the ceiling. The same corner family (`ss`,
coldest/highest-supply) shows the same-sign, similar-magnitude growth
elsewhere in the grid (e.g. `res_ss_-40c_3.63v`: 236.68 → 248.52 mV, +11.8 mV,
still passing with 1.48 mV left) — a systematic shift, not an isolated
outlier. It does **not** show up in the cell-level record above (V_hys
157.249 mV at the identical corner, comfortably inside [100, 250] mV) or in
the post-layout Monte Carlo record (worst case 173.674 mV): the mechanism
needs the full-assembly path's real, corner-dependent `bias_core` VREF/IBIAS
in the loop, not the divider extraction or local mismatch alone.

Per this document's own error-budget accounting (the divider ratio is the
part this cell owns; `VREF` accuracy is `bias_core`'s), and per #85's
acceptance criteria that a post-layout regression against the schematic-level
record is flagged and routed rather than silently absorbed: this finding was
tracked as [issue #187](https://github.com/2AMLogic/gf180-temp-por/issues/187),
not fixed there — #85 is verification-only.

> **#187 has now root-caused it, and both of the hypotheses above are
> refuted.** The reading is not one quantity: 55 % of it is hysteresis, 37 %
> is `bias_core`'s reference being displaced by the moving rail and 8 % is
> comparator/output-chain delay. The divider ratio, as physically drawn,
> implements **143.3 mV** — mid-window. See
> [Most of the full-assembly `V_hys` reading is not hysteresis](#most-of-the-full-assembly-v_hys-reading-is-not-hysteresis-issue-187)
> below and
> [DR-021](../spec/decision-records/DR-021-por-hysteresis-quasi-static-scope.md).

### Reproducing this section's evidence

```bash
python3 sim/build_tb.py --check                                      # postlayout fragments <-> layout/postlayout/*.spice
python3 sim/run_corners.py sim/por-comparator-designer-check/testbench-postlayout -j 8
python3 sim/run_mc.py sim/por-threshold-mc/testbench-postlayout       -j 8
python3 sim/run_corners.py sim/por-vth/testbench-postlayout           -j 8
```

## Most of the full-assembly `V_hys` reading is not hysteresis (issue #187)

The section above records a post-layout `por-hysteresis` excursion at one
corner and routes it. This section is the root cause, measured:
[`sim/por-vth/control/results.md`](../sim/por-vth/control/results.md),
generated by
[`run_ramp_rate_probe.py`](../sim/por-vth/control/run_ramp_rate_probe.py).
The ratified conclusion is
[DR-021](../spec/decision-records/DR-021-por-hysteresis-quasi-static-scope.md).
**Nothing in this cell changes as a result** — `RTOP`/`RBOT`/`RHYS` are
unchanged, and the reason is a measurement, not a preference.

### The deck's supply axis is also a ramp-rate axis

`sim/por-vth/`'s triangle wave traverses `vdd_val − 2.0 V` in a **fixed 4 ms**
on each quasi-static segment. So its `dVDD/dt` is not one number: it is
**242.5 / 325 / 407.5 V/s** at 2.97 / 3.30 / 3.63 V, a 1.68× spread that lands
squarely on the supply axis of the grid. `ss_-40c_3.63v` is not only the
coldest, slowest, highest-supply point — it is also the **fastest-ramped** one.

Holding the rate at 242.5 V/s instead and sweeping only the supply, at that
same corner on the extracted netlist:

| VDD | dVDD/dt | VPOR↑ | V_hys | parent record's V_hys |
| --- | ---: | ---: | ---: | ---: |
| 2.97 V | 242.5 V/s | 2.62809 V | 211.382 mV | 211.382 mV |
| 3.30 V | 242.5 V/s | 2.62809 V | 215.655 mV | 238.555 mV |
| 3.63 V | 242.5 V/s | 2.62809 V | 215.655 mV | **261.092 mV** |

The 49.7 mV of `V_hys` spread and the 20.6 mV of `VPOR↑` spread the parent
record attributes to its supply axis are 4.3 mV and 0.0 mV once the rate is
held. They were a rate dependence wearing a supply label.

### `V_hys` is proportional to `dVDD/dt`, and its static limit is mid-window

Same corner, extracted netlist, ramp duration swept over a decade and a half:

| ramp | dVDD/dt | V_hys | of which at the comparator's input |
| ---: | ---: | ---: | ---: |
| 4 ms | 407.5 V/s | **261.092 mV** | 236.742 mV |
| 8 ms | 203.7 V/s | 204.717 mV | 190.280 mV |
| 16 ms | 101.9 V/s | 175.069 mV | 165.355 mV |
| 32 ms | 50.9 V/s | 159.497 mV | 152.359 mV |
| 64 ms | 25.5 V/s | 151.450 mV | 145.744 mV |
| 128 ms | 12.7 V/s | 147.354 mV | 142.389 mV |

Extrapolated to a static rail: **143.3 mV**, against a ratified 100 / 150 /
250 mV window. The schematic netlist extrapolates to 143.3 mV as well, and the
cell-level post-layout record's own supply trend at this corner (154.778 /
156.019 / 157.249 mV — that deck's supply axis is a rate axis too, at 297 /
330 / 363 V/s) extrapolates to 143.7 mV. Three independent routes to the same
number, and it is the number
[Device sizing and why](#device-sizing-and-why)'s algebra predicts.

### What actually moves is `VREF`, not the divider

The control samples both comparator inputs at a fixed rail voltage clear of
either threshold, once per edge, and compares each against the value a static
rail would give it. At the parent deck's own 407.5 V/s, extracted netlist:

| Node | up-ramp | down-ramp | against |
| --- | ---: | ---: | --- |
| `VREF` | **+19.043 mV** | **−20.756 mV** | its own settled value on the flat hold of the same run |
| `SNS` | −1.905 mV | +2.178 mV | the static tap the drawn resistor lengths give |

`bias_core`'s reference is displaced by an order of magnitude more than the
sense divider's tap is, and in the direction that pushes the two edges apart on
both of them. The displacement is proportional to the rate through the origin
(≈49 µs of equivalent time constant), and it **reverses sign with the ramp
direction** — so it is the moving rail displacing a settled reference, not a
reference that has not settled yet. The deck's own `vref_settle_drift_mv`
integrity guard cannot see it: the reference *is* settled on the flat hold
where that guard samples, and the down-ramp edge happens several ms later.

Referred out through the divider's ~2.1× ratio, ±20 mV on `VREF` is ±43 mV on
`VDD` per edge — 97.7 mV of the 261.092 mV reading.

**And this term is the same on both netlists** (+19.065 / −20.684 mV
schematic, +19.043 / −20.756 mV extracted), which bounds what post-layout can
say about it. `klt`'s parasitic model emits one lumped capacitance per net
with the **ground net** as its second terminal — every one of the 103 `C_*`
cards in `layout/postlayout/temp_por_top.spice` does — so it has no
representation of net-to-net coupling at all. The 97.7 mV measured here is
therefore a *device-level* coupling term (the reference's own
drain/bulk-to-`VDD` capacitance, present identically in the schematic
netlist), and **any additional coupling onto `VREF` from drawn interconnect
adjacency is outside what this netlist can show, in either direction**. Filed
generically as
[klayout-tools#728](https://github.com/2AMLogic/klayout-tools/issues/728) per
CLAUDE.md's friction protocol; the eventual fix is the field-solver work that
repo already tracks.

### The decomposition, and where the +12.35 mV regression actually is

| Term at 407.5 V/s | Schematic | Extracted | Δ |
| --- | ---: | ---: | ---: |
| **Total measured `V_hys`** | 248.741 mV | 261.092 mV | **+12.351 mV** |
| Static `V_hys` (zero-rate limit) | 143.300 mV | 143.258 mV | −0.042 mV |
| Rate excess at the comparator's input | 97.423 mV | 97.708 mV | +0.285 mV |
| Rate excess, comparator + output chain | 8.018 mV | 20.126 mV | **+12.108 mV** |

**98 % of the post-layout regression is the last row**: the extraction's
interconnect capacitance on the comparator's *own internal* nodes —
`xcmp__VDDA`, `NA`, `CMPO`, `N1`, `TN`, `NBG`, 13.6–21.3 fF each — slowing it
down while the rail keeps moving under it. Both of issue #187's candidate
hypotheses are refuted by direct measurement:

- **Not the divider's drawn interconnect R/C.** `klt` extracts 25.9 fF on
  `SNS` and 17.5 fF on `SNSB` against a ~5.9 MΩ Thevenin source — ~0.15 µs,
  three orders of magnitude below the displacement measured here — and the
  `SNS` row above confirms it directly: the tap is within 1.9 mV of static at
  the fastest rate on the ladder.
- **Not a tight design margin in the divider ratio.** Its static hysteresis is
  143.3 mV drawn and 143.3 mV in schematic — unchanged by the extraction to
  within 0.05 mV, and nowhere near either bound. The schematic record's
  celebrated "1.26 mV of headroom" was 105 mV of ramp displacement sitting on
  top of a comfortable 143 mV, not a design running out of room.

### Why the divider is not re-ratioed

Because the reading is only 55 % hysteresis, buying back the 11.1 mV of
excursion costs 11.1 mV of *real* hysteresis: the string would have to drop to
~132 mV static, off its ratified 150 mV typ and toward the 100 mV floor that
exists to guarantee chatter rejection — spending margin that matters to buy
margin against a term that is not hysteresis. And it would not hold: the same
1.68× of ramp rate the parent deck's own supply axis already spans puts the
re-ratioed divider back over the ceiling. The full argument, the alternatives
(including speeding the comparator up, and stiffening `VREF`), and the
ratified scope this leaves the row with are in
[DR-021](../spec/decision-records/DR-021-por-hysteresis-quasi-static-scope.md).

### Reproducing this section's evidence

```bash
python3 sim/por-vth/control/run_ramp_rate_probe.py -j 15
```

15 points at one corner, longest ~35 min. `--render-only` regenerates
`results.md` and `results.json` from the committed `logs/` without
re-simulating, and is idempotent — re-rendering a clean checkout reproduces
both files byte-for-byte (per-run wall-clock times, the one field no log
carries, are preserved from the committed `results.json`), so checking the
generated tables costs a reviewer nothing but the read.

### The deck itself is now fixed at a constant `dVDD/dt` (issue #206)

Everything above diagnoses `sim/por-vth/`'s *historical* stimulus — the one
that traversed `vdd_val − 2.0 V` in a fixed 4 ms, so its ramp rate was itself
a function of the supply. That stimulus is unchanged by this section (DR-021
deliberately left it alone, "so the root-cause reasoning and the deck change
are reviewed separately"). Issue #206 is that separate review: the deck now
derives its ramp duration from a manifest, constant `dvdd_dt_v_per_s`
(`tramp = (vdd_val − 2.0) / dvdd_dt_v_per_s`), chosen at 242.5 V/s — the old
scheme's own 2.97 V corner, per
[`sim/por-vth/control/rate_selection_results.md`](../sim/por-vth/control/rate_selection_results.md)
— plus a quasi-staticity guard segment (a second cycle at half that rate,
whose own `V_hys` must track the primary segment's within a measured bound).

Both grids now **PASS 81/81**, at every one of the three rows this section
discusses:

| Spec row | Window | Schematic (`20260811-125410-c8a41a4`) | Post-layout (`20260811-131325-c23be4a`) |
| --- | --- | --- | --- |
| [`por-vth-rise`](../spec/target-spec.md#por-vth-rise) VPOR↑ | 2.47 / 2.60 / 2.73 V | 2.58384–2.63001 V | 2.58574–2.63222 V |
| [`por-vth-fall`](../spec/target-spec.md#por-vth-fall) VPOR↓ | 2.22 / 2.45 / 2.63 V | 2.40536–2.45092 V | 2.40102–2.44714 V |
| [`por-hysteresis`](../spec/target-spec.md#por-hysteresis) V_hys | 100 / 150 / 250 mV | 164.633–206.847 mV | 169.340–215.655 mV |

The `ss_-40c_3.63v` point this section built its whole decomposition around
now reads **215.655 mV** post-layout at the deck's own 242.5 V/s (was
261.092 mV at 407.5 V/s under the confounded deck) — **34.3 mV inside the
250 mV ceiling**, and consistent with the decomposition above: 143.3 mV of
static hysteresis plus the residual rate term this deck's own quasi-static
rate still carries. `VPOR↑` is bit-identical across the whole supply axis at
every PVT point on both grids, exactly as arm C above predicted once
`dVDD/dt` stopped varying with `vdd_val`.

**Nothing here relaxes DR-021.** The ratified 100/150/250 mV window is
unchanged, and the historical records
([`20260801-233802-32fbaa0`](../sim/por-vth/records/20260801-233802-32fbaa0.md),
[`20260811-073945-12473c3`](../sim/por-vth/records/20260811-073945-12473c3.md))
stand, append-only, as exactly what the old fixed-duration deck measured —
DR-021's decomposition of *that* reading is still correct and still the
record of why it read what it did. The two new records above are the
*current* evidence for these three rows, run against the corrected,
genuinely quasi-static stimulus.

## Reproducing the evidence

```bash
bash layout/run_checks.sh por_comparator     # DRC/LVS on the drawn MOS portion
python3 design/netlist.py --check            # schematic ↔ committed netlist
python3 sim/build_tb.py --check              # netlist ↔ testbench fragment
python3 sim/run_corners.py por-comparator-designer-check
```

The last command mints a **new** record id; `sim/` is append-only, so it will
not overwrite `20260801-015413-5dfccf2`.

## Out of scope here, on purpose

| Not here | Where |
| --- | --- |
| Deglitch, the ≥1 ms one-shot, push-pull drive, the below-floor `RESETn` pull-down | `por_output_chain`, #12 |
| The real `VREF` / `IBIAS` / `BIAS_OK` sources and their startup ordering | `bias_core`, #11 |
| Ramp-rate envelope, brownout re-assertion, reset-pulse interaction on a real bring-up sequence | POR testbench suite, #14 |
| ~~Monte Carlo mismatch on the three `[3σ]` threshold rows~~ — **done**, `sim/por-threshold-mc/` record `20260802-083749-3b9b414`; all three pass | ~~#15~~ |
| Matching strategy for the whole block, measured area | #17 |
| ~~Drawing the sense divider~~ — **done**, #91; extracted and simulated post-layout, #82/#180/#85 | see [Layout](#layout--partially-drawn-69), [Post-layout re-run](#post-layout-re-run-issue-85) |
| ~~Root-causing / fixing the post-layout `por-hysteresis` regression at `ss_-40c_3.63v`~~ — **done**, #187: the reading is 55 % hysteresis / 37 % `VREF` ramp displacement / 8 % comparator delay; no design change, [DR-021](../spec/decision-records/DR-021-por-hysteresis-quasi-static-scope.md) | see [Most of the full-assembly `V_hys` reading is not hysteresis](#most-of-the-full-assembly-v_hys-reading-is-not-hysteresis-issue-187) |
| ~~Re-cutting `sim/por-vth/` at a fixed `dVDD/dt` so its supply axis stops confounding rate, and giving it a quasi-staticity guard on the measurand~~ — **done**, #206: both grids now pass 81/81 | see [The deck itself is now fixed at a constant `dVDD/dt`](#the-deck-itself-is-now-fixed-at-a-constant-dvdddt-issue-206) |
| Stiffening `VREF` against a ramping rail — the largest of the three terms above, and `bias_core`'s design, not this cell's | #11, #208 |
