# `bias_core` — shared bias / reference core

Sizing rationale, startup analysis and Iq apportionment for
`design/bias_core.sch` (issue #11). Topology per
[DR-005](../spec/decision-records/DR-005-temp-por-architecture-survey.md);
device choices per [`sim/devchar/SUMMARY.md`](../sim/devchar/SUMMARY.md)
(issue #4, PR #22); targets per
[`spec/target-spec.md`](../spec/target-spec.md), ratified via DR-008 on #1.
**This document does not change any ratified value.** Where a ratified row is
not met, it says so and names the owner of the re-cost, which is what
`target-spec.md` §5 asks this issue to do.

Every number below that is not a device dimension comes from a recorded
evidence run, not from an estimate:

| Evidence | What it substantiates |
| --- | --- |
| [`sim/bias-core-designer-check/`](../sim/bias-core-designer-check/) | settled `VREF`, `IBIAS`, always-on Iq against [`por-iq`](../spec/target-spec.md#por-iq), absence of a degenerate DC solution, reference settling and dropout, the rail at which the assembled block would release, and the starved-loop window on a fast ramp and after a brownout — 81-point PVT grid (9 corners × 3 temperatures × 3 supplies) |
| [`sim/bias-core-ibias-sharing/`](../sim/bias-core-ibias-sharing/) | the shared `IBIAS` net in the reset-asserted state, with a disabled `temp_core` and `por_comparator` wired exactly as `design/netlist/temp_por_top.spice` wires them, against a control without `temp_core` — same 81-point grid |
| [`sim/por-output-chain-ibias-sharing/`](../sim/por-output-chain-ibias-sharing/) | the **magnitude** half of the same net that the row above answers the liveness half of: all four cells spliced, a zero-volt ammeter on every `IBIAS` pin, so the current *split* between the consumer diodes is measured leg-by-leg in both `RESETn` states rather than inferred from the node's voltage — same 81-point grid, both netlist levels. Added by #221 / DR-024 |
| [`sim/temp-por-top-release/`](../sim/temp-por-top-release/) | this cell inside the **full four-cell assembly**: whether the shared node survives the reset-asserted state, whether `RESETn` releases and enables the sensor, and the assembled block's `por-iq` — same 81-point grid. Added by #41 / DR-010 |
| [`sim/bias-core-startup/`](../sim/bias-core-startup/) | branch-tracking, **quasi-static transient** rail ramp (not a per-point solve): whether a continuously rising rail leaves this cell on the correct branch and asserts `BIAS_OK` exactly once, whether the answer is ramp-rate independent, and whether all of it repeats after a full rail collapse — 81-point grid (27 distinct corner/temperature combinations, each at three bit-identical supply replicates by construction). Opened as a defect report by #43; **re-founded on a transient and closed by #46** — see [Resolved](#resolved-the-bias_ok-quasi-static-failure-was-a-testbench-artefact-issues-43-46) |

All are **deterministic corner** records: `design.ngspice` sets
`sw_stat_mismatch=0`, so everything below bounds the **systematic + corner**
term only. Local mismatch on the 8:1 PNP ratio, the `R2/R1` ratio and the
amplifier's input pair is issue #15's Monte Carlo job. Full
ramp-rate/brownout envelope against a real assembled block is #14's.

**Two of the recorded checks fail on purpose, and a third — reported by issue
#43 — turned out not to be a circuit defect at all:**

1. [`por-iq`](../spec/target-spec.md#por-iq) **was < 1 µA and not met; it is
   now re-costed to < 3.0 µA and met** — see
   [Iq apportionment](#iq-apportionment) and
   [DR-018](../spec/decision-records/DR-018-por-iq-recost.md).
2. A **starved-loop window** exists at the ratified fast end of
   [`por-ramp-rate`](../spec/target-spec.md#por-ramp-rate) and after a
   brownout, during which `BIAS_OK` can read a false valid — see
   [The starved-loop window](#the-starved-loop-window).
3. ~~**`BIAS_OK` fails to assert, or asserts non-monotonically, at every one
   of the 27 corner/temperature combinations on a quasi-static (branch-
   tracking) rising rail.**~~ **Not a defect in this cell.** Root-caused by
   #46 to the reporting testbench's own `gmin = 1 nS` convergence aid, which
   injected **0.563 nA** of *differential* error into a settle comparator
   whose whole signal is **0.247 nA** (measured by the committed control
   experiment, `sim/bias-core-startup/control/`). Re-measured on a
   quasi-static **transient** ramp at
   ngspice's default `gmin`, the cell asserts `BIAS_OK` exactly once, before
   the ratified release threshold, at **all 81 points** — and does the same
   after a full rail collapse. See
   [Resolved](#resolved-the-bias_ok-quasi-static-failure-was-a-testbench-artefact-issues-43-46).
   **No schematic change was made, and none is warranted on this evidence.**

Plus one integration defect that no single-cell testbench could see, which
this issue surfaced and **#41 has since fixed**:

4. ~~The **shared `IBIAS` net is clamped to `VSS` in the reset-asserted
   state**, which is a closed bias-vs-POR lockup at the top level.~~
   **Resolved** by
   [DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md):
   a disabled consumer of the shared node must present high impedance to it,
   so `temp_core`'s `XMDIB` clamp is gone. The shared node now sits at
   0.568–0.861 V in the reset-asserted state (was 1.0–6.6 mV) and the
   assembled block releases `RESETn` at every one of the 81 points — see
   [The shared IBIAS net](#the-shared-ibias-net-–-resolved-by-dr-010). The
   two checks in `sim/bias-core-ibias-sharing/` that were written as the
   requirement and had been failing now pass on their own, exactly as that
   testbench's `tb.json` predicted they would.

## What this cell is and is not

- It is the **always-on** bias/reference core: no enable pin, no off state,
  live from the first millivolt of rail. Everything it draws is therefore
  charged to `por-iq` by `target-spec.md` §5 rule 1, with no apportionment
  argument available or needed.
- It owns **its own startup kick** (DR-005 step 3). The separate below-floor
  `RESETn` pull-down is `por_output_chain`'s (#12, DR-004).
- It owns **`BIAS_OK`** (DR-005 step 4) — the flag that stops
  `por_comparator`'s threshold decision from becoming authoritative before
  the reference is valid. It does **not** own the full startup-ordering AND
  with the pulse timer, which is #12's.

## Interface

Unchanged from the ports-only placeholder committed in PR #29; this issue
replaced the internals only, so `design/bias_core.sym` is untouched.

| Pin | Dir | Meaning |
| --- | --- | --- |
| `VDD`, `VSS` | inout | 3.3 V core-flavour supply pair (DR-001) |
| `IBIAS` | out | shared bias-mirror node. Convention set by #9/#10 and honoured here: `bias_core` **sources 0.5 µA** (nominal, tt/27 °C/3.30 V) **into** the pin. Current output; compliance `V(IBIAS) ≤ VDD − 0.2 V`. |
| `VREF` | out | absolute reference, **1.20 V nominal** — the value `design/por_comparator.md` sized its divider ratio against, so that sizing stands with no re-ratio. |
| `BIAS_OK` | out | "shared core is up and settled", **active high**, rail-to-rail. |

## Topology

```
              VDD ──┬─────┬─────┬──────────────────────────── VDD
                  ┌─┴─┐ ┌─┴─┐ ┌─┴─┐                8u/4u pfet, 100 nA each
             PG ──┤MP1├─┤MP2├─┤MP3├── PG            (+ MPBN, 1/4 scale)
                  └─┬─┘ └─┬─┘ └─┬─┘
                    NA  NBTOP  VREF ──────────────► VREF pad
                    │     │     │
                    │    RT    R2 = 6.30 M
                    │     │     │
                    │     NB   ER
                    │     │     │
                    │    R1    QR                   pnp_10p00x10p00, 1x
                    │     │     │
                   Q1    EC    VSS
                  (1x)   │
                    │  Q8A..Q8H  (8x)
                   VSS   VSS

     NA, NB ──► error amplifier ──► PG        forces V(NA) = V(NB)
     NA, NBTOP ──► settle comparator ──► BIAS_OK
     PB (secondary bias rail) ──► IBIAS output leg, all amplifier tails
```

The amplifier forces `V(NA) = V(NB)`, so the voltage across `R1` is exactly
the emitter-area-ratio ΔV_EB and the branch current is

```
I     = ΔV_EB / R1 = (kT/q)·ln(8) / R1                     (PTAT)
VREF  = V_EB(XQR) + (R2/R1)·ΔV_EB                          (first-order flat)
IBIAS = 20 · (I/4)                                          (via PB)
```

Three properties fall out of writing it this way, and all three are
load-bearing:

- **`VREF` depends on `R2/R1`, not on R.** The absolute value and the
  temperature coefficient of the poly resistor cancel in a same-flavour
  ratio (`sim/devchar/SUMMARY.md` establishes this at the model level). The
  `res_ff`/`res_ss` corners move `R1` by ±25 % and move `VREF` by 0.6 %.
- **The amplifier's inputs are PNP-clamped.** `NA` is a V_EB and `NB` is a
  V_EB plus ΔV_EB, so neither can rail no matter how far the mirror
  over-drives. An earlier revision of this cell used a Kuijk arrangement
  with the amplifier sensing the tops of two large resistors instead; over-
  driving the mirror pushed both inputs to `VDD`, the input pair went into
  triode, the differential signal vanished and the loop sat in a stable
  high-current state at 17–90 µA. Measured on the same grid, not
  hypothetical. The three-leg arrangement here cannot reach that state,
  which is why it was chosen over the two-leg one despite costing an extra
  100 nA branch.
- **The reference leg is separate from the loop.** `XMP3`/`R2`/`XQR` is a
  matched third leg, so `VREF` railing (which it does transiently on a fast
  ramp) cannot destabilise the loop.

## Device sizing and why

### Vertical PNPs — `pnp_10p00x10p00`, 8:1, ~100 nA/branch

Unit cell and ratio come straight from `sim/devchar/SUMMARY.md`
("Recommendation: sensing core"): `pnp_10p00x10p00` in an **8:1
emitter-area pair**, built as **eight unit-cell instances wired in
parallel** (`XQ8A..XQ8H`), not one instance with `par=8` — that parameter
scales only the model's mismatch term, not `Is`. `XQR` is a ninth,
identical device carrying the same current, so its V_EB matches `XQ1`'s by
construction in a deterministic corner.

**Deviation from DR-005's bias-point estimate, stated explicitly.** DR-005
estimates 1–5 µA/branch for the shared core. This cell runs **~100 nA/branch**
at tt/27 °C — 10–50× below that estimate — because the estimate predates
[`por-iq`](../spec/target-spec.md#por-iq)'s original <1 µA row being written
down. Even at 100 nA/branch the row was not met against that original budget
(see below; it is met against the current, DR-018-recosted <3.0 µA budget),
so 1 µA/branch was never a candidate. The property the 8:1 recommendation rests on still holds
at 100 nA: measured ΔV_EB is **41.86 / 53.90 / 71.50 mV** at −40/27/125 °C
against **41.75 / 53.79 / 71.30 mV** of theory — a **0.20–0.29 % error**,
comparable with the 0.33 % `sim/devchar` measured at 10 µA.

### Resistors — `ppolyf_u_3k`, W = 2 µm

| Device | Drawn L | Squares | R at tt/27 °C | Sets |
| --- | ---: | ---: | ---: | --- |
| `R1` | 350.0 µm | 175.0 | 537.6 kΩ | `I = ΔV_EB/R1` = 100 nA |
| `R2` | 4104.0 µm | 2052.0 | 6.304 MΩ | `R2/R1` = 11.726 → the PTAT term that flattens `VREF` |
| `RT` | 17.5 µm | 8.75 | 26.9 kΩ | `RT/R1` = 0.05 → the settle-detect offset |
| `RZ` | 1016.0 µm | 508.0 | 1.561 MΩ | Miller nulling resistor, ≈ 1/gm(`XMS2N`) |

`ppolyf_u_3k` rather than `temp_core`'s `ppolyf_u`: at ~3 kΩ/□ it is the
highest-sheet flavour `sim/devchar` measured, and a `ppolyf_u` `R2` would
need 8.5× the area for the same value. `VREF` only depends on the **ratio**
`R2/R1`, and `SUMMARY.md` shows the body-resistor temperature factor is a
multiplicative function of flavour alone, so the −1545 ppm/°C TC and the
±25 % sheet corner cancel in the ratio exactly as they do for
`por_comparator`'s divider. What does *not* cancel is the effect on the
absolute current — see [Iq apportionment](#iq-apportionment).

`RT` is the only unusual one. It is a 5 % tap on `R1`, placed between
`XMP2`'s drain (`NBTOP`) and `NB`, so that

```
V(NBTOP) − V(NA) = I·(R1 + RT) − ΔV_EB
```

which is **negative until the loop current reaches `R1/(R1+RT)` = 95.2 % of
its settled value** and is `+I·RT` — a PVT-stable, PTAT **2.1 / 2.7 / 3.6 mV**
at −40/27/125 °C — once settled. That is the settle detector's input, and it
is a ratio of same-flavour resistors times ΔV_EB, so it carries no corner
spread of its own. Its cost to the mirror is a 2.1–3.6 mV V_DS mismatch
between `XMP1` and `XMP2`, i.e. under 0.03 % of ratio on a 4 µm-long device.

### Mirror and the secondary bias rail `PB`

| Device | W/L | Role |
| --- | --- | --- |
| `MP1`, `MP2`, `MP3` | 8 µm / 4 µm | the three matched core legs, ~100 nA each |
| `MPBN` | 2 µm / 4 µm | 1/4-scale leg that generates `NBG` → `PB` |
| `MBN`, `MBN2` | 2 µm / 4 µm | `NBG` diode and its mirror into `XMBP` |
| `MBP` | 2 µm / 4 µm | diode-connected pfet defining `PB` |
| `MPIB` | 40 µm / 4 µm | `IBIAS` output leg, 20:1 against `XMBP` → 0.5 µA |

**Only the four core legs hang off `PG`.** Every other current source in the
cell is gated from `PB` instead. That is a compensation decision, not a
stylistic one: `PG` is the amplifier's output node, and `XMPIB`'s gate alone
is 160 µm² of poly. With `XMPIB`, the amplifier tail, the second-stage load
and the settle-comparator tail all on `PG`, the loop's second pole sat about
a decade **below** its unity-gain frequency and the loop **oscillated** —
measured, as a 180 µs-period relaxation with `VREF` swinging 0.46…2.5 V at
every corner. Moving the wide-gate sources to `PB` (a low-impedance diode
node that is not in the loop) cut `C(PG)` by ~4× and the same loop settles
monotonically at all 81 points.

### Error amplifier

PMOS input pair, NMOS mirror load, NMOS common-source second stage,
Miller-compensated with a nulling resistor — the same structure as
`design/temp_core.sch`'s amplifier.

| Device | W/L | Role |
| --- | --- | --- |
| `MPT` | 2 µm / 4 µm | tail from `PB`, ~26 nA |
| `MI1`, `MI2` | 16 µm / 4 µm | input pair, gates on `NA`, `NB` |
| `ML1`, `ML2` | 4 µm / 8 µm | NMOS mirror load |
| `MS2N` | 8 µm / 8 µm | second stage, gate `N2` |
| `MS2P` | 2 µm / 4 µm | second-stage load from `PB` |
| `CC` + `RZ` | 20 × 20 µm MIM (0.8 pF) + 1.56 MΩ | Miller compensation with nulling zero |

A PMOS input pair is required, not preferred: the inputs sit at a V_EB,
which falls to **0.36 V at 125 °C** (measured), far below an NMOS pair's
usable common-mode floor. `XMS2N` is a current-density copy of `XML1`, so
stage 1's output sits at the diode node's own V_GS and the *systematic*
input offset is structurally near zero — measured `|V(NA) − V(NB)| ≤ 1 µV`
in the settled state at every corner.

`RZ` ≈ 1/gm(`XMS2N`) moves the right-half-plane zero out of the way; without
it that zero sits about 2× above the unity-gain frequency and costs ~26° of
phase.

## Startup

A ΔV_EB loop has a degenerate zero-current solution as well as its intended
one. Two independent pieces of evidence say this cell does not sit in it:

- **`vref_op_v`** samples `VREF` in the operating point ngspice solves
  *before* the transient starts, with the static branch already at full
  rail — the same analysis that caught #9's first revision sitting in its
  dead state. Measured **1.18759…1.21024 V at all 81 points**, i.e. bit-identical
  to the settled value: the solver finds the intended solution from cold,
  before the kick has done anything.
- **`bo_shallow_ppm` / `bo_deep_ppm`** compare `VREF` before and after a dip
  to 0.5 V (rail below dropout, nodes still charged — the classic latch
  trap) and after a full collapse to 0 V. Measured **0…13 ppm at 79 of 81
  points**; the two exceptions are recovery-time artefacts, not latches (see
  [The starved-loop window](#the-starved-loop-window)).

  **Both of those checks sample after a recovery, so they can only report a
  latch once the recovery has finished, and issue #185 is what happens when
  it has not.** On the *extracted* netlist the recovery is up to an order of
  magnitude slower, and a fixed wall-clock sample taken mid-recovery reads
  −5·10⁵ ppm — which looks exactly like the latch this bullet is here to rule
  out, and is not one. The deck now samples at 29.9 ms, and the one corner it
  still does not clear was taken out to 120 ms in
  [`control/results.md`](../sim/bias-core-designer-check/control/results.md):
  the reference comes back to **0.000 ppm** of its pre-event value there too.
  The no-latch statement therefore stands under real parasitics — it just
  needs a longer look. See
  [The post-layout brownout regression](#the-post-layout-brownout-regression--it-was-the-deck-issue-185).

The kick itself is a **current-referenced dead-loop detector**, the same
principle `design/temp_core.md` arrived at:

| Device | Size | Role |
| --- | --- | --- |
| `KS0..KS4` | nfet 1 µm / 8 µm ×5, diode-connected | five-deep stack from `VDD`: a rail-referenced pull-up on `NKG`, deliberately deep in subthreshold |
| `KA` | pfet 1 µm / 4 µm, gate `PB` | replica that delivers current only while the loop is biased |
| `KAN` / `KPD` | nfet 2 µm / 4 µm, nfet 8 µm / 4 µm | mirror it into a 4× pull-down on `NKG` |
| `KICK` | nfet 1 µm / 4 µm, gate `NKG` | the kick: pulls the mirror gate `PG` down |

Loop alive: `KPD` beats the stack, `NKG` ≈ 0, `KICK` idle. Loop dead: `PB`
collapses to `VDD`, `KA` delivers nothing, the stack pulls `NKG` up and
`KICK` pulls `PG` down until the loop restarts. The stack is sized so its
current — the only *static* cost of the whole startup block — is **≤ 17.5 nA
at ff/125 °C/3.63 V** and never zero at any corner.

**The comparison is loop current versus a rail-referenced current, not a
voltage level on `VREF`.** An earlier revision gated the detector on
`V(VREF) > Vt` and left the core parked near zero current for ~200 µs after a
deep brownout at `fs`/−40 °C, because 0.7 V of a not-yet-settled `VREF`
already looks like "alive" to an nfet gate — and `BIAS_OK` stayed stale-high
throughout. Measured, then fixed, then re-measured.

`XMOKC` closes the same hole on the `BIAS_OK` side: it forces the settle
comparator's output low whenever `NKG` says the loop is dead. Without it a
collapsed core leaves that output stale — there is no tail current to move
it — and `BIAS_OK` reads a false valid for as long as the restart takes.

## `BIAS_OK`

The settle detector is a PMOS pair comparing `NBTOP` against `NA` (i.e. the
`RT` tap described above), an NMOS-loaded gain stage, and a deliberately
skewed output inverter.

**It is one-sided on purpose.** It asserts when the loop current is **above**
95.2 % of target and says nothing about the current being too high. That is
the correct asymmetry:

- A reference that is **low** lowers `por_comparator`'s threshold
  (`VPOR↑ = 2.16667·VREF`) and releases reset **early**, below the ratified
  [`por-vth-rise`](../spec/target-spec.md#por-vth-rise) minimum. This is the
  failure mode, and it is what the detector catches.
- A reference that is **high** raises the threshold and **delays** release,
  which [`por-reset-pulse`](../spec/target-spec.md#por-reset-pulse)
  explicitly does not bound ("no maximum specified in wave 1").

On a rising ramp the amplifier lags in the direction that over-drives the
loop, so the error is on the safe side — and the record measures that rather
than asserting it.

### The release guard

Timing `BIAS_OK` against `VREF` in isolation is the wrong question, because
`BIAS_OK` going valid while `VREF` is still **rail-limited** is harmless: a
rail-limited `VREF` makes `2.16667·VREF` larger than `VDD` by construction.
The record therefore measures the thing that matters — the rail at which
(`BIAS_OK` is a valid high) **and** (`VDD ≥ 2.16667·VREF`) first hold
together, i.e. the `VDD` at which the assembled block would actually release:

| | Measured over the 81-point grid | Bound |
| --- | --- | --- |
| `relv_slow_v` (500 µs ramp) | **2.800…3.117 V** | ≥ 2.47 V ✅ |
| `relv_fast_v` (1.0 V/µs ramp) | **= VDD at every point** (2.97/3.30/3.63 V) | ≥ 2.47 V ✅ |
| `okf_at_1v_mv` (`BIAS_OK` at VDD = 1.0 V, fast ramp) | **−0.088…+0.107 mV** | ≤ 300 mV ✅ |

The `relv_slow_v` numbers sit **above** the ratified 2.60 V typ, by
93…239 mV (`err_at_relv_mv`). That is not a threshold error: it is the
reference reading high while the rail is still slewing, and it is a *late*
release. Its coefficient is worth stating because #14 needs it —

> **Ramp-rate feedthrough.** The mirror gate `PG` has to track `VDD`, so the
> Miller capacitor injects `Cc·dVDD/dt` into the amplifier's stage-1 output,
> which the loop can only absorb as an input-referred offset of
> `(Cc/gm1)·dVDD/dt`.
>
> **Measured directly on `bias_core` alone — not inferred from a downstream
> threshold — across the full 81-point PVT grid, on both ramp directions**
> ([issue #208](https://github.com/2AMLogic/gf180-temp-por/issues/208),
> [`control/ramp_feedthrough_results.md`](../sim/bias-core-designer-check/control/ramp_feedthrough_results.md)).
> This supersedes the single **≈ 2.4 µs** figure this note previously quoted,
> which undershoots the measured coefficient at **every** corner in the
> grid — not only at the `ss`/-40 °C corner issue #208 was filed from:
>
> | | Up-ramp (`VREF` high) | Down-ramp (`VREF` low) |
> | --- | --- | --- |
> | Schematic | **17.31…47.45 µs** | **17.54…51.08 µs** |
> | Extracted | **17.31…47.40 µs** | **17.59…51.27 µs** |
>
> The coefficient's **sign reverses with ramp direction** — toward more loop
> current (`VREF` high) on a rising rail, toward less (`VREF` low) on a
> falling one — rather than "always toward more loop current", which this
> note previously stated on the strength of a rising-ramp-only measurement.
> The worst corner in both directions is `ss`/-40 °C, which independently
> reproduces [`sim/por-vth/control/results.md`](../sim/por-vth/control/results.md)'s
> own **~49 µs** figure (measured indirectly, through the full four-cell
> assembly, issue #187/#218/[DR-021](../spec/decision-records/DR-021-por-hysteresis-quasi-static-scope.md))
> to within ~1 µs on both netlists — two independent methodologies agreeing
> at the one point they share. `ff`/125 °C is the best corner in both
> directions, at roughly a third of `ss`/-40 °C's magnitude: the coefficient
> tracks the reference's own node impedances, which rise at cold/slow
> corners for the same reason a nA-scale bias network's settling time does.

`BIAS_OK` itself asserts at `t_ok_us` = **193…307 µs** into the 500 µs ramp,
with the reference then **45…407 mV** from its settled value
(`err_at_ok_mv`) — almost all of that being the feedthrough term above.
`ok_droop_mv` ≤ 0.016 mV: the flag is a hard rail-to-rail logic level for
`por_comparator`'s inverter, never a partially resolved analog one.

### Settling and dropout

| Property | Measured | Note |
| --- | --- | --- |
| Settling after the rail stops moving (`t_settle_us`) | **10.9…33.4 µs** | to within 0.1 % of the settled value |
| Core minimum operating voltage (`vdd_ref90_v`) | **1.127…1.788 V** | rail at which `VREF` first reaches 90 % of settled |
| Brownout recovery (`t_bo_recover_us`) | **0…655 µs** | rail return → `BIAS_OK` valid again, after a full collapse |

The dropout number is the important one for block self-consistency: at
≤ 1.79 V it sits comfortably below
[`por-vth-fall`](../spec/target-spec.md#por-vth-fall)'s 2.22 V minimum, so on
a falling rail the assert edge is set by `por_comparator`'s divider, not by
the reference collapsing underneath it.

## Resolved: the `BIAS_OK` quasi-static failure was a testbench artefact (issues #43, #46)

**Issue #43 reported, and record `20260801-111049-bc599be` measured, that
`BIAS_OK` fails to assert or asserts non-monotonically at every one of the 27
corner/temperature combinations on a quasi-static rising rail. Issue #46
root-caused that result to the reporting deck's own convergence aid. The cell
is not defective; the deck was. No change was made to
`design/bias_core.sch`.**

This section replaces the "Open defect" write-up PR #47 put here. The
superseded finding is not deleted — its record, its raw per-corner logs and
its netlist snapshot all remain under `sim/bias-core-startup/`, because
`sim/` is append-only. What changed is the *interpretation*, and the
interpretation is now backed by a controlled experiment rather than by
inference.

### The root cause, in one paragraph

The superseded deck swept the rail with `.dc` and could only be made to
converge by raising `gmin` from ngspice's default `1e-12` to `1e-9`. `GMIN`
is a conductance the simulator places across **every device junction** to
keep the Jacobian non-singular. At 1 nS and 3.3 V of rail that is **~2.7 nA
per junction**. The settle comparator this experiment exists to test runs its
input pair at **4.728 and 4.481 nA**, and the whole signal it resolves is the
**0.247 nA** difference between them — a fraction of one junction's worth of
aid. Worse, the aid is not common-mode: the comparator's output node `NOKO`
carries one junction its reference-side counterpart `NOKL` does not
(`XMOKC`'s drain, the dead-loop detector's forced-low path), so **0.563 nA**
of the injected current appears as a pure **differential** error, of the sign
that opposes assertion — more than twice the signal. The deck was measuring
its own crutch.

### The controlled experiment

One variable, one deck, `tt` / −40 °C / `VDD` = 3.3 V, plain `op` on
`design/netlist/bias_core.spice` with the same `IBIAS` consumer-diode load
the testbenches use. The only difference between the two columns is the
`.options gmin` line.

**The experiment is committed and re-runnable** —
`sim/bias-core-startup/control/`: the stimulus fragment, the script that
composes and runs both variants in one process, the two exact decks as run,
both raw ngspice logs, and
[`control/results.md`](../sim/bias-core-startup/control/results.md), which is
generated from those logs. Every number in this section is transcribed from
`results.md` and from nowhere else; re-run it with

```
python3 sim/bias-core-startup/control/run_gmin_control.py
```

It is a *diagnosis*, not a recorded result — one PVT point cannot substantiate
a spec row — so it deliberately does not mint a record; see `sim/README.md`,
"Control experiments". The corner-grid evidence is the 81-point record below.

| | ngspice default (`gmin = 1e-12`) | the superseded deck (`gmin = 1e-9`) |
| --- | ---: | ---: |
| `V(NOKO)` — settle comparator output | **1.643 V** (resolved high) | **0.605 V** (unresolved) |
| `V(NOKL)` — its diode-load reference | 0.602 V | 0.626 V |
| `V(NOKX)` — threshold-stage output | 94 µV | 3.256 V |
| **`BIAS_OK`** | **3.29999985 V — asserted** | **1.54 µV — not asserted** |
| `VREF` | 1.1978 V | 1.2121 V (+1.2 %) |
| `I(XMOKA)` (gate `NA`) | 4.728 nA | 7.799 nA |
| `I(XMOKB)` (gate `NBTOP`) | 4.481 nA | 7.247 nA |
| `I(XMOL1)` (diode load, mirrors `XMOKB`) | 4.483 nA | 9.295 nA |
| `I(XMOL2)` (mirror output, loads `XMOKA`) | 4.727 nA | 9.284 nA |

Read the last four rows as KCL and the artefact is explicit. At the default
`gmin` the loads carry what the input pair delivers, to three digits
(4.483 vs 4.481 nA; 4.727 vs 4.728 nA) — the comparator sees only its own
signal, **`I(XMOKA) − I(XMOKB)` = +0.247 nA**, and `NOKO` resolves high. At
`gmin = 1e-9` the loads carry **2.048 nA and 1.485 nA more** than the pair
delivers; the **0.563 nA** difference between those two excesses is the
unbalanced part, and it is `XMOKC`'s drain junction hanging on `NOKO` with no
counterpart on `NOKL` (`V(NOKO)` × 1 nS = 0.605 nA of `gmin` current at that
one junction). That 0.563 nA exceeds even the 0.552 nA the pair delivers *at
the perturbed operating point*, and it is more than twice the 0.247 nA of
real signal at the true one, so the comparator lands on the wrong side.

Those last two figures are the number this document previously reported two
ways, and they are two different quantities: **0.247 nA is the signal** — what
the pair produces in the circuit as it actually operates — while 0.552 nA is
what the pair produces in the deck the aid has already displaced, and is not
a property of the circuit at all. The claim "the aid is larger than the
signal" holds on either, by 2.3× on the one that matters.

`VREF` moving 1.2 % between the two columns is the same effect on the main
loop, and it is why the superseded record's "`VREF` settles correctly at
every point that could be measured" was true only approximately.

### Why the `.dc` sweep could not simply be re-run without the aid

It does not converge. At `gmin = 1e-12` the `.dc` continuation hits the
harness's 300 s per-point timeout at **all 27** corner/temperature
combinations. A DC continuation is the wrong tool for a circuit whose
operating point below ~1 V of rail has the startup stack and all three main
legs near cutoff simultaneously. The experiment therefore had to change
method, not just options.

### What replaces it

`sim/bias-core-startup/` is now a **quasi-static transient rail ramp** at
ngspice's default `gmin` — the same "slow ramp, not a DC sweep" argument
`sim/por-output-chain-floor/` already makes in this repo — with three DUTs in
one `tran`:

| DUT | Rail | Purpose |
| --- | --- | --- |
| `xqs` | 0 → 3.63 V over 30 ms (**121 V/s**) | the primary quasi-static cold start; every branch-tracking, ordering and release-rail measurement |
| `xqf` | the same, 4× faster (**484 V/s**) | measures ramp-rate independence, i.e. proves the primary result really is in the quasi-static limit |
| `xbo` | the `xqs` ramp, then a **full collapse to 0 V**, 3 ms of dead rail, then the same quasi-static ramp again | the brownout-restart branch #43's acceptance criteria asked for and #46 inherited |

Both rates sit 3–4 decades below the **0.36 V/µs** boundary at which this
document's own [starved-loop window](#the-starved-loop-window) measures the
loop starting to lag, and inside the ratified
[`por-ramp-rate`](../spec/target-spec.md#por-ramp-rate) envelope — whose full
sweep remains #14's chartered row and is deliberately not pre-empted here.

### The result: 81 of 81 points pass

Record `20260801-230642-c320628` (`sim/bias-core-startup/records/`), full
81-point grid, **status PASS, every check green at every point**. This
record **supersedes** the original 27/27-FAIL record
`20260801-111049-bc599be` via `--supersedes`, closing issue #50's evidence-
hygiene gap: the record that first reported this 81/81 PASS result,
`20260801-144500-ab081eb`, carried `Supersedes: (none)`, so a reader landing
on `bc599be` had no pointer in `sim/` to the record that corrects it. Every
measurement in the table below is bit-identical between `ab081eb` and
`c320628` — the re-run changes only the record's evidence-chain metadata, not
the circuit result:

| | Measured over the 81-point grid | Bound |
| --- | --- | --- |
| `ok_chatter_mv` — rail between the first and last upward crossing of `BIAS_OK` | **0 at all 81 points** | ≤ 1.0 mV ✅ |
| `v_bias_ok_v` — rail at which `BIAS_OK` asserts | **1.000…1.581 V** | ≤ 2.45 V ✅ |
| `release_margin_v` — how far below the ratified 2.47 V minimum it asserts | **0.889…1.470 V** | ≥ 0.02 V ✅ |
| `relv_qs_v` — rail at which the assembled block would actually release | **2.583…2.629 V** | ≥ 2.47 V ✅ |
| `vref_at_ok_pct` — `VREF` at the instant the flag asserts, vs. its settled value | **78.6…107.0 %** | ≥ 70 % ✅ |
| `vref_final_v` | **1.1876…1.2090 V** | 1.14…1.26 V ✅ |
| `noko_final_v` — the settle comparator's own resolved output level | **1.376…1.817 V** | ≥ 1.0 V ✅ |
| `nkg_final_v` — startup kick idle at the top of the ramp | **≤ 5.5 mV** | ≤ 0.5 V ✅ |
| `qs_rate_delta_mv` — assertion rail, 484 V/s minus 121 V/s | **0.001…131.7 mV** | ±250 mV ✅ |
| `v_core_up_v` — rail at which `VREF` first reaches 1.10 V | **1.145…1.569 V** | ≤ 1.9 V ✅ |

Two of those rows say more than their tick does.

**`relv_qs_v` is stronger than "above the minimum".** At 2.583–2.629 V it
sits inside the *full* ratified
[`por-vth-rise`](../spec/target-spec.md#por-vth-rise) window — 2.47 / **2.60**
/ 2.73 V — and within 30 mV of its **typical**, at every one of the 81 points.
The check only asks that the assembled block not release below the 2.47 V
minimum; what the grid actually shows is a release rail landing on the
ratified target, not merely on the legal side of its edge.

**`vref_at_ok_pct` is bounded as of issue #50**, having been recorded
unbounded in the #46 revision (`ab081eb`) and checked against the bound for
the first time in the `--supersedes` re-run cited above (`c320628`) — the
78.6…107.0 % row clears the new floor by 8.6 points. It needs a bound of its
own because
`relv_qs_v` is a *conjunction*: at the 9 hot combinations `BIAS_OK` reads a
valid high from about 1.0 V of rail, so the `v(bias_okq) > 0.5·v(vddq)` term
in `Brelq` is satisfied from the bottom of the ramp and `relv_qs_v` is set
**entirely** by the `VDD ≥ 2.16667·VREF` term. That is harmless — a
rail-limited `VREF` makes `2.16667·VREF` exceed `VDD` by construction, which
is the argument [The release guard](#the-release-guard) makes — but at those
points `relv_qs_v` carries no information about whether the *flag* is early,
and `vref_at_ok_pct` was then the only evidence on that question: recorded,
argued, untested. The bound is a floor on "the reference is substantially
there when the flag goes true", set 8.6 points below the worst measured point
(78.6 % at `res_ff`/125 °C). It is not spec-derived — no ratified row is
involved, and `relv_qs_v` remains the pass/fail that carries `por-vth-rise`.

and, on the brownout-restart branch:

| | Measured over the 81-point grid | Bound |
| --- | --- | --- |
| `ok_bo_dip_mv` — `BIAS_OK` with the rail collapsed to 0 V | **−61.2…+33.6 mV** | ±300 mV ✅ |
| `v_bias_ok_restart_v` — rail at which it re-asserts on the restart ramp | **1.000…2.338 V** | ≤ 2.45 V ✅ |
| `ok_bo_end_droop_mv` — `VDD` − `BIAS_OK` after the restart | **≤ 0.015 mV** | ≤ 1.0 mV ✅ |
| `vref_bo_end_delta_ppm` — `VREF` after the restart vs. after the cold start | **−0.83…+0.83 ppm** | ±1000 ppm ✅ |

That last row is the strongest single statement in the record. Two
quasi-static approaches to the same rail — one from a cold cell, one from a
cell that has been up, fully collapsed and restarted — land on the same
reference to **better than one part per million**. A second reachable
operating branch cannot survive that. What it does *not* say is that the
restart began from a completely discharged cell: `vref_bo_dip_v` measures
`VREF` still at **0.518 V** two-thirds of the way through the 3 ms dead-rail
window at `ss`/−40 °C, so the restart is a genuine repeat, not a proof that no
second branch exists. That stronger statement is
`sim/bias-core-designer-check/`'s `vref_op_v`, which *seeds* the DC solve in
the degenerate zero-current state at all 81 points.

#### The one tight number

`v_bias_ok_restart_v` = **2.338 V at `ss`/−40 °C** leaves **112 mV** to its
2.45 V bound. That is the tightest rail margin in the record — its only peer
is `relv_qs_v`'s 113 mV above the ratified 2.47 V floor (2.583 V at
`bjt_ff`/125 °C), and the same flag on the *cold* start clears the *same*
2.45 V bound by 869 mV. The restart therefore asserts roughly **750 mV
later** than the cold start at that corner. It passes, and
the mechanism is understood — `ss`/−40 °C is the slowest corner, and after a
collapse the cell restarts from a partly-discharged state with the same
nA-class currents having to re-charge `PG` and the settle comparator's nodes —
but it is the number to watch. Anything that slows the restart further (a
larger `XCC`, a weaker startup kick, a colder or slower corner added to the
grid) spends this margin first, and it is the only measurement in the record
where a modest regression would cross a bound. It is called out in
`tb.json`'s own check description for the same reason.

`qs_lag_est_mv` — the residual distance between the primary 121 V/s result
and the true quasi-static limit, extrapolated from the two measured rates —
is **≤ 43.9 mV of rail**, against release margins of about a volt. The
method's own error is three orders of magnitude smaller than the margin it is
measuring.

### No regression in the sibling records

`design/bias_core.sch` is untouched, so `design/netlist/bias_core.spice` is
byte-identical (sha256 `87b6f943…`) and the two sibling experiments cannot in
principle have moved. Both were re-run anyway, on a clean tree, because
"cannot in principle" is not evidence:

| Experiment | Re-run record | Result | Against its pre-#46 record |
| --- | --- | --- | --- |
| `sim/bias-core-designer-check/` | `20260801-150709-5a013e8` | **FAIL**, unchanged — `por-iq` and the starved-loop window, the two conflicts this document already owns | **Bit-identical to `20260801-053019-732a894`**: every measurement's min, max, mean, spread and the corner each extremum lands on |
| `sim/bias-core-ibias-sharing/` | `20260801-152327-b72c10c` | **PASS**, 81/81, unchanged | Identical to `20260801-073555-8b7e57f` on six of eight measurements; the two that differ are `por_raw_shared_droop_mv` / `por_raw_control_droop_mv`, whose extremes move by **1 µV** against a 20 mV bound |

That 1 µV is **not unexplained nondeterminism**: the two records' own
environment blocks say the baseline `20260801-073555-8b7e57f` ran on
**ngspice-42 / Linux / python 3.12.3** and the re-run
`20260801-152327-b72c10c` on **ngspice-46 / macOS / python 3.14.6**, against
the *same* testbench netlist (sha256 `072b8fc4…`) and the same pinned PDK. A
1 µV difference on a 20 mV bound between two simulator versions on two
platforms is the floating-point noise floor of the measurement, and it is the
only place a re-run on the same netlist can move at all. The harness records
that environment on every run precisely so a reader can settle this question
from the evidence rather than by assumption.

### What changed in the testbench's checks, and why

The method change forced a re-derivation of the check bounds, and three of
them moved. All three are stated here rather than left in the diff, because
"a bound moved and the result now passes" is exactly the thing a reader
should be suspicious of. Every bound that carries a **ratified spec row** is
unchanged.

| Check | Was | Now | Why |
| --- | --- | --- | --- |
| `v_bias_ok_v` | min 1.5 V, max 2.45 V | **max 2.45 V only** | The max is spec-facing and unchanged. The min assumed the core's dropout is above 1.5 V. It is not — this document's own `vdd_ref90_v` measures **1.127–1.788 V**, and quasi-statically the loop is up and merely rail-limited from ~0.95 V at hot corners, so a *correct* flag legitimately asserts near 1.0 V there. Replaced by `relv_qs_v`. |
| `startup_margin_v` | min 0.1 V | **recorded, unbounded** | In the quasi-static limit this is not a margin. `v_core_up_v` and `v_bias_ok_v` are two points on the *same* steep transition, so demanding 100 mV of rail between them demands that the flag be **late**. The old bound encodes a 500 µs-ramp intuition — the very lag this experiment exists to remove. Measured: **−0.181…+0.045 V**. |
| `ok_at_140_mv` | max 300 mV | **removed; `ok_at_100_mv` recorded, unbounded** | Its stated premise, "1.40 V of rail is below the core's dropout at every corner", is contradicted by `vdd_ref90_v` above. There is no fixed rail at which "the core is definitely not up" holds across all 27 combinations *and* the output stage is still driven, so no honest fixed-rail bound exists. Replaced by `relv_qs_v`. |

All three removals are covered by **one** new check that is strictly stronger
because it is *reference-referred* instead of rail-referred:

> **`relv_qs_v ≥ 2.47 V`** — the rail at which (`BIAS_OK` is a valid high)
> **and** (`VDD ≥ 2.16667·VREF`) first hold together, i.e. the rail at which
> the assembled block would actually release. It fails if and only if
> `BIAS_OK` vouches for a reference low enough to pull `por_comparator`'s
> threshold below the ratified
> [`por-vth-rise`](../spec/target-spec.md#por-vth-rise) minimum. A `BIAS_OK`
> that goes valid while `VREF` is still merely **rail-limited** cannot trip
> it — correctly, because a rail-limited `VREF` makes `2.16667·VREF` larger
> than `VDD` by construction, which is the argument
> [The release guard](#the-release-guard) already makes. Same B-source
> construction as `sim/bias-core-designer-check/`'s `relv_slow_v`, evaluated
> in the quasi-static limit instead of on a 500 µs ramp.

Five further checks are **added**, not relaxed: `qs_rate_delta_mv`
(ramp-rate independence), `noko_final_v` (below), and the three
brownout-restart checks `ok_bo_dip_mv`, `v_bias_ok_restart_v` and
`vref_bo_end_delta_ppm`.

### The permanent guard against this recurring

`noko_final_v` is new and deliberately chosen. `NOKO` is the settle
comparator's own output — the node the `RT` tap's 2.1–3.6 mV differential is
amplified to before `XMOK2` turns it into a logic level. Because that first
stage is a **linear OTA, not a regenerative comparator**, `NOKO`'s settled
level *is* the margin: it has to sit well above the ~0.6 V at which `XMOK2`
starts to conduct, or the assertion is a coin flip. It is also the single
number that separates the artefact from the circuit at `tt`/−40 °C —
**0.605 V** with the aid, **1.643 V** without — so any future re-introduction
of a nA-scale numerical crutch, or any erosion of the comparator's drive,
fails this check first instead of surfacing as an unexplained `BIAS_OK`
failure. Measured: **1.376…1.817 V** across the grid.

### What this does *not* claim

- It does **not** claim the settle comparator has generous margin. It has
  0.78–1.22 V of `NOKO` headroom over `XMOK2`'s threshold, from a
  2.1–3.6 mV input differential amplified by a single stage. That is enough
  in a deterministic corner and it is now measured on every run, but **local
  mismatch on the comparator's input pair and load mirror is #15's Monte
  Carlo job**, not this record's, and a few millivolts of random offset is
  the same size as the signal. #15 should treat this pair as a priority
  instance.
- It does **not** retract [the starved-loop window](#the-starved-loop-window).
  That is a separate, still-open, *fast*-ramp finding measured by
  `sim/bias-core-designer-check/` at the default `gmin`, and it is untouched
  by any of this.
- It does **not** claim the superseded record was worthless. It is the
  evidence that produced the question, and its raw logs are what made the
  root cause findable. The lesson it carries forward is narrower and more
  useful than "the cell is broken": **a convergence aid whose injected
  current is comparable with the signal under test is not a convergence aid,
  it is a different circuit** — and at this block's nA-class bias currents,
  ngspice's default `gmin` is already 2.7 pA/junction at 2.7 V, so the
  headroom to abuse is smaller here than in almost any other analog block.

## The starved-loop window

**This is a measured defect, not a modelling artefact, and it is the second
of the two conflicts this document exists to surface.**

At the ratified fast end of
[`por-ramp-rate`](../spec/target-spec.md#por-ramp-rate) — **1.0 V/µs** — the
amplifier cannot slew `PG`. `PG` must track `VDD`, `C(PG)` is ~0.45 pF plus
0.8 pF of Miller capacitor, and the second stage sources ~26 nA: the
available slew rate is ~21 mV/µs against a rail moving at 1000 mV/µs. The
loop is therefore driven far past its operating point during the ramp,
parks at a small fraction of its intended current when the ramp stops, and
crawls back over hundreds of microseconds to milliseconds. Worst observed:
`VREF` sitting at **0.54 V** (45 % of nominal) for **4.4 ms** at `sf`/−40 °C.

While it is parked, **every** recovery mechanism in the cell is starved with
it — the amplifier tail, the settle comparator's tail and the dead-loop
detector's replica are all biased from the loop — so the settle comparator's
high-impedance output cannot be pulled down and `BIAS_OK` reads a **false
valid**. Measured, as the time-integral of (`BIAS_OK` valid) ∧ (`VREF` more
than 100 mV below settled):

| Branch | `t_false_ok_*_us` over the 81-point grid | Bound |
| --- | --- | --- |
| 500 µs ramp (≤ 7.3 V/ms) | **0…45.7 µs** (45.7 µs at `ff`/125 °C only; 0 at 78 of 81 points) | ≤ 5 µs ❌ at 3 points |
| 1.0 V/µs ramp | **11…1989 µs** | ≤ 5 µs ❌ at all 81 points |
| brownout branch (0.5 V dip, then full collapse) | **326…1567 µs** | ≤ 5 µs ❌ at all 81 points |

> **The two figures above that end near 2 ms are floors, not measurements
> (issue #185).** They were taken on a 2 ms transient, and the window they
> measure is longer than that at the cold corners — the same 4.4 ms this
> paragraph already quotes. On the 30 ms deck that replaced it, and against
> the *extracted* netlist, the fast-ramp branch reads **27.99…6584.96 µs** and
> the brownout branches **359.267…39866.3 µs**. The conclusion is unchanged
> and the direction is unchanged; only the magnitude was being clipped. See
> [The post-layout brownout regression](#the-post-layout-brownout-regression--it-was-the-deck-issue-185).

**Measured boundary.** Correct at ramps of **0.36 V/µs and slower** (10 µs
to full rail) at every corner, including −40 °C; false-valid at 1.0 V/µs.
`por-ramp-rate` ratifies 1 V/µs, so the cell is **~3× short of the ratified
fast limit**.

#### The same window on a *falling* rail — and it is far narrower (#55)

Issue #55 root-caused `sim/por-brownout/`'s 0/81 failure to this same
mechanism, running the other way. On a brownout the rail falls, `PG` again
cannot follow, and `V_sg` — the overdrive on the whole PMOS mirror bank —
does not merely shrink but **inverts**: measured **776.2 mV pre-dip →
−74.4 mV** 8 µs into a 1 µs edge. The bank is driven fully off, every bias
derived from it dies, and (as on the rising edge) the settle comparator dies
with it, so `BIAS_OK` reads a **false valid** for the whole collapse.

The falling boundary is **much lower than the rising one**, and this is the
number that matters for [`por-brownout`](../spec/target-spec.md#por-brownout):

| Direction | Boundary (correct behaviour at or below) | Source |
| --- | --- | --- |
| Rising (`por-ramp-rate`) | **0.36 V/µs** | `sim/bias-core-designer-check/`, 81 points |
| Falling (`por-brownout`) | **3.40 mV/µs**, binds at `ss`/−40 °C/2.97 V (FAIL confirmed from 3.4795 mV/µs) | `sim/por-brownout-slew/`, full 81-point grid (#60) |

The ~31× asymmetry is expected rather than surprising: on a rising rail the
loop is driven toward *more* current and recovers by settling down onto its
operating point, while on a falling rail it is driven toward *less* and
recovers only by charging `PG` back up through a second stage that the
collapse has already starved. The falling boundary sits at roughly half this
document's own independently derived ~21 mV/µs `PG` slew capability, which is
the corroboration that the two are the same mechanism rather than two
coincidences.

Two consequences worth stating plainly:

- **The dip's depth is not what breaks it.** A dip to 2.30 V — above
  `vdd_ref90_v`'s 1.788 V worst case at every corner — fails identically to
  one at 1.0 V. The "below its own operating floor" caveat DR-005 wrote, and
  which `design/bias_core.md` inherited, names the wrong variable: the
  collapse is dynamic, not static.
- **Waiting does not help.** Held below VPOR↓,min for 5 ms at a 1 µs edge —
  500× `T_dip,min` — the loop never recovers while the rail stays down, so
  reset still never asserts. Only the *recovery* edge restarts it.

The boundary above was originally a **one-corner** number, not fit to ratify
against; [DR-011](../spec/decision-records/DR-011-brownout-falling-slew-limit.md)
recorded it as `[TBD-#60]` pending an 81-point characterization. #60's full
grid (`sim/por-brownout-slew/`) has since supplied that characterization:
the boundary binds at `ss`/−40 °C/2.97 V, PASS at every one of 81 corners
confirmed at 3.40 mV/µs and FAIL (that same corner, and its 3.30/3.63 V
siblings) confirmed from 3.4795 mV/µs — a knife-edge, non-monotonic
transition rather than a single clean threshold (see
`sim/por-brownout-slew/records/*-boundary.md`), so the ratified bound sits on
the safe side of the whole transition band rather than at a bisected
midpoint. The "why it cannot be fixed inside this cell's Iq budget"
arithmetic below applies unchanged — it is the same detector that would be
needed.

**The non-monotonic band's mechanism, root-caused (#74).** A follow-up
characterization — three additional full-grid rungs at 3.42/3.44/3.46 mV/µs
(the last one moving the earliest observed failure down from 3.4795 to
**3.46 mV/µs**, at `ss`/−40 °C/3.30 V) plus an event-timing control at the
binding corner family — confirms the transition-zone hypothesis above and
turns it into a concrete mechanism rather than an analogy. It is a race
between two things this same starved loop drives: the dip window (fixed by
the falling edge's own duration) and `por_output_chain`'s deglitch dwell
(`design/por_output_chain.md`), realized here not at its documented
1.86–8.88 µs ceiling but at whatever current survives a bias collapse that is
**still in progress** when `POR_RAW` trips — the near-boundary edge has not
finished falling, so the deglitch tail keeps losing current for hundreds of
microseconds after the decision instant, stretching the measured dwell to
several hundred microseconds and, in a few cases, past 1 ms. That is
materially slower than either `design/por_output_chain.md`'s own
IBIAS-envelope characterization or
[DR-011](../spec/decision-records/DR-011-brownout-falling-slew-limit.md)'s
control C (valid-low in 3.70–7.30 µs down to zero `IBIAS`) — neither of which
is contradicted, because both hold the rail static once collapsed, and this
regime never gets there before the window closes. Because the collapse
trajectory behind that race differs slightly with the starting supply
(a higher `vdd_val` buys a longer absolute edge for the same mV/µs), the
race's winner is not a function of slew rate alone: `ss`/−40 °C/3.30 V and
/3.63 V cross it at slightly different slews, which is the non-monotonicity
itself. Full data, the per-supply event timeline, and the "is it the solver"
check that rules out an integration artefact are in
[`sim/por-brownout-slew/records/20260802-134958-dd0cd60-transition-band.md`](../sim/por-brownout-slew/records/20260802-134958-dd0cd60-transition-band.md).
This does not touch the ratified 3.40 mV/µs bound — every PASS margin at or
below it is 108.7 µs or more, well clear of the band, which only opens at
3.46 mV/µs — and it is not a claim that `por_output_chain` is defective: its
own characterization and DR-011's control both stand for the static condition
they measured.

#### An intermediate falling-slew band with a different symptom (#61)

DR-011's Consequences section flagged, but deliberately left open, a second
falling-edge finding: at falling rates **slower** than the boundary above
(so `RESETn` does reach a valid low and the dip is not the DR-005-owned
below-`vdd_ref90_v` failure), `POR_RAW` can still assert at a rail **above**
`VPOR-uparrow,max` = 2.73 V — a spurious reset while the supply is still
comfortably inside the ratified operating range.
[DR-013](../spec/decision-records/DR-013-por-brownout-spurious-assert.md)
confirms this across the full 81-point grid, and it is pervasive rather than
a corner curiosity: **45/81 (56 %)** of corners fail at 7.67 mV/µs, **74/81
(91 %)** at 2.30 mV/µs, and even the control's own "correct" 0.77 mV/µs
reference point fails at **15/81 (19 %)** of corners — overwhelmingly
`−40 °C` combined with the two higher supplies. The assert rail **tracks
`VDD`** rather than sitting at a fixed absolute threshold: holding process
and temperature fixed and sweeping only supply, the 2.30 mV/µs branch's
assert rail sits within 9 mV of 160 mV below whichever `VDD` it started
from, while the supply itself moves by 660 mV across the grid's three
points — a ratiometric trip, not a threshold pinned to a device voltage.

The obvious candidate explanation — this section's own ramp-rate `VREF`
feedthrough coefficient, extended to a falling edge — **substantially closes
once corner- and direction-matched, though not completely**
([DR-025](../spec/decision-records/DR-025-bias-core-ramp-feedthrough-grid-and-dr013-recheck.md),
issue #208). DR-013's original check used the single ≈2.4 µs figure this
section used to quote, which "Ramp-rate feedthrough" above now shows was
wrong at every corner in the grid, applied with the rising-edge sign to a
falling event. Using the corner- and direction-matched coefficient instead —
**−30.7 µs** at `tt`/27 °C/3.30 V (schematic), not +2.4 µs — the predicted
`VREF` offset is **−235 mV** at the 7.67 mV/µs branch and **−71 mV** at the
2.30 mV/µs branch, against DR-013's own measured **−467 mV** and **−81 mV**:
within a factor of ~2 and within 13 % respectively, not one to two orders of
magnitude off, and now the **same sign** — `VREF` depressed in both the
prediction and the measurement. That resolves the "wrong order of magnitude"
and "wrong sign of the `VREF` offset" objections DR-013 raised.

**It does not resolve the separate paradox DR-013 also raised.** A depressed
`VREF` still predicts, via the static `VPOR-downarrow = VREF ·
(RTOP+RBOT+RHYS)/(RBOT+RHYS)` divider algebra in `design/por_comparator.md`,
a *lower* assert threshold — yet the assert rail measures *above*
`VPOR-uparrow,max`. That is a property of the comparator/divider's dynamic
response during a fast dip, not of this cell's own reference feedthrough,
and it remains unidentified — see DR-025.

### Not the same defect as `por-ramp-rate`'s release-edge chatter (issue #56)

`sim/por-ramp-rate/records/20260802-000004-32fbaa0.md`'s full-assembly sweep
also measures `RESETn` **chattering** (crossing its release threshold more
than once) at up to 60 of 81 points per rate, at all four tested rates
including the two slow ones (1 V/s, 10 V/s) where this section's slew-rate
argument does not apply. It was an open question whether that is this window
operating at smaller scale on a slow ramp, or a distinct effect. **It is
distinct, and it is not owned by this cell.** `sim/por-ramp-rate/control/`
traces the release path on a slow ramp and finds `VREF`/`BIAS_OK`/`POR_RAW`
each cross their threshold once, cleanly, well before `RESETn` starts
toggling — this cell is settled throughout the chatter window, and the
mechanism is ramp-rate independent (same window width a decade apart in
rate), the opposite signature from this section's slew-limited one.

**What it actually is** (
[DR-016](../spec/decision-records/DR-016-por-ramp-rate-chatter-release-latch.md),
superseding DR-015's narrower localisation): a relaxation loop through the
**shared `IBIAS` node**. `RESETn`'s release enables `temp_core`, whose mirror
diode joins the shared node and steps it down by ~34 mV; `por_output_chain`'s
nA starve references follow, walking its trip detector's decision point back
until `RESETn` re-asserts — which disables `temp_core` again. Cutting the
`RESETn` → `temp_core.EN` → `IBIAS` path in a control arm removes the chatter
without any device in `por_output_chain` changing. Fixed by a release latch
(`XMRLK`) inside `por_output_chain`; see
[`design/por_output_chain.md`, "The release-edge chatter"](por_output_chain.md#the-release-edge-chatter--a-relaxation-loop-through-the-shared-ibias-node-not-a-local-instability).

**This cell is implicated only as the shared node's owner, not as the
defect.** The ~34 mV step is the correct, expected behaviour of a sub-µA
mirror reference when a third diode load is switched onto it — the arithmetic
in [Why it cannot be fixed inside this cell's Iq budget](#why-it-cannot-be-fixed-inside-this-cells-iq-budget)
applies equally to any proposal to stiffen the node so the step goes away.
The defence belongs downstream, in whichever consumer's decision the step can
walk back.

### Why it cannot be fixed inside this cell's Iq budget

The obvious fix is a "core is starved" detector that does not depend on the
core's own bias — i.e. a rail-referenced reference current. There is no such
thing available in this PDK at this current level, and the arithmetic says
so rather than the intuition:

- The only rail-referenced element that costs nA is a subthreshold
  diode-connected MOS stack. The five-deep stack used for the kick measures
  **12.6 pA (ss/−40 °C) … 17.5 nA (ff/125 °C)** — a **1390:1** corner
  spread. A four-deep stack is worse (**19.8 pA … 181 nA**, 9100:1).
- For a detector that trips at a fixed fraction of the loop current, the
  reference must satisfy `k·I_min > S_max` (so it does not fire when the
  loop is healthy at its weakest corner) and `k·0.001·I_max < S_min` (so it
  *does* fire when the loop is parked at its strongest corner). With
  `I` spanning 8…25 nA per unit leg and `S` spanning 12.6 pA…17.5 nA, those
  two inequalities require `k > 2.19` and `k < 0.50` simultaneously. **No
  value of `k` exists.**
- A resistor is the corner-stable alternative (±25 %, not 1390:1), but a
  rail-referenced 20 nA needs ~150 MΩ, which is ~49 000 □ of `ppolyf_u_3k` —
  about **twice the entire `area` planning budget** for one bias element.
- The remedy that does work is **more amplifier current**: the slew problem
  scales directly with the second stage's drive, and a detector referenced
  to a 100 nA-class rail current is buildable. That is exactly the budget
  [`por-iq`](../spec/target-spec.md#por-iq) has already run out of.

**So this is an architecture-level tension between two ratified rows**, not a
sizing miss: `por-iq` (originally <1 µA) and `por-ramp-rate`'s 1 V/µs fast
limit cannot both be met by a bandgap-referenced always-on core in gf180mcu
at this scale, **for the incremental Iq a rail-referenced starve detector
would need on top of what the cell already draws**. `target-spec.md` §5
already withdrew the <0.3 µA stretch with the words "requires architecture
revision"; this is the same finding one row further out. Resolving it is a
decision-record question for #1/#14, and the options are:

1. **Re-cost `por-iq`** upward (the §5 mechanism, and see
   [Iq apportionment](#iq-apportionment) — the row is already missed by 2.3×
   for unrelated reasons). **Partially taken by
   [DR-018](../spec/decision-records/DR-018-por-iq-recost.md)**: it re-costs
   `por-iq` to <3.0 µA, which covers the "unrelated reasons" apportionment
   overrun above (2371 nA measured, 20.5 % margin under the new ceiling) —
   but DR-018 explicitly does **not** fold in any additional current for a
   rail-referenced starve detector, because none has been designed or built.
   Whether the ~615 nA of headroom DR-018 leaves at the binding corner
   (3000 − 2385 nA) is enough for that detector, or whether `por-iq` would
   need a further re-cost to afford one, remains open — see DR-018's
   Consequences and the still-open starved-loop window below.
2. **Re-cost `por-ramp-rate`**'s fast limit down to the measured 0.36 V/µs.
   Still open; DR-018 explicitly declines to take this option (see that
   record's "Alternatives considered" — recasting the ramp-rate row, on its
   own, would not reduce the currently-measured `por-iq` by any amount, since
   no detector current is in that measurement today).
3. **Change the architecture.** ~~E.g. a `RESETn`-gated `IBIAS` (see below),
   which frees ~1 µA of budget that could be spent on amplifier drive.~~
   **That particular architecture change is now ruled out**: DR-010 rejects a
   `RESETn`-gated `IBIAS` because `por_comparator` and `por_output_chain`
   consume `IBIAS` precisely while `RESETn` is asserted, so gating it there
   would starve the POR decision itself. The ~1 µA it appeared to free is the
   current that biases them. Some other architecture change may still do it;
   this one does not.

Nothing here relaxes either row to make the result pass. The static
apportionment overrun (why `por-iq` misses regardless of ramp-rate) is closed
by DR-018; the starved-loop window itself (why a fast ramp or brownout can
read a false-valid `BIAS_OK`) is not, and remains open for a future decision
record.

## Iq apportionment

[`por-iq`](../spec/target-spec.md#por-iq) is **< 3.0 µA** (re-costed from
< 1 µA by [DR-018](../spec/decision-records/DR-018-por-iq-recost.md) — this
section is the apportionment that record's margin arithmetic is built on),
quoted with `RESETn` asserted and the temperature sensor disabled, and per §5
rule 1 it includes *every* branch that must conduct for the POR threshold
decision in that state. `bias_core` has no enable and no off state, so **its
entire supply current is that contribution** — there is no share to argue
about.

Measured over the 81-point grid:

| | Minimum | Maximum (binding corner) |
| --- | --- | --- |
| `bias_core` total (`iq_por_ua`) | **0.541 µA** (`ss_-40c_2.97v`) | **2.047 µA** (`ff_125c_3.63v`) |
| of which leaves through `IBIAS` (`ibias_na`) | 297 nA | **1119 nA** |
| `bias_core`'s own core (`iq_own_ua`) | 244 nA | **929 nA** |

**Cross-reference (#199).** `design/por_output_chain.md`'s "Hand-off to #11"
states the `IBIAS` window that cell can tolerate without a resize —
0.44×–4.7× nominal — and issue #199 asks whether this cell's actual output
falls inside it. It does, on the evidence already in this table: `ibias_na`'s
post-layout minimum/maximum
([`sim/bias-core-designer-check/records/20260811-123635-eb0f4ef.md`](../sim/bias-core-designer-check/records/20260811-123635-eb0f4ef.md),
297.089 / 1117.85 nA) are **0.594× / 2.236×** nominal, both inside that
envelope with margin on each side. No change follows for this cell; see
`design/por_output_chain.md`, "#199: the two hand-offs, answered", for the
full corner-matched comparison.

At the binding corner **FF / +125 °C / 3.63 V**, which is exactly the corner
the `por-iq` row names:

| Item | Current | Source |
| --- | ---: | --- |
| `bias_core` core (3 legs, amplifier, `PB` rail, settle comparator, startup stack) | 929 nA | measured `iq_own_ua` |
| `bias_core`'s `IBIAS` output leg | 1119 nA | measured `ibias_na` |
| **`bias_core` total** | **2047 nA** | measured `iq_por_ua` |
| `por_comparator` own draw | 292 nA | `design/por_comparator.md`, measured `iq_own_ua` |
| `por_output_chain` own draw, `RESETn` asserted | 31.6 nA | `design/por_output_chain.md` (#12, closed), measured `iq_asserted_1x_na` |
| **Total against `por-iq` (withdrawn <1 µA budget)** | **2371 nA** | **2.37× over the withdrawn budget**, all three contributors now designed and measured |
| **Total against `por-iq` (current <3.0 µA budget, [DR-018](../spec/decision-records/DR-018-por-iq-recost.md))** | **2371 nA** | **79 % of the re-costed budget** — matches the full-assembly measured 2371–2385 nA at this corner to within 0.6 %, and clears the ceiling with the 20.5 % margin DR-018's arithmetic requires |

`por_comparator`'s record quotes 792 nA against this row, of which 500 nA was
an *idealised* `IBIAS` source standing in for this cell. Summing the two
records naively would double-count it; the table above adds `bias_core`'s
real total to `por_comparator`'s **own** 292 nA, which is the
non-double-counted number.

**Where it goes, and what would have to change.**

- **The 0.5 µA `IBIAS` convention is the single largest line item.** At the
  binding corner it is 1119 nA — **more than the entire `por-iq` budget on
  its own**, before any other branch conducts. In the reset-asserted state
  most of it is still *unused*: `por_comparator` divides it 20:1 down to a
  25 nA tail, and `temp_core` — the consumer that actually wants 0.5 µA — is
  disabled. Since DR-010 it is at least no longer *thrown away*: `temp_core`'s
  clamp is gone, so what the POR path does not use now sits on the shared
  node rather than being shorted to `VSS` (see
  [The shared IBIAS net](#the-shared-ibias-net-–-resolved-by-dr-010)). The
  supply current is the same either way — this is a wasted-headroom argument,
  not a saving.
- **`bias_core` cannot fix that on its own, and must not try.** The cell has
  **no input pins at all**: it cannot know whether POR has released, so it
  cannot source 100 nA before release and 500 nA after. That was an interface
  change and therefore a decision record rather than a #11 edit — and the
  record went the other way: **DR-010 rejects it outright**, because
  `por_comparator` and `por_output_chain` need `IBIAS` in exactly the
  `RESETn`-asserted window such a gate would switch it off in. Treat the
  ~1 µA as unrecoverable by this route.
- **Even a free `IBIAS` would not have closed the gap against the withdrawn
  1 µA budget**: 929 nA of core + 292 nA of comparator + 31.6 nA of
  `por_output_chain` = 1252.6 nA, still over that number. It comfortably
  clears the current 3.0 µA budget, but that is not the same claim — the
  1119 nA `IBIAS` leg is not free, and this arithmetic does not by itself
  justify spending it; it only shows that *even in the impossible case where
  it cost nothing*, the pre-DR-018 target could not have been hit without
  design work elsewhere too.
- **The core is already 10–50× below DR-005's own 1–5 µA/branch estimate.**
  Halving it again costs resistor area quadratically (`R2` would grow to
  12.6 MΩ, ~16 400 µm² of poly on its own) and slows the loop further, which
  makes [The starved-loop window](#the-starved-loop-window) worse.
- **Roughly 40 % of the total is temperature and resistor corner, not
  design.** `I = ΔV_EB/R1` with a −1545 ppm/°C `ppolyf_u_3k` `R1` is
  *super*-PTAT: the same cell measures 0.541 µA at `ss`/−40 °C and 2.047 µA
  at `ff`/125 °C. A lower-TC flavour would flatten it at ~8.5× the area.

**This is the re-cost `target-spec.md` §5 assigned to #11 and #1, and it has
now been taken**: [DR-018](../spec/decision-records/DR-018-por-iq-recost.md)
re-costs `por-iq` to < 3.0 µA — 20.5 % margin over the measured 2.385 µA
worst case, confirmed on both the schematic and post-layout netlists — rather
than relaxing the arithmetic to fit the withdrawn number. `sim/`'s own check
files are unchanged by that record (it is a spec decision, not a simulation
re-run): `sim/bias-core-designer-check/testbench/tb.json` is left at the
pre-DR-018 1.0 µA bound and its own record still reads FAIL at 38 of 81
points against *that* check — a mechanical follow-up to move the various
`tb.json` `por-iq`/`iq-total` bounds onto the current 3.0 µA ceiling is noted
as open work in DR-018's Consequences.

## The shared `IBIAS` net — resolved by DR-010

`design/netlist/temp_por_top.spice` wires `IBIAS` as a **single net** shared
by `bias_core`, `temp_core`, `por_comparator` and `por_output_chain`. DR-005
startup ordering step 6 holds `temp_core` disabled until POR releases, and
`temp_core`'s disabled state used to clamp the `IBIAS` **pin** to `VSS`
through an `ENB`-gated `XMDIB`.

That was worse than a current-budget problem. `sim/bias-core-ibias-sharing/`
instantiates the real cells in the real top-level wiring and compares them
against a control without `temp_core`, and in record
`20260801-054722-6cf5898` (the netlist as of #11):

- **Control** (no `temp_core`): the shared node sat at a diode drop,
  `por_comparator`'s tail mirror was biased, and `POR_RAW` released at a rail
  well above every corner's threshold — which is also the first evidence
  that `bias_core`'s real `IBIAS`/`VREF`/`BIAS_OK` reproduce what
  `sim/por-comparator-designer-check` obtained from idealised stimuli.
- **Real wiring** (disabled `temp_core` present): the clamp held the shared
  node at **1.0–6.6 mV** whatever `bias_core` sourced into it,
  `por_comparator`'s tail was starved, `POR_RAW` could not go high, `RESETn`
  was never released, and `temp_core` was therefore never enabled. **A closed
  bias-vs-POR lockup loop** — precisely the failure #11 was chartered to
  prove absent.

`VREF` was unaffected in both branches (the reference loop is self-biased and
does not depend on the `IBIAS` leg's compliance), which is what identified
this as an interface defect on one net rather than a failure of the core.

### What was decided

The fix touched a cell #11 could not modify — `temp_core`'s `XMDIB` gating and
the `IBIAS` interface contract itself — so it went to a decision record, which
is [DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md)
(issue #41). **A consumer of the shared `IBIAS` net presents high impedance to
it whenever it is disabled**: it may gate its own internal fan-out off the
node, never clamp it. `temp_core`'s `XMDIB` is deleted; the node's operating
point is defined by `por_output_chain`'s always-on diode-connected `XMBD`.

Of the three candidates this section originally listed, DR-010 records why the
other two were rejected — briefly, because **gating `bias_core`'s own `IBIAS`
output on `RESETn`** (the one credited above with recovering ~1 µA of `por-iq`)
would starve `por_comparator` and `por_output_chain` in exactly the window
they exist to work in, turning a lockup a clamp happened to cause into one the
interface would guarantee; and **splitting `IBIAS` into two nets** would add a
second permanently-conducting output leg to a block already 2.37× over
`por-iq`. Read DR-010 before revisiting either.

### Measured after the fix

Same testbench, same 81-point grid, record `20260801-073555-8b7e57f`
(**PASS**, all six checks, including the two that were written as the
requirement and had been failing):

| | Before (`…-6cf5898`) | After (`…-8b7e57f`) |
| --- | --- | --- |
| `vibias_shared_v` (disabled `temp_core` present) | 1.0–6.6 mV | **0.568–0.861 V** |
| `vibias_control_v` (no `temp_core`) | 0.568–0.861 V | 0.568–0.861 V |
| shared vs. control agreement | ~0.6 V apart | **≤ 3 µV apart** |
| `por_raw_shared_droop_mv` | pinned low | **≤ 0.005 mV** from the rail |

And on the **full four-cell assembly** — `sim/temp-por-top-release/`, record
`20260802-205904-bdc077d` (re-run on the post-#56 assembly;
`20260801-074334-8b7e57f`, the first corner record taken on `temp_por_top` as
a whole, measured it before `XMRLK`):

| | Result, 81 points |
| --- | --- |
| `RESETn` releases | **at every point**, 5.61–16.95 ms |
| `PTAT` after release | **1.003–1.716 V** — the sensor really is enabled |
| shared `IBIAS`, reset asserted | 0.507–0.821 V |
| shared `IBIAS`, reset **released** | 0.460–0.793 V — **lower at every point** |
| `iq_por_ua` vs. [`por-iq`](../spec/target-spec.md#por-iq) | **0.657–2.385 µA** — against the withdrawn <1 µA budget, FAILS at 54 of 81 points; against the current [DR-018](../spec/decision-records/DR-018-por-iq-recost.md)-recosted **<3.0 µA budget, PASSES at 81 of 81** |

The released row is not a rounding difference and it is not new data — it has
been in this record since the row was added — but issue #56 is what gave it a
meaning. Releasing `RESETn` **enables `temp_core`**, whose mirror diode joins
this node, so the same source current splits one more way and the node's
operating point steps **down** by tens of millivolts (−36 mV on the means
here; −34.4 mV measured directly at `tt`/27 °C in
`sim/por-ramp-rate/control/`). Every nA-biased decision hanging off this node
moves with that step. That is the **dynamic** half of
[DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md)'s
shared-node contract, added by
[DR-016](../spec/decision-records/DR-016-por-ramp-rate-chatter-release-latch.md):
DR-010 required a disabled consumer to present high impedance; DR-016 adds
that *switching* a consumer moves the node, and that a downstream decision the
node can walk back must be latched rather than left standing.

> **How much current each consumer actually gets — measured (issue #221,
> [DR-024](../spec/decision-records/DR-024-por-output-chain-real-ibias-delivery.md)).**
> The rows above report the shared node's **voltage**; they say nothing about
> how the source current divides between the consumer diodes hanging off it,
> and no committed testbench measured that until #221.
> [`sim/por-output-chain-ibias-sharing/`](../sim/por-output-chain-ibias-sharing/)
> splices all four cells with a zero-volt ammeter on *each* `IBIAS` pin and
> reports the split leg-by-leg, 81 points, both `RESETn` states, both netlist
> levels. `por_output_chain`'s share is **0.344×–1.155× the 0.5 µA convention
> asserted, 0.182×–0.608× released** — under the ≥0.44× floor
> `design/por_output_chain.md` needs at 61 of 81 points in the released state.
> **This is not a `bias_core` magnitude miss**: this cell's own output leg is
> in spec (297–1119 nA, `sim/bias-core-designer-check/`); the shortfall is the
> division. DR-024 shows with arithmetic that scaling `XMPIB` — or adding the
> per-consumer second output leg DR-010 rejected — cannot clear 220 nA cold
> without breaking DR-018's 3.0 µA `por-iq` ceiling hot, because this
> reference current's own 3.77× hot/cold ratio is worse than the ratio the
> budget's headroom can absorb. **Nothing in this cell changes on that
> evidence**; the remaining levers are routed to
> [#235](https://github.com/2AMLogic/gf180-temp-por/issues/235) and
> [#236](https://github.com/2AMLogic/gf180-temp-por/issues/236).

That last row is the *other* conflict this document already owns (see
[Iq apportionment](#iq-apportionment)), now measured on the real assembly
instead of summed across per-cell records. DR-010 fixed a **liveness** defect
and does not touch it; per
[DR-018](../spec/decision-records/DR-018-por-iq-recost.md) `por-iq` is now
re-costed to <3.0 µA and this row is met (see above) rather than relaxed to
pass — the withdrawn 1.0 µA figure quoted here is the ceiling this record
measured *against*, not the current ratified target.

## Area — flagged for #17

Not a target this issue owns ([`area`](../spec/target-spec.md#area) is
`[TBD-#17]` with a ≤ 0.05 mm² wave-1 planning budget), but the number
matters because `por_comparator` already flagged the same pressure:

- Drawn poly here: 5487.5 µm × 2 µm = **10 975 µm²**, plus **436 µm²** of MIM
  (`CC` 20 × 20 µm, `COK` 6 × 6 µm).
- With `por_comparator`'s 30 883 µm² of divider poly that is **~42 300 µm²**,
  i.e. **~85 % of the whole block's planning budget for two sub-cells**,
  before `temp_core`, before #12, and before serpentine-folding overhead.
- The same lever `design/por_comparator.md` identifies applies here and is
  quadratic: at fixed R, area scales as W². Redrawing this cell's string at
  W = 1 µm gives identical resistances and identical ratios for ~1/4 the
  area. It is kept at W = 2 µm here to match the geometry `sim/devchar`
  characterised and `por_comparator`'s convention, so the electrical
  evidence rests on characterised ground. The width decision belongs with
  #17's floorplan and #15's mismatch data.

## Layout — partially drawn (#68)

The MOS portion of this cell is drawn and verified:
[`layout/cells/bias_core.gds`](../layout/cells/bias_core.gds), with the
recorded DRC/extract/LVS reports under
[`layout/reports/bias_core/`](../layout/reports/bias_core/). All **34** MOS
devices in the table above are present, DRC-clean against `klt`'s curated
`gf180mcu` deck, and LVS-clean (34/34 devices, 26/26 nets, 6/6 pins) against a
reference derived mechanically from `design/netlist/bias_core.spice` — so every
`W`/`L` in this document that belongs to a MOS device is now compared against
drawn polygons rather than only simulated.

**Nothing above about the passive and bipolar devices is checked by that run.**
The 10 vertical PNPs (`XQ1`, `XQ8A..H`, `XQR`), the 4 poly resistors (`R1`,
`R2`, `RT`, `RZ`) and the 2 MiM caps (`CC`, `COK`) are outside the deck's
device coverage (klayout-tools#219/#222) and are deliberately **not drawn** —
their area is reserved in the layout as a floorplan rectangle instead. So the
8:1 emitter ratio, the `R2/R1` = 11.726 ratio and the `RT` 5 % tap remain
schematic-and-simulation claims only, and the poly area flagged in
[Area](#area--flagged-for-17) is a computed figure, not a drawn one.
[`layout/README.md`](../layout/README.md) § "The cells under test" states the
full boundary; the guard ring and well ties drawn there are a design-review
claim, not a checked one (klayout-tools#281).

## Reproducing the evidence

```bash
bash layout/run_checks.sh bias_core          # DRC/LVS on the drawn MOS portion
python3 design/netlist.py --check            # schematic <-> committed netlist
python3 sim/build_tb.py --check              # netlist <-> testbench fragment
python3 sim/run_corners.py bias-core-designer-check --timeout 7200
python3 sim/run_corners.py bias-core-ibias-sharing  --timeout 900
python3 sim/run_corners.py temp-por-top-release     --timeout 1800
python3 sim/run_corners.py bias-core-startup        --timeout 900
python3 sim/bias-core-startup/control/run_gmin_control.py
python3 sim/bias-core-startup/control/run_ok_dip_decay.py
python3 sim/bias-core-designer-check/control/run_starved_window.py
```

Append `/testbench-postlayout` to any of the first four slugs to re-run it
against the klt-extracted netlist instead of the schematic export — see
[Post-layout re-run](#post-layout-re-run-issue-84).

`bias-core-designer-check`'s timeout is 7200 s rather than the 900 s the
other slugs use because #185 lengthened its transient from 2 ms to 30 ms so
that the deck is longer than the starved-loop window it measures (see
[that section](#the-post-layout-brownout-regression--it-was-the-deck-issue-185)).
Budget roughly 30–40 CPU-seconds per corner point.

The last three lines are control experiments, and the first of them is the
`gmin` one behind
[Resolved](#resolved-the-bias_ok-quasi-static-failure-was-a-testbench-artefact-issues-43-46):
two `op` runs of one deck, seconds rather than minutes. It resolves the PDK
through the same `sim/harness` the corner runner uses, so it needs no
`source sim/env.sh` and no hand-assembled deck, and it rewrites
`sim/bias-core-startup/control/{decks,logs}/` and
[`control/results.md`](../sim/bias-core-startup/control/results.md) in place —
which is deliberate and is why a control is not a record: it makes no claim,
so there is nothing for the append-only rule to protect (`sim/README.md`,
"Control experiments"). Every number in
[The controlled experiment](#the-controlled-experiment) is transcribed from
that `results.md`.

The other two are #185's, and follow the same rules: `run_ok_dip_decay.py`
samples `BIAS_OK`'s dead-rail discharge as a curve on both netlists
([`dip_results.md`](../sim/bias-core-startup/control/dip_results.md), four
short transients), and `run_starved_window.py` takes the anatomy of the
superseded 2 ms brownout branch plus a 120 ms latch test at the corners the
30 ms deck does not clear
([`results.md`](../sim/bias-core-designer-check/control/results.md), the
slower of the two). Every number in
[The post-layout brownout regression](#the-post-layout-brownout-regression--it-was-the-deck-issue-185)
is transcribed from those two files.

Exit codes, and why each is what it is:

| Run | Exit | Why |
| --- | --- | --- |
| `bias-core-designer-check` | **non-zero** | `por-iq` (against `tb.json`'s own pre-[DR-018](../spec/decision-records/DR-018-por-iq-recost.md) 1.0 µA check bound — not yet moved to the current 3.0 µA target, see that record's Consequences) and the starved-loop window, the two conflicts above. Unchanged. |
| `bias-core-ibias-sharing` | **zero** | was non-zero before DR-010; its two requirement-shaped checks went green by themselves when the interface was corrected, exactly as its `tb.json` said they would |
| `temp-por-top-release` | **non-zero** | `por-iq` again, now measured on the assembled block, against `tb.json`'s own unmoved 1.0 µA check bound (met against the current 3.0 µA target — see [DR-018](../spec/decision-records/DR-018-por-iq-recost.md)). Every liveness and startup-ordering check in it passes. |
| `bias-core-startup` | **zero** | was non-zero (`error`) while the experiment was a `gmin`-aided `.dc` sweep. Re-founded on a quasi-static transient by #46 and now **PASS at all 81 points** — see [Resolved](#resolved-the-bias_ok-quasi-static-failure-was-a-testbench-artefact-issues-43-46). |

`sim/` is append-only, so a re-run mints a new record id and does not
overwrite the committed ones.

## Out of scope here, on purpose

| Not here | Where |
| --- | --- |
| Mismatch / Monte Carlo on the 8:1 ratio, `R2/R1` and the amplifier offset — **plus the settle comparator's input pair and load mirror, whose 2.1–3.6 mV signal makes it the block's most offset-sensitive stage** | #15 |
| Ramp-rate envelope, brownout re-assertion and reset-pulse interaction on the assembled block | #14 |
| Deglitch, the ≥1 ms one-shot, push-pull drive, the below-floor `RESETn` pull-down | `por_output_chain`, #12 |
| Re-costing `por-iq`'s static apportionment overrun | **done**: [DR-018](../spec/decision-records/DR-018-por-iq-recost.md), issue #189 — <1 µA to <3.0 µA |
| Re-costing `por-ramp-rate`, or affording the starved-loop window's rail-referenced detector | a new decision record through #1 — still open |
| The `IBIAS` interface change | **done**: [DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md), issue #41 |
| Matching strategy for the whole block, measured area | #17 |
| Drawing the PNPs, poly resistors and MiM caps — blocked on the extraction deck growing non-MOS device coverage (klayout-tools#219/#222) | see [Layout](#layout--partially-drawn-68) |
| ~~`BIAS_OK` transient cross-check, root-cause and fix~~ | **done**: #46 — root-caused to the testbench's `gmin` aid, re-founded on a quasi-static transient, 81/81 PASS, no schematic change. See [Resolved](#resolved-the-bias_ok-quasi-static-failure-was-a-testbench-artefact-issues-43-46). |

## Post-layout re-run (issue #84)

Everything above is against the schematic export
(`design/netlist/bias_core.spice`). Issue #84 re-ran the three
`bias_core`-domain testbenches against the real klt-extracted netlist —
`layout/postlayout/bias_core.spice` (and, for `bias-core-ibias-sharing`'s
three-way splice, `layout/postlayout/{temp_core,por_comparator}.spice` too)
— produced by #82/PR #180's direct-extraction flow, **not** the
composite-splice approach `bias_core`'s own layout history first assumed
(PR #94, closed unused). Per
[`layout/postlayout/AUDIT.md`](../layout/postlayout/AUDIT.md), `bias_core`'s
extraction has **no remaining ideal device**: all 70 devices are drawn,
including the 10 vertical PNPs, the 4 poly resistors and the 2 MiM caps that
the [Layout](#layout--partially-drawn-68) section above still describes as
reserved-but-undrawn floorplan area — that section is unchanged here (it is
`design/netlist.py`/`layout/run_checks.sh`'s scope, not this issue's), but
the post-layout evidence below already reflects the fully-drawn cell. Each
new run inlines a sibling `testbench-postlayout/` fragment — a
`POSTLAYOUT_FRAGMENTS` entry in `sim/build_tb.py`, the same mechanism #86
established for the POR output chain — beside the existing schematic-level
`testbench/`, so none of the schematic-level records above are touched.

These three runs pre-dated the reconciliation onto that shared mechanism, so
each fragment's `* Regenerate with:` comment line was rewritten afterwards
(from a since-removed `--postlayout <slug>` invocation to the plain
`python3 sim/build_tb.py` the dict-driven builder emits). That comment is the
**only** line that differs between the committed fragment and the frozen
`netlist-snapshots/<record-id>.spice` each record cites: every SPICE card —
stimulus, DUT, sha256-attributed sources — is byte-identical, so the results
below are the results of the netlist the snapshots freeze and were not
re-simulated.

| Evidence (`Netlist provenance: extracted`) | Result | vs. schematic baseline |
| --- | --- | --- |
| [`sim/bias-core-designer-check/records/20260811-123635-eb0f4ef.md`](../sim/bias-core-designer-check/records/20260811-123635-eb0f4ef.md) | FAIL (as expected — see below) | **regressed**: two new failure modes, see #185 |
| [`sim/bias-core-startup/records/20260811-125228-e403f89.md`](../sim/bias-core-startup/records/20260811-125228-e403f89.md) | FAIL | **regressed**: one new marginal failure, see #185 |
| [`sim/bias-core-ibias-sharing/records/20260811-060715-5ff219c.md`](../sim/bias-core-ibias-sharing/records/20260811-060715-5ff219c.md) | PASS, 81/81 | unchanged — matches [`sim/bias-core-ibias-sharing/records/20260801-152327-b72c10c.md`](../sim/bias-core-ibias-sharing/records/20260801-152327-b72c10c.md) |

The designer-check and startup rows above cite clean-tree re-runs rather than
this cell's first post-layout pass: `20260811-063744-5ff219c` and
`20260811-062115-5ff219c` were both minted against uncommitted work and are
each their experiment's *sole* post-layout evidence, so a stamped-only
citation was not an option here per `sim/README.md`'s citation policy.
`20260811-123635-eb0f4ef` and `20260811-125228-e403f89` reproduce their
numbers exactly on a clean tree — see
[#209](https://github.com/2AMLogic/gf180-temp-por/issues/209).

`bias-core-designer-check`'s two documented, on-purpose failures reproduce
**unchanged**: `iq_por_ua` (38/81 points, [Iq apportionment](#iq-apportionment))
and the starved-loop window's `t_false_ok_fast_us` /
`t_false_ok_brownout_us` / `t_false_ok_slow_us` (81, 81 and 3 points
respectively — the same count as the schematic record, at the same
corners). Real interconnect parasitics do not change either conclusion.

**Two checks regress, and are routed to #185 rather than resolved here** —
#84's scope is an honest re-run, not a redesign. **#185 has since resolved
all three bullets below**; each is annotated with its outcome, and the
reasoning is in
[The post-layout brownout regression](#the-post-layout-brownout-regression--it-was-the-deck-issue-185):

- `bo_deep_ppm` / `bo_shallow_ppm` (post-brownout `VREF` reproducibility,
  ±500 ppm bound) go from 2/2 failing corners at schematic level to 21/12
  under extraction — the same handful of extreme cold/fast-process corners
  that were already marginal, now pushed further out by real parasitic
  loading on the recovery path.
  **#185 outcome: measurement window.** Both sample instants sat inside the
  starved-loop window under real parasitics. On the 30 ms deck they read
  12/81 → **0/81** and 21/81 → **1/81** failing, and the one remaining corner
  is measured recovering (to 0.000 ppm) at 30.95 ms rather than latched.
- `ok_bo_end_droop_mv` (`BIAS_OK` droop 390 µs after a full rail collapse,
  20 mV bound) is a **new failure mode**: 0 failing corners at schematic
  level, 3 under extraction (`tt_27c_3.63v`, `ss_27c_3.63v`,
  `bjt_ff_27c_3.63v`), with droop up to 3630 mV — `BIAS_OK` is not settling
  back to a hard high in the sampled window at those points.
  **#185 outcome: measurement window, and the sharpest case of it.** At
  `tt_27c_3.63v` the 1.95 ms sample lands in a 113 µs notch during which
  `BIAS_OK` is *correctly* low, mid-recovery, and is back at the rail 49 µs
  later. 3/81 → **1/81** on the 30 ms deck.
- `bias-core-startup`'s `ok_bo_dip_mv` (`BIAS_OK` absolute level mid-collapse,
  ±300 mV bound) goes from 0 failing corners (schematic) to 3
  (`ss_-40c_2.97v` / `_3.30v` / `_3.63v`, 303.432 mV vs. the 300 mV bound —
  was 33.6 mV pre-extraction): a real, if marginal (~1.1 %), shift.
  **#185 outcome: genuinely the cell, and it is an RC rather than a latch.**
  The extracted `BIAS_OK`/`NOKX` net's dead-rail discharge is ~9× slower and
  monotonic; the physically load-bearing requirement (below `nfet_03v3` Vt,
  ≈0.822 V at these corners) still holds by 2.7×. The bound is **not moved**
  and the check still reads FAIL — whether it should be harmonized with this
  cell's other deck, which bounds the same quantity at 500 mV, is left to #1.

`bias-core-ibias-sharing`'s shared `IBIAS`/`VREF` distribution — the
[DR-010](#the-shared-ibias-net--resolved-by-dr-010) contract this issue's
Watch item asked to be re-checked under real parasitic loading — holds:
81/81 PASS, no regression on any of its checks (including the two that used
to be the design-defect checks pre-DR-010; see the updated
`sim/bias-core-ibias-sharing/testbench-postlayout/tb.json` check
descriptions for why those no longer read as "expected to fail").

## The post-layout brownout regression — it was the deck (issue #185)

Issue #185 took the four checks the table above routes to it and asked the
only question that matters about a regression on an extracted netlist: is
the *cell* worse, or is the *measurement* wrong? Three of the four are the
measurement; the fourth is genuinely the cell. Neither answer is a reason to
change `design/bias_core.sch`, and no ratified bound moved.

Evidence minted for this issue, all on the replacement 30 ms deck:

| Record | Provenance | Result |
| --- | --- | --- |
| [`sim/bias-core-designer-check/records/20260811-114539-9fcede8.md`](../sim/bias-core-designer-check/records/20260811-114539-9fcede8.md) | `extracted` | FAIL — `iq_por_ua` 38/81 and the starved-loop window, both on purpose; `t_bo_recover_us` 34/81 newly visible; `bo_deep_ppm` / `ok_bo_end_droop_mv` 1/81 |
| [`sim/bias-core-designer-check/records/20260811-114349-9fcede8.md`](../sim/bias-core-designer-check/records/20260811-114349-9fcede8.md) | `schematic` | FAIL — the same two on-purpose failures; `t_bo_recover_us` 2/81 newly visible; `bo_*_ppm` and `ok_bo_end_droop_mv` **0/81** |
| [`sim/bias-core-designer-check/control/results.md`](../sim/bias-core-designer-check/control/results.md) | control | anatomy of the superseded deck + the 120 ms latch test |
| [`sim/bias-core-startup/control/dip_results.md`](../sim/bias-core-startup/control/dip_results.md) | control | `BIAS_OK`'s dead-rail discharge curve, both netlists |

**Provenance caveat on the two 30 ms records** (per `sim/README.md`,
"Citing a 'taken against a dirty working tree' record", and
[#209](https://github.com/2AMLogic/gf180-temp-por/issues/209)): both
`20260811-114539-9fcede8` and `20260811-114349-9fcede8` were minted against
an uncommitted working tree and carry the harness's *"not citable as a
clean-tree result"* stamp in their own **Netlist provenance** field. The
direction-of-change conclusions this section draws from them — which checks
stop failing, which start telling the truth, and that the schematic and
extracted netlists move the same way — are citable as they stand. The precise
30 ms figures quoted below are not yet clean-tree numbers; no ratified bound
was moved on them, and no clean-tree successor exists yet because this deck
is a 30 ms × 81-point transient rather than one of the cheap per-cell decks
#209 re-ran.

`sim/bias-core-startup/` and `sim/bias-core-ibias-sharing/` are untouched by
this issue — no testbench and no DUT netlist under either of them changed —
so their post-layout records
([`20260811-125228-e403f89`](../sim/bias-core-startup/records/20260811-125228-e403f89.md),
[`20260811-060715-5ff219c`](../sim/bias-core-ibias-sharing/records/20260811-060715-5ff219c.md),
the latter 81/81 PASS) stand as taken.

### Three of the four checks were one bug, and it was in the testbench

`bo_shallow_ppm`, `bo_deep_ppm` and `ok_bo_end_droop_mv` are all **fixed
wall-clock samples** on a 2 ms transient — 940 µs, 1.95 ms, 1.95 ms. What
they have in common is not a circuit node; it is that under real parasitics
each of those instants moved from *after* this cell's own starved-loop
window to *inside* it. **The 2 ms deck was shorter than the phenomenon it
was measuring**, and three other numbers in the same record say so
independently, before any new simulation is run:

| Symptom in record [`20260811-123635-eb0f4ef`](../sim/bias-core-designer-check/records/20260811-123635-eb0f4ef.md) | What it means |
| --- | --- |
| `t_bo_recover_us` **negative at 34 of 81 points** (down to −6.136 µs) | A recovery that completes *before the rail returns* is impossible. `when v(bias_okb)=1.4 rise=last` had no genuine post-collapse crossing inside 2 ms to find, so it returned the capacitive blip `BIAS_OK` makes while the rail's own 10 µs return ramp drags the high-impedance node up through 1.4 V. The check was reporting a measurement failure as a PASS. |
| `t_false_ok_fast_us` **clustered at 1503–1988 µs at 14 points**, `t_false_ok_brownout_us` at 1508–1577 µs at 14 points | Saturation against the 0→2 ms integration window, not a measured duration. This document's own [starved-loop window](#the-starved-loop-window) section already recorded a **4.4 ms** parked window at `sf`/−40 °C — longer than the deck measuring it. |
| `bo_shallow_ppm` / `bo_deep_ppm` magnitudes near **−5·10⁵ ppm** | −500 000 ppm is `VREF` at *half* its settled value. That is not a reproducibility error at all; it is the reference still parked, sampled mid-recovery. |

[`sim/bias-core-designer-check/control/results.md`](../sim/bias-core-designer-check/control/results.md)
takes the anatomy directly, at `tt`/27 °C/3.63 V — one of the three corners
where `ok_bo_end_droop_mv` read 3630 mV — with the superseded serialized
brownout branch held long enough to run past the end of the recovery, and
with the DUT netlist as its only variable. Both netlists show the *same three
phases*; only their durations differ. Times below are relative to the rail
reaching full value at 1.110 ms, and the return ramp starts 10 µs before that:

| | schematic export | klt-extracted |
| --- | ---: | ---: |
| `BIAS_OK` dragged back above 1.4 V capacitively, on the rail's own return ramp — a **false** valid, because `VREF` is still parked | −6.1 µs | −6.1 µs |
| …stays falsely valid for | 69.7 µs | **777.9 µs** (11.2×) |
| …then correctly **de-asserts** at | +63.5 µs | **+771.8 µs** |
| `VREF` last more than 1 % from settled | +78.4 µs | **+790.9 µs** |
| …and `BIAS_OK` genuinely re-asserts at | +104.7 µs | **+884.4 µs** |
| `ok_bo_end_droop_mv` at the record's 1.95 ms sample | 0.075 mV | **3630 mV** |

The extracted cell is therefore **correctly low** from +771.8 µs to +884.4 µs
— a 113 µs notch while the settle detector holds the flag down and the loop
re-establishes itself — and **the record's 1.95 ms sample instant (+840 µs)
falls inside it.** The 3630 mV "droop" is `BIAS_OK` doing exactly its job at
that instant.

Nothing about the mechanism is new post-layout. The schematic export has the
same notch; it has simply come and gone long before 1.95 ms. What real
interconnect parasitics changed is the **time constant**, not the behaviour.

### What changed, and what deliberately did not

The fix is in `sim/bias-core-designer-check/testbench/`, and it makes the
grid *more* honest rather than less — two of the changes below add failures:

1. **The transient runs to 30 ms instead of 2 ms**, so
   `t_false_ok_fast_us` / `t_false_ok_brownout_us` stop saturating and
   `t_bo_recover_us` has a real edge to find. `t_bo_recover_us` accordingly
   stops reading impossible negative values and starts **failing** at the
   corners where recovery genuinely exceeds its 900 µs bound. Those failures
   are newly *visible*, not newly *caused*.
2. **The 0.5 V dip and the full collapse move onto separate DUTs.**
   Serialized, the dip parks the loop at the slow corners and it is *still*
   parked when the collapse arrives 400 µs later — so `bo_deep_ppm` was never
   measuring recovery from a collapse of a settled cell. Each branch now sees
   its event from the settled state and gets its own recovery window.
3. **The three post-event samples move to 29.9 ms**, past the starved window
   at most corners, so they measure the properties their own descriptions
   claim: reproducibility of the reference, and whether the flag re-arms to a
   hard rail-to-rail high.

A fourth change is small and worth stating on its own: **`t_bo_recover_us`
gains a `min` of 0 µs**. That is not a design bound — it is the guard that
stops the measurement from reporting its own failure as a PASS. A recovery
that completes before the rail returns is impossible, so a negative reading
means `rise=last` found no genuine post-collapse crossing at all; without the
floor, 34 of 81 such points read as comfortably inside the 900 µs bound.

**No bound was relaxed and no device changed.** 30 ms is deliberately *not*
long enough to make every corner pass: the control's Part B takes the same
event out to 120 ms at the corners the 30 ms deck does not clear and shows the
reference does come back there — to **0.000 ppm** of its pre-event value, i.e.
slowly, not never — so a `bo_*_ppm` that still fails at 29.9 ms is reporting a
recovery still in progress. (That control also cross-checks itself against the
graded deck: at `sf_-40c_3.30v` the two agree on `BIAS_OK`'s re-assert to
within 10 µs on a 26 ms measurement, so the one corner that still fails —
`sf_-40c_3.63v`, recovering at 30.95 ms — misses by a clear ~1 ms rather than
by rounding.) Extending the deck until the grid went green would have hidden
precisely the number `t_false_ok_brownout_us` exists to report.

### The result, on the same extracted netlist

Both columns are `Netlist provenance: extracted`, same PDK, same 81-point grid;
only the deck differs.

| check | 2 ms deck ([`20260811-123635-eb0f4ef`](../sim/bias-core-designer-check/records/20260811-123635-eb0f4ef.md)) | 30 ms deck (this issue) |
| --- | --- | --- |
| `bo_shallow_ppm` | **12/81 FAIL**, down to −6.54·10⁵ ppm | **0/81 FAIL**, whole grid 0…2.5 ppm |
| `bo_deep_ppm` | **21/81 FAIL**, down to −6.50·10⁵ ppm | **1/81 FAIL** (`sf_-40c_3.63v`), rest 0…0.83 ppm |
| `ok_bo_end_droop_mv` | **3/81 FAIL**, up to 3630 mV | **1/81 FAIL** (`sf_-40c_3.63v`), rest −0.074…0 mV |
| `t_bo_recover_us` | 0/81 FAIL — but 34 points read *impossible negative* values as PASS | **34/81 FAIL**: 21 genuinely over the 900 µs bound (up to 24.9 ms), 13 with no recovery edge inside 30 ms |
| `t_false_ok_brownout_us` | 81/81 FAIL, **saturated** at ≤1576.61 µs | 81/81 FAIL, unclipped: 359.267…**39866.3 µs** |
| `t_false_ok_fast_us` | 81/81 FAIL, **saturated** at ≤1988.49 µs | 81/81 FAIL, unclipped: 27.9902…**6584.96 µs** |
| `iq_por_ua` | 38/81 FAIL (on purpose) | 38/81 FAIL — unchanged |
| `t_false_ok_slow_us` | 3/81 FAIL (on purpose) | 3/81 FAIL — unchanged |
| every other check | PASS | PASS, with `vref_v` / `vref_op_v` / `t_settle_us` identical to six figures |

Read the two right-hand columns together and the shape of the fix is plain:
the three checks that had no business failing stop failing, and the two that
own the phenomenon start telling the truth about how big it is. The false-valid
window after a fast collapse is not the ≤1.58 ms the old deck could see; at
`sf`/−40 °C/3.63 V it is **39.9 ms**.

### The same deck change, re-run at schematic level — and the cleanest proof

The deck change was re-run against the schematic export too, so the two
provenances stay comparable and so the fix can be shown not to be
extraction-specific. It is not:

| check | 2 ms deck ([`20260801-150709-5a013e8`](../sim/bias-core-designer-check/records/20260801-150709-5a013e8.md)) | 30 ms deck (this issue) |
| --- | --- | --- |
| `bo_shallow_ppm` | 2/81 FAIL, down to −5.18·10⁵ ppm | **0/81 FAIL** |
| `bo_deep_ppm` | 2/81 FAIL, down to −5.03·10⁵ ppm | **0/81 FAIL** |
| `ok_bo_end_droop_mv` | 0/81, spread −2.141…3.889 mV | 0/81, spread **−0.048…0.022 mV** |
| `t_bo_recover_us` | 0/81 FAIL — 2 points reading impossible negatives | **2/81 FAIL** |
| `t_false_ok_fast_us` | 81/81, saturated at ≤1989.29 µs | 81/81, unclipped to **13414.4 µs** |
| `iq_por_ua` / `t_false_ok_slow_us` | 38/81 · 3/81 | 38/81 · 3/81 — unchanged |

**The `t_bo_recover_us` row is the proof that the new failures are unmasked
rather than caused.** On the schematic netlist, exactly two points read a
negative recovery time on the 2 ms deck — `fs_-40c_3.63v` (−6.141 µs) and
`sf_-40c_3.63v` (−4.695 µs) — and on the 30 ms deck **those same two points,
and no others**, read 1002.85 µs and 1303.43 µs: genuinely over the 900 µs
bound, and previously scoring PASS because the number was nonsense. The
mapping is one-to-one. Every other corner on the grid still passes the check.

This also settles a smaller point the old deck could not: `sf`/−40 °C/3.63 V's
false-valid window on the 1.0 V/µs ramp is **13.4 ms**, not the ~4.4 ms this
document has been quoting from a deck that stopped at 2 ms.

### `ok_bo_dip_mv` is the one that is genuinely the cell — and it is an RC, not a latch

`sim/bias-core-startup/`'s `ok_bo_dip_mv` samples `BIAS_OK` once, 2 ms into a
3 ms dead-rail window, against a ±300 mV bound; extraction takes it from
33.6 mV to 303.432 mV at `ss_-40c_*`. That is not a sampling artefact — the
same instant on both netlists reads genuinely different voltages — so it
needed its own measurement.
[`sim/bias-core-startup/control/dip_results.md`](../sim/bias-core-startup/control/dip_results.md)
stretches the dead-rail window from 3 ms to 17 ms and samples the discharge
as a curve rather than at one point:

| Time since the rail reached 0 V | schematic export | klt-extracted |
| ---: | ---: | ---: |
| 0.5 ms | 53.56 mV | 327.8 mV |
| **2 ms** (the check's own sample) | **33.63 mV** | **303.4 mV** |
| 5 ms | 16.0 mV | 270.9 mV |
| 12 ms | 5.356 mV | 210.8 mV |
| 17 ms | 3.554 mV | 176.4 mV |

Three things follow, and the first is the one that matters:

- **The node is not stuck.** The extracted discharge is monotonic across all
  eight samples; it needs roughly the whole 17 ms window to reach the level
  the schematic export reaches in 2 ms. This is not the held stale valid
  `XMOKC` exists to prevent — it is the same discharge on a ~9× longer time
  constant.
- **The core is not implicated.** `V(VREF)` on the same DUT tracks between the
  two netlists to within 4 mV at `ss`/−40 °C over the entire window, against a
  `BIAS_OK` difference of 270 mV at the same instant. What moved is the
  `BIAS_OK`/`NOKX` output net's own parasitic RC.
- **The physically load-bearing requirement still holds with margin.** The
  check exists because `BIAS_OK` must not be a level a downstream `nfet_03v3`
  gate could read as high. `sim/devchar/SUMMARY.md` measures
  `nfet_03v3 Vgs,th` = 0.7547 V at `ss`/27 °C with dVt/dT = −1.006 mV/°C, i.e.
  **≈0.822 V at the −40 °C corners that fail** — 303.4 mV is 37 % of it.

So the ±300 mV bound is crossed by 1.1 % while the requirement behind it is
met by 2.7×. **The bound is not moved here.** It is not a ratified
`spec/target-spec.md` row, but this cell's *other* testbench bounds the same
physical quantity at 500 mV, citing the same `sim/devchar/SUMMARY.md` Vt
argument — two decks, two numbers, one quantity, and only one of them
derived. Which number is right, and whether the two should be harmonized, is
a ratification judgement for #1 in exactly the sense
[DR-017](../spec/decision-records/DR-017-por-glitch-representative-depth.md)
left "whether to re-cut this check" to #1 rather than taking it. Until then
the check reads FAIL at three corners, on the record, with the mechanism
measured.
