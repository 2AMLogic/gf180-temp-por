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

    Nwell 21/0 · Comp 22/0 · Pplus 31/0 · Nplus 32/0 · Poly2 30/0 ·
    Contact 33/0 · Metal1 34/0 · Metal2 36/0
    Metal1 pin/label purpose 34/10 (net names -> extracted pin names)
    Metal4 46/0 · FuseTop 75/0 · CAP_MK 117/5 · MIM_L_MK 117/10
                    (the MiM capacitor stack, ``por_output_chain`` only)
    SAB 49/0 · RES_MK 110/5
                    (the poly-resistor marker pair, ``temp_core``'s R2 ladder
                    only, #93)
    DRC_BJT 127/5
                    (the vertical-bipolar marker, ``temp_core``'s PNP array
                    only, #93)

plus one repo-local annotation layer that is **not** a gf180mcu drawn layer and
is read by neither the DRC deck nor the extraction deck:

    RESERVED 200/0  area reserved for devices the deck cannot represent
                    (see ``bias_core``'s and ``por_comparator``'s docstrings;
                    ``por_output_chain``'s MiM reservation is gone -- it draws
                    those capacitors for real, #92)

Device dimensions are never retyped here. The real sub-circuit cells
(``bias_core``, ``por_comparator``, ``por_output_chain``) read every ``L``/``W``
out of their ``design/netlist/*.spice`` through ``lvs_reference``'s parser --
the same golden netlist the LVS reference is derived from -- so the layout and
the reference cannot drift apart silently: move a size in the schematic and both
``--check`` gates fail together. The same holds for the one reserved region
whose size is load-bearing: the sense divider's footprint is folded from the
golden netlist's own ``r_width`` / ``r_length``, not from a number typed in
here.
"""

from __future__ import annotations

import argparse
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
#: Upper routing layers. Used only by ``temp_por_top`` (#72): every sub-circuit
#: cell below is Metal1-only, and stays that way. See ``temp_por_top``'s
#: docstring and ``layout/floorplan.md`` -> "Routing / metal-level note" for
#: why the block-level assembly may use them and the sub-cells do not.
VIA1 = (35, 0)
METAL2 = (36, 0)
METAL2_LABEL = (36, 10)
VIA2 = (38, 0)
METAL3 = (42, 0)
#: The gf180mcu MiM capacitor stack, used only by ``por_output_chain`` (#92).
#: ``klt``'s curated deck recognises exactly one MiM device class,
#: ``cap_mim_2f0_m4m5_noshield`` -- the DRM's "10.4.2 MIM Option B" 5-metal
#: stack -- as a ``FuseTop`` top plate carrying **both** marker layers over a
#: ``Metal4`` bottom plate. All four layers are read by the extraction deck, and
#: ``Metal4`` by the DRC deck's ``mim.*`` rules; none is an annotation layer.
METAL4 = (46, 0)
FUSETOP = (75, 0)
CAP_MK = (117, 5)
MIM_L_MK = (117, 10)
#: Implant and device-marker layers -- the drawn poly resistors' and vertical
#: bipolars' own stack, shared by ``temp_core`` (#93) and ``bias_core`` (#90).
#: Only ``DRC_BJT`` carries a rule in ``klt``'s curated ``gf180mcu`` DRC deck
#: (``bjt.separation.comp.1``); the *extraction* deck reads all six.
#:
#: A plain ``ppolyf_u`` body is ``Poly2 & RES_MK & Pplus & SAB``, and the
#: high-sheet-rho family is the same stack plus the ``Resistor`` high-rho ID
#: layer. Either way the recognised body is cut out of the poly connectivity
#: region, so the marked segment is a device and the unmarked poly either side
#: of it stays the device's two terminals. ``Pplus`` is not required for that
#: recognition -- it is drawn because it is what makes the device *p+* poly
#: rather than n+, and the deck reads it (the ``ppolyf_u`` class's own
#: ``requires``), so leaving it off would be a silent under-description.
#:
#: For a vertical bipolar the deck's base region is ``Nwell`` ∩ ``DRC_BJT``, its
#: emitter is the ``Comp`` inside that base, and it draws no collector at all
#: (the substrate is the collector). ``DRC_BJT`` being a DRC layer too is why it
#: has to stay clear of every ``Comp`` that is not an emitter.
PPLUS = (31, 0)
NPLUS = (32, 0)
SAB = (49, 0)
RESISTOR_ID = (62, 0)
RES_MK = (110, 5)
DRC_BJT = (127, 5)
RESERVED = (200, 0)

#: gf180mcu DRM "CO.1": contact is a fixed 0.22 x 0.22 um square.
CONTACT_SIDE_UM = 0.22
#: gf180mcu DRM "V1.1"/"V2.1": Via1/Via2 are a fixed 0.26 x 0.26 um square.
#: ``klt``'s curated ``gf180mcu`` DRC deck carries no via rule at all (see
#: ``layout/README.md`` -> "Known deck limits"), so this size is held to the
#: DRM by construction here rather than by a check.
VIA_SIDE_UM = 0.26
#: gf180mcu DRM "CO.3": minimum Poly2 overlap of a contact, all round. A Poly2
#: shape that a contact lands on has to extend at least this far past every
#: edge of the contact, so the shortest Poly2 stub that can host a contact
#: centred at ``x`` reaches ``x + CONTACT_SIDE_UM / 2 + POLY2_CONT_ENC_UM``.
POLY2_CONT_ENC_UM = 0.07


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
        # Quantise the centre to the layout's own DBU grid *before* deriving
        # the two edges: computing them straight from a `cx`/`cy` that is not
        # already grid-exact (e.g. an `_span()`-derived centre, whose step is
        # an arbitrary division and so is not, in general, an exact multiple
        # of the grid) lets the two edges round independently and land 1 DBU
        # closer together than `CONTACT_SIDE_UM` -- a `contact.width.1`
        # violation despite every caller asking for the same fixed size
        # (#91's sense divider first surfaced this on an unrelated,
        # pre-existing `_span()` call it happened to shift).
        dbu = self.layout.dbu
        cx = round(cx / dbu) * dbu
        cy = round(cy / dbu) * dbu
        half = CONTACT_SIDE_UM / 2.0
        self.box(CONTACT, cx - half, cy - half, cx + half, cy + half)

    def via(self, spec, cx: float, cy: float) -> None:
        """One DRM-sized Via1/Via2 square centred at ``cx, cy``."""
        half = VIA_SIDE_UM / 2.0
        self.box(spec, cx - half, cy - half, cx + half, cy + half)

    def label(self, name: str, x: float, y: float, spec=METAL1_LABEL) -> None:
        self.cell.shapes(self._layer(spec)).insert(
            self._kdb.DText(name, self._kdb.DTrans(self._kdb.DVector(x, y))).to_itype(
                self.layout.dbu
            )
        )

    def labels_in(self, cell, spec=METAL1_LABEL) -> dict[str, list[tuple[float, float]]]:
        """Every label string drawn (recursively) in ``cell``, and where.

        ``temp_por_top`` reads its own instances' pin labels back out of the
        stream it just built, instead of re-deriving each sub-cell's internal
        geometry: a pin label is by construction a point inside a Metal1 shape
        on that net, which is exactly what the assembly needs to land a via on.
        Coordinates are in ``cell``'s own frame; the caller adds the placement
        offset.
        """
        found: dict[str, list[tuple[float, float]]] = {}
        for item in cell.begin_shapes_rec(self._layer(spec)).each():
            text = item.shape().dtext.transformed(item.dtrans())
            found.setdefault(text.string, []).append((text.x, text.y))
        return {name: sorted(points) for name, points in found.items()}

    def instance(self, name: str, body, dx: float, dy: float):
        """Draw ``body`` into a child cell and place one instance at ``dx, dy``.

        The cell hierarchy is real in the stream and flat everywhere it is
        checked: both ``klt drc`` and ``klt extract`` read each layer through
        ``begin_shapes_rec`` on the top cell, i.e. flattened (see
        ``klayout_tools.drc``/``extract``). So an instanced sub-cell's geometry
        -- including its Metal1 labels -- lands in the parent's own flat
        connectivity graph, which is what lets a parent wire abut a sub-cell's
        strap and come out as one net.

        Returns the child cell, so a parent that has just placed a sub-circuit
        can read its pin labels back out (:meth:`labels_in`) rather than
        re-deriving the sub-circuit's internal geometry a second time.
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
        return child

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

# --- bias_core's passive/bipolar block (#90) ------------------------------- #
#
# The 16 non-MOS devices used to be a blank 130 x 130 um rectangle on annotation
# layer 200/0, because the deck recognised nfet/pfet only. They are drawn now.
# The block sits to the right of the MOS row, inside the same guard ring, and
# reaches the row the same way everything else in this cell does: **horizontal
# Poly2 tracks, vertical Metal1 risers**. Its own eight tracks sit in a band
# below it (one per net a drawn passive touches); a Metal1 jog in the gap
# between the row and the block carries each of the five nets that exist on both
# sides from its row track down to its block track.

#: x gap between the MOS row's right edge and the passive block, in um. Wide
#: enough for the five Metal1 jog columns below plus clearance either side.
PASSIVE_GAP_UM = 13.0
#: First jog column's x, relative to the MOS row's right edge, and their pitch.
#: Ordered so a jog column's x rises with its row track's y, which is what keeps
#: a jog from ever reaching the y of a row track that extends past it.
PASSIVE_JOG_X0_UM = 3.0
PASSIVE_JOG_PITCH_UM = 2.0
#: Lowest of the block's own Poly2 distribution tracks (they use the row's own
#: :data:`TRACK_PITCH_UM`).
PASSIVE_TRACK_Y0_UM = -3.0
#: The baseline every drawn passive sits on -- clear of the track band below it.
PASSIVE_BASE_Y_UM = 13.0
#: One Poly2 track per net a drawn passive touches, bottom to top. The first
#: five also exist on the MOS row (:data:`BIAS_CORE_TRACKS`) and are jogged
#: across, in the row's own track order; ``EC``/``ER``/``NZ`` exist only here.
BIAS_CORE_PASSIVE_TRACKS = ("NA", "NB", "NBTOP", "N2", "VREF", "EC", "ER", "NZ")
BIAS_CORE_PASSIVE_CROSSING = ("NA", "NB", "NBTOP", "N2", "VREF")
#: The 3x3 common-centroid array the emitter-ratio pair is drawn as: the 1x
#: device (``XQ1``) at the centre, the eight 8x devices on the perimeter, so
#: the 8x leg's centroid *is* the 1x leg's. ``XQR`` -- the VREF branch's own
#: separate 1x device, not part of that ratio -- takes a fourth column beside
#: the middle row. Slots are ``(column, row)``.
BIAS_CORE_PNP_SLOTS = {
    "XQ1": (1, 1),
    "XQ8A": (0, 0),
    "XQ8B": (1, 0),
    "XQ8C": (2, 0),
    "XQ8D": (0, 1),
    "XQ8E": (2, 1),
    "XQ8F": (0, 2),
    "XQ8G": (1, 2),
    "XQ8H": (2, 2),
    "XQR": (3, 1),
}
#: Nwell margin around the PNP array's emitter bounding box, in um.
PNP_NWELL_MARGIN_UM = 8.0
#: Where the array's Nwell tap ring sits inside that margin, in um from the
#: emitter bounding box. Far enough outside every ``DRC_BJT`` mark to clear
#: ``bjt.separation.comp.1`` with margin, and far enough inside the Nwell edge
#: to clear ``nwell.enclosing.comp.1`` with margin.
PNP_TAP_OFFSET_UM = 4.0
PNP_TAP_W_UM = 1.0
#: Metal1 escape-riser width and its clearance from an emitter plate, in um.
PNP_ESCAPE_W_UM = 0.4
#: Resistor banks, widest first, and the gap between two of them, in um.
BIAS_CORE_RESISTOR_ORDER = ("XR2", "XRZ", "XR1", "XRT")
RES_BANK_GAP_UM = 5.0


def _golden_devices(source: str, subckt: str) -> dict[str, dict]:
    """Parse ``design/netlist/<source>``'s ``<subckt>`` for its MOS devices."""
    text = (REPO_ROOT / "design" / "netlist" / source).read_text()
    return lvsref.parse_devices(lvsref.subckt_body(text, subckt))


def _golden_caps(source: str, subckt: str) -> dict[str, dict]:
    """Parse ``design/netlist/<source>``'s ``<subckt>`` for its MiM caps."""
    text = (REPO_ROOT / "design" / "netlist" / source).read_text()
    return lvsref.parse_capacitors(lvsref.subckt_body(text, subckt))


def _golden_resistors(source: str, subckt: str) -> dict[str, dict]:
    """Parse ``design/netlist/<source>``'s ``<subckt>`` for its poly resistors."""
    text = (REPO_ROOT / "design" / "netlist" / source).read_text()
    return {name: card for name, card in
            lvsref.parse_passives(lvsref.subckt_body(text, subckt)).items()
            if card["kind"] == "resistor"}


def _golden_bipolars(source: str, subckt: str) -> dict[str, dict]:
    """Parse ``design/netlist/<source>``'s ``<subckt>`` for its vertical PNPs."""
    text = (REPO_ROOT / "design" / "netlist" / source).read_text()
    return {name: card for name, card in
            lvsref.parse_passives(lvsref.subckt_body(text, subckt)).items()
            if card["kind"] == "bipolar"}


#: gf180mcu DRM "10.4.2 MIM Capacitor", Option B, rule ``MIMTM.3``: minimum MiM
#: bottom-plate (Metal4) overlap of the top plate (FuseTop) is 0.6 um. Drawn
#: with margin -- the recognised capacitance is set by the *top* plate's area
#: (the plates' geometric overlap), so an oversized bottom plate costs nothing.
#: ``klt``'s ``mim.enclosing.fusetop.1`` checks this one.
MIM_ENCLOSURE_UM = 0.7
#: DRM rule ``MIMTM.1``: minimum MiM bottom-plate spacing to any bottom-plate
#: metal, 1.2 um. Drawn with the same margin; ``klt``'s ``mim.space.1`` checks
#: it (as a general Metal4-to-Metal4 space, which over-flags rather than under-).
MIM_SPACE_UM = 1.4


def _mim_cap(b: CellBuilder, x0: float, y0: float, w: float, h: float) -> None:
    """One drawn MiM capacitor with its lower-left top-plate corner at x0, y0.

    Three coincident rectangles on ``FuseTop`` + ``CAP_MK`` + ``MIM_L_MK`` --
    the deck's ``top_plate`` and both of its ``top_plate_requires`` markers, all
    three needed before any of the geometry is a capacitor rather than
    unrecognised metal -- over a ``Metal4`` bottom plate enclosing it by
    :data:`MIM_ENCLOSURE_UM` on every side. The extracted capacitance is the two
    plates' overlap area times the deck's 2.0 fF/um^2, i.e. ``w * h`` exactly,
    which is what ``lvs_reference.build_cap_cards`` puts in the reference.
    """
    b.box(FUSETOP, x0, y0, x0 + w, y0 + h)
    b.box(CAP_MK, x0, y0, x0 + w, y0 + h)
    b.box(MIM_L_MK, x0, y0, x0 + w, y0 + h)
    edge = MIM_ENCLOSURE_UM
    b.box(METAL4, x0 - edge, y0 - edge, x0 + w + edge, y0 + h + edge)


def _mim_block(
    caps: dict[str, dict], arrays: dict[str, tuple[int, int]], x0: float, y0: float
) -> tuple[list[tuple[str, float, float, float, float]], float, float]:
    """Place every drawn MiM plate of ``arrays``, left to right from x0, y0.

    ``arrays`` maps a golden MiM card's name to the (columns, rows) array its
    ``m=`` multiplier is drawn as -- one schematic device stays one contiguous
    array, because that is what it is. Plate sizes come out of the golden
    netlist's own ``c_width`` / ``c_length``; nothing is retyped here, so a
    schematic edit that resizes a cap moves this geometry with it and both
    ``--check`` gates fail together if the committed stream is not rebuilt.

    ``x0``/``y0`` are the lower-left corner of the first *bottom* plate.
    Returns ``(rects, x1, y1)`` where ``rects`` are the top plates as
    ``(name, x, y, w, h)`` and ``x1``/``y1`` bound the whole block's Metal4.
    """
    rects: list[tuple[str, float, float, float, float]] = []
    edge, gap = MIM_ENCLOSURE_UM, MIM_SPACE_UM
    cursor = x0
    top = y0
    for name, (columns, rows) in arrays.items():
        cap = caps[name]
        units = lvsref.cap_units(cap)
        if columns * rows != units:
            raise ValueError(
                f"{name}: {columns}x{rows} drawn plates for m={units} in the "
                "golden netlist"
            )
        width = lvsref.to_um(cap["params"]["c_width"])
        height = lvsref.to_um(cap["params"]["c_length"])
        pitch_x = width + 2 * edge + gap
        pitch_y = height + 2 * edge + gap
        for row in range(rows):
            for column in range(columns):
                rects.append(
                    (
                        name,
                        cursor + edge + column * pitch_x,
                        y0 + edge + row * pitch_y,
                        width,
                        height,
                    )
                )
        cursor += columns * pitch_x
        top = max(top, y0 + rows * pitch_y)
    return rects, cursor - gap, top - gap


#: Poly space between two adjacent legs of a drawn serpentine resistor, in um
#: (DRM ``PL.3a`` asks 0.24; drawn at 1.0 so the fold is readable and the bend
#: that joins two legs is the same width as a leg).
RES_SPACE_UM = 1.0
#: How far each end of a fold's poly runs past the marked body before its
#: terminal contact, in um. The head is *unmarked* poly -- that is what makes it
#: the device's terminal rather than more resistor -- and it carries exactly one
#: contact, because two or more would trip klayout-tools#288's resistor-body
#: heuristic on the head itself (see ``layout/README.md``).
RES_HEAD_UM = 4.0


def _poly_resistor(
    b: CellBuilder, x0: float, y0: float, width: float, leg: float, legs: int
) -> tuple[float, float]:
    """One folded poly resistor, its lower-left leg corner at ``x0, y0``.

    ``legs`` marked vertical legs of ``width`` x ``leg`` on a
    ``width + RES_SPACE_UM`` pitch, joined alternately top and bottom by
    *unmarked* poly bends, with an unmarked head running :data:`RES_HEAD_UM`
    below the free end of the first and last leg. ``legs`` is always even
    (:func:`lvs_reference.resistor_segments`), which is exactly what puts both
    heads at the bottom edge so each terminal risers straight down to its
    routing track with nothing to cross.

    The marker rectangles are the legs *exactly*: the deck's recognised body is
    ``Poly2 & RES_MK & SAB & Resistor``, and KLayout derives the device's
    ``L``/``W`` from that region's own area and perimeter, so a marker that
    overshot a leg into a bend would silently lengthen the extracted resistor.

    Returns the two heads' centre x, in ``(first, last)`` order -- i.e. the
    golden netlist's own ``(a, b)`` node order.
    """
    pitch = width + RES_SPACE_UM
    leg_x = [x0 + index * pitch for index in range(legs)]

    for x in leg_x:
        b.box(POLY2, x, y0, x + width, y0 + leg)
        # Marked body: coincident on all four layers, from one rectangle.
        for spec in (PPLUS, SAB, RESISTOR_ID, RES_MK):
            b.box(spec, x, y0, x + width, y0 + leg)

    for index in range(legs - 1):
        x = leg_x[index]
        if index % 2 == 0:
            b.box(POLY2, x, y0 + leg, x + pitch + width, y0 + leg + width)
        else:
            b.box(POLY2, x, y0 - width, x + pitch + width, y0)

    heads = (leg_x[0], leg_x[-1])
    for x in heads:
        b.box(POLY2, x, y0 - RES_HEAD_UM, x + width, y0)
        b.contact(x + width / 2.0, y0 - RES_HEAD_UM / 2.0)
    return (heads[0] + width / 2.0, heads[1] + width / 2.0)


#: Emitter-to-emitter gap inside the drawn PNP array, in um (DRM ``DF.3a`` asks
#: 0.28). Wide enough that two neighbouring emitters' ``DRC_BJT`` marks -- each
#: grown by ``lvs_reference.BIPOLAR_BASE_MARGIN_UM`` -- stay geometrically separate,
#: which is what gives every drawn device its own base region (hence its own
#: ``AB``/``PB``) while one shared drawn Nwell still puts every base on one net.
PNP_GAP_UM = 5.0
PNP_CONT_INSET_UM = 0.5  # contact array inset from the emitter window's edge
PNP_CONT_PITCH_UM = 2.0
PNP_PLATE_INSET_UM = 0.3  # Metal1 emitter plate inset from the same edge


def _pnp_unit(b: CellBuilder, x0: float, y0: float, width: float, length: float) -> None:
    """One drawn vertical PNP's emitter window and device mark at ``x0, y0``.

    The base is the caller's drawn Nwell (shared by the whole array, so every
    base is one net), the collector is the substrate and is not drawn at all,
    and this is the rest: a ``Comp`` emitter window of the size the PDK
    subcircuit's own name declares, a contact array inside it, its Metal1 plate,
    and the ``DRC_BJT`` mark grown by ``lvs_reference.BIPOLAR_BASE_MARGIN_UM`` on
    every side -- the mark being what turns Nwell into a *base* rather than an
    ordinary PMOS well, and what fixes the extracted base area.
    """
    b.box(COMP, x0, y0, x0 + width, y0 + length)
    margin = lvsref.BIPOLAR_BASE_MARGIN_UM
    b.box(DRC_BJT, x0 - margin, y0 - margin, x0 + width + margin, y0 + length + margin)
    for cx in _span(
        x0 + PNP_CONT_INSET_UM, x0 + width - PNP_CONT_INSET_UM, PNP_CONT_PITCH_UM
    ):
        for cy in _span(
            y0 + PNP_CONT_INSET_UM, y0 + length - PNP_CONT_INSET_UM, PNP_CONT_PITCH_UM
        ):
            b.contact(cx, cy)


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


def _poly2_landing_x1(contact_cx: float) -> float:
    """Right edge of a Poly2 track that must host a contact at ``contact_cx``.

    A routing track that simply *ends* on its landing contact's centre covers
    only the contact's west half, which is a ``poly2.enclosing.contact.1``
    (DRM ``CO.3``) violation on the east side -- and one the deck reports
    against Poly2, not against the contact, so it is easy to miss while reading
    the contact's own placement (#102). Deriving the overhang from ``CO.3``
    rather than hand-writing a coordinate keeps the enclosure correct if the
    track pitch or contact size ever moves.

    The overhang is at least half a track width, so a track that ends this way
    gets the same margin east that its own ``TRACK_W_UM`` width already gives
    the contact north and south.
    """
    return contact_cx + max(
        TRACK_W_UM / 2.0, CONTACT_SIDE_UM / 2.0 + POLY2_CONT_ENC_UM
    )


def _span(low: float, high: float, pitch: float) -> list[float]:
    """Evenly spaced centres covering ``[low, high]`` at about ``pitch``."""
    if high <= low:
        return [(low + high) / 2.0]
    count = max(1, int((high - low) / pitch))
    step = (high - low) / count
    return [low + index * step for index in range(count + 1)]


def _place_tiles(devices: dict[str, dict], groups) -> list[dict]:
    """Fix every device's x across a left-to-right sequence of regions.

    ``groups`` is a sequence of device-name sequences; each becomes one
    contiguous region of the drawn row, separated from the next by
    ``REGION_GAP_UM`` (wide enough for an Nwell edge to fall between an Nwell'd
    region and an adjacent non-Nwell one). ``l``/``w`` come out of the golden
    netlist -- no dimension is retyped here.
    """
    tiles: list[dict] = []
    cursor = 0.0
    for index, group in enumerate(groups):
        if index:
            cursor += REGION_GAP_UM
        for name in group:
            device = devices[name]
            length = lvsref.to_um(device["params"]["l"])
            width = lvsref.to_um(device["params"]["w"])
            drain, gate, source, _body = device["nodes"]
            tiles.append(
                {
                    "name": name,
                    "group": index,
                    "x0": cursor,
                    "l": length,
                    "w": width,
                    "d": drain,
                    "g": gate,
                    "s": source,
                }
            )
            cursor += 2 * SD_EXT_UM + length + TILE_GAP_UM
    return tiles


def _tile_x1(tile: dict) -> float:
    """Right edge of a tile's drawn active."""
    return tile["x0"] + 2 * SD_EXT_UM + tile["l"]


def _terminal_x(tile: dict, terminal: str) -> float:
    """x of a tile's source / gate / drain riser column."""
    if terminal == "s":
        return tile["x0"] + CONT_INSET_UM
    if terminal == "d":
        return _tile_x1(tile) - CONT_INSET_UM
    if terminal == "g":
        return tile["x0"] + SD_EXT_UM + tile["l"] / 2.0
    raise ValueError(f"unknown terminal {terminal!r}")


def _make_riser(b: CellBuilder, vdd_y1: float, vss_y0: float, track_y: dict):
    """Build a ``riser(x_centre, net, y_low, y_high)`` closure for one cell frame.

    One Metal1 riser from a device terminal to its rail or track, bound to
    the calling cell's own supply-rail y-coordinates and Poly2 track map.
    """

    def riser(x_centre: float, net: str, y_low: float, y_high: float) -> None:
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

    return riser


def _draw_tiles(b: CellBuilder, tiles: list[dict], riser) -> None:
    """Draw one single-finger MOS per tile, and riser out its three terminals.

    ``riser(x, net, y_low, y_high)`` is the caller's frame-aware router: it
    knows where that cell's supply rails and Poly2 tracks are.
    """
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
        # in these cells routes.
        b.box(POLY2, gate_x0, -0.3, gate_x0 + length, width + 1.1)
        b.contact(gate_cx, width + 0.75)
        for y in _contact_rows(width):
            b.contact(x_source, y)
            b.contact(x_drain, y)

        riser(x_source, tile["s"], 0.15, max(0.6, width - 0.2))
        riser(x_drain, tile["d"], 0.15, max(0.6, width - 0.2))
        riser(gate_cx, tile["g"], width + 0.55, width + 0.95)


def _draw_guard_ring(
    b: CellBuilder, gx0: float, gy0: float, gx1: float, gy1: float
) -> None:
    """A continuous COMP+Metal1 p-substrate guard ring, contacted at 1 um.

    Tied to VSS by the caller abutting the VSS rail to it; no floating segment.
    The deck has no tap/well-label layer, so LVS cannot confirm the tie, and
    nothing in the flow checks the ring's continuity either (filed generically
    as klayout-tools#303) -- that stays a design-review claim for this cell
    (``layout/README.md``).
    """
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


def _bias_core_passives(
    b: CellBuilder, px0: float, track_y: dict[str, float], vss_y1: float
) -> tuple[float, float]:
    """Draw ``bias_core``'s 16 non-MOS devices; return the block's ``(x1, y1)``.

    Three regions, left to right / bottom to top from ``px0``:

    * the **PNP array** -- one drawn Nwell holding all ten emitters, each with
      its own ``DRC_BJT`` mark, laid out per :data:`BIAS_CORE_PNP_SLOTS`, with a
      VSS-tied Nwell tap ring around it and one Metal1 escape riser per net;
    * the **MiM caps**, above the array, drawn but connected to nothing -- the
      deck registers a recognised capacitor's plates outside its own metal/via
      stack, so no drawn routing can put a plate on a net (klayout-tools#314);
    * the **resistor banks**, each a fold from :func:`_poly_resistor` whose leg
      count and length come from ``lvs_reference.resistor_segments`` -- the same
      function the reference netlist declares them from.

    Every terminal risers straight down on Metal1 to its own Poly2 track in
    ``track_y``. Nothing here draws a horizontal Metal1 run, so no two nets'
    Metal1 can meet: a riser crossing a track it does not belong to has no
    contact, exactly as in the MOS row above.
    """
    resistors = _golden_resistors("bias_core.spice", "bias_core")
    bipolars = _golden_bipolars("bias_core.spice", "bias_core")

    # --- PNP array ----------------------------------------------------------
    emitter_w, emitter_l = lvsref.emitter_window_um(bipolars["XQ1"]["model"])
    for name, card in bipolars.items():
        if lvsref.emitter_window_um(card["model"]) != (emitter_w, emitter_l):
            raise ValueError(f"{name}: the array assumes one emitter size")
    pitch = emitter_w + PNP_GAP_UM
    columns = max(column for column, _row in BIAS_CORE_PNP_SLOTS.values()) + 1
    rows = max(row for _column, row in BIAS_CORE_PNP_SLOTS.values()) + 1
    ax = px0 + PNP_NWELL_MARGIN_UM
    ay = PASSIVE_BASE_Y_UM
    array_w = (columns - 1) * pitch + emitter_w
    array_h = (rows - 1) * pitch + emitter_l

    b.box(
        NWELL,
        ax - PNP_NWELL_MARGIN_UM,
        ay - PNP_NWELL_MARGIN_UM,
        ax + array_w + PNP_NWELL_MARGIN_UM,
        ay + array_h + PNP_NWELL_MARGIN_UM,
    )
    for name, (column, row) in BIAS_CORE_PNP_SLOTS.items():
        _pnp_unit(
            b, ax + column * pitch, ay + row * pitch, emitter_w, emitter_l
        )
        del name

    # Escape risers: one per net, each in a column gap or beside the array, so
    # the centre device's own escape never has to cross the ring of eight.
    gap = PNP_GAP_UM / 2.0
    plate = PNP_PLATE_INSET_UM
    half = PNP_ESCAPE_W_UM / 2.0
    escape_x = {
        "EC": (
            ax - gap + half,  # col 0, out to the left
            ax + emitter_w + gap,  # cols 1 (rows 0 and 2), into the first gap
            ax + 2 * pitch + emitter_w + gap,  # col 2, out to the right
        ),
        "NA": (ax + pitch + emitter_w + gap,),  # XQ1, into the second gap
        "ER": (ax + 3 * pitch + emitter_w + gap,),  # XQR, out to the right
    }
    #: Which escape column each drawn emitter's Metal1 plate reaches out to.
    plate_reach = {
        (0, 0): escape_x["EC"][0], (0, 1): escape_x["EC"][0],
        (0, 2): escape_x["EC"][0],
        (1, 0): escape_x["EC"][1], (1, 2): escape_x["EC"][1],
        (2, 0): escape_x["EC"][2], (2, 1): escape_x["EC"][2],
        (2, 2): escape_x["EC"][2],
        (1, 1): escape_x["NA"][0],
        (3, 1): escape_x["ER"][0],
    }
    for (column, row), reach in plate_reach.items():
        x0 = ax + column * pitch + plate
        x1 = ax + column * pitch + emitter_w - plate
        b.box(
            METAL1,
            min(x0, reach - half),
            ay + row * pitch + plate,
            max(x1, reach + half),
            ay + row * pitch + emitter_l - plate,
        )
    for net, columns_x in escape_x.items():
        top = ay + (rows - 1) * pitch + emitter_l - plate
        if net == "NA" or net == "ER":
            top = ay + pitch + emitter_l - plate
        for x in columns_x:
            b.box(METAL1, x - half, track_y[net] - 0.2, x + half, top)
            b.contact(x, track_y[net])

    # Nwell tap ring: continuous on three sides, open at the bottom where every
    # escape riser leaves. Tied to VSS by its own riser down to the rail. As
    # everywhere else in this cell the tie is a design-review claim, not a
    # checked one -- the deck has no tap layer (klayout-tools#303).
    tap = PNP_TAP_OFFSET_UM
    tap_x0, tap_x1 = ax - tap - PNP_TAP_W_UM, ax + array_w + tap
    tap_y0, tap_y1 = ay - tap, ay + array_h + tap
    ring = [
        (tap_x0, tap_y0, tap_x0 + PNP_TAP_W_UM, tap_y1 + PNP_TAP_W_UM),
        (tap_x1, tap_y0, tap_x1 + PNP_TAP_W_UM, tap_y1 + PNP_TAP_W_UM),
        (tap_x0, tap_y1, tap_x1 + PNP_TAP_W_UM, tap_y1 + PNP_TAP_W_UM),
    ]
    for rect in ring:
        b.box(COMP, *rect)
        b.box(METAL1, rect[0] - 0.1, rect[1] - 0.1, rect[2] + 0.1, rect[3] + 0.1)
    tap_half = PNP_TAP_W_UM / 2.0
    for y in _span(tap_y0 + tap_half, tap_y1 + tap_half, TAP_PITCH_UM):
        b.contact(tap_x0 + tap_half, y)
        b.contact(tap_x1 + tap_half, y)
    for x in _span(tap_x0 + tap_half, tap_x1 + tap_half, TAP_PITCH_UM):
        b.contact(x, tap_y1 + tap_half)
    b.box(METAL1, tap_x0 + 0.1, vss_y1, tap_x0 + PNP_TAP_W_UM - 0.1, tap_y0)

    nwell_x1 = ax + array_w + PNP_NWELL_MARGIN_UM
    nwell_y1 = ay + array_h + PNP_NWELL_MARGIN_UM

    # --- MiM caps, above the array -----------------------------------------
    caps = _golden_caps("bias_core.spice", "bias_core")
    mim_plates, mim_x1, mim_y1 = _mim_block(
        caps, {"XCC": (1, 1), "XCOK": (1, 1)}, px0, nwell_y1 + 6.0
    )
    for _name, x, y, width, height in mim_plates:
        _mim_cap(b, x, y, width, height)

    # --- resistor banks -----------------------------------------------------
    bank_x = max(nwell_x1, mim_x1) + RES_BANK_GAP_UM
    block_y1 = max(nwell_y1, mim_y1)
    for name in BIAS_CORE_RESISTOR_ORDER:
        card = resistors[name]
        width = lvsref.to_um(card["params"]["r_width"])
        # The one fold decision, taken in lvs_reference so the drawn string and
        # the declared one can never disagree (bias_core's own manifest entry
        # sets this cell's leg ceiling/target).
        segments = lvsref.resistor_segments(
            lvsref.to_um(card["params"]["r_length"]),
            lvsref.resistor_fold("bias_core"),
        )
        heads = _poly_resistor(
            b, bank_x, PASSIVE_BASE_Y_UM, width, segments[0], len(segments)
        )
        for head_x, net in zip(heads, card["nodes"][:2]):
            b.box(
                METAL1,
                head_x - PNP_ESCAPE_W_UM,
                PASSIVE_BASE_Y_UM - RES_HEAD_UM + 0.4,
                head_x + PNP_ESCAPE_W_UM,
                PASSIVE_BASE_Y_UM - RES_HEAD_UM / 2.0 + 0.4,
            )
            b.box(
                METAL1,
                head_x - PNP_ESCAPE_W_UM / 2.0,
                track_y[net] - 0.2,
                head_x + PNP_ESCAPE_W_UM / 2.0,
                PASSIVE_BASE_Y_UM - RES_HEAD_UM / 2.0 + 0.4,
            )
            b.contact(head_x, track_y[net])
        bank_w = (len(segments) - 1) * (width + RES_SPACE_UM) + width
        bank_x += bank_w + RES_BANK_GAP_UM
        block_y1 = max(block_y1, PASSIVE_BASE_Y_UM + segments[0] + width)

    return bank_x - RES_BANK_GAP_UM, block_y1


def bias_core(b: CellBuilder) -> None:
    """``bias_core`` (``design/bias_core.sch``), drawn -- all 50 devices.

    **What is drawn.** 34 MOS in the device row, and -- as of #90 -- the 16
    non-MOS devices that used to be a blank rectangle on annotation layer 200/0
    beside it: 10 vertical PNPs (``XQ1``, ``XQ8A..H``, ``XQR``), 4 poly
    resistors (``XR1``, ``XR2``, ``XRT``, ``XRZ``) and 2 MiM caps (``XCC``,
    ``XCOK``). They were left out while ``klt``'s curated ``gf180mcu`` deck
    recognised ``nfet``/``pfet`` only, because a drawn-but-unrecognised poly
    resistor body extracts as ordinary *interconnect* and silently shorts its
    own two terminal nets (``NB``-``EC``, ``VREF``-``ER``, ``NBTOP``-``NB``,
    ``NZ``-``N2``). ``klt 0.1.0`` declares ``bjt``, ``ppolyf_u``/``ppolyf_u_1k``
    and ``cap_mim_2f0_m4m5_noshield`` as well, so the geometry that makes each
    of them a *device* rather than interconnect is drawn here and every one of
    those four nets is now a distinct extracted net. See
    :func:`_bias_core_passives`.

    **Structure** (all dimensions from ``design/netlist/bias_core.spice``)::

        +--- guard ring: COMP + Metal1, VSS-tied, continuous, contacts 1um ---+
        |  VDD rail (Metal1)                          [ resistor folds ]      |
        |  ..... routing channel: one Poly2 track per signal net ..... |      |
        |                                             [ MiM caps ]    | jogs |
        |  [ PMOS row, one Nwell ]   [ NMOS row ]     [ PNP array  ]   |      |
        |  Nwell tie strap (COMP in Nwell -> VDD)     ... passive tracks ...  |
        |  VSS rail (Metal1) over a p-substrate tap strap (COMP), full width  |
        +---------------------------------------------------------------------+

    Routing is Metal1-only throughout, in both regions and for the same reason:
    the scheme that makes this cell routable on one metal is **horizontal Poly2
    tracks, vertical Metal1 risers**. A riser crosses every track it does not
    belong to with no contact, so the only connections are the ones drawn. The
    passive block has its own eight-track band below it (one per net a drawn
    passive touches); the five nets that exist in both regions are carried
    across by one Metal1 jog each, in the gap between the two.

    Matched pairs get ordinary matched-pair practice (adjacent placement, same
    orientation, identical drawn geometry, common well): ``XMI1``/``XMI2``,
    ``XML1``/``XML2``, ``XMOKA``/``XMOKB``, ``XMOL1``/``XMOL2``, and the three
    core mirror legs ``XMP1``/``XMP2``/``XMP3``. ``layout/floorplan.md``'s
    ranked common-centroid plan covers ``temp_core`` and ``por_comparator``
    only -- it prescribes nothing for this cell, so nothing is invented for the
    MOS row. The one place this cell *does* use a common centroid is the
    emitter-ratio pair the whole reference depends on: ``XQ1`` sits at the
    centre of the 3x3 array whose perimeter is ``XQ8A..H``
    (:data:`BIAS_CORE_PNP_SLOTS`), so the 8x leg's centroid is the 1x leg's.

    **What the resistors cannot be matched on.** Every leg of every fold is the
    same drawn width (the golden netlist's own ``r_width``), which is the
    first-order matching parameter. Leg *lengths* differ per resistor, and have
    to: the schematic's ``R2/R1`` is 4104/350, whose lowest terms need a unit
    leg of 2 um -- 2227 legs between the two devices. A non-integer design ratio
    is a schematic fact this layout must not silently "fix", so the fold picks
    the closest exact division per device instead (:func:`resistor_segments`).
    """
    devices = _golden_devices("bias_core.spice", "bias_core")

    # --- placement pass: fix every device's x, then derive the frame -------
    tiles = _place_tiles(devices, (BIAS_CORE_PMOS, BIAS_CORE_NMOS))

    pmos = [tile for tile in tiles if tile["group"] == 0]
    p_x0 = pmos[0]["x0"]
    p_x1 = _tile_x1(pmos[-1])
    row_x1 = _tile_x1(tiles[-1])
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

    # The passive/bipolar block, and the two things that reach it: one Poly2
    # track per net a drawn passive touches, and one Metal1 jog column per net
    # that also exists on the MOS row.
    passive_x0 = row_x1 + PASSIVE_GAP_UM
    passive_track_y = {
        net: PASSIVE_TRACK_Y0_UM + index * TRACK_PITCH_UM
        for index, net in enumerate(BIAS_CORE_PASSIVE_TRACKS)
    }
    jog_x = {
        net: row_x1 + PASSIVE_JOG_X0_UM + index * PASSIVE_JOG_PITCH_UM
        for index, net in enumerate(BIAS_CORE_PASSIVE_CROSSING)
    }

    riser = _make_riser(b, vdd_y1, vss_y0, track_y)

    # --- devices -----------------------------------------------------------
    _draw_tiles(b, tiles, riser)

    # --- Poly2 routing channel --------------------------------------------
    # A net that also exists in the passive block runs on to its own jog column
    # instead of stopping at the row's edge. The columns rise with their tracks'
    # y, so no jog ever descends across a track that reaches past it.
    for net in BIAS_CORE_TRACKS:
        y = track_y[net]
        half_w = TRACK_W_UM / 2.0
        x1 = jog_x[net] + 0.6 if net in jog_x else row_x1 + 1.0
        b.box(POLY2, p_x0 - 1.0, y - half_w, x1, y + half_w)

    # --- Nwell, and its tie strap -----------------------------------------
    b.box(NWELL, p_x0 - 1.0, -2.6, p_x1 + 1.0, max_pw + 1.5)
    b.box(COMP, p_x0 - 0.5, tie_y0, p_x1 + 0.5, tie_y1)
    b.box(METAL1, p_x0 - 0.6, tie_y0 - 0.05, p_x1 + 0.6, tie_y1 + 0.05)
    for x in _span(p_x0 - 0.1, p_x1 + 0.1, TAP_PITCH_UM):
        b.contact(x, (tie_y0 + tie_y1) / 2.0)
    # ... carried up to the VDD rail clear of the first device's own risers.
    b.box(METAL1, p_x0 - 0.6, tie_y1, p_x0 - 0.2, vdd_y1)

    # --- the passive/bipolar block, and its own track band ------------------
    block_x1, block_y1 = _bias_core_passives(b, passive_x0, passive_track_y, vss_y1)
    for net, y in passive_track_y.items():
        half_w = TRACK_W_UM / 2.0
        x0 = jog_x[net] - 0.6 if net in jog_x else passive_x0 - 0.6
        b.box(POLY2, x0, y - half_w, block_x1, y + half_w)
    for net, x in jog_x.items():
        b.box(
            METAL1,
            x - RISER_W_UM / 2.0,
            passive_track_y[net] - 0.2,
            x + RISER_W_UM / 2.0,
            track_y[net] + 0.2,
        )
        b.contact(x, track_y[net])
        b.contact(x, passive_track_y[net])

    clear = GUARD_RING_CLEAR_UM + GUARD_RING_W_UM
    gx0 = p_x0 - 1.0 - clear
    gx1 = block_x1 + clear
    gy0 = vss_y0 - clear
    gy1 = max(vdd_y1, block_y1) + clear

    # --- supply rails ------------------------------------------------------
    # VSS runs the full cell width: the passive block's Nwell tap ties to it.
    b.box(METAL1, gx0 + 2.5, vdd_y0, row_x1 + 2.0, vdd_y1)
    b.box(METAL1, gx0 + 1.0, vss_y0, block_x1 + 1.0, vss_y1)
    b.box(COMP, gx0 + 2.3, vss_y0, block_x1 + 0.7, vss_y1)
    for x in _span(gx0 + 2.8, block_x1 + 0.2, TAP_PITCH_UM):
        b.contact(x, (vss_y0 + vss_y1) / 2.0)

    # --- guard ring: continuous, VSS-tied, contacted at 1 um ---------------
    # Tied to VSS by abutting the VSS rail's left end; no floating segment.
    _draw_guard_ring(b, gx0, gy0, gx1, gy1)

    # --- pins --------------------------------------------------------------
    b.label("VDD", row_x1, (vdd_y0 + vdd_y1) / 2.0)
    b.label("VSS", row_x1, (vss_y0 + vss_y1) / 2.0)
    by_name = {tile["name"]: tile for tile in tiles}
    for net, owner in BIAS_CORE_PIN_ON_DRAIN.items():
        b.label(net, _terminal_x(by_name[owner], "d"), track_y[net])


# --------------------------------------------------------------------------- #
# por_output_chain (#70)
# --------------------------------------------------------------------------- #

#: ``por_output_chain``'s NMOS devices, left to right. ``XMBD`` leads: it is the
#: always-on ``IBIAS`` mirror diode that DR-010 makes load-bearing for the whole
#: shared node, so it sits at the ``IBIAS``-entry (bias_core-facing) edge of the
#: cell with nothing between it and the ``IBIAS`` pin.
POR_OUTPUT_CHAIN_NMOS = (
    "XMBD",
    "XMN1",
    # 10 nA NMOS reference leg, then the two 5x deglitch tails' NMOS half
    "XMND",
    "XMDGNT",
    "XMDGNI",
    # the two restoring inverters' NMOS halves
    "XMG1N",
    "XMG2N",
    "XMDIS",
    # trip detector, then the release latch that holds its stage-A node down
    # once RESETn is high (issue #56 / DR-016) -- adjacent to XMDBNI, whose
    # gate it shares a net with (ND1) and whose geometry it duplicates.
    "XMDANT",
    "XMDBNI",
    "XMRLK",
    # release-NAND series pull-down stack (matched pair -- adjacent, same
    # orientation, identical drawn geometry)
    "XMNAN1",
    "XMNAN2",
)

#: ``por_output_chain``'s PMOS devices, left to right, ending with ``XMOP`` so
#: the push-pull pair lands together at the pad-facing end (see the docstring).
POR_OUTPUT_CHAIN_PMOS = (
    # 10 nA PMOS reference and its copy (matched mirror pair -- adjacent)
    "XMPD",
    "XMP2",
    "XMDGPT",
    # the 1:4 timer leg and the trip stage B source, both off PDN (matched
    # legs -- identical geometry, adjacent, same orientation)
    "XMPT",
    "XMDBPT",
    "XMDGPI",
    "XMG1P",
    "XMG2P",
    "XMTSW",
    "XMDAPI",
    # release-NAND parallel pull-ups (matched pair -- adjacent)
    "XMNAP1",
    "XMNAP2",
    "XMAST",
    # output pull-up: last, so it abuts the driver region
    "XMOP",
)

#: The pad-facing output pull-down. Its own region at the right-hand edge, so
#: ``RESETn`` leaves the cell at the edge nearest the ``RESETn`` pad.
POR_OUTPUT_CHAIN_DRIVER = ("XMON",)

#: One Poly2 routing track per signal net, bottom to top in the channel above
#: the device row. ``VDD``/``VSS`` are Metal1 rails, not tracks.
POR_OUTPUT_CHAIN_TRACKS = (
    "PDN",
    "NDL",
    "IBIAS",
    "POR_RAW",
    "NDGP",
    "NDGN",
    "NDG",
    "PGDG",
    "PGDGB",
    "NTS",
    "TIM",
    "ND1",
    "TRIP",
    "NNAND",
    "RSTB",
    "RESETn",
)

#: Metal1 pin labels: net -> (device, terminal). A label becomes an extracted
#: pin only inside a Metal1 shape on that net, so each is dropped on the riser
#: of a terminal that carries it -- chosen at the edge the signal enters or
#: leaves by.
POR_OUTPUT_CHAIN_PIN_ON = {
    "IBIAS": ("XMBD", "d"),
    "POR_RAW": ("XMDGNI", "g"),
    "RESETn": ("XMON", "d"),
}

#: How the cell's 2 MiM caps are drawn: name -> (columns, rows). ``XCTIM``'s
#: ``m=4`` becomes a 2x2 array of its own 28x28 um plate, kept contiguous
#: because it is one schematic device; ``XCDG`` is a single 11x11 um plate in
#: the column beside it. ``_mim_block`` asserts each array against the golden
#: netlist's own ``m=``, and takes the plate sizes from the same card, so
#: nothing about the caps is retyped here.
#:
#: The whole block lands in the same place the pre-#92 reservation did (above
#: the VDD rail, inside the guard ring) and comes out 74.0 x 60.2 um against the
#: 70 x 62 um that reservation predicted -- the same separate floor area, now
#: drawn. It is still **not** stacked over the device row: MiM sits high enough
#: that stacking is plausible, but that is a DRC call this repo cannot make
#: against a deck carrying two MiM rules and no inter-layer ones, so the
#: pessimistic choice stands (``design/por_output_chain.md`` defers the same
#: question).
POC_MIM_ARRAYS = {"XCTIM": (2, 2), "XCDG": (1, 1)}


def por_output_chain(b: CellBuilder) -> None:
    """All of ``por_output_chain`` (``design/por_output_chain.sch``) -- the 28
    MOS devices and, since #92, both MiM caps.

    **What is drawn, and what is still not proven.** The cell has 30 devices:
    28 single-finger MOS (14 pfet, 14 nfet) and 2 MiM caps (``XCDG`` 11x11 um,
    ``XCTIM`` 4 x 28x28 um). All 30 are drawn and all 30 are extracted and
    compared -- 33 extracted devices, because ``XCTIM``'s ``m=4`` draws as four
    units and the deck models no multiplier. The 28th MOS, ``XMRLK``, is the
    release latch issue #56 added (DR-016); it is placed beside ``XMDBNI``,
    whose gate net (``ND1``) and drawn geometry it shares.

    The caps were reserved floor area until #92: ``klt``'s curated ``gf180mcu``
    deck used to recognise ``nfet``/``pfet`` only (klayout-tools#219), so drawn
    MiM geometry would have been read as ordinary interconnect and silently
    shorted (klayout-tools#288). ``klt 0.1.0`` declares
    ``cap_mim_2f0_m4m5_noshield`` (#225 landed), so the plates are now real:
    ``FuseTop`` top plate carrying both ``CAP_MK`` and ``MIM_L_MK``, over a
    ``Metal4`` bottom plate -- see :func:`_mim_cap`. That is the whole of the
    upper-level geometry in this cell; signal routing is still Metal1-only.

    What the compare now proves about them is their **capacitance**: the
    extracted value is the drawn plates' overlap area times the deck's
    2.0 fF/um^2, checked against the same golden ``c_width``/``c_length`` the
    plates are drawn from. What it still does not prove is **what either plate
    is connected to**. ``klt`` registers a recognised capacitor's plates as
    their own self-connected nodes outside the deck's metal/via stack, and the
    top plate's layer is not in that stack at all, so no drawn routing can put a
    plate on a schematic net -- every cap extracts as an isolated pair of nets
    whatever is drawn around it. Drawing plate-to-rail routing anyway would add
    real geometry that no check in this flow can read, so it is not drawn, and
    ``lvs_reference.py`` names the plate nets after the schematic nodes they are
    *meant* to be on (``XCDG.NDG``) so the gap is legible in the reference
    netlist. Filed generically as klayout-tools#314 (and #315 for the deck
    modelling only the 5-metal MiM variant); ``layout/README.md`` records both.

    That gap costs **no net** in the compare: both ``NDG`` and ``TIM`` carry MOS
    terminals as well, so every net in the schematic still exists on both sides
    with all of its MOS connections. And the two capacitor *values* -- the
    deglitch dwell and the one-shot width -- are no longer purely ``sim/``'s
    claim: the drawn area behind them is now checked.

    **Placement.** ``layout/floorplan.md`` puts this cell nearest the
    ``RESETn`` pad, "shortest path from the push-pull output driver", and in
    the always-on POR domain. Both are honoured *inside* the cell as well as
    by the block-level slot:

    - ``XMON`` -- the push-pull pull-down -- is its own region at the **right
      (pad-facing) edge**, with ``XMOP`` the last device of the PMOS region
      immediately to its left. The pair is adjacent, and the ``RESETn`` pin
      label sits on ``XMON``'s drain riser, the cell's right-most Metal1 on
      that net. Nothing is placed between the driver and the pad edge.
    - ``XMBD`` leads the NMOS region at the **left (``bias_core``-facing)
      edge**, where ``IBIAS`` arrives. Per
      ``spec/decision-records/DR-010-...``, ``XMBD`` is ungated and always on,
      and is what defines the shared ``IBIAS`` node's operating point. It is
      drawn gate-and-drain on the ``IBIAS`` pin net and source on ``VSS``, with
      **no series device anywhere in that path** -- the pin label is on
      ``XMBD``'s own drain riser, so there is nowhere for a gating element to
      hide. ``layout/tests/test_lvs_reference.py`` asserts that mechanically
      rather than leaving it to this paragraph.

    **Structure** (all dimensions from ``design/netlist/por_output_chain.spice``,
    the same golden netlist the LVS reference is derived from)::

        +--- guard ring: COMP + Metal1, VSS-tied, continuous, contacts 1um ---+
        |  [ MiM block: 4 x XCTIM as 2x2, then XCDG -- Metal4 + FuseTop ]     |
        |  VDD rail (Metal1)                                                  |
        |  ..... routing channel: one Poly2 track per signal net .....        |
        |  [ NMOS row ]  [ PMOS row, one Nwell, ends XMOP ]   [ XMON ]        |
        |                Nwell tie strap (COMP in Nwell -> VDD)     ^ RESETn  |
        |  VSS rail (Metal1) over a p-substrate tap strap (COMP)              |
        +---------------------------------------------------------------------+

    Signal routing is Metal1-only -- the scheme this cell was drawn with when
    the extraction deck declared one metal level, kept because it works and
    redrawing a proven cell to use a capability it does not need is a
    regression risk for no gain. The MiM block's ``Metal4`` is the cell's only
    geometry above Metal1, and it is device geometry, not routing. The scheme
    that makes 28 devices routable on one metal is ``bias_core``'s: **horizontal
    Poly2 tracks, one per signal net, with vertical Metal1 risers**, so a riser
    crosses every track it does not belong to with no contact.

    **Matching.** ``layout/floorplan.md``'s ranked, #15-data-driven
    common-centroid plan covers ``temp_core`` (ranks 1-3) and ``por_comparator``
    (rank 4) only -- it prescribes nothing for this cell, and nothing is
    invented here to fill the gap. The same-polarity matched groups get ordinary
    matched-pair practice instead (adjacent placement, same orientation,
    identical drawn geometry, common well): ``XMPD``/``XMP2`` (the 10 nA PMOS
    reference and its copy), ``XMPT``/``XMDBPT`` (identical 0.5/10 legs off
    ``PDN``), ``XMNAP1``/``XMNAP2`` and ``XMNAN1``/``XMNAN2`` (the release
    NAND's pull-up pair and pull-down stack). **Dummy edge devices are not
    drawn**: a drawn dummy MOS extracts as a real device, and the deck has no
    way to mark one as non-functional, so it would land in the extracted
    netlist as a device the schematic-derived reference does not have and fail
    LVS. That is a tool gap, filed generically upstream, not a matching
    decision -- see ``layout/README.md``.
    """
    devices = _golden_devices("por_output_chain.spice", "por_output_chain")

    # --- placement pass: fix every device's x, then derive the frame -------
    tiles = _place_tiles(
        devices,
        (POR_OUTPUT_CHAIN_NMOS, POR_OUTPUT_CHAIN_PMOS, POR_OUTPUT_CHAIN_DRIVER),
    )
    by_name = {tile["name"]: tile for tile in tiles}

    pmos = [tile for tile in tiles if tile["group"] == 1]
    p_x0 = pmos[0]["x0"]
    p_x1 = _tile_x1(pmos[-1])
    row_x0 = tiles[0]["x0"]
    row_x1 = _tile_x1(tiles[-1])
    max_w = max(tile["w"] for tile in tiles)
    max_pw = max(tile["w"] for tile in pmos)

    channel_y0 = max_w + 3.0
    track_y = {
        net: channel_y0 + index * TRACK_PITCH_UM
        for index, net in enumerate(POR_OUTPUT_CHAIN_TRACKS)
    }
    vdd_y0 = channel_y0 + len(POR_OUTPUT_CHAIN_TRACKS) * TRACK_PITCH_UM + 1.5
    vdd_y1 = vdd_y0 + 1.2
    vss_y0, vss_y1 = -5.2, -4.2
    tie_y0, tie_y1 = -2.2, -1.2

    mim_plates, mim_x1, mim_y1 = _mim_block(
        _golden_caps("por_output_chain.spice", "por_output_chain"),
        POC_MIM_ARRAYS,
        row_x0 + 1.0,
        vdd_y1 + 3.0,
    )

    clear = GUARD_RING_CLEAR_UM + GUARD_RING_W_UM
    gx0 = row_x0 - 1.0 - clear
    gx1 = row_x1 + 2.0 + clear
    gy0 = vss_y0 - clear
    gy1 = mim_y1 + clear
    if mim_x1 + clear > gx1:
        raise ValueError("the drawn MiM block does not fit inside the guard ring")

    riser = _make_riser(b, vdd_y1, vss_y0, track_y)

    # --- devices -----------------------------------------------------------
    _draw_tiles(b, tiles, riser)

    # --- Poly2 routing channel --------------------------------------------
    for net in POR_OUTPUT_CHAIN_TRACKS:
        y = track_y[net]
        half_w = TRACK_W_UM / 2.0
        b.box(POLY2, row_x0 - 1.0, y - half_w, row_x1 + 1.0, y + half_w)

    # --- Nwell over the PMOS row, and its VDD tie strap --------------------
    # XMON's active starts REGION_GAP_UM + TILE_GAP_UM right of XMOP's, so the
    # well edge clears the pad-facing nfet by 4 um.
    b.box(NWELL, p_x0 - 1.0, -2.6, p_x1 + 1.0, max_pw + 1.5)
    b.box(COMP, p_x0 - 0.5, tie_y0, p_x1 + 0.5, tie_y1)
    b.box(METAL1, p_x0 - 0.6, tie_y0 - 0.05, p_x1 + 0.6, tie_y1 + 0.05)
    for x in _span(p_x0 - 0.1, p_x1 + 0.1, TAP_PITCH_UM):
        b.contact(x, (tie_y0 + tie_y1) / 2.0)
    # ... carried up to the VDD rail in the gap between the two device rows,
    # clear of any device's own risers.
    b.box(METAL1, p_x0 - 0.6, tie_y1, p_x0 - 0.2, vdd_y1)

    # --- supply rails ------------------------------------------------------
    b.box(METAL1, gx0 + 2.5, vdd_y0, row_x1 + 2.0, vdd_y1)
    b.box(METAL1, gx0 + 1.0, vss_y0, row_x1 + 2.0, vss_y1)
    b.box(COMP, gx0 + 2.3, vss_y0, row_x1 + 1.7, vss_y1)
    for x in _span(gx0 + 2.8, row_x1 + 1.2, TAP_PITCH_UM):
        b.contact(x, (vss_y0 + vss_y1) / 2.0)

    # --- guard ring: continuous, VSS-tied, contacted at 1 um ---------------
    # This is the cell's edge of the always-on POR domain's ring; it is tied to
    # VSS by abutting the VSS rail's left end, with no floating segment.
    _draw_guard_ring(b, gx0, gy0, gx1, gy1)

    # --- MiM caps: drawn, not reserved (#92) -------------------------------
    for _name, x, y, w, h in mim_plates:
        _mim_cap(b, x, y, w, h)

    # --- pins --------------------------------------------------------------
    b.label("VDD", row_x1, (vdd_y0 + vdd_y1) / 2.0)
    b.label("VSS", row_x1, (vss_y0 + vss_y1) / 2.0)
    for net, (owner, terminal) in POR_OUTPUT_CHAIN_PIN_ON.items():
        b.label(net, _terminal_x(by_name[owner], terminal), track_y[net])


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
#: divider"). Poly resistors -- drawn for real as of #91: ``klt 0.1.0``'s
#: extraction deck models a drawn ``ppolyf_u``/``ppolyf_u_1k`` high-sheet-rho
#: poly resistor (klayout-tools#219/#222/#299), and ``por_comparator``'s
#: docstring explains why marker geometry, not schematic model naming, is
#: what makes each segment a real device instead of a short.
POR_DIVIDER_RESISTORS = ("XRTOP", "XRBOT", "XRHYS")

#: Poly-to-poly space between adjacent legs of a folded divider resistor's
#: serpentine. The DRM minimum (``PL.3a``) is 0.24 um; 1.0 um is ordinary
#: poly-resistor practice.
DIVIDER_LEG_SPACE_UM = 1.0
#: Unmarked Poly2 cap length at each folded resistor's two open (contacted)
#: ends. Kept outside the RES_MK/SAB/Resistor(62,0) body so the deck's own
#: "terminal = Poly2 minus the recognised body" derivation
#: (klayout_tools.decks.gf180mcu's "Drawn resistors" note) finds a real,
#: unmarked cap there for the contact to land on, instead of more body.
DIVIDER_CAP_UM = 0.8
#: Horizontal gap between the divider's three independently-folded strings.
DIVIDER_STRING_GAP_UM = 6.0
#: Baseline y for every string's bottom (open) end -- clear of the VSS rail.
DIVIDER_BASE_Y_UM = -3.5

#: The high-sheet-rho selector, spelled locally for the divider's own code
#: (klayout_tools.decks.gf180mcu, "Drawn resistors"): ``RES_MK`` is the deck's
#: resistor-candidate marker, required for every recognised flavour, and
#: ``SAB`` (salicide block) plus this ``Resistor`` ID layer together select the
#: ``ppolyf_u_1k`` class specifically. All three are the module-level layer
#: constants at the top of this file -- this is an alias, not a second
#: definition. ``Pplus`` is neither required nor excluded for that flavour
#: (unlike the base ``ppolyf_u``), so the divider deliberately does not draw it.
DIVIDER_RESISTOR_MK = RESISTOR_ID


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


def _divider_resistor_lengths() -> tuple[float, dict[str, float]]:
    """``(leg_width_um, {name: r_length_um})`` for the sense divider's three
    segments, read straight from the golden netlist.
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
        # fail here rather than draw a structure that no longer matches the
        # plan.
        raise ValueError(f"sense divider legs are not one width: {sorted(widths)}")
    leg_w = widths.pop()
    lengths = {name: lvsref.to_um(card["r_length"]) for name, card in cards.items()}
    return leg_w, lengths


def _resistor_leg_plan(length_um: float, leg_w: float) -> tuple[int, float, float]:
    """``(legs, leg_len_um, tail_extra_um)`` folding ``length_um`` of a
    ``leg_w``-wide poly resistor into a roughly square zig-zag serpentine
    whose drawn body AREA -- and so the resistance KLayout's native resistor
    extractor computes (``area / width * sheet_rho``, confirmed directly
    against ``klt`` for this exact construction) -- reconstructs
    ``length_um`` at ``leg_w`` to within floating-point noise, not merely
    approximately: every dimension below is chosen as an exact multiple of
    the layout's own 1 nm grid (``DBU_UM``) so no rounding remainder can
    accumulate across the (potentially several dozen) legs a long, thin
    schematic resistor folds into.

    All ``legs`` parallel Poly2 legs share one uniform ``leg_len_um``, joined
    by ``legs - 1`` same-width turns that alternate top/bottom -- each turn
    bridges only the ``DIVIDER_LEG_SPACE_UM`` gap between two adjacent legs
    (touching, not overlapping, either leg's own footprint), contributing
    exactly ``DIVIDER_LEG_SPACE_UM`` to the total electrical length -- except
    the *last* leg, which is ``tail_extra_um`` taller than the rest: the one
    place the exact-nanometre integer division below can leave a remainder
    (at most ``legs`` nm), folded entirely into the one leg whose far end is
    already an open (unjogged) terminal, so it costs nothing but a few
    nanometres of that leg's own length -- not a second, misaligned turn.
    An odd leg count keeps the string's two open ends on opposite sides
    (see :func:`_resistor_string`), convenient for wiring one to each of two
    different nets without doubling back.
    """
    nm = round(1.0 / DBU_UM)  # DBU per micrometre (1000, i.e. a 1 nm grid)
    length_nm = round(length_um * nm)
    space_nm = round(DIVIDER_LEG_SPACE_UM * nm)
    cap_nm = round(DIVIDER_CAP_UM * nm)

    pitch_um = leg_w + DIVIDER_LEG_SPACE_UM
    target_leg_len_um = max(leg_w, math.sqrt(length_um * pitch_um))
    legs = max(1, round(length_um / (target_leg_len_um + DIVIDER_LEG_SPACE_UM)))
    if legs % 2 == 0:
        legs += 1

    # legs * leg_len + tail_extra - 2 * CAP + (legs - 1) * SPACE == length_um
    # (see _resistor_string's marked-area accounting), solved exactly in
    # integer nanometres so the identity holds bit-for-bit, not just to
    # floating-point tolerance.
    budget_nm = length_nm + 2 * cap_nm - (legs - 1) * space_nm
    leg_len_nm = budget_nm // legs
    tail_extra_nm = budget_nm - leg_len_nm * legs  # 0 <= tail_extra_nm < legs
    return legs, leg_len_nm / nm, tail_extra_nm / nm


def _resistor_string(
    b: CellBuilder,
    x0: float,
    y0: float,
    *,
    leg_w: float,
    legs: int,
    leg_len: float,
    tail_extra: float,
) -> dict[str, tuple[float, float] | float]:
    """Draw one folded, RES_MK/SAB/Resistor(62,0)-marked poly resistor:
    ``legs`` parallel Poly2 legs of width ``leg_w`` at
    ``leg_w + DIVIDER_LEG_SPACE_UM`` pitch, starting at ``(x0, y0)``, joined
    by same-width turns alternating top/bottom (an ordinary zig-zag
    serpentine) -- see :func:`_resistor_leg_plan` for why ``legs`` is odd,
    every leg but the last shares one uniform ``leg_len``, and the marked
    body's area exactly reconstructs the segment's schematic length. Each
    leg is fully marked except a :data:`DIVIDER_CAP_UM` unmarked cap at the
    string's two open (leg 0's bottom, the last leg's top) ends, where a
    contact lands.

    Returns ``{"a": (x, y), "b": (x, y), "x0", "y0", "x1", "y1"}``: the two
    open ends' own contact points (for wiring) and the drawn bounding box.
    """
    pitch = leg_w + DIVIDER_LEG_SPACE_UM
    y1 = y0 + leg_len  # shared top for every leg except the last
    x1 = x0 + (legs - 1) * pitch + leg_w
    last_top = y1 + tail_extra

    for i in range(legs):
        lx0 = x0 + i * pitch
        lx1 = lx0 + leg_w
        leg_top = last_top if i == legs - 1 else y1
        b.box(POLY2, lx0, y0, lx1, leg_top)
        mark_y0 = y0 + DIVIDER_CAP_UM if i == 0 else y0
        mark_y1 = leg_top - DIVIDER_CAP_UM if i == legs - 1 else leg_top
        for spec in (SAB, RES_MK, DIVIDER_RESISTOR_MK):
            b.box(spec, lx0, mark_y0, lx1, mark_y1)

    for i in range(legs - 1):
        lx0 = x0 + i * pitch
        gx0, gx1 = lx0 + leg_w, lx0 + pitch
        gy0, gy1 = (y1 - leg_w, y1) if i % 2 == 0 else (y0, y0 + leg_w)
        b.box(POLY2, gx0, gy0, gx1, gy1)
        for spec in (SAB, RES_MK, DIVIDER_RESISTOR_MK):
            b.box(spec, gx0, gy0, gx1, gy1)

    def terminal(cy0: float, cy1: float, cx: float) -> tuple[float, float]:
        mid = (cy0 + cy1) / 2.0
        b.box(METAL1, cx - leg_w / 2.0, cy0, cx + leg_w / 2.0, cy1)
        b.contact(cx, mid)
        return (cx, mid)

    a_point = terminal(y0, y0 + DIVIDER_CAP_UM, x0 + leg_w / 2.0)
    b_point = terminal(last_top - DIVIDER_CAP_UM, last_top, x1 - leg_w / 2.0)

    return {"a": a_point, "b": b_point, "x0": x0, "y0": y0, "x1": x1, "y1": last_top}


def por_comparator(b: CellBuilder) -> None:
    """``por_comparator`` (``design/por_comparator.sch``): 18 MOS devices plus
    the 3-segment sense divider, all drawn and all in the compare (#91).

    **The sense divider is now drawn for real.** ``XRTOP``/``XRBOT``/``XRHYS``
    are ``ppolyf_u_3k`` poly resistors in the schematic. ``klt 0.1.0``'s
    extraction deck recognises a drawn, RES_MK/SAB-marked poly resistor as a
    real two-terminal device (klayout-tools#219/#222) -- but only two flavours
    of gf180mcu's high-sheet-rho poly family are wired: the base ``ppolyf_u``
    (350 ohm/sq) and the PDK's own default ``ppolyf_u_1k`` (1000 ohm/sq,
    klayout-tools#299). ``_2k``/``_3k`` remain **deliberately unmodelled**
    (#299's "Non-goals": all three flavours are the *same* drawn geometry,
    selected only by a build-time ``POLY_RES`` option no drawn layer
    distinguishes, so wiring one is the PDK's own default, not a guess).
    Filed as a fresh friction issue since the design now actually needs the
    ``_3k`` flavour: klayout-tools#323.

    So each segment is drawn with ``RES_MK``/``SAB``/``Resistor(62,0))`` --
    exactly what a real ``ppolyf_u_3k`` resistor's geometry would carry too,
    since the three flavours are geometrically identical -- and extracts as
    the deck's ``ppolyf_u_1k`` class. ``layout/lvs_reference.py``'s
    ``RESISTOR_CLASS`` therefore compares each segment's *drawn* W/L against
    the deck's modelled 1000 ohm/sq, not the schematic's 3000 ohm/sq: a
    **documented, deliberate fidelity loss**, in the same spirit as the
    NMOS/PMOS body-net rewrites below. It is still a meaningful check for
    *this* divider specifically: all three segments are the same poly flavour
    and width, so the sheet-rho substitution is a common factor across all
    three -- the check still proves each segment's drawn length (so its
    resistance *ratio* against the other two, which is what the hysteresis
    ratio actually depends on -- design/por_comparator.md, "Why the
    hysteresis is a resistor ratio") is exactly what the schematic asks for.
    What it does not prove is the *absolute* resistance at the schematic's
    true 3000 ohm/sq corner; that remains ``sim/``'s claim, unchanged.

    Each segment folds into a roughly-square zig-zag serpentine
    (:func:`_resistor_leg_plan`/:func:`_resistor_string`) whose drawn body
    AREA reconstructs the schematic's own ``r_length`` exactly (to
    floating-point noise, not merely approximately -- the two functions'
    docstrings explain why that identity is load-bearing for LVS, not
    cosmetic), so no dimension here is retyped from the golden netlist.

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
      and ordinary serpentine folding for area -- exactly what
      :func:`_resistor_leg_plan`'s fold is computed from. No end-of-string
      dummy legs are drawn (a layout-quality nicety, not a tool limit or an
      LVS requirement -- unlike #295's MOS matched-pair dummies, a resistor
      leg needs no contact to serve its process-matching purpose, so this is
      simply out of scope for this bring-up pass).
    * The load mirror ``XMLA``/``XMLB`` gets the same ordinary matched-pair
      practice (adjacent, same orientation, one well) although the floorplan
      names no plan for it.

    **Structure** -- same two-layer scheme as ``bias_core``: horizontal Poly2
    tracks, vertical Metal1 risers, Metal1-only by necessity (the extraction
    deck still declares one metal level at ``klt 0.1.0``)::

        +--- guard ring: COMP + Metal1, VSS-tied, continuous, contacts 1um ----+
        |  VDD rail (Metal1)                                                   |
        |  ..... routing channel: one Poly2 track per signal net .....         |
        |  [ PMOS row, one Nwell ]  [ NMOS row ]  [inv] [ 3 folded resistors ] |
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

    # --- sense divider: 3 independently-folded, RES_MK/SAB/Resistor(62,0)
    # marked poly resistors (#91), side by side starting past the inverter.
    div_leg_w, div_lengths = _divider_resistor_lengths()
    div_terms: dict[str, dict] = {}
    cursor_x = inv_x1 + 6.0
    for name in POR_DIVIDER_RESISTORS:
        legs, leg_len, tail_extra = _resistor_leg_plan(div_lengths[name], div_leg_w)
        div_terms[name] = _resistor_string(
            b,
            cursor_x,
            DIVIDER_BASE_Y_UM,
            leg_w=div_leg_w,
            legs=legs,
            leg_len=leg_len,
            tail_extra=tail_extra,
        )
        cursor_x = div_terms[name]["x1"] + DIVIDER_STRING_GAP_UM
    div_x1 = max(term["x1"] for term in div_terms.values())
    div_y1 = max(term["y1"] for term in div_terms.values())

    clear = GUARD_RING_CLEAR_UM + GUARD_RING_W_UM
    gx0 = p_x0 - 1.0 - clear
    # div_x1/div_y1 carry the divider's own exact-nanometre fractional
    # remainder (see _resistor_leg_plan); round the guard ring's outer edges
    # that derive from them up to the nearest 0.5 um (same snapping
    # convention the old reserved-footprint helper used) so the guard ring's
    # own `_span`-placed contacts land on round, DBU-safe centres.
    gx1 = math.ceil((div_x1 + clear) * 2.0) / 2.0
    gy0 = min(vss_y0, DIVIDER_BASE_Y_UM) - clear
    gy1 = math.ceil((max(vdd_y1, div_y1) + clear) * 2.0) / 2.0

    riser = _make_riser(b, vdd_y1, vss_y0, track_y)

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
    # Every track reaches only as far as the device row / inverter needs (the
    # default `row_x1 + 1.0` fallback below); SNS/SNSB deliberately do NOT
    # reach the divider on Poly2 -- see the Metal2 escape immediately after
    # this loop for why and what replaces it. The instanced inverter's two
    # nets still get their own short custom reach.
    #
    # SNS/SNSB do need an explicit reach even so: their track has to run
    # *past* the escape contact's centre, not stop on it. Both used to fall
    # back to `row_x1 + 1.0`, which is exactly `div_trunk_x0` -- the escape
    # contact's own centre x -- so the Poly2 covered only the contact's west
    # half and left its east half bare: two `poly2.enclosing.contact.1`
    # violations (CO.3), one per net, in a cell whose committed report claimed
    # clean (#102). `_poly2_landing_x1` sizes the overhang from the rule, so
    # the enclosure cannot silently go to zero again if the pitch moves.
    div_trunk_x0 = row_x1 + 1.0
    track_x1 = {
        "BIAS_OK": inv_x - 2.6,
        "BIAS_OKB": inv_x + 1.8,
        "SNS": _poly2_landing_x1(div_trunk_x0),
        "SNSB": _poly2_landing_x1(div_trunk_x0),
    }
    for net in POR_COMPARATOR_TRACKS:
        y = track_y[net]
        half_w = TRACK_W_UM / 2.0
        b.box(POLY2, p_x0 - 1.0, y - half_w, track_x1.get(net, row_x1 + 1.0), y + half_w)

    # --- SNS/SNSB: escape onto Metal2 before the divider, not through it ---
    # A Poly2 track spanning the whole divider width (the first cut at this)
    # physically crosses every leg-to-leg gap of all three folded resistor
    # strings, filling each gap with unmarked-but-touching Poly2 and bridging
    # every leg of a string to its neighbours -- a real short, and why
    # extraction saw each string as "one resistor shape" touched by dozens of
    # spurious contacts (#91 debugging). Two Metal1 vertical risers per net
    # (one per resistor terminal, drawn below in "sense divider wiring")
    # cannot be joined by a single Metal1 trunk either: the far terminal's
    # riser for one net and the near terminal's riser for the *other* net
    # both pass through the same track-height band at different x, and a
    # Metal1 trunk long enough to join its own two terminals would cross
    # them -- a same-layer short between SNS and SNSB. Metal2 has no such
    # conflict: nothing else in this cell draws on it, and crossing over a
    # Metal1 riser on a different layer with no via is not a connection.
    def _via1_pad(cx: float, cy: float) -> None:
        b.via(VIA1, cx, cy)
        pad = 0.25
        b.box(METAL2, cx - pad, cy - pad, cx + pad, cy + pad)

    for net in ("SNS", "SNSB"):
        y = track_y[net]
        # One contact just inside where the (now-short) Poly2 track ends -- the
        # track runs on to `_poly2_landing_x1(div_trunk_x0)` so this contact is
        # enclosed on all four sides (see the routing channel above) -- up
        # through a Metal1 landing pad and a Via1, onto Metal2.
        b.contact(div_trunk_x0, y)
        b.box(
            METAL1,
            div_trunk_x0 - RISER_W_UM / 2.0,
            y - RISER_W_UM / 2.0,
            div_trunk_x0 + RISER_W_UM / 2.0,
            y + RISER_W_UM / 2.0,
        )
        _via1_pad(div_trunk_x0, y)
        # The Metal2 trunk itself, all the way across the divider region.
        # Each resistor terminal's own Metal1 riser (below) meets it with its
        # own Via1, not by touching this trunk's Metal1 predecessor.
        b.box(METAL2, div_trunk_x0, y - TRACK_W_UM / 2.0, div_x1, y + TRACK_W_UM / 2.0)

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
    # Each rail reaches only as far as its own divider terminal needs (XRTOP's
    # VDD end / XRHYS's VSS end), NOT all the way to div_x1. A rail spanning
    # the full divider width would cross the *other* two nets' own SNS/SNSB
    # risers -- XRBOT's and XRHYS's far ("b") terminals are well above the
    # rails' own Y-band and travel down through it on their way to the
    # SNS/SNSB Metal2 trunk (see the Metal2 escape above) -- and a Metal1
    # rail is a real short wherever a Metal1 riser passes through its Y-band,
    # regardless of x. This was a real bug here (#91 debugging): both rails
    # used to reach div_x1 and shorted SNS and SNSB to VDD. Stopping each
    # rail just past its own terminal, and nowhere near x=378/434 (XRBOT's
    # and XRHYS's SNS/SNSB risers), removes the crossing entirely.
    b.box(METAL1, gx0 + 2.5, vdd_y0, div_terms["XRTOP"]["x1"] + 1.0, vdd_y1)
    b.box(METAL1, gx0 + 1.0, vss_y0, div_terms["XRHYS"]["a"][0] + 2.0, vss_y1)
    b.box(COMP, gx0 + 2.3, vss_y0, inv_x1 + 1.7, vss_y1)
    for x in _span(gx0 + 2.8, inv_x1 + 1.2, TAP_PITCH_UM):
        b.contact(x, (vss_y0 + vss_y1) / 2.0)

    # --- guard ring: continuous, VSS-tied, contacted at 1 um ----------------
    # Tied to VSS by abutting the VSS rail's left end; no floating segment.
    # This cell sits on the always-on POR domain's side of the block-level
    # domain seam (layout/floorplan.md, "Guard-ring / isolation plan"), whose
    # correctness the deck cannot check -- klayout-tools#303.
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

    # --- sense divider wiring: VDD -[XRTOP]- SNS -[XRBOT]- SNSB -[XRHYS]- VSS
    # (design/netlist/por_comparator.spice's own node order for each card).
    # Each resistor's third (bulk) node needs no drawn connection at all: the
    # deck's bulk_to_substrate resistor extractor ties it to the same
    # synthetic substrate net every NMOS body already lands on (confirmed
    # directly against klt -- see layout/lvs_reference.py's RESISTOR_CLASS).
    divider_ends = {
        "XRTOP": ("SNS", "VDD"),
        "XRBOT": ("SNSB", "SNS"),
        "XRHYS": ("VSS", "SNSB"),
    }
    for name, (net_a, net_b) in divider_ends.items():
        for net, point in ((net_a, div_terms[name]["a"]), (net_b, div_terms[name]["b"])):
            cx, cy = point
            via_needed = net not in ("VDD", "VSS")
            if net == "VDD":
                y_to = vdd_y1
            elif net == "VSS":
                y_to = vss_y0
            else:
                y_to = track_y[net]
            y_lo, y_hi = sorted((cy, y_to))
            # A Via1 (not a Poly2 contact -- see the Metal2 escape above)
            # needs the riser's own Metal1 to extend slightly past the via,
            # same enclosure margin `riser()` uses for its Poly2 contacts.
            if via_needed:
                if y_to >= cy:
                    y_hi += 0.2
                else:
                    y_lo -= 0.2
            b.box(
                METAL1,
                cx - RISER_W_UM / 2.0,
                y_lo,
                cx + RISER_W_UM / 2.0,
                y_hi,
            )
            if via_needed:
                _via1_pad(cx, y_to)

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
    # #93: the two nets the folded-in passives add. NC joins XR1's far end to
    # the eight XQ8 emitters; NZ is XRZ's free end (its other schematic
    # connection is the MiM cap XCC, which stays undrawn -- see temp_core's
    # docstring). Appended rather than inserted so every track above keeps the
    # y it already had.
    "NC",
    "NZ",
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

    def land_via(self, net: str, x_center: float) -> float:
        """Land a Metal2 riser on ``net``'s track; return the track y.

        The passive field (#93) sits beyond the device rows and reaches the
        channel from above on Metal2 rather than on a poly crossunder. That is
        not a style choice: a poly run contacted at both ends is exactly the
        shape klayout-tools#288 flags as an unmodelled resistor body, so
        wiring the *resistors* in on poly would add noise to the one warning
        this cell is trying to read.
        """
        y = self.track_y[net]
        _m1_to_m2(self.b, x_center, y)
        self._reach[net] = max(self._reach[net], x_center + _VIA_PAD_HALF)
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
    """``temp_core`` -- one top cell holding every device the deck can model.

    Until #93 this stream carried **three** top cells: ``temp_core`` (the MOS
    network, the only one ``klt extract``/``klt lvs`` ran on) plus
    ``temp_core_r2_ladder`` and ``temp_core_pnp_array``, drawn as siblings so
    that ``klt drc`` -- which checks every top cell in a stream -- would still
    see them. That split existed for exactly one reason: the curated
    ``gf180mcu`` extraction deck had no resistor or bipolar device class, so a
    drawn poly resistor body extracted as ordinary interconnect and would have
    shorted its own two terminals, merging ``PTAT`` into ``VSS`` through the
    trim ladder.

    klayout-tools#222/#223 removed that reason: with ``SAB``/``RES_MK`` on a
    poly body the deck cuts it out of the connectivity graph and extracts a
    ``ppolyf_u``, and with ``DRC_BJT`` over an emitter it extracts a ``bjt``.
    The ladder and the array are therefore **drawn into this cell**, and the
    sibling top cells are gone -- a sibling is DRC-checked but never extracted
    or compared, so keeping the split would have kept 59 real devices
    permanently outside the only check that could answer for their wiring.

    One device stays out: the MiM cap ``XCC``. See :func:`_temp_core_passives`.
    """
    _temp_core_body(b)


def _temp_core_body(b: CellBuilder) -> None:
    """Everything ``temp_core`` draws, as a plain body with no ``add_cell``.

    Split out for ``temp_por_top`` (#72), which instances *this* into the
    block-level assembly rather than calling :func:`temp_core` -- a cell body
    handed to :meth:`CellBuilder.instance` must not retarget the builder.
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

    _temp_core_passives(b, channel)
    channel.draw()


#: The passive field: the R2 gain ladder and the PNP centroid array, drawn
#: beyond the right end of the device rows and above the routing channel, so
#: every terminal reaches its own channel track by dropping straight down on
#: Metal2. Nothing here is placed by eye relative to the MOS rows: the field
#: starts clear of the widest drawn row and each structure's own extent is
#: derived below.
_FIELD_X0 = 300.0  # right of the device row (which ends at x = 288)
_FIELD_Y0 = 62.0  # above the PMOS row's Nwell (which tops out at 54.5)
_VIA_PAD_HALF = 0.25  # half-size of a Metal1/Metal2 via landing pad
_M2_HALF = 0.22  # half-width of a Metal2 wire (0.44 >= metal2.width.1's 0.28)

#: One drawn ``ppolyf_u`` segment. ``head`` is the unmarked, contacted poly at
#: each end -- the deck takes a resistor's terminals from ``body minus the
#: recognised segment``, so the head *is* the terminal. Exactly **one** contact
#: per head: a poly island touching contact at two or more separate points is
#: what klayout-tools#288's diagnostic reads as an unmodelled resistor body, so
#: a multi-contact head on a resistor the deck *does* model would be a false
#: positive in the one warning this cell needs to stay readable.
_R_PITCH = 3.0
_R_HEAD = 1.0
_R_DUMMY_LEGS = 2  # unmarked, uncontacted edge legs at each end of the bank

#: rank 3's ``pnp_10p00x10p00`` unit emitter, and the 5x5 grid that holds the
#: active 3x3 (``XQ1`` centre + ``XQ8A..XQ8H`` around it) inside a ring of
#: dummy unit cells.
_Q_EMITTER = 10.0
_Q_PITCH = 14.0
_Q_GRID = 5
_Q_GAP = 25.0  # x between the resistor bank and the PNP array


def _m2_h(b: CellBuilder, x0: float, x1: float, y: float) -> None:
    b.box(METAL2, min(x0, x1), y - _M2_HALF, max(x0, x1), y + _M2_HALF)


def _m2_v(b: CellBuilder, x: float, y0: float, y1: float) -> None:
    b.box(METAL2, x - _M2_HALF, min(y0, y1), x + _M2_HALF, max(y0, y1))


def _m1_to_m2(b: CellBuilder, x: float, y: float) -> None:
    """One Via1 with its own landing pad on both levels."""
    half = _VIA_PAD_HALF
    b.box(METAL1, x - half, y - half, x + half, y + half)
    b.box(METAL2, x - half, y - half, x + half, y + half)
    b.via(VIA1, x, y)


def _r_segment(b: CellBuilder, x: float, y: float, width: float, length: float) -> float:
    """One recognised ``ppolyf_u`` body with its two contacted heads.

    Returns the tile's total height. The marker layers overhang the poly in
    ``x`` so the recognised region (``Poly2 & RES_MK & Pplus & SAB``) is
    exactly ``width x length`` -- the extractor computes ``R = L / W * 350``
    from that region and nothing else, so the overhang is what makes the drawn
    resistance equal the one ``lvs_reference.py`` states.
    """
    height = length + 2.0 * _R_HEAD
    b.box(POLY2, x, y, x + width, y + height)
    b.box(PPLUS, x - 0.2, y - 0.2, x + width + 0.2, y + height + 0.2)
    b.box(SAB, x - 0.4, y + _R_HEAD - 0.2, x + width + 0.4, y + _R_HEAD + length + 0.2)
    b.box(RES_MK, x - 0.3, y + _R_HEAD, x + width + 0.3, y + _R_HEAD + length)
    for end in (y + _R_HEAD / 2.0, y + height - _R_HEAD / 2.0):
        b.contact(x + width / 2.0, end)
        b.box(METAL1, x + 0.1, end - 0.4, x + width - 0.1, end + 0.4)
    return height


def _temp_core_passives(b: CellBuilder, channel: _Channel) -> None:
    """The R2 gain ladder and the PNP array, drawn *into* ``temp_core`` (#93).

    Both used to be sibling top cells, DRC-checked but never extracted. They
    are here now because the curated deck grew the two device classes they
    need (klayout-tools#222/#223) and this repo owns the marker geometry that
    turns drawn poly and drawn diffusion into those devices.

    **The MiM cap ``XCC`` is still not drawn**, and that is a deck limit, not
    an oversight. Two independent blockers, either one sufficient:

    * the deck models exactly one MiM device, ``cap_mim_2f0_m4m5_noshield``
      (bottom plate ``Metal4``, top plate ``FuseTop``), while this block's cap
      is the ``m3m4`` flavour the schematic names. Drawing the ``m4m5`` stack
      to make the deck recognise *something* would be drawing a different
      device than the schematic asks for;
    * a recognised MiM's two plate regions are registered as their own
      self-connected nodes and are **not** wired into the deck's
      contact/via/metal connectivity stack, so the extracted cap's terminals
      are anonymous nets no matter what the layout connects them to. A drawn
      ``XCC`` would compare as a capacitor floating between two nets, which
      says less than leaving it out and saying so.

    See ``layout/README.md`` -> "Known deck limits".
    """
    right = _temp_core_resistor_bank(b, channel, _FIELD_X0, _FIELD_Y0)
    _temp_core_pnp_array(b, channel, right + _Q_GAP, _FIELD_Y0)


def _temp_core_resistor_bank(
    b: CellBuilder, channel: _Channel, x0: float, y0: float
) -> float:
    """rank 2's gain-ratio bank: every ``ppolyf_u`` of the golden netlist,
    drawn at its own length, as a series string of straight segments.

    Straight, not serpentine, and that is forced: KLayout's resistor extractor
    solves ``L``/``W`` from the recognised body's own area and perimeter, so a
    folded body extracts a length its corners make wrong. A long resistor is
    therefore a *string* of straight bodies strapped end to end -- ordinary
    PDK resistor-array practice, and the same "describe the device the way the
    deck can see it" move ``lvs_reference.py``'s ``fingers`` field already
    makes for a matched MOS pair.

    Matching, per ``layout/floorplan.md`` rank 2: every segment of every
    resistor is the same drawn **width**, the same flavour, the same
    orientation and the same end geometry, on one uniform pitch, with unmarked
    dummy legs at both ends of the bank. Segment *lengths* differ between
    devices because the netlist's own values are not commensurate -- a
    uniform-length unit tile cannot build this ladder, and drawing one that
    pretends to would be the decorative array this bank replaces.
    """
    devices = lvsref.parse_passives(
        lvsref.subckt_body(
            (REPO_ROOT / "design" / "netlist" / "temp_core.spice").read_text(),
            "temp_core",
        )
    )
    order = lvsref.CELLS["temp_core"]["resistors"]
    width = lvsref.to_um(devices[order[0]]["params"]["r_width"])
    plan = []
    for name in order:
        device = devices[name]
        if lvsref.to_um(device["params"]["r_width"]) != width:
            raise SystemExit(f"{name}: the bank draws one width, not two")
        head, tail, _bulk = device["nodes"]
        plan.append((head, tail, lvsref.resistor_segments(
            lvsref.to_um(device["params"]["r_length"]),
            lvsref.resistor_fold("temp_core"),
        )))
    tallest = max(max(segments) for _h, _t, segments in plan)

    col = 0

    def leg_x(index: int) -> float:
        return x0 + index * _R_PITCH

    for index in range(_R_DUMMY_LEGS):
        # Unmarked and uncontacted: a *marked* dummy would extract as a real
        # ppolyf_u the golden netlist never asked for (klayout-tools#295's gap,
        # met here for resistors), and a contacted unmarked one would be
        # flagged by #288's diagnostic. Uncontacted poly is neither.
        b.box(POLY2, leg_x(index), y0, leg_x(index) + width, y0 + tallest + 2 * _R_HEAD)
        b.box(PPLUS, leg_x(index) - 0.2, y0 - 0.2,
              leg_x(index) + width + 0.2, y0 + tallest + 2 * _R_HEAD + 0.2)
        col += 1

    for head, tail, segments in plan:
        first = col
        for length in segments:
            _r_segment(b, leg_x(col), y0, width, length)
            col += 1
        last = col - 1
        # Alternating end straps: top between an even-indexed pair, bottom
        # between an odd-indexed pair. An even segment count therefore leaves
        # both free ends at the *bottom*, which is what lets both terminals
        # drop straight down to the channel without crossing the string.
        height = segments[0] + 2.0 * _R_HEAD
        for offset in range(len(segments) - 1):
            y = y0 + (height - _R_HEAD / 2.0 if offset % 2 == 0 else _R_HEAD / 2.0)
            left = leg_x(first + offset) + 0.1
            b.box(METAL1, left, y - 0.4, leg_x(first + offset + 1) + width - 0.1, y + 0.4)
        for net, column in ((head, first), (tail, last)):
            x = leg_x(column) + width / 2.0
            _m1_to_m2(b, x, y0 + _R_HEAD / 2.0)
            track_y = channel.land_via(net, x)
            _m2_v(b, x, track_y, y0 + _R_HEAD / 2.0)

    for index in range(_R_DUMMY_LEGS):
        b.box(POLY2, leg_x(col), y0, leg_x(col) + width, y0 + tallest + 2 * _R_HEAD)
        b.box(PPLUS, leg_x(col) - 0.2, y0 - 0.2,
              leg_x(col) + width + 0.2, y0 + tallest + 2 * _R_HEAD + 0.2)
        col += 1
        del index

    return leg_x(col - 1) + width


def _temp_core_pnp_array(b: CellBuilder, channel: _Channel, x0: float, y0: float) -> None:
    """rank 3's vertical-PNP centroid array: ``XQ1`` at the centre of the
    active 3x3, the eight ``XQ8`` units around it, one shared base/collector
    ring construction, and a dummy unit cell on the whole perimeter.

    Only the nine active units carry a ``DRC_BJT`` patch, and each patch is
    scoped to its own emitter rather than blanketing the array. That is what
    makes the extraction match the schematic: the deck derives a bipolar base
    as ``Nwell & DRC_BJT`` and an emitter as ``Comp &`` that base, so a marker
    covering the whole array turns the shared n+ **base ring** into a 26th
    emitter, and marking the sixteen dummies would put sixteen devices in the
    netlist that no golden netlist asked for.
    """
    span = (_Q_GRID - 1) * _Q_PITCH + _Q_EMITTER
    active = range(1, _Q_GRID - 1)

    def cx(col: int) -> float:
        return x0 + col * _Q_PITCH + _Q_EMITTER / 2.0

    def cy(row: int) -> float:
        return y0 + row * _Q_PITCH + _Q_EMITTER / 2.0

    def lane(gap: int) -> float:
        """y of the Metal2 lane in the gap above row ``gap``."""
        return y0 + gap * _Q_PITCH + _Q_EMITTER + (_Q_PITCH - _Q_EMITTER) / 2.0

    for row in range(_Q_GRID):
        for col in range(_Q_GRID):
            x, y = x0 + col * _Q_PITCH, y0 + row * _Q_PITCH
            b.box(COMP, x, y, x + _Q_EMITTER, y + _Q_EMITTER)
            b.box(PPLUS, x - 0.3, y - 0.3, x + _Q_EMITTER + 0.3, y + _Q_EMITTER + 0.3)
            steps = int(_Q_EMITTER - 1.0)
            for i in range(steps):
                for j in range(steps):
                    b.contact(x + 0.5 + i, y + 0.5 + j)
            b.box(METAL1, x + 0.2, y + 0.2, x + _Q_EMITTER - 0.2, y + _Q_EMITTER - 0.2)
            if row in active and col in active:
                # "BJT.3" keeps DRC_BJT 0.1 um clear of unrelated COMP; the
                # 1 um patch margin leaves 3 um to the next unit's diffusion.
                b.box(DRC_BJT, x - 1.0, y - 1.0, x + _Q_EMITTER + 1.0, y + _Q_EMITTER + 1.0)

    def ring(spec, inner: float, width: float) -> None:
        lo, hi = x0 - inner, x0 + span + inner
        blo, bhi = y0 - inner, y0 + span + inner
        b.box(spec, lo, blo, hi, blo + width)
        b.box(spec, lo, bhi - width, hi, bhi)
        b.box(spec, lo, blo, lo + width, bhi)
        b.box(spec, hi - width, blo, hi, bhi)

    def ring_contacts(inner: float, width: float) -> None:
        lo, hi = x0 - inner, x0 + span + inner
        blo, bhi = y0 - inner, y0 + span + inner
        mid = width / 2.0
        for i in range(int((hi - lo) - 1.0)):
            pos = lo + 0.5 + i
            b.contact(pos, blo + mid)
            b.contact(pos, bhi - mid)
        for i in range(int((bhi - blo) - 1.0)):
            pos = blo + 0.5 + i
            b.contact(lo + mid, pos)
            b.contact(hi - mid, pos)

    # Shared base ring (n+ COMP inside the Nwell) ...
    ring(COMP, 4.0, 2.0)
    ring(NPLUS, 4.3, 2.6)
    ring_contacts(4.0, 2.0)
    ring(METAL1, 3.8, 1.6)
    # ... one Nwell holding the whole array and its base ring ...
    b.box(NWELL, x0 - 5.5, y0 - 5.5, x0 + span + 5.5, y0 + span + 5.5)
    # ... and the collector ring (p+ COMP on substrate, outside the Nwell).
    ring(COMP, 10.0, 2.0)
    ring(PPLUS, 10.3, 2.6)
    ring_contacts(10.0, 2.0)
    ring(METAL1, 9.8, 1.6)

    # --- the eight XQ8 emitters, all on NC --------------------------------
    # Every wire below stays out of lane(2), which is XQ1's only way out of
    # the middle of the array; the two lanes NC does use are the ones just
    # outside the active block, joined by one column in the col3/col4 gap.
    low, high = lane(0), lane(_Q_GRID - 2)
    join_x = x0 + (_Q_GRID - 2) * _Q_PITCH + _Q_EMITTER + (_Q_PITCH - _Q_EMITTER) / 2.0
    nc_exit = x0 + span + 14.0
    _m2_h(b, cx(1), nc_exit, low)
    _m2_h(b, cx(1), join_x, high)
    _m2_v(b, join_x, low, high)
    for col in (1, _Q_GRID - 2):
        _m2_v(b, cx(col), low, cy(_Q_GRID - 3))  # rows 1 and 2 of this column
        _m2_v(b, cx(col), cy(_Q_GRID - 2), high)  # row 3
        for row in active:
            _m1_to_m2(b, cx(col), cy(row))
    _m2_v(b, cx(2), low, cy(1))
    _m2_v(b, cx(2), cy(_Q_GRID - 2), high)
    _m1_to_m2(b, cx(2), cy(1))
    _m1_to_m2(b, cx(2), cy(_Q_GRID - 2))
    nc_y = channel.land_via("NC", nc_exit)
    _m2_v(b, nc_exit, nc_y, low)

    # --- XQ1, the centre unit, out through lane(2) on its own -------------
    na_exit = x0 - _Q_GAP / 2.0
    _m1_to_m2(b, cx(2), cy(2))
    _m2_v(b, cx(2), cy(2), lane(2))
    _m2_h(b, na_exit, cx(2), lane(2))
    na_y = channel.land_via("NA", na_exit)
    _m2_v(b, na_exit, na_y, lane(2))

    # --- both rings down to VSS -------------------------------------------
    # The deck cannot check this tie (Nwell is never joined to Contact, so the
    # extracted base stays an anonymous net either way) -- it is drawn because
    # it is right, and layout/README.md records that it is unchecked.
    tie_x = x0 + span - 6.0
    _m1_to_m2(b, tie_x, y0 - 3.0)
    _m1_to_m2(b, tie_x, y0 - 9.0)
    vss_y = channel.land_via("VSS", tie_x)
    _m2_v(b, tie_x, vss_y, y0 - 3.0)


# --------------------------------------------------------------------------- #
# temp_por_top -- the block-level assembly (#72)
# --------------------------------------------------------------------------- #
#
# Routing regime. layout/floorplan.md's "Routing / metal-level note" recorded
# that the installed klt 0.1.0's gf180mcu EXTRACTION_DECK declared
# ``metals=((34, 0),)`` -- Metal1 only -- and committed the floorplan to a
# single-metal regime "until the local klt install is upgraded past
# klayout-tools#238", with an explicit instruction to re-check before assuming
# the limit still applies. Re-checked for this cell:
#
#     $ klt --version
#     klt 0.1.0
#     >>> EXTRACTION_DECK.metals
#     ((34, 0), (36, 0), (42, 0), (46, 0), (81, 0))
#     >>> EXTRACTION_DECK.vias
#     ((35, 0), (38, 0), (40, 0), (41, 0))
#
# klayout-tools#238's full Metal1-Metal5 / Via1-Via4 stack **is** in the
# installed build, and the DRC deck carries metal2/metal3 width+space rules
# (they showed as `rules_skipped` before only because no stream drew those
# layers). The single-metal constraint is therefore lifted, and this assembly
# uses it: every sub-circuit below stays Metal1-only and byte-identical, and
# *only* this cell routes on Metal2/Metal3.
#
# That is not a convenience. Four independently laid-out cells plus rails have
# nets that must cross, and in a one-metal regime every crossing is either a
# poly crossunder (a resistor-shaped poly shape the deck absorbs into
# interconnect) or a break in a guard ring. Routing above Metal1 means **no
# guard ring in this cell has a single notch in it** -- the four columns that
# cross the domain-seam moat (IBIAS and RESETn/EN, plus the VSS and POR-domain
# VDD risers) cross *over* it on Metal3, short and direct, none of them drawn
# on the Metal1/COMP the moat itself is made of, so it stays unbroken end to
# end.
#
# Discipline, held by the build-time checks at the bottom of ``temp_por_top``
# rather than by convention: Metal2 runs horizontally, Metal3 vertically, one
# Metal2 trunk per crossing net at its own y, one Metal3 column per pin escape
# at its own x. Nothing in this cell is drawn on Metal1 except the two guard
# rings.

#: Where each sub-circuit's own origin lands in the assembled block, in the
#: order the floorplan sketch reads: ``temp_core`` alone on top (the
#: temp-sensor domain), then the always-on POR domain left to right below the
#: seam with ``bias_core`` at its seam-facing left edge.
#:
#: ``por_output_chain``'s ``dx`` moved 820 -> 920 for #97: #91 grew
#: ``por_comparator`` from its #69-era 313 um-wide placeholder to a real
#: 445.0 um (``-5.5..439.5`` local, landing at absolute x 444.5..889.5 at its
#: own ``dx=450``), which ate all 57 um of the original gap to
#: ``por_output_chain`` at ``dx=820`` (absolute left 814.5) and then some --
#: a 75 um instance-boundary overlap that DRC'd dirty at 92 violations
#: (``contact.space.1`` x79, ``poly2.enclosing.contact.1`` x9 of them at the
#: overlap -- the other 2 are ``por_comparator``'s own pre-existing,
#: independent divider-contact violations, tracked separately in #102/#103,
#: not a placement defect -- and ``contact.width.1`` x2). ``bias_core``'s own
#: #90 growth (to 434.9 um wide) still clears ``por_comparator``'s left edge
#: at ``dx=450`` with a 15.1 um gap, so that boundary needed no change. The
#: new ``dx=920`` reopens a clean ~25 um gap past ``por_comparator``'s grown
#: right edge (889.5 -> instance left 914.5), confirmed DRC-clean at the
#: instance boundary by sweeping the gap from 0 to 105 um past the old value
#: and taking a point with comfortable margin on both sides (90-105 um all
#: verified clean of placement-collision violations) rather than the
#: narrowest value that merely stops complaining. This only widens the gap
#: between ``por_comparator`` and ``por_output_chain``; every other adjacency
#: floorplan.md's ranked plan asks for (``temp_core`` alone above the seam,
#: ``bias_core`` at the POR row's seam-facing left edge, ``por_output_chain``
#: at the row's ``RESETn``-facing right edge) is unchanged.
TOP_PLACEMENT = (
    ("temp_core", "temp_por_top_temp_core", 0.0, 0.0),
    ("bias_core", "temp_por_top_bias_core", 0.0, -400.0),
    ("por_comparator", "temp_por_top_por_comparator", 450.0, -400.0),
    ("por_output_chain", "temp_por_top_por_output_chain", 920.0, -400.0),
)

#: Which pin of which instance each crossing net has to reach. Names are the
#: sub-circuit's own pin labels; ``temp_core``'s ``EN`` is the ratified
#: top-level ``RESETn`` (``design/netlist/temp_por_top.spice``:
#: ``xtemp VDD VSS IBIAS RESETn PTAT CTAT temp_core``).
TOP_NET_PINS = {
    "VDD": (
        ("temp_core", "VDD"),
        ("bias_core", "VDD"),
        ("por_comparator", "VDD"),
        ("por_output_chain", "VDD"),
    ),
    "VSS": (
        ("temp_core", "VSS"),
        ("bias_core", "VSS"),
        ("por_comparator", "VSS"),
        ("por_output_chain", "VSS"),
    ),
    "IBIAS": (
        ("temp_core", "IBIAS"),
        ("bias_core", "IBIAS"),
        ("por_comparator", "IBIAS"),
        ("por_output_chain", "IBIAS"),
    ),
    "VREF": (("bias_core", "VREF"), ("por_comparator", "VREF")),
    "BIAS_OK": (("bias_core", "BIAS_OK"), ("por_comparator", "BIAS_OK")),
    "POR_RAW": (("por_comparator", "POR_RAW"), ("por_output_chain", "POR_RAW")),
    "RESETn": (("por_output_chain", "RESETn"), ("temp_core", "EN")),
}

#: y of each crossing net's own horizontal Metal2 trunk, in the open band
#: between the POR row's bottom (-409.7) and the VSS rail. ``VSS`` has none:
#: its trunk *is* the bottom rail, which is also the guard-ring tie net
#: (``layout/floorplan.md`` -> "Pin placement").
TOP_TRUNK_Y = {
    "POR_RAW": -420.0,
    "BIAS_OK": -425.0,
    "RESETn": -430.0,
    "VREF": -435.0,
    "IBIAS": -440.0,
    "VDD": -445.0,
}

#: Left-margin Metal3 columns, clear in x of both domains and of the seam
#: moat's taps. ``temp_core``'s four crossing pins reach the POR domain and
#: the rails through here rather than through either domain's footprint. All
#: of these x's sit inside the moat's own x-span, so every column whose two
#: endpoints straddle :data:`TOP_SEAM_Y` -- ``VSS``, ``RESETn``, ``IBIAS``,
#: and the ``VDD_POR`` riser -- passes *over* the moat on Metal3 (``VDD``,
#: which reaches the top rail, is the one that does not). None is drawn on
#: Metal1/COMP, so none of them notches it.
TOP_MARGIN_X = {
    "VSS": -48.0,
    "VDD": -52.0,
    "RESETn": -56.0,
    "IBIAS": -60.0,
    "VDD_POR": -64.0,
}

#: Where the domain-seam moat is strapped down to the VSS rail. Three ties,
#: spread across its length: the moat is one continuous shape, so one tie is
#: electrically sufficient -- the other two exist so a single broken via
#: cannot silently float the whole seam (which no automated check in this flow
#: would catch; see ``layout/README.md`` -> "Known deck limits"). Unchanged by
#: #97's ``por_output_chain`` move: 960 still sits comfortably inside the
#: widened seam (``TOP_SEAM_X1`` is now 1188) and clear of every escape
#: column ``_top_escape_columns`` allocates near the shifted instance (the
#: nearest, ``POR_RAW``'s, lands at x = 980.45 -- 20+ um away, verified by
#: rebuilding with the new placement).
TOP_SEAM_TIE_X = (-68.0, 420.0, 960.0)

TOP_WIRE_W = 0.44  # Metal2/Metal3 route width (>= metal2/3.width.1's 0.28)
TOP_PAD_HALF = 0.22  # half-size of a Metal2/Metal3 via landing pad
TOP_ESCAPE_PITCH = 1.5  # minimum x between two Metal3 pin-escape columns
TOP_RING_W = 4.0  # guard-ring / moat COMP+Metal1 width
TOP_RAIL_HALF = 2.0  # half-height of the VDD rail
TOP_VSS_RAIL_HALF = 1.5  # half-height of the VSS rail (inside the ring)

#: The outer perimeter guard ring, and the VDD/VSS rails it frames. The top
#: edge moved out from y = 114 to y = 254 when #93 folded ``temp_core``'s
#: passives into the cell: the resistor bank and the PNP array stand above the
#: device rows, so the temp-sensor domain is ~125 um taller than it was. The
#: right edge moved out from x = 1094 to x = 1194 for #97, the same +100 um
#: as ``por_output_chain``'s ``dx`` above, so the ring/rail keep the same
#: margin past that instance's grown-gap right edge that they held before.
#: Every other edge, and the whole POR domain floor, is untouched.
TOP_PERIM = (-140.0, -540.0, 1194.0, 254.0)
TOP_RAIL_X0, TOP_RAIL_X1 = -134.0, 1188.0
TOP_VDD_RAIL_Y = 240.0
TOP_VSS_RAIL_Y = -538.0

#: The domain-seam moat: one continuous VSS-tied p-substrate strip along the
#: full seam between the two domains, unbroken (see the module comment above
#: on why it needs no notch). ``TOP_SEAM_X1`` moves with ``TOP_RAIL_X1`` (#97)
#: so the moat still reaches the same margin past the perimeter ring's right
#: segment that it did before ``por_output_chain`` moved.
TOP_SEAM_Y = -108.0
TOP_SEAM_X0, TOP_SEAM_X1 = -134.0, 1188.0

#: ``PTAT``/``CTAT`` leave ``temp_core`` westward on their own Metal2 tracks
#: and stop here, just inside the perimeter ring's left segment.
TOP_LEFT_PAD_X = -120.0
#: ``RESETn``'s pad, just inside the perimeter ring's right segment. Moves
#: with ``TOP_RAIL_X1``/``TOP_PERIM`` (#97) to keep the same 8 um margin
#: inside the rail edge.
TOP_RIGHT_PAD_X = 1180.0

#: The ratified 5-pad pinout, in ``design/netlist/temp_por_top.spice``'s own
#: ``.subckt temp_por_top`` order. ``design/netlist.py --check`` asserts this
#: at the schematic level; ``layout/lvs_reference.py``'s ``temp_por_top``
#: manifest asserts the layout's extracted pin set against the same source.
TOP_PINOUT = ("VDD", "VSS", "PTAT", "CTAT", "RESETn")


class _TopRoutes:
    """Every rectangle ``temp_por_top`` draws itself, tagged with its net.

    Exists for the check at the end of :func:`temp_por_top`. Two same-layer
    rectangles on *different* nets that overlap are an electrical short that
    ``klt drc`` cannot see (two overlapping shapes merge into one legal
    polygon -- no width or spacing rule is broken) and that a reviewer reading
    a floorplan will not see either. In a cell whose whole job is to join four
    already-clean blocks, that is the failure mode worth a mechanical guard,
    so the guard is here and it raises.
    """

    #: layer -> (name, minimum spacing between different nets, um). Thresholds
    #: are the curated deck's own (``metal1.space.1`` 0.23, ``metal2.space.1``
    #: and ``metal3.space.1`` 0.28); via layers have no deck rule, so they are
    #: checked for overlap only.
    LIMITS = {
        METAL1: ("Metal1", 0.23),
        METAL2: ("Metal2", 0.28),
        METAL3: ("Metal3", 0.28),
        VIA1: ("Via1", 0.0),
        VIA2: ("Via2", 0.0),
    }

    def __init__(self, builder: CellBuilder) -> None:
        self.b = builder
        self.rects: list[tuple[tuple[int, int], str, tuple[float, ...]]] = []

    def box(self, spec, net: str, x0: float, y0: float, x1: float, y1: float) -> None:
        self.b.box(spec, x0, y0, x1, y1)
        if spec in self.LIMITS:
            self.rects.append((spec, net, (x0, y0, x1, y1)))

    def hwire(self, net: str, y: float, x0: float, x1: float, spec=METAL2) -> None:
        half = TOP_WIRE_W / 2.0
        self.box(spec, net, min(x0, x1), y - half, max(x0, x1), y + half)

    def vwire(self, net: str, x: float, y0: float, y1: float, spec=METAL3) -> None:
        half = TOP_WIRE_W / 2.0
        self.box(spec, net, x - half, min(y0, y1), x + half, max(y0, y1))

    def pad(self, spec, net: str, x: float, y: float) -> None:
        h = TOP_PAD_HALF
        self.box(spec, net, x - h, y - h, x + h, y + h)

    def via1(self, net: str, x: float, y: float) -> None:
        """A Via1 onto an instance's own Metal1 pin strap, with its Metal2 pad.

        The Metal1 side is the sub-circuit's -- untouched, and already at
        least 0.30 um across at every pin label
        (:meth:`CellBuilder.labels_in`), so a 0.26 um via lands inside it.
        """
        self.box(VIA1, net, x - VIA_SIDE_UM / 2.0, y - VIA_SIDE_UM / 2.0,
                 x + VIA_SIDE_UM / 2.0, y + VIA_SIDE_UM / 2.0)
        self.pad(METAL2, net, x, y)

    def via2(self, net: str, x: float, y: float) -> None:
        """A Via2 with a landing pad on both of its levels."""
        self.box(VIA2, net, x - VIA_SIDE_UM / 2.0, y - VIA_SIDE_UM / 2.0,
                 x + VIA_SIDE_UM / 2.0, y + VIA_SIDE_UM / 2.0)
        self.pad(METAL2, net, x, y)
        self.pad(METAL3, net, x, y)

    #: Which layers a via may bridge, bottom to top. Two rectangles on the
    #: same layer, or on two adjacent entries of this stack, are electrically
    #: one shape where they overlap.
    STACK = (METAL1, VIA1, METAL2, VIA2, METAL3)

    @staticmethod
    def _gap(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        return max(max(a[0] - b[2], b[0] - a[2]), max(a[1] - b[3], b[1] - a[3]))

    def check(self) -> None:
        """Raise unless this cell's own shapes realise exactly its own nets.

        Three properties, all mechanical, none of them things ``klt drc`` or
        ``klt lvs`` can establish here:

        1. **No short.** Two same-layer rectangles on different nets never
           overlap, and never sit closer than the deck's own spacing rule.
           Overlap in particular is invisible to DRC -- two overlapping shapes
           merge into one perfectly legal polygon.
        2. **No via bridges two nets.** Following the via stack, every
           connected group of rectangles carries exactly one net name.
        3. **Every net is one piece.** Each net this cell draws forms exactly
           one connected group -- so the domain-seam moat and the perimeter
           ring are *continuous*, and *are* on ``VSS`` along with the bottom
           rail, rather than being a shape that merely looks like a ring in a
           plot. This is the guard-ring claim klayout-tools#303 records the
           deck cannot make (no tap or well-label layer, and no continuity
           check: a floating or broken ring compares clean), made here
           instead, at build time, from the geometry.
        """
        problems: list[str] = []
        for index, (spec, net, rect) in enumerate(self.rects):
            name, limit = self.LIMITS[spec]
            for other_spec, other_net, other in self.rects[index + 1 :]:
                if other_spec != spec or other_net == net:
                    continue
                gap = self._gap(rect, other)
                if gap < limit - 1e-9:
                    kind = "SHORT" if gap < 0 else f"spacing {gap:.3f} < {limit}"
                    problems.append(
                        f"{name} {kind}: {net} {rect} vs {other_net} {other}"
                    )

        parent = list(range(len(self.rects)))

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        level = {spec: index for index, spec in enumerate(self.STACK)}
        for index, (spec, _net, rect) in enumerate(self.rects):
            for offset, (other_spec, _other_net, other) in enumerate(
                self.rects[index + 1 :]
            ):
                if abs(level[spec] - level[other_spec]) > 1:
                    continue
                if self._gap(rect, other) < -1e-9:
                    parent[find(index)] = find(index + 1 + offset)

        groups: dict[int, set[str]] = {}
        nets: dict[str, set[int]] = {}
        for index, (_spec, net, _rect) in enumerate(self.rects):
            root = find(index)
            groups.setdefault(root, set()).add(net)
            nets.setdefault(net, set()).add(root)
        for members in groups.values():
            if len(members) > 1:
                problems.append(
                    "one connected group carries more than one net: "
                    + ", ".join(sorted(members))
                )
        for net, roots in sorted(nets.items()):
            if len(roots) > 1:
                problems.append(
                    f"net {net} is drawn as {len(roots)} disconnected pieces"
                )

        if problems:
            raise AssertionError(
                "temp_por_top routing does not realise its own nets:\n  "
                + "\n  ".join(problems[:20])
            )


def _top_escape_columns(pins: list[dict]) -> None:
    """Give each pin its own Metal3 column, as near its own x as possible.

    Two pins whose Metal3 escapes would overlap in y (``bias_core``'s ``VDD``
    and ``VSS`` labels share an x, as do ``por_output_chain``'s ``VDD``,
    ``VSS`` and ``RESETn``) get pushed apart in ``TOP_ESCAPE_PITCH`` steps.
    Deterministic: ``pins`` arrives in a fixed order and only ever moves right.
    """
    placed: list[tuple[float, float, float]] = []
    for pin in pins:
        low, high = sorted((pin["py"], pin["ty"]))
        x = pin["px"]
        while any(
            abs(x - other_x) < TOP_ESCAPE_PITCH - 1e-9
            and not (high < other_low - 1e-9 or low > other_high + 1e-9)
            for other_x, other_low, other_high in placed
        ):
            x += TOP_ESCAPE_PITCH
        placed.append((x, low, high))
        pin["xe"] = x


def _top_escape(
    routes: _TopRoutes, net: str, px: float, py: float, xe: float, ty: float
) -> None:
    """Route one instance pin onto its net's trunk.

    Metal1 pin strap -> Via1 -> Metal2 jog along the pin's own y out to the
    escape column -> Via2 -> Metal3 down (or up) the column -> Via2 onto the
    Metal2 trunk. This is the only shape this cell ever makes: everything that
    crosses between instances is one of these plus one horizontal trunk.
    """
    routes.via1(net, px, py)
    routes.hwire(net, py, px, xe)
    routes.via2(net, xe, py)
    routes.vwire(net, xe, py, ty)
    routes.via2(net, xe, ty)


def _guard_ring_segments(
    x0: float, y0: float, x1: float, y1: float
) -> tuple[tuple[float, float, float, float], ...]:
    """The four overlapping rectangles of a guard ring: bottom, top, left, right."""
    return (
        (x0, y0, x1, y0 + TOP_RING_W),
        (x0, y1 - TOP_RING_W, x1, y1),
        (x0, y0, x0 + TOP_RING_W, y1),
        (x1 - TOP_RING_W, y0, x1, y1),
    )


def _top_guard_ring(routes: _TopRoutes, x0: float, y0: float, x1: float, y1: float) -> None:
    """A closed COMP+Metal1 p-substrate guard ring, contacted at 1 um.

    Asserts it actually closed. ``_TopRoutes.check``'s connectivity pass
    cannot do this one: a ring is redundant by construction, so a ring with a
    single break in one segment is still one connected shape and still lands
    on ``VSS``. What distinguishes the two is topology -- a closed ring is an
    annulus (one polygon with exactly one hole), a broken one is simply
    connected -- so that is what is checked. Nothing in ``klt``'s curated
    deck checks it: no tap or well-label layer, and no ring-continuity rule,
    so a broken *or* floating ring compares clean on both ``klt drc`` and
    ``klt lvs`` (filed generically as klayout-tools#303).
    """
    import klayout.db as kdb

    segments = _guard_ring_segments(x0, y0, x1, y1)
    for rect in segments:
        routes.box(COMP, "VSS", *rect)
        routes.box(METAL1, "VSS", *rect)

    closed = kdb.Region()
    for rect in segments:
        closed.insert(kdb.DBox(*rect).to_itype(routes.b.layout.dbu))
    closed.merge()
    if closed.count() != 1 or closed.holes().count() != 1:
        raise AssertionError(
            f"guard ring ({x0}, {y0})-({x1}, {y1}) is not a closed annulus: "
            f"{closed.count()} polygon(s), {closed.holes().count()} hole(s)"
        )
    half = TOP_RING_W / 2.0
    for x in _span(x0 + half, x1 - half, TAP_PITCH_UM):
        routes.b.contact(x, y0 + half)
        routes.b.contact(x, y1 - half)
    for y in _span(y0 + TOP_RING_W + half, y1 - TOP_RING_W - half, TAP_PITCH_UM):
        routes.b.contact(x0 + half, y)
        routes.b.contact(x1 - half, y)


def temp_por_top(b: CellBuilder) -> None:
    """The block-level assembly (#72): the four sub-circuits, wired.

    Instances ``bias_core`` (#68), ``por_comparator`` (#69),
    ``por_output_chain`` (#70) and ``temp_core``'s MOS network (#71)
    **unmodified** -- every one of those cells' own committed GDS is still
    byte-reproducible from the same function this cell calls, so this assembly
    inherits each of their already-recorded DRC/LVS results rather than
    re-litigating them -- and adds exactly four things:

    1. the two guard rings (domain-seam moat + outer perimeter),
    2. the ``VDD``/``VSS`` rails,
    3. one Metal2 trunk per net that crosses between instances,
    4. the ratified 5-pad pinout (:data:`TOP_PINOUT`).

    **Floorplan** (``layout/floorplan.md`` -> "Block-level floorplan sketch"),
    as realised in :data:`TOP_PLACEMENT`:

    - ``temp_core`` alone above the seam (the temp-sensor domain), its pin
      column facing the ``PTAT``/``CTAT`` pads on the left edge.
    - ``bias_core``, ``por_comparator``, ``por_output_chain`` below it (the
      always-on POR domain), left to right, with ``bias_core`` at the
      domain's seam-facing left edge -- it is what both domains consume, so
      the two shared-net feedthroughs (``IBIAS`` up to ``temp_core``;
      ``IBIAS``/``VREF``/``BIAS_OK`` rightward inside the POR domain) start
      there -- and ``por_output_chain`` at the right edge, beside ``RESETn``.
    - ``VDD`` and ``VSS`` are full-width rails at the top and bottom. Each
      domain taps each rail on its own riser: ``temp_core`` through the left
      margin, the POR row through its own trunk. No domain's supply is
      daisy-chained through the other.
    - The domain-seam moat is one continuous, unbroken, VSS-tied strip along
      the whole seam. Four Metal3 columns in the left margin cross *over* it,
      all within the moat's own x-span: two signals (``IBIAS``, and
      ``RESETn``/``EN``) and two supplies (``VSS`` down to the bottom rail,
      and the POR domain's own ``VDD`` riser up to the top rail).
      ``temp_core``'s ``VDD`` tap is the only left-margin column that does not
      cross, since the top rail is on its own side of the seam. What matters
      for isolation is not the *count* of crossings but that none of them is
      drawn on Metal1/COMP, where the moat lives: every crossing is a Metal3
      wire passing over an unbroken ring, so the moat needs no notch anywhere
      -- which is what ``layout/floorplan.md``'s isolation plan asks for, and
      what the single-metal "one feedthrough through a notch" plan only
      approximated. ``IBIAS`` remains the only *bias* net the floorplan lets
      cross into the temp-sensor domain (``VREF``/``BIAS_OK`` stay
      POR-domain-internal).

    **DR-010's shared-``IBIAS`` contract at the layout level.**
    ``por_output_chain``'s ungated ``XMBD`` is what defines the shared
    ``IBIAS`` node's operating point (see the decision record, and #41's fix).
    Here ``IBIAS`` is one Metal2 trunk that every consumer taps from --
    ``bias_core``'s ``XMPIB`` source, ``por_comparator``'s ``XMBD``,
    ``por_output_chain``'s ``XMBD``, ``temp_core``'s ``XMBD`` -- with no
    series element, switch or gated segment anywhere on it, so no floorplan or
    routing choice here can let a disabled consumer clamp it: the layout
    reproduces the schematic's single shared node exactly, and the LVS compare
    against ``design/netlist/temp_por_top.spice`` is what holds it there.

    **What is checked and what is not.** ``bash layout/run_checks.sh
    temp_por_top`` gives DRC clean, LVS match on the drawn device set, and
    both negative controls detected. It does **not** check the guard rings: the
    curated ``gf180mcu`` deck has no tap or well-label layer, so a ring left
    floating, tied to the wrong net, or physically broken compares clean --
    both defects were built and confirmed clean, and the tool gap is filed
    generically as klayout-tools#303 (**not** #281, which is closed and whose
    resolution, #285's ``device.body_unverified`` warning, says nothing about
    a ring). Two things stand in for that here, and both are mechanical
    rather than a claim in prose: :func:`_top_guard_ring` cannot draw a gap
    (four overlapping rectangles, no gap parameter), and the block-time checks
    at the end of this function assert every Via1/Via2 lands inside metal on
    both sides and that no two different-net shapes this cell draws overlap.
    What remains a design-review claim is the same one every cell in this repo
    carries: that VSS is the right net to tie them to.

    Device coverage: this cell inherits every one of the four sub-circuits'
    drawn devices unchanged, extraction being flat -- ``temp_core``'s PNP
    array and R2 gain ladder (#93), ``por_output_chain``'s two MiM caps and
    its ``XMRLK`` release latch (#92, issue #56), ``por_comparator``'s sense
    divider (#91) and ``bias_core``'s PNPs/resistors/MiM caps (#90), reunited
    with the rest of this assembly by #97's floorplan re-derivation. What
    still is not drawn anywhere in the four sub-circuits -- only
    ``temp_core``'s own MiM cap -- is still outside this compare too (see
    ``layout/lvs_reference.py``'s ``temp_por_top`` manifest, and
    ``layout/README.md`` -> "Known deck limits" for what that leaves
    unproven).
    """
    routes = _TopRoutes(b)

    # --- the four sub-circuits, placed --------------------------------------
    bodies = {
        "temp_core": _temp_core_body,
        "bias_core": bias_core,
        "por_comparator": por_comparator,
        "por_output_chain": por_output_chain,
    }
    anchors: dict[str, dict[str, tuple[float, float]]] = {}
    for cell_name, inst_name, dx, dy in TOP_PLACEMENT:
        child = b.instance(inst_name, bodies[cell_name], dx, dy)
        # A pin label is a point inside a Metal1 shape on that net. Where a
        # sub-circuit carries more than one label for a net (por_comparator's
        # VDD/VSS: one on its own rail, one inside the instanced BIAS_OKB
        # inverter), the first in sorted order is its own rail -- the strap
        # this assembly should land on, not the sub-instance's.
        anchors[cell_name] = {
            net: (points[0][0] + dx, points[0][1] + dy)
            for net, points in b.labels_in(child).items()
        }

    # --- pin escapes: Metal1 pin -> Metal2 pad -> Metal3 column -> trunk -----
    pins: list[dict] = []
    for net in sorted(TOP_NET_PINS):
        for cell_name, pin_name in TOP_NET_PINS[net]:
            px, py = anchors[cell_name][pin_name]
            if cell_name == "temp_core":
                # temp_core reaches everything through the left margin, on its
                # own y, so its escape column is fixed rather than allocated.
                continue
            pins.append(
                {
                    "net": net,
                    "cell": cell_name,
                    "px": px,
                    "py": py,
                    "ty": TOP_VSS_RAIL_Y if net == "VSS" else TOP_TRUNK_Y[net],
                }
            )
    _top_escape_columns(pins)

    trunk_x: dict[str, list[float]] = {net: [] for net in TOP_NET_PINS}
    for pin in pins:
        _top_escape(routes, pin["net"], pin["px"], pin["py"], pin["xe"], pin["ty"])
        trunk_x[pin["net"]].append(pin["xe"])

    # --- temp_core's own escapes, up the left margin ------------------------
    for net, pin_name in (
        ("VSS", "VSS"),
        ("VDD", "VDD"),
        ("RESETn", "EN"),
        ("IBIAS", "IBIAS"),
    ):
        px, py = anchors["temp_core"][pin_name]
        xe = TOP_MARGIN_X[net]
        if net == "VSS":
            ty = TOP_VSS_RAIL_Y
        elif net == "VDD":
            ty = TOP_VDD_RAIL_Y  # temp_core taps the top rail directly
        else:
            ty = TOP_TRUNK_Y[net]
        _top_escape(routes, net, px, py, xe, ty)
        if net not in ("VSS", "VDD"):
            trunk_x[net].append(xe)

    # --- the crossing nets' trunks -----------------------------------------
    for net, y in TOP_TRUNK_Y.items():
        xs = trunk_x[net]
        if net == "VDD":
            xs = xs + [TOP_MARGIN_X["VDD_POR"]]
        if net == "RESETn":
            xs = xs + [TOP_RIGHT_PAD_X]
        routes.hwire(net, y, min(xs), max(xs))

    # --- VDD / VSS: full-width top and bottom rails -------------------------
    routes.box(
        METAL2,
        "VDD",
        TOP_RAIL_X0,
        TOP_VDD_RAIL_Y - TOP_RAIL_HALF,
        TOP_RAIL_X1,
        TOP_VDD_RAIL_Y + TOP_RAIL_HALF,
    )
    routes.box(
        METAL2,
        "VSS",
        TOP_RAIL_X0,
        TOP_VSS_RAIL_Y - TOP_VSS_RAIL_HALF,
        TOP_RAIL_X1,
        TOP_VSS_RAIL_Y + TOP_VSS_RAIL_HALF,
    )
    # The POR domain's own VDD riser: rail -> trunk, in the left margin, not
    # through either domain's footprint.
    riser_x = TOP_MARGIN_X["VDD_POR"]
    routes.vwire("VDD", riser_x, TOP_TRUNK_Y["VDD"], TOP_VDD_RAIL_Y)
    for y in (TOP_TRUNK_Y["VDD"], TOP_VDD_RAIL_Y):
        routes.via2("VDD", riser_x, y)

    # --- guard rings: the outer perimeter, and the domain-seam moat ---------
    _top_guard_ring(routes, *TOP_PERIM)
    routes.box(
        COMP,
        "VSS",
        TOP_SEAM_X0,
        TOP_SEAM_Y - TOP_RING_W / 2.0,
        TOP_SEAM_X1,
        TOP_SEAM_Y + TOP_RING_W / 2.0,
    )
    routes.box(
        METAL1,
        "VSS",
        TOP_SEAM_X0,
        TOP_SEAM_Y - TOP_RING_W / 2.0,
        TOP_SEAM_X1,
        TOP_SEAM_Y + TOP_RING_W / 2.0,
    )
    for x in _span(TOP_SEAM_X0 + 1.0, TOP_SEAM_X1 - 1.0, TAP_PITCH_UM):
        b.contact(x, TOP_SEAM_Y)

    # The perimeter ring is tied to VSS by the bottom rail running along its
    # own bottom segment on Metal2, stitched down at a regular pitch; the seam
    # moat is tied by three risers to the same rail. VSS is therefore the
    # guard-ring tie net by construction, exactly as layout/floorplan.md's pin
    # table says ("VSS ... also the guard-ring tie net").
    for x in _span(TOP_RAIL_X0 + 5.0, TOP_RAIL_X1 - 5.0, 25.0):
        routes.via1("VSS", x, TOP_VSS_RAIL_Y)
    for x in TOP_SEAM_TIE_X:
        routes.via1("VSS", x, TOP_SEAM_Y)
        routes.via2("VSS", x, TOP_SEAM_Y)
        routes.vwire("VSS", x, TOP_SEAM_Y, TOP_VSS_RAIL_Y)
        routes.via2("VSS", x, TOP_VSS_RAIL_Y)

    # --- the ratified 5-pad pinout -----------------------------------------
    # PTAT/CTAT leave temp_core westward on their own Metal2 tracks to the
    # left edge; RESETn's pad is the right end of its own trunk. VDD/VSS are
    # labelled on their rails. These five Metal2 labels are the *only* labels
    # drawn directly in this cell, which is what `top_cell_pins` turns into
    # exactly this pin set (klayout-tools#291) -- every sub-circuit's own
    # labels stay below the top cell and stay internal.
    for pad_net in ("CTAT", "PTAT"):
        px, py = anchors["temp_core"][pad_net]
        routes.via1(pad_net, px, py)
        routes.hwire(pad_net, py, TOP_LEFT_PAD_X, px)
        b.label(pad_net, TOP_LEFT_PAD_X + 1.0, py, METAL2_LABEL)
    b.label("RESETn", TOP_RIGHT_PAD_X, TOP_TRUNK_Y["RESETn"], METAL2_LABEL)
    b.label("VDD", 0.0, TOP_VDD_RAIL_Y, METAL2_LABEL)
    b.label("VSS", 0.0, TOP_VSS_RAIL_Y, METAL2_LABEL)

    # --- build-time checks (see this function's docstring) ------------------
    routes.check()
    _top_assert_connected(b)


def _top_assert_connected(b: CellBuilder) -> None:
    """Every via this cell drew lands inside metal on both of its levels.

    A via drawn a hair off its landing pad costs nothing in DRC (the curated
    deck has no via rule at all) and produces an open, not a short -- which
    LVS *does* catch, but only as an unexplained topology mismatch a long way
    from its cause. Checking it here turns that into a build-time failure that
    names the layer.
    """
    import klayout.db as kdb

    top = b.cell
    layers = {
        spec: kdb.Region(top.begin_shapes_rec(b._layer(spec))).merged()
        for spec in (METAL1, METAL2, METAL3, VIA1, VIA2)
    }
    for via, below, above in ((VIA1, METAL1, METAL2), (VIA2, METAL2, METAL3)):
        for level in (below, above):
            stranded = layers[via] - layers[level]
            if not stranded.is_empty():
                raise AssertionError(
                    f"temp_por_top: {stranded.count()} via shape(s) on "
                    f"{via} are not covered by {level}"
                )


#: cell name -> body. Add a cell here and it joins ``layout/run_checks.sh``.
CELLS = {
    "bias_core": bias_core,
    "por_comparator": por_comparator,
    "por_comparator_bias_okb_inv": por_comparator_bias_okb_inv,
    "temp_core": temp_core,
    "por_output_chain": por_output_chain,
    "temp_por_top": temp_por_top,
}


def build(name: str, out_dir: Path) -> Path:
    builder = CellBuilder(name)
    CELLS[name](builder)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.gds"
    builder.write(path)
    return path


def run(check: bool, only: str | None) -> int:
    names = [only] if only else sorted(CELLS)
    for name in names:
        if name not in CELLS:
            print(f"unknown cell {name!r} (have: {', '.join(sorted(CELLS))})")
            return 2

    if not check:
        for name in names:
            # A frozen cell's committed stream is pinned (see
            # lvs_reference.FROZEN_CELLS); a whole-repo regeneration must not
            # silently overwrite it and break the pin. Naming it explicitly
            # with --cell still rebuilds it -- that is the tracking issue's own
            # workflow.
            if name in lvsref.FROZEN_CELLS and only is None:
                issue = lvsref.FROZEN_CELLS[name]["issue"]
                print(
                    f"skip {name}.gds  (frozen for {issue}; "
                    f"pass --cell {name} to rebuild it anyway)"
                )
                continue
            path = build(name, CELLS_DIR)
            print(
                f"wrote {path.relative_to(REPO_ROOT)}  "
                f"sha256={lvsref.sha256_bytes(path.read_bytes())[:16]}"
            )
        return 0

    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            committed = CELLS_DIR / f"{name}.gds"
            # Frozen cells are held against their pinned committed digest
            # rather than against a rebuild -- deferring that rebuild is
            # exactly what the freeze is for. `frozen_check` returns None for
            # every other cell, which falls through to the normal compare.
            frozen = lvsref.frozen_check(name, "gds", committed)
            if frozen is not None:
                if frozen.ok:
                    print(frozen.line)
                else:
                    failures.append(frozen.line)
                continue
            fresh = build(name, Path(tmp))
            if not committed.exists():
                failures.append(f"{name}: not committed (run without --check)")
                continue
            fresh_sha256 = lvsref.sha256_bytes(fresh.read_bytes())
            committed_sha256 = lvsref.sha256_bytes(committed.read_bytes())
            if fresh_sha256 != committed_sha256:
                failures.append(
                    f"{name}: committed GDS is stale "
                    f"(committed {committed_sha256[:16]}, "
                    f"rebuilt {fresh_sha256[:16]})"
                )
            else:
                print(f"ok {name}.gds  sha256={committed_sha256[:16]}")

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
