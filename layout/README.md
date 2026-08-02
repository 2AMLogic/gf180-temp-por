# layout/ — DRC/LVS flow for gf180mcu, driven by klayout-tools

This directory holds the block's layout artifacts and the **repeatable DRC/LVS
invocation** they are checked with. It is `klt`-driven end to end: no GUI, no
interactive KLayout session, no netgen/magic.

> **Status: the block's layout is drawn and assembled — as far as the deck can
> see it.**
> #16 brought the flow up on one two-device proof cell. #68 added `bias_core`
> (**34** MOS devices), #69 `por_comparator` (**18**), #70 `por_output_chain`
> (**27**) and #71 `temp_core` (**55** drawn: 39 schematic MOS split into
> interleaved fingers, plus 6 edge dummies). #72 assembles all four into
> **`temp_por_top`** — **134** devices, **78** nets, and the ratified 5-pad
> pinout — with the domain-seam moat, the perimeter guard ring and the
> `VDD`/`VSS` rails. Every cell is DRC-clean and LVS-clean against the
> schematic-derived netlist with both negative controls detected.
> No cell is the *whole* cell. `bias_core`'s 10 vertical PNPs, 4 poly resistors
> and 2 MiM caps; `por_comparator`'s 3-segment sense divider;
> `por_output_chain`'s 2 MiM caps; `temp_core`'s PNP array, resistor ladder and
> MiM cap — all outside what the curated deck can extract, all deliberately not
> drawn *into the extracted cell*, and all inherited unchanged by
> `temp_por_top`, which therefore cannot be LVS'd whole either (see
> [The cells under test](#the-cells-under-test) and
> [Known deck limits](#known-deck-limits--what-a-clean-lvs-here-does-not-prove)).
> **What no check in this flow covers** is guard-ring and well-tie
> *correctness*: the deck has no tap or well-label layer, so a broken or
> floating ring is DRC-clean and LVS-match. `temp_por_top` therefore carries
> its own build-time geometric checks for that; see its section below.
> #17's floorplan sketch and matching plan — the ranked, #15-data-driven
> common-centroid/interdigitation/guard-ring plan this flow's cells implement —
> is [`layout/floorplan.md`](floorplan.md).
> **Post-layout simulation** does not follow from a clean LVS here, because the
> extraction has no bipolars, resistors or caps in it to simulate. #82 builds
> the bridge — extracted MOS + real interconnect parasitics, schematic-ideal
> passives — and is honest about which half is which: see
> [Composite post-layout netlists](#composite-post-layout-netlists).

## Run it

```bash
bash layout/run_checks.sh              # every cell under layout/cells/
bash layout/run_checks.sh <cell>       # one cell
bash layout/run_checks.sh --check-env  # what klt/PDK am I about to use?
```

Exit 0 means, for every cell: the committed GDS and reference netlist are
current, DRC is clean, extraction succeeded, LVS matches, **and** both LVS
negative controls were detected. Every JSON report is rewritten under
`layout/reports/` and committed as evidence.

### Prerequisites

| Need | Why | Check |
| ---- | --- | ----- |
| [`klt`](https://github.com/2AMLogic/klayout-tools) on `PATH` | runs DRC, extraction, LVS | `klt --version` |
| the `klayout` python module | only to *rebuild* `layout/cells/*.gds` | `python3 -c "import klayout.db"` |
| a gf180mcu PDK install | not required by this flow | `klt pdk find` |

`run_checks.sh` finds the `klayout` module on `python3`, else on `klt`'s own
interpreter, else via `uv run --with klayout python3`; if none of those work it
skips only the GDS staleness check and still runs DRC/LVS.

The curated `gf180mcu` DRC and extraction decks are self-contained inside
`klt` — **no PDK install is read** by `klt drc`, `klt extract`, or `klt lvs`
here. That is why this flow runs in environments where the simulation flow
(`sim/`, which does need the PDK) cannot.

## What the flow does, step by step

Everything below is what `run_checks.sh` runs; it is spelled out so a step can
be run by hand while debugging a cell.

**0. Staleness gates.** Both generated inputs are regenerated and compared
against what is committed, so a recorded clean run can never be a run against
sources that have since moved:

```bash
python3 layout/build_cells.py   --check   # committed GDS still matches its source
python3 layout/lvs_reference.py --check   # reference netlist still matches design/
```

**1. DRC.**

```bash
klt drc layout/cells/<cell>.gds --deck gf180mcu --format json
```

Exit 0 = clean, 3 = ran and found violations, 1 = failed to run.

**2. Extraction** — the layout side of the compare, recorded for `#18` to reuse:

```bash
klt extract layout/cells/<cell>.gds --deck gf180mcu \
  --top <cell> -o layout/reports/<cell>/extracted.spice --format json
```

**3. LVS** against the schematic-derived reference. `klt lvs` takes a *request
document*, not positional netlist args; the request re-extracts the layout
inline, so step 2 is recorded evidence rather than a dependency:

```bash
klt lvs layout/cells/<cell>.lvs.json --format json
```

Exit 0 = match, 3 = mismatch, 1 = failed to run.

**4. Negative controls — the part that makes step 3 mean anything.** A
mis-wired LVS invocation that compares nothing also reports `match`, so a clean
run is not by itself evidence. `layout/lvs_reference.py --corrupt` re-derives
the same reference with exactly one defect injected, and the run **requires**
LVS to report a mismatch for both:

| Control | Defect injected | Catches |
| ------- | --------------- | ------- |
| `topology` | one device's source re-tied to the other's supply rail | a compare that ignores connectivity |
| `device-param` | one device's `W` doubled | a compare that checks the graph and ignores device sizes |

They fail independently — that is why there are two, per klayout-tools'
`docs/cli/lvs.md` § "Negative controls".

## Files

```
layout/
  run_checks.sh                  the repeatable invocation (source of truth)
  build_cells.py                 builds cells/*.gds, byte-reproducibly
  lvs_reference.py               derives cells/*.reference.spice from design/netlist/
  cells/
    <cell>.gds                   the layout stream
    <cell>.reference.spice       generated -- do not edit
    <cell>.lvs.json              the klt lvs request document
  reports/
    environment.json             klt version + deck the reports were produced with
    <cell>/drc.json              klt drc report
    <cell>/extract.json          klt extract report
    <cell>/extracted.spice       the layout-side netlist
    <cell>/lvs.json              klt lvs report
    <cell>/negative-controls.json both controls' verdicts
```

Reports are regenerated wholesale by `run_checks.sh` and are byte-stable across
runs (paths are repo-relative, digests are content-based), so a re-run that
changes nothing produces an empty `git diff` — that is the repeatability check.

## The cells under test

### `bias_core` — the MOS portion of the shared bias/reference core (#68)

`design/bias_core.sch`'s 34 MOS devices, drawn from
`design/netlist/bias_core.spice`. 397.9 × 140.7 µm, 2367 polygons.

**What a clean run here covers, and what it does not.** `bias_core` has 50
devices. 34 are MOS and are drawn, extracted and compared. The other **16 are
not drawn at all**:

| Not drawn | Devices | Why |
| --- | --- | --- |
| Vertical PNPs | `XQ1`, `XQ8A`…`XQ8H`, `XQR` (10) | deck extracts `nfet`/`pfet` only — [klayout-tools#219](https://github.com/2AMLogic/klayout-tools/issues/219) |
| Poly resistors | `XR1`, `XR2`, `XRT`, `XRZ` (4) | same, resistor sub-issue [#222](https://github.com/2AMLogic/klayout-tools/issues/222) |
| MiM caps | `XCC`, `XCOK` (2) | same; also needs the upper metals the deck does not declare |

Leaving them out is a deliberate choice, not an oversight. Drawing a poly
resistor body **would make the report worse**: with no resistor device in the
deck, the extractor reads a drawn poly body as ordinary interconnect and
silently **shorts its two terminal nets** (`NB`–`EC`, `VREF`–`ER`,
`NBTOP`–`NB`, `NZ`–`N2`) — which then reads as a layout bug in the part of the
cell that *can* be checked. So the sub-cell boundary drawn here is "everything
the deck can represent, and nothing it cannot", and the passive/bipolar region
is reserved as a floorplan rectangle on annotation layer **200/0** (read by
neither deck, so it changes no verdict) rather than filled with geometry no
check in this repo could answer for.

Consequences to carry forward, stated so nobody has to re-derive them:

- The three nets that exist **only** through a resistor (`EC`, `ER`, `NZ`) are
  absent from both sides of the compare.
- `VREF`, `IBIAS` and `NB` appear with **one** MOS terminal each, because their
  other connections are to devices that are not drawn.
- Nothing here says the reference is 1.20 V, that `R2/R1` is 11.726, or that
  the 8:1 emitter ratio is matched. Those are `sim/`'s claims, unchanged.

**Structure.** Routing is Metal1-only because the extraction deck declares one
metal level; the scheme that makes 34 devices routable on one metal is
**horizontal Poly2 tracks (one per signal net) with vertical Metal1 risers**,
so a riser crosses every track it does not belong to with no contact. `VDD` and
`VSS` are Metal1 rails above and below the row. One drawn Nwell holds the whole
PMOS row.

**Matched pairs** get ordinary matched-pair practice — adjacent placement, same
orientation, identical drawn geometry, common well: `XMI1`/`XMI2`,
`XML1`/`XML2`, `XMOKA`/`XMOKB`, `XMOL1`/`XMOL2`, and the three core mirror legs
`XMP1`/`XMP2`/`XMP3`. `floorplan.md`'s ranked common-centroid plan covers
`temp_core` (ranks 1–3) and `por_comparator` (rank 4) only — it prescribes
nothing for this cell, and nothing was invented here to fill the gap.

**Guard ring and well ties are drawn, and are a design-review claim, not a
checked one.** A continuous VSS-tied p-substrate guard ring (COMP + Metal1,
contacted at 1 µm pitch, no floating segment) surrounds the cell; the Nwell has
its own VDD-tied COMP strap. Per
[klayout-tools#303](https://github.com/2AMLogic/klayout-tools/issues/303) the
deck has no tap/well-label layer and no ring-continuity rule, so **a mis-tied,
untied, or physically broken ring would compare clean** — this flow does not
verify it, and `klt 0.1.0` does not yet emit the
`device.body_unverified` warning that klayout-tools#285 added (the extract
report's `warnings` array is empty).

Recorded result (`layout/reports/bias_core/`):

| Check | Result |
| ----- | ------ |
| `klt drc --deck gf180mcu` | clean — 0 violations |
| `klt extract --deck gf180mcu` | 34 devices (18 nfet, 16 pfet), 26 nets, 6 pins |
| `klt lvs` | **match** — 34/34 devices, 26/26 nets, 6/6 pins, 0 mismatches |
| negative control `topology` | detected (exit 3; `device.unmatched` 1, `topology` 2) |
| negative control `device-param` | detected (exit 3; `device.property` 5, `topology` 2) |

### `por_comparator` — the POR threshold comparator (#69)

`design/por_comparator.sch`'s 18 MOS devices, drawn from
`design/netlist/por_comparator.spice`. 313.0 × 230.2 µm, 1489 polygons, two
cells (it instances the proof cell below).

**What a clean run here covers, and what it does not.** `por_comparator` has 21
devices. 18 are MOS and are drawn, extracted and compared. The other **3 are
not drawn at all**:

| Not drawn | Devices | Why |
| --- | --- | --- |
| Sense divider | `XRTOP`, `XRBOT`, `XRHYS` (3 × `ppolyf_u_3k`) | deck extracts `nfet`/`pfet` only — [klayout-tools#219](https://github.com/2AMLogic/klayout-tools/issues/219), resistor sub-issue [#222](https://github.com/2AMLogic/klayout-tools/issues/222) |

Same reasoning as `bias_core` above, and here it bites the cell's most
important net: a drawn poly resistor body extracts as ordinary interconnect, so
drawing the string would short `VDD`–`SNS`, `SNS`–`SNSB` and `SNSB`–`VSS`
together — collapsing the comparator's own sense node onto the rail. The
divider's area is therefore **reserved** on annotation layer 200/0 (read by
neither deck) and its two taps are routed out to that region's edge.

Consequences to carry forward:

- `SNS` and `SNSB` appear with **one** MOS terminal each (`XMINA`'s gate,
  `XMHSW`'s drain); their other connections are to devices that are not drawn.
  **They do not appear under those names in `extracted.spice`** — `grep -i sns
  layout/reports/por_comparator/extracted.spice` returns nothing, and the same
  is true of `temp_por_top`'s. That is not a missing net: no Metal1 *label* is
  drawn on either routing track (this cell labels only the 6 nets that are
  pins, plus the 2 it inherits from the instanced sub-cell), so extraction
  names both positionally — they are `$10` and `$14` in the current build. The
  schematic names survive only on the reference side of LVS, and the
  correspondence between the two is topological, not textual. Anything that
  needs to attach to those nodes must **solve** that correspondence rather
  than grep for a name; `layout/composite_netlist.py` does, and
  [`layout/composite/AUDIT.md`](composite/AUDIT.md) records which anonymous
  net each schematic name landed on for every cell. The same caution applies
  to every unlabelled net in every cell, not just these two.
- Nothing here says `RTOP/RBOT` is 1.16667, that V_hys is 150 mV, or that the
  three segments match. Those are `sim/`'s claims, unchanged.
- The reserved rectangle is **222.0 × 219.5 µm = 0.0487 mm²**, computed by
  `build_cells.py`'s `_divider_footprint()` from the golden netlist's own
  `r_width`/`r_length` (15 441.67 µm of 2 µm-wide poly) folded at a 3 µm
  serpentine pitch into 72 active legs plus one end-of-string dummy leg at each
  end. That is the same order as the ≈0.045 mm² `design/por_comparator.md`
  flagged for #17, now derived rather than estimated. The cell's 313 × 230 µm
  bounding box is **not** an area claim for the block: two thirds of it is the
  reserved divider and most of the rest is whitespace beside a 30 µm-tall
  device row, which the top-level assembly (#72) is where packing happens.

**The `BIAS_OKB` inverter is instanced, not re-drawn.** `MENP`/`MENN` already
exist as `por_comparator_bias_okb_inv` below, so this cell places one instance
of it. Both `klt drc` and `klt extract` read layers through `begin_shapes_rec`
on the top cell, i.e. flattened, so the instance's geometry — labels included —
joins the parent's own connectivity graph. One consequence is visible in the
reference netlist: the sub-cell carries its own `BIAS_OKB` Metal1 label, a
named top-level net becomes a pin, so `BIAS_OKB` is a **pin** of this cell
rather than an internal node. The manifest declares it as such instead of
deleting a label from an already-proven cell.

**Matching plan — `floorplan.md` rank 4, followed as floorplanned:** standard
practice, **not** common-centroid, for both structures the plan names, because
#15's MC record measures `vth-rise`/`vth-fall`/`v_hys` passing at 100 % yield
regardless of the comparator's own 5.47–6.62 mV offset (the ratio-feedback
hysteresis cancels it architecturally). Concretely: `XMINA`/`XMINB` are
adjacent, same orientation, identical drawn geometry, one substrate context, no
finger splitting and no interleaving, with their gate nets (`SNS`/`VREF`) on
adjacent routing tracks and their drain nets (`NA`/`CMPO`) on the next adjacent
pair, so the two halves' routing differs by one 0.8 µm track pitch; the divider
keeps **W = 2 µm** with same-flavor same-width legs, ordinary serpentine folding
for area, and standard end-of-string dummies. The load mirror `XMLA`/`XMLB`
gets the same ordinary matched-pair treatment although the floorplan names no
plan for it. `layout/tests/test_lvs_reference.py`'s
`PorComparatorMatchingPlanTest` asserts each of those properties, so a later
edit that quietly breaks the plan fails a test rather than only a review.

**Guard ring and well ties are drawn, and are a design-review claim, not a
checked one** — same as `bias_core`: a continuous VSS-tied p-substrate ring
(COMP + Metal1, contacted at 1 µm pitch, no floating segment) surrounds the
cell and the parent Nwell has its own VDD-tied COMP strap, but per
[klayout-tools#303](https://github.com/2AMLogic/klayout-tools/issues/303) a
mis-tied, untied, or physically broken ring would compare clean. This cell sits on the always-on
POR domain's side of the block-level domain seam (`floorplan.md`, "Guard-ring /
isolation plan"), so that seam's correctness is exactly what review has to
carry. `klt 0.1.0` still does not emit the `device.body_unverified` warning
klayout-tools#285 added — the extract report's `warnings` array is empty.

Recorded result (`layout/reports/por_comparator/`):

| Check | Result |
| ----- | ------ |
| `klt drc --deck gf180mcu` | clean — 0 violations |
| `klt extract --deck gf180mcu` | 18 devices (12 nfet, 6 pfet), 18 nets, 8 pins |
| `klt lvs` | **match** — 18/18 devices, 18/18 nets, 8/8 pins, 0 mismatches |
| negative control `topology` | detected (exit 3; `device.unmatched` 1, `topology` 1) |
| negative control `device-param` | detected (exit 3; `device.property` 5, `topology` 1) |

### `por_output_chain` — the MOS portion of the reset output chain (#70)

`design/por_output_chain.sch`'s 27 MOS devices, drawn from
`design/netlist/por_output_chain.spice`. 221.7 × 107.7 µm, 1458 polygons.

**What a clean run here covers, and what it does not.** The cell has 29
devices. 27 are MOS (14 pfet, 13 nfet) and are drawn, extracted and compared.
The other **2 are not drawn at all**:

| Not drawn | Devices | Why |
| --- | --- | --- |
| MiM caps | `XCDG` (11 × 11 µm), `XCTIM` (4 × 28 × 28 µm) | deck extracts `nfet`/`pfet` only — [klayout-tools#219](https://github.com/2AMLogic/klayout-tools/issues/219); also needs the metal 3/4 the deck does not declare ([#220](https://github.com/2AMLogic/klayout-tools/issues/220)) |

There is **no resistor in this cell** — `por_output_chain.md`'s only mention of
one is in the *negative*, explaining why the ≥1 ms one-shot is a current-starved
ramp rather than an RC ("1 ms into a 6 pF capacitor needs ~160 MΩ, which is not
buildable here"). Confirmed against the current schematic export: the golden
netlist's only non-MOS cards are the two `cap_mim_2f0_m3m4_noshield` calls
above. So the resistor half of the deck's coverage gap
([#222](https://github.com/2AMLogic/klayout-tools/issues/222)) does not bear on
this cell at all.

Unlike `bias_core`, leaving the undrawn devices out **costs no net**: `NDG` and
`TIM` each carry MOS terminals as well as a cap terminal, so every net in the
schematic still exists on both sides of the compare, with every one of its MOS
connections. `layout/tests/test_lvs_reference.py` asserts that rather than
leaving it to this paragraph, so a future schematic edit that made an undrawn
device the sole owner of a node fails loudly instead of quietly narrowing what
LVS answers for. What stays unproven is the two **capacitor values** — i.e. the
deglitch dwell and the one-shot width. Those remain `sim/`'s claims, unchanged.

**Structure.** Same scheme as `bias_core`, and for the same reason: the
extraction deck still declares one metal level at `klt 0.1.0`, so routing is
**horizontal Poly2 tracks (one per signal net) with vertical Metal1 risers**.
`VDD`/`VSS` are Metal1 rails above and below the row; one drawn Nwell holds the
whole PMOS row.

**Placement follows `floorplan.md` inside the cell, not just at block level.**
`floorplan.md` puts this cell nearest the `RESETn` pad, "shortest path from the
push-pull output driver", in the always-on POR domain. Both ends are honoured
in the drawn row:

- `XMON` — the push-pull pull-down — is its own region at the **right,
  pad-facing edge**, with `XMOP` the last device of the PMOS row immediately to
  its left. The `RESETn` pin label sits on `XMON`'s own drain riser, the
  right-most Metal1 in the cell on that net; nothing is placed between the
  driver and the pad edge.
- `XMBD` leads the NMOS row at the **left, `bias_core`-facing edge**, where
  `IBIAS` arrives. Per
  [DR-010](../spec/decision-records/DR-010-shared-ibias-disabled-consumer-contract.md)
  `XMBD` is ungated and always on, and is the element that *defines* the shared
  `IBIAS` node's operating point. It is drawn diode-connected (gate and drain on
  the `IBIAS` pin net, source on `VSS`) with **no series device anywhere in that
  path**, and the `IBIAS` pin label is on `XMBD`'s own drain riser, so there is
  nowhere for a gating element to hide. The only other device touching `IBIAS`
  is `XMN1`'s *gate* — a mirror read, not a series element. A unit test asserts
  each clause of that.

**Matched pairs** get ordinary matched-pair practice — adjacent placement, same
orientation, identical drawn geometry, common well: `XMPD`/`XMP2` (the 10 nA
PMOS reference and its copy), `XMPT`/`XMDBPT` (identical 0.5/10 legs off `PDN`),
`XMNAP1`/`XMNAP2` and `XMNAN1`/`XMNAN2` (the release NAND's pull-up pair and
pull-down stack). `floorplan.md`'s ranked common-centroid plan covers
`temp_core` (ranks 1–3) and `por_comparator` (rank 4) only — it prescribes
nothing for this cell, and nothing was invented here to fill the gap.

**Dummy edge devices are not drawn, and that is a tool limit, not a matching
call.** A drawn dummy MOS extracts as an ordinary device; the deck has no way
to mark one non-functional, so it would appear in the extracted netlist as a
device the schematic-derived reference does not have and fail LVS. The only
alternatives are to abandon LVS on the cell or to hand-add fudge devices to the
reference — which would end its mechanical derivability from the schematic and
give a real missing device somewhere to hide. Filed generically:
[klayout-tools#295](https://github.com/2AMLogic/klayout-tools/issues/295).

**Guard ring and well ties are drawn, and are a design-review claim, not a
checked one** — same as `bias_core`, and it matters more here because this cell
sits on the always-on POR domain's outer edge. A continuous VSS-tied
p-substrate guard ring (COMP + Metal1, contacted at 1 µm pitch, no floating
segment) surrounds the cell, and the Nwell has its own VDD-tied COMP strap. Per
[klayout-tools#303](https://github.com/2AMLogic/klayout-tools/issues/303) the
deck has no tap/well-label layer and no ring-continuity rule, so **a mis-tied,
untied, or physically broken ring would compare clean**; `klt 0.1.0` still does not emit the `device.body_unverified` warning
klayout-tools#285 added (`extract.json`'s `warnings` array is empty).

**MiM area is reserved, not stacked.** The two caps need about 3.26 × 10³ µm²
of MiM. `design/por_output_chain.md` notes MiM sits on metal 3/4 and *may* be
stackable over neighbouring circuitry, explicitly deferring that to a
DRC/layout call. This cell does not make that call in the optimistic direction:
70 × 62 µm is reserved as **separate floor area** on annotation layer 200/0,
above the VDD rail and inside the guard ring, so the area number stays
pessimistic. Nothing in this repo can currently answer the stacking question —
the deck declares one metal level and has no MiM rules at all.

Recorded result (`layout/reports/por_output_chain/`):

| Check | Result |
| ----- | ------ |
| `klt drc --deck gf180mcu` | clean — 0 violations |
| `klt extract --deck gf180mcu` | 27 devices (13 nfet, 14 pfet), 20 nets, 6 pins |
| `klt lvs` | **match** — 27/27 devices, 20/20 nets, 6/6 pins, 0 mismatches |
| negative control `topology` | detected (exit 3; `device.unmatched` 1, `topology` 1) |
| negative control `device-param` | detected (exit 3; `device.property` 5, `topology` 1) |

### `temp_core` — the PTAT/CTAT sensing core (#71)

`design/temp_core.sch`'s 39 MOS devices, drawn from
`design/netlist/temp_core.spice` per `layout/floorplan.md`'s ranked matching
plan: the rank-1 amplifier input pair and load mirror and the rank-2 cascoded
gain mirror are each drawn as **interleaved unit fingers** on a uniform pitch
in the plan's common-centroid order, with edge dummy fingers. The curated deck
runs no device-combination step, so N parallel fingers stay N devices in the
extraction; `lvs_reference.py`'s `fingers` field splits the same schematic
device into the same N devices of W/N in the reference, and its `dummies` field
declares the edge fingers explicitly (they are not in the schematic, so a
derived dummy would be a device LVS accepts that no golden netlist asked for).
39 + 10 extra fingers + 6 dummies = **55** drawn devices, all accounted for.

The cell's PNP array, `R2` gain ladder and MiM cap are outside the deck's
extraction and are drawn as **sibling top cells** (`temp_core_pnp_array`,
`temp_core_r2_ladder`) rather than omitted: `klt drc` checks every top cell in
a stream while `klt extract`/`klt lvs` take a single `--top`, so the geometry
is still checked without a drawn poly-resistor body shorting `PTAT` into `VSS`
through the trim ladder.

Recorded result (`layout/reports/temp_core/`):

| Check | Result |
| ----- | ------ |
| `klt drc --deck gf180mcu` | clean — 0 violations |
| `klt extract --deck gf180mcu` | 55 devices (27 nfet, 28 pfet), 30 nets, 28 pins |
| `klt lvs` | **match** — 55/55 devices, 30/30 nets, 28/28 pins |
| negative control `topology` | detected (exit 3; `device.unmatched` 1) |
| negative control `device-param` | detected (exit 3; `device.property` 5) |

### `temp_por_top` — the block-level assembly (#72)

All four sub-circuits instanced into one cell, with the two guard rings, the
`VDD`/`VSS` rails and the ratified 5-pad pinout (`VDD`, `VSS`, `PTAT`, `CTAT`,
`RESETn`). **No sub-circuit is modified to fit**: each of the four functions
this cell calls still produces its own committed GDS byte-for-byte, so
`temp_por_top` inherits their recorded results rather than re-opening them.

**Routing.** This is the first cell in the repo to route above Metal1, and it
is why the "single metal level" limit below now reads differently: the
installed `klt 0.1.0`'s extraction deck declares the full Metal1–Metal5 /
Via1–Via4 stack. Discipline: Metal2 horizontal, Metal3 vertical, one Metal2
trunk per crossing net at its own `y`, one Metal3 column per pin escape at its
own `x`; Metal1 is used **only** for the two guard rings. Every crossing net
reaches an instance by landing a Via1 on that instance's own Metal1 pin
strap — nothing abuts, nothing is redrawn.

The direct consequence, and the reason it matters here: **no guard ring in
this cell has a notch in it.** In a single-metal regime the `IBIAS`
feedthrough would have to break the domain-seam moat to cross it. On Metal3 it
crosses *over* the moat instead, with the moat continuous end to end — which is
what `layout/floorplan.md`'s isolation plan asks for and what a notched ring
only approximates.

**What actually crosses the seam, exactly.** Four left-margin Metal3 columns
straddle the moat's `y`, all of them inside the moat's own `x`-span: two
signals — `IBIAS` (`x = -60`, up to `temp_core`) and `RESETn`/`EN` (`x = -56`) —
and two supplies — `VSS` down to the bottom rail (`x = -48`, which is also the
rings' tie net) and the POR domain's own `VDD` riser up to the top rail
(`x = -64`). `temp_core`'s `VDD` tap (`x = -52`) is the one left-margin column
that does not cross, because the top rail is on its side of the seam. The
isolation claim does not rest on the *count*: it rests on **none of the four
being drawn on Metal1/COMP**, the layers the moat is made of, so every crossing
passes over an unbroken ring rather than through a notch in it. `IBIAS` is
still the only *bias* net that crosses into the temp-sensor domain — `VREF` and
`BIAS_OK` stay POR-domain-internal — which is the part of `floorplan.md`'s plan
that is about coupling rather than about ring continuity.

**The check the deck cannot do.** A guard ring that is broken, or drawn but
never tied to `VSS`, is DRC-clean and LVS-match — both were built and confirmed
clean while developing this cell, and the tool gap is filed generically as
[klayout-tools#303](https://github.com/2AMLogic/klayout-tools/issues/303). `build_cells.py`
therefore checks the geometry itself, at build time, and refuses to write the
stream otherwise:

| Build-time check | What it catches |
| ---------------- | --------------- |
| every net this cell draws is **one connected group** across the via stack | a guard ring drawn but never joined to `VSS`; any open |
| every connected group carries **one net name** | a via bridging two nets; two same-layer shapes overlapping |
| different-net shapes respect the deck's own spacing rule | under-spacing DRC would catch, caught earlier and by name |
| each guard ring merges to **one polygon with exactly one hole** | a ring with a gap in one segment — still connected, still on `VSS`, but no longer a ring |
| every Via1/Via2 is covered by metal on **both** levels | a via drawn a hair off its landing pad (an open, not a short) |

Each of these was negative-controlled by deliberately introducing the defect it
describes and confirming the check fires. What is *still* a design-review claim,
and the only one left, is that `VSS` is the right net to tie the rings to.

**Coverage.** Every non-MOS device of all four sub-circuits is outside this
compare — `bias_core`'s `XQ1`/`XQ8A..H`/`XQR` PNPs, `XR1`/`XR2`/`XRT`/`XRZ`
resistors and `XCC`/`XCOK` MiM caps; `por_comparator`'s `XRTOP`/`XRBOT`/`XRHYS`
divider; `por_output_chain`'s `XCDG`/`XCTIM` MiM caps; `temp_core`'s
`XQ1`/`XQ8A..H` PNPs, `XR1`/`XR2*`/`XRISO`/`XRZ` resistors and `XCC` MiM cap.
The 134 devices below are the MOS subset, and only the MOS subset.

Recorded result (`layout/reports/temp_por_top/`):

| Check | Result |
| ----- | ------ |
| `klt drc --deck gf180mcu` | clean — 0 violations (Metal2/Metal3 rules now exercised, not skipped) |
| `klt extract --deck gf180mcu --top-cell-pins` | 134 devices (70 nfet, 64 pfet), 78 nets, 6 pins |
| `klt lvs` | **match** — 134/134 devices, 78/78 nets, 6/6 pins |
| negative control `topology` | detected (exit 3; `device.unmatched` 1) |
| negative control `device-param` | detected (exit 3; `device.property` 5) |

The 6 pins are the ratified 5 pads plus the deck's `vsubs` global. That set is
exactly what `layout.top_cell_pins` produces: the five Metal2 labels this cell
draws itself are its only labels, and every sub-circuit's own labels stay below
the top cell and stay internal. `lvs_reference.py` asserts the reference's own
port list against `design/netlist/temp_por_top.spice`'s `.subckt` line, in
order — the same ratified-pinout assertion `design/netlist.py --check` makes at
the schematic level.

### `por_comparator_bias_okb_inv` — the flow's original proof cell (#16)

`por_comparator_bias_okb_inv` — the local inverter that produces `BIAS_OKB`
inside `por_comparator` (`MENP` / `MENN` in that cell's device table). Two
devices, both gates on one drawn poly strip, both drains on one Metal1 strap.

It was chosen because it is the smallest piece of this block that the curated
`gf180mcu` extraction deck can represent **completely** — every device in it is
a plain single-finger MOS, so a clean LVS is a statement about the whole cell
rather than about the subset the deck happens to understand. Sizing is not
retyped here: `lvs_reference.py` reads `L`/`W` out of
`design/netlist/por_comparator.spice`, which `design/netlist.py` exports from
the schematic. Change the schematic and the reference netlist goes stale, and
`run_checks.sh` fails until it is regenerated.

Recorded result (`layout/reports/por_comparator_bias_okb_inv/`):

| Check | Result |
| ----- | ------ |
| `klt drc --deck gf180mcu` | clean — 0 violations |
| `klt extract --deck gf180mcu` | 2 devices (1 nfet, 1 pfet), 6 nets, 5 pins |
| `klt lvs` | **match** — 2/2 devices, 6/6 nets, 5/5 pins, 0 mismatches |
| negative control `topology` | detected (exit 3, mismatch) |
| negative control `device-param` | detected (exit 3, mismatch) |

## Composite post-layout netlists

`klt extract` produces a **MOS-only** netlist for every cell here — no
bipolar, no resistor, no MiM cap, in any of them (see
[Known deck limits](#known-deck-limits--what-a-clean-lvs-here-does-not-prove);
the deck now *declares* those classes, but none of the drawn cells carries the
marker geometry they need). So "re-run the verification suite on the extracted
netlist" cannot be done literally: the devices that set this block's analog
behaviour are not in the extraction at all, and `klt extract --parasitics`
only ever hangs first-order R/C on the nets that exist in that MOS-only graph.

What *can* be done is a **composite** netlist, and
`layout/composite_netlist.py` builds one per cell:

```bash
python3 layout/composite_netlist.py --extract   # klt extract --parasitics (needs klt)
python3 layout/composite_netlist.py             # regenerate layout/composite/
python3 layout/composite_netlist.py --check     # committed outputs still current?
python3 layout/composite_smoke.py               # DC smoke run (needs ngspice + PDK)
```

| Part of the composite netlist | Comes from | Real? |
| --- | --- | --- |
| every MOS device, with its drawn `L`/`W`/`AS`/`AD`/`PS`/`PD` | `klt extract --deck gf180mcu --parasitics` | **yes — layout** |
| one series R + one lumped C per net | the same run | **yes — layout** (first-order, from the deck's curated sheet table; not a field solve) |
| MOS *body* nodes | the golden schematic | no — the deck has no tap/well-label layer, so an extracted body lands on a substrate global or an anonymous well net, and a floating body cannot be simulated |
| vertical PNPs, poly resistors, MiM caps | `design/netlist/<cell>.spice`, **verbatim** | **no — ideal**; not drawn anywhere, so no geometry, no parasitics, no layout-derived matching |
| the nets those devices alone own (`EC`, `ER`, `NZ`, `NC`, …) | introduced by the splice | no — brand-new nodes, checked by name against every extracted net so the splice cannot short one |

**What a result taken on one of these may claim.** Real interconnect
parasitics loading the real MOS topology — the sensing core's high-impedance
bias/mirror nodes, the POR chain's switching nodes, the cross-domain
routing — and nothing else. It is **not** a parasitic-extracted analog core.
Every generated netlist repeats that in its own header; every `sim/` record
taken against one must repeat it in its **Claim** field, per CLAUDE.md's "no
claim without a testbench" and "the spec is not relaxed to make a result
pass". A record's **Netlist provenance** field should read
`composite post-layout (layout/composite/<cell>.composite.spice)`.

**Where to expect a difference, and where not to.** The parasitic model is one
series R feeding one lumped C per net. At DC the R carries no current and the
C is an open, so **every DC quantity is parasitic-invariant by construction** —
and `layout/composite/SMOKE.md` measures exactly that: all five cells
reproduce their golden-schematic operating points to within 0.04 %. A
switching edge is a different matter; `temp_por_top`'s reset release moves
**+1.9 %** on the same run. Post-layout claims worth recording against these
netlists are therefore timing/edge claims, not DC ones.

**How the splice knows where to attach.** Not by name. Most extracted nets are
anonymous (`$5`, `$12`, …) because the layout labels only its pins, so the
schematic net names survive only on the reference side of LVS — the
`SNS`/`SNSB` case above is the one that bites. `composite_netlist.py`
therefore *solves* the net correspondence between the extracted netlist and
`layout/cells/<cell>.reference.spice` (colour refinement plus backtracking,
seeded by the pin names both sides agree on) — the same correspondence
`klt lvs` computes internally but does not report, filed upstream as
[klayout-tools#311](https://github.com/2AMLogic/klayout-tools/issues/311). The
solved mapping is **verified, not trusted**:

| Check | Catches |
| --- | --- |
| the extracted device multiset, translated through the mapping, equals the reference device multiset | any wrong pairing anywhere in the graph |
| the mapping is a bijection, onto, and maps pins to pins | a merge that would short two nets |
| every extracted net that *does* carry a drawn label lands on the reference net of the same name | a plausible-but-wrong isomorphism — the solver is never given below-top labels, so this is independent information |
| no spliced-in node name collides with an extracted net name | the splice silently shorting a new node onto a real one |
| the golden schematic, run through a byte-identical smoke deck, gives the same answer | a splice attached to the wrong node, which would still converge and still print numbers |

Two negative controls in `layout/tests/test_composite_netlist.py` keep those
honest: swapping two nets of a solved mapping must be rejected, and
`lvs_reference.py --corrupt topology`'s deliberately mis-wired reference must
not solve at all.

### Files, and the parasitics coverage counter

```
layout/
  composite_netlist.py             the generator (stdlib only; --extract needs klt)
  composite_smoke.py               the DC smoke run (needs ngspice + the PDK)
  composite/
    <cell>.composite.spice         the composite netlist (golden .subckt port list)
    <cell>.audit.json              per-net provenance + counters
    AUDIT.md                       the per-cell audit tables, rendered
    SMOKE.md                       the smoke run, rendered
  reports/<cell>/
    extracted-parasitics.spice     klt extract --parasitics output
    extracted-parasitics.json      its report
    composite-smoke.json           the cell's smoke result
```

`extracted-parasitics.*` are **separate artifacts on purpose**:
`run_checks.sh` keeps `extracted.spice` / `extract.json` byte-stable as the
DRC/LVS flow's own repeatability contract, and nothing here touches them.

Every cell's audit reports **nets carrying parasitics vs. nets in the
extraction** — the
[klayout-tools#283](https://github.com/2AMLogic/klayout-tools/issues/283)
sanity check, since that issue was a *silent zero* on unlabelled nets and
these cells are mostly unlabelled nets. Current build:

| cell | MOS devices (layout) | spliced devices (ideal) | nets with parasitics | ΣC |
| --- | --- | --- | --- | --- |
| `bias_core` | 34 | 16 | 24/26 (92.3 %) | 1498.6 fF |
| `temp_core` | 55 | 20 | 27/30 (90.0 %) | 1087.3 fF |
| `por_comparator` | 18 | 3 | 15/18 (83.3 %) | 376.7 fF |
| `por_output_chain` | 27 | 2 | 18/20 (90.0 %) | 813.9 fF |
| `temp_por_top` | 134 | 41 | 71/78 (91.0 %) | 4767.5 fF |

The nets with no parasitics are, in every cell, the deck's synthetic body nets
(the substrate global and each anonymous Nwell) plus one supply — nets with no
drawn interconnect of their own to be resistive or capacitive. `--extract`
refuses to write an artifact whose coverage is zero, and the generator refuses
to build if its own recount disagrees with the recorded JSON.

## Known deck limits — what a clean LVS here does *not* prove

`klt`'s `gf180mcu` decks are curated starter subsets, not the full DRM/LVS rule
set. The limits below are the ones that bear on reading these reports. Each was
hit during this bring-up and, where it is a tool gap rather than a fact of life,
filed upstream per this repo's friction protocol.

- **Device coverage is MOS-only.** The extraction deck recognises `nfet`/`pfet`
  and nothing else in the version this flow was brought up on, so a cell
  containing poly resistors, MiM caps, or vertical bipolars cannot be LVS'd
  whole. That is why the proof cell is an all-MOS one, why `bias_core`'s
  16 non-MOS devices and `por_comparator`'s 3-segment sense divider are **not
  drawn** rather than drawn-and-ignored — a drawn poly resistor body extracts as
  interconnect and shorts its own terminal nets — and why `por_output_chain`'s
  2 MiM caps are not drawn either.
  **Re-checked at `klt 0.1.0` for #72** — and this has moved. The installed
  deck now *declares* `['nfet', 'pfet', 'bjt', 'cap_mim_2f0_m4m5_noshield',
  'resistor']` (every `lvs.json` records it), so
  [klayout-tools#219](https://github.com/2AMLogic/klayout-tools/issues/219) and
  its sub-issues #222 (resistors) / #225 (MiM caps) have landed here. What has
  **not** moved is these cells: recognising a resistor or a MiM cap needs
  marker layers (`SAB`/`RES_MK`, `CAP_MK`/`MIM_L_MK`) that none of the drawn
  cells carry, and the drawn geometry that *would* become those devices was
  laid out for a deck that could not model them. So every non-MOS device in
  this block is still undrawn-or-sibling and still outside the compare — now
  as a **drawing** gap this repo owns, not a tool gap. Closing it is
  post-#72 work.
  The *silence* has moved too, in the right direction:
  [klayout-tools#288](https://github.com/2AMLogic/klayout-tools/issues/288) is
  live in this build — every cell's `extract.json` now carries a warning naming
  the count of poly shapes with "the resistor-body signature" that were
  absorbed into interconnect (19 in `bias_core`, 10 in `por_comparator`, 16 in
  `por_output_chain`, 110 in `temp_core`, 155 in `temp_por_top` = the sum). The
  failure mode is now a wrong netlist *with a warning*, which is what was asked
  for.
- **There is no dummy-device concept**, so matched-pair *dummy edges* cannot be
  drawn on any cell that must also LVS: a drawn dummy MOS extracts as a real
  device the schematic-derived reference does not have. The cells here
  therefore stop at adjacency/orientation/geometry matching and draw no
  dummies — a layout decision made by a tool limit, which is exactly the kind
  of thing this repo exists to surface. Filed by #70:
  [klayout-tools#295](https://github.com/2AMLogic/klayout-tools/issues/295).
- **There is no annotation-layer contract**, so the reserved regions in
  `bias_core` (passives/bipolars), `por_comparator` (the sense divider) and
  `por_output_chain` (the MiM area) sit on a layer (200/0) chosen because no
  deck reads it today, not because any deck promises not to. Filed:
  [klayout-tools#289](https://github.com/2AMLogic/klayout-tools/issues/289).
  Re-check after a `klt` upgrade: if `klt drc`'s or `klt extract`'s layer set
  ever grows to include it, the reports move and `run_checks.sh` says so.
- **A sub-cell's labels become the parent's pins.** Extraction is flat, and it
  ends by promoting *every named net* to a top-level pin — including nets that
  are named only because a label sits inside an instanced sub-cell. So
  `por_comparator` instancing `por_comparator_bias_okb_inv` inherits its
  `BIAS_OKB` label and `BIAS_OKB` becomes a **pin** of `por_comparator`, even
  though the schematic calls it an internal node. Filed:
  [klayout-tools#291](https://github.com/2AMLogic/klayout-tools/issues/291) —
  **now fixed in this build**, and load-bearing for #72: `klt extract
  --top-cell-pins` / `"top_cell_pins": true` in the `klt lvs` request promotes
  only labels drawn *directly in the top cell*. Without it `temp_por_top` would
  have inherited every one of `temp_core`'s 27 routing-channel labels as a
  top-level pin and could not have been compared against the ratified 5-pad
  pinout at all. A cell that instances others should set it (see
  [Adding a cell](#adding-a-cell-for-17--18)); `por_comparator` predates the fix
  and still declares `BIAS_OKB` as a port in its manifest, which remains
  correct for that cell as drawn.
- **Body terminals are synthetic.** The deck draws no substrate tap, so NMOS
  bodies land on a global `vsubs` net; gf180mcu has no distinct tap or
  well-label layer, so an extracted Nwell is an anonymous net. `lvs_reference.py`
  therefore rewrites the schematic's body nodes to match. **Consequence: a
  mis-tied, untied, or physically broken guard ring compares clean.** Both were
  built and confirmed during #72: a `temp_por_top` whose seam moat is drawn but
  never tied to `VSS`, and one whose perimeter ring has a 10 µm gap in a
  segment, are each `klt drc` clean and `klt lvs` **match**.
  Filed: [klayout-tools#303](https://github.com/2AMLogic/klayout-tools/issues/303)
  — that is the issue that tracks this gap, with those two defect builds as its
  evidence.
  The older [klayout-tools#281](https://github.com/2AMLogic/klayout-tools/issues/281)
  (synthetic body nets) is **closed**, resolved by #285, and its curated scope
  was narrowed to that one warning — so it does **not** track ring continuity or
  the tie, and should not be cited for them. #285 **is** live in this build:
  every `lvs.json` now carries two `device.body_unverified` warnings naming how
  many NMOS bodies went to `vsubs` and how many PMOS bodies went to an anonymous
  well net. That is a real signal — it says the compare did not check bodies —
  but it is not a *tie* check, and it says nothing at all about a guard ring. So
  ring correctness stays outside the deck. `temp_por_top` answers it with
  build-time geometric checks instead (see its section above); every other
  cell's ring remains a design-review claim.
- **The reference netlist has to be converted, not just pointed at.** `klt lvs`
  needs plain-element SPICE (`M1 d g s b nfet L=0.5U W=1U`); `design/netlist.py`
  emits the ngspice simulation form (`XM1 d g s b nfet_03v3 L=0.5u ...`).
  Pointing LVS at the raw export does not error — it silently produces a
  net-merge cascade that reads like a layout bug. `lvs_reference.py` is this
  repo's converter. Filed:
  [klayout-tools#280](https://github.com/2AMLogic/klayout-tools/issues/280).
- **A parameter-only defect is poorly localised on a small cell** — and #68
  measured the size at which that stops being true. On the two-device proof
  cell the `device-param` control is *detected* but reported as
  `device.unmatched` + a `net.unmatched` cascade rather than the documented
  `device.property` entry naming the wrong parameter, so the report points at
  connectivity when the defect is a width. On the 34-device `bias_core` the same
  control reports **`device.property` ×5**, i.e. it classifies correctly — which
  is the first evidence in this repo for the "classifies correctly once the
  circuit is larger" expectation rather than an assumption about it. #70's
  27-device `por_output_chain` and #69's 18-device `por_comparator` both
  reproduce that (`device.property` ×5), so it is not a one-off and the
  cross-over sits below 18 devices, not somewhere between 2 and 34. Filed:
  [klayout-tools#282](https://github.com/2AMLogic/klayout-tools/issues/282).
- **~~Single metal level.~~ Lifted — re-checked at `klt 0.1.0` for #72.**
  #68, #69 and #70 each re-checked this and each found `metals=((34, 0),)`.
  #72 re-checked it again and found the installed build now declares the full
  stack — `metals=((34,0),(36,0),(42,0),(46,0),(81,0))`,
  `vias=((35,0),(38,0),(40,0),(41,0))` — i.e.
  [klayout-tools#220](https://github.com/2AMLogic/klayout-tools/issues/220) /
  #238 have landed here. The DRC deck's `metal2`/`metal3` width and space rules
  are real and now actually exercised (they used to appear under
  `rules_skipped` only because no stream drew those layers).
  Consequences, in order of how much they matter:
  - `temp_por_top` routes on Metal2/Metal3 and so needs **no notch in either
    guard ring** — see its section above. This is the single biggest thing the
    lifted limit bought.
  - `bias_core`, `por_comparator`, `por_output_chain` and `temp_core` are
    **unchanged**: they route on Metal1 with Poly2 crossunders, their committed
    GDS is byte-identical, and their recorded results stand. Nothing about the
    lifted limit obliges a redraw, and redrawing a proven cell to use a
    capability it does not need would be a regression risk for no gain.
  - The MiM caps stay undrawn, but the reason has narrowed: the gf180mcu MiM
    stack (metal 3/4 + `FuseTop`) is now in the deck's layer set, so what is
    missing is the marker geometry in these cells, not the deck.
  `layout/floorplan.md`'s "Routing / metal-level note" carries the same
  re-check.
- **DRC is a curated subset.** Width/space/enclosure across Poly2/Comp/Contact/
  Metal1, plus Nwell spacing/enclosure and one BJT rule. Clean here means clean
  against *that* subset — it is not a tapeout-grade signoff, and no claim in
  this repo should be written as if it were.

`layout/reports/environment.json` records the `klt` version each report was
produced with, because several of the limits above are version-dependent.
Re-run `run_checks.sh` after upgrading `klt` and commit the refreshed reports.

## Adding a cell (for #17 / #18)

1. Add a builder function to `layout/build_cells.py` and register it in `CELLS`;
   run `python3 layout/build_cells.py --cell <name>` to write the GDS.
2. Add a manifest entry to `layout/lvs_reference.py`'s `CELLS` — the golden
   netlist it derives from, the devices to take, the layout's own pin set
   (`ports`), its unlabelled internal nets (`internal`), and which PMOS devices
   share which drawn Nwell (`wells`). Run it to write the reference. On a cell
   with more than two devices, check that `devices[0]` and `devices[1]` do not
   share a source net — if they do, the `topology` negative control corrupts
   nothing and silently stops controlling anything.
3. Copy an existing `cells/<cell>.lvs.json` and point it at the new names.
   **If the cell instances other cells**, set `"top_cell_pins": true` in its
   `layout` block — otherwise every label inside every instanced sub-cell
   becomes a pin of yours, and the compare is against a pin set nobody
   designed. `run_checks.sh` mirrors that flag onto the recorded `klt extract`
   run and onto both negative-control requests, so all three see the same
   compare.
4. `bash layout/run_checks.sh <name>` — and do not treat a clean LVS as real
   until both negative controls report detected.

An **assembly** cell (one that instances others, like `temp_por_top`) differs in
two further ways:

- Its `lvs_reference.py` manifest lists no devices. It carries an `assembly`
  field naming `(instance, cell)` pairs, and the reference is composed from
  those cells' own manifests with each instance's nets renamed through the
  golden top-level netlist's own instance lines — a formal port maps to whatever
  the top level wires it to, every other net is prefixed with the instance name,
  and the deck's substrate global is never renamed. Nothing is retyped, so the
  assembled reference cannot drift from the cells it assembles.
- Nothing in this flow checks a guard ring, a well tie, or a different-net
  overlap on the same layer (all three are DRC-clean and LVS-match — see
  [Known deck limits](#known-deck-limits--what-a-clean-lvs-here-does-not-prove)).
  If your cell draws rings or rails, check the geometry yourself at build time
  and refuse to write the stream otherwise; `temp_por_top`'s `_TopRoutes.check`
  and `_top_guard_ring` are the pattern, and `layout/tests` covers them without
  needing `klt` or a PDK.

Keep the friction protocol running while you do it: every time `klt` is
awkward, missing something, or wrong, file it generically at
`2AMLogic/klayout-tools` — the tool gap, never the design.
