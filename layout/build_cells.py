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
                    (see ``bias_core``'s and ``por_comparator``'s docstrings)

Device dimensions are never retyped here. ``bias_core`` and ``por_comparator``
read every ``L``/``W`` out of ``design/netlist/*.spice`` through
``lvs_reference``'s parser -- the same golden netlist the LVS reference is
derived from -- so the layout and the reference cannot drift apart silently:
move a size in the schematic and both ``--check`` gates fail together. The same
holds for the one reserved region whose size is load-bearing: the sense
divider's footprint is folded from the golden netlist's own ``r_width`` /
``r_length``, not from a number typed in here.
"""

from __future__ import annotations

import argparse
import hashlib
import math
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

    def instance(self, name: str, body, dx: float, dy: float) -> None:
        """Draw ``body`` into a child cell and place one instance at ``dx, dy``.

        The cell hierarchy is real in the stream and flat everywhere it is
        checked: both ``klt drc`` and ``klt extract`` read each layer through
        ``begin_shapes_rec`` on the top cell, i.e. flattened (see
        ``klayout_tools.drc``/``extract``). So an instanced sub-cell's geometry
        -- including its Metal1 labels -- lands in the parent's own flat
        connectivity graph, which is what lets a parent wire abut a sub-cell's
        strap and come out as one net.
        """
        child = self.layout.create_cell(name)
        parent, self.cell = self.cell, child
        try:
            body(self)
        finally:
            self.cell = parent
        self.cell.insert(
            self._kdb.DCellInstArray(
                child.cell_index(), self._kdb.DTrans(self._kdb.DVector(dx, dy))
            )
        )

    def add_cell(self, name: str) -> None:
        """Start a second (sibling) top cell in the same stream.

        ``klt drc`` checks **every** top cell in a stream, while ``klt
        extract``/``klt lvs`` take a single ``--top``. That split is what lets
        one stream carry both the LVS'd cell and structures the curated
        extraction deck cannot model as devices (see ``temp_core`` below).
        """
        self.cell = self.layout.create_cell(name)

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


# --------------------------------------------------------------------------- #
# por_comparator (#69)
# --------------------------------------------------------------------------- #

#: ``por_comparator``'s PMOS devices, left to right across the drawn row.
#: ``XMENP`` is absent on purpose -- it comes in with the instanced
#: ``por_comparator_bias_okb_inv`` sub-cell.
POR_COMPARATOR_PMOS = (
    # load mirror (matched pair -- adjacent, same orientation)
    "XMLA",
    "XMLB",
    # VDDA supply gate, then the two output-inverter PMOS
    "XMENSRC",
    "XMI1P",
    "XMI2P",
)

#: ``por_comparator``'s NMOS devices, left to right across the drawn row.
#: ``XMENN`` is absent on purpose (see ``POR_COMPARATOR_PMOS``).
POR_COMPARATOR_NMOS = (
    # comparator input pair, then its tail -- floorplan rank 4: side by side,
    # same orientation, no interleaving (see the cell docstring)
    "XMINA",
    "XMINB",
    "XMTAIL",
    # local bias mirror and its BIAS_OK-gated clamps
    "XMBD",
    "XMPASS",
    "XMDNB",
    "XMDIB",
    # hysteresis switch, CMPO clamp, output inverters
    "XMHSW",
    "XMDCMPO",
    "XMI1N",
    "XMI2N",
)

#: One Poly2 routing track per signal net, bottom to top in the channel above
#: the device row. ``VDD``/``VSS`` are not here -- they are Metal1 rails.
#:
#: Order is not arbitrary: the input pair's two gate nets (``SNS``/``VREF``)
#: are adjacent, and so are its two drain nets (``NA``/``CMPO``), with the
#: shared source (``TN``) directly below both -- so ``XMINA``'s and
#: ``XMINB``'s routing differs by exactly one 0.8 um track pitch, which is the
#: "short and symmetric routing from SNS and VREF" the floorplan asks for.
#: ``SNS`` and ``SNSB`` are the two nets the (undrawn) sense divider taps, so
#: both tracks are also run out to the reserved divider region.
POR_COMPARATOR_TRACKS = (
    "TN",
    "SNS",
    "VREF",
    "NA",
    "CMPO",
    "VDDA",
    "N1",
    "POR_RAW",
    "NBG",
    "IBIAS",
    "BIAS_OK",
    "BIAS_OKB",
    "SNSB",
)

#: Metal1 pin labels, dropped on the riser of the named device terminal (a
#: label only becomes an extracted pin if it sits inside a Metal1 shape on that
#: net). ``VDD``/``VSS`` go on the rails; ``BIAS_OK``/``BIAS_OKB`` arrive with
#: the instanced sub-cell, which carries its own labels.
POR_COMPARATOR_PIN_ON_DRAIN = {"IBIAS": "XMBD", "POR_RAW": "XMI2P"}
POR_COMPARATOR_PIN_ON_GATE = {"VREF": "XMINB"}

#: The sense divider, VDD end first (``design/por_comparator.md``, "Sense
#: divider"). Poly resistors: outside the curated deck's device coverage, so
#: reserved rather than drawn -- see ``por_comparator``'s docstring.
POR_DIVIDER_RESISTORS = ("XRTOP", "XRBOT", "XRHYS")

#: Poly-to-poly space between adjacent serpentine legs of the folded divider.
#: The DRM minimum (``PL.3a``) is 0.24 um; 1.0 um is ordinary poly-resistor
#: practice and is the assumption the reserved footprint is computed against.
DIVIDER_LEG_SPACE_UM = 1.0
#: Standard end-of-string dummy segments: one leg at each end of the string.
DIVIDER_DUMMY_LEGS = 2
#: Turn + head/tail contact overhead at each end of a leg.
DIVIDER_LEG_END_UM = 2.0


def _poly_resistors(source: str, subckt: str, names: tuple[str, ...]) -> dict:
    """Parse ``design/netlist/<source>``'s ``<subckt>`` for the named resistors.

    ``lvs_reference.parse_devices`` deliberately drops every card the curated
    deck cannot model, resistors included, so this reads their ``r_width`` /
    ``r_length`` directly -- still out of the same golden netlist, so no
    dimension is retyped here either.
    """
    text = (REPO_ROOT / "design" / "netlist" / source).read_text()
    found: dict[str, dict[str, str]] = {}
    for line in lvsref.subckt_body(text, subckt):
        fields = line.split()
        if fields[0] not in names:
            continue
        found[fields[0]] = {
            key.lower(): value.strip("'\"")
            for key, _, value in (f.partition("=") for f in fields[1:] if "=" in f)
        }
    missing = [name for name in names if name not in found]
    if missing:
        raise KeyError(f"{source}:{subckt}: no resistor card for {missing}")
    return found


def _divider_footprint() -> tuple[float, float, float, float, int]:
    """The folded sense divider's reserved footprint, from the golden netlist.

    Returns ``(width_um, height_um, drawn_length_um, leg_width_um, legs)`` for
    an ordinary serpentine fold: same-flavor, same-width legs at a fixed pitch,
    folded to a roughly square footprint, plus one dummy leg at each end. Area
    is what constrains this structure, not matching -- ``layout/floorplan.md``
    rank 4 -- so the fold is chosen for footprint and the number it produces is
    computed here rather than asserted.
    """
    cards = _poly_resistors(
        "por_comparator.spice", "por_comparator", POR_DIVIDER_RESISTORS
    )
    widths = {lvsref.to_um(card["r_width"]) for card in cards.values()}
    if len(widths) != 1:
        # Same-width legs are the premise of the TC/sheet-rho-in-ratio
        # cancellation this divider's accuracy rests on (design/
        # por_comparator.md, "Why the hysteresis is a resistor ratio"), and of
        # the floorplan's rank-4 plan. If the schematic ever stops agreeing,
        # fail here rather than reserve an area for a structure that no longer
        # matches the plan.
        raise ValueError(f"sense divider legs are not one width: {sorted(widths)}")
    leg_w = widths.pop()
    drawn = sum(lvsref.to_um(card["r_length"]) for card in cards.values())
    pitch = leg_w + DIVIDER_LEG_SPACE_UM
    leg_len = math.sqrt(drawn * pitch)  # square-ish serpentine
    legs = math.ceil(drawn / leg_len) + DIVIDER_DUMMY_LEGS
    width = math.ceil(legs * pitch * 2.0) / 2.0
    height = math.ceil((leg_len + 2 * DIVIDER_LEG_END_UM) * 2.0) / 2.0
    return width, height, drawn, leg_w, legs


def por_comparator(b: CellBuilder) -> None:
    """The MOS portion of ``por_comparator`` (``design/por_comparator.sch``).

    **What is drawn, and what deliberately is not.** ``por_comparator`` has 18
    MOS devices and three ``ppolyf_u_3k`` poly resistors -- the sense divider
    ``XRTOP``/``XRBOT``/``XRHYS``. The curated ``gf180mcu`` extraction deck
    recognises ``nfet``/``pfet`` and nothing else (klayout-tools#219, resistors
    #222), so the divider cannot be extracted as devices. Drawing its poly
    anyway would be worse than leaving it out: the deck would read a drawn
    resistor body as plain interconnect and silently short ``VDD``-``SNS``,
    ``SNS``-``SNSB`` and ``SNSB``-``VSS`` together -- collapsing the comparator's
    own sense node onto the rail, which would then read as a layout bug in the
    part that *can* be checked. So, exactly as in ``bias_core`` (#68), the
    divider's area is **reserved** on annotation layer 200/0 (read by neither
    deck, so it changes no DRC or LVS verdict) and its two taps ``SNS``/``SNSB``
    are routed out to that region's edge. ``layout/README.md`` records which
    devices that leaves outside LVS coverage.

    The reserved rectangle is not a guess: :func:`_divider_footprint` reads
    ``r_width``/``r_length`` for the three segments out of the golden netlist
    and folds them at ``leg width + 1 um`` pitch into a roughly square
    serpentine, plus one end-of-string dummy leg at each end.

    **The BIAS_OKB inverter is instanced, not re-drawn.** ``MENP``/``MENN``
    already exist as ``por_comparator_bias_okb_inv`` (#16's proof cell, DRC- and
    LVS-clean in its own right), so this cell places one instance of it rather
    than a second copy of the same two devices. Its ``BIAS_OKB`` Metal1 label
    comes along with it and names that net in the flattened parent, which is
    why ``BIAS_OKB`` is a pin of this cell and not an internal node (see
    ``layout/lvs_reference.py``'s manifest entry).

    **Matching plan** -- ``layout/floorplan.md`` rank 4, followed as
    floorplanned, i.e. **standard practice, not common-centroid**, because
    #15's MC record measures the ratified threshold rows passing at 100 % yield
    regardless of the comparator's own offset:

    * ``XMINA``/``XMINB`` are adjacent, same orientation, identical drawn
      geometry, in the same substrate context, with no finger splitting and no
      interleaving. Their gate nets (``SNS``/``VREF``) sit on adjacent routing
      tracks and their drain nets (``NA``/``CMPO``) on the next adjacent pair,
      so the two halves' routing differs by one 0.8 um track pitch.
    * The sense divider keeps ``W = 2 um`` (the floorplan's explicit
      conclusion; nothing here narrows it) with same-flavor, same-width legs
      and ordinary serpentine folding for area, and standard end-of-string
      dummy segments -- all of which is what the reserved footprint above is
      computed from.
    * The load mirror ``XMLA``/``XMLB`` gets the same ordinary matched-pair
      practice (adjacent, same orientation, one well) although the floorplan
      names no plan for it.

    **Structure** -- same two-layer scheme as ``bias_core``: horizontal Poly2
    tracks, vertical Metal1 risers, Metal1-only by necessity (the extraction
    deck still declares one metal level at ``klt 0.1.0``)::

        +--- guard ring: COMP + Metal1, VSS-tied, continuous, contacts 1um ----+
        |  VDD rail (Metal1)                                                   |
        |  ..... routing channel: one Poly2 track per signal net .....         |
        |  [ PMOS row, one Nwell ]  [ NMOS row ]  [inv] [ reserved divider ]   |
        |  Nwell tie strap (COMP in Nwell -> VDD)                              |
        |  VSS rail (Metal1) over a p-substrate tap strap (COMP)               |
        +----------------------------------------------------------------------+

    Each cell in this file owns its own placement pass rather than sharing one
    emitter: a committed ``.gds`` is recorded evidence with its own DRC/LVS
    reports, and a shared emitter would mean a tweak aimed at one cell silently
    re-streams the other and invalidates reports nobody re-ran.
    """
    devices = _golden_devices("por_comparator.spice", "por_comparator")

    # --- placement pass: fix every device's x, then derive the frame -------
    tiles = []
    cursor = 0.0
    for name in POR_COMPARATOR_PMOS + POR_COMPARATOR_NMOS:
        if name == POR_COMPARATOR_NMOS[0]:
            cursor += REGION_GAP_UM
        device = devices[name]
        length = lvsref.to_um(device["params"]["l"])
        width = lvsref.to_um(device["params"]["w"])
        drain, gate, source, _body = device["nodes"]
        tiles.append(
            {
                "name": name,
                "pmos": name in POR_COMPARATOR_PMOS,
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
        for index, net in enumerate(POR_COMPARATOR_TRACKS)
    }
    vdd_y0 = channel_y0 + len(POR_COMPARATOR_TRACKS) * TRACK_PITCH_UM + 1.5
    vdd_y1 = vdd_y0 + 1.2
    vss_y0, vss_y1 = -5.2, -4.2
    tie_y0, tie_y1 = -2.2, -1.2

    # The instanced BIAS_OKB inverter sits on the row's own baseline, clear of
    # the routing channel: its own Poly2 gate strip tops out at y = 5.3, well
    # below the lowest track, so no track can touch it.
    inv_x, inv_y = row_x1 + 6.0, 0.0
    inv_x1 = inv_x + 2.4  # its Nwell's right edge

    div_w, div_h, div_len, div_leg_w, div_legs = _divider_footprint()
    reserved_x0 = inv_x1 + 6.0
    reserved_x1 = reserved_x0 + div_w
    reserved_y0 = -3.5
    reserved_y1 = reserved_y0 + div_h

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
        b.box(POLY2, gate_x0, -0.3, gate_x0 + length, width + 1.1)
        b.contact(gate_cx, width + 0.75)
        for y in _contact_rows(width):
            b.contact(x_source, y)
            b.contact(x_drain, y)

        riser(x_source, tile["s"], 0.15, max(0.6, width - 0.2))
        riser(x_drain, tile["d"], 0.15, max(0.6, width - 0.2))
        riser(gate_cx, tile["g"], width + 0.55, width + 0.95)

    # --- Poly2 routing channel ---------------------------------------------
    # Two tracks run further right than the device row: the pair the sense
    # divider taps (out to the reserved region), and the two nets the instanced
    # inverter drives/receives (out to its own risers).
    track_x1 = {
        "SNS": reserved_x0 + 3.0,
        "SNSB": reserved_x0 + 3.0,
        "BIAS_OK": inv_x - 2.6,
        "BIAS_OKB": inv_x + 1.8,
    }
    for net in POR_COMPARATOR_TRACKS:
        y = track_y[net]
        half_w = TRACK_W_UM / 2.0
        b.box(POLY2, p_x0 - 1.0, y - half_w, track_x1.get(net, row_x1 + 1.0), y + half_w)

    # --- Nwell, and its tie strap ------------------------------------------
    b.box(NWELL, p_x0 - 1.0, -2.6, p_x1 + 1.0, max_pw + 1.5)
    b.box(COMP, p_x0 - 0.5, tie_y0, p_x1 + 0.5, tie_y1)
    b.box(METAL1, p_x0 - 0.6, tie_y0 - 0.05, p_x1 + 0.6, tie_y1 + 0.05)
    for x in _span(p_x0 - 0.1, p_x1 + 0.1, TAP_PITCH_UM):
        b.contact(x, (tie_y0 + tie_y1) / 2.0)
    # ... carried up to the VDD rail clear of the first device's own risers.
    b.box(METAL1, p_x0 - 0.6, tie_y1, p_x0 - 0.2, vdd_y1)

    # --- the instanced BIAS_OKB inverter, and its four connections ----------
    b.instance("por_comparator_bias_okb_inv", por_comparator_bias_okb_inv, inv_x, inv_y)
    # VSS / VDD: straight down / up out of the sub-cell's own supply straps,
    # in the x window those straps share and the BIAS_OKB strap does not.
    b.box(METAL1, inv_x + 0.05, vss_y0, inv_x + 0.45, 0.75)
    b.box(METAL1, inv_x + 0.05, 3.75, inv_x + 0.45, vdd_y1)
    # BIAS_OKB: up the right-hand side, onto its own track.
    b.box(METAL1, inv_x + 1.2, 4.3, inv_x + 1.6, track_y["BIAS_OKB"] + 0.2)
    b.contact(inv_x + 1.4, track_y["BIAS_OKB"])
    # BIAS_OK: out to the left at the sub-cell's own gate-strap height (clear
    # of both supply straps in y), then up onto its track.
    b.box(METAL1, inv_x - 3.2, 1.8, inv_x - 0.5, 2.2)
    b.box(METAL1, inv_x - 3.2, 1.8, inv_x - 2.8, track_y["BIAS_OK"] + 0.2)
    b.contact(inv_x - 3.0, track_y["BIAS_OK"])

    # --- supply rails -------------------------------------------------------
    b.box(METAL1, gx0 + 2.5, vdd_y0, inv_x1 + 2.0, vdd_y1)
    b.box(METAL1, gx0 + 1.0, vss_y0, inv_x1 + 2.0, vss_y1)
    b.box(COMP, gx0 + 2.3, vss_y0, inv_x1 + 1.7, vss_y1)
    for x in _span(gx0 + 2.8, inv_x1 + 1.2, TAP_PITCH_UM):
        b.contact(x, (vss_y0 + vss_y1) / 2.0)

    # --- guard ring: continuous, VSS-tied, contacted at 1 um ----------------
    # Tied to VSS by abutting the VSS rail's left end; no floating segment.
    # This cell sits on the always-on POR domain's side of the block-level
    # domain seam (layout/floorplan.md, "Guard-ring / isolation plan"), whose
    # correctness the deck cannot check -- klayout-tools#281.
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

    # --- reserved sense-divider region (annotation only) --------------------
    b.box(RESERVED, reserved_x0, reserved_y0, reserved_x1, reserved_y1)

    # --- pins ---------------------------------------------------------------
    b.label("VDD", row_x1, (vdd_y0 + vdd_y1) / 2.0)
    b.label("VSS", row_x1, (vss_y0 + vss_y1) / 2.0)
    by_name = {tile["name"]: tile for tile in tiles}
    for net, owner in POR_COMPARATOR_PIN_ON_DRAIN.items():
        tile = by_name[owner]
        x = tile["x0"] + 2 * SD_EXT_UM + tile["l"] - CONT_INSET_UM
        b.label(net, x, track_y[net])
    for net, owner in POR_COMPARATOR_PIN_ON_GATE.items():
        tile = by_name[owner]
        b.label(net, tile["x0"] + SD_EXT_UM + tile["l"] / 2.0, track_y[net])


# --------------------------------------------------------------------------- #
# temp_core -- the PTAT/CTAT sensing core (#71)
# --------------------------------------------------------------------------- #
#
# Construction: two device rows (NMOS below, PMOS in Nwell above) facing one
# Metal1 routing channel. Each net owns one horizontal Metal1 track in the
# channel; each device terminal reaches its track on a vertical **poly**
# crossunder with a contact at each end. That is the single-metal-level regime
# layout/floorplan.md commits to ("poly used as the crossunder layer where two
# Metal1 runs must cross") -- klt 0.1.0's gf180mcu extraction deck still
# declares Metal1 only.
#
# Every drawn MOS is one finger. Matched devices are drawn as N identical
# fingers placed on a uniform pitch in the floorplan's common-centroid order,
# with edge dummy fingers; the reference netlist splits the same schematic
# device into the same N parallel devices (see layout/lvs_reference.py's
# ``fingers``/``dummies`` manifest fields and layout/README.md).

_TRACK_Y0 = 3.0  # y of the lowest routing track
_TRACK_PITCH = 1.0
_TRACK_HALF = 0.16  # Metal1 track half-width (0.32 total >= Mn.1's 0.23)
_TRACK_LEFT = -3.0  # every track starts here, so labels share one pin column

_SD_EXT = 0.8  # active from its own edge to the gate edge
_POLY_OVERHANG = 0.3  # gate poly beyond the channel edge (Poly2 over field)
_POLY_HALF = 0.20  # half-width of a poly crossunder (0.40 >= CO.3 0.22+2*0.07)
_COL_HALF = 0.16  # half-width of a Metal1 source/drain column
_LANDING = 0.6  # comp edge -> the poly crossunder's landing contact
_SLOT_GAP = 0.5  # x gap between adjacent device slots
_WELL_MARGIN = 0.5  # Nwell beyond the comp it holds (>= DF.4d's 0.12)
_WELL_SPLIT = 2.0  # extra x gap between two differently-biased Nwells
_CONTACT_PITCH = 1.0  # source/drain contact pitch along the channel width
_ROW_GAP = 3.0  # channel edge -> device row

#: One Metal1 track per net, in this order (bottom of the channel upward).
_TEMP_CORE_NETS = [
    "VSS",
    "VDD",
    "EN",
    "ENB",
    "IBIAS",
    "NBG",
    "PB",
    "PCAS",
    "NT",
    "NA",
    "NB",
    "N1",
    "N2",
    "PG",
    "M1D",
    "M2D",
    "M3D",
    "ND",
    "NR",
    "CTAT",
    "PTAT",
    "T5",
    "T4",
    "T3",
    "T2",
    "T1",
    "T0",
]


class _Channel:
    """The Metal1 routing channel: one horizontal track per net."""

    def __init__(self, builder: CellBuilder, nets: list[str]) -> None:
        self.b = builder
        self.nets = list(nets)
        self.track_y = {
            net: _TRACK_Y0 + index * _TRACK_PITCH for index, net in enumerate(self.nets)
        }
        self._reach = {net: _TRACK_LEFT for net in self.nets}

    @property
    def top(self) -> float:
        return _TRACK_Y0 + (len(self.nets) - 1) * _TRACK_PITCH

    def land(self, net: str, x_center: float) -> float:
        """Contact a poly crossunder onto ``net``'s track; return the track y."""
        y = self.track_y[net]
        self.b.contact(x_center, y)
        self._reach[net] = max(self._reach[net], x_center + 0.25)
        return y

    def draw(self) -> None:
        for net in self.nets:
            y = self.track_y[net]
            self.b.box(METAL1, _TRACK_LEFT, y - _TRACK_HALF, self._reach[net], y + _TRACK_HALF)
            self.b.label(net, _TRACK_LEFT + 1.0, y)


def _mos_finger(
    b: CellBuilder,
    channel: _Channel,
    x: float,
    *,
    pmos: bool,
    length: float,
    width: float,
    drain: str,
    gate: str,
    source: str,
    row_y: float,
) -> float:
    """Draw one MOS finger at ``x``; return the slot width.

    ``row_y`` is the comp edge facing the channel (the NMOS row's comp sits
    below it, the PMOS row's above it). Source/drain/gate each leave the device
    on their own poly crossunder and land on their net's track.
    """
    sign = 1.0 if pmos else -1.0  # direction from the channel into the row

    gate_x0 = x + _SD_EXT
    gate_x1 = gate_x0 + length
    gate_xc = 0.5 * (gate_x0 + gate_x1)
    comp_x1 = gate_x1 + _SD_EXT

    def band(y0: float, y1: float) -> tuple[float, float]:
        """A (low, high) y pair for offsets measured into the row."""
        a, c = row_y + sign * y0, row_y + sign * y1
        return (a, c) if a <= c else (c, a)

    # --- active + gate ------------------------------------------------------
    comp_lo, comp_hi = band(0.0, width)
    b.box(COMP, x, comp_lo, comp_x1, comp_hi)
    bar_lo, bar_hi = band(-_POLY_OVERHANG, width + _POLY_OVERHANG)
    b.box(POLY2, gate_x0, bar_lo, gate_x1, bar_hi)

    # --- source / drain columns --------------------------------------------
    for terminal_xc, poly_xc, net in (
        (x + 0.25, x + 0.25, source),
        (gate_x1 + 0.55, gate_x1 + 0.55, drain),
    ):
        stop = width - 0.3
        offset = 0.3
        while offset <= stop + 1e-9:
            b.contact(terminal_xc, row_y + sign * offset)
            offset += _CONTACT_PITCH
        if width < 0.6:  # too narrow for the loop above: one centred contact
            b.contact(terminal_xc, row_y + sign * width / 2.0)

        col_lo, col_hi = band(-(_LANDING + 0.15), width - 0.15)
        b.box(METAL1, terminal_xc - _COL_HALF, col_lo, terminal_xc + _COL_HALF, col_hi)

        track_y = channel.land(net, poly_xc)
        b.contact(poly_xc, row_y - sign * _LANDING)
        poly_end = track_y - sign * 0.18
        poly_start = row_y - sign * (_LANDING - 0.25)
        lo, hi = (min(poly_start, poly_end), max(poly_start, poly_end))
        b.box(POLY2, poly_xc - _POLY_HALF, lo, poly_xc + _POLY_HALF, hi)

    # --- gate crossunder ----------------------------------------------------
    gate_track = channel.land(gate, gate_xc)
    stub_far = gate_track - sign * 0.18
    stub_near = row_y
    lo, hi = (min(stub_far, stub_near), max(stub_far, stub_near))
    b.box(POLY2, gate_xc - _POLY_HALF, lo, gate_xc + _POLY_HALF, hi)

    return comp_x1 - x


#: The drawn device row, left to right. Each entry is
#: ``(row, length_um, width_um, drain, gate, source, well)``; ``well`` is
#: ``None`` for NMOS. ``"gap"`` entries open extra x for an Nwell split.
#:
#: Ordering is the floorplan's ranked matching plan, not the netlist's order:
#: rank 1's input pair (A-B-B-A) and load mirror (A-B-B-A) and rank 2's
#: cascoded mirror (1-2-3-3-2-1, each cascode finger abutting its own leg's
#: finger) are drawn as contiguous, uniformly pitched arrays with edge dummies.
_TEMP_CORE_ROW: list[tuple] = [
    # -- rank 1: amplifier input pair, common-centroid A-B-B-A in Nwell "NW2"
    ("p", 4.0, 16.0, "NT", "NT", "NT", "NW2"),  # edge dummy
    ("p", 4.0, 16.0, "N1", "NA", "NT", "NW2"),  # XMI1 finger A
    ("p", 4.0, 16.0, "N2", "NB", "NT", "NW2"),  # XMI2 finger B
    ("p", 4.0, 16.0, "N2", "NB", "NT", "NW2"),  # XMI2 finger B
    ("p", 4.0, 16.0, "N1", "NA", "NT", "NW2"),  # XMI1 finger A
    ("p", 4.0, 16.0, "NT", "NT", "NT", "NW2"),  # edge dummy
    ("gap",),
    # -- rank 1: tail device, adjacent to the pair (no centroid budget spent)
    ("p", 4.0, 20.0, "NT", "PB", "VDD", "NW1"),  # XMT
    # -- rank 1: load mirror, common-centroid A-B-B-A
    ("n", 8.0, 4.0, "VSS", "VSS", "VSS", None),  # edge dummy
    ("n", 8.0, 4.0, "N1", "N1", "VSS", None),  # XML1 finger A
    ("n", 8.0, 4.0, "N2", "N1", "VSS", None),  # XML2 finger B
    ("n", 8.0, 4.0, "N2", "N1", "VSS", None),  # XML2 finger B
    ("n", 8.0, 4.0, "N1", "N1", "VSS", None),  # XML1 finger A
    ("n", 8.0, 4.0, "VSS", "VSS", "VSS", None),  # edge dummy
    # -- rank 2: cascoded PMOS mirror, 1-2-3-3-2-1 with abutted cascodes
    ("p", 4.0, 4.0, "VDD", "VDD", "VDD", "NW1"),  # edge dummy
    ("p", 4.0, 4.0, "M1D", "PG", "VDD", "NW1"),  # XMP1 finger 1
    ("p", 1.0, 4.0, "NA", "PCAS", "M1D", "NW1"),  # XMPC1 finger 1
    ("p", 4.0, 4.0, "M2D", "PG", "VDD", "NW1"),  # XMP2 finger 2
    ("p", 1.0, 4.0, "NB", "PCAS", "M2D", "NW1"),  # XMPC2 finger 2
    ("p", 4.0, 4.0, "M3D", "PG", "VDD", "NW1"),  # XMP3 finger 3
    ("p", 1.0, 4.0, "PTAT", "PCAS", "M3D", "NW1"),  # XMPC3 finger 3
    ("p", 1.0, 4.0, "PTAT", "PCAS", "M3D", "NW1"),  # XMPC3 finger 3
    ("p", 4.0, 4.0, "M3D", "PG", "VDD", "NW1"),  # XMP3 finger 3
    ("p", 1.0, 4.0, "NB", "PCAS", "M2D", "NW1"),  # XMPC2 finger 2
    ("p", 4.0, 4.0, "M2D", "PG", "VDD", "NW1"),  # XMP2 finger 2
    ("p", 1.0, 4.0, "NA", "PCAS", "M1D", "NW1"),  # XMPC1 finger 1
    ("p", 4.0, 4.0, "M1D", "PG", "VDD", "NW1"),  # XMP1 finger 1
    ("p", 4.0, 4.0, "VDD", "VDD", "VDD", "NW1"),  # edge dummy
    # -- second stage + compensation (standard practice, per the floorplan)
    ("n", 8.0, 8.0, "PG", "N2", "VSS", None),  # XMS2N
    ("p", 4.0, 10.0, "PG", "PB", "VDD", "NW1"),  # XMS2P
    # -- bias mirror / enable network
    ("n", 2.0, 4.0, "IBIAS", "NBG", "VSS", None),  # XMBD
    ("n", 0.5, 2.0, "IBIAS", "EN", "NBG", None),  # XMPASS
    ("n", 0.5, 2.0, "NBG", "ENB", "VSS", None),  # XMDNB
    ("n", 2.0, 4.0, "PB", "NBG", "VSS", None),  # XMBN1
    ("p", 4.0, 10.0, "PB", "PB", "VDD", "NW1"),  # XMBP
    ("n", 2.0, 4.0, "PCAS", "NBG", "VSS", None),  # XMBN2
    ("p", 8.0, 1.0, "PCAS", "PCAS", "VDD", "NW1"),  # XMCB
    ("p", 0.5, 2.0, "ENB", "EN", "VDD", "NW1"),  # XMINVP
    ("n", 0.5, 1.0, "ENB", "EN", "VSS", None),  # XMINVN
    # -- startup detector
    ("p", 8.0, 1.0, "ND", "PB", "VDD", "NW1"),  # XMSU1
    ("n", 2.0, 2.0, "ND", "NR", "VSS", None),  # XMSU2
    ("n", 1.0, 4.0, "PG", "ND", "VSS", None),  # XMSU3
    ("p", 4.0, 1.0, "NR", "PG", "VDD", "NW1"),  # XMSU4
    ("n", 2.0, 2.0, "NR", "NR", "VSS", None),  # XMSU5
    # -- disable / reset clamps
    ("n", 0.5, 2.0, "ND", "ENB", "VSS", None),  # XMDND
    ("p", 0.5, 4.0, "PG", "EN", "VDD", "NW1"),  # XMENPG
    ("n", 1.0, 1.0, "PTAT", "ENB", "VSS", None),  # XMENPT
    ("n", 1.0, 1.0, "CTAT", "ENB", "VSS", None),  # XMENCT
    ("n", 1.0, 2.0, "N2", "ENB", "VSS", None),  # XMDN2
    ("n", 1.0, 2.0, "NT", "ENB", "VSS", None),  # XMDNT
    # -- rank 2: trim switches, placed symmetric left/right about the ladder
    ("n", 0.5, 32.0, "T5", "VDD", "T4", None),  # XSW5
    ("n", 0.5, 32.0, "T3", "VSS", "T2", None),  # XSW3
    ("n", 0.5, 32.0, "T1", "VSS", "T0", None),  # XSW1
    ("n", 0.5, 32.0, "T0", "VSS", "VSS", None),  # XSW0
    ("n", 0.5, 32.0, "T2", "VSS", "T1", None),  # XSW2
    ("n", 0.5, 32.0, "T4", "VSS", "T3", None),  # XSW4
]


def temp_core(b: CellBuilder) -> None:
    """``temp_core``'s MOS network, plus its two non-extractable structures.

    The stream carries three top cells:

    ``temp_core``
        every MOS device of ``design/netlist/temp_core.spice``, drawn per
        ``layout/floorplan.md``'s ranked matching plan. This is the cell
        ``klt extract``/``klt lvs`` run on (``--top temp_core``).
    ``temp_core_r2_ladder``
        rank 2's tiled, common-centroid ``ppolyf_u`` gain-ratio array.
    ``temp_core_pnp_array``
        rank 3's ``pnp_10p00x10p00`` centroid array with its dummy ring.

    The last two hold **no** device the curated ``gf180mcu`` extraction deck
    can recognise (klayout-tools#219/#222: MOS-only device coverage), and a
    drawn poly resistor is seen by that deck as a plain poly wire -- putting
    one in ``temp_core`` would short its own two terminals together and merge
    ``PTAT`` into ``VSS`` through the trim ladder. They are therefore drawn as
    sibling top cells: ``klt drc`` checks every top cell in the stream, so the
    geometry is still verified, while extraction/LVS stay on the MOS subset.
    """
    channel = _Channel(b, _TEMP_CORE_NETS)
    nrow_y = 0.0
    prow_y = channel.top + _ROW_GAP

    x = 0.0
    wells: dict[str, list[tuple[float, float, float]]] = {}
    for entry in _TEMP_CORE_ROW:
        if entry[0] == "gap":
            x += _WELL_SPLIT
            continue
        row, length, width, drain, gate, source, well = entry
        pmos = row == "p"
        slot = _mos_finger(
            b,
            channel,
            x,
            pmos=pmos,
            length=length,
            width=width,
            drain=drain,
            gate=gate,
            source=source,
            row_y=prow_y if pmos else nrow_y,
        )
        if pmos:
            wells.setdefault(well, []).append((x, x + slot, width))
        x += slot + _SLOT_GAP

    for spans in wells.values():
        x0 = min(span[0] for span in spans) - _WELL_MARGIN
        x1 = max(span[1] for span in spans) + _WELL_MARGIN
        y1 = prow_y + max(span[2] for span in spans) + _WELL_MARGIN
        b.box(NWELL, x0, prow_y - _WELL_MARGIN, x1, y1)

    channel.draw()

    _temp_core_r2_ladder(b)
    _temp_core_pnp_array(b)


#: Implant marker layers. No rule in ``klt``'s curated ``gf180mcu`` DRC deck
#: reads them, but a ``ppolyf_u`` body and a vertical PNP's emitter/base/
#: collector are not identifiable without them.
PPLUS = (31, 0)
NPLUS = (32, 0)
DRC_BJT = (127, 5)

#: rank 2's unit sub-resistor: the block's ``2 um`` drawn width convention and
#: ``XR1``'s own drawn length, so ``R1`` is exactly one unit and every ``R2``
#: segment is tiled from copies of it (``design/netlist/temp_core.spice``).
_R_UNIT_W = 2.0
_R_UNIT_L = 119.47
_R_COLS = 11  # 9 interior columns + one dummy column each side
_R_ROWS = 5  # 3 interior rows + one dummy row top and bottom


def _r_tile(b: CellBuilder, x: float, y: float) -> None:
    """One ``ppolyf_u`` unit sub-resistor with both terminals contacted."""
    b.box(POLY2, x, y, x + _R_UNIT_W, y + _R_UNIT_L)
    b.box(PPLUS, x - 0.2, y - 0.2, x + _R_UNIT_W + 0.2, y + _R_UNIT_L + 0.2)
    for end in (y + 0.3, y + _R_UNIT_L - 0.3):
        for offset in (0.5, 1.0, 1.5):
            b.contact(x + offset, end)
        b.box(METAL1, x - 0.05, end - 0.21, x + _R_UNIT_W + 0.05, end + 0.21)


def _temp_core_r2_ladder(b: CellBuilder) -> None:
    """rank 2's gain-ratio array: ``XR1``'s unit at the centroid, the ``R2``
    tiles common-centroid around it, dummy tiles on the whole perimeter.

    Every tile is one copy of the same drawn unit (same width, orientation and
    end geometry), so the ratio -- not just the absolute values -- is what the
    array protects, exactly as ``layout/floorplan.md`` rank 2 asks. The
    perimeter dummy ring is the "dummy resistor segments, same flavor/width"
    row of that document's dummy-strategy table.
    """
    b.add_cell("temp_core_r2_ladder")
    pitch_x = _R_UNIT_W + 1.0
    pitch_y = _R_UNIT_L + 2.0
    for row in range(_R_ROWS):
        y = row * pitch_y
        for col in range(_R_COLS):
            _r_tile(b, col * pitch_x, y)
        # Serpentine straps: the tiled units are a series string, not islands.
        for col in range(_R_COLS - 1):
            end = y + 0.3 if col % 2 == 0 else y + _R_UNIT_L - 0.3
            b.box(
                METAL1,
                col * pitch_x + _R_UNIT_W + 0.05,
                end - 0.21,
                (col + 1) * pitch_x - 0.05,
                end + 0.21,
            )
    # The centroid tile is R1's unit; label it so the array is readable.
    b.label("R1_UNIT", 5 * pitch_x + 1.0, 2 * pitch_y + _R_UNIT_L / 2.0)


#: rank 3's ``pnp_10p00x10p00`` unit emitter, and the 5x5 grid that holds the
#: active 3x3 (``XQ1`` centre + ``XQ8A..XQ8H`` at 45 degree steps) inside a
#: ring of dummy unit cells.
_Q_EMITTER = 10.0
_Q_PITCH = 14.0
_Q_GRID = 5


def _temp_core_pnp_array(b: CellBuilder) -> None:
    """rank 3's vertical-PNP centroid array, with one shared base/collector
    ring construction so every unit device sees the same well/tap environment.
    """
    b.add_cell("temp_core_pnp_array")
    span = (_Q_GRID - 1) * _Q_PITCH + _Q_EMITTER

    for row in range(_Q_GRID):
        for col in range(_Q_GRID):
            x, y = col * _Q_PITCH, row * _Q_PITCH
            b.box(COMP, x, y, x + _Q_EMITTER, y + _Q_EMITTER)
            b.box(PPLUS, x - 0.3, y - 0.3, x + _Q_EMITTER + 0.3, y + _Q_EMITTER + 0.3)
            steps = int(_Q_EMITTER - 1.0)
            for i in range(steps):
                for j in range(steps):
                    b.contact(x + 0.5 + i, y + 0.5 + j)
            b.box(METAL1, x + 0.2, y + 0.2, x + _Q_EMITTER - 0.2, y + _Q_EMITTER - 0.2)

    def ring(spec, inner: float, width: float) -> None:
        lo, hi = -inner, span + inner
        b.box(spec, lo, lo, hi, lo + width)
        b.box(spec, lo, hi - width, hi, hi)
        b.box(spec, lo, lo, lo + width, hi)
        b.box(spec, hi - width, lo, hi, hi)

    def ring_contacts(inner: float, width: float) -> None:
        lo, hi = -inner, span + inner
        mid = width / 2.0
        steps = int((hi - lo) - 1.0)
        for i in range(steps):
            pos = lo + 0.5 + i
            b.contact(pos, lo + mid)
            b.contact(pos, hi - mid)
            b.contact(lo + mid, pos)
            b.contact(hi - mid, pos)

    # Shared base ring (n+ COMP inside the Nwell) ...
    ring(COMP, 4.0, 2.0)
    ring(NPLUS, 4.3, 2.6)
    ring_contacts(4.0, 2.0)
    ring(METAL1, 3.8, 1.6)
    # ... one Nwell holding the whole array and its base ring, marked as one
    # bipolar device region (the DRM's DRC_BJT mark layer; "BJT.3" keeps it
    # 0.1 um clear of unrelated COMP, which the collector ring is not) ...
    b.box(NWELL, -5.5, -5.5, span + 5.5, span + 5.5)
    b.box(DRC_BJT, -5.5, -5.5, span + 5.5, span + 5.5)
    # ... and the collector ring (p+ COMP on substrate, outside the Nwell).
    ring(COMP, 10.0, 2.0)
    ring(PPLUS, 10.3, 2.6)
    ring_contacts(10.0, 2.0)
    ring(METAL1, 9.8, 1.6)


#: cell name -> body. Add a cell here and it joins ``layout/run_checks.sh``.
CELLS = {
    "bias_core": bias_core,
    "por_comparator": por_comparator,
    "por_comparator_bias_okb_inv": por_comparator_bias_okb_inv,
    "temp_core": temp_core,
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
