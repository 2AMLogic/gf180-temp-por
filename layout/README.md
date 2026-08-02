# layout/ — DRC/LVS flow for gf180mcu, driven by klayout-tools

This directory holds the block's layout artifacts and the **repeatable DRC/LVS
invocation** they are checked with. It is `klt`-driven end to end: no GUI, no
interactive KLayout session, no netgen/magic.

> **Status: the flow is proven, the block's layout is not drawn.**
> One real cell from `design/` is laid out here, and it runs DRC-clean and
> LVS-clean against its schematic-derived netlist, with both LVS negative
> controls detected. That is the deliverable of #16 — a working flow that the
> floorplan (#17) and post-layout verification (#18) inherit instead of
> rediscovering. It is **not** a claim about the block's layout, which does not
> exist yet. #17's floorplan sketch and matching plan — the ranked,
> #15-data-driven common-centroid/interdigitation/guard-ring plan this flow's
> cells will eventually implement — is [`layout/floorplan.md`](floorplan.md).

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

## The cell under test

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
  whole. That is why the proof cell is an all-MOS one. Upstream:
  [klayout-tools#219](https://github.com/2AMLogic/klayout-tools/issues/219)
  (and its sub-issue #222 for resistors) — already open before this bring-up.
- **Body terminals are synthetic.** The deck draws no substrate tap, so NMOS
  bodies land on a global `vsubs` net; gf180mcu has no distinct tap or
  well-label layer, so an extracted Nwell is an anonymous net. `lvs_reference.py`
  therefore rewrites the schematic's body nodes to match. **Consequence: a
  mis-tied or untied well would compare clean.** Well/substrate ties are *not*
  verified by this flow. Filed:
  [klayout-tools#281](https://github.com/2AMLogic/klayout-tools/issues/281).
- **The reference netlist has to be converted, not just pointed at.** `klt lvs`
  needs plain-element SPICE (`M1 d g s b nfet L=0.5U W=1U`); `design/netlist.py`
  emits the ngspice simulation form (`XM1 d g s b nfet_03v3 L=0.5u ...`).
  Pointing LVS at the raw export does not error — it silently produces a
  net-merge cascade that reads like a layout bug. `lvs_reference.py` is this
  repo's converter. Filed:
  [klayout-tools#280](https://github.com/2AMLogic/klayout-tools/issues/280).
- **A parameter-only defect is poorly localised on a small cell.** The
  `device-param` control above is *detected*, but on a two-device cell it is
  reported as `device.unmatched` + a `net.unmatched` cascade rather than the
  documented `device.property` entry naming the wrong parameter — so the report
  points at connectivity when the defect is a width. It classifies correctly
  once the circuit is larger. Filed:
  [klayout-tools#282](https://github.com/2AMLogic/klayout-tools/issues/282).
- **Single metal level.** The extraction deck this flow was brought up on
  declares `Metal1` only, so a cell must route on Metal1 to extract as connected
  nets. Upstream [klayout-tools#220](https://github.com/2AMLogic/klayout-tools/issues/220)
  is closed — re-check `klt`'s version before assuming the limit still applies
  when #17 needs upper metal.
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
   netlist it derives from, the devices to take, the layout's own pin set, and
   which PMOS devices share which drawn Nwell. Run it to write the reference.
3. Copy an existing `cells/<cell>.lvs.json` and point it at the new names.
4. `bash layout/run_checks.sh <name>` — and do not treat a clean LVS as real
   until both negative controls report detected.

Keep the friction protocol running while you do it: every time `klt` is
awkward, missing something, or wrong, file it generically at
`2AMLogic/klayout-tools` — the tool gap, never the design.
