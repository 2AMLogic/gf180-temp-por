# layout/ — DRC/LVS flow for gf180mcu, driven by klayout-tools

This directory holds the block's layout artifacts and the **repeatable DRC/LVS
invocation** they are checked with. It is `klt`-driven end to end: no GUI, no
interactive KLayout session, no netgen/magic.

> **Status: the flow is proven, and three of the block's four sub-circuits are
> drawn — as far as the deck can see them.**
> #16 brought the flow up on one two-device proof cell. #68 added `bias_core`
> (**34** MOS devices), #69 added `por_comparator` (**18**) and #70 added
> `por_output_chain` (**27**), each DRC-clean and LVS-clean against the
> schematic-derived netlist, with both negative controls detected. None of them
> is the *whole* cell — `bias_core`'s 10 vertical PNPs, 4 poly resistors and 2
> MiM caps, `por_comparator`'s 3-segment sense divider, and
> `por_output_chain`'s 2 MiM caps, are outside the curated deck's device
> coverage and are deliberately not drawn (see
> [The cells under test](#the-cells-under-test) and
> [Known deck limits](#known-deck-limits--what-a-clean-lvs-here-does-not-prove)).
> `temp_core` and the top-level assembly are not drawn.
> #17's floorplan sketch and matching plan — the ranked, #15-data-driven
> common-centroid/interdigitation/guard-ring plan this flow's cells implement —
> is [`layout/floorplan.md`](floorplan.md).

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
[klayout-tools#281](https://github.com/2AMLogic/klayout-tools/issues/281) the
deck has no tap/well-label layer, so **a mis-tied or untied ring would compare
clean** — this flow does not verify it, and `klt 0.1.0` does not yet emit the
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
[klayout-tools#281](https://github.com/2AMLogic/klayout-tools/issues/281) a
mis-tied or untied ring would compare clean. This cell sits on the always-on
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
[klayout-tools#281](https://github.com/2AMLogic/klayout-tools/issues/281) the
deck has no tap/well-label layer, so **a mis-tied or untied ring would compare
clean**; `klt 0.1.0` still does not emit the `device.body_unverified` warning
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
  **Re-checked at `klt 0.1.0` for #70**: upstream
  [klayout-tools#219](https://github.com/2AMLogic/klayout-tools/issues/219) and
  its sub-issues #222 (resistors) / #225 (MiM caps) are now *closed*, but the
  installed 0.1.0 deck still declares an active/poly/nwell/contact/metal1 layer
  set with no resistor, capacitor or bipolar device class — so the limit is
  unchanged **here** until `klt` is upgraded. Re-check `klt --version` and
  re-run `run_checks.sh` after any upgrade; if the deck grows those classes,
  the undrawn devices in all three cells become drawable and the coverage
  caveats above shrink.
  The *silence* is the sharper half and is separately filed by #68:
  [klayout-tools#288](https://github.com/2AMLogic/klayout-tools/issues/288) —
  extraction absorbs unmodelled-device geometry into interconnect with an empty
  `warnings` array, so the failure mode is a wrong netlist, not an error.
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
  though the schematic calls it an internal node. There is no pin-set knob on
  `klt extract` or in the `klt lvs` request, and the alternative — deleting the
  label from the sub-cell — would break the sub-cell's own standalone LVS. The
  manifest therefore declares it as a port. Filed:
  [klayout-tools#291](https://github.com/2AMLogic/klayout-tools/issues/291).
- **Body terminals are synthetic.** The deck draws no substrate tap, so NMOS
  bodies land on a global `vsubs` net; gf180mcu has no distinct tap or
  well-label layer, so an extracted Nwell is an anonymous net. `lvs_reference.py`
  therefore rewrites the schematic's body nodes to match. **Consequence: a
  mis-tied or untied well would compare clean.** Well/substrate ties are *not*
  verified by this flow — `bias_core` draws a continuous VSS-tied guard ring and
  a VDD-tied Nwell strap, and their correctness is a **design-review** claim.
  Filed: [klayout-tools#281](https://github.com/2AMLogic/klayout-tools/issues/281);
  its follow-up #285 adds a `device.body_unverified` warning, but `klt 0.1.0`
  does not emit it (`warnings` is empty in both cells' `extract.json`), so there
  is no mechanical confirmation signal to read yet.
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
- **Single metal level.** The extraction deck declares `Metal1` only, so a cell
  must route on Metal1 to extract as connected nets. Upstream
  [klayout-tools#220](https://github.com/2AMLogic/klayout-tools/issues/220) and
  #238 are closed, but **re-checked at `klt 0.1.0` for #68, #69 and again for
  #70: the installed version still declares one metal** (`metals=((34, 0),)`),
  so `bias_core`, `por_comparator` and `por_output_chain` all route on Metal1
  with Poly2 as the crossing layer. Re-check `klt --version` before assuming
  the limit still applies. This is also half of why the MiM caps are undrawn:
  the gf180mcu MiM stack lives on metal 3/4, which the deck does not declare at
  all.
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
4. `bash layout/run_checks.sh <name>` — and do not treat a clean LVS as real
   until both negative controls report detected.

Keep the friction protocol running while you do it: every time `klt` is
awkward, missing something, or wrong, file it generically at
`2AMLogic/klayout-tools` — the tool gap, never the design.
