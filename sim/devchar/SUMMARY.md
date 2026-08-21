# Device characterization summary (issue #4)

Evidence for the vertical-PNP, resistor-flavor, and MOS device sweeps this
block's PTAT/CTAT sensing core, POR divider/comparator, and bias branches
stand on. Per CLAUDE.md ("no claim without a testbench"), every number
below is sourced from a recorded `sim/devchar/results/*.csv` row, not
estimated -- the estimates in `spec/decision-records/DR-005-*.md` are the
things this evidence is meant to confirm or correct.

## Environment

- **PDK**: gf180mcuD, installed via volare (commit
  `c6d73a35f524070e85faff4a6a9eef49553ebc2b`), model file
  `libs.tech/ngspice/sm141064.ngspice` + `design.ngspice` (sets
  `sw_stat_global=0`, `sw_stat_mismatch=0` -- deterministic, no Monte Carlo).
- **ngspice**: 46.
- **Rail**: 3.3 V nominal, +-10 % (2.97-3.63 V), per
  `spec/decision-records/DR-001-supply-flavor.md`.
- **Temperature grid**: -40, -15, 10, 27, 60, 90, 125 C (7 points, covers
  the CLAUDE.md -40/27/125 minimum with enough resolution for a linear-fit
  slope).
- Every CSV row carries its own `pdk_variant`, `ngspice_version`, `corner`,
  `temp_c`, and a `raw_ref` pointing at the per-run raw ngspice log +
  `wrdata` dump under `results/raw/<run_id>/`. This is the "minimal fields"
  fallback from the issue's Implementation Guidance -- `spec/`'s
  `spec/decision-records/` convention had landed by the time this ran, but
  issue #5 (evidence-record format) had not; reconcile format if #5 lands
  with a different shape.
- **Reproducibility**: two independent runs (`run_devchar.py` full grid,
  then `--quick`) are both present in the CSVs; every overlapping
  (corner, temp, device/flavor) row matches exactly between runs (0
  mismatches across 225 compared keys) -- deterministic given
  `sw_stat_mismatch=0`.

## How to reproduce

```
cd sim/devchar
./run_devchar.sh --quick      # -40/27/125 C only, ~1 min
./run_devchar.sh              # full 7-point grid, ~3 min
```

`PDK_ROOT` (default `~/.volare`) and `NGSPICE` env vars override the tool
locations. Runs **append** to `results/*.csv` (append-only evidence, per
CLAUDE.md) and write fresh raw data under `results/raw/<run_id>/` -- they
never overwrite prior rows.

## Deck vs. runner split (for the future #2 harness migration)

`pnp_vbe.spice`, `res_tc.spice`, `mos_vt_sub.spice` are pure `@@TOKEN@@`
templates with zero corner/temperature/device sweep logic inside them.
`run_devchar.py` owns all of that (the corner x temp x device product,
NMOS/PMOS bias-network mirroring, CSV emission, derived-metric report).
Migrating onto the #2 harness once it lands should mean swapping the
runner's orchestration layer, not rewriting the decks.

## PDK/model finding worth flagging

The vertical-PNP subckts' `par=` instance parameter (documented informally
as an "emitter multiplier") only scales the **mismatch** term inside the
model (`... / sqrt(par)`) -- the `q0` BJT element line forwards only
`dtemp=`, not `par=`, so a single instance with `par=8` does **not**
produce 8x the nominal `Is`/area the way a SPICE `m=`/`AREA=` multiplier
would (verified: a lone `par=8` instance produced the *same* VBE as
`par=1` at equal bias current). `pnp_vbe.spice` instead builds every
area/multiplicity ratio the physically-correct way real layouts do it: N
unit-cell subckt instances wired electrically in parallel. This is not a
klayout-tools friction item (it's an ngspice/model characterization
nuance, not a layout-tool gap) but is worth downstream design awareness if
#8/#9 schematic entry assumes `par=` scales area.

## PNP: vertical-PNP VBE / delta-VBE

Deck: `pnp_vbe.spice`. Data: `results/pnp_vbe.csv` (21 corner x temp deck
invocations per run x 10 measurement rows each = 210 rows/run; the CSV
holds two independent runs appended, see Reproducibility above). Full
derived numbers: `results/derived_metrics_<run_id>.md` (one per full run).

### Physics sanity anchors -- all pass

| Anchor | Target | Measured | Result |
|---|---|---|---|
| VBE(27 C, typical, `pnp_10p00x10p00`, 10 uA) | 0.55-0.75 V | **0.689299 V** | PASS |
| dVBE/dT (typical, linear fit -40...125 C) | -1.5...-2.2 mV/C | **-1.8319 mV/C** | PASS |
| dVBE/dT (bjt_ss / bjt_ff, same fit) | -1.5...-2.2 mV/C | **-1.7957 / -1.8559 mV/C** | PASS |
| delta-VBE(27 C, 8:1 ratio) vs. (kT/q)*ln(8) | within a few % | 53.964 mV vs. 53.785 mV theory | **0.33 %** error |
| delta-VBE(27 C, 4:1 ratio) vs. (kT/q)*ln(4) | within a few % | 35.999 mV vs. 35.856 mV theory | **0.40 %** error |

Additional monotonicity sanity checks (not required anchors, but corroborate
the deck is wired correctly): at fixed 10 uA/27 C/typical, smaller-emitter
geometries show higher VBE for the same bias current (`pnp_10p00x10p00`
0.6893 V < `pnp_05p00x05p00` 0.7227 V < `pnp_10p00x00p42` 0.7575 V <
`pnp_05p00x00p42` 0.7762 V -- smaller area -> lower Is -> higher VBE at equal
Ic, as expected). VBE vs. bias-current decade spacing on
`pnp_10p00x10p00`/typical/27 C: 1->10 uA gives +59.75 mV/decade, 10->100 uA
gives +60.93 mV/decade, both close to ideal (kT/q)*ln(10) = 59.54 mV/decade,
with the small excess at higher current consistent with `rb`/`re` ohmic
drop (not a bug).

### Corner spread (10 uA, `pnp_10p00x10p00`)

| Corner | VBE(-40 C) | VBE(125 C) | dVBE/dT (endpoint) |
|---|---|---|---|
| bjt_typical | 0.8091 V | 0.5070 V | -1.831 mV/C |
| bjt_ss | 0.8156 V | 0.5193 V | -1.796 mV/C |
| bjt_ff | 0.8046 V | 0.4984 V | -1.856 mV/C |

### Model-stated BJT parameters (from `sm141064.ngspice` `.model` cards --
not simulated, read directly from the vendor model; included because
DR-005 asked for beta / Early voltage as sweep-plan inputs)

| Geometry | BF (nominal) | VAF (V) | VAR (V) |
|---|---|---|---|
| pnp_10p00x10p00 | 1.70 | 206.4 | 23.0 |
| pnp_05p00x05p00 | 1.65 | 208.8 | 27.4 |
| pnp_10p00x00p42 | 1.69 | 80.0 | 23.0 |
| pnp_05p00x00p42 | 1.681 | 180.0 | 23.0 |

The 10p00x00p42 "thin strip" geometry has a markedly lower Early voltage
(80 V vs. ~200 V for the others) -- a design input for #9 if output
impedance / current-source-loading sensitivity matters for the chosen
bias branch.

### Recommendation: sensing core

**`pnp_10p00x10p00` as the unit cell**, biased around 10 uA (mid-decade
point measured; well inside the 1-5 uA/branch estimate in DR-005 while
still 1-2 decades from either rail current), with the **8:1 emitter-ratio
pair (8 parallel unit cells vs. 1)** for the PTAT term -- its delta-VBE tracks
theory tightest (0.33 % error) of the two ratios measured and gives more
PTAT amplification headroom than 4:1 for the single-point trim DR-005
recommends. `pnp_10p00x10p00` also has the highest Early voltage (206 V)
of the four geometries, minimizing bias-current-source-loading sensitivity
for the CTAT (single diode-connected) leg.

## Resistors: TC / sheet-R / corner spread

Deck: `res_tc.spice`. Data: `results/res_tc.csv` (21 corner x temp deck
invocations per run x 8 flavor rows each = 168 rows/run; two independent
runs appended, see Reproducibility above). Geometry: 50 um x 2 um for
every flavor (fixed; TC and corner
ratios are geometry-independent for this model -- see below).

### R(27 C) by corner and typical-corner TC (-40...125 C endpoint)

| Flavor | res_typical (ohm) | res_ss (ohm) | res_ff (ohm) | typical TC (ppm/C) |
|---|---|---|---|---|
| ppolyf_u | 9038.7 | 10834.2 | 7243.3 | **-74.8** |
| ppolyf_u_1k | 25413.5 | 30479.2 | 20347.9 | -871.8 |
| ppolyf_u_2k | 51207.7 | 61442.4 | 40972.9 | -1545.2 |
| ppolyf_u_3k | 76794.9 | 95984.9 | 57604.4 | -1544.7 |
| nplus_u | 1450.1 | 1808.2 | 1092.0 | +1373.3 |
| pplus_u | 4819.2 | 5849.8 | 3788.4 | +1365.2 |
| npolyf_u | 7979.8 | 9516.3 | 6443.2 | -1324.0 |
| nwell | 32591.0 | 39044.8 | 26137.4 | +2609.6 |

**Corner spot-check**: all 8 flavors show `res_ss > res_typical > res_ff`
at fixed geometry/bias -- R up at the slow corner, R down at the fast corner, the
direction the Test Plan calls for. Measured TC also matches the vendor
`.model` body-resistor `tc1` coefficients within a few % to ~20%
(e.g. `nplus_u` measured +1373 ppm/C vs. model `r_tc1`=1360 ppm/C;
`ppolyf_u` measured -74.8 ppm/C vs. model `r_tc1`=-90 ppm/C, the larger
relative gap here being expected since `ppolyf_u`'s coefficient is small in
absolute terms so second-order `r_tc2` and terminal-resistance `rt1`/`rt2`
contributions are relatively more visible).

### Supply-dependence

Not repeated across the +-10 % rail sweep: every flavor characterized here
ships `r_vc1=0`, `r_vc2=0` in `sm141064.ngspice` (checked directly), so the
body-resistor model is linear in bias voltage by construction -- a fixed
1 V test point is sufficient and a voltage sweep would not add information.
This is stated explicitly rather than silently skipped, per the issue's
"supply-dependent measurements" criterion.

### Recommendation: TC cancellation, sensing core, and POR divider

The body-resistor model's temperature factor `r_temp(T)` is a **pure
multiplicative function of flavor only** (`1 + r_tc1*dT + r_tc2*dT^2`,
independent of `r_length`/`r_width`) -- so a ratio of **two same-flavor**
resistors cancels TC essentially exactly at the model level, regardless of
which flavor is chosen or how large its absolute TC is. Flavor choice for
a same-flavor ratio pair is therefore driven by **area/value practicality**
and **absolute-TC-driven residual sensitivity to real silicon mismatch**
(the deterministic-corner model can't see mismatch -- that's #15's job --
but a lower-|TC| flavor bounds how much any *unmodeled* mismatch in
tempco between two nominally-matched legs can move the ratio):

- **Sensing core PTAT gain resistor pair: `ppolyf_u`.** Lowest |TC| of all
  8 flavors measured (-74.8 ppm/C), the conventional analog-precision
  resistor choice (poly-on-field-oxide, no substrate junction the way
  diffusion resistors have), and a practical mid-range sheet resistance
  (~350 ohm/sq) for a moderate-value gain ratio.
- **POR divider: `ppolyf_u_3k`.** Highest sheet resistance measured
  (~3 kohm/sq nominal, ~76.8 kohm at this test geometry) -- needed for area
  efficiency at the POR core's <1 uA (<0.3 uA stretch) Iq budget without
  an oversized divider. Same-flavor top/bottom legs for the same TC-in-
  ratio cancellation argument as above.

## MOS: Vt, subthreshold, corner spread, supply-dependence

Deck: `mos_vt_sub.spice`. Data: `results/mos_vt_sub.csv`. Vt extraction:
constant-current method, `Id_target = 100 nA*(W/L)` (W=10 um, L=1 um for
03v3/06v0/05v0 family; W=10 um, L=1.8 um -- the device's own default/min
length -- for the native `nfet_06v0_nvt`). Subthreshold swing: two-point
method one decade apart, both >=2 decades below the Vt-defining current.

### Physics/corner sanity -- nfet_03v3 / pfet_03v3 (comparator input pair
candidates)

| Corner | nfet_03v3 Vgs,th (27 C) | pfet_03v3 Vgs,th (27 C) |
|---|---|---|
| typical | 0.6444 V | -0.8429 V |
| ss | 0.7547 V | -0.9697 V |
| ff | 0.5341 V | -0.7162 V |
| fs | 0.5641 V | -0.9345 V |
| sf | 0.7248 V | -0.7513 V |

`|Vt|` increases at `ss` and decreases at `ff` for both polarities -- the
direction the Test Plan calls for. `nfet_03v3`: SS(27 C, typical) =
85.14 mV/dec, dVt/dT (-40...125 C) = -1.006 mV/C. `pfet_03v3`: SS = 90.44
mV/dec, dVt/dT = +0.934 mV/C (sign flips as expected -- PMOS |Vgs,th|
shrinks with increasing temperature the same physical direction as NMOS,
which is a *positive* slope in the signed `Vgs,th` convention used here).

### Native device (`nfet_06v0_nvt`) -- answers DR-005's open device question

DR-005 flagged "confirm whether gf180mcu offers a native or zero-Vt NMOS
option" as an open input. **Answer: yes.** Measured
`Vgs,th(27 C, typical) = -0.1202 V` -- a small negative threshold, i.e. the
device conducts even at `Vgs=0` (confirmed directly: at `Vgs=0` the
low-field drain current already exceeds the 100 nA*(W/L) Vt-defining
target). Corner spread at 27 C: typical -0.120 V, ss +0.098 V, ff -0.340 V,
fs -0.267 V, sf +0.025 V -- a **~440 mV process-corner-only spread**
(deterministic corners, not mismatch/Monte Carlo -- #15's job for the
mismatch component DR-005 also asked about). This is a real design input:
DR-005's startup-assist leg must tolerate this corner spread (specifically
the `ss` corner, where the device's Vt turns slightly positive) without
losing its "conducts before anything else is biased" property.

### 06v0/05v0 family (typical corner only, per DR-001's request not to
starve #7 pending final supply-flavor ratification)

| Device | Vgs,th (27 C, typical) | SS (mV/dec) | Ion (27 C, typical) |
|---|---|---|---|
| nfet_06v0 | 0.7215 V | 92.47 | 4.678 mA |
| pfet_06v0 | -0.9582 V | 99.22 | 1.646 mA |
| nfet_05v0 | 0.7215 V | 92.47 | 3.584 mA |
| pfet_05v0 | -0.9582 V | 99.22 | 1.180 mA |

`nfet_05v0`/`pfet_05v0` share `nfet_06v0`/`pfet_06v0`'s Vt/SS exactly --
confirmed directly in `sm141064.ngspice`, the `05v0` subckts instantiate
the `06v0` BSIM model with a different default length, per a PDK comment
in the model file ("An nfet_05v0 device is defined as a regular nFET
device allowing a slightly shorter gate length... otherwise the model is
exactly the same as nfet_06v0"). The Ion difference above is entirely the
different Ion-measurement rail (5.0 V vs. 6.0 V), not a model difference.

### Supply-dependence (DR-001: 3.3 V +-10 % = 2.97-3.63 V), typical/27 C

| Device | Ion @2.97 V | Ion @3.30 V | Ion @3.63 V |
|---|---|---|---|
| nfet_03v3 | 2.0767 mA | 2.4972 mA | 2.9194 mA |
| pfet_03v3 | 0.5740 mA | 0.7304 mA | 0.8993 mA |

Vgs,th is unchanged across these three rows (the low-field Vt-extraction
branch is independent of the separate full-rail Ion branch by
construction) -- Ion scales roughly linearly with rail (~40% swing across
the +-10% window), the expected square-law-region behavior for a fixed
overdrive-referenced measurement.

### Recommendation: comparator input pair and bias branches

- **Comparator input pair: `nfet_03v3`.** On the pinned 3.3 V rail
  (DR-001), lower |Vt| (0.644 V vs. 0.843 V for `pfet_03v3`) leaves more
  headroom for an input common-mode range near a bandgap-scale (~1.2 V)
  reference node; tighter absolute SS (85.1 vs. 90.4 mV/dec) is a mild
  secondary point in its favor. Final input-pair polarity is #10's call
  once the actual reference-node voltage is fixed -- this is a data point,
  not a topology decision.
- **Low-Iq bias / POR startup-assist branches: `nfet_06v0_nvt`** (native),
  per DR-005's recommendation and confirmed here to actually exist with
  the expected near-zero/self-conducting Vt -- the ~440 mV corner spread
  above is the number #11/#14 need to size headroom margin against.
- 06v0/05v0 family: characterized at typical only as requested; not
  recommended for the 3.3 V-pinned signal path per DR-001 (thick-oxide
  devices, larger area, no headroom need on a 3.3 V rail) -- data retained
  here purely so #7's final ratification isn't starved of it if the
  supply-flavor decision is revisited.

## Out of scope (explicitly, not silently)

- **Mismatch / Monte Carlo** (`sm141064.ngspice` `statistical` `.lib`
  section, `sw_stat_mismatch=1`): confirmed present in the model file, not
  exercised here -- this was issue #15's job. Every number in this summary
  is a deterministic-corner value; per-device local mismatch (the
  dominant real-silicon limiter for the 8:1 delta-VBE ratio, the resistor-ratio
  cancellation, and the native-device corner spread above) is not
  captured and should not be assumed small just because the corner-only
  spread looks tractable here.

  **#15 has since run it, and the warning above was correct.**
  `sim/temp-accuracy-mc/` (record `20260802-082345-989ce7a`) and
  `sim/por-threshold-mc/` (record `20260802-083749-3b9b414`) sample local
  mismatch at N = 500 per binding point via `sim/run_mc.py`. The POR
  threshold rows survive it with margin; the two temperature-accuracy rows
  do not -- the sensing amplifier's input-referred offset alone measures
  3.07 mV at 3 sigma against the ~0.46 mV its budget allowed, and the
  untrimmed row misses +/-3 C by 6.5x
  (`spec/decision-records/DR-029-temp-accuracy-mismatch-not-met.md`).
  "Should not be assumed small" turned out to be the understatement.

  This summary is **not** re-run or amended for that: `sim/` is append-only,
  these are device-characterization curves rather than spec claims, and the
  numbers here remain correct as the deterministic values they were always
  labelled as. The mismatch axis lives in the two MC experiments, not here.
- **Evidence-record format reconciliation with #5**: this summary uses the
  issue's fallback minimal-field CSV schema (see Environment above); if
  #5 lands a different canonical shape, reconcile as a follow-up rather
  than blocking on it here.
