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
| [`temp-vt-transfer`](../spec/target-spec.md#temp-vt-transfer) | nominal slope + output range, design intent | `PTAT` = +4.3088 mV/K through the origin, 1.004–1.717 V; `CTAT` = −1.86 mV/°C, 0.461–0.782 V. Headroom bound holds with +260 mV worst-case margin. |
| [`temp-trim-strategy`](../spec/target-spec.md#temp-trim-strategy) | trim *mechanism* | 6-bit binary-weighted short-out ladder on `R2`, metal-strapped in wave 1, fuse/OTP-ready. |

Both rows are filled in `spec/target-spec.md` itself as well; the register
entries are struck through there rather than deleted, so the audit trail from
"unset, owned by #9" to "filled" stays visible.

Every number in this file that is not a device dimension is taken from a
recorded evidence run, not estimated:

| Evidence | What it substantiates |
| --- | --- |
| [`sim/temp-core-designer-check/`](../sim/temp-core-designer-check/) — record `20260801-073732-8b7e57f` | PTAT/CTAT transfer, output headroom, supply sensitivity, systematic temperature error, Iq, disabled-state draw and the DR-010 high-impedance invariant, pad-load cost, trim range/LSB — 216-point PVT grid (9 corners × 8 temperatures × 3 supplies) |
| [`sim/temp-core-startup/`](../sim/temp-core-startup/) — record `20260801-073944-8b7e57f` | cold start from 0 V with EN gated by POR, pre-POR quiescent draw and the same invariant through the cold start, brownout restart — 81-point PVT grid (9 corners × 3 temperatures × 3 supplies) |
| [`sim/temp-por-top-release/`](../sim/temp-por-top-release/) — record `20260802-205904-bdc077d` (re-run on the post-#56 assembly; `20260801-074334-8b7e57f` measured it before `XMRLK`) | this cell inside the **full four-cell assembly**: that `RESETn` releases and thereby enables it, and that its disabled state no longer prevents that — 81-point PVT grid |
| [`sim/temp-accuracy-vt/`](../sim/temp-accuracy-vt/) — record `20260801-121458-660d016` (issue #13) | the **published, measured** numbers for `spec/target-spec.md`'s `temp-vt-transfer`, `temp-accuracy-untrimmed`, `temp-accuracy-trimmed` (derived), `temp-supply-sensitivity` and `temp-iq` rows, taken on the real four-cell assembly (`bias_core`-driven `IBIAS`, `RESETn`-gated enable) now that #41/DR-010 makes that path live — supersedes this cell's own idealised-500 nA-source numbers below as the ratified evidence, though those numbers land in the same neighbourhood (see each section) — 108-point PVT grid (9 corners × 4 temperatures incl. a 25 °C trim reference × 3 supplies) |

> **All four of those experiments have since been re-run against the
> post-layout extracted netlist (#83), and no check regressed.** Everything in
> this document up to
> ["Post-layout re-run (issue #83)"](#post-layout-re-run-issue-83) is
> schematic-level evidence and stays as it is; that section is the separate,
> appended answer to "does the drawn layout still do it?", with the four new
> record-ids, the parasitic loading on this cell's high-impedance nodes, and
> the exceptions [`layout/postlayout/AUDIT.md`](../layout/postlayout/AUDIT.md)
> puts on an `extracted` claim.

Both `temp_core` records were **re-run under
[DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md)**
and supersede the `20260731-*` pair, which was taken before the `IBIAS`
disabled-state clamp was deleted (`sim/` is append-only, so those records are
still on disk and still describe the netlist they were run against). Every
enabled-state number below is unchanged; what moved is confined to the
disabled branch and to startup timing, and is called out where it appears.

Both are **deterministic corner** records: `design.ngspice` sets
`sw_stat_mismatch=0`, so everything below bounds the **systematic** error
only. The random/mismatch share was issue #15's Monte Carlo job, and the
budget below is written so #15 knew exactly how much room it had left.

> **#15 has now run it, and the budget does not close.**
> [`sim/temp-accuracy-mc/`](../sim/temp-accuracy-mc/) — record
> `20260802-082345-989ce7a`, N = 500 local-mismatch samples at each of the
> four binding points, `sw_stat_mismatch=1` — measures
> **σ(`V_os`) = 0.93–1.02 mV**, i.e. **3.07 mV at 3σ against the ≈0.46 mV**
> this document's budget left for it (**6.7×**). Both accuracy rows miss:
> untrimmed **−19.23…+19.63 °C** against ±3 °C, trimmed **−7.08…+7.70 °C**
> against ±1.5 °C. The per-device attribution is
> [`…-breakdown.md`](../sim/temp-accuracy-mc/records/20260802-082345-989ce7a-breakdown.md);
> the spec consequence — targets kept, rows recorded as measured misses, fix
> routed to a design revision — is
> [DR-011](../spec/decision-records/DR-011-temp-accuracy-mismatch-not-met.md).
> **Everything below is still correct as a systematic bound; it is simply no
> longer the whole story.** The "Against the targets" section carries the
> mismatch-inclusive numbers.

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
across all 216 PVT points: **|V(NA) − V(NB)| ≤ 5.1 µV**. This matters
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

`ENB` (the local inverse of `EN`) clamps every high-impedance **internal**
node so the cell is genuinely off rather than merely unbiased: `NBG`
(`XMDNB`), the startup node `ND` (`XMDND`), the amplifier tail `NT`
(`XMDNT`), stage 1's output `N2` (`XMDN2`), and both output pads (`XMENPT`,
`XMENCT`). `XMENPG` pulls the mirror gate `PG` to `VDD`.

**The `IBIAS` pin is deliberately *not* among them
([DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md)).**
It used to be: an `ENB`-gated `XMDIB` (1 µm/1 µm) shorted the pin to `VSS`.
But `IBIAS` is a net shared with `por_comparator` and `por_output_chain`, and
`EN` **is** `RESETn` — so that clamp held the shared node at `VSS` for the
entire pre-POR window, starved `por_comparator`'s tail mirror, and made
`RESETn` unreleasable, which in turn kept this cell disabled and the clamp
engaged. A closed bias-vs-POR lockup, measured at all 81 PVT points by
`sim/bias-core-ibias-sharing/`. DR-010 deletes the clamp and rules that a
**disabled consumer of a shared bias node presents high impedance to it**.
`XMPASS` (off) and `XMDNB` (`NBG` → `VSS`) already turn the local mirror off,
so no additional device is needed: the pin is high-Z, and the node's operating
point is set by `por_output_chain`'s always-on diode-connected `XMBD`.

`XMDIB` existed to give a *forced* current somewhere to go when a single-cell
testbench drives the pin from an ideal source with `EN` low — a testbench
condition, never a system one. Since DR-010 those testbenches terminate the
forced reference themselves (`xmshd` / `xmsh`, a diode-connected `nfet_03v3`
4 µm/4 µm standing in for the rest of the shared net).

`XMDNT`/`XMDN2` were **added because the startup record caught their
absence**. Without them, `NT` and `N2` float when the tail is off; at the
`fs` corner (fast NMOS → low Vt) `N2` drifted above `XMS2N`'s threshold and
opened a `VDD → XMENPG → PG → XMS2N → VSS` path drawing **1.17 µA at
−40 °C while the cell was supposed to be off**. With the clamps, measured
across the full grid:

| Measurement | Result |
| --- | --- |
| Cell's own draw from its `VDD` pin, `EN` low | ≤ **0.69 nA** |
| `PTAT`, `CTAT` pad voltage, `EN` low | ≤ **53 nV** (held at `VSS`, not floating) |
| Current the disabled cell takes **out of the shared `IBIAS` node** | ≤ **0.152 nA** (`ibias_dis_na`) |
| Shared `IBIAS` node with this cell disabled on it | **0.499–0.873 V** (`vibias_dis_v`) — a diode drop, not `VSS` |
| Draw seen at the rail including the `IBIAS` reference | 0.500 µA |

The last three rows are the DR-010 contract as numbers. The first two are the
high-impedance invariant: the disabled cell takes 0.03 % of the 0.5 µA `IBIAS`
convention and does not drag the node down, so the whole reference stays
available to `por_comparator` and `por_output_chain` in exactly the state POR
has to work in. Both are checked at every corner
(`sim/temp-core-designer-check/`, bound 25 nA / 0.3 V), so a future edit that
re-introduces a clamp fails a corner run rather than passing review.

The last row is not this cell's current: `bias_core` sources 0.5 µA into the
`IBIAS` net whether or not `temp_core` is enabled, and the single-cell
testbenches meter it on the same rail, so the reference lands in the supply
reading. It is recorded here so #11/#14 budget it against the block Iq rather
than rediscovering it. **Note the change of destination since DR-010**: that
current is no longer thrown into a clamp here — in the assembled block it
reaches the POR consumers that need it. It is still spent (it is `por-iq`'s
single largest line item, `design/bias_core.md` "Iq apportionment"), but it is
now spent *on the POR decision* rather than wasted. Gating it off at the source
is not the remedy: see DR-010's "Alternatives considered".

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
| Time from `EN` release to `PTAT` crossing 0.5 V | 2.91 – 7.06 µs |
| `PTAT` after brownout restart vs. after cold start | **−0.58 … 0 ppm** (bound ±100 ppm) |
| `CTAT` after brownout restart vs. after cold start | **0 ppm** at every point |

Restart agreement to well under 1 ppm at every corner is the strong form of the
claim: if the loop could latch into its degenerate state, a rail collapse is
where it would do it.

> **These two rows moved under DR-010** (they read 2.24–4.81 µs and 0 ppm
> before). Not a design change — a **modelling** change, and a more honest one.
> Deleting the `IBIAS` clamp means this cell no longer defines the shared node,
> so the testbench now terminates the forced reference in `xmsh`, a stand-in
> for the rest of the shared net. The reference is therefore *shared* with that
> stand-in instead of being handed to the DUT whole, which is what the
> assembled block actually does — `por_comparator` and `por_output_chain` are
> real consumers of the same 0.5 µA. Less bias current into this cell's local
> mirror means a slower kick, hence the longer start times. The old numbers
> flattered the cell by giving it a reference no system would give it.

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

**Confirmed on the real assembled path (#13, `sim/temp-accuracy-vt/`,
`bias_core`-driven `IBIAS` rather than this idealised 500 nA source):** K₂₅ =
4.304–4.30756 mV/K, CTAT slope −1.88424…−1.82384 mV/°C, output range
1.00329–1.71599 V / 0.460507–0.782332 V, worst headroom margin **+260.507 mV**
at the *same* binding corner (`bjt_ff_125c_2.97v`). The idealised-source
numbers above are not an approximation the real block departs from — they
hold to within measurement precision.

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
| Amplifier systematic offset | \|V(NA) − V(NB)\| ≤ **5.1 µV** → **±0.03 °C** | `XMS2N` as a current-density copy of `XML1` |
| Mirror-ratio error | inside the above | `XMP1`/`XMP2` see equal VGS *and* equal VDS |
| Supply sensitivity | **−0.054 … +0.014 °C** over the whole ±10 % window, worst point of the grid, against the ≤0.33 °C bound of [`temp-supply-sensitivity`](../spec/target-spec.md#temp-supply-sensitivity) → **16 % of that budget** | cascoded mirror; measured per-point against an identical DUT held at `vdd_nom`, not inferred across points |
| **Random mismatch** | **not visible here** — **measured by #15**: σ(`V_os`) 0.93–1.02 mV, σ(gain `R2/R1`×mirror) 0.54–1.05 %, σ(Δ`V_BE`) 0.18–0.20 mV | PNP `Is` mismatch, input-pair and mirror Vt mismatch. **Issue #15**, `sim/temp-accuracy-mc/` record `20260802-082345-989ce7a-breakdown`. This is what the trim actually exists for — and, per that record, the trim removes the gain and Δ`V_BE` terms but not `V_os`. |

### *Not* correctable by a single-point trim

| Term | Measured | Notes |
| --- | --- | --- |
| Curvature / nonlinearity | **−0.094 … +0.256 °C** worst case over all 27 (corner, supply) combinations | residual after normalising each corner's own `K` at 25 °C; dominated by the +125 °C end |
| Trim quantisation | **±0.35 °C** (½ LSB, LSB = 0.71 °C) | a residual of the trim mechanism itself |
| Random offset residual after trim | **not visible here** — **measured by #15**: σ = 1.05–1.75 °C from `V_os` alone, plus 0.68–1.11 °C of curvature the linear attribution does not explain | ±1.87 °C per mV of `Vos` at 125 °C — **confirmed on 500 dice per point**, empirical lever +1.94/+2.02 °C/mV hot, −1.32/−1.34 °C/mV cold. **Issue #15**, record `20260802-082345-989ce7a-breakdown`. |

The curvature number is derived from the record's own per-corner table:
for each (corner, supply), `resid(T) = (K(T)/K(25 °C) − 1)·T`, which is
exactly the error a perfect 25 °C gain trim leaves behind. The 25 °C point is
in the temperature list for this purpose.

### Against the targets

| Spec row | Target | Systematic budget consumed | Left for mismatch (#15) |
| --- | --- | --- | --- |
| [`temp-accuracy-untrimmed`](../spec/target-spec.md#temp-accuracy-untrimmed) | ±3 °C **[3σ]** | **−0.230 … +0.422 °C** (`ff_-40c_2.97v` / `ss_125c_3.30v`), i.e. **14 %** | ±2.58 °C, i.e. `Vos(3σ) < 0.46 mV` |
| [`temp-accuracy-trimmed`](../spec/target-spec.md#temp-accuracy-trimmed) | ±1.5 °C **[3σ]** (stretch) | curvature ±0.256 °C + quantisation ±0.35 °C = **±0.61 °C**, i.e. **41 %** | ±0.89 °C, i.e. `Vos(3σ) < 0.48 mV` |

Both rows are `[3σ]` in `spec/target-spec.md` — they are mismatch-inclusive by
definition, and nothing in the two columns above is. What this record does is
fix the systematic term so #15's Monte Carlo had a known amount of budget to
fit into, rather than an unknown one.

**#15's Monte Carlo has now filled the fourth column, and it overflows.**
Measured at the four binding points these rows name, N = 500 local-mismatch
samples each (`sim/temp-accuracy-mc/`, record `20260802-082345-989ce7a`):

| Spec row | Target | Budget left for mismatch | Mismatch **measured** | Verdict |
| --- | --- | --- | --- | --- |
| [`temp-accuracy-untrimmed`](../spec/target-spec.md#temp-accuracy-untrimmed) | ±3 °C **[3σ]** | ±2.58 °C, i.e. `Vos(3σ) < 0.46 mV` | σ = 6.08–6.48 °C ⇒ **−19.23…+19.63 °C at 3σ**; `Vos(3σ)` = **3.07 mV** | **not met, 6.5×** |
| [`temp-accuracy-trimmed`](../spec/target-spec.md#temp-accuracy-trimmed) | ±1.5 °C **[3σ]** | ±0.89 °C, i.e. `Vos(3σ) < 0.48 mV` | σ = 1.49–2.46 °C ⇒ **−7.08…+7.70 °C at 3σ** | **not met, 4.9×** |

Per-device attribution of the untrimmed σ
([`…-breakdown.md`](../sim/temp-accuracy-mc/records/20260802-082345-989ce7a-breakdown.md);
the three terms come out of the measurements algebraically, and their
root-sum-square lands within 2.1–5.0 % of the directly-measured σ):

| Term | Devices | σ | σ-share of the untrimmed error | 3σ vs ±3 °C |
| --- | --- | --- | --- | --- |
| Amplifier offset `V_os` | `XMI1`/`XMI2`, `XML1`/`XML2` | 0.93–1.02 mV | 5.18–5.71 °C | **518–571 %** |
| Gain `A = R2/R1` × mirror | `XR1`/`XR2*`, `XMP1`/`XMP2`/`XMP3` | 0.54–1.05 % | 2.16–2.44 °C | **216–244 %** |
| PNP pair Δ`V_BE` | `XQ1` vs `XQ8A..H` | 0.18–0.20 mV | 1.00–1.11 °C | **100–111 %** |

**Two things in that table were not in this document's prediction.** First,
`V_os` is 6.7× over its budget rather than marginally over — the paragraph
below called that outcome "not obviously achievable", and it is not achieved.
Second, and more consequentially, **`V_os` is not the only term over budget**:
the gain term alone is 216–244 % of the untrimmed window, so remedy (a)/(c)
below closes the dominant term without closing the row. `spec/target-spec.md`
records both rows as measured misses with their targets intact, under
[DR-011](../spec/decision-records/DR-011-temp-accuracy-mismatch-not-met.md).

**#13's assembled-path numbers (`sim/temp-accuracy-vt/`, `bias_core`-driven
`IBIAS`) land in the same neighbourhood**: untrimmed **−0.335…+0.099 °C**
(11 % of budget), trimmed curvature+quantisation **−0.346…+0.847 °C** (56 %).
These are the *published* numbers `spec/target-spec.md` cites; the two-cell
idealised-source figures above remain useful as the designer-level sanity
check that motivated this cell's sizing.

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

**It did, so here is what those remedies now cost against measured numbers**
(the full argument, and the reasons none of them is *chosen* here, are in
[DR-011](../spec/decision-records/DR-011-temp-accuracy-mismatch-not-met.md)):

- **(a) grow the pair/mirror.** σ(`V_os`) falls as 1/√(WL); 3.07 mV → 0.46 mV
  is a 6.7× σ reduction, i.e. **≈45× the area** of `XMI1`/`XMI2`/`XML1`/`XML2`.
  Not viable against [`area`](../spec/target-spec.md#area) alone.
- **(b) re-balance the trim ladder.** Still worth doing — it shrinks the
  ±0.28/±0.48 °C quantisation term measured above at no extra bits — but the
  quantisation term is nowhere near the binding one, so it is a refinement,
  not a fix.
- **(c) chop or auto-zero.** DR-005's "revisit if exactly this evidence
  appears" condition is met. It removes the dominant untrimmed term. It does
  **not** on its own close either row: the gain term survives it (216–244 %
  of the untrimmed window), and on the trimmed row the ½-LSB quantisation plus
  0.68–1.11 °C of unexplained curvature still leave ≈3.6 °C at 3σ.
- **(d) new, and not on the original list: fix the gain term.** The
  `XMP1`/`XMP2`/`XMP3` mirror's V_th mismatch — not the `R2/R1` ratio, whose
  same-flavour poly matches far better than 1 % at these areas — is the likely
  bulk of σ(`A`), and its temperature dependence is the most plausible source
  of the trimmed row's unexplained residue. Longer/degenerated mirror devices
  and a common-centroid `XR1`/`XR2*` layout (#17) are needed **whichever**
  amplifier remedy is chosen.

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
  **#13 confirms the estimate on the real assembled path**: incremental
  `temp-iq`, measured the way §5 actually defines it (post-release minus the
  reset-asserted draw, `sim/temp-accuracy-vt/`), is **15.90 µA** at
  `ff_125c_3.63v` — 1 % from this bottom-up estimate — and **5.80…15.90 µA**
  over the full grid. That is the *published* number `spec/target-spec.md`
  now cites for `temp-iq`.
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
python3 sim/run_corners.py temp-core-designer-check
python3 sim/run_corners.py temp-core-startup
python3 sim/run_corners.py temp-por-top-release   # this cell in the assembly
python3 sim/run_corners.py temp-accuracy-vt       # #13's published measured evidence
python3 sim/temp-accuracy-vt/analyze_derived.py <record-id> --write   # temp-accuracy-trimmed
```

Both the `temp-por-top-release` and `temp-accuracy-vt` runs exit non-zero **by
design**: the assembled block carries [`por-iq`](../spec/target-spec.md#por-iq)
(needed as the incremental `temp-iq` subtrahend) and that row misses its own
target, an overrun `design/bias_core.md` owns and DR-010 does not address.
Every check this cell's own rows own passes.

The first two commands are the chain that ties an evidence record back to
`design/temp_core.sch`: `netlist.py --check` proves the exported netlist
reproduces from the schematic byte-for-byte, and `build_tb.py --check` proves
the simulated fragment is that netlist plus a committed stimulus file, not a
hand-inlined copy that has since drifted.

## Out of scope here, on purpose

- **Mismatch / Monte Carlo** — issue #15. Everything above is deterministic
  corners; the budget is written to hand #15 a specific target
  (`Vos(3σ) < ~0.5 mV`).
- **Full spec-row coverage** — issue #13, **delivered**
  (`sim/temp-accuracy-vt/`). The two experiments above remain the
  designer-level, idealised-source check that the sizing closes; they are not
  the ratified-spec testbench suite, which runs on the real assembled path.
- **Chopping** — DR-005 rejected it for wave 1 (Iq, clock, ripple). Not an
  oversight; see the error budget for the specific evidence that would
  reopen it.
- **Output buffer** — DR-005's separate `temp_buffer` cell, not in the
  wave-1 hierarchy. The pad load spec above is the consequence.
- **Layout matching** — issue #17. The 8:1 PNP array and the `R2/R1` ratio
  both want common-centroid/interdigitated treatment; nothing in this
  schematic prevents it, and the 8 discrete unit cells exist partly so that
  it is possible. **The post-layout section below does not close this**: an
  extracted netlist carries interconnect R/C and drawn device dimensions, not
  gradient, stress or orientation effects, so "extraction changes nothing" is
  a statement about loading, not about matching.

## Post-layout re-run (issue #83)

Everything above is against the schematic export
(`design/netlist/temp_core.spice`, and `temp_por_top.spice` for the assembled
path). Issue #83 re-ran all four temp-sensing-domain testbenches against the
real klt-extracted netlists — `layout/postlayout/temp_core.spice` and
`layout/postlayout/temp_por_top.spice`, produced by #82/PR #180's
direct-extraction flow — using the sibling `testbench-postlayout/` mechanism
#86 established (a `POSTLAYOUT_FRAGMENTS` entry in `sim/build_tb.py` plus a
hand-authored manifest beside the existing `testbench/`). None of the
schematic-level records above is touched, and none of the numbers above is
restated or corrected: this section is the separate question #18 asks, *does
the drawn layout still do it?*

**What the extracted netlist is, and is not.** `temp_core` comes out as
**115 drawn devices at their drawn dimensions** (27 `nfet_03v3`, 28
`pfet_03v3`, 9 `pnp_10p00x10p00`, 50 `ppolyf_u`, 1 `cap_mim_2f0_m3m4_noshield`)
with first-order interconnect R/C on 69 of 73 nets (**ΣC = 1552.3 fF**), net
names restored through `klt lvs`'s 73/73 verified correspondence; `temp_por_top`
the same for all four cells (239 devices, ΣC = 5900.6 fF). Per
[`layout/postlayout/AUDIT.md`](../layout/postlayout/AUDIT.md), one thing is
*not* the layout's:

- Four body/well/plate nets (`NW1`→`VDD`, `NW2`→`NT`, `NWQ`→`VSS`,
  `vsubs`→`VSS`; 9 in the assembly) are tied where the **schematic** puts
  them, because the extraction deck's connectivity stack does not reach an
  Nwell, a substrate ring or a bipolar base well — they extract isolated and
  would otherwise float.

That is a shorter list than #83's original re-run worked with: `XCC`, the
12 × 12 µm MiM compensation cap on `PG`/`NZ`, was reserved floor area in
`temp_core`'s layout at that point and the netlist spliced it back in at its
schematic value so the deck was simulatable at all — so anything in that
original re-run that turned on the amplifier's compensation was a schematic
claim, not a post-layout one.

> **Update, 2026-08-19 (#259, #270).** `XCC` is now drawn and routed onto
> `PG`/`NZ` ([DR-028](../spec/decision-records/DR-028-temp-core-xcc-draw-it.md)):
> `temp_core` extracts 115/115 devices and `AUDIT.md` reports no ideal device
> anywhere. All four records below have been **re-run** against that netlist
> (#270) — the table now cites the re-run records, taken against a clean
> working tree so they carry no dirty-tree citation caveat either. The
> pre-#259 records they supersede stay on disk, still correctly stamped with
> the ideal-splice caveat that was accurate when they were taken:
> [`sim/temp-core-designer-check/…/20260811-075055-b06af8e.md`](../sim/temp-core-designer-check/records/20260811-075055-b06af8e.md),
> [`sim/temp-core-startup/…/20260811-074657-7c1c116.md`](../sim/temp-core-startup/records/20260811-074657-7c1c116.md),
> [`sim/temp-accuracy-vt/…/20260811-084152-68c0017.md`](../sim/temp-accuracy-vt/records/20260811-084152-68c0017.md),
> [`sim/temp-accuracy-mc/…/20260811-090721-3ec259f.md`](../sim/temp-accuracy-mc/records/20260811-090721-3ec259f.md).

Everything else — MOS, vertical PNP and poly resistor bodies alike — is a real
extraction of drawn geometry. `temp_core` needs none of the device-model
substitutions AUDIT.md records for the cells that use `ppolyf_u_1k` or MiM
caps; the assembly inherits 27 resistor and 8 MiM name-only substitutions from
its other three cells, on drawn geometry that is the schematic's either way.

### The four records

| Evidence (`Netlist provenance: extracted`) | Result | vs. schematic baseline |
| --- | --- | --- |
| [`sim/temp-core-designer-check/…/20260819-172959-fd167d8.md`](../sim/temp-core-designer-check/records/20260819-172959-fd167d8.md) | **PASS**, 216/216 points | unchanged — no check regressed |
| [`sim/temp-core-startup/…/20260819-170120-47d2f2a.md`](../sim/temp-core-startup/records/20260819-170120-47d2f2a.md) | **PASS**, 81/81 points | unchanged — no check regressed |
| [`sim/temp-accuracy-vt/…/20260819-173345-2a37d6c.md`](../sim/temp-accuracy-vt/records/20260819-173345-2a37d6c.md) (+ `-derived`) | FAIL on [`por-iq`](../spec/target-spec.md#por-iq) only, 108/108 points | unchanged — that row already failed at schematic level ([Iq apportionment is `design/bias_core.md`'s](../design/bias_core.md), #14's row, carried here only as the `temp-iq` subtrahend) |
| [`sim/temp-accuracy-mc/…/20260819-171829-b403a17.md`](../sim/temp-accuracy-mc/records/20260819-171829-b403a17.md) (+ `-breakdown`) | FAIL | unchanged — the same [DR-011](../spec/decision-records/DR-011-temp-accuracy-mismatch-not-met.md) mismatch miss, on the same eight (binding point, measurement) pairs |

Each of these four records is #270's re-run of the corresponding row in
#83's original table (above), against the netlist with `XCC` drawn, and
supersedes both that pre-#259 extracted record and (transitively) the
schematic-level record underneath it. The three corner-sweep records are each
paired with a `<record-id>-postlayout-delta` derived record — re-derived by
#270 against the *same* schematic baseline #83 used, so the comparison is a
direct extracted-vs-schematic delta rather than an extracted-vs-extracted one
— `sim/postlayout_delta.py` joins the two grids on corner-id and re-evaluates
the experiment's own `tb.json` checks against both.

### **Zero regressions.**

Across all four experiments, **no check that passed on a schematic-level
record fails on the extracted one.** The single `MISS` in the set
(`iq_por_ua`) is classified `MISS -> MISS`: the schematic-level record already
carried it, so it is not a post-layout finding, and it is not re-opened here.
Nothing in `spec/target-spec.md` moved, and nothing needed to.

### Parasitic loading on the high-impedance nodes

#18's acceptance criteria ask for this explicitly rather than folded into a
pass/fail. Read out of the extracted netlist (`layout/postlayout.py` models
each net's drawn interconnect as one lumped series R to a `<net>__par` stub
with a lumped C to `VSS`, so the loading a node sees is its own row); the full
table is in each delta record.

| Node | Why it matters | ΣC | ΣR |
| --- | --- | --- | --- |
| `PTAT` | the output pad, `R2` ≈ 516 kΩ source impedance, no buffer | 39.5 fF | 962 Ω |
| `CTAT` | the output pad, `XRISO` ≈ 20 kΩ | 32.4 fF | 509 Ω |
| `NA` / `NB` | the amplifier inputs — `V(NA) = V(NB)` *is* the measurement | 63.1 / 43.5 fF | 2133 / 2057 Ω |
| `NC` | `R1`'s bottom node into the 8× PNP array — not high-impedance itself, listed because the PTAT term is the voltage `V(NB) − V(NC)` across `R1` | 85.4 fF | 66 Ω |
| `PG` | the mirror gate = the amplifier's output node (and one `XCC` plate) | 61.7 fF | 5100 Ω |
| `NZ` | the other `XCC` plate | 29.3 fF | 106 Ω |
| `PB` / `PCAS` | bias gate nodes, capacitively loaded only | 47.2 / 53.7 fF | 3536 / 4549 Ω |
| `ND` / `NR` | the startup kick pair | 34.8 / 35.4 fF | 1513 / 1695 Ω |
| `IBIAS` | the DR-010 shared node | 20.3 fF | 323 Ω |

Cell total 1552.3 fF over 69 nets. In the assembled `temp_por_top` the shared
`IBIAS` net grows to **122.6 fF / 10.6 kΩ** because it spans all four cells,
`RESETn` carries 78.0 fF / 5.6 kΩ, and the assembly totals 5880.2 fF over 136
nets.

**None of that is enough to move a spec row, and the reason is structural**:
every quantity these four experiments measure is a DC operating point or a
microsecond-to-millisecond transient. The worst case here is `PTAT` — 39.5 fF
against a 516 kΩ source impedance, a **20 ns** pole — two orders of magnitude
below the 3–5 µs sensor start and six below the 1–17 ms reset release.

### What the parasitics did do

| Quantity | Schematic | Extracted | Δ |
| --- | --- | --- | --- |
| Systematic untrimmed error (cell) | −0.230 … +0.422 °C | −0.065 … +0.554 °C | **+0.19 °C**; 14 % → 18 % of ±3 °C |
| Systematic untrimmed error (assembly, #13's published row) | −0.335 … +0.099 °C | −0.156 … +0.248 °C | **+0.19 °C**; 11 % → 8 % of ±3 °C |
| After the 25 °C gain trim (derived) | −0.346 … +0.847 °C | −0.325 … +0.798 °C | −0.05 °C; 56 % → **53 %** of ±1.5 °C |
| Amplifier systematic offset `V(NA)−V(NB)` | −5.06 … +4.26 µV | −5.80 … +4.67 µV | +0.74 µV; still ~17× inside the ±100 µV check |
| Supply sensitivity, per point | −0.089 … +0.034 °C | −0.093 … +0.037 °C | +4.5 %; 28 % of the ±0.33 °C bound |
| Worst output headroom margin | +260.507 mV | +260.422 mV | −0.085 mV |
| `temp-iq`, incremental | 5.80 … 15.90 µA | 5.79 … 15.87 µA | −0.24 % |
| **`RESETn` release time** | 5.61 … 16.95 ms | 5.73 … 17.29 ms | **+1.99 %** |
| 10 MΩ pad-load gain error | −8.18 … −4.48 % | −8.20 … −4.49 % | +0.4 % |
| DR-010 disabled draw from `IBIAS` | 0.00126 … 0.152 nA | 0.00126 … 0.153 nA | +0.25 %, against a 25 nA bound |

Two rows are worth reading twice:

- **The +0.19 °C shift in the untrimmed systematic error is a real, and
  benign, consequence of the drawn resistors.** It is a *gain* shift —
  `K(25 °C)` moves by +0.07 % — and it appears identically on the cell and on
  the assembly, which is what an `R2/R1` ratio effect should do. It is
  therefore in the class the ratified one-point 25 °C trim removes, which is
  why the *trimmed* row moves the other way (56 % → 53 % of budget) even as
  the untrimmed one grows. It is nowhere near binding either way: the mismatch
  share DR-011 records dominates the untrimmed row by ~35× (±20 °C at 3σ
  against 0.55 °C systematic) and the trimmed row by ~9× (±7.4 °C against
  0.80 °C).
- **The +1.99 % reset release time is the one place the drawn interconnect
  genuinely bites.** It is the same +2.0 % `layout/postlayout/SMOKE.md`
  measured on this assembly at the nominal point, now confirmed across the
  whole PVT grid, and it stays inside the 1–25 ms liveness bound with room to
  spare. It belongs to `por_output_chain`'s timing capacitors, not to this
  cell.

### What this does **not** establish

- **Loop stability.** As of #270's re-run (table above), all four records are
  taken against a netlist where `XCC` is drawn and routed onto `PG`/`NZ`
  rather than spliced in ideal (#259, DR-028) — `layout/postlayout/AUDIT.md`
  reports no ideal device in `temp_core`. That establishes the **closed-loop
  transient behaviour** these testbenches actually exercise — cold-start
  settling (`start_us`), freedom from a degenerate non-converging state, and
  the settled DC operating point — through the real drawn compensation cap
  rather than a schematic-value splice, and every one of those measurements
  is unchanged from both the schematic baseline and the pre-#259 extracted
  predecessor to within their per-corner delta tables (the paired
  `<record-id>-postlayout-delta` records above show **zero regressions**
  across all four experiments).

  **#274 has since closed the remaining gap**:
  [`sim/temp-core-loop-stability/`](../sim/temp-core-loop-stability/) —
  record `20260819-182610-a4eebe7` — is this repo's first small-signal `.ac`
  testbench, breaking the loop at `PG` exactly as the "Error amplifier"
  section above describes it: the amplifier's own output stays on `PG`
  (`XMS2N`/`XMS2P` drains, the `XCC`/`XRZ` compensation network), and only
  the two mirror-gate connections that actually close the loop — `XMP1` and
  `XMP2`'s gates, back through `NA`/`NB` — move to a new node the testbench
  injects an AC test signal onto (`XMP3`'s gate, the dead-end `PTAT`-readout
  leg, is left on `PG`, since it does not feed back into the amplifier's own
  inputs). Across the full 81-point PVT grid:

  | Measurement | Min | Max |
  | --- | --- | --- |
  | Unity-gain crossover | 0.720 MHz (`res_ff_125c_2.97v`) | 1.640 MHz (`res_ss_-40c_3.63v`) |
  | Phase margin | **34.2°** (`ff_-40c_2.97v`) | **47.1°** (`ss_27c_3.63v`) |
  | Gain margin | **4.43 dB** (`res_ss_-40c_3.63v`) | **7.50 dB** (`res_ff_125c_2.97v`) |

  The loop-break technique's own DC operating point was verified identical to
  the closed loop at every one of the 81 points (`V(PG)` and the injection
  node differ by exactly 0 mV, `checks.dc_bias_delta_mv` in the record), and
  the DC `V(PTAT)`/`V(CTAT)` values it reports at `tt`/27 °C/3.3 V — 1.29334 V
  / 0.65335 V — match `sim/temp-core-designer-check/`'s own clean-tree
  schematic-level record (`20260731-230435-80f0981`: 1.293341 V / 0.653347 V)
  to better than 1 ppm. This is a **schematic-level** record
  (`design/netlist/temp_core.spice`, which already carries #259/DR-028's real
  drawn `XCC` dimensions); a post-layout re-run against the extracted netlist
  is out of scope here and can follow the same pattern the other four
  `temp_core` testbenches already use, if/when a concrete margin bound makes
  the extracted delta worth measuring.

  **No target bound is ratified against these numbers.** Per #274's own
  scoping question, promoting a specific phase/gain-margin requirement to
  `spec/target-spec.md` is left as a separate, deliberate decision (its own
  decision record) for whenever one is actually needed — nothing in either
  this record or the transient records above shows evidence of an actual
  instability problem; the worst-case 34.2° margin is measured at the
  fast-process, coldest, lowest-supply corner, which is also the corner every
  other `temp_core` record already treats as its hardest case, not a
  surprise this record newly discovered.
- **Mismatch as a layout property.** The post-layout Monte Carlo record
  re-measures the local-mismatch distribution and finds it unchanged —
  σ(`V_os`) 0.922–0.996 mV against 0.930–1.025 mV schematic, untrimmed 3σ
  −19.12…+20.44 °C against −19.23…+19.63 °C. That is the expected result
  (local mismatch is a property of the PDK's statistical device models, which
  apply to the same drawn devices either way, and interconnect loading is not
  a mismatch term) and it is worth having recorded rather than assumed:
  **DR-011's conclusion survives extraction intact.** What it does *not* cover
  is layout-*dependent* matching — common-centroid placement of the 8:1 PNP
  array and the `R2`/`R1` ladder, gradient, stress and orientation effects.
  Those are #17's, and no netlist-level extraction can see them.
- **Anything resting on a body-tie assumption**, per the four ties listed
  above.

### Reproducing the post-layout evidence

```bash
python3 layout/postlayout.py --check      # the extracted netlists are current
python3 sim/build_tb.py --check           # the fragments are those netlists + stimulus
python3 sim/run_corners.py sim/temp-core-designer-check/testbench-postlayout
python3 sim/run_corners.py sim/temp-core-startup/testbench-postlayout
python3 sim/run_corners.py sim/temp-accuracy-vt/testbench-postlayout
python3 sim/run_mc.py     sim/temp-accuracy-mc/testbench-postlayout
python3 sim/temp-accuracy-vt/analyze_derived.py <record-id> --write
python3 sim/temp-accuracy-mc/analyze_breakdown.py <record-id> --write
python3 sim/postlayout_delta.py <slug> <extracted-id> --against <schematic-id> \
    --high-z PTAT,CTAT,NA,NB,NC,PG,NZ,PB,PCAS,ND,NR,NT,IBIAS --write
```

The post-layout runs take a *testbench directory*, not the bare slug: a bare
slug resolves to the schematic `testbench/` sibling, which is the point of
keeping both. `postlayout_delta.py` exits non-zero if any check regressed from
the schematic-level record to the extracted one, so a regression cannot be
scrolled past; on this cell it exits 0.
