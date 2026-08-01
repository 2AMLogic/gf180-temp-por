# `bias_core` — shared bias / reference core

Sizing rationale, startup analysis and Iq apportionment for
`design/bias_core.sch` (issue #11). Topology per
[DR-005](../spec/decision-records/DR-005-temp-por-architecture-survey.md);
device choices per [`sim/devchar/SUMMARY.md`](../sim/devchar/SUMMARY.md)
(issue #4); targets per [`spec/target-spec.md`](../spec/target-spec.md)
(RATIFIED, DR-008 — this document does not amend it, and where a number here
does not fit a ratified row it says so instead of moving the row).

**This document is where `spec/target-spec.md` §5's "Known accounting risk —
owned by #11" gets its answer.** The answer is **no**: the shared core does
not fit inside the `<1 µA` [`por-iq`](../spec/target-spec.md#por-iq) target,
and the shortfall is large enough that it is a re-cost, not a rounding
error. The numbers, the decomposition and what a re-cost would have to move
are in [Iq budget and the `por-iq` apportionment](#iq-budget-and-the-por-iq-apportionment).

Every number in this file that is not a device dimension comes from a
recorded evidence run, not an estimate:

| Evidence | What it substantiates |
| --- | --- |
| [`sim/bias-core-designer-check/`](../sim/bias-core-designer-check/) | settled `VREF` over the 81-point grid, current sourced into `IBIAS`, amplifier systematic offset, startup-kick idle state, the **no-latched-dead-state DC proof**, and three fixed-rail snapshots placing `BIAS_OK`/`VREF` validity against the ratified release threshold |
| [`sim/bias-core-iq/`](../sim/bias-core-iq/) | the `por-iq` apportionment: total, core share and `IBIAS` distribution share, over the 81-point grid. **This record is a recorded FAIL against `por-iq`** — deliberately, see below |
| [`sim/bias-core-startup/`](../sim/bias-core-startup/) | quasi-static rail sweep 0 → 3.63 V: the rail at which the core comes up, the rail at which `BIAS_OK` asserts, the margin between them, and the reference error at the earliest legal release rail |

All three are **deterministic corner** records: `design.ngspice` sets
`sw_stat_mismatch=0`, so everything below bounds the **systematic** error
only. The random/mismatch share is issue #15's Monte Carlo job.

## Interface — and the one consequence that dominates this document

The port list is fixed by the #8 stub and is unchanged by this issue:

```
.subckt bias_core VDD VSS IBIAS VREF BIAS_OK
```

**There is no enable pin.** That is not a detail: `spec/target-spec.md` §5
rule 1 charges `por-iq` with every branch that must conduct while `RESETn`
is asserted, and with no enable there is no state in which any branch of this
cell is off. **The whole cell is charged to `por-iq` by construction**, and
no amount of internal partitioning can move part of it to
[`temp-iq`](../spec/target-spec.md#temp-iq). DR-005's option of "partitioning
the bias" — an always-on nA-class branch for POR and a richer branch for the
temperature sensor — is not reachable through this interface; it would need
a port change and therefore a decision record.

| Pin | Direction | What this cell guarantees |
| --- | --- | --- |
| `VDD`/`VSS` | supply | 3.3 V core flavour, 2.97–3.63 V steady state (DR-001) |
| `IBIAS` | out | **sources** current into the pin; consumers put a diode-connected nfet on it. 478 nA at tt/27 °C/3.30 V, 266–966 nA over the grid |
| `VREF` | out | 1.1888–1.2107 V over the grid (**±0.91 %** about 1.1995 V). Gate-only load — no DC current may be drawn |
| `BIAS_OK` | out | high only when the core is up *and* the rail has headroom over `VREF`; asserts at 1.54–2.32 V of rail, always after `VREF` has arrived and always before the 2.47 V minimum release threshold |

## Topology

```
                          PG (mirror gate, self-biased)
   VDD ──┬──────┬──────┬──────┬──────┬──────┬──────────── VDD
        MP1    MP2    MP3    MP4    MT    MSU4          pfet, L=8u (MP4 L=4u)
         │      │      │      │      │      │
        NA     NB    VREF   IBIAS   NT     NK ──┬── MNAT (native, Vgs=0)
         │      │      │             │          │      │
         │     R1      R3            │        MSU3    RDEG
         │      │      │             │       (kick)    │
         │     NC     NRE            │          │     VSS
        Q1    Q8A..H   QR            │         PG
         │      │      │             │
        VSS    VSS    VSS      consumers' diodes

   NA, NB ──► error amplifier (PMOS pair, NMOS mirror load,
              NMOS common-source 2nd stage, Miller + nulling R) ──► PG
```

The amplifier forces `V(NA) = V(NB)`, so the voltage across `R1` is exactly
the emitter-area-ratio ΔVBE and the branch current is

```
I = ΔVBE / R1 = (kT/q)·ln(8) / R1                      ≈ 60 nA at 27 °C
```

`MP3` is a matched leg dropping that same current on `R3` in series with a
1× PNP, so

```
V(VREF) = VBE(QR) + (R3/R1)·(kT/q)·ln(8)
```

— a first-order bandgap: a CTAT `VBE` plus a PTAT term whose gain is a
**same-flavour resistor ratio**. Two properties fall out and both are
load-bearing:

- **`VREF` depends on `R3/R1`, not on `R`.** `ppolyf_u_3k`'s −1545 ppm/°C
  tempco and its ±25 % sheet corner cancel in the ratio. The record
  confirms it: the `res_ff`/`res_ss` corners move both resistors by ±25 %
  and move `VREF` by **−0.5 %/+0.05 %** (1.19354 V at `res_ss_-40c_2.97v`,
  1.20751 V at `res_ff_125c_3.63v`).
- **The branch current is deliberately *not* ratio-stable.** `I = ΔVBE/R1`
  is PTAT over `R`'s negative tempco, so it nearly doubles from `ss`/−40 °C
  to `ff`/+125 °C. That is the single largest term in the Iq problem below,
  and it is a property of the topology, not of the sizing.

## Device sizing and why

### Vertical PNP — `pnp_10p00x10p00`, 8:1, ~60 nA/branch

Unit cell and ratio come from `sim/devchar/SUMMARY.md` ("Recommendation:
sensing core"): `pnp_10p00x10p00` in an **8:1 emitter-area pair**, built as
**eight unit-cell instances in parallel** (`XQ8A..XQ8H`), not one instance
with `par=8` — SUMMARY.md records that the gf180mcu vertical-PNP `par=`
parameter scales only the model's mismatch term and not `Is`, so `par=8`
would be a 1:1 ratio wearing an 8:1 label. `temp_core` made the same choice
for the same reason.

A tenth PNP, `XQR`, is the `VREF` leg's CTAT device. It is a separate device
rather than a tap off `XQ1` so that the `VREF` output is buffered from the
loop: anything that loads `VREF` perturbs `VREF` only, never the branch
current that defines the reference.

**Bias point: ~60 nA/branch, an order of magnitude below both DR-005's
1–5 µA/branch estimate and SUMMARY.md's 10 µA characterisation point.** The
reason is the Iq budget and nothing else — see below. The property the 8:1
recommendation rests on still holds there: `VREF`'s measured 81-point spread
is ±0.91 %, and the `bjt_ff`/`bjt_ss` corners (which move `Is` directly)
move it by only −0.9 %/+0.9 %.

### Resistors — `ppolyf_u_3k`, W = 1 µm

| Device | `r_width` × `r_length` | ≈ value (typ, 27 °C) | Role |
| --- | --- | --- | --- |
| `XR1` | 1 µm × 299 µm | 896 kΩ | ΔVBE → branch current: 53.8 mV / 896 kΩ ≈ 60 nA |
| `XR3` | 1 µm × 3580 µm | 10.7 MΩ | PTAT gain for `VREF`; `R3/R1 ≈ 12` |
| `XRZ` | 2 µm × 366 µm | 573 kΩ | nulling resistor for the Miller compensation, ≈ 1/gm2 |
| `XRDEG` | 1 µm × 1600 µm | 4.8 MΩ | source degeneration for the native startup device |

`ppolyf_u_3k` — not `temp_core`'s `ppolyf_u` — because at 60 nA the total
resistance the reference needs is set by physics, not by choice:
`R1 + R3 ≈ (VREF − VBE + ΔVBE)/I ≈ 0.7 V / 60 nA ≈ 11.6 MΩ`. `ppolyf_u` at
~360 Ω/□ would need **32 000 µm²** of poly for that, i.e. two thirds of the
whole block's ≤0.05 mm² planning budget
([`area`](../spec/target-spec.md#area)) for one resistor. `ppolyf_u_3k` at
~3.1 kΩ/□ does it in **~3900 µm²**. The cost of the choice is `ppolyf_u_3k`'s
much larger |TC| (−1545 vs −74.8 ppm/°C), and that cost is paid *entirely in
the branch current*, not in `VREF`, because `VREF` only sees the ratio —
which is exactly the trade `sim/devchar/SUMMARY.md` says a same-flavour ratio
pair lets you make. `R1` and `R3` share width as well as flavour so the ratio
is a length ratio.

`R3/R1 = 11.97` was tuned by simulation, not derived: with `VBE` at 60 nA the
first-order zero-TC ratio is not the textbook `≈ 10.2` computed from a 10 µA
`VBE` tempco. The measured residual over −40…125 °C at `tt` is **2.4 mV
(0.20 %)**.

### Cascode-free PMOS mirror — `L = 8 µm`

Four legs off `PG`: `MP1`/`MP2` (the 1:1 pair, W = 2 µm), `MP3` (the `VREF`
leg, W = 2 µm) and `MP4` (the `IBIAS` leg, W = 8 µm / L = 4 µm = 8×), plus
the amplifier tail `MT` and the startup replica `MSU4`.

**No cascodes, deliberately, and this is a departure from `temp_core`.**
`temp_core` cascodes its mirror because its third leg's drain swings ~1 V
away from legs 1 and 2. Here:

- The pair that *defines* ΔVBE, `MP1`/`MP2`, sees identical VGS **and**
  identical VDS — both drains sit at the same `VBE`, because the amplifier
  forces `V(NA) = V(NB)`. That ratio is exact by construction and a cascode
  would add nothing to it.
- `MP3`'s drain sits 0.64 V higher (at `VREF`). `L = 8 µm` keeps the
  resulting Early-effect ratio error near 1 %, which lands in `VREF` as
  roughly 0.6 %.
- A wide-swing cascode stack would cost ~0.4 V of extra dropout, and this
  cell has to be *valid* well below the 2.47 V minimum release threshold
  (DR-005 startup step 3). The measured dropout is **1.15–1.86 V**; with a
  cascode it would not have cleared 2.47 V at the slow/cold corner.

That is the trade: ~0.6 % of `VREF` accuracy bought 0.4 V of dropout margin.
Given that `VREF`'s measured total spread is 1.82 % against a ratified ±5 %
window, it is the right side of the trade.

### Error amplifier

PMOS input pair with an NMOS mirror load, then an NMOS common-source second
stage, Miller-compensated with a nulling resistor — the same shape as
`temp_core`'s, scaled down ~40×.

| Device | Size | Role |
| --- | --- | --- |
| `XMT` | pfet 2 µm/8 µm, gate `PG` | tail, ≈ 60 nA (self-biased off the mirror) |
| `XMI1`, `XMI2` | pfet 8 µm/4 µm | input pair, gates on `NA`, `NB` |
| `XML1`, `XML2` | nfet 2 µm/8 µm | mirror load |
| `XMS2N` | nfet 2 µm/8 µm | second stage — a **current-density copy** of `XML1` |
| `XMS2P` | pfet 2 µm/8 µm, gate `PB` | second-stage load, ≈ 60 nA |
| `XMBP`, `XMBN` | pfet 1 µm/8 µm, nfet 1 µm/8 µm | make `PB` (≈ 15 nA leg) |
| `XCC` + `XRZ` | 45 µm × 45 µm MIM (≈ 4 pF) + 573 kΩ | Miller compensation, nulling zero |

A PMOS input pair is required, not preferred: the inputs sit at a `VBE`,
which falls to **0.34 V at 125 °C** at this current, far below an NMOS
pair's usable common-mode floor.

`XMS2N` is a current-density copy of `XML1` (both nfet 2 µm/8 µm at the same
current), so stage 1's output sits at the diode node's own VGS and the
*systematic* input offset is structurally near zero rather than a residual.
Measured across all 81 PVT points: **−5.96 … +9.48 µV**. This matters
disproportionately — the loop solves `I·R1 = ΔVBE + Vos`, so 1 mV of input
offset would be a **1.9 % branch-current error and a ~1.2 % `VREF` error**,
a quarter of the whole ratified threshold window.

**`XMS2P` cannot use `PG` as its gate**, which is why the `XMBP`/`XMBN` leg
exists: stage 2's *drain* is `PG`, so a PMOS load with its gate on `PG` would
be diode-connected and would collapse the stage's output impedance — and with
it the loop gain that keeps the offset at µV.

`XCC` is large (4 pF, 2025 µm²) because the compensation has to work at
30 nA of stage current into a mirror gate carrying every leg's `Cgg`. It is
the second-largest passive in the cell after `R3`, and it is the price of a
core that runs two orders of magnitude below DR-005's estimate.

## Startup

A ΔVBE loop has a degenerate zero-current solution as well as its intended
one. This cell's kick (DR-005 startup step 3) is a **current-referenced**
detector, like `temp_core`'s and for the same reason — `temp_core.md` records
that no fixed voltage threshold on a `VBE` node can separate live from dead
across the rated range, because a *dead* core's `VBE` at −40 °C is higher
than a *live* core's at 125 °C. What is different here is the *node* the
detector drives.

| Device | Size | Role |
| --- | --- | --- |
| `XMSU4` | pfet 2 µm/8 µm, gate `PG` | 1:1 replica of a mirror leg → carries the loop current alive, ~0 dead |
| `XMNAT` | `nfet_06v0_nvt` 0.8 µm/50 µm ×16, gate and source at the **VSS side** | always-on weak pull-down, Vgs = 0 |
| `XRDEG` | 4.8 MΩ | source degeneration for `XMNAT` |
| `XMSU3` | pfet 1 µm/2 µm, source on `PG`, own nwell | the kick |

Alive, `XMSU4` outruns the degenerated native by more than 10×, so `NK` sits
at the rail (measured **0.956–1.000 × VDD** across the grid) and `XMSU3` sees
VGS = 0 and is fully off — the kick contributes nothing to the operating
point. Dead, `XMSU4` delivers nothing, `NK` collapses to ~0, `XMSU3` sees the
full rail across gate-source and pulls `PG` down until the loop starts.

Three sizing points are load-bearing, and two of them were **found by
simulation after an earlier revision failed**:

- **The weak always-on device is a pull-DOWN with its source at VSS, not a
  pull-UP on the sensed node.** The first revision used a native device as a
  pull-*up*: as the sensed node rose, its own source rose with it, the body
  effect raised the device's threshold, and its drive collapsed. At
  `ss`/−40 °C — where the native's threshold is already *positive* — the node
  stalled at 0.15 V, below any nfet threshold, and **the core never started
  at that corner**. Moving the weak device to the VSS side removes the body
  effect from the loop entirely and is what makes `NK` a genuine rail-to-rail
  node.
- **The kick is a PMOS in its own nwell, source on `PG`.** Nothing in the
  kick path depends on an nfet threshold being reached, which is what lets it
  work at the slow/cold corner where `Vt(nfet)` is 0.82 V.
- **The native device is source-degenerated.** `sim/devchar/SUMMARY.md`
  measured a **~440 mV corner spread** on the native threshold and called it
  "the number #11/#14 need to size headroom margin against" — this cell is
  that consumer. Undegenerated, `XMNAT` spans about 0.05 nA (`ss`/−40 °C) to
  4 µA (`ff`/+125 °C), five decades; the 4.8 MΩ degeneration self-biases the
  strong end down to a few tens of nA while leaving the weak end untouched,
  which is the only way both "beats the replica's leakage when dead" and
  "costs little when alive" hold at once. Sixteen unit devices in parallel
  set the weak end high enough to win against the replica leg's own
  subthreshold leakage at `ss`/−40 °C.

### The evidence, and why it is a DC sweep rather than a transient

`sim/bias-core-startup/` sweeps the rail **quasi-statically**, 0 → 3.63 V in
2 mV steps, seeding each step from the previous solution — so it tracks the
branch an arbitrarily slow ramp would sit on, and stays on a wrong branch if
one exists. That property is the whole point:

> A revision of this cell that passed a per-point `op` at 2.97/3.30/3.63 V at
> **all 81 grid points** was tracking a **second, high-current branch** with
> `VREF` pinned near `VDD − 0.2 V` from 1.4 V of rail all the way to 3.3 V at
> `ss`/−40 °C. Independent per-point operating points saw none of it, because
> each one starts from the solver's own guess and lands on the good solution.

Two things are therefore proven separately, and neither substitutes for the
other:

| Claim | Where | How |
| --- | --- | --- |
| The degenerate **zero-current** state is not stable anywhere on the grid | `sim/bias-core-designer-check/`, `vref_dead_v` | an electrically identical instance whose DC solve is **seeded in** that state (mirror gate at VDD, core nodes at 0, `NK` at 0) at all 81 points. Measured `vref_dead_v` is **bit-identical to `vref_v` at every point** |
| No **other** branch is reachable on the way up | `sim/bias-core-startup/` | branch-tracking rail sweep, all 81 points |

A transient starting from 0 V cannot prove either: it visits one trajectory,
never visits the dead state, and its answer depends on the ramp rate.
Ramp-rate coverage (both endpoints of the ratified 1 V/s … 1 V/µs envelope
plus a decade inside each) is [`por-ramp-rate`](../spec/target-spec.md#por-ramp-rate),
which the spec assigns to **#14** — this record deliberately does not
pre-empt it with one arbitrary rate.

### Measured startup ordering

| Quantity | Measured over 81 points | Meaning |
| --- | --- | --- |
| `v_core_up_v` | see `sim/bias-core-startup/` | rail at which `VREF` first reaches 1.10 V — the core's effective dropout, the number DR-005 left qualitative |
| `v_bias_ok_v` | see record | rail at which `BIAS_OK` asserts |
| `startup_margin_v` | `v_bias_ok_v − v_core_up_v` | the settle margin DR-005 defers to "#11/#14 sim", in ramp-rate-independent form: **#14 divides it by the ramp rate under test to get a time**, which is why it is quoted as a voltage |
| `release_margin_v` | `2.47 V − v_bias_ok_v` | how far below the earliest *legal* release the flag is already true |
| `vref_err_247_pct` | ±0.03 % (`sim/bias-core-designer-check/`, fixed-rail probe) | the reference is right, not merely flagged, by the earliest rail a release may happen at |

## `BIAS_OK`

DR-005 step 4 gates `por_comparator`'s release decision on this flag, so the
failure that matters is a **false-early** assertion: `por_comparator`'s
threshold is `VREF` times a resistor ratio, so with `BIAS_OK` high and `VREF`
still at, say, half its final value, POR would release at roughly half the
intended rail. The flag therefore requires **three** conditions, ANDed:

1. **The core is alive** — `NK` high. This is stronger than it looks: `NK`
   only reaches the rail once the replica leg carries the *full* loop
   current, which requires the mirror legs to have left triode. "`NK` high"
   is therefore "the core has its headroom and is at full current", not
   merely "some current is flowing".
2. **`VREF` is up** — `XMOKS` (nfet, gate on `VREF`) pulls `NOK` down only
   above ~0.7 V. An independent guard against `VREF` being held down
   externally.
3. **The rail has headroom over `VREF`** — `XMHD` (pfet, source on `VDD`,
   gate on `VREF`) conducts only when `VDD − VREF` exceeds a PMOS threshold,
   i.e. above ~2.0 V of rail. **This is the term that stops the false-early
   assertion**, and it was added after measurement: with conditions 1 and 2
   alone the flag followed the loop coming alive, which happens several
   hundred millivolts of rail before the reference is right.

`XMOKD` forces `NOK` high (and so `BIAS_OK` low) whenever the core is not
alive, and `XMOKZ` clamps `BIAS_OK` to `VSS` directly from `NKB`, so the flag
is **driven** low rather than merely undriven. Measured at a fixed 1.40 V
rail — below the core's dropout at every corner — `BIAS_OK` is **≤ 65 nV**
across the grid.

### Below the operating floor

Stated rather than implied, following `por_comparator.md`'s precedent.
**Below roughly 1 V of rail, neither device of the `BIAS_OK` output inverter
has a gate-source voltage above its threshold**, so the pin is
high-impedance rather than driven, and couples capacitively to the rising
rail. Nothing in a 3.3 V-only PDK can drive a rail-referenced logic level
below one threshold of rail; that is a property of the flavour (DR-001), not
of this sizing. It is also not this cell's problem to solve: DR-004 assigns
holding `RESETn` low from 0 V to `por_output_chain`'s below-floor pull-down
(#12), and `por_comparator` is itself dead in that regime. The claim this
cell makes is bounded accordingly — `BIAS_OK` is *driven* low for every rail
from ~1 V upward, and the 1.40 V fixed-rail probe is the evidence.

## `IBIAS` fan-out — a number #13/#14 need

The convention `temp_core` and `por_comparator` were each characterised
against is **0.5 µA at their own `IBIAS` pin**, with a local diode-connected
nfet on it (`temp_core` 4 µm/2 µm, `por_comparator` 2 µm/2 µm). This cell
sources **478 nA at tt/27 °C/3.30 V** into that convention's load, measured
with an in-line ammeter — i.e. it meets the convention as a *single-consumer*
number.

At the top level, though, `IBIAS` is **one net with three consumers**
(`design/README.md`'s hierarchy diagram). Their local diodes sit in parallel,
so each consumer's share is roughly its own `W/L` divided by the sum:

- Honouring "0.5 µA at *each* pin" would require this cell to source
  **~1.5 µA**, which is 1.5× the entire `por-iq` budget before the reference
  core, the comparator or the pulse timer draw anything. That is arithmetic,
  not an opinion.
- Sourcing 0.5 µA into the shared node instead — what this cell does — gives
  `temp_core` ~2/3 and `por_comparator` ~1/3 of it once both diodes are
  present, so `por_comparator`'s 25 nA tail scales down with it and the cell
  gets slower than the version `sim/por-comparator-designer-check/`
  characterised.

Both readings cannot be true at once, and this issue is not entitled to pick
one unilaterally — it changes a cell (#10) that is already characterised.
**Recorded here as an integration item for #13/#14**, with the measurement
that makes it concrete: the testbenches in `sim/bias-core-*/` load `IBIAS`
with a verbatim replica of the two designed consumers' diodes in parallel, so
the 478 nA figure is the shared-node number, not a single-cell idealisation.

A second, sharper integration hazard, found while wiring the load: **a
disabled `temp_core` clamps the shared `IBIAS` net to `VSS`.**
`design/netlist/temp_core.spice`'s `XMDIB` (nfet 1 µm/1 µm, gate on `ENB`)
pulls the pin to ground whenever `EN` is low — and `EN` is `RESETn`, so it is
low for exactly the pre-POR window in which `por_comparator` needs `IBIAS` to
make its decision. `temp_core.md` already flags the current cost of this
("if pre-POR block current matters, the fix belongs in `bias_core`") but not
the functional one. This cell **cannot** fix it: gating its own output would
have to be gated on something, and the only candidate it owns is `BIAS_OK`,
which by construction asserts *before* POR releases. The fix belongs at the
top level or in `temp_core`, and it is flagged here rather than absorbed.

## Iq budget and the `por-iq` apportionment

This is the acceptance-critical number for issue #11, and
[`spec/target-spec.md` §5](../spec/target-spec.md#5-quiescent-current-accounting-amendment-a7)
names this issue as the owner of the risk:

> **Known accounting risk — owned by #11.** DR-005 charges the shared core's
> 1–5 µA/branch to its *temperature-sensor* estimate, while its startup
> ordering has that same core live and settled **before** POR releases. Under
> rule 1 that current lands in `por-iq`. #11 must therefore either show the
> shared core's reset-asserted-state current fits inside <1 µA, or #1 must
> re-cost the row.

**It does not fit.** Measured over the full 81-point grid
(`sim/bias-core-iq/`), with `IBIAS` loaded by the two designed consumers'
diodes:

| Quantity | Minimum | tt/27 °C/3.30 V | **Maximum (FF/+125 °C/3.63 V — the corner the row names)** |
| --- | ---: | ---: | ---: |
| `bias_core` total, charged to `por-iq` | 432 nA (`ss_-40c_2.97v`) | 798 nA | **1687 nA** |
| — reference-core share | 165 nA | 320 nA | **725 nA** |
| — `IBIAS` distribution share | 266 nA | 478 nA | **966 nA** |

Where the core share goes at tt/27 °C/3.30 V (320 nA total):

| Branch | Current |
| --- | ---: |
| `MP1` + `MP2` (the ΔVBE pair) | 120 nA |
| `MP3` (the `VREF` output leg) | 60 nA |
| Amplifier tail `MT` | 60 nA |
| Amplifier second stage `MS2P` | 60 nA |
| `PB` bias leg (`MBP`/`MBN`) | 15 nA |
| Startup replica `MSU4` | 60 nA |
| Native pull-down `MNAT` (degenerated) | ≤ 45 nA |
| `BIAS_OK` detectors (`MOKP`, `MHDL`) | 30 nA |
| Static CMOS gates | ~0 |

(The branch list sums above the measured 320 nA because the replica and
detector legs share the mirror's own legs' current at partial ratios; the
measured number is the one that counts.)

### Against the target ([`por-iq`](../spec/target-spec.md#por-iq))

`por-iq` is **< 1 µA**, `[CWC]`, binding at FF/+125 °C/3.63 V, and by rule 1
it must cover `bias_core` **plus** `por_comparator` **plus**
`por_output_chain`:

| Contributor | At FF/+125 °C/3.63 V | Source |
| --- | ---: | --- |
| `bias_core` (this cell, all of it — no enable pin) | **1687 nA** | `sim/bias-core-iq/` |
| `por_comparator` own draw | **292 nA** | `sim/por-comparator-designer-check/`, `design/por_comparator.md` |
| `por_output_chain` own draw | **not yet designed** | #12 |
| **Total so far** | **≥ 1979 nA** | |
| **Target** | **< 1000 nA** | `spec/target-spec.md#por-iq` |

**The shortfall is ~2×, before #12 contributes anything.** Two sharper
statements, so the re-cost conversation starts from facts rather than from
this cell's sizing choices:

1. **Removing the whole `IBIAS` distribution current would not fix it.** The
   reference core alone at the binding corner is 725 nA; adding
   `por_comparator`'s measured 292 nA already reaches **1017 nA** — over
   budget with a zero-current bias distribution network and nothing at all
   for #12.
2. **Nor would slowing the core down further.** The core share is already at
   ~60 nA/branch, 17–83× below DR-005's own 1–5 µA/branch estimate for this
   topology. The resistors that set it are already 11.6 MΩ in the
   highest-sheet flavour the PDK offers; halving the current again doubles
   them to ~8000 µm² of poly and pushes the amplifier's settling into the
   regime where the ramp-rate envelope starts to bind.

This document deliberately does **not** relax anything to make the arithmetic
work — §5 says the same about itself. What it does is name what a re-cost
would have to move, in increasing order of cost:

- **Re-cost the `por-iq` row** through a new decision record (#1 is closed).
  Given DR-005's own 0.3–0.8 µA estimate for the precision path *alone*,
  measured 1.0 µA for core + comparator with no distribution current at all,
  and the withdrawn `<0.3 µA` stretch already conceded as
  architecture-limited, a target in the low-µA range is what the ratified
  architecture actually supports.
- **Add an enable pin to `bias_core`.** This is the option §5's own wording
  gestures at ("whatever part of the shared bias/reference core has to be
  live") and DR-005's partition option assumed. It needs a port-list change
  and therefore a decision record, and it is not free: whatever is disabled
  pre-POR must still leave `VREF` and `BIAS_OK` valid, which is most of the
  core.
- **Change the `IBIAS` distribution convention** — the 266–966 nA
  distribution share is over half the cell's draw at every corner and is
  spent purely on holding a shared gate node, since each consumer's local
  diode dumps its share to ground. A voltage-mode bias distribution (one
  master diode here, gate node distributed, no per-consumer diode) would
  remove most of it, at the cost of re-characterising #9 and #10.

### `temp-iq`, and what this changes for #9

`temp_core.md` counted the 0.5 µA `IBIAS` reference inside its own
8.14–16.27 µA range and noted that, charged the way §5 defines it,
`temp-iq` would be **15.77 µA** at the binding corner. This record settles
that: **the `IBIAS` current is `por-iq`'s**, because `bias_core` has no
enable and sources it whether or not the sensor is on. So `temp-iq`'s
smaller number is the correct one, and
[`temp-iq`](../spec/target-spec.md#temp-iq)'s `<20 µA` target keeps its
margin. That is the one part of the §5 accounting risk that resolves in the
spec's favour.

## Error budget — what `VREF` costs `por-vth-rise`

`sim/por-comparator-designer-check/` **measured** the comparator's
sensitivity to `VREF` as **1.00 fractional** (`vref_gain_frac`), and
`por_comparator.md` records that the comparator itself spends only ±0.15 % of
the ratified ±5 % window. So essentially the whole window belongs to this
cell's reference.

| Term | Systematic, measured over 81 points | Notes |
| --- | --- | --- |
| Total `VREF` spread | **1.1888 – 1.2107 V**, i.e. **±0.91 %** about 1.1995 V | 18 % of the ±5 % window |
| — resistor corners (`res_ff`/`res_ss`) | −0.50 % / +0.05 % | ±25 % sheet moves the ratio by well under 1 % |
| — BJT corners (`bjt_ff`/`bjt_ss`) | −0.90 % / +0.92 % | the dominant systematic term: `VBE(QR)` moves directly |
| — temperature, `tt`, −40…125 °C | 2.4 mV (**0.20 %**) | first-order curvature after the `R3/R1` tune |
| — supply, over the whole ±10 % window | ≤ 0.05 % | `L = 8 µm` mirror, no cascode |
| Amplifier systematic offset | **−5.96 … +9.48 µV** → **< 0.02 %** of `VREF` | `XMS2N` as a current-density copy of `XML1` |
| **Random mismatch** | **not visible here** | PNP `Is` mismatch, input-pair and mirror `Vt` mismatch. **Issue #15** |

**The honest reading**: the systematic budget uses 18 % of the ratified
window, leaving ~±4.1 % for #15's mismatch term — comfortable, and much more
comfortable than `temp_core`'s equivalent hand-off, because a bandgap
reference's absolute value is a far weaker function of device matching than a
temperature *slope* is. `por-vth-rise` is a `[3σ]` row marked
`conditional #15`, and nothing here upgrades it.

## Area — flagged for #17

Approximate drawn area of the passives, which dominate:

| Item | Area |
| --- | ---: |
| `XR3` (10.7 MΩ) | ~3600 µm² |
| `XRNR`-class degeneration + nulling resistors | ~2300 µm² |
| `XCC` (4 pF MIM) | ~2025 µm² |
| Ten `pnp_10p00x10p00` unit cells | ~1000 µm² + spacing |
| Sixteen native unit devices | ~640 µm² |
| MOS devices | ~350 µm² |

That is roughly **10 000 µm² before spacing and routing**, i.e. about 20 % of
the ≤0.05 mm² planning budget in [`area`](../spec/target-spec.md#area), for
one of four cells. `XR3` at 1 µm × 3580 µm will be a serpentine and its
matching to `XR1` is what holds `VREF`'s temperature curve — flagged for #17
as a common-centroid/interdigitated candidate alongside the 8:1 PNP array.

**klayout-tools friction check**: nothing in this cell needs a tool
capability that does not exist — a serpentined poly resistor, a parallel PNP
array, a MIM cap and ordinary MOS devices. No issue is filed against
`2AMLogic/klayout-tools` for it. Re-evaluate at #17 when the `R3`/`R1`
serpentine is actually drawn as a matched array.

## Reproducing the evidence

```bash
python3 design/netlist.py --check        # netlists match the schematics
python3 sim/build_tb.py --check          # testbench fragments match the netlists
python3 sim/run_corners.py bias-core-designer-check -j 6 --timeout 1500
python3 sim/run_corners.py bias-core-iq -j 6 --timeout 1500
python3 sim/run_corners.py bias-core-startup -j 6 --timeout 1500
```

`sim/run_corners.py bias-core-iq` **exits 1 by design** — its `por-iq` check
is the recorded spec conflict, not a regression.

> **Toolchain note.** `design/netlist.py` needs **xschem ≥ 3.4.7**. xschem
> 3.4.4 (the current Debian package) ignores `top_is_subckt` and emits every
> cell as a commented `**.subckt` plus a flat `.end` deck, which makes
> `--check` fail on *every* cell including the ones already committed. If
> `--check` reports "`.subckt temp_por_top not found in its own netlist`",
> that is the symptom; put a 3.4.7 build ahead of the packaged one on `PATH`.

## Out of scope here, on purpose

- **Mismatch / Monte Carlo** — issue #15. Everything above is deterministic
  corners.
- **Ramp-rate and brownout envelopes** — [`por-ramp-rate`](../spec/target-spec.md#por-ramp-rate)
  and [`por-brownout`](../spec/target-spec.md#por-brownout) are #14's rows.
  This cell's startup evidence is the ramp-rate-independent quasi-static
  statement plus the seeded dead-state proof; #14 owns the time domain.
- **Full spec-row coverage** — issue #13.
- **Trim** — DR-005 puts the single trim node on the PTAT gain path inside
  `temp_core`, and rules out a POR trim node in wave 1. There is no trim on
  `VREF`, which is why the ±0.91 % systematic spread above has to stand on
  its own.
- **Layout matching** — issue #17.
