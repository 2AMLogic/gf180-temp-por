# `temp_core` — PTAT / CTAT temperature-sensing core

Sizing rationale, error budget and Iq budget for `design/temp_core.sch`
(issue #9). Topology per
[DR-005](../spec/decision-records/DR-005-temp-por-architecture-survey.md);
device choices per [`sim/devchar/SUMMARY.md`](../sim/devchar/SUMMARY.md)
(issue #4, PR #22); targets per
[`spec/target-spec.md`](../spec/target-spec.md) (DRAFT, ratification is #1's
operator gate — this document does not ratify anything).

**This document is where two `[TBD-#9]` rows of `spec/target-spec.md` get
their values**, per that file's §8 Open TBD register:

| Spec row | What #9 owed it | Value |
| --- | --- | --- |
| [`temp-vt-transfer`](../spec/target-spec.md#temp-vt-transfer) | nominal slope + output range, design intent | `PTAT` = +4.3088 mV/K through the origin, 1.004–1.717 V; `CTAT` = −1.86 mV/°C, 0.461–0.782 V. Headroom bound holds with +265 mV worst-case margin. |
| [`temp-trim-strategy`](../spec/target-spec.md#temp-trim-strategy) | trim *mechanism* | 6-bit binary-weighted short-out ladder on `R2`, metal-strapped in wave 1, fuse/OTP-ready. |

Both rows are filled in `spec/target-spec.md` itself as well; the register
entries are struck through there rather than deleted, so the audit trail from
"unset, owned by #9" to "filled" stays visible.

Every number in this file that is not a device dimension is taken from a
recorded evidence run, not estimated:

| Evidence | What it substantiates |
| --- | --- |
| [`sim/temp-core-designer-check/`](../sim/temp-core-designer-check/) | PTAT/CTAT transfer, systematic temperature error, Iq, disabled-state draw, pad-load cost, trim range/LSB — 216-point PVT grid (9 corners × 8 temperatures × 3 supplies) |
| [`sim/temp-core-startup/`](../sim/temp-core-startup/) | cold start from 0 V with EN gated by POR, pre-POR quiescent draw, brownout restart — 81-point PVT grid (9 corners × 3 temperatures × 3 supplies) |

Both are **deterministic corner** records: `design.ngspice` sets
`sw_stat_mismatch=0`, so everything below bounds the **systematic** error
only. The random/mismatch share is issue #15's Monte Carlo job, and the
budget below is written so #15 knows exactly how much room it has left.

## Topology

```
                       PG (mirror gate)
        VDD ──┬────────┬────────┬────────────── VDD
             MP1      MP2      MP3            8u/4u pfet, 2.5 uA each
              │        │        │
            MPC1     MPC2     MPC3            8u/1u cascode, gate PCAS
              │        │        │
             NA       NB      PTAT ──────────► PTAT pad
              │        │        │
              │       R1        R2 = R2FIX + 6-bit trim ladder
              │        │        │
              │       NC       VSS
              │        │
             Q1      Q8A..Q8H                 pnp_10p00x10p00, 1x : 8x
              │        │
             VSS      VSS

        NA, NB ──► error amplifier ──► PG      forces V(NA) = V(NB)
        NA ── RISO ──► CTAT pad
```

The error amplifier forces `V(NA) = V(NB)`, so the voltage across `R1` is
exactly the emitter-area-ratio ΔVBE and the branch current is

```
I = ΔVBE / R1 = (kT/q)·ln(8) / R1                          (PTAT)
```

`MP3`/`MPC3` is a matched third leg that drops that same current on `R2`:

```
V(PTAT) = (R2/R1)·(kT/q)·ln(8)                             (PTAT, by construction)
V(CTAT) = VEB(Q1)                                          (CTAT, ~ -1.86 mV/C)
```

Two properties fall out of writing it this way, and both are load-bearing
for the error budget:

- **`V(PTAT)` depends on `R2/R1`, not on R.** The absolute value and the
  temperature coefficient of the poly resistor cancel in a same-flavour
  ratio. `sim/devchar/SUMMARY.md` establishes this at the model level (the
  body-resistor temperature factor is a multiplicative function of flavour
  only, independent of `r_length`/`r_width`); the `res_ff`/`res_ss` corners
  confirm it in the record — they move `R2` by ±21 % (412–625 kΩ) and move
  the PTAT transfer constant by 0.03 %.
- **The core is deliberately *not* compensated.** DR-005 chose a
  bandgap-style core left uncompensated on purpose; the PTAT term is
  published raw rather than summed with the CTAT term into a flat
  reference. Both terms are brought out as pads (DR-002).

## Device sizing and why

### Vertical PNP pair — `pnp_10p00x10p00`, 8:1, 2.5 µA/branch

Unit cell and ratio come straight from `sim/devchar/SUMMARY.md`
("Recommendation: sensing core"): `pnp_10p00x10p00` in an **8:1 emitter-area
pair**, built as **eight unit-cell instances wired in parallel**
(`XQ8A..XQ8H`), not one instance with `par=8`. That is not a stylistic
choice — SUMMARY.md's "PDK/model finding worth flagging" records that the
gf180mcu vertical-PNP `par=` parameter scales only the mismatch term inside
the model and *not* `Is`, so `par=8` would have produced a 1:1 ratio wearing
an 8:1 label. Eight parallel instances is also what the layout will
physically be (#17's common-centroid array).

`pnp_10p00x10p00` additionally has the highest Early voltage of the four
characterised geometries (206 V), which minimises how much the cascoded
current-source loading moves the single-device CTAT leg.

**Deviation from the issue's stated bias point, stated explicitly.** Issue
#9's acceptance criteria ask for "near 10 µA/branch", quoting SUMMARY.md's
sensing-core recommendation. This cell uses **2.5 µA/branch**. The reason is
arithmetic, not preference:

- Two core branches at 10 µA are **20 µA on their own**, which equals the
  entire `<20 µA` block Iq target before the mirror's third leg, the
  amplifier or the bias network are counted. The 10 µA row and the 20 µA row
  cannot both be satisfied.
- SUMMARY.md's own sentence recommends 10 µA as "well inside the 1–5 µA/branch
  estimate in DR-005", which 10 µA is not — the recommendation is internally
  inconsistent, and DR-005's 1–5 µA/branch is the figure that was actually
  derived against the Iq row. 2.5 µA/branch sits in the middle of it.
- 10 µA was the *characterisation* bias point (a mid-decade point chosen so
  the sweep had a decade of margin either side), and SUMMARY.md's own
  decade-spacing check (59.75 and 60.93 mV/decade against the ideal 59.54)
  shows the device is well-behaved across 1–100 µA. Nothing in the
  recommendation depends on 10 µA specifically.
- The property the recommendation actually rests on — that the 8:1 ΔVBE
  tracks `(kT/q)·ln(8)` — **holds at 2.5 µA and is measured here**:
  53.879 mV against 53.785 mV of theory at 27 °C, a **0.17 % error**, i.e.
  slightly *better* than the 0.33 % SUMMARY.md measured at 10 µA.

Everything else in the sensing-core recommendation (unit cell, 8:1 over 4:1,
parallel instances) is followed exactly.

### PTAT gain resistors — `ppolyf_u`

`R1` and the whole `R2` ladder are `ppolyf_u`, per SUMMARY.md
("Recommendation: TC cancellation, sensing core, and POR divider"): the
lowest |TC| of the eight flavours measured (−74.8 ppm/°C), poly-on-field-oxide
with no substrate junction, and a practical ~360 Ω/□ for a moderate-value
ratio. Same flavour on both sides of the ratio is what makes the TC cancel.

| Device | `r_width` × `r_length` | ≈ value (typ, 27 °C) | Role |
| --- | --- | --- | --- |
| `XR1` | 2 µm × 119.47 µm | 21.6 kΩ | ΔVBE → branch current: 53.88 mV / 21.6 kΩ = 2.5 µA |
| `XR2F` | 2 µm × 2652.60 µm | 479 kΩ | fixed part of the gain resistor |
| `XR2T5..XR2T0` | 2 µm × 229.71 … 6.85 µm | 41.5 … 1.24 kΩ | binary trim ladder (see below) |
| `XRISO` | 2 µm × 111.05 µm | 20 kΩ | isolates the CTAT pad from the loop node `NA` |

`R2/R1 = 24` at the nominal trim code, giving
`V(PTAT) = 24 × 53.88 mV = 1.293 V` at 27 °C — measured 1.29334 V.

`XRISO` exists so that pad capacitance and any probe leakage land on a
20 kΩ series resistance instead of directly on `NA`, which is inside the
amplifier's feedback loop. It costs nothing in accuracy: `CTAT` is measured
with a high-impedance load, so no current flows through it.

### Error amplifier

PMOS input pair with an NMOS mirror load, then an NMOS common-source second
stage, Miller-compensated with a nulling resistor.

| Device | Size | Role |
| --- | --- | --- |
| `XMT` | pfet 20 µm/4 µm | tail, gate on `PB` → 1 µA |
| `XMI1`, `XMI2` | pfet 32 µm/4 µm | input pair, gates on `NA`, `NB` |
| `XML1`, `XML2` | nfet 8 µm/8 µm | mirror load |
| `XMS2N` | nfet 8 µm/8 µm | second stage |
| `XMS2P` | pfet 10 µm/4 µm | second-stage load, 0.5 µA |
| `XCC` + `XRZ` | 12 µm × 12 µm MIM + 175 kΩ `ppolyf_u` | Miller compensation, nulling zero |

A PMOS input pair is required, not preferred: the inputs sit at a VBE, which
falls to **0.46 V at 125 °C** (measured), far below an NMOS pair's usable
common-mode floor on a 2.97 V rail.

`XMS2N` is deliberately a current-density copy of `XML1` (both nfet
8 µm/8 µm, both carrying the same 0.5 µA when balanced), so stage 1's output
node sits at exactly the diode node's own VGS and the *systematic* input
offset is structurally near zero rather than being a residual. Measured
across all 216 PVT points: **|V(NA) − V(NB)| ≤ 5.4 µV**. This matters
disproportionately — see the error budget: 1 mV of input offset is 5.6 °C.

### Cascoded PMOS mirror

`XMP1/2/3` (pfet 8 µm/4 µm) with `XMPC1/2/3` (pfet 8 µm/1 µm) cascodes on
`PCAS`. `XMP1` and `XMP2` see identical VGS *and* identical VDS (the loop
forces `V(NA) = V(NB)`), so the 1:1 ratio that defines ΔVBE is exact by
construction. Leg 3's drain swings ~1 V lower than legs 1 and 2 across
temperature; the cascode is what keeps it on ratio anyway. Measured worst-case
headroom `VDD − V(M3D)` is **265 mV at `ff_-40c_2.97v`** — the cascode stack
stays in saturation at the worst (cold, low-rail, fast) corner.

## Trim: single 25 °C gain trim

DR-005 settled the *stance* (one trim node on the PTAT gain path, one-point
trim at 25 °C, no POR trim node in wave 1) and explicitly deferred the
*mechanism* to this issue.

**Mechanism chosen: a 6-bit binary-weighted short-out ladder on `R2`,
strapped by metal in wave 1.** `R2` is `XR2F` in series with six
binary-weighted segments `XR2T5..XR2T0`; each segment is shunted by an NMOS
switch (`XSW5..XSW0`, 32 µm/0.5 µm) whose gate is strapped to `VDD` (segment
shorted → lower gain) or `VSS` (segment in circuit → higher gain).

Why this mechanism:

- **No pad, no pin.** The ratified pinout (DR-002/DR-003, `design/README.md`)
  has no trim/config/programming pins, and this respects that: the trim is an
  internal metal-1 strap option, not a programming interface.
- **It is the drop-in hook-up point for a fuse/OTP bit cell later.** The six
  gates are the entire trim interface. Replacing the metal straps with a
  fuse/OTP array is a change to what drives six gates, not a change to the
  PTAT path — so wave 1 does not have to pay for OTP, and wave 2 does not
  have to redesign the core.
- **It trims gain, not offset.** `R2/R1` is precisely the quantity the
  one-point trim needs to move (see error budget).

Measured, across the full 216-point grid:

| Property | Design intent | Measured |
| --- | --- | --- |
| Nominal `R2` (code `100000b`) | 24 × `R1` | 412–625 kΩ over corners, 516 kΩ typ |
| 1 LSB | 0.25 % of `R2` | 0.2287–0.2423 % |
| Full range | ±7.9 % about the nominal code | 15.608–15.695 % total (±7.80 … ±7.85 %) |

In temperature terms at the 25 °C trim point: **1 LSB = 0.71 °C**, so trim
quantisation contributes **±0.35 °C**, and the **full range corrects ±23 °C**
of gain error — equivalently an amplifier input offset of **±4.2 mV**.

The switches are sized 32 µm/0.5 µm so that their `Ron` is small against the
smallest segment they short (1.24 kΩ); the measured LSB coming in at 0.229 %
rather than the drawn 0.25 % is exactly that `Ron` in series, and it is a
*measured* property of the ladder rather than an unmodelled one.

**Wave-1 code is `100000b`** — mid-scale, so the trim can move the gain in
either direction. `XSW5`'s gate straps to `VDD`, `XSW4..XSW0`'s to `VSS`.

**klayout-tools friction check**: DR-005 flagged trim-cell layout support as
a possible friction-protocol item. This mechanism does not need any special
tool support — it is a resistor ladder plus six NMOS switches plus a metal
strap option, all ordinary cells. No issue is filed against
`2AMLogic/klayout-tools` for it. Re-evaluate when #17 lays out the ladder as
a matched array, and when/if wave 2 replaces the straps with a fuse/OTP
bit-cell array.

## Enable: gated by POR

`EN` is active-high and is **driven directly from `RESETn`** at the top
level. `design/netlist/temp_por_top.spice` already wires it that way (from
#8):

```
xtemp VDD VSS IBIAS RESETn PTAT CTAT temp_core
```

`RESETn` is active-low (DR-004), so `RESETn` high = reset released = sensor
enabled. This is DR-005 startup-ordering step 6: the sensor is enabled only
*after* POR releases and is never required to be valid before POR, which
keeps it entirely out of the startup chicken-and-egg problem — only POR
itself needs a path that works before anything is biased.

Nothing in this cell is on POR's critical path. `IBIAS` is consumed but its
absolute accuracy is not: it sets only the amplifier tail and cascode bias.
The PTAT current is `ΔVBE/R1` and is independent of it.

### Disabled state (`EN` low, pre-POR)

`ENB` (the local inverse of `EN`) clamps every high-impedance node so the
cell is genuinely off rather than merely unbiased: `NBG` (`XMDNB`), the
`IBIAS` pin (`XMDIB`), the startup node `ND` (`XMDND`), the amplifier tail
`NT` (`XMDNT`), stage 1's output `N2` (`XMDN2`), and both output pads
(`XMENPT`, `XMENCT`). `XMENPG` pulls the mirror gate `PG` to `VDD`.

`XMDNT`/`XMDN2` were **added because the startup record caught their
absence**. Without them, `NT` and `N2` float when the tail is off; at the
`fs` corner (fast NMOS → low Vt) `N2` drifted above `XMS2N`'s threshold and
opened a `VDD → XMENPG → PG → XMS2N → VSS` path drawing **1.17 µA at
−40 °C while the cell was supposed to be off**. With the clamps, measured
across the full grid:

| Measurement | Result |
| --- | --- |
| Cell's own draw from its `VDD` pin, `EN` low | ≤ **0.69 nA** |
| `PTAT`, `CTAT` pad voltage, `EN` low | ≤ 52 µV (held at `VSS`, not floating) |
| Draw seen at the rail including the shunted `IBIAS` reference | 0.500 µA |

That last row is not this cell's current: `bias_core` sources 0.5 µA into the
`IBIAS` pin whether or not `temp_core` is enabled, and a disabled `temp_core`
clamps the pin to `VSS`, so the reference lands in the supply reading. It is
recorded here so #11/#14 budget it against the block Iq rather than
rediscovering it. If pre-POR block current matters, the fix belongs in
`bias_core` (gate its own output), not here.

## Startup

A ΔVBE loop has a degenerate zero-current solution as well as its intended
one. This cell's first revision detected "loop is dead" the obvious way — a
large NMOS with its gate on `NA`, the 1x PNP's VEB — and the designer-check
op grid **caught it sitting in the dead state** at `fs_-40c_2.97v`,
`res_ff_-15c_3.63v` and `res_ss_-40c_2.97v`: `V(NA) = 0.484 V` against
`V(NB) = 0.661 V`, amplifier railed, mirror off, `V(PTAT) = 24 mV`.

The root cause is not a sizing miss, it is that **no fixed voltage threshold
on `NA` can separate the two states across the rated range**: `NA` is a VBE,
a *dead* core's VBE at −40 °C (≈0.48 V) is *higher* than a *live* core's VBE
at 125 °C (≈0.46 V). An absolute-level detector cannot work here at all.

The detector is therefore **current-referenced**:

| Device | Size | Role |
| --- | --- | --- |
| `XMSU4` | pfet 1 µm/4 µm, gate `PG` | 1:8 replica of a mirror leg → ~0.31 µA alive, ~0 dead |
| `XMSU5` | nfet 2 µm/2 µm, diode | turns the replica current into a gate voltage `NR` |
| `XMSU2` | nfet 2 µm/2 µm, gate `NR` | mirrors it, pulling `ND` down |
| `XMSU1` | pfet 1 µm/8 µm, gate `PB` | ~25 nA `IBIAS`-referenced pull-up on `ND` |
| `XMSU3` | nfet 4 µm/1 µm, gate `ND` | the kick: pulls `PG` down |

Alive, `XMSU2` beats `XMSU1` by more than 10×, `ND` collapses, and the kick
contributes nothing to the operating point (measured `V(ND)` = 2.95–4.38 mV
across the whole grid). Dead, `XMSU4` delivers nothing, `ND` rises to `VDD`,
`XMSU3` pulls `PG` down and the loop starts. The comparison is *loop current
vs. IBIAS current* — both track over PVT, which is why the detector survives
corners an absolute-level detector cannot. It trips at roughly 8 % of nominal
loop current, so it also recovers from the partial-current state the old
detector got stuck in (~50 nA), not only from a true zero.

Cost: one 0.31 µA replica leg (see Iq budget).

`sim/temp-core-startup/` is the evidence that this actually works. Over 81
PVT points, each simulating VDD ramping from 0 V, POR releasing `EN`, then a
full rail collapse and restart:

| Measurement | Result |
| --- | --- |
| Time from `EN` release to `PTAT` crossing 0.5 V | 2.24 – 4.81 µs |
| `PTAT` after brownout restart vs. after cold start | **0 ppm** at every point |
| `CTAT` after brownout restart vs. after cold start | **0 ppm** at every point |

Bit-identical restart at every corner is the strong form of the claim: if the
loop could latch into its degenerate state, a rail collapse is where it would
do it.

## V(T) transfer and output range

Filling [`temp-vt-transfer`](../spec/target-spec.md#temp-vt-transfer). Both
pads are judged at their pin voltage through this characteristic (DR-002), so
an unstated slope makes the accuracy row unverifiable — which is why the spec
marks the row load-bearing.

| | `PTAT` | `CTAT` |
| --- | --- | --- |
| Characteristic | `V = K₀·T`, **K₀ = 4.308842 mV/K** (absolute temperature, line through the origin — *not* an offset-and-slope fit) | `V = VEB(Q1)`, **−1.86 mV/°C**, 0.6533 V at 27 °C |
| Value at −40 / 27 / 125 °C (tt, 3.3 V) | 1.0043 / 1.2933 / 1.7166 V | 0.7758 / 0.6533 / 0.4691 V |
| Range over the full 216-point grid | **1.0036 – 1.7174 V** | **0.4605 – 0.7823 V** |
| Source impedance | `R2` ≈ 516 kΩ | `XRISO` ≈ 20 kΩ |

`PTAT` passing through the origin is a property of the topology, not a fit:
`V(PTAT) = (R2/R1)·(k/q)·ln(8)·T` has no additive term. It is what makes the
one-point gain trim sufficient in principle — a single multiplicative
correction is the only degree of freedom a line through the origin has.

The spec's headroom bound (`0.2 V ≤ V(out) ≤ VDD − 0.2 V` at every corner) is
checked **per point** in the record as a single worst-of-four margin. Worst
case over the grid: **+260 mV** (`vout_margin_v`), at the hot end where
`V(PTAT)` is highest against a 2.97 V rail.

## Error budget

The sensitivity that governs everything below: with
`ΔVBE = c·T`, `c = 53.879 mV / 300.15 K = 179.5 µV/K`, the PTAT transfer
constant is `K0 = 4.308842 mV/K` (tt, 25 °C), so

```
1 mV at the PTAT pad          = 0.232 C
1 mV of amplifier input offset = 5.57 C untrimmed  (a pure gain error)
1 mV of amplifier input offset = 1.87 C at 125 C after a 25 C gain trim
```

That last line is the single most important number in this document, and it
is worth being blunt about: **a one-point gain trim does not remove input
offset, it only shortens its lever arm — by a factor of about 3.** Trimming
gain at 25 °C makes the output right at 25 °C; the residual error at another
temperature is `(Vos/c)·(T25−T)/T25`, which is ±1.87 °C/mV at 125 °C and
+1.21 °C/mV at −40 °C. Anything that claims a one-point trim "removes offset"
is wrong about this circuit.

### Correctable by the single 25 °C gain trim (gain/offset class)

Everything that scales `R2/R1` or adds a constant to `ΔVBE`.

| Term | Systematic, measured | Notes |
| --- | --- | --- |
| Resistor-ratio tolerance | `K(25 °C)` spans 4.30624–4.31086 mV/K across all 9 process corners × 3 supplies = **0.107 %** → **±0.16 °C** | same-flavour ratio; `res_ff`/`res_ss` move `R2` by ±21 % and move `K` by 0.03 % |
| Amplifier systematic offset | \|V(NA) − V(NB)\| ≤ **5.4 µV** → **±0.03 °C** | `XMS2N` as a current-density copy of `XML1` |
| Mirror-ratio error | inside the above | `XMP1`/`XMP2` see equal VGS *and* equal VDS |
| Supply sensitivity | **−0.054 … +0.014 °C** over the whole ±10 % window, worst point of the grid, against the ≤0.33 °C bound of [`temp-supply-sensitivity`](../spec/target-spec.md#temp-supply-sensitivity) → **16 % of that budget** | cascoded mirror; measured per-point against an identical DUT held at `vdd_nom`, not inferred across points |
| **Random mismatch** | **not visible here** | PNP `Is` mismatch, input-pair and mirror Vt mismatch. **Issue #15.** This is what the trim actually exists for. |

### *Not* correctable by a single-point trim

| Term | Measured | Notes |
| --- | --- | --- |
| Curvature / nonlinearity | **−0.094 … +0.256 °C** worst case over all 27 (corner, supply) combinations | residual after normalising each corner's own `K` at 25 °C; dominated by the +125 °C end |
| Trim quantisation | **±0.35 °C** (½ LSB, LSB = 0.71 °C) | a residual of the trim mechanism itself |
| Random offset residual after trim | **not visible here** | ±1.87 °C per mV of `Vos` at 125 °C. **Issue #15.** |

The curvature number is derived from the record's own per-corner table:
for each (corner, supply), `resid(T) = (K(T)/K(25 °C) − 1)·T`, which is
exactly the error a perfect 25 °C gain trim leaves behind. The 25 °C point is
in the temperature list for this purpose.

### Against the targets

| Spec row | Target | Systematic budget consumed | Left for mismatch (#15) |
| --- | --- | --- | --- |
| [`temp-accuracy-untrimmed`](../spec/target-spec.md#temp-accuracy-untrimmed) | ±3 °C **[3σ]** | **−0.230 … +0.422 °C** (`ff_-40c_2.97v` / `ss_125c_3.30v`), i.e. **14 %** | ±2.58 °C, i.e. `Vos(3σ) < 0.46 mV` |
| [`temp-accuracy-trimmed`](../spec/target-spec.md#temp-accuracy-trimmed) | ±1.5 °C **[3σ]** (stretch) | curvature ±0.256 °C + quantisation ±0.35 °C = **±0.61 °C**, i.e. **41 %** | ±0.89 °C, i.e. `Vos(3σ) < 0.48 mV` |

Both rows are `[3σ]` and `conditional #15` in `spec/target-spec.md` — they are
mismatch-inclusive by definition, and nothing here is. What this record does
is fix the systematic term so #15's Monte Carlo has a known amount of budget
to fit into, rather than an unknown one.

**The honest reading**: the systematic budget is comfortable at both targets
— DR-005's worry that curvature alone might eat the ±1.5 °C stretch does not
materialise, at 0.26 °C. But both targets now reduce to the *same* question,
random input-referred offset, and both want it under about 0.5 mV at 3σ.
That is not obviously achievable for a plain (unchopped) pair, and it is
precisely the number issue #15 has to produce.

If #15 shows `Vos(3σ)` above ~0.5 mV, the remedies in order of cost are:
(a) grow the input pair and the mirror devices — cheap in Iq, expensive in
area, and only √-effective; (b) trim finer (the ±23 °C range is far wider
than needed for a ±4 mV offset once mismatch is actually known, so
re-balancing range against LSB buys a smaller quantisation term without more
bits); (c) chopping, which DR-005 rejected for wave 1 on Iq and complexity
grounds and explicitly said to revisit if exactly this evidence appears.
This cell is deliberately built so that (b) is a resistor-length change and
(c) is a change at the amplifier's inputs, not a re-topology.

### Output loading — stated, not hidden

This cell has **no output buffer**. DR-005 puts the buffer in a separate
`temp_buffer` cell, and it is not in the ratified `temp_por_top` hierarchy
(`design/README.md`) for wave 1. `PTAT`'s source impedance is `R2` ≈ 516 kΩ
and `CTAT`'s is `XRISO` ≈ 20 kΩ.

Measured cost of that: a **10 MΩ** pad load pulls `PTAT` down by
**4.48–8.18 %**, i.e. by up to **19 °C**. So the pad specification is
**`Rload ≥ 1 GΩ`** (which the 1 TΩ measurement load bounds), and any consumer
that cannot meet it needs the `temp_buffer` cell. This is recorded as a
measurement rather than an argument so that #13's testbench suite and any
future ADC pairing (the DR-002 digital stretch) start from a number.

## Iq budget

Measured over the full 216-point grid, running, **including** the 0.5 µA
`IBIAS` reference the testbench pushes into the pin:

| | Value | At |
| --- | --- | --- |
| Minimum | **8.14 µA** | `ss_-40c_2.97v` |
| Typical | 10.70 µA | `tt_27c_3.30v` |
| **Maximum** | **16.27 µA** | `ff_125c_3.63v` |

Where it goes at tt/27 °C/3.3 V:

| Branch | Current |
| --- | --- |
| Three mirror legs (`XMP1/2/3`) at ΔVBE/R1 | 7.50 µA |
| Amplifier tail (`XMT`) | 1.00 µA |
| Amplifier second stage (`XMS2P`) | 0.50 µA |
| `IBIAS` reference into the pin (`bias_core`'s, not this cell's) | 0.50 µA |
| `PB` mirror leg (`XMBN1`/`XMBP`) | 0.50 µA |
| `PCAS` cascode-bias leg (`XMBN2`/`XMCB`) | 0.50 µA |
| Startup replica (`XMSU4`) | 0.31 µA |
| Startup pull-up (`XMSU1`) | 0.03 µA |
| **Total (predicted / measured)** | **10.84 / 10.70 µA** |

### Against the target ([`temp-iq`](../spec/target-spec.md#temp-iq))

- **`<20 µA` target: met**, with 19 % margin at the worst corner
  (`ff_125c_3.63v`, 16.27 µA — which is exactly the FF/+125 °C/3.63 V binding
  corner the spec row names). DR-005 estimated 5–15 µA for a plain core; the
  measured 8.1–16.3 µA lands on that estimate, slightly wide at the hot fast
  corner.
- The number above is **conservative against the row as written**.
  `spec/target-spec.md` §5 defines `temp-iq` as the *incremental* current
  above `por-iq`, and charges shared-bias-core branches that must be live
  before POR releases to `por-iq` instead. The 0.5 µA `IBIAS` reference is one
  of those, and it is counted here anyway. Charged the way §5 defines it,
  `temp-iq` would be **15.77 µA** at the binding corner. This record does not
  claim the smaller number, because how much of the shared core is live
  pre-POR is #11's to establish, not this cell's.
- **`<5 µA` stretch: not met, and not reachable by tuning this design.** The
  floor is structural: three mirror legs at 2.5 µA is 7.5 µA before the
  amplifier draws anything. Reaching 5 µA total needs branch currents near
  0.8 µA, which means `R1` ≈ 67 kΩ and `R2` ≈ 1.6 MΩ (about 5× the poly
  area of the present ladder) *and* a subthreshold-biased amplifier, i.e. the
  "dedicated low-power amplifier redesign" DR-005 named. DR-005 explicitly
  flags the stretch as "an optimization target for #9, not resolved here";
  this record resolves it as **a follow-up, with the specific blockers
  named** rather than leaving it open-ended.

  Note the interaction with the error budget: cutting the branch current 3×
  raises `R1`/`R2` 3×, which raises resistor thermal noise and mismatch
  sensitivity at exactly the moment the offset budget above is already the
  binding constraint. The stretch should not be attempted before #15
  quantifies mismatch.

## Reproducing the evidence

```bash
python3 design/netlist.py --check        # netlists match the schematics
python3 sim/build_tb.py --check          # testbench fragments match the netlists
python3 sim/run_corners.py temp-core-designer-check -j 8
python3 sim/run_corners.py temp-core-startup -j 8
```

The first two commands are the chain that ties an evidence record back to
`design/temp_core.sch`: `netlist.py --check` proves the exported netlist
reproduces from the schematic byte-for-byte, and `build_tb.py --check` proves
the simulated fragment is that netlist plus a committed stimulus file, not a
hand-inlined copy that has since drifted.

## Out of scope here, on purpose

- **Mismatch / Monte Carlo** — issue #15. Everything above is deterministic
  corners; the budget is written to hand #15 a specific target
  (`Vos(3σ) < ~0.5 mV`).
- **Full spec-row coverage** — issue #13. These two experiments are the
  designer-level check that the sizing closes, not the ratified-spec
  testbench suite.
- **Chopping** — DR-005 rejected it for wave 1 (Iq, clock, ripple). Not an
  oversight; see the error budget for the specific evidence that would
  reopen it.
- **Output buffer** — DR-005's separate `temp_buffer` cell, not in the
  wave-1 hierarchy. The pad load spec above is the consequence.
- **Layout matching** — issue #17. The 8:1 PNP array and the `R2/R1` ratio
  both want common-centroid/interdigitated treatment; nothing in this
  schematic prevents it, and the 8 discrete unit cells exist partly so that
  it is possible.
