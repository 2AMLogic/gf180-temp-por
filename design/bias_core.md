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

Both are **deterministic corner** records: `design.ngspice` sets
`sw_stat_mismatch=0`, so everything below bounds the **systematic + corner**
term only. Local mismatch on the 8:1 PNP ratio, the `R2/R1` ratio and the
amplifier's input pair is issue #15's Monte Carlo job. Full
ramp-rate/brownout envelope against a real assembled block is #14's.

**Two of the recorded checks fail on purpose.** They are the two conflicts
this issue was chartered to surface rather than absorb:

1. [`por-iq`](../spec/target-spec.md#por-iq) **< 1 µA is not met** — see
   [Iq apportionment](#iq-apportionment).
2. A **starved-loop window** exists at the ratified fast end of
   [`por-ramp-rate`](../spec/target-spec.md#por-ramp-rate) and after a
   brownout, during which `BIAS_OK` can read a false valid — see
   [The starved-loop window](#the-starved-loop-window).

Plus one integration defect that no single-cell testbench can see:

3. The **shared `IBIAS` net is clamped to `VSS` in the reset-asserted
   state**, which is a closed bias-vs-POR lockup at the top level — see
   [The shared IBIAS net](#the-shared-ibias-net).

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
[`por-iq`](../spec/target-spec.md#por-iq)'s <1 µA row being written down.
Even at 100 nA/branch the row is not met (see below), so 1 µA/branch was
never a candidate. The property the 8:1 recommendation rests on still holds
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
> `(Cc/gm1)·dVDD/dt`. The coefficient is **≈ 2.4 µs** times the ramp rate,
> and its sign is always toward more loop current, i.e. `VREF` high.

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

**Measured boundary.** Correct at ramps of **0.36 V/µs and slower** (10 µs
to full rail) at every corner, including −40 °C; false-valid at 1.0 V/µs.
`por-ramp-rate` ratifies 1 V/µs, so the cell is **~3× short of the ratified
fast limit**.

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
sizing miss: `por-iq` <1 µA and `por-ramp-rate`'s 1 V/µs fast limit cannot
both be met by a bandgap-referenced always-on core in gf180mcu at this
scale. `target-spec.md` §5 already withdrew the <0.3 µA stretch with the
words "requires architecture revision"; this is the same finding one row
further out. Resolving it is a decision-record question for #1/#14, and the
options are:

1. **Re-cost `por-iq`** upward (the §5 mechanism, and see
   [Iq apportionment](#iq-apportionment) — the row is already missed by 2.3×
   for unrelated reasons).
2. **Re-cost `por-ramp-rate`**'s fast limit down to the measured 0.36 V/µs.
3. **Change the architecture** — e.g. a `RESETn`-gated `IBIAS` (see below),
   which frees ~1 µA of budget that could be spent on amplifier drive.

Nothing here relaxes either row to make the result pass.

## Iq apportionment

[`por-iq`](../spec/target-spec.md#por-iq) is **< 1 µA**, quoted with `RESETn`
asserted and the temperature sensor disabled, and per §5 rule 1 it includes
*every* branch that must conduct for the POR threshold decision in that
state. `bias_core` has no enable and no off state, so **its entire supply
current is that contribution** — there is no share to argue about.

Measured over the 81-point grid:

| | Minimum | Maximum (binding corner) |
| --- | --- | --- |
| `bias_core` total (`iq_por_ua`) | **0.541 µA** (`ss_-40c_2.97v`) | **2.047 µA** (`ff_125c_3.63v`) |
| of which leaves through `IBIAS` (`ibias_na`) | 297 nA | **1119 nA** |
| `bias_core`'s own core (`iq_own_ua`) | 244 nA | **929 nA** |

At the binding corner **FF / +125 °C / 3.63 V**, which is exactly the corner
the `por-iq` row names:

| Item | Current | Source |
| --- | ---: | --- |
| `bias_core` core (3 legs, amplifier, `PB` rail, settle comparator, startup stack) | 929 nA | measured `iq_own_ua` |
| `bias_core`'s `IBIAS` output leg | 1119 nA | measured `ibias_na` |
| **`bias_core` total** | **2047 nA** | measured `iq_por_ua` |
| `por_comparator` own draw | 292 nA | `design/por_comparator.md`, measured `iq_own_ua` |
| `por_output_chain` own draw | **[TBD-#12]** | not designed yet |
| **Total against `por-iq` (<1 µA)** | **≥ 2339 nA** | **2.34× over budget, before #12 adds anything** |

`por_comparator`'s record quotes 792 nA against this row, of which 500 nA was
an *idealised* `IBIAS` source standing in for this cell. Summing the two
records naively would double-count it; the table above adds `bias_core`'s
real total to `por_comparator`'s **own** 292 nA, which is the
non-double-counted number.

**Where it goes, and what would have to change.**

- **The 0.5 µA `IBIAS` convention is the single largest line item.** At the
  binding corner it is 1119 nA — **more than the entire `por-iq` budget on
  its own**, before any other branch conducts. And in the reset-asserted
  state it is *entirely wasted*: `por_comparator` divides it 20:1 down to a
  25 nA tail, and `temp_core` — the consumer that actually wants 0.5 µA — is
  disabled and throws it into a clamp (see below).
- **`bias_core` cannot fix that on its own.** The cell has **no input pins
  at all**: it cannot know whether POR has released, so it cannot source
  100 nA before release and 500 nA after. Adding an `EN`/`RESETn` input is
  an interface change and therefore a decision record, not a #11 edit.
- **Even a free `IBIAS` would not close the gap**: 929 nA of core + 292 nA
  of comparator = 1221 nA, still over, before #12.
- **The core is already 10–50× below DR-005's own 1–5 µA/branch estimate.**
  Halving it again costs resistor area quadratically (`R2` would grow to
  12.6 MΩ, ~16 400 µm² of poly on its own) and slows the loop further, which
  makes [The starved-loop window](#the-starved-loop-window) worse.
- **Roughly 40 % of the total is temperature and resistor corner, not
  design.** `I = ΔV_EB/R1` with a −1545 ppm/°C `ppolyf_u_3k` `R1` is
  *super*-PTAT: the same cell measures 0.541 µA at `ss`/−40 °C and 2.047 µA
  at `ff`/125 °C. A lower-TC flavour would flatten it at ~8.5× the area.

**This is the re-cost `target-spec.md` §5 assigns to #11 and #1.** Per that
amendment's own words the target is not relaxed here to make the arithmetic
work; the check in `sim/bias-core-designer-check/testbench/tb.json` is left
at the ratified 1.0 µA and fails at 38 of 81 points.

## The shared `IBIAS` net

`design/netlist/temp_por_top.spice` wires `IBIAS` as a **single net** shared
by `bias_core`, `temp_core`, `por_comparator` and `por_output_chain`. DR-005
startup ordering step 6 holds `temp_core` disabled until POR releases, and
`temp_core`'s disabled state clamps the `IBIAS` **pin** to `VSS` through its
`XMDIB` device — deliberately, and documented in `design/temp_core.md`
("Disabled state"), which also anticipates that "if pre-POR block current
matters, the fix belongs in `bias_core` (gate its own output), not here".

It is worse than a current-budget problem. `sim/bias-core-ibias-sharing/`
instantiates the real cells in the real top-level wiring and compares them
against a control without `temp_core`:

- **Control** (no `temp_core`): the shared node sits at a diode drop,
  `por_comparator`'s tail mirror is biased, and `POR_RAW` releases at a rail
  well above every corner's threshold — which is also the first evidence
  that `bias_core`'s real `IBIAS`/`VREF`/`BIAS_OK` reproduce what
  `sim/por-comparator-designer-check` obtained from idealised stimuli.
- **Real wiring** (disabled `temp_core` present): the clamp holds the shared
  node near `VSS` whatever `bias_core` sources into it, `por_comparator`'s
  tail is starved, `POR_RAW` cannot go high, `RESETn` is never released, and
  `temp_core` is therefore never enabled. **That is a closed bias-vs-POR
  lockup loop** — precisely the failure this issue is chartered to prove
  absent.

`VREF` is unaffected in both branches (the reference loop is self-biased and
does not depend on the `IBIAS` leg's compliance), which is what identifies
this as an interface defect on one net rather than a failure of the core.

The fix necessarily touches a cell this issue may not modify — `temp_core`'s
`XMDIB` gating, or the `IBIAS` interface contract itself — so it is recorded
here with a failing check that will go green by itself once the interface is
corrected. The natural candidates:

1. Gate `temp_core`'s `XMDIB` on something other than the always-asserted
   pre-POR `EN` (it exists to stop a forced current having nowhere to go,
   which is a testbench condition, not a system one).
2. Give `bias_core` a `RESETn`/`EN` input and let it gate its own `IBIAS`
   output — which also recovers ~1 µA of `por-iq` budget (see above).
3. Split `IBIAS` into two nets, POR-side and sensor-side.

All three are interface changes and belong in a decision record.

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

## Reproducing the evidence

```bash
python3 design/netlist.py --check            # schematic <-> committed netlist
python3 sim/build_tb.py --check              # netlist <-> testbench fragment
python3 sim/run_corners.py bias-core-designer-check -j 8 --timeout 900
python3 sim/run_corners.py bias-core-ibias-sharing  -j 8 --timeout 900
```

Both runs exit non-zero by design — see the two failing checks above. `sim/`
is append-only, so a re-run mints a new record id and does not overwrite the
committed ones.

## Out of scope here, on purpose

| Not here | Where |
| --- | --- |
| Mismatch / Monte Carlo on the 8:1 ratio, `R2/R1` and the amplifier offset | #15 |
| Ramp-rate envelope, brownout re-assertion and reset-pulse interaction on the assembled block | #14 |
| Deglitch, the ≥1 ms one-shot, push-pull drive, the below-floor `RESETn` pull-down | `por_output_chain`, #12 |
| Re-costing `por-iq` or `por-ramp-rate`, and the `IBIAS` interface change | a new decision record through #1 |
| Layout, matching strategy, measured area | #17 |
