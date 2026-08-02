# layout/ — DRC/LVS flow for gf180mcu, driven by klayout-tools

This directory holds the block's layout artifacts and the **repeatable DRC/LVS
invocation** they are checked with. It is `klt`-driven end to end: no GUI, no
interactive KLayout session, no netgen/magic.

> **Status: the block's layout is drawn and assembled — as far as the deck can
> see it.**
> #16 brought the flow up on one two-device proof cell. #68 added `bias_core`
> (**34** MOS devices), #69 `por_comparator` (**18**), #70 `por_output_chain`
> (**28**, after issue #56's release latch) and #71 `temp_core` (**55** drawn:
> 39 schematic MOS split into
> interleaved fingers, plus 6 edge dummies). #72 assembles all four into
> **`temp_por_top`** — with the domain-seam moat, the perimeter guard ring and
> the `VDD`/`VSS` rails. #92 then drew `por_output_chain`'s **2 MiM caps** (5
> drawn units) as the first non-MOS devices in the block, and #93 folded
> `temp_core`'s PNP array and `R2` gain ladder into the extracted cell as real
> `bjt`/`ppolyf_u` devices (**114** drawn, up from 55), retiring the sibling
> top cells that used to hold them. #91 then drew `por_comparator`'s
> 3-segment sense divider as real `ppolyf_u_1k`-class poly resistors (**21**
> drawn, up from 18), and #90 drew `bias_core`'s **16**: 10 vertical PNPs, 4
> poly resistors (strung into 24 legs) and 2 MiM caps. **Every sub-circuit is
> now whole at the *cell* level** — every device in all four schematics is
> drawn, extracted and compared, except `temp_core`'s single MiM cap.
> `temp_por_top`'s own committed assembly still predates all four of
> #90/#91/#92/#93 — and issue #56's release latch too: **198** devices, **131**
> nets, and the ratified 5-pad pinout, unchanged by any of them; #97 is what
> unfreezes it, reworking that floorplan once for all of them at once rather
> than once per sub-cell change (rebuilding the assembly before then DRCs
> dirty — see the `temp_por_top` section). Every cell under test is LVS-clean
> against the schematic-derived netlist with every applicable negative control
> detected (three per cell where a cell draws a resistor or a bipolar:
> topology, device-param, and passive-param). **DRC is *not* currently clean
> everywhere, and the committed reports do not yet say so.** `por_comparator`'s
> committed `drc.json` reads `clean`, but it was recorded under an older `klt`
> whose `"enclosing"` primitive missed zero-overlap escapes
> ([klayout-tools#318](https://github.com/2AMLogic/klayout-tools/issues/318),
> fixed upstream); that cell's *unchanged* committed GDS fails **2×
> `poly2.enclosing.contact.1`** under the current deck — a real drawing defect
> that was always there, fixed by #102, root-caused by #103 (which also added
> the deck-hash guard that catches this class of stale-report drift). Until
> #102 lands, treat every "clean" DRC row in this file as *as-recorded*, not as
> a current verdict; the `por_comparator` section and
> [Known deck limits](#known-deck-limits--what-a-clean-lvs-here-does-not-prove)
> have the full trace.
> `temp_core`'s own MiM cap is the one device still outside what the curated
> deck can extract, deliberately not drawn *into the extracted cell*, and
> inherited unchanged by `temp_por_top`, which therefore cannot be LVS'd whole
> either (see
> [The cells under test](#the-cells-under-test) and
> [Known deck limits](#known-deck-limits--what-a-clean-lvs-here-does-not-prove)).
> **What no check in this flow covers** is guard-ring and well-tie
> *correctness*: the deck has no tap or well-label layer, so a broken or
> floating ring is DRC-clean and LVS-match. `temp_por_top` therefore carries
> its own build-time geometric checks for that; see its section below.
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

**0b. Deck-hash consistency gate.** A recorded DRC-clean verdict is only
meaningful relative to one `klt` deck revision, so every committed
`layout/reports/*/drc.json` has to agree on `provenance.deck.content_hash` —
otherwise the evidence describes two different rule sets and a clean report
for one cell says nothing about another's. Unscoped even for a single-cell
run, since it is a property of the whole `layout/reports/` directory, not of
any one cell; tolerates `temp_por_top` while it is intentionally frozen
behind #97 (`lvs_reference.FROZEN_DECK_CELLS`):

```bash
python3 layout/lvs_reference.py --check-deck-hash
```

Both gates run before the first per-cell check, and `run_checks.sh` is
`set -e`, so a cell that fails one of them used to abort the whole script —
including the cells that were current (#102). Frozen cells (below) are why that
is no longer possible.

#### Frozen cells

One cell — `temp_por_top` — is deliberately held behind its own sources: its
committed assembly stays at the #72 sub-cell set because rebuilding it against
today's grown sub-cells is DRC-dirty at the instance boundaries, and **#97**
owns reworking the floorplan once for all of that rather than once per sub-cell
change. `lvs_reference.py`'s `FROZEN_CELLS` table declares that, and **both**
`--check` paths read it (`build_cells.py` imports the module), so a freeze is
declared once and cannot drift between the two gates:

```python
FROZEN_CELLS = {
    "temp_por_top": {
        "issue": "#97",              # the freeze's removal condition
        "why": "...",                # why it is frozen, in prose
        "gds_sha256": "...",         # the pinned committed stream
        "reference_sha256": "...",   # the pinned committed reference
    },
}
```

A freeze is **not** "stop checking this cell". The committed bytes are still
verified on every run against the digests pinned above; what is suspended is
only the comparison against a *fresh rebuild*, which is the part #97 owns. So
the states stay distinguishable in the log:

| Committed artefact | `--check` says |
| ------------------ | -------------- |
| unfrozen, current | `ok <artefact>` |
| unfrozen, source has moved | `FAIL …: committed … is stale` |
| frozen, pinned baseline intact | `frozen <artefact> … (see #97)` |
| frozen, baseline **changed** | `FAIL …: no longer matches the pinned frozen baseline` |

Running either script *without* `--check` also skips a frozen cell (rather than
overwriting it and quietly breaking the pin) unless it is named explicitly with
`--cell`, which is #97's own workflow. `layout/tests/test_lvs_reference.py`'s
`FrozenCellTest` asserts the pinned digests against the committed files, so the
pin is enforced in CI too (stdlib only, no `klt`) — and asserts that an
*unfrozen* stale cell still fails, so the mechanism cannot decay into a blanket
staleness bypass.

**To end a freeze**: delete its `FROZEN_CELLS` entry. Nothing else changes —
both gates fall straight back to rebuild-and-compare.

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

That byte-stability is across runs with the **same** `klt`. Every report records
the deck it was produced against (`provenance.deck.content_hash`), and `klt`
0.1.0's curated decks are still moving without a version bump — so the committed
set is *heterogeneous by cell*: each cell's reports carry whatever deck was
current when that cell last landed, and a re-run against a newer `klt`
legitimately rewrites them (new deck hash, plus any diagnostic field the newer
extractor emits). Re-running the whole flow to normalise that is a deliberate,
separate act, not a side effect of touching one cell: a PR that changes one
cell's geometry regenerates **that cell's** reports and leaves the rest alone,
because `reports/` is append-only evidence (`CLAUDE.md`) and silently restamping
five other cells' recorded runs with a deck they were never checked against
would destroy exactly the provenance the directory exists to carry.

## The cells under test

### `bias_core` — the shared bias/reference core, whole (#68, completed by #90)

`design/bias_core.sch`'s **50 devices** — all of them — drawn from
`design/netlist/bias_core.spice`. 434.9 × 285.7 µm, 3578 polygons.

**What a clean run here covers.** #68 drew the 34 MOS devices and left the
other 16 out, deliberately: the curated deck recognised `nfet`/`pfet` only, so
a drawn poly resistor body extracted as ordinary interconnect and **shorted its
own two terminal nets** (`NB`–`EC`, `VREF`–`ER`, `NBTOP`–`NB`, `NZ`–`N2`),
which then read as a layout bug in the part of the cell that *could* be
checked. The passive/bipolar area was a blank rectangle on annotation layer
200/0 instead. `klt 0.1.0` declares `bjt`, `ppolyf_u_1k` and
`cap_mim_2f0_m4m5_noshield` as well, so #90 drew them:

| Drawn as | Devices | Recognised by |
| --- | --- | --- |
| Vertical PNPs | `XQ1`, `XQ8A`…`XQ8H`, `XQR` (10) | one shared `Nwell` base, a `Comp` emitter window per device, a per-device `DRC_BJT` mark; collector = substrate, not drawn |
| Poly resistors | `XR1`, `XR2`, `XRT`, `XRZ` (4, folded into **24** legs) | `Poly2` + `RES_MK` + `SAB` + `Resistor`, with `Pplus` for the p+ implant; unmarked bends and heads are the terminals |
| MiM caps | `XCC`, `XCOK` (2) | `FuseTop` + `CAP_MK` + `MIM_L_MK` over a `Metal4` bottom plate |

The four formerly-shorted net pairs are now four pairs of **distinct extracted
nets**, and the reserved 200/0 rectangle is gone. Three DRC rules that used to
appear under `rules_skipped` because no stream drew their layers —
`bjt.separation.comp.1`, `mim.space.1`, `mim.enclosing.fusetop.1` — are now
actually exercised.

That the marker geometry is what does it, rather than the compare being
insensitive to it, was confirmed by rebuilding the same cell with one marker
layer moved to a layer no deck reads:

| Defect built | Result |
| --- | --- |
| `RES_MK` removed | 24 `ppolyf_u_1k` devices gone; **54 nets collapse to 30** — the documented short cascade, exactly the failure #68 avoided by not drawing |
| `DRC_BJT` removed | 10 `bjt` devices gone; the base well net disappears (54 → 53 nets) |

Consequences to carry forward, stated so nobody has to re-derive them:

- **Sheet resistance is the PDK's default option, not the schematic's.** The
  schematic instantiates `ppolyf_u_3k`. That whole family — `_1k`/`_2k`/`_3k` —
  is *one drawn device*; which sheet-rho a run gets is a deck-level `POLY_RES`
  option, not drawn geometry. `klt`'s deck models only the PDK's own default
  (`POLY_RES='1k'`), so a drawn leg is recognised as `ppolyf_u_1k` at
  1000 Ω/sq. The compare therefore answers for every leg's **drawn geometry**
  (2 µm wide, exactly the golden `r_length`/legs long) and not for the
  resistance the schematic intends. Known upstream, in
  [klayout-tools#299](https://github.com/2AMLogic/klayout-tools/issues/299)'s
  own non-goals.
- **A fold is N devices, not one.** The deck runs no device-combination step
  and cuts each *marked* leg out of poly separately, so a serpentine extracts
  as one two-terminal device per leg with the unmarked bends as anonymous
  nodes. `lvs_reference.py` emits the same N series legs — the same treatment
  `fingers` gives a multi-finger MOS — so both sides describe the same object.
- **A bipolar's base is an anonymous well and its collector is the substrate
  global.** The deck draws no collector layer and gf180mcu has no well-label or
  tap layer, so the schematic's `VSS` base/collector nodes are rewritten in the
  reference. The drawn Nwell tap ring that ties the base to `VSS` is a
  design-review claim, like every other tie in this repo
  ([klayout-tools#303](https://github.com/2AMLogic/klayout-tools/issues/303)).
- **MiM plates own no net.** Unchanged from `por_output_chain`: `klt` registers
  a recognised capacitor's plates outside its own metal/via stack, so no drawn
  routing can put a plate on a schematic net
  ([klayout-tools#314](https://github.com/2AMLogic/klayout-tools/issues/314)),
  and the drawn device class is the deck's `m4m5` stack where the schematic
  says `m3m4`
  ([#315](https://github.com/2AMLogic/klayout-tools/issues/315)). `NZ`
  therefore reaches the compare through `XRZ`'s terminal alone.
- Nothing here says the reference is 1.20 V, that `R2/R1` is 11.726, or that
  the 8:1 emitter ratio *achieves* its target ΔV_BE. Those are `sim/`'s claims,
  unchanged. What the layout now does say is that the 8× leg is drawn as eight
  identical devices centred on the 1× device, and that every resistor leg is
  drawn at the same width.

**Structure.** Routing is Metal1-only throughout; the scheme that makes a
50-device cell routable on one metal is **horizontal Poly2 tracks (one per
signal net) with vertical Metal1 risers**, so a riser crosses every track it
does not belong to with no contact. `VDD` and `VSS` are Metal1 rails above and
below the row (`VSS` now runs the full cell width, because the PNP array's well
tap ties to it). One drawn Nwell holds the whole PMOS row; a second, separate
one is the PNP array's shared base. The passive block sits to the right of the
device row with **its own eight-track band** below it — one track per net a
drawn passive touches — and the five nets that exist in both regions are
carried across by **one Metal1 jog column each**, in the 13 µm gap between
them. The jog columns rise in x with their row track's y, which is what keeps a
jog from ever descending across a track that reaches past it.

**Matching, where the cell actually has a ratio to hold.** `floorplan.md`'s
ranked common-centroid plan prescribes nothing for this cell, and nothing was
invented for the MOS row. The one place a centroid *is* drawn is the pair the
whole reference rests on: **`XQ1` sits at the centre of a 3×3 array whose
perimeter is `XQ8A`…`XQ8H`**, so the 8× leg's centroid is the 1× leg's.
`XQR` — the `VREF` branch's own separate 1× device, not part of that ratio —
takes a fourth column beside the middle row. A unit test asserts the centroid
and the adjacency from the drawn slot table rather than from this paragraph.

The resistors get the matching they *can* get and no more: every leg of every
fold is the golden netlist's own `r_width` (2 µm), the first-order matching
parameter. Leg **lengths** differ per device and have to — `R2/R1` is
4104/350, whose lowest terms need a 2 µm unit leg, i.e. 2227 legs across the
two devices. A non-integer design ratio is a schematic fact, and this layout
does not quietly "fix" it; the fold picks the closest exact division per
device instead (`lvs_reference.resistor_segments`, which also forces an even
leg count so both ends of a fold come out at the same edge).

**Matched pairs** in the MOS row get ordinary matched-pair practice — adjacent
placement, same orientation, identical drawn geometry, common well:
`XMI1`/`XMI2`, `XML1`/`XML2`, `XMOKA`/`XMOKB`, `XMOL1`/`XMOL2`, and the three
core mirror legs `XMP1`/`XMP2`/`XMP3`.

**Guard ring and well ties are drawn, and are a design-review claim, not a
checked one.** A continuous VSS-tied p-substrate guard ring (COMP + Metal1,
contacted at 1 µm pitch, no floating segment) surrounds the cell; the PMOS
Nwell has its own VDD-tied COMP strap and the PNP array's Nwell a VSS-tied tap
ring on three sides (open at the bottom, where every escape riser leaves). Per
[klayout-tools#303](https://github.com/2AMLogic/klayout-tools/issues/303) the
deck has no tap/well-label layer and no ring-continuity rule, so **a mis-tied,
untied, or physically broken ring would compare clean** — this flow does not
verify it. That now bites in one more place than it used to: the PNP base tie
is one of those ties, so a clean LVS says the ten bipolars' bases are one node,
not that that node is `VSS`.

Recorded result (`layout/reports/bias_core/`):

| Check | Result |
| ----- | ------ |
| `klt drc --deck gf180mcu` | clean — 0 violations (`bjt.*` and `mim.*` rules now exercised, not skipped) |
| `klt extract --deck gf180mcu` | **70** devices (18 nfet, 16 pfet, 10 bjt, 24 ppolyf_u_1k, 2 MiM), 54 nets, 6 pins |
| `klt lvs` | **match** — 70/70 devices, 54/54 nets, 6/6 pins, 0 errors (2 `device.body_unverified` warnings) |
| negative control `topology` | detected (exit 3; `device.unmatched` 1, `topology` 6) |
| negative control `device-param` | detected (exit 3; `device.property` 5, `topology` 6) |
| negative control `passive-param` | detected (exit 3; `device.property` 11, `topology` 9) |

### `por_comparator` — the POR threshold comparator (#69, sense divider #91)

`design/por_comparator.sch`'s 21 devices, drawn from
`design/netlist/por_comparator.spice`. 445.0 × 164.7 µm, two cells (it
instances the proof cell below).

**All 21 devices are now drawn, extracted and compared.** 18 are MOS. The
other 3 are the sense divider `XRTOP`/`XRBOT`/`XRHYS` (schematic
`ppolyf_u_3k` poly resistors) — reserved as a blank floorplan rectangle
through #69, and drawn for real as of #91: `klt 0.1.0`'s extraction deck
recognises a drawn, `RES_MK`/`SAB`-marked poly resistor as a real
two-terminal device ([klayout-tools#219](https://github.com/2AMLogic/klayout-tools/issues/219)/[#222](https://github.com/2AMLogic/klayout-tools/issues/222)), but only
two flavors of gf180mcu's high-sheet-rho poly family are wired: the base
`ppolyf_u` (350 ohm/sq) and the PDK's own default `ppolyf_u_1k` (1000
ohm/sq, [klayout-tools#299](https://github.com/2AMLogic/klayout-tools/issues/299)). `_2k`/`_3k` are not — filed as
[klayout-tools#323](https://github.com/2AMLogic/klayout-tools/issues/323) since this design specifically needs `_3k`. So each
segment is drawn with `RES_MK`/`SAB`/`Resistor(62,0)` — exactly what a real
`ppolyf_u_3k` resistor's geometry would carry too, since the three flavors
are geometrically identical — and extracts as the deck's `ppolyf_u_1k`
class. `layout/lvs_reference.py`'s reference cards therefore compare each
segment's *drawn* length against the deck's modelled 1000 ohm/sq, not the
schematic's 3000 ohm/sq: a **documented, deliberate fidelity loss**, in the
same spirit as the NMOS/PMOS body-net rewrites below. It is still a
meaningful check for *this* divider specifically: all three segments are
the same poly flavor and width, so the sheet-rho substitution is a common
factor across all three — the check still proves each segment's drawn
length (so its resistance *ratio* against the other two, which is what the
hysteresis ratio actually depends on — `design/por_comparator.md`, "Why the
hysteresis is a resistor ratio") is exactly what the schematic asks for.
What it does not prove is the *absolute* resistance at the schematic's true
3000 ohm/sq corner; that remains `sim/`'s claim, unchanged.

Consequences to carry forward:

- `SNS` and `SNSB` now have **two** terminals each — one MOS (`XMINA`'s
  gate, `XMHSW`'s drain) and one resistor terminal — correcting a stale
  claim from #69 that each had only one (#82's curation of #91 found
  `SNS`/`SNSB` no longer matched that description at all).
- Nothing here says `RTOP/RBOT` is 1.16667, that V_hys is 150 mV, or that
  the three segments match to the schematic's absolute values. Those remain
  `sim/`'s claims.
- Each segment folds into a roughly-square zig-zag serpentine
  (`build_cells.py`'s `_resistor_leg_plan`/`_resistor_string`) whose drawn
  body AREA reconstructs the schematic's own `r_length` exactly (to
  floating-point noise), so no dimension is retyped from the golden
  netlist. The three strings sit side by side past the device row; the
  cell's footprint grew from #69's 313 × 230 µm placeholder-rectangle
  bounding box to 445 × 165 µm as a direct result of drawing real (rather
  than reserved) geometry.
- Routing `SNS`/`SNSB` out to the divider crosses Metal2, not Poly2: a
  Poly2 track spanning the whole divider width would physically cross
  every leg-to-leg gap of all three folded strings, filling each gap with
  unmarked-but-touching Poly2 and bridging every leg together — a real
  short, and the actual root cause of the "resistor shape ignored"
  extraction warnings hit while debugging #91 (the Poly2 track's own
  contacts land within 2, not 20+, distinct clusters once the crossing is
  removed). The two nets instead escape onto Metal2 just past the device
  row (one contact + Via1 each) and cross the divider on that layer, which
  cannot short to the resistor bodies no matter what it passes over. The
  `VDD`/`VSS` supply rails were a second instance of the same class of bug:
  extending either rail's Metal1 all the way to the divider's right edge
  (so `XRTOP`'s `VDD` end and `XRHYS`'s `VSS` end could each reach it with
  a plain riser) meant the rail's own Y-band crossed `XRBOT`'s and
  `XRHYS`'s *other* terminal risers on their way down to the Metal2
  trunks — shorting `SNS`/`SNSB` to `VDD`. Both rails now stop just past
  their own divider terminal instead of reaching the full width.
- That Metal2 escape's own two Poly2 landing contacts were the cell's last
  DRC violations, and the reason this cell is the one that proved a committed
  report can lie (#102): each net's Poly2 track *ended on* its landing
  contact's centre x, so the Poly2 covered only the contact's west half and
  left the east half bare — two `poly2.enclosing.contact.1` (DRM `CO.3`)
  violations in the committed stream, under a committed `drc.json` that said
  `clean`. The report was textually indistinguishable from a genuine clean one
  (`status: clean`, `violation_count: 0`, empty `violations`), which is exactly
  why nothing noticed. Both tracks now run *past* their contact by
  `build_cells.py`'s `_poly2_landing_x1`, which derives the overhang from
  `CO.3` and the contact size rather than from a hand-written coordinate, so
  the enclosure cannot silently go to zero again if the track pitch moves.
- [klayout-tools#288](https://github.com/2AMLogic/klayout-tools/issues/288)'s per-cell warning count for "poly shapes with the
  resistor-body signature but no marker layer at all" is **12** here, not
  lower than #69's baseline of 10 as originally hoped. Root cause: none
  of the 12 are divider geometry — the divider's own marked legs
  contribute *zero* to this count now (down from all of them, since they
  used to be undrawn and so not a factor at all). All 12 are the cell's
  ordinary multi-fanout Poly2 routing tracks (`TN`, `NA`, `CMPO`, `VDDA`,
  `N1`, `POR_RAW`, `NBG`, `IBIAS`, `BIAS_OK`, `BIAS_OKB`, and now `SNS` and
  `SNSB`), which this heuristic cannot distinguish from a resistor body —
  any unmarked Poly2 net touching 2+ separate contacts trips it, resistor
  or not (10 of these tracks already did on #69's committed cell, unrelated
  to the divider; `SNS`/`SNSB` are the two newly added, each because the
  Metal2 escape above gives them a second contact — the one at the
  MOS-gate/drain end they always had, plus the new one where the track
  meets its Via1). A real fix would need the deck to distinguish "this
  candidate is already accounted for by a recognised resistor a few
  microns away" from "this is genuinely unmodelled" — out of scope here.

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
keeps **W = 2 µm** with same-flavor same-width legs and ordinary serpentine
folding for area — no end-of-string dummy legs, a layout-quality nicety out
of scope for this bring-up pass rather than a tool limit or LVS requirement.
The load mirror `XMLA`/`XMLB` gets the same ordinary matched-pair treatment
although the floorplan names no plan for it. `layout/tests/test_lvs_reference.py`'s
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
klayout-tools#285 added as an extract-time warning — it still only surfaces
as an LVS mismatch category (see the recorded result below).

**`temp_por_top` needs its own follow-up pass.** Drawing the divider for real
grew this cell's footprint well beyond #69's placeholder rectangle, which
invalidates `temp_por_top`'s existing instance placement (confirmed: a
`temp_por_top` rebuilt against this change alone is DRC-dirty at the
`por_comparator`/neighbor-cell boundary). `temp_por_top`'s own committed
GDS is intentionally left untouched by this change — see #97, which waits
for #90/#92/#93 to land too before re-deriving the floorplan once, rather
than reworking it four times.

**The "clean" DRC row below is currently stale (#102 in flight; #103 root-caused
it and added the guard that catches this class of drift).** The committed
`layout/reports/por_comparator/drc.json` was recorded against an installed
`klt` build whose `Region.enclosing_check`/`enclosed_check`-backed
`"enclosing"` check primitive only reports *marginal* violations at facing
edges of shapes that already partially overlap — a shape of the enclosed
layer with **zero** overlap with the enclosing layer (the worst-case
enclosure failure, not a lesser one) produced no violation at all. Filed
generically, with no design details, as
[klayout-tools#318](https://github.com/2AMLogic/klayout-tools/issues/318) and
fixed upstream (`klayout-tools` PR #327): the same primitive now also flags
that zero-overlap escape under the same rule id. Rerunning `klt drc` against
this cell's *unchanged* committed GDS with the fix installed reports 2
violations of `poly2.enclosing.contact.1` (DRM `CO.3`, 0.07 µm Poly2-over-
Contact — a threshold that has never moved: `gf180mcu.py`'s
`poly2.enclosing.contact.1` entry is unchanged since it was first authored),
both at the `SNS`/`SNSB` Metal2-escape landing contacts. So this was never a
clean layout that a rule tightened against — it was always 0.07 µm short of
the rule, and the "clean" report below was a false negative in the tool, not
evidence the layout ever met the rule. #102 root-causes the exact drawing
defect (`build_cells.py`'s `SNS`/`SNSB` Poly2 track landing its contact with
zero enclosure margin) and fixes it; the committed GDS/report here are
intentionally left as `main` has them until it lands, per this repo's
"regenerate the evidence, don't hand-edit it" rule.

Recorded result (`layout/reports/por_comparator/`) — **stale, see caveat
above; do not read the DRC row as a current verdict**:

| Check | Result |
| ----- | ------ |
| `klt drc --deck gf180mcu` | clean — 0 violations (stale: current `klt` finds 2× `poly2.enclosing.contact.1`, see #102) |
| `klt extract --deck gf180mcu` | 21 devices (12 nfet, 6 pfet, 3 ppolyf_u_1k), 18 nets, 8 pins |
| `klt lvs` | **match** — 21/21 devices, 18/18 nets, 8/8 pins |
| negative control `topology` | detected (exit 3; `device.unmatched` 1, `topology` 2) |
| negative control `device-param` | detected (exit 3; `device.property` 5, `topology` 2) |

### `por_output_chain` — the reset output chain (#70, MiM caps added by #92)

`design/por_output_chain.sch`'s 28 MOS devices **and both of its MiM caps**,
drawn from `design/netlist/por_output_chain.spice`. 225.3 × 105.9 µm, 1493
polygons. The 28th MOS, `XMRLK`, is the release latch issue #56 added
([DR-016](../spec/decision-records/DR-016-por-ramp-rate-chatter-release-latch.md));
it is placed beside `XMDBNI`, whose gate net (`ND1`) and drawn geometry it
shares.

**What a clean run here covers, and what it does not.** The cell has 30
schematic devices and all 30 are drawn: 28 MOS (14 pfet, 14 nfet), plus `XCDG`
(11 × 11 µm) and `XCTIM` (4 × 28 × 28 µm). The extraction sees **33** devices,
because `XCTIM`'s `m=4` draws as four units and the curated deck models no
multiplier — the same treatment `temp_core`'s multi-finger MOS get.

The caps were reserved floor area until #92, when the deck grew a MiM device
class. What each half of the compare now answers for:

| Device | Drawn as | What LVS proves | What it does not |
| --- | --- | --- | --- |
| 28 MOS | Comp/Poly2/Contact/Metal1 | count, sizing, signal-net topology | body ties (see below) |
| 5 MiM units | `FuseTop` + `CAP_MK` + `MIM_L_MK` over `Metal4` | count, **plate area → capacitance** (242 fF and 4 × 1.568 pF, from the golden `c_width`/`c_length`) | what either plate is connected to |

The connectivity gap is the deck's, not the drawing's: `klt` registers a
recognised capacitor's two plates as their own self-connected nodes *outside*
its metal/via stack, and the top plate's layer (`FuseTop`) is not in that stack
at all, so **no drawn routing can put a MiM plate on a schematic net** — every
cap extracts as an isolated pair of nets whatever is drawn around it. Drawing
plate-to-rail routing anyway would add real geometry no check in this flow can
read, so it is not drawn. `lvs_reference.py` names the plate nets after the
schematic nodes they are *meant* to be on (`XCDG.NDG`, `XCTIM.3.VSS`) so the
loss is legible in the reference netlist instead of hiding behind an anonymous
node. Filed generically:
[klayout-tools#314](https://github.com/2AMLogic/klayout-tools/issues/314).

A second, smaller substitution: the schematics instantiate the PDK's
**4-metal-level** MiM (`cap_mim_2f0_m3m4_noshield`); the curated deck models
only the DRM's "10.4.2 MIM Option B" **5-metal-level** stack
(`cap_mim_2f0_m4m5_noshield`) and declares no other MiM class, so that is what
the layout draws. Same 2.0 fF/µm² device, same plate geometry, same extracted
capacitance — only the metal pair the stack sits on differs. Filed:
[klayout-tools#315](https://github.com/2AMLogic/klayout-tools/issues/315).

There is **no resistor in this cell** — `por_output_chain.md`'s only mention of
one is in the *negative*, explaining why the ≥1 ms one-shot is a current-starved
ramp rather than an RC ("1 ms into a 6 pF capacitor needs ~160 MΩ, which is not
buildable here"). Confirmed against the current schematic export: the golden
netlist's only non-MOS cards are the two `cap_mim_2f0_m3m4_noshield` calls
above. So the resistor half of the deck's coverage gap
([#222](https://github.com/2AMLogic/klayout-tools/issues/222)) does not bear on
this cell at all.

The plate-net gap **costs no net** in the compare: `NDG` and `TIM` each carry
MOS terminals as well as a cap terminal, so every net in the schematic still
exists on both sides with every one of its MOS connections.
`layout/tests/test_lvs_reference.py` asserts that rather than leaving it to this
paragraph, so a future schematic edit that made a cap the sole owner of a node
fails loudly instead of quietly narrowing what LVS answers for. And the two
**capacitor values** — the deglitch dwell and the one-shot width — are no longer
purely `sim/`'s claim: the drawn area behind them is now checked against the
schematic, though the wiring that delivers them is not.

**Structure.** Same scheme as `bias_core`: **horizontal Poly2 tracks (one per
signal net) with vertical Metal1 risers**. `VDD`/`VSS` are Metal1 rails above
and below the row; one drawn Nwell holds the whole PMOS row. Signal routing
stays Metal1-only — the scheme the cell was drawn with when the deck declared
one metal level, kept because redrawing a proven cell to use a capability it
does not need is a regression risk for no gain. The MiM block's `Metal4` is the
cell's only geometry above Metal1, and it is device geometry, not routing.

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

**MiM is drawn as separate floor area, still not stacked.** The two caps need
about 3.26 × 10³ µm² of plate. `design/por_output_chain.md` notes MiM sits high
in the stack and *may* be stackable over neighbouring circuitry, explicitly
deferring that to a DRC/layout call. #92 drew the plates; it did **not** make
that call in the optimistic direction. `XCTIM`'s four units are a 2 × 2 array
with `XCDG` in the column beside them, in the same place the pre-#92 reservation
occupied — above the VDD rail, inside the guard ring — and the block comes out
**74.0 × 60.2 µm** against the 70 × 62 µm that reservation predicted. Plate
spacing and bottom-plate enclosure are drawn to the DRM's own `MIMTM.1` (1.2 µm)
and `MIMTM.3` (0.6 µm) with margin, and `klt`'s `mim.space.1` /
`mim.enclosing.fusetop.1` are the two rules that check them — the whole of the
deck's MiM rule set. Stacking stays unanswered: the deck carries no inter-layer
rule that could say whether MiM over the device row is legal.

The 200/0 annotation rectangle this cell used to carry for that area is **gone**
— `extract.json`'s `ignored_layers` is now empty for this cell. `bias_core`'s is
gone too (#90); `por_comparator`'s sense-divider reservation is the last one
left.

Recorded result (`layout/reports/por_output_chain/`):

| Check | Result |
| ----- | ------ |
| `klt drc --deck gf180mcu` | clean — 0 violations (`mim.space.1` / `mim.enclosing.fusetop.1` now exercised) |
| `klt extract --deck gf180mcu` | 33 devices (14 nfet, 14 pfet, 5 `cap_mim_2f0_m4m5_noshield`), 30 nets, 6 pins |
| `klt lvs` | **match** — 33/33 devices, 30/30 nets, 6/6 pins, 0 errors (13 warnings: 2 `device.body_unverified`, 11 ambiguous-pairing `topology`) |
| negative control `topology` | detected (exit 3; `device.unmatched` 1, `topology` 12) |
| negative control `device-param` | detected (exit 3; `device.property` 5, `topology` 12) |

The 11 `topology` entries are `warning` severity, not errors: 10 of them are the
comparer reporting that it paired the 10 isolated MiM plate nets structurally
rather than by name (they are indistinguishable by construction — that *is* the
connectivity gap above), plus the one this cell already had. `klt lvs` still
exits 0 and reports `match`.

What moved in `drc.json`'s own `coverage` block, which is the check that the new
geometry is *checked* rather than merely tolerated:

- `mim.space.1` and `mim.enclosing.fusetop.1` left `rules_skipped` — they are
  now exercised, having previously appeared there only because no stream in the
  repo drew `Metal4`/`FuseTop`.
- `layers_checked` gained `46/0` and `75/0`; `layers_in_stream_without_rules`
  lost `200/0` (the reservation is gone) and gained `117/5` / `117/10`, the two
  marker layers — the extraction deck reads them, the DRC deck has no rule for
  them, and the DRM has none either.
- No new warning of any kind: `extract.json`'s `warnings` array is the same
  single #288 entry, with the same count (see the next section).

Note the deck has **no `metal4` width rule at all** — `mim.space.1` is the only
thing standing over `Metal4` geometry — so bottom-plate width is held to the DRM
by construction here, not by a check. Same posture as the Via1/Via2 sizes.

### `temp_core` — the PTAT/CTAT sensing core (#71, passives folded in by #93)

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
39 + 10 extra fingers + 6 dummies = **55** drawn MOS devices.

**The sibling-top-cell split is retired; the passives are folded into this
cell (#93).** Until #93 this GDS stream carried **three** top cells:
`temp_core` (the 55-device MOS network above, the only one `klt
extract`/`klt lvs` ever ran on) plus `temp_core_r2_ladder` and
`temp_core_pnp_array` as undrawn-device *siblings* — `klt drc` checks every
top cell in a stream, so the split let the rank-3 PNP array and the rank-2
`R2` gain ladder be DRC-checked without a drawn, unmarked poly-resistor body
shorting `PTAT` into `VSS` through the trim ladder (`klt extract`/`klt lvs`
take a single `--top` and so never saw them). That constraint was a *deck*
one: at the time, the curated `gf180mcu` extraction deck declared no
`resistor`/`bjt` device class at all, so a drawn resistor body would have
extracted as ordinary interconnect and a drawn bipolar as nothing.

`klt 0.1.0` removed it — `resistor` and `bjt` both landed
(klayout-tools#222/#223/#225) — which turned the split from a necessity into
59 real devices sitting permanently outside the only checks that could answer
for their wiring and sizing. **Decision: fold the PNP array and the `R2`
ladder into `temp_core` and retire the two sibling top cells**, rather than
add marker geometry to them in place and keep the split. A sibling is
DRC-checked but never extracted or LVS'd — keeping it would have kept a
resistor bank that can short `PTAT`/`VSS` and a PNP array with a schematic-set
8:1 ratio both outside the one check that reads device sizing, for no reason
once the deck could model them. Folding costs nothing this repo needs the
split for: the two former siblings carried no independent pin contract of
their own, and DRC on `temp_core` alone still covers the same geometry now
that it is drawn in one stream.

**What is drawn and how.** `XR1`/`XRISO`/`XRZ`/`XR2F`/`XR2T5..T0` (the `R2`
gain ladder plus the isolation and zero resistors) are drawn as
`ppolyf_u`-recognised bodies: `SAB` (49/0) + `RES_MK` (110/5) over Pplus'd
Poly2, so the deck cuts each body out of ordinary poly connectivity and
extracts a resistor instead of shorting its own two terminals. Every resistor
is a **series string of straight segments** at the schematic's own drawn
length (KLayout solves a resistor's `L`/`W` from its recognised region's own
area and perimeter, so a folded/serpentine body would extract the wrong
length), reached from the routing channel on **Metal2 risers rather than poly
crossunders** — deliberately, so the new geometry adds no poly shape that
touches contact at 2+ points and could be mistaken for another unmodelled
resistor body (see "Known deck limits" below). `XQ1`/`XQ8A..H` (the rank-3
PNP centroid array: `XQ1` centre, the eight `XQ8` units around it, both inside
a ring of unmarked dummy units) each get a per-emitter `DRC_BJT` (127/5)
patch scoped to their own emitter, not a blanket over the whole array — a
marker over the shared n+ base ring would extract a 26th device the golden
netlist never asked for, and marking the sixteen dummies would add sixteen
more.

**One device stays out: the MiM cap `XCC`.** Two independent blockers, either
sufficient: the deck models exactly one MiM device
(`cap_mim_2f0_m4m5_noshield`, the DRM's 5-metal-level Option B) while this
cell's cap is the `m3m4` flavour the schematic names (same substitution
`por_output_chain`'s MiM caps make, klayout-tools#315); and a recognised MiM's
two plate regions are registered *outside* the deck's metal/via connectivity
stack (klayout-tools#314), so a drawn `XCC` would compare as a capacitor
floating between two anonymous nets — which says less than leaving it out and
recording why.

Two deck-imposed rewrites apply to the folded-in passives, mirroring the ones
`lvs_reference.py`'s module docstring already states for the MOS bodies: a
`ppolyf_u` resistor's bulk terminal is rewritten to the deck's global
substrate net (no drawn tap layer to derive anything else from), and a
vertical bipolar's **collector** goes to that same global (the DRM's vertical
device has no drawn collector layer — its collector *is* the substrate) while
its **base** goes to the drawn Nwell's anonymous per-well net (the deck never
joins `Nwell` to `Contact`, so the base ring's `VSS` tie is invisible to it).
The schematic ties both to `VSS`; the layout does too, and no check in this
flow proves it.

Recorded result (`layout/reports/temp_core/`):

| Check | Result |
| ----- | ------ |
| `klt drc --deck gf180mcu` | clean — 0 violations |
| `klt extract --deck gf180mcu` | 114 devices (27 nfet, 28 pfet, 50 `ppolyf_u`, 9 `bjt`), 73 nets, 30 pins |
| `klt lvs` | **match** — 114/114 devices, 73/73 nets, 30/30 pins, 0 errors (2 `device.body_unverified` warnings) |
| negative control `topology` | detected (exit 3; `device.unmatched` 1, `topology` 1) |
| negative control `device-param` | detected (exit 3; `device.property` 5, `topology` 1) |
| negative control `passive-param` | detected (exit 3; `device.property` 11, `topology` 3) |

`passive-param` is new here (#93): it doubles the first resistor's value and
halves the first bipolar's emitter area, so a clean run is evidence the
compare reads the passives' **sizes**, not just their topology — the same
role `device-param` plays for the MOS devices, extended to the two device
classes this cell just started drawing. `bias_core` draws marked passives too
(#90) and runs the same control; `por_comparator` and the two MOS-only cells
draw none, so the control reports `n/a` there (see `run_checks.sh`'s per-cell
output).

**The klayout-tools#288 poly-shape warning does not drop, and that is the
expected result, not a regression.** `temp_core`'s `extract.json` still
reports the same **110** "poly shapes with the resistor-body signature" both
before and after this change (see "Known deck limits" below for what the
warning actually counts): those 110 shapes are the routing channel's own
Poly2 gate-to-track crossunders, unrelated to the resistor bank, which was
never drawn as unmarked poly inside this cell before #93 (it lived in the
now-retired siblings). The new resistor and bipolar geometry deliberately
reaches the channel on Metal2 risers rather than poly crossunders
specifically so it cannot add to this count — the same "count is unmoved by
an unrelated device change" result #92 already recorded for
`por_output_chain`'s MiM caps (16 before, 16 after). Drawing the channel's own
tracks on a marked layer would be wrong: they are real interconnect, not
resistor bodies, and marking them would make the deck extract devices no
golden netlist has.

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

**Coverage.** This `temp_por_top` GDS predates every one of #90/#91/#92/#93,
so most non-MOS devices of the four sub-circuits are still outside *this*
compare even though each is drawn and LVS-checked at its own cell level:
`bias_core`'s `XQ1`/`XQ8A..H`/`XQR` PNPs, `XR1`/`XR2`/`XRT`/`XRZ` resistors and
`XCC`/`XCOK` MiM caps (#90); `por_comparator`'s `XRTOP`/`XRBOT`/`XRHYS` divider
(#91); `temp_core`'s own `XCC` MiM cap, which is not drawn anywhere. Two
exceptions, both inherited unchanged because extraction is flat:
`por_output_chain`'s `XCDG`/`XCTIM` (#92 drew them — 5
`cap_mim_2f0_m4m5_noshield` units, with the same isolated-plate-net caveat that
cell's section records), and `temp_core`'s own PNP array and `R2` gain ladder
(#93 folded them in — 9 `bjt` + 50 `ppolyf_u` real devices, retiring the
sibling top cells that used to hold them outside this compare entirely). So the
198 devices below are the MOS subset **plus one cell's MiM caps plus one cell's
resistors and bipolars** — not yet `por_comparator`'s 3 divider resistors nor
`bias_core`'s 36.

**`XMRLK` is not in this assembly either, and deliberately so.** Issue #56's
release latch is the 28th MOS of `por_output_chain` and is drawn, extracted and
LVS-matched *in that cell* (section above). It is **not** in the committed
`temp_por_top` GDS/reference below, for the same reason `bias_core`'s passives
and `por_comparator`'s divider are not: this assembly is frozen behind #97.

Catching this cell up is #97, once rather than once per sub-cell change:
regenerating it against today's `build_cells.py` is not a no-op — the grown
sub-cell footprints collide at the instance boundary, and the rebuilt stream
DRCs **dirty**: 92 violations (`contact.space.1` ×79, `poly2.enclosing.contact.1`
×11, `contact.width.1` ×2), reproducible on `main` alone with none of #90's
geometry. That is precisely the placement re-derivation #97 exists to do, and it
waits on #90/#93. `temp_por_top`'s committed artifacts are therefore left
byte-for-byte as `main` has them; #97 picks up `XMRLK` along with the rest when
it reassembles.

Recorded result (`layout/reports/temp_por_top/`) — unchanged from `main`, i.e.
still the pre-#90/#91/#56 assembly:

| Check | Result |
| ----- | ------ |
| `klt drc --deck gf180mcu` | clean — 0 violations (Metal2/Metal3 rules now exercised, not skipped; `mim.*` too since #92) |
| `klt extract --deck gf180mcu --top-cell-pins` | 198 devices (70 nfet, 64 pfet, 50 `ppolyf_u`, 9 `bjt`, 5 `cap_mim_2f0_m4m5_noshield`), 131 nets, 6 pins |
| `klt lvs` | **match** — 198/198 devices, 131/131 nets, 6/6 pins, 0 errors (2 `device.body_unverified` warnings) |
| negative control `topology` | detected (exit 3; `device.unmatched` 1, `topology` 12) |
| negative control `device-param` | detected (exit 3; `device.property` 5, `topology` 12) |
| negative control `passive-param` | detected (exit 3; `device.property` 11, `topology` 15) |

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

## Known deck limits — what a clean LVS here does *not* prove

`klt`'s `gf180mcu` decks are curated starter subsets, not the full DRM/LVS rule
set. The limits below are the ones that bear on reading these reports. Each was
hit during this bring-up and, where it is a tool gap rather than a fact of life,
filed upstream per this repo's friction protocol.

- **Device coverage is MOS-only.** The extraction deck recognises `nfet`/`pfet`
  and nothing else in the version this flow was brought up on, so a cell
  containing poly resistors, MiM caps, or vertical bipolars cannot be LVS'd
  whole. That is why the proof cell is an all-MOS one and why `bias_core`'s
  16 non-MOS devices are **not drawn** rather than drawn-and-ignored — a
  drawn poly resistor body extracts as interconnect and shorts its own
  terminal nets. `por_output_chain`'s 2 MiM caps and `por_comparator`'s
  3-segment sense divider were in the same boat through #70/#69; they are
  drawn for real as of #92/#91 (see their own sections above) — the first
  of this block's non-MOS devices to cross out of this bullet.
  **Re-checked at `klt 0.1.0` for #72** — and this has moved. The installed
  deck now *declares* `['nfet', 'pfet', 'bjt', 'cap_mim_2f0_m4m5_noshield',
  'resistor']` (every `lvs.json` records it), so
  [klayout-tools#219](https://github.com/2AMLogic/klayout-tools/issues/219) and
  its sub-issues #222 (resistors) / #225 (MiM caps) have landed here. What did
  **not** move at #72 was these cells: recognising a resistor or a MiM cap needs
  marker layers (`SAB`/`RES_MK`, `CAP_MK`/`MIM_L_MK`) that none of the drawn
  cells carried, and the drawn geometry that *would* become those devices was
  laid out for a deck that could not model them. That left a **drawing** gap
  this repo owns, not a tool gap.
  **#92 closed the first of it**: `por_output_chain` now draws both MiM caps for
  real (`FuseTop` + `CAP_MK` + `MIM_L_MK` over `Metal4`), and they extract as 5
  `cap_mim_2f0_m4m5_noshield` devices with the right capacitance instead of as
  reserved floor area. Two residual tool gaps surfaced doing it, both filed
  generically:
  [klayout-tools#314](https://github.com/2AMLogic/klayout-tools/issues/314) — a
  recognised capacitor's plate regions are registered *outside* the deck's
  metal/via connectivity stack (and its top-plate layer is not in that stack at
  all), so **no drawn routing can put a MiM plate on a schematic net**; the
  compare answers for plate area, never for plate connectivity. And
  [klayout-tools#315](https://github.com/2AMLogic/klayout-tools/issues/315) —
  the deck models exactly one of the PDK's MiM stack variants, so a schematic
  instantiating the other (`..._m3m4_...`) has to be drawn as the modelled one.
  **#91, #93 and #90 closed the second, for every cell that has one.**
  #91: `por_comparator` now draws its 3-segment sense divider for real
  (`RES_MK`/`SAB`/`Resistor(62,0)` over `Poly2`), extracting as 3
  `ppolyf_u_1k` devices instead of reserved floor area. #93: `temp_core`'s
  `R2` gain ladder and its rank-3 PNP array are now drawn with `SAB`/`RES_MK`
  and `DRC_BJT` markers and extract as 50 `ppolyf_u` + 9 `bjt` real devices
  instead of sitting outside the compare in retired sibling top cells. #90:
  `bias_core`'s 4 poly resistors, 10 vertical PNPs and 2 MiM caps extract as
  24 `ppolyf_u_1k` + 10 `bjt` + 2 MiM, which makes that cell whole. (See each
  cell's own section above for its marker geometry and drawing decision.)
  `temp_core`'s own MiM cap `XCC` is the one device left out anywhere, for the
  same two reasons `por_output_chain`'s substitution above states (wrong MiM
  stack variant, unconnectable plate nets).
  Two deck-*option* limits surfaced doing this, neither a missing capability:
  - **The high-rho poly resistor's sheet resistance is a deck option, not
    drawn geometry.** `ppolyf_u_1k`/`_2k`/`_3k` are geometrically identical —
    one `SAB` + `RES_MK` + `Resistor` stack — and which one a run extracts is
    the official runset's `POLY_RES` build option. `klt` models the PDK's own
    default (`_1k`) only, so this repo's `ppolyf_u_3k` devices, in both
    `bias_core` and `por_comparator`, are drawn at their schematic dimensions
    and recognised at 1000 Ω/sq. (`temp_core`'s plain `ppolyf_u` devices are
    unaffected: that class carries no `Resistor` ID layer and the deck's own
    350 Ω/sq applies. `lvs_reference.py`'s single `RESISTOR_CLASS` table
    carries both families and both sheet rhos.) An explicit non-goal of
    [klayout-tools#299](https://github.com/2AMLogic/klayout-tools/issues/299)
    and filed as
    [klayout-tools#323](https://github.com/2AMLogic/klayout-tools/issues/323);
    it is the exact analogue of #315's MiM-stack substitution, and like it, it
    costs the *value* and not the geometry.
  - **A string of marked bodies is N devices.** The deck cuts each *marked*
    body out of poly separately and runs no device-combination step, so a
    resistor drawn as a string of legs extracts as one two-terminal device per
    leg. That is arguably correct behaviour rather than a gap — it is the same
    "no combination step" this repo already handles for multi-finger MOS
    (`fingers`) and multiplied MiM caps — so it is handled the same way, by
    declaring the same N devices in the reference, and no new issue was filed
    for it. It also leaves a cell a genuine choice, and this block makes it
    both ways: `por_comparator` serpentines one continuous body per resistor
    (1 device each, area-derived), `bias_core` and `temp_core` string separate
    legs (N devices each). Both go through the one
    `lvs_reference.resistor_segments()`, with the style and the leg
    ceiling/target in each manifest entry's `resistor_fold`, so the code that
    draws the bodies and the reference that declares them can never disagree.
  The *silence* has moved too, in the right direction:
  [klayout-tools#288](https://github.com/2AMLogic/klayout-tools/issues/288) is
  live in this build — every cell's `extract.json` now carries a warning naming
  the count of poly shapes with "the resistor-body signature" that were
  absorbed into interconnect.
  **These counts are mostly `Poly2` routing tracks, not undrawn devices**, and
  #91/#92/#93/#90 each confirmed it, from four different directions. #92:
  `por_output_chain`'s count is **16 before and 16 after** drawing its MiM
  caps — 16 is exactly the number of horizontal Poly2 signal tracks the cell
  routes on (`POR_OUTPUT_CHAIN_TRACKS`), each a poly run contacted at both ends
  and touching no recognised gate, i.e. the heuristic's stated signature, so it
  flags the routing scheme rather than a missing device; MiM geometry cannot
  move it in either direction. #93: `temp_core`'s is **110 before and 110
  after** folding in its resistor bank and PNP array — because that geometry
  reaches the routing channel on Metal2 risers rather than poly crossunders
  precisely so it draws no *new* poly shape the heuristic could flag; same
  signature, same non-effect. #91: `por_comparator`'s moved from **10 to 12**
  drawing its divider — *up*, not down, and none of the 12 is divider geometry
  (the divider's own marked legs contribute zero); two pre-existing routing
  tracks (`SNS`, `SNSB`) newly trip the heuristic because reaching the divider
  gives each of them a second contact where none existed before. #90:
  `bias_core`'s went **19 → 28** across drawing its 16 devices — again *up*,
  while the cell went from 16 undrawn devices to zero — because the passive
  block adds its own eight-track distribution band and two row tracks (`NB`,
  `VREF`) gained a second contact by finally having a second device to reach.
  Every one of the 28 was enumerated; not one is a device.
  What #90 also showed is that the markers are load-bearing: rebuilding the
  same `bias_core` geometry with `RES_MK` moved to a layer no deck reads drops
  all 24 resistors, collapses **54 nets to 30** — the documented short
  cascade — and pushes that cell's #288 count to 32 as the four folds finally
  trip it. So the heuristic flags the *routing scheme*, and the only way to
  drive these counts toward zero would be to route on a metal the sub-cells
  deliberately do not use. Current per-cell counts: 28 in `bias_core`, 12 in
  `por_comparator`, 16 in `por_output_chain`, 110 in `temp_core` — and 155 in
  `temp_por_top`, which is the #72-era sum its frozen GDS still reflects, not
  the 166 those four now add up to (see #97).
  The false-positive rate is filed generically as
  [klayout-tools#324](https://github.com/2AMLogic/klayout-tools/issues/324) —
  which also carries the *other* half of what #90 hit: a correctly recognised
  resistor's own unmarked terminal head is flagged too, if it carries more than
  one contact. That one changed this layout. Each drawn head in `bias_core` has
  **exactly one contact**, not the contact array a 2 µm-wide head would
  normally get, purely to keep the diagnostic quiet — a worse layout for no
  electrical reason, which is precisely the kind of thing this repo exists to
  report.
- **There is no dummy-device concept**, so matched-pair *dummy edges* cannot be
  drawn on any cell that must also LVS: a drawn dummy MOS extracts as a real
  device the schematic-derived reference does not have. The cells here
  therefore stop at adjacency/orientation/geometry matching and draw no
  dummies — a layout decision made by a tool limit, which is exactly the kind
  of thing this repo exists to surface. Filed by #70:
  [klayout-tools#295](https://github.com/2AMLogic/klayout-tools/issues/295).
- **There is no annotation-layer contract.** Every reserved region this block
  ever drew is now gone — #92 replaced `por_output_chain`'s with drawn MiM
  caps, #91 `por_comparator`'s with a drawn divider, and #90 `bias_core`'s
  with its drawn passives and bipolars — so `extract.json` reports an empty
  `ignored_layers` for each of them. The 200/0 layer those regions sat on was
  chosen because no deck reads it today, not because any deck promises not to,
  which is why the gap is still worth tracking even with nothing on it. Filed:
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
  - `por_comparator` is **unchanged**: it routes on Metal1 with Poly2
    crossunders, its committed GDS is byte-identical, and its recorded results
    stand. Nothing about the lifted limit obliges a redraw, and redrawing a
    proven cell to use a capability it does not need would be a regression risk
    for no gain. `por_output_chain` and `bias_core` keep the same Metal1-only
    *signal* routing too; #92 and #90 added `Metal4` to them only as MiM
    bottom-plate geometry. `temp_core`'s MOS network is likewise unchanged;
    #93 added its `R2` ladder and PNP array on Metal2 risers rather than Poly2
    crossunders specifically to keep the klayout-tools#288 poly-shape count
    from moving (see `temp_core`'s own section above) — the one cell here where
    the lifted limit *was* used, and by choice, not by need.
  - The MiM caps stopped being undrawn: the gf180mcu MiM stack (`Metal4` +
    `FuseTop` + the two marker layers) is in the deck's layer set, which is what
    let #92 draw `por_output_chain`'s and #90 `bias_core`'s. `temp_core`'s is
    still the missing marker geometry in *that* cell, not the deck — unchanged
    by #93, which drew its resistor and bipolar markers but deliberately left
    `XCC` out (see `temp_core`'s own section above).
  `layout/floorplan.md`'s "Routing / metal-level note" carries the same
  re-check.
- **DRC is a curated subset.** Width/space/enclosure across Poly2/Comp/Contact/
  Metal1–Metal5, plus Nwell spacing/enclosure, two MiM rules and one BJT rule.
  As of #90 every rule in the deck except the `metal5`/`metaltop` pairs is
  actually exercised by some cell in this repo — `bjt.separation.comp.1`,
  `mim.space.1` and `mim.enclosing.fusetop.1` left `rules_skipped` with the
  geometry that finally drew their layers. Clean here still means clean against
  *that subset*: there is no rule at all for `Pplus`, `SAB`, `RES_MK` or the
  `Resistor` ID layer, so nothing in this flow checks a drawn resistor's own
  DRM rules. It is not a tapeout-grade signoff, and no claim in this repo
  should be written as if it were.
- **~~`"enclosing"`/`"enclosed"` checks missed zero-overlap escapes.~~ Fixed
  upstream, found via `por_comparator` (#102/#103).** `klt drc`'s `"enclosing"`
  check kind (`poly2.enclosing.contact.1` among others) used to dispatch
  straight onto KLayout's `Region.enclosing_check`, which only reports
  *marginal* violations at facing edges of shapes that already partially
  overlap — a shape of the enclosed layer with **zero** overlap with the
  enclosing layer (the worst-case enclosure failure) produced no violation at
  all, so a layout that missed a contact's enclosure entirely could still
  read `status: clean`. Found rerunning `por_comparator`'s committed,
  unchanged GDS through a newer `klt` build and seeing it go from clean to 2
  violations with no layout change on this side. Filed generically (tool gap,
  no design details) as
  [klayout-tools#318](https://github.com/2AMLogic/klayout-tools/issues/318)
  and already fixed upstream (`klayout-tools` PR #327): the same rule id now
  also reports the zero-overlap escape. `por_comparator`'s own section above
  has the full trace; the drawing defect itself (not a tool problem) is #102.
- **Committed reports can silently drift onto two different `klt` deck
  revisions.** `provenance.deck.content_hash` (below) is a hash of the deck's
  own source module, so any change to the file that defines the `gf180mcu`
  deck — including one scoped to extraction, nothing to do with DRC rules —
  moves it, and nothing used to check that every committed
  `layout/reports/*/drc.json` names the *same* one. That is exactly how the
  zero-overlap-escape fix above went undetected here for as long as it did:
  `por_comparator`'s report was regenerated once, under an older deck, and
  never again. #103 added `python3 layout/lvs_reference.py --check-deck-hash`
  (wired into `run_checks.sh`, unscoped even for a single-cell run) so this
  fails loudly instead of drifting silently; it tolerates `temp_por_top`
  while that cell is intentionally frozen behind #97 (see
  `lvs_reference.FROZEN_DECK_CELLS`).

`layout/reports/environment.json` records the `klt` version each report was
produced with, because several of the limits above are version-dependent.
Re-run `run_checks.sh` after upgrading `klt` and commit the refreshed reports
— `run_checks.sh` now checks that every committed cell's `drc.json` agrees on
`provenance.deck.content_hash` before running anything else, so a report
regenerated against a new `klt` for only some cells is caught immediately
rather than becoming this section's next entry.

## Adding a cell (for #17 / #18)

1. Add a builder function to `layout/build_cells.py` and register it in `CELLS`;
   run `python3 layout/build_cells.py --cell <name>` to write the GDS.
2. Add a manifest entry to `layout/lvs_reference.py`'s `CELLS` — the golden
   netlist it derives from, the devices to take, the layout's own pin set
   (`ports`), its unlabelled internal nets (`internal`), and which PMOS devices
   share which drawn Nwell (`wells`), plus any non-MOS devices the cell draws:
   `caps` (MiM — plate nets are synthesized per instance, not declared, because
   the deck cannot connect a plate to anything), `resistors` (+ an optional
   `resistor_fold` — the leg count comes from `resistor_segments`, and the
   nodes between legs are synthesized the same way) and `bipolars` +
   `bjt_well` (vertical bipolars — the collector is rewritten to the substrate
   global and the base to the drawn well, and `AE` is declared from the PDK
   subcircuit's own emitter size; a `Q` card without it does not pair). Run it to
   write the reference. On a cell with more than two devices, check that
   `devices[0]` and `devices[1]` do not share a source net — if they do, the
   `topology` negative control corrupts nothing and silently stops controlling
   anything.
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
