#!/usr/bin/env python3
"""Build the layout cells under ``layout/cells/`` from a deterministic source.

    python3 layout/build_cells.py            # rebuild layout/cells/*.gds
    python3 layout/build_cells.py --check    # verify committed GDS are current
    python3 layout/build_cells.py --cell por_comparator_bias_okb_inv

Needs the ``klayout`` python module (``klt``'s own runtime dependency). If it is
not importable from the interpreter you run this with, use ``klt``'s:

    uv run --with klayout python3 layout/build_cells.py

Geometry is emitted as plain drawn rectangles on the gf180mcu drawn layers, at
coordinates written out in full below rather than produced by a PCell -- this is
the DRC/LVS **flow** bring-up (#16), not the block's real layout (#17/#18). What
matters here is that the cell is a verbatim piece of a real schematic in
``design/`` so the LVS compare has a golden netlist to answer to, and that the
stream is byte-reproducible so a recorded clean run can be re-run and re-checked.

GDS timestamps are suppressed (``gds2_write_timestamps = False``) -- without
that, two builds of identical geometry differ byte-for-byte and no committed
stream can ever be ``--check``ed.

Layers are the gf180mcu drawn layers ``klt``'s curated ``gf180mcu`` deck reads
(see ``layout/README.md`` for the deck's documented coverage limits):

    Nwell 21/0 · Comp 22/0 · Poly2 30/0 · Contact 33/0 · Metal1 34/0
    Metal1 pin/label purpose 34/10 (net names -> extracted pin names)

plus one repo-local annotation layer that is **not** a gf180mcu drawn layer and
is read by neither the DRC deck nor the extraction deck:

    RESERVED 200/0  area reserved for devices the deck cannot represent
                    (see ``bias_core``'s docstring)

Device dimensions are never retyped here. ``bias_core`` reads every ``L``/``W``
out of ``design/netlist/bias_core.spice`` through ``lvs_reference``'s parser --
the same golden netlist the LVS reference is derived from -- so the layout and
the reference cannot drift apart silently: move a size in the schematic and
both ``--check`` gates fail together.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAYOUT_DIR.parent
CELLS_DIR = LAYOUT_DIR / "cells"

sys.path.insert(0, str(LAYOUT_DIR))

import lvs_reference as lvsref  # noqa: E402  (needs LAYOUT_DIR on sys.path)

DBU_UM = 0.001

NWELL = (21, 0)
COMP = (22, 0)
POLY2 = (30, 0)
CONTACT = (33, 0)
METAL1 = (34, 0)
METAL1_LABEL = (34, 10)
RESERVED = (200, 0)

#: gf180mcu DRM "CO.1": contact is a fixed 0.22 x 0.22 um square.
CONTACT_SIDE_UM = 0.22


class CellBuilder:
    """Thin wrapper over ``klayout.db`` so a cell body reads as geometry."""

    def __init__(self, name: str) -> None:
        import klayout.db as kdb  # imported late: see the module docstring

        self._kdb = kdb
        self.layout = kdb.Layout()
        self.layout.dbu = DBU_UM
        self.cell = self.layout.create_cell(name)

    def _layer(self, spec: tuple[int, int]) -> int:
        return self.layout.layer(spec[0], spec[1])

    def box(self, spec, x0: float, y0: float, x1: float, y1: float) -> None:
        self.cell.shapes(self._layer(spec)).insert(
            self._kdb.DBox(x0, y0, x1, y1).to_itype(self.layout.dbu)
        )

    def contact(self, cx: float, cy: float) -> None:
        half = CONTACT_SIDE_UM / 2.0
        self.box(CONTACT, cx - half, cy - half, cx + half, cy + half)

    def label(self, name: str, x: float, y: float) -> None:
        self.cell.shapes(self._layer(METAL1_LABEL)).insert(
            self._kdb.DText(name, self._kdb.DTrans(self._kdb.DVector(x, y))).to_itype(
                self.layout.dbu
            )
        )

    def write(self, path: Path) -> None:
        options = self._kdb.SaveLayoutOptions()
        options.gds2_write_timestamps = False
        self.layout.write(str(path), options)


def por_comparator_bias_okb_inv(b: CellBuilder) -> None:
    """``por_comparator``'s local ``BIAS_OKB`` inverter (``MENP`` / ``MENN``).

    Two devices, verbatim from ``design/por_comparator.sch``:

        MENP  pfet 2/0.5 um   MENN  nfet 1/0.5 um

    -- the "local inverter producing ``BIAS_OKB``" row of
    ``design/por_comparator.md``'s device table. Both gates are the one drawn
    poly strip (``BIAS_OK``), both drains land on the one Metal1 strap
    (``BIAS_OKB``), sources go to the ``VDD`` / ``VSS`` straps.

    Floorplan (um), source column | gate | drain column::

        y=5.6  +--------- Nwell ----------+
        y=5.0  |  +----- PMOS Comp -----+ |     W = 2.0 um
        y=3.0  |  +---------------------+ |
        y=2.4  +--------------------------+
        y=2.0        [gate contact]              -> BIAS_OK
        y=1.0     +----- NMOS Comp -----+        W = 1.0 um
        y=0.0     +---------------------+
               x=0    0.5  1.0        1.8
                      |<L>|  L = 0.5 um
    """
    # Active. NMOS on field, PMOS in the well.
    b.box(COMP, 0.0, 0.0, 1.8, 1.0)
    b.box(COMP, 0.0, 3.0, 1.8, 5.0)
    b.box(NWELL, -0.6, 2.4, 2.4, 5.6)

    # One shared gate strip through both channels: L = 0.5 um.
    b.box(POLY2, 0.5, -0.3, 1.0, 5.3)

    b.contact(0.25, 0.5)  # NMOS source
    b.contact(1.40, 0.5)  # NMOS drain
    b.contact(0.25, 4.0)  # PMOS source
    b.contact(1.40, 4.0)  # PMOS drain
    b.contact(0.75, 2.0)  # shared gate

    b.box(METAL1, -0.60, 0.25, 0.45, 0.75)  # VSS strap
    b.box(METAL1, -0.60, 3.75, 0.45, 4.25)  # VDD strap
    b.box(METAL1, -0.60, 1.80, 0.95, 2.20)  # BIAS_OK  (gate)
    b.box(METAL1, 1.20, 0.20, 1.60, 4.30)  # BIAS_OKB (drains)

    b.label("VSS", 0.0, 0.5)
    b.label("VDD", 0.0, 4.0)
    b.label("BIAS_OK", 0.0, 2.0)
    b.label("BIAS_OKB", 1.4, 2.0)


# --------------------------------------------------------------------------- #
# bias_core (#68)
# --------------------------------------------------------------------------- #

#: ``bias_core``'s PMOS devices, left to right across the drawn row.
BIAS_CORE_PMOS = (
    # core mirror bank -- the three matched legs plus the 1/4-scale leg
    "XMP1",
    "XMP2",
    "XMP3",
    "XMPBN",
    # secondary bias rail PB and its consumers
    "XMBP",
    "XMPIB",
    "XMPT",
    # error amplifier input pair (matched pair -- adjacent, same orientation)
    "XMI1",
    "XMI2",
    "XMS2P",
    # startup kick replica
    "XKA",
    # settle comparator: tail, then the matched input pair
    "XMPOK",
    "XMOKA",
    "XMOKB",
    # BIAS_OK output stage
    "XMOK2P",
    "XMO1P",
)

#: ``bias_core``'s NMOS devices, left to right across the drawn row.
BIAS_CORE_NMOS = (
    "XMBN",
    "XMBN2",
    # amplifier load mirror (matched pair -- adjacent, same orientation)
    "XML1",
    "XML2",
    "XMS2N",
    # startup kick: the five-deep diode stack, then its pull-down path
    "XKS0",
    "XKS1",
    "XKS2",
    "XKS3",
    "XKS4",
    "XKAN",
    "XKPD",
    "XKICK",
    # settle comparator load mirror (matched pair) and the dead-loop clamp
    "XMOL1",
    "XMOL2",
    "XMOKC",
    "XMOK2",
    "XMO1N",
)

#: One Poly2 routing track per signal net, bottom to top in the channel above
#: the device row. ``VDD``/``VSS`` are not here -- they are Metal1 rails.
BIAS_CORE_TRACKS = (
    "PG",
    "PB",
    "NBG",
    "NA",
    "NB",
    "NBTOP",
    "NT",
    "N1",
    "N2",
    "VREF",
    "IBIAS",
    "NKM",
    "NKG",
    "KS1",
    "KS2",
    "KS3",
    "KS4",
    "TOK",
    "NOKO",
    "NOKL",
    "NOKX",
    "BIAS_OK",
)

#: Metal1 pin labels. A label only becomes an extracted pin if it sits inside a
#: Metal1 shape on that net, so each is dropped on a wire that carries it.
BIAS_CORE_PIN_ON_DRAIN = {"IBIAS": "XMPIB", "VREF": "XMP3", "BIAS_OK": "XMO1P"}

SD_EXT_UM = 0.8  # source/drain extension either side of the gate
CONT_INSET_UM = 0.35  # contact column inset from the COMP edge
RISER_W_UM = 0.4  # Metal1 vertical riser width
TRACK_W_UM = 0.4  # Poly2 horizontal track width
TRACK_PITCH_UM = 0.8
TILE_GAP_UM = 1.0  # spacing between adjacent device tiles
REGION_GAP_UM = 4.0  # spacing between the PMOS and NMOS regions
GUARD_RING_W_UM = 1.5
GUARD_RING_CLEAR_UM = 3.0
TAP_PITCH_UM = 1.0  # contact pitch along guard ring / tap straps
#: Area reserved for the devices the curated deck cannot represent (10 vertical
#: PNPs, 4 poly resistors, 2 MiM caps). See ``bias_core``'s docstring.
RESERVED_W_UM = 130.0
RESERVED_H_UM = 130.0


def _golden_devices(source: str, subckt: str) -> dict[str, dict]:
    """Parse ``design/netlist/<source>``'s ``<subckt>`` for its MOS devices."""
    text = (REPO_ROOT / "design" / "netlist" / source).read_text()
    return lvsref.parse_devices(lvsref.subckt_body(text, subckt))


def _contact_rows(width_um: float) -> list[float]:
    """Contact y-centres down a device's source/drain column.

    Kept at >= 0.5 um pitch (DRM ``CO.2a`` asks 0.25) and inset far enough that
    ``CO.4``'s 0.07 um COMP overlap holds at both ends of the diffusion.
    """
    low, high = CONT_INSET_UM, width_um - CONT_INSET_UM
    if high - low < 0.47:
        return [width_um / 2.0]
    count = int((high - low) / 0.5) + 1
    step = (high - low) / (count - 1)
    return [low + index * step for index in range(count)]


def _span(low: float, high: float, pitch: float) -> list[float]:
    """Evenly spaced centres covering ``[low, high]`` at about ``pitch``."""
    if high <= low:
        return [(low + high) / 2.0]
    count = max(1, int((high - low) / pitch))
    step = (high - low) / count
    return [low + index * step for index in range(count + 1)]


def bias_core(b: CellBuilder) -> None:
    """The MOS portion of ``bias_core`` (``design/bias_core.sch``), drawn.

    **What is drawn, and what deliberately is not.** ``bias_core`` has 34 MOS
    devices, 10 vertical PNPs (``XQ1``, ``XQ8A..H``, ``XQR``), 4 poly resistors
    (``XR1``, ``XR2``, ``XRT``, ``XRZ``) and 2 MiM caps (``XCC``, ``XCOK``).
    ``klt``'s curated ``gf180mcu`` extraction deck recognises ``nfet``/``pfet``
    and nothing else (klayout-tools#219, resistors #222), so the non-MOS
    devices cannot be extracted as devices -- and drawing them anyway would be
    worse than leaving them out, because the deck would read a drawn poly
    resistor body as *interconnect* and silently short its two terminal nets
    (``NB``-``EC``, ``VREF``-``ER``, ``NBTOP``-``NB``, ``NZ``-``N2``), which
    would then read as a layout bug in the part that *can* be checked.

    So the sub-cell boundary this cell draws is: **everything the deck can
    represent, and nothing it cannot**. The passive/bipolar region is reserved
    as a floorplan rectangle on annotation layer 200/0 -- read by neither deck,
    so it changes no DRC or LVS verdict -- rather than filled with geometry
    that no check in this repo could answer for. ``layout/README.md`` records
    which devices that leaves outside LVS coverage.

    **Structure** (all dimensions from ``design/netlist/bias_core.spice``)::

        +--- guard ring: COMP + Metal1, VSS-tied, continuous, contacts 1um ---+
        |  VDD rail (Metal1)                                                  |
        |  ..... routing channel: one Poly2 track per signal net .....        |
        |  [ PMOS row, one Nwell ]   [ NMOS row ]      [ reserved passive ]   |
        |  Nwell tie strap (COMP in Nwell -> VDD)                             |
        |  VSS rail (Metal1) over a p-substrate tap strap (COMP)              |
        +---------------------------------------------------------------------+

    Routing is Metal1-only by necessity -- the extraction deck declares one
    metal level (``layout/README.md``, "Single metal level"; still true at
    ``klt 0.1.0``). The two-layer scheme that makes a 34-device cell routable
    on one metal is: **horizontal Poly2 tracks, vertical Metal1 risers**. A
    riser crosses every track it does not belong to with no contact, so the
    only connections are the ones drawn.

    Matched pairs get ordinary matched-pair practice (adjacent placement, same
    orientation, identical drawn geometry, common well): ``XMI1``/``XMI2``,
    ``XML1``/``XML2``, ``XMOKA``/``XMOKB``, ``XMOL1``/``XMOL2``, and the three
    core mirror legs ``XMP1``/``XMP2``/``XMP3``. ``layout/floorplan.md``'s
    ranked common-centroid plan covers ``temp_core`` and ``por_comparator``
    only -- it prescribes nothing for this cell, so nothing is invented here.
    """
    devices = _golden_devices("bias_core.spice", "bias_core")

    # --- placement pass: fix every device's x, then derive the frame -------
    tiles = []
    cursor = 0.0
    for name in BIAS_CORE_PMOS + BIAS_CORE_NMOS:
        if name == BIAS_CORE_NMOS[0]:
            cursor += REGION_GAP_UM
        device = devices[name]
        length = lvsref.to_um(device["params"]["l"])
        width = lvsref.to_um(device["params"]["w"])
        drain, gate, source, _body = device["nodes"]
        tiles.append(
            {
                "name": name,
                "pmos": name in BIAS_CORE_PMOS,
                "x0": cursor,
                "l": length,
                "w": width,
                "d": drain,
                "g": gate,
                "s": source,
            }
        )
        cursor += 2 * SD_EXT_UM + length + TILE_GAP_UM

    pmos = [tile for tile in tiles if tile["pmos"]]
    p_x0 = pmos[0]["x0"]
    p_x1 = pmos[-1]["x0"] + 2 * SD_EXT_UM + pmos[-1]["l"]
    row_x1 = cursor - TILE_GAP_UM
    max_w = max(tile["w"] for tile in tiles)
    max_pw = max(tile["w"] for tile in pmos)

    channel_y0 = max_w + 3.0
    track_y = {
        net: channel_y0 + index * TRACK_PITCH_UM
        for index, net in enumerate(BIAS_CORE_TRACKS)
    }
    vdd_y0 = channel_y0 + len(BIAS_CORE_TRACKS) * TRACK_PITCH_UM + 1.5
    vdd_y1 = vdd_y0 + 1.2
    vss_y0, vss_y1 = -5.2, -4.2
    tie_y0, tie_y1 = -2.2, -1.2

    reserved_x0 = row_x1 + 5.0
    reserved_x1 = reserved_x0 + RESERVED_W_UM
    reserved_y0 = -3.5
    reserved_y1 = reserved_y0 + RESERVED_H_UM

    clear = GUARD_RING_CLEAR_UM + GUARD_RING_W_UM
    gx0 = p_x0 - 1.0 - clear
    gx1 = reserved_x1 + clear
    gy0 = vss_y0 - clear
    gy1 = max(vdd_y1, reserved_y1) + clear

    def riser(x_centre: float, net: str, y_low: float, y_high: float) -> None:
        """One Metal1 riser from a device terminal to its rail or track."""
        if net == "VDD":
            y_high = vdd_y1
        elif net == "VSS":
            y_low = vss_y0
        else:
            y_high = track_y[net] + 0.2
            b.contact(x_centre, track_y[net])
        b.box(
            METAL1,
            x_centre - RISER_W_UM / 2.0,
            y_low,
            x_centre + RISER_W_UM / 2.0,
            y_high,
        )

    # --- devices -----------------------------------------------------------
    for tile in tiles:
        x0, length, width = tile["x0"], tile["l"], tile["w"]
        tile_w = 2 * SD_EXT_UM + length
        gate_x0 = x0 + SD_EXT_UM
        gate_cx = gate_x0 + length / 2.0
        x_source = x0 + CONT_INSET_UM
        x_drain = x0 + tile_w - CONT_INSET_UM

        b.box(COMP, x0, 0.0, x0 + tile_w, width)
        # The gate strip runs past the channel at both ends (DRM PL.4) and
        # carries its own landing pad above the diffusion, where nothing else
        # in this cell routes.
        b.box(POLY2, gate_x0, -0.3, gate_x0 + length, width + 1.1)
        b.contact(gate_cx, width + 0.75)
        for y in _contact_rows(width):
            b.contact(x_source, y)
            b.contact(x_drain, y)

        riser(x_source, tile["s"], 0.15, max(0.6, width - 0.2))
        riser(x_drain, tile["d"], 0.15, max(0.6, width - 0.2))
        riser(gate_cx, tile["g"], width + 0.55, width + 0.95)

    # --- Poly2 routing channel --------------------------------------------
    for net in BIAS_CORE_TRACKS:
        y = track_y[net]
        half_w = TRACK_W_UM / 2.0
        b.box(POLY2, p_x0 - 1.0, y - half_w, row_x1 + 1.0, y + half_w)

    # --- Nwell, and its tie strap -----------------------------------------
    b.box(NWELL, p_x0 - 1.0, -2.6, p_x1 + 1.0, max_pw + 1.5)
    b.box(COMP, p_x0 - 0.5, tie_y0, p_x1 + 0.5, tie_y1)
    b.box(METAL1, p_x0 - 0.6, tie_y0 - 0.05, p_x1 + 0.6, tie_y1 + 0.05)
    for x in _span(p_x0 - 0.1, p_x1 + 0.1, TAP_PITCH_UM):
        b.contact(x, (tie_y0 + tie_y1) / 2.0)
    # ... carried up to the VDD rail clear of the first device's own risers.
    b.box(METAL1, p_x0 - 0.6, tie_y1, p_x0 - 0.2, vdd_y1)

    # --- supply rails ------------------------------------------------------
    b.box(METAL1, gx0 + 2.5, vdd_y0, row_x1 + 2.0, vdd_y1)
    b.box(METAL1, gx0 + 1.0, vss_y0, row_x1 + 2.0, vss_y1)
    b.box(COMP, gx0 + 2.3, vss_y0, row_x1 + 1.7, vss_y1)
    for x in _span(gx0 + 2.8, row_x1 + 1.2, TAP_PITCH_UM):
        b.contact(x, (vss_y0 + vss_y1) / 2.0)

    # --- guard ring: continuous, VSS-tied, contacted at 1 um ---------------
    # Tied to VSS by abutting the VSS rail's left end; no floating segment.
    ring = [
        (gx0, gy0, gx1, gy0 + GUARD_RING_W_UM),
        (gx0, gy1 - GUARD_RING_W_UM, gx1, gy1),
        (gx0, gy0, gx0 + GUARD_RING_W_UM, gy1),
        (gx1 - GUARD_RING_W_UM, gy0, gx1, gy1),
    ]
    for rect in ring:
        b.box(COMP, *rect)
        b.box(METAL1, *rect)
    half = GUARD_RING_W_UM / 2.0
    for x in _span(gx0 + half, gx1 - half, TAP_PITCH_UM):
        b.contact(x, gy0 + half)
        b.contact(x, gy1 - half)
    inner_low = gy0 + GUARD_RING_W_UM + half
    inner_high = gy1 - GUARD_RING_W_UM - half
    for y in _span(inner_low, inner_high, TAP_PITCH_UM):
        b.contact(gx0 + half, y)
        b.contact(gx1 - half, y)

    # --- reserved passive/bipolar region (annotation only) -----------------
    b.box(RESERVED, reserved_x0, reserved_y0, reserved_x1, reserved_y1)

    # --- pins --------------------------------------------------------------
    b.label("VDD", row_x1, (vdd_y0 + vdd_y1) / 2.0)
    b.label("VSS", row_x1, (vss_y0 + vss_y1) / 2.0)
    by_name = {tile["name"]: tile for tile in tiles}
    for net, owner in BIAS_CORE_PIN_ON_DRAIN.items():
        tile = by_name[owner]
        x = tile["x0"] + 2 * SD_EXT_UM + tile["l"] - CONT_INSET_UM
        b.label(net, x, track_y[net])


#: cell name -> body. Add a cell here and it joins ``layout/run_checks.sh``.
CELLS = {
    "bias_core": bias_core,
    "por_comparator_bias_okb_inv": por_comparator_bias_okb_inv,
}


def build(name: str, out_dir: Path) -> Path:
    builder = CellBuilder(name)
    CELLS[name](builder)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.gds"
    builder.write(path)
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(check: bool, only: str | None) -> int:
    names = [only] if only else sorted(CELLS)
    for name in names:
        if name not in CELLS:
            print(f"unknown cell {name!r} (have: {', '.join(sorted(CELLS))})")
            return 2

    if not check:
        for name in names:
            path = build(name, CELLS_DIR)
            print(f"wrote {path.relative_to(REPO_ROOT)}  sha256={sha256(path)[:16]}")
        return 0

    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            fresh = build(name, Path(tmp))
            committed = CELLS_DIR / f"{name}.gds"
            if not committed.exists():
                failures.append(f"{name}: not committed (run without --check)")
                continue
            if sha256(fresh) != sha256(committed):
                failures.append(
                    f"{name}: committed GDS is stale "
                    f"(committed {sha256(committed)[:16]}, "
                    f"rebuilt {sha256(fresh)[:16]})"
                )
            else:
                print(f"ok {name}.gds  sha256={sha256(committed)[:16]}")

    for line in failures:
        print(f"FAIL {line}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild into a temp dir and fail if the committed GDS differs",
    )
    parser.add_argument("--cell", help="build/check only this cell")
    args = parser.parse_args(argv)
    return run(args.check, args.cell)


if __name__ == "__main__":
    sys.exit(main())
