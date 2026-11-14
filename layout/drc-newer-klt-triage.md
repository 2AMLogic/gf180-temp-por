# DRC triage: what the committed cells show under `klt` 0.8.0 and later

`layout/toolchain.json` pins the `klt` build this repo's DRC/LVS evidence is
for at **0.6.0**. #400 tried to move that pin and stopped: under `klt` 0.8.0
all six committed cells turn from clean to violating, with counts in the
thousands. Before the pin can move, somebody has to say, rule by rule, whether
those violations are real layout defects that the older deck never checked, or
a change in the deck.

This note is that ruling. **Its conclusion: all eleven rules that fire are
real layout defects. None is a deck-side defect.** The five follow-up issues
in [§8](#8-follow-up-issues-before-400-can-proceed) are what #400 is waiting
on.

Nothing here changes any layout, deck or pin. `layout/toolchain.json`,
`layout/cells/` and `layout/reports/` are untouched by the commit that adds
this note.

## Contents

- [1. What was run](#1-what-was-run)
- [2. The 0.6.0 baseline, and what "clean" actually meant](#2-the-060-baseline-and-what-clean-actually-meant)
- [3. The 0.6.0 → 0.8.0 deck transition is purely additive](#3-the-060--080-deck-transition-is-purely-additive)
- [4. Every rule that fires, per cell](#4-every-rule-that-fires-per-cell)
- [5. Rule-by-rule classification](#5-rule-by-rule-classification)
  - [5.1 The seven `*.ongrid.1` rules — 31,928 violations](#51-the-seven-ongrid1-rules--31928-violations)
  - [5.2 `comp.coverage.1` — 314 violations, every cell affected](#52-compcoverage1--314-violations-every-cell-affected)
  - [5.3 `poly2.enclosing.sab.1` — 1,004 violations](#53-poly2enclosingsab1--1004-violations)
  - [5.4 `sab.space.1` — 98 violations](#54-sabspace1--98-violations)
  - [5.5 `comp.tap_distance.nwell.lv.1` — 2 violations](#55-comptap_distancenwelllv1--2-violations)
- [6. Deck-side findings: none](#6-deck-side-findings-none)
- [7. The tool gap this triage did surface](#7-the-tool-gap-this-triage-did-surface)
- [8. Follow-up issues before #400 can proceed](#8-follow-up-issues-before-400-can-proceed)
- [9. What this note does not cover](#9-what-this-note-does-not-cover)

## 1. What was run

| | |
|---|---|
| `klt` version | **0.8.0** (`klayout-tools==0.8.0` from PyPI) |
| KLayout engine | **0.30.12**, pinned explicitly |
| deck | `gf180mcu`, content hash `sha256:0eb6df1bafc5106ec50bd58479dbd7cda36bb685f1ef18cd3a2244a6e7e48666` |
| layouts | the committed `layout/cells/*.gds`, unmodified, at `daa202a4` |
| date | 2026-11-14 |

0.8.0 is the version #400 targets, and the deck hash above is the one #400
recorded. The engine is pinned because `klt` warns that a different KLayout
build can change report counts; with `klayout==0.30.12` the report's
`provenance.klayout_version_mismatch` is `false`, so no count here carries
that caveat.

> The host's own `klt` (a `0.9.2.dev` build) ships a **third** `gf180mcu` deck,
> with 126 rules, whose hash matches neither the pin nor 0.8.0. It is not used
> anywhere in this note. Every command below runs in a throwaway environment
> via `uvx`, so the `klt` on `PATH` — the one `layout/run_checks.sh` gates
> on — is never involved.

### Reproduction

```bash
# Per-cell DRC under 0.8.0. Writes to a scratch dir: never layout/reports/.
OUT=$(mktemp -d)
for c in bias_core por_comparator por_comparator_bias_okb_inv \
         por_output_chain temp_core temp_por_top; do
  uvx --from "klayout-tools==0.8.0" --with "klayout==0.30.12" \
    klt drc "layout/cells/$c.gds" --deck gf180mcu --format json > "$OUT/$c.json"
done

# The two decks' rule sets, for the comparison in section 3.
uvx --from "klayout-tools==0.6.0" klt deck rules --deck gf180mcu --format json > "$OUT/rules-060.json"
uvx --from "klayout-tools==0.8.0" klt deck rules --deck gf180mcu --format json > "$OUT/rules-080.json"
```

`klt drc` in 0.8.0 has no `-o`; the report goes to stdout. It exits `3` when a
layout violates, which is the expected status for every run here, not an error.

**`layout/run_checks.sh` cannot be used for this.** Its `toolchain_gate()`
(`layout/run_checks.sh:146-204`) probes the `klt` on `PATH` and refuses to run
unless it ships the pinned 0.6.0 deck hash. There is deliberately no
pinned-deck path to a 0.8.0 run, so `klt drc` is invoked directly above.

Independent geometry cross-checks in [§5](#5-rule-by-rule-classification) read
the committed GDS with the `klayout.db` Python module and recompute each rule
from drawn layers, so no count below rests on `klt` agreeing with itself.
Generator attribution comes from instrumenting `CellBuilder.box()` while
rebuilding each cell **into a temporary directory**, and matching `klt`'s
violation markers to the recorded call sites by coordinate.

## 2. The 0.6.0 baseline, and what "clean" actually meant

Re-run under the *pinned* 0.6.0 build, all six cells are clean, and the deck
hash is the pinned one:

```
bias_core:                   status=clean count=0  deck sha256:95c2eb9148b29ded0…
por_comparator:              status=clean count=0  deck sha256:95c2eb9148b29ded0…
por_comparator_bias_okb_inv: status=clean count=0  deck sha256:95c2eb9148b29ded0…
por_output_chain:            status=clean count=0  deck sha256:95c2eb9148b29ded0…
temp_core:                   status=clean count=0  deck sha256:95c2eb9148b29ded0…
temp_por_top:                status=clean count=0  deck sha256:95c2eb9148b29ded0…
```

So the committed evidence is not stale or wrong about its own deck. But
"clean" is a statement about the rules the deck contains, and **all eleven
rules that fire under 0.8.0 are absent from the 0.6.0 deck entirely**:

| rule | in the 0.6.0 deck? | 0.6.0 verdict on the cells it fires on |
|---|---|---|
| `contact.ongrid.1` | no | never evaluated |
| `via1.ongrid.1` | no | never evaluated |
| `metal1.ongrid.1` | no | never evaluated |
| `poly2.ongrid.1` | no | never evaluated |
| `sab.ongrid.1` | no | never evaluated |
| `res_mk.ongrid.1` | no | never evaluated |
| `resistor.ongrid.1` | no | never evaluated |
| `comp.coverage.1` | no | never evaluated |
| `poly2.enclosing.sab.1` | no | never evaluated |
| `sab.space.1` | no | never evaluated |
| `comp.tap_distance.nwell.lv.1` | no | never evaluated |

Not one of them was present-and-passing. This is the single most important
fact for framing the rest: **"the deck used to pass this" is not available as
an explanation for any of the eleven.** The pinned deck did not pass these
cells on these rules — it never checked them.

## 3. The 0.6.0 → 0.8.0 deck transition is purely additive

Keying both `klt deck rules --format json` outputs by rule `id`:

| | |
|---|---|
| rules in the 0.6.0 deck | **46** |
| rules in the 0.8.0 deck | **114** |
| added in 0.8.0 | **68** |
| removed in 0.8.0 | **0** |
| shared rules whose `check`, `value_um`, `limits` or `layers` changed | **0** |

Both decks report `nominal_dbu_um: 0.001`.

The 0.6.0 run reports content hash `sha256:95c2eb91…5f6cb637` — **exactly the
hash pinned in `layout/toolchain.json`**, so this is the pinned deck and not a
lookalike build.

No rule was removed, re-thresholded, re-scoped or re-layered. The deck got
strictly stricter by covering more of the DRM. That rules out the whole class
of "the deck changed its mind" explanations at the level of the rule *set*,
and it is why §5 can concentrate on the one question that stays genuinely
open per rule: does the newly-modelled rule, as `klt` implements it, flag
geometry that is actually defective?

## 4. Every rule that fires, per cell

Counts are `rule_counts` from each 0.8.0 report. `—` means the rule did not
fire on that cell (either clean or skipped for want of its layers; see
[§9](#9-what-this-note-does-not-cover)).

| rule | `bias_core` | `por_comparator` | `…bias_okb_inv` | `por_output_chain` | `temp_core` | `temp_por_top` |
|---|---:|---:|---:|---:|---:|---:|
| `contact.ongrid.1` | 7400 | 4176 | — | 3384 | — | 14960 |
| `poly2.enclosing.sab.1` | 48 | 454 | — | — | — | 502 |
| `poly2.ongrid.1` | — | 228 | — | — | — | 228 |
| `sab.ongrid.1` | — | 228 | — | — | — | 228 |
| `res_mk.ongrid.1` | — | 228 | — | — | — | 228 |
| `resistor.ongrid.1` | — | 228 | — | — | — | 228 |
| `via1.ongrid.1` | — | — | — | — | — | 160 |
| `comp.coverage.1` | 48 | 21 | 2 | 31 | 55 | 157 |
| `sab.space.1` | — | — | — | — | 49 | 49 |
| `metal1.ongrid.1` | — | 12 | — | — | — | 12 |
| `comp.tap_distance.nwell.lv.1` | — | — | — | — | 1 | 1 |
| **total** | **7496** | **5575** | **2** | **3415** | **105** | **16753** |

Every total matches the number #400 recorded, exactly.

> **Two ways to total these, and this note uses both.** Summing the table's
> six columns gives **33,346**, but that double-counts: `temp_por_top`
> instantiates the other five cells, so it re-reports their geometry (see the
> next subsection). The count of **distinct** defects is **16,753**. Section 5
> quotes per-rule sums across all six reports, because those are the numbers a
> reader can add up from this table; [§8](#8-follow-up-issues-before-400-can-proceed)
> quotes distinct counts, because that is the work. Each subsection says which.

### `temp_por_top` adds exactly one defect of its own

`temp_por_top` is the block-level assembly, so its violations are mostly its
sub-cells' seen through instantiation. Summing the five sub-cells rule by rule
and differencing against the top cell:

| rule | Σ sub-cells | `temp_por_top` | delta |
|---|---:|---:|---:|
| `comp.coverage.1` | 157 | 157 | 0 |
| `comp.tap_distance.nwell.lv.1` | 1 | 1 | 0 |
| `contact.ongrid.1` | 14960 | 14960 | 0 |
| `metal1.ongrid.1` | 12 | 12 | 0 |
| `poly2.enclosing.sab.1` | 502 | 502 | 0 |
| `poly2.ongrid.1` | 228 | 228 | 0 |
| `res_mk.ongrid.1` | 228 | 228 | 0 |
| `resistor.ongrid.1` | 228 | 228 | 0 |
| `sab.ongrid.1` | 228 | 228 | 0 |
| `sab.space.1` | 49 | 49 | 0 |
| `via1.ongrid.1` | 0 | **160** | **+160** |
| **total** | **16593** | **16753** | **+160** |

Every rule closes to zero except `via1.ongrid.1`. The top level introduces
exactly one new defect — its own Via1 placement — and nothing else. **Fixing
the five sub-cells fixes 16,593 of `temp_por_top`'s 16,753 violations**, which
is why the follow-ups in §8 are organised by generator construct rather than
by cell.

## 5. Rule-by-rule classification

Summary: **eleven rules fire, eleven are layout defects, zero are deck-side
defects.** Each subsection quotes the deck's own rule text (via `klt deck
rules`, which carries per-rule provenance into the upstream PDK), gives an
example location, states the independent cross-check, and names the generator
code that draws the shape.

All eleven rules carry the same provenance: upstream repo
`google/globalfoundries-pdk-libs-gf180mcu_fd_pv` at commit
`f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`. They are models of real published
GF180MCU DRM rules, not `klt` inventions.

### 5.1 The seven `*.ongrid.1` rules — 31,928 violations

**Classification: layout defect.**

`contact.ongrid.1`, `via1.ongrid.1`, `metal1.ongrid.1`, `poly2.ongrid.1`,
`sab.ongrid.1`, `res_mk.ongrid.1`, `resistor.ongrid.1`.

#### The rule

All seven are the same check on a different layer, e.g.

> **`contact.ongrid.1`** — "contact vertices must be on the 0.005um
> manufacturing grid"
> `check: ongrid`, `scope: OFFGRID`, `limits: {"grid_um": 0.005}`,
> `layers: ["Contact"]`
> upstream `libs.tech/klayout/tech/drc/rule_decks/geom.rb`, rule id
> `contact_OFFGRID`

The decisive detail is that the deck's `nominal_dbu_um` is **0.001** while the
`*_OFFGRID` rules check a **0.005 µm** grid. A coordinate can be exact in DBU
and still off the manufacturing grid — which is precisely the gap this layout
falls into.

#### Independent cross-check

Each `ongrid` violation marker is a degenerate point (`bbox` with
`left == right`, `bottom == top`) naming one vertex. Testing every marker's
coordinate against the 5 nm grid directly:

| | |
|---|---|
| markers whose vertex is genuinely off the 0.005 µm grid | **31,928** |
| markers whose vertex is on the grid (i.e. false positives) | **0** |

Not one of the 31,928 is spurious.

#### Example locations

| cell | rule | vertex (DBU) | x mod 5 | y mod 5 |
|---|---|---|---:|---:|
| `bias_core` | `contact.ongrid.1` | `(-4860, -6559)` | 0 | **1** |
| `por_output_chain` | `contact.ongrid.1` | `(-4860, -6556)` | 0 | **4** |
| `por_comparator` | `metal1.ongrid.1` | `(377000, 138804)` | 0 | **4** |
| `por_comparator` | `poly2`/`sab`/`res_mk`/`resistor` `.ongrid.1` | `(81000, 150402)` | 0 | **2** |
| `temp_por_top` | `via1.ongrid.1` | `(-103899, -538130)` | **1** | 0 |

The four `por_comparator` marker layers share one vertex, `(81.000,
150.402) µm`: one off-grid rectangle drawn on four layers at once.

#### Generator code

Two spacing helpers divide a span by a count, so their step is an arbitrary
multiple of 1 nm rather than of 5 nm:

- `_span()` — `layout/build_cells.py:985-991`, `step = (high - low) / count`
- `_contact_rows()` — `layout/build_cells.py:951-963`, `step = (high - low) / (count - 1)`

`CellBuilder.contact()` (`:192-206`) *does* quantise its centre, but to
`self.layout.dbu` — 1 nm. Its own comment says why it exists: to stop the two
edges rounding apart into a `contact.width.1` violation. That is a different
problem, and 1 nm quantisation cannot fix a 5 nm grid.
`CellBuilder.via()` (`:208-212`) and the top-level `via1()` (`:3440-3449`) do
not quantise at all. All the half-widths are already grid-exact
(`CONTACT_SIDE_UM = 0.22` → 110 DBU; `VIA_SIDE_UM = 0.26` → 130 DBU), so the
entire error is in the centre.

Instrumenting the generator, the off-grid shapes come from:

| cell | layer | off-grid shapes | drawn by |
|---|---|---:|---|
| `bias_core` | Contact | 1850 | `_draw_guard_ring():1132,1133,1137,1138`; `bias_core():1468`; `_draw_tiles():1093` |
| `por_comparator` | Contact | 1044 | `por_comparator():2405,2406,2410,2411,2387`; `_draw_tiles():1093` |
| `por_comparator` | Poly2/SAB/RES_MK/Resistor | 170 each | `_resistor_string():2102,2106,2112,2114` |
| `por_comparator` | Metal1 | 4 | `terminal():2118`; `por_comparator():2443` |
| `por_output_chain` | Contact | 846 | `_draw_guard_ring():1132,1133,1137,1138`; `por_output_chain():1791,1801` |
| `temp_por_top` | Contact | 3740 | the above, through instantiation |
| `temp_por_top` | Via1 | 40 | `CellBuilder.via1():3447` |

Every Contact site is a `b.contact()` whose centre comes from `_span()` or
`_contact_rows()`, which confirms the mechanism rather than merely being
consistent with it.

The counts reconcile at **4 violations per off-grid rectangle** where one rule
dominates a cell — `bias_core` 1850 × 4 = 7400; `por_output_chain` 846 × 4 =
3384; `temp_por_top` Via1 40 × 4 = 160 — i.e. one marker per off-grid vertex
of each rectangle.

> **A latent instance of the same defect.** `CellBuilder.pad()` (`:3436-3438`)
> also draws off-grid shapes, 40 of them on Metal2 in `temp_por_top`. The deck
> carries no `metal2.ongrid.*` rule, so this does not fire today. It is the
> same bug and should be fixed in the same pass.

### 5.2 `comp.coverage.1` — 314 violations, every cell affected

**Classification: layout defect.** This is the most consequential finding here.

#### The rule

> **`comp.coverage.1`** — "COMP not covered by Nplus or Pplus is forbidden
> (except COMP under the Schottky-diode marking)"
> `check: comp_coverage`, `scope: 7.5 Comp`,
> `layers: ["Comp", "Nplus", "Pplus", "Schottky_diode"]`
> upstream `libs.tech/klayout/tech/drc/rule_decks/comp.rb`, rule id **`DF.12`**

#### Independent cross-check

Computing `Region(Comp) - (Nplus + Pplus + Schottky_diode)` flat from each top
cell and merging reproduces every count **exactly, 1:1** — the strongest
agreement of any rule in this triage:

| cell | independent uncovered regions | `klt` count | uncovered COMP area |
|---|---:|---:|---:|
| `por_comparator_bias_okb_inv` | 2 | 2 | 5.40 µm² |
| `por_comparator` | 21 | 21 | 2030.10 µm² |
| `por_output_chain` | 31 | 31 | 1749.90 µm² |
| `bias_core` | 48 | 48 | 4875.40 µm² |
| `temp_core` | 55 | 55 | 1849.30 µm² |
| `temp_por_top` | 157 | 157 | 32752.70 µm² |

In `temp_core`, 1849 µm² of the 5597 µm² of drawn COMP — a third of it — has
no implant over it at all. **`temp_core` is the least affected cell, not the
worst.** In the other four leaf cells the uncovered area equals the *total*
drawn COMP area — `bias_core` 4875.40, `por_comparator` 2030.10,
`por_output_chain` 1749.90, `…bias_okb_inv` 5.40 µm², each identical to its
row above — so those four have no implant over COMP anywhere at all, rather
than incomplete coverage. That follows from the generator without measuring
anything: of the seven implant sites listed below, the four resistor sites
(`:900`, `:2905`, `:3044`, `:3071`) draw `PPLUS` coincident with a `POLY2`
body — implant over poly, never over COMP — and the only three that cover COMP
(`:3109`, `:3143`, `:3150`) all sit in `_temp_core_pnp_array()`, which only
`temp_core` instantiates (`:2952`). `temp_core` is therefore the one cell with
any implant over COMP, which is exactly why it is the one cell whose coverage
is partial. This bears on how #516 is scoped: four of the six cells need
implant drawn from scratch, not an existing pattern extended.

Example: `por_comparator_bias_okb_inv`, uncovered COMP at
`(0.0, 0.0)..(1.8, 1.0) µm` — a plain 1.8 × 1.0 µm rectangle of bare
diffusion. This cell is the flow's smallest, with only two violations in total,
and both are this.

#### Generator code

`PPLUS`/`NPLUS` are drawn at only seven sites in the whole of
`layout/build_cells.py` — the poly resistors (`:900`, `:2905`, `:3044`,
`:3071`), the PNP emitters (`:3109`), and the `temp_core` PNP array's two
rings (`:3143`, `:3150`). **The MOS drawing paths draw none.** Matching
`klt`'s markers to call sites:

| cell | attribution |
|---|---|
| `temp_core` | **55/55** → `_mos_finger():2630` — `b.box(COMP, x, comp_lo, comp_x1, comp_hi)` |
| `bias_core` | 34 → `_draw_tiles():1085`; 10 → `_pnp_unit():939`; 2 → `_bias_core_passives():1250`; 1 each → `bias_core():1427`, `:1466` |
| `por_output_chain` | 28 → `_draw_tiles():1085`; 1 each → `_draw_guard_ring():1128`, `por_output_chain():1788`, `:1799` |
| `por_comparator` | 17 → `_draw_tiles():1085`; 1 each → `por_comparator():2349`, `:2385` |
| `…bias_okb_inv` | 1 each → `por_comparator_bias_okb_inv():295`, `:296` |

`_mos_finger()` and `_draw_tiles()` both draw COMP and a Poly2 gate and no
implant. `_draw_guard_ring():1128` draws guard-ring COMP with no implant
either.

#### Why clean LVS never caught it

`klt`'s gf180mcu **device recognition does not require implants**, independent
of the pinned deck's rule set. `klt deck devices --deck gf180mcu` reports:

```
nfet: source_drain = Comp, requires [],        excludes [Nwell]
      gate         = Poly2, requires [],       excludes [Nwell]
pfet: source_drain = Comp, requires [Nwell], …
```

So the devices extract and match with no implant present, and the NMOS/PMOS
distinction is carried only by Nwell presence. **A passing LVS is not evidence
that the implant is there.** As drawn, these MOS devices have no defined
source/drain doping.

### 5.3 `poly2.enclosing.sab.1` — 1,004 violations

**Classification: layout defect.**

#### The rule

> **`poly2.enclosing.sab.1`** — "minimum Poly2 extension beyond related SAB"
> `check: enclosing`, `scope: SB`, `value_um: 0.22` (`value_dbu: 220`),
> `layers: ["Poly2", "SAB"]`
> upstream `libs.tech/klayout/tech/drc/rule_decks/sab.rb`, rule id **`SB.10`**

#### Independent cross-check and example

The measured extension is **0.000 µm** where 0.220 is required. On
`bias_core`, SAB spans x `419.900…421.900 µm` inside a Poly2 spanning x
`419.900…424.900 µm`: the left edges are coincident, extension `+0.000`. The
violation markers agree — `bias_core`'s first marker is a degenerate polygon
with all four points at x `341900` DBU, i.e. a Poly2 edge and a SAB edge at
the same coordinate. On `por_comparator` the leg tops give `+0.003`, `+0.023`
and `+0.038 µm`, all far under 0.220.

A region-level cross-check (`SAB - Poly2.sized(-220)`) matches `klt` exactly
on `bias_core` (**48/48**). On the other cells it over-reports relative to
`klt`, and **`klt` is the one that is right** — see the note below.

#### Generator code

Matching markers to call sites gives a single clean attribution per cell:

| cell | attribution |
|---|---|
| `bias_core` | **48/48** → `_poly_resistor():898` |
| `por_comparator` | **454/454** → `_resistor_string():2102` |
| `temp_por_top` | 502 → the two above (48 + 454), through instantiation |

Both constructions draw the marker layers from the *same* rectangle as the
poly, which is deliberate and documented — the comment at `:899` reads
"Marked body: coincident on all four layers, from one rectangle":

```python
# _poly_resistor(), layout/build_cells.py:898-901
b.box(POLY2, x, y0, x + width, y0 + leg)
# Marked body: coincident on all four layers, from one rectangle.
for spec in (PPLUS, SAB, RESISTOR_ID, RES_MK):
    b.box(spec, x, y0, x + width, y0 + leg)
```

Coincident rectangles are what make the extracted body exactly `width × leg`,
and therefore what makes the drawn resistance equal the value
`layout/lvs_reference.py` states — so a fix has to add the extension without
moving the recognised region's dimensions.

> **Why `klt` reports 0 on `temp_core` and the naive check reports 100.**
> `temp_core`'s resistors come from `_r_segment():2906`, which draws SAB
> **0.4 µm wider** than the poly on each side, on purpose. `SB.10` constrains
> Poly2 extending beyond SAB; where SAB is the wider layer the rule does not
> apply, and `klt`'s edge-pair `enclosing` check correctly does not fire.
> The blunt `SAB - Poly2.sized(-220)` cross-check has no notion of which
> side is "related" and flags all 100 of them. `klt` is correct and the
> cross-check is crude. This is worth stating plainly because it is the one
> place in this triage where the independent check and the tool disagree, and
> the disagreement resolves in the tool's favour.

### 5.4 `sab.space.1` — 98 violations

**Classification: layout defect.**

#### The rule

> **`sab.space.1`** — "minimum SAB spacing"
> `check: space`, `scope: SB`, `value_um: 0.42` (`value_dbu: 420`),
> `layers: ["SAB"]`
> upstream `libs.tech/klayout/tech/drc/rule_decks/sab.rb`, rule id **`SB.2`**

#### Independent cross-check and example

`Region(SAB).space_check(420)` reproduces the count **exactly (49/49)** on
`temp_core`, and 0 on `por_comparator`, matching `klt` on both.

Example on `temp_core`: the marker is the gap between SAB edges at x
`308.400 µm` and x `308.600 µm`, running y `62.800…122.935 µm` — a
**0.200 µm** gap where **0.420 µm** is required, under half the rule.

#### Generator code

**49/49 → `_r_segment():2906`**:

```python
b.box(SAB, x - 0.4, y + _R_HEAD - 0.2, x + width + 0.4, y + _R_HEAD + length + 0.2)
```

The 0.4 µm overhang is deliberate and well-motivated (`:2897-2901`): it makes
the recognised region `Poly2 & RES_MK & Pplus & SAB` exactly `width × length`,
which the extractor turns into `R = L / W * 350`, which is what makes the
drawn resistance match `lvs_reference.py`. But two neighbouring segments each
overhang 0.4 µm *toward each other*, so the SAB-to-SAB gap is the poly pitch
minus 0.8 µm — and at the pitch this tile uses, that leaves 0.2 µm.

The same construction's deliberate extra SAB width is what keeps `temp_core`
clean on `SB.10` (§5.3). The two SAB rules pull in opposite directions here:
`_poly_resistor()` is too narrow for `SB.10`, `_r_segment()` is too wide for
`SB.2`. Neither is clean, and they need different fixes.

### 5.5 `comp.tap_distance.nwell.lv.1` — 2 violations

**Classification: layout defect.**

This is the rule most likely *a priori* to have been a modelling artefact —
it is a topology check with a sampling parameter, it fires exactly once, and
upstream `klt` work in its neighbourhood (`klayout-tools#3484`/`#3546`, the
gf180mcu NP/PP PCOMP rules split by Nwell distance) made it a plausible
candidate for a deck-side finding. It is not one. The geometry really does
violate the rule, and by 50 %.

#### The rule

> **`comp.tap_distance.nwell.lv.1`** — "Max distance of an Nwell tap (NCOMP
> inside Nwell) from PCOMP inside Nwell: 20um (3.3V)"
> `check: tap_distance`, `scope: 7.5 Comp`,
> `limits: {"well_domain": "inside", "voltage": "lv", "max_distance_um": 20.0, "step_um": 0.5}`
> upstream `libs.tech/klayout/tech/drc/rule_decks/comp.rb`, rule id **`DF.13_LV`**

#### Independent cross-check

`klt`'s marker is the box `(514.0, 90.0)..(524.0, 100.0) µm`. Computing, for
every PCOMP-inside-Nwell region in `temp_core`, the true polygon distance to
the nearest NCOMP-inside-Nwell material:

| distance to nearest tap | PCOMP regions | verdict |
|---:|---:|---|
| **30.000 µm** | **1** | **violates** (limit 20) |
| 16.000 µm | 8 | passes |
| 2.000 µm | 16 | passes |

Exactly one of the 25 regions exceeds 20 µm, matching `klt`'s count of 1 — and
it is the region at `(514, 90)..(524, 100) µm`, exactly the one `klt` flagged.

> A first attempt at this cross-check used bounding-box distance and found
> *every* PCOMP at distance 0, which looked like a `klt` false positive. That
> was an artefact of the method: the tap is a **ring** (bbox 74 × 74 µm, area
> only 576 µm²), so its bounding box covers the hole and swallows the whole
> array. True polygon distance is required, and it vindicates `klt`.

#### Generator code

**1/1 → `_temp_core_pnp_array():3108`** (the emitter COMP). The arithmetic is
fully determined by the array's own constants:

- emitters are a `_Q_GRID = 5` × 5 grid at `_Q_PITCH = 14.0 µm`, each
  `_Q_EMITTER = 10.0 µm` square (`:3105-3109`), so `span = 4 × 14 + 10 = 66 µm`
- the shared base ring — the Nwell tap — is drawn around the **perimeter only**:
  `ring(COMP, 4.0, 2.0)` / `ring(NPLUS, 4.3, 2.6)` (`:3142-3143`)
- one Nwell holds the whole array (`:3147`)

An emitter's distance to the ring's inner edge is set by how deep into the
array it sits: `min(row, 4 - row, col, 4 - col) × 14 + 2 µm`. That partitions
the 25 emitters into exactly three buckets. The **sixteen** perimeter emitters
— every one with a row or column of `0` or `4`, which is `25 - 3 × 3` — sit
`2 µm` from the ring. The remaining nine are the inner 3 × 3: **eight** of them
measure exactly `14 + 2 = 16 µm` and pass, and the ninth — the centre —
measures `2 × 14 + 2 = 30 µm`, against a 20 µm limit. So a 3 × 3 array at this
pitch would have been clean, and a 5 × 5 cannot be: the centre is the one
position a perimeter-only tap ring cannot reach.

This is a well-biasing and latch-up robustness defect, not a cosmetic one: the
centre of the array is the point whose well potential is least controlled.

## 6. Deck-side findings: none

**Zero of the eleven rules is a deck-side defect.** Stated explicitly because
the acceptance criterion for this triage asks each rule to be classified as
one or the other, and the honest answer came out entirely on one side. The
evidence:

1. **The deck transition added rules and changed none** (§3): 68 added, 0
   removed, 0 of the 46 shared rules altered in `check`, `value_um`, `limits`
   or `layers`. There is no re-thresholding to blame.
2. **All eleven firing rules were absent from the pinned deck** (§2), so no
   rule reversed a verdict it had previously given.
3. **Every rule's geometry was re-derived independently** from the committed
   GDS (§5), without reusing `klt`'s own computation. The grid rules match
   with **zero** false positives out of 31,928; `comp.coverage.1` matches
   1:1 on all six cells; `sab.space.1` matches 49/49;
   `comp.tap_distance.nwell.lv.1` matches 1/1 and identifies the same region.
4. **Where an independent check and `klt` disagreed, `klt` was right** —
   `poly2.enclosing.sab.1` on `temp_core` (§5.3) and the first
   `comp.tap_distance` attempt (§5.5) were both failures of the cross-check,
   not of the deck.
5. **All eleven rules trace to published GF180MCU DRM rules** with upstream
   provenance (`google/globalfoundries-pdk-libs-gf180mcu_fd_pv` @ `f6eeac7`):
   `contact_OFFGRID` and siblings, `DF.12`, `SB.10`, `SB.2`, `DF.13_LV`. None
   is a `klt` invention, and each models its upstream rule faithfully as far
   as this triage could measure.

No issue was filed at `2AMLogic/klayout-tools` for a deck defect, because
there is none to file. Manufacturing one to satisfy the criterion would have
been worse than useless — it would have put a false bug report in front of the
tool's maintainers and left five real layout defects mis-attributed.

## 7. The tool gap this triage did surface

Answering "which rules changed between these two deck revisions?" required
installing two `klayout-tools` releases into throwaway environments and
diffing `klt deck rules --format json` by hand. `klt deck` has `resolve`,
`hash`, `path`, `info`, `rules` and `devices`; none takes two revisions
(checked on 0.8.0 and on a `0.9.2.dev` build).

Filed generically as
**[`2AMLogic/klayout-tools#5680`](https://github.com/2AMLogic/klayout-tools/issues/5680)** —
a proposed `klt deck diff --deck <name> --from <ref> --to <ref>` reporting
added / removed / changed rules with the fields that moved. The comparison is
also easy to get subtly wrong: keying on rule `id` alone would miss a rule
whose `value_um` or `limits` moved while its id stayed, which is exactly the
case that most needs catching, and the case §3 had to rule out by hand.

## 8. Follow-up issues before #400 can proceed

Organised by generator construct, because that is how the defects cluster — the
seven `*.ongrid.1` rules are one cause across six layers and four cells, not
seven problems.

Counts here are **distinct** defects (§4): the sub-cells' violations plus
`temp_por_top`'s own, without the double-count from instantiation.

| # | issue | rules fixed | distinct | across the six reports |
|---|---|---|---:|---:|
| **#515** | Snap generator-derived coordinates to the 0.005 µm manufacturing grid | the seven `*.ongrid.1` | 16,044 | 31,928 |
| **#516** | MOS source/drain and guard-ring COMP are drawn with no Nplus/Pplus implant (`DF.12`) | `comp.coverage.1` | 157 | 314 |
| **#517** | Poly resistors draw SAB coincident with Poly2: zero extension where `SB.10` requires 0.22 µm | `poly2.enclosing.sab.1` | 502 | 1,004 |
| **#518** | `temp_core` resistor tile: neighbouring SAB markers 0.2 µm apart where `SB.2` requires 0.42 µm | `sab.space.1` | 49 | 98 |
| **#519** | `temp_core` PNP array: centre emitter 30 µm from the Nwell tap ring where `DF.13_LV` allows 20 µm | `comp.tap_distance.nwell.lv.1` | 1 | 2 |
| | **total** | **all 11 rules** | **16,753** | **33,346** |

The distinct total, 16,753, is exactly `temp_por_top`'s own violation count —
which it has to be, since that cell contains all five sub-cells plus its own
160 off-grid Via1 and nothing else (§4). The five issues account for every
rule that fires, with nothing left over.

Sequencing notes for whoever picks these up:

- **#516 is the most serious** and should go first. The others are
  manufacturability and robustness rules; #516 means the MOS devices have no
  defined source/drain doping at all, and a passing LVS does not catch it.
- **#515 moves geometry in every cell**, so it will churn `layout/cells/*.gds`
  and every report. Landing it near-last reduces rebase pain for the others;
  landing it first means the others' regenerated evidence is already on-grid.
  Either order works — pick one deliberately rather than by accident.
- **#517 and #518 are the same two resistor constructions pulling opposite
  ways** (§5.4) and are best reviewed together, even if they land separately.
- Each of the five regenerates `layout/cells/*.gds` and `layout/reports/`, and
  each must keep LVS matching `layout/lvs_reference.py`. #517 and #518 in
  particular must not change the extracted resistor values.
- **#400 stays blocked until all five land.** Moving the pin with any of them
  outstanding would mean committing a `layout/reports/` that records real
  violations as the evidence base, which is the opposite of what the pin is
  for.

## 9. What this note does not cover

- **Rules that neither fired nor were checked.** `klt` skips a rule whose
  layers are absent from the stream, and reports which. Per cell, checked /
  skipped out of the 114-rule deck: `bias_core` 72/42, `por_comparator` 34/80,
  `por_comparator_bias_okb_inv` 19/95, `por_output_chain` 57/57, `temp_core`
  80/34, `temp_por_top` 81/33. Checked + skipped = 114 in every case, so the
  accounting is complete — but a skipped rule is **not** a passed rule, and
  this triage says nothing about the 33–95 skipped per cell. That is a
  separate question from the one #400 asked.
- **`klt` 0.9.x and later.** Only 0.8.0 was triaged, because that is what
  #400 targets. The host's `0.9.2.dev` build ships a 126-rule deck — 12 more
  than 0.8.0 — so moving the pin past 0.8.0 will need its own pass over
  whatever those 12 add.
- **Whether the five fixes are sufficient for a clean 0.8.0 run.** Each
  follow-up carries its own acceptance criterion of zero violations for its
  rule, but fixing one can expose another: adding implants (#516) can engage
  implant spacing and overlap rules currently skipped for want of those
  layers, and snapping geometry (#515) moves every enclosure margin. The
  honest statement is that these five are necessary; sufficiency is only
  established by a clean full run, which is #400's job.
- **The layers with no rules at all.** Every cell reports `34/10` (Metal1
  labels) and `temp_por_top` also `36/10` as present in the stream with no
  deck rule. That is unchanged from the pinned deck and unrelated to this
  triage; `layout/README.md`'s "Known deck limits" section is where deck
  coverage gaps of that kind are tracked.
