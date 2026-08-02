# layout/ — DRC/LVS flow for gf180mcu, driven by klayout-tools

This directory holds the block's layout artifacts and the **repeatable DRC/LVS
invocation** they are checked with. It is `klt`-driven end to end: no GUI, no
interactive KLayout session, no netgen/magic.

> **Status: the flow is proven, and the first of the block's four sub-circuits
> is drawn — as far as the deck can see it.**
> #16 brought the flow up on one two-device proof cell. #68 added `bias_core`,
> the first real sub-circuit: all **34** of its MOS devices, DRC-clean and
> LVS-clean against the schematic-derived netlist, with both negative controls
> detected. That is **not** the whole cell — `bias_core`'s 10 vertical PNPs, 4
> poly resistors and 2 MiM caps are outside the curated deck's device coverage
> and are deliberately not drawn (see
> [The cells under test](#the-cells-under-test) and
> [Known deck limits](#known-deck-limits--what-a-clean-lvs-here-does-not-prove)).
> The remaining three sub-circuits and the top-level assembly are not drawn.
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
  whole. That is why the proof cell is an all-MOS one, and why `bias_core`'s
  16 non-MOS devices are **not drawn** rather than drawn-and-ignored — a drawn
  poly resistor body extracts as interconnect and shorts its own terminal nets.
  Still true at `klt 0.1.0`. Upstream:
  [klayout-tools#219](https://github.com/2AMLogic/klayout-tools/issues/219)
  (and its sub-issue #222 for resistors) — already open before this bring-up.
  The *silence* is the sharper half and is separately filed by #68:
  [klayout-tools#288](https://github.com/2AMLogic/klayout-tools/issues/288) —
  extraction absorbs unmodelled-device geometry into interconnect with an empty
  `warnings` array, so the failure mode is a wrong netlist, not an error.
- **There is no annotation-layer contract**, so the reserved passive/bipolar
  region in `bias_core` sits on a layer (200/0) chosen because no deck reads it
  today, not because any deck promises not to. Filed:
  [klayout-tools#289](https://github.com/2AMLogic/klayout-tools/issues/289).
  Re-check after a `klt` upgrade: if `klt drc`'s or `klt extract`'s layer set
  ever grows to include it, the reports move and `run_checks.sh` says so.
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
  circuit is larger" expectation rather than an assumption about it. Filed:
  [klayout-tools#282](https://github.com/2AMLogic/klayout-tools/issues/282).
- **Single metal level.** The extraction deck declares `Metal1` only, so a cell
  must route on Metal1 to extract as connected nets. Upstream
  [klayout-tools#220](https://github.com/2AMLogic/klayout-tools/issues/220) and
  #238 are closed, but **re-checked at `klt 0.1.0` for #68: the installed
  version still declares one metal**, so `bias_core` routes on Metal1 with
  Poly2 as the crossing layer. Re-check `klt --version` before assuming the
  limit still applies.
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
