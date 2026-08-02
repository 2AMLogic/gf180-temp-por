#!/usr/bin/env python3
"""Derive ``klt lvs`` reference netlists from the golden ``design/netlist/*.spice``.

    python3 layout/lvs_reference.py            # regenerate layout/cells/*.reference.spice
    python3 layout/lvs_reference.py --check    # verify committed references are current
    python3 layout/lvs_reference.py --cell por_comparator_bias_okb_inv
    python3 layout/lvs_reference.py --cell <name> --corrupt device-param -o /tmp/bad.spice
    python3 layout/lvs_reference.py --check-deck-hash  # committed drc.json all one deck?

stdlib only; no PDK, no klayout, no ngspice.

Why this exists
---------------
``klt lvs``'s reference side must be in KLayout's **schematic-equivalent,
plain-element** form (``M1 d g s b nfet L=0.5U W=1U``). ``design/netlist.py``
exports the **ngspice simulation** form, where a gf180mcu device is a subcircuit
call (``XMENP d g s b pfet_03v3 L=0.5u W=2u nf=1 ...``). Handing the simulation
form to ``klt lvs`` does not error -- ``NetlistSpiceReader`` reads each ``X``
card as an instance of an undefined subcircuit, the circuit collapses toward one
merged net, and the compare reports net/topology mismatches that read like a
layout bug. So the transform below is mandatory, and it is done here, once,
mechanically, from the committed golden netlist rather than by hand-typing device
sizes into a second copy of the truth.

Two deck-imposed rewrites happen alongside the form change, both forced by
documented limits of ``klt``'s curated ``gf180mcu`` extraction deck (see
``layout/README.md`` -> "Known deck limits"):

* **NMOS body** -- the deck draws no substrate/pwell tap layer, so every
  extracted NMOS body lands on the global substrate net. The schematic's body
  node (``VSS``) is rewritten to that global net.
* **PMOS body** -- the deck has no tap layer or well-label layer for gf180mcu,
  so an extracted Nwell is an anonymous net carrying only the body terminals
  inside it. The schematic's body node (``VDD``) is rewritten to a per-well net
  named by the manifest, connected to nothing else.

Three further rewrites apply to the non-MOS device classes the deck now models
-- the drawn MiM capacitor (``caps``), the drawn poly resistor (``resistors``)
and the drawn vertical bipolar (``bipolars``) in the manifest below:

* **MiM plates** -- ``klt``'s extraction registers a recognised capacitor's two
  plate regions as their own self-connected connectivity nodes, *not* as part
  of the deck's metal/via stack (``CapacitorDevice``'s own documented "Known
  limitation"), and the top plate's layer (``FuseTop``) is not in that stack at
  all. So however the plates are wired in the drawn layout, each extracts as an
  isolated two-terminal net pair. The schematic's plate nodes are rewritten to
  per-instance isolated nets named after them (``XCDG.NDG`` / ``XCDG.VSS``), so
  the loss is visible on the face of the reference netlist rather than implied.
  Filed generically as klayout-tools#314.
* **Bipolar base and collector** -- the deck recognises a vertical bipolar as
  ``Nwell`` ∩ ``DRC_BJT`` (base) with a ``Comp`` emitter inside it and *no
  drawn collector*: the collector is the substrate, so it lands on the same
  global substrate net every NMOS body does. The base is the drawn Nwell, and
  gf180mcu's curated deck has no well-label or tap layer, so that well is an
  anonymous net exactly as the PMOS bodies' well is. The schematic's collector
  node is therefore rewritten to the substrate global and its base node to the
  manifest's ``bjt_well`` net -- so a clean compare proves the emitter's
  connectivity and both devices' drawn areas, **not** that the base is tied to
  the rail the schematic puts it on.
* **Poly resistor sheet resistance and folding** -- see :data:`RESISTOR_CLASS`
  and :func:`resistor_segments`: for the high-rho family the deck models the
  PDK's ``POLY_RES='1k'`` default only, and a resistor drawn as a string of
  legs extracts as one device per leg.

All of these are *deliberate fidelity loss*: they make the reference describe
what the deck can actually see. A clean LVS here therefore proves device count,
device sizing, MiM plate area (hence capacitance), drawn resistor and bipolar
geometry, and signal-net topology -- **not** that wells and substrate are
correctly tied, and **not** what either MiM plate is connected to. Filed
upstream as tool friction; tracked in ``layout/README.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

LAYOUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAYOUT_DIR.parent
NETLIST_DIR = REPO_ROOT / "design" / "netlist"
CELLS_DIR = LAYOUT_DIR / "cells"
REPORTS_DIR = LAYOUT_DIR / "reports"

#: Cells whose committed ``layout/reports/<cell>/drc.json`` is allowed to lag
#: the rest on deck version because the cell itself is intentionally frozen
#: (see that cell's own section in ``layout/README.md``). Today this is only
#: ``temp_por_top``, held behind #97 (its assembly is re-derived once, after
#: the sub-cell device work lands, rather than four times); remove an entry
#: once its issue lands and its reports are regenerated against the shared
#: deck like every other cell's.
FROZEN_DECK_CELLS = {"temp_por_top"}

#: The deck ties every extracted NMOS body to this global net.
SUBSTRATE_NET = "vsubs"

#: gf180mcu PDK device subcircuit -> the curated deck's device class. The deck
#: draws one generic ``nfet``/``pfet`` class per polarity with no voltage-flavor
#: distinction, so every ``*_03v3`` core device maps onto the same pair.
DEVICE_CLASS = {
    "nfet_03v3": ("M", "nfet"),
    "pfet_03v3": ("M", "pfet"),
}

#: gf180mcu PDK MiM-capacitor subcircuit -> the curated deck's device class.
#:
#: The mapping is not the identity, and the difference is load-bearing. The
#: schematics instantiate the PDK's **4-metal-level** MiM (``..._m3m4_...``,
#: bottom plate on metal 3); ``klt``'s curated deck transcribes only the DRM's
#: "10.4.2 MIM Option B" **5-metal-level** stack (``..._m4m5_...``, bottom plate
#: on Metal4/``FuseTop`` top plate) and declares no other MiM device class, so
#: that is the only variant a drawn cell can be recognised as. Both are the same
#: 2.0 fF/um^2 device with the same drawn plate geometry -- only the metal pair
#: the stack sits on differs -- so the extracted capacitance is unaffected, but
#: the *stack level* the layout draws is the deck's, not the schematic's. Filed
#: generically as klayout-tools#315 (``layout/README.md`` -> "Known deck limits").
CAP_CLASS = {"cap_mim_2f0_m3m4_noshield": "cap_mim_2f0_m4m5_noshield"}

#: Capacitance per square micrometre of MiM plate *overlap*, in Farads --
#: ``klt``'s curated ``gf180mcu`` deck's own ``area_cap_f_um2`` for
#: ``cap_mim_2f0_m4m5_noshield`` (2.0 fF/um^2, the PDK's own default
#: ``MIM_CAP='2'`` density, and the ``2f0`` in the device name). This module is
#: stdlib-only by design (no PDK, no klayout, no klt import), so the number is
#: transcribed here with its provenance rather than read out of the deck; the
#: extracted capacitance is ``plate overlap area * this``, so a wrong value here
#: shows up immediately as a ``device.property`` LVS mismatch, not as silence.
MIM_AREA_CAP_F_UM2 = 2.0e-15

#: gf180mcu PDK resistor subcircuit -> (extracted device class, sheet rho in
#: ohms per square). One table for **both** poly-resistor families this block
#: draws, because both extract through the same deck device and differ only in
#: the two numbers here:
#:
#: * ``ppolyf_u`` -- the plain unsalicided p+ poly resistor (``Poly2`` +
#:   ``SAB`` + ``RES_MK``, no ``Resistor`` high-rho ID layer). 350 ohm/square
#:   is the curated deck's own value, transcribed there from the PDK's
#:   ``res_extraction.lvs`` / ``gf180mcuD.tech``.
#: * ``ppolyf_u_3k`` -> ``ppolyf_u_1k`` -- the high-sheet-rho family (the same
#:   stack *plus* the ``Resistor`` ID layer). Here the mapping is not the
#:   identity, and the difference is load-bearing: ``_1k``/``_2k``/``_3k`` are
#:   one geometrically identical drawn device that the official LVS runset
#:   resolves through a **deck-level** ``POLY_RES`` option rather than through
#:   any drawn geometry, and ``klt``'s curated deck models only the PDK's own
#:   default for that option (``POLY_RES='1k'``, confirmed by open_pdks' own
#:   variant string "2fF MiM + 1k high sheet rho poly"). So the *drawn* device
#:   is the schematic's, at the schematic's own ``r_width``/``r_length``; only
#:   the sheet resistance the deck attributes to it is the PDK default rather
#:   than the 3k option -- a deliberate fidelity loss in the same spirit as the
#:   NMOS/PMOS body rewrites above. Known and documented in
#:   klayout-tools#299's own non-goals and filed as klayout-tools#323;
#:   ``layout/README.md`` -> "Known deck limits" carries it.
#:
#: This module imports neither ``klt`` nor the PDK, so both sheet rhos are
#: transcribed here with their provenance for the same reason
#: :data:`MIM_AREA_CAP_F_UM2` is. The reference has to state the same
#: resistance the extractor computes from the drawn geometry
#: (``R = rho * L / W``), so a wrong value fails LVS loudly rather than
#: silently.
#:
#: What is deliberately **not** here is how a cell *draws* the thing. Both
#: schematic models are drawn both ways in this block (``bias_core`` strings
#: its ``ppolyf_u_3k`` resistors, ``por_comparator`` serpentines them), so the
#: drawn style is a per-cell layout decision and lives in that cell's own
#: manifest entry as :data:`ResistorFold` -- see :func:`resistor_segments`.
RESISTOR_CLASS = {
    "ppolyf_u": ("ppolyf_u", 350.0),
    "ppolyf_u_3k": ("ppolyf_u_1k", 1000.0),
}


class ResistorFold(NamedTuple):
    """How one cell cuts a long drawn resistor into *recognised bodies*.

    ``klt`` recognises a resistor body as the marker-covered part of the poly
    and solves its ``L``/``W`` from that region's own area and perimeter, which
    leaves a cell two honest ways to draw a resistor far longer than it is
    wide, and this block uses both:

    * ``style="string"`` -- a series string of straight marked segments
      strapped end to end, which extracts as **one device per segment**. The
      strapping nodes are anonymous. ``max_um`` is the hard ceiling on one
      segment (it is what bounds the drawn bank's height) and ``target_um`` is
      the length the split aims for when several counts are legal; ``None``
      means "as long as the ceiling allows", i.e. the fewest segments.
    * ``style="serpentine"`` -- one continuous marked body zig-zagged, which
      extracts as **one device** whose area alone reconstructs the schematic's
      ``r_length`` (``build_cells.py``'s ``_resistor_leg_plan`` draws it and
      owns the corner bookkeeping that makes the area come out exact).

    Either way :func:`resistor_segments` returns the drawn bodies' lengths and
    the reference emits one card each, so the two sides cannot disagree about
    how many devices the layout contains.
    """

    style: str = "string"
    max_um: float = 120.0
    target_um: float | None = None


#: The fold a cell gets when its manifest entry names no ``resistor_fold``.
#: 120 um is ``temp_core``'s rank-2 bank, the first one drawn.
DEFAULT_RESISTOR_FOLD = ResistorFold()

#: The extraction deck recognises one generic ``bjt`` class off the DRM's
#: ``DRC_BJT`` mark layer -- it models no Nplus/Pplus implant, so it cannot
#: tell an NPN from a PNP and does not try (see the deck's own note). The
#: PDK's device name carries the drawn emitter window, which is what fixes the
#: ``AE``/``PE`` the reference declares, so it is read from the name rather
#: than retyped: ``pnp_10p00x10p00`` -> 10.00 x 10.00 um. A schematic that
#: swaps to a different emitter size therefore moves the drawn geometry and the
#: declared parameters together.
BIPOLAR_CLASS = "bjt"
BIPOLAR_NAME_RE = re.compile(r"^(?:npn|pnp)_(\d+)p(\d+)x(\d+)p(\d+)$")

#: How far the drawn ``DRC_BJT`` mark extends beyond the emitter window on every
#: side, in um. The deck's bipolar base region is ``Nwell`` ∩ ``DRC_BJT``, so
#: this margin is exactly what fixes the extracted ``AB``/``PB`` (and, with no
#: drawn collector layer, ``AC``/``PC``). It lives here rather than in
#: ``build_cells.py`` because it is a *device* dimension, not a floorplan one:
#: it has to stay small enough that two neighbouring marks in an array never
#: merge (which would give both devices one shared base region) and large enough
#: to clear the deck's ``bjt.separation.comp.1`` against the array's well tap.
BIPOLAR_BASE_MARGIN_UM = 1.5

#: Layout cell -> how to build its reference netlist from a golden netlist.
#:
#: ``devices`` is in emission order and fixes ``M1``, ``M2``, ... numbering.
#: ``ports`` must match the layout's own extracted pin set (a labelled Metal1
#: net becomes a pin; the substrate net is always one). ``internal`` declares
#: the cell's remaining nets -- unlabelled in the layout, so anonymous in the
#: extracted netlist and matched by topology alone, but still spelled out here
#: so the undeclared-net guard below stays a real check rather than a rubber
#: stamp. ``wells`` groups the PMOS devices that share one drawn Nwell onto one
#: body net. ``caps`` (optional) lists the drawn MiM capacitors, in emission
#: order; their plate nets are synthesized per instance rather than declared,
#: because the deck cannot connect a recognised capacitor's plates to anything
#: (see :func:`cap_plate_nets`).
#:
#: The two remaining drawn classes follow the same pattern. ``resistors`` and
#: ``bipolars`` (both optional) list the cell's poly resistors and vertical
#: bipolars in emission order; ``bjt_well`` names the one drawn Nwell every
#: bipolar's base lands on (anonymous in the extraction, exactly like
#: ``wells``); ``resistor_fold`` (optional, default :data:`DEFAULT_RESISTOR_FOLD`)
#: is how that cell draws a long resistor -- serpentined into one body, or cut
#: into a string of legs at its own ceiling/target (:func:`resistor_segments`).
#: Every
#: card of every class is numbered in one emission sequence, MOS first, so the
#: MOS-only negative controls below can always assume ``cards[0]``/``cards[1]``.
#:
#: ``devices[0]`` and ``devices[1]`` must not share a source net: the
#: ``topology`` negative control re-ties the first device's source to the
#: second's, and if they already agree the "corrupted" reference is identical
#: to the clean one and the control silently stops controlling anything.
CELLS = {
    "por_comparator_bias_okb_inv": {
        "source": "por_comparator.spice",
        "subckt": "por_comparator",
        # design/por_comparator.md, device table: "MENP / MENN -- local
        # inverter producing BIAS_OKB".
        "devices": ["XMENN", "XMENP"],
        "ports": ["BIAS_OK", "BIAS_OKB", "VDD", "VSS", SUBSTRATE_NET],
        "wells": {"NW1": ["XMENP"]},
    },
    "por_comparator": {
        "source": "por_comparator.spice",
        "subckt": "por_comparator",
        # Every MOS device in design/por_comparator.sch -- 6 pfet + 12 nfet.
        # XMENN/XMENP lead so the topology control has two different sources to
        # work with (see the note above CELLS); they are also the pair the
        # por_comparator_bias_okb_inv sub-cell instance contributes, so the
        # control's defect lands inside the instanced geometry rather than in
        # the parent row.
        #
        # The cell's other three devices -- the sense divider XRTOP/XRBOT/
        # XRHYS (schematic ``ppolyf_u_3k`` poly resistors) -- are drawn for
        # real as of #91 (RES_MK/SAB/Resistor(62,0) marker geometry; see
        # layout/build_cells.py's por_comparator docstring) and extract as
        # the curated deck's ``ppolyf_u_1k`` class (the deck wires only the
        # base + ``_1k`` sheet-rho flavors, not ``_3k`` -- see
        # RESISTOR_CLASS's ``ppolyf_u_3k`` entry above). Their reference
        # cards are listed separately below, in the manifest's own
        # "resistors" key (folded, per that same entry's third element -- see
        # build_passive_cards).
        "devices": [
            "XMENN",
            "XMENP",
            "XMLA",
            "XMLB",
            "XMENSRC",
            "XMI1P",
            "XMI2P",
            "XMINA",
            "XMINB",
            "XMTAIL",
            "XMBD",
            "XMPASS",
            "XMDNB",
            "XMDIB",
            "XMHSW",
            "XMDCMPO",
            "XMI1N",
            "XMI2N",
        ],
        "ports": [
            "BIAS_OK",
            # BIAS_OKB is an internal node of the schematic, but the reused
            # por_comparator_bias_okb_inv sub-cell carries its own Metal1
            # "BIAS_OKB" label, which flattens into this cell and names the net
            # -- and a named top-level net becomes a pin. Declared here so the
            # compare stays exact rather than being papered over by deleting a
            # label from the already-proven sub-cell.
            "BIAS_OKB",
            "IBIAS",
            "POR_RAW",
            "VDD",
            "VREF",
            "VSS",
            SUBSTRATE_NET,
        ],
        # SNS and SNSB are the sense divider's taps -- internal nets, unlabeled
        # in the layout, matched by topology alone: each now has two device
        # terminals (one MOS -- XMINA's gate / XMHSW's drain -- and one
        # resistor terminal, per the schematic's own node order below) instead
        # of one, now that the divider is drawn for real (#91).
        "internal": ["NBG", "SNS", "SNSB", "N1", "TN", "NA", "CMPO", "VDDA"],
        # Two drawn Nwells: one holds the parent cell's whole PMOS row, the
        # other is the one inside the instanced por_comparator_bias_okb_inv.
        "wells": {
            "NW1": ["XMLA", "XMLB", "XMENSRC", "XMI1P", "XMI2P"],
            "NW2": ["XMENP"],
        },
        # design/netlist/por_comparator.spice's own node order for each card
        # (VDD end first, design/por_comparator.md "Sense divider"): XRTOP
        # SNS VDD VSS, XRBOT SNSB SNS VSS, XRHYS VSS SNSB VSS. The third
        # (bulk) node is always rewritten to SUBSTRATE_NET by
        # build_passive_cards regardless of what the schematic names there.
        "resistors": ["XRTOP", "XRBOT", "XRHYS"],
        # ...each drawn as one continuous serpentined body rather than a
        # string of separate ones, so each is a single extracted device (#91;
        # build_cells.py's _resistor_leg_plan owns the corner bookkeeping that
        # makes the marked area reconstruct r_length exactly).
        "resistor_fold": ResistorFold(style="serpentine"),
    },
    "bias_core": {
        "source": "bias_core.spice",
        "subckt": "bias_core",
        # Every MOS device in design/bias_core.sch -- 16 pfet + 18 nfet. The
        # cell's other 16 devices are drawn and compared too, as of #90: the 10
        # vertical PNPs in `bipolars`, the 4 poly resistors in `resistors`
        # (folded, so 24 drawn legs) and the 2 MiM caps in `caps` below.
        "devices": [
            # XMBN/XMP1 lead so the topology control has two different sources
            # to work with (see the note above CELLS).
            "XMBN",
            "XMP1",
            "XMP2",
            "XMP3",
            "XMPBN",
            "XMBP",
            "XMPIB",
            "XMPT",
            "XMI1",
            "XMI2",
            "XMS2P",
            "XKA",
            "XMPOK",
            "XMOKA",
            "XMOKB",
            "XMOK2P",
            "XMO1P",
            "XMBN2",
            "XML1",
            "XML2",
            "XMS2N",
            "XKS0",
            "XKS1",
            "XKS2",
            "XKS3",
            "XKS4",
            "XKAN",
            "XKPD",
            "XKICK",
            "XMOL1",
            "XMOL2",
            "XMOKC",
            "XMOK2",
            "XMO1N",
        ],
        # The 10 vertical PNPs, in emission order. XQ1 is the 1x leg and
        # XQ8A..H the 8x leg of the emitter-ratio pair; the layout draws them
        # as a 3x3 common-centroid array with XQ1 at the centre. XQR is the
        # VREF branch's own 1x device.
        "bipolars": ["XQ1", "XQ8A", "XQ8B", "XQ8C", "XQ8D", "XQ8E", "XQ8F",
                     "XQ8G", "XQ8H", "XQR"],
        # The Nwell every drawn PNP's base lands on. All ten share one drawn
        # well (their bases are one node in the schematic), and gf180mcu's
        # curated deck has no well-label layer, so it is anonymous in the
        # extraction and matched by topology -- exactly like `wells` below.
        "bjt_well": "NWQ",
        # The 4 poly resistors, in emission order. Each is drawn as a folded
        # string, so each contributes `resistor_segments()` legs in series
        # joined by anonymous internal nets (XR2.1 ...) -- 24 legs in all.
        "resistors": ["XRT", "XR1", "XR2", "XRZ"],
        # This bank's legs are drawn vertically beside the PMOS row, so they
        # can be much longer than temp_core's rank-2 bank before they set the
        # cell height; 250 um of target keeps XR2's 4104 um to 16 legs rather
        # than the 36 the default ceiling would force.
        "resistor_fold": ResistorFold(
            style="string", max_um=300.0, target_um=250.0
        ),
        # The 2 MiM caps. Plate nets are per-instance isolated -- see
        # `cap_plate_nets` -- so they prove capacitance, not connectivity.
        "caps": ["XCC", "XCOK"],
        "ports": ["BIAS_OK", "IBIAS", "VDD", "VREF", "VSS", SUBSTRATE_NET],
        "internal": [
            "PG",
            "PB",
            "NBG",
            "NA",
            "NB",
            "NBTOP",
            "NT",
            "N1",
            "N2",
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
            # The three nets that exist only through a drawn passive. Before
            # #90 they were absent from both sides of the compare because the
            # devices that own them were not drawn: EC ties XR1 to the 8x PNP
            # leg, ER ties XR2 to XQR, NZ ties XRZ to the XCC plate.
            "EC",
            "ER",
            "NZ",
        ],
        # One drawn Nwell holds the whole PMOS row, so every pfet body lands on
        # the same anonymous well net.
        "wells": {
            "NW1": [
                "XMP1",
                "XMP2",
                "XMP3",
                "XMPBN",
                "XMBP",
                "XMPIB",
                "XMPT",
                "XMI1",
                "XMI2",
                "XMS2P",
                "XKA",
                "XMPOK",
                "XMOKA",
                "XMOKB",
                "XMOK2P",
                "XMO1P",
            ]
        },
    },
    # temp_core: every device of design/netlist/temp_core.spice except the MiM
    # cap XCC. The vertical PNPs (XQ1/XQ8A..H) and the poly resistors
    # (XR1/XR2*/XRISO/XRZ) used to be drawn as sibling top cells, outside this
    # compare, because the curated deck could not model them; #93 folded them
    # back in once klayout-tools#222/#223 landed and the marker geometry was
    # drawn. XCC stays out: the deck models only the 5LM (Metal4/Metal5) MiM
    # option and this block's cap is the m3m4 flavour, and a recognised MiM's
    # plate nets are not joined to the routing connectivity stack at all --
    # see layout/README.md -> "Known deck limits".
    "temp_core": {
        "source": "temp_core.spice",
        "subckt": "temp_core",
        "devices": [
            "XMBD",
            "XMPASS",
            "XMDNB",
            "XMBN1",
            "XMBP",
            "XMBN2",
            "XMCB",
            "XMINVP",
            "XMINVN",
            "XMT",
            "XMI1",
            "XMI2",
            "XML1",
            "XML2",
            "XMS2N",
            "XMS2P",
            "XMP1",
            "XMPC1",
            "XMP2",
            "XMPC2",
            "XMP3",
            "XMPC3",
            "XMSU1",
            "XMSU2",
            "XMSU3",
            "XMDND",
            "XMENPG",
            "XMENPT",
            "XMENCT",
            "XMSU4",
            "XMSU5",
            "XMDN2",
            "XMDNT",
            "XSW5",
            "XSW4",
            "XSW3",
            "XSW2",
            "XSW1",
            "XSW0",
        ],
        # Devices drawn as N interleaved unit fingers (layout/floorplan.md's
        # rank-1 input pair / load mirror and rank-2 cascoded mirror).
        "fingers": {
            "XMI1": 2,
            "XMI2": 2,
            "XML1": 2,
            "XML2": 2,
            "XMP1": 2,
            "XMPC1": 2,
            "XMP2": 2,
            "XMPC2": 2,
            "XMP3": 2,
            "XMPC3": 2,
        },
        # Edge dummy fingers. Drawn-only: they are not in the schematic, so
        # they are declared here rather than derived, and they are the reason
        # LVS still accounts for *every* drawn device.
        "dummies": [
            {"class": "pfet", "l": 4.0, "w": 16.0, "nets": ["NT", "NT", "NT"],
             "well": "NW2"},
            {"class": "pfet", "l": 4.0, "w": 16.0, "nets": ["NT", "NT", "NT"],
             "well": "NW2"},
            {"class": "nfet", "l": 8.0, "w": 4.0, "nets": ["VSS", "VSS", "VSS"]},
            {"class": "nfet", "l": 8.0, "w": 4.0, "nets": ["VSS", "VSS", "VSS"]},
            {"class": "pfet", "l": 4.0, "w": 4.0, "nets": ["VDD", "VDD", "VDD"],
             "well": "NW1"},
            {"class": "pfet", "l": 4.0, "w": 4.0, "nets": ["VDD", "VDD", "VDD"],
             "well": "NW1"},
        ],
        # The R2 gain ladder, the isolation/zero resistors and the PNP array,
        # in the order layout/build_cells.py draws them left to right.
        "resistors": [
            "XR1",
            "XRISO",
            "XRZ",
            "XR2F",
            "XR2T5",
            "XR2T4",
            "XR2T3",
            "XR2T2",
            "XR2T1",
            "XR2T0",
        ],
        # rank 3's centroid array: XQ1 at the centre, the 8 XQ8 units around
        # it. Every one of them is a 10x10 um emitter, which is the whole
        # point of the 8:1 ratio and the one parameter the compare checks.
        "bipolars": [
            "XQ1",
            "XQ8A",
            "XQ8B",
            "XQ8C",
            "XQ8D",
            "XQ8E",
            "XQ8F",
            "XQ8G",
            "XQ8H",
        ],
        # The drawn Nwell every PNP's base lands in. Same deck-imposed rewrite
        # as the PMOS wells below: the deck never joins Nwell to Contact, so
        # the base ring's VSS tie is invisible and the base is an anonymous
        # net carrying only base terminals.
        "bjt_well": "NWQ",
        "ports": [
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
            # Drawn as routing tracks (and so labelled, and so pins) only
            # since #93 folded the passives in: NC joins XR1 to the eight
            # XQ8 emitters, NZ is XRZ's free end. NZ's other schematic
            # connection is to XCC, which is not drawn (see the note above
            # this manifest), so NZ carries exactly one device terminal --
            # the same situation por_comparator's SNS/SNSB are in.
            "NC",
            "NZ",
            SUBSTRATE_NET,
        ],
        # Two drawn Nwells: the input pair's own well is biased to the tail
        # node NT, every other PMOS sits in the VDD well.
        "wells": {
            "NW1": [
                "XMBP",
                "XMCB",
                "XMINVP",
                "XMT",
                "XMS2P",
                "XMP1",
                "XMPC1",
                "XMP2",
                "XMPC2",
                "XMP3",
                "XMPC3",
                "XMSU1",
                "XMENPG",
                "XMSU4",
            ],
            "NW2": ["XMI1", "XMI2"],
        },
    },
    "por_output_chain": {
        "source": "por_output_chain.spice",
        "subckt": "por_output_chain",
        # Every MOS device in design/por_output_chain.sch -- 14 pfet + 14 nfet.
        # The cell's other 2 devices are the MiM caps XCDG/XCTIM, now drawn and
        # compared as well -- see this manifest's own `caps` field below.
        "devices": [
            # XMBD/XMPD lead so the topology control has two different sources
            # to work with (see the note above CELLS). XMBD first is not
            # incidental: it is DR-010's always-on IBIAS mirror diode, so it is
            # also the device the device-param control perturbs.
            "XMBD",
            "XMPD",
            "XMN1",
            "XMND",
            "XMDGNT",
            "XMDGNI",
            "XMG1N",
            "XMG2N",
            "XMDIS",
            "XMDANT",
            "XMDBNI",
            # XMRLK -- the issue #56 / DR-016 release latch on ND1.
            "XMRLK",
            "XMNAN1",
            "XMNAN2",
            "XMON",
            "XMP2",
            "XMDGPT",
            "XMPT",
            "XMDBPT",
            "XMDGPI",
            "XMG1P",
            "XMG2P",
            "XMTSW",
            "XMDAPI",
            "XMNAP1",
            "XMNAP2",
            "XMAST",
            "XMOP",
        ],
        # The cell's 2 MiM caps, in emission order (fixes C1..C5 numbering).
        # XCTIM is m=4, so it contributes 4 drawn units; the layout draws the
        # same 5 plates from the same golden c_width/c_length. Their plate nets
        # are per-instance isolated (see `cap_plate_nets`) -- the deck cannot
        # wire a recognised capacitor's plates to anything -- so unlike the MOS
        # devices they prove capacitance, not connectivity. Both schematic plate
        # nodes (NDG, TIM) also carry MOS terminals, so no net depends on them.
        "caps": ["XCDG", "XCTIM"],
        "ports": ["IBIAS", "POR_RAW", "RESETn", "VDD", "VSS", SUBSTRATE_NET],
        "internal": [
            "PDN",
            "NDL",
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
        ],
        # One drawn Nwell holds the whole PMOS row, XMOP included.
        "wells": {
            "NW1": [
                "XMPD",
                "XMP2",
                "XMDGPT",
                "XMPT",
                "XMDBPT",
                "XMDGPI",
                "XMG1P",
                "XMG2P",
                "XMTSW",
                "XMDAPI",
                "XMNAP1",
                "XMNAP2",
                "XMAST",
                "XMOP",
            ]
        },
    },
}

#: temp_por_top: the block-level assembly (#72). Unlike every entry above, it
#: lists no devices of its own -- it is *composed* from the four sub-cell
#: manifests, with each instance's nets renamed through the golden top-level
#: netlist's own port mapping (``build_assembly`` below). That is the point:
#: the assembled reference cannot drift from the four cells it assembles,
#: because it is generated from them and from
#: ``design/netlist/temp_por_top.spice``'s own instance lines, not retyped.
#:
#: Everything the four cells leave outside the curated deck's device coverage
#: (klayout-tools#219/#222) is still outside it here, and now all of it at once
#: -- ``layout/README.md`` -> "Known deck limits" carries the list. What the
#: cells *do* draw comes through unchanged, including ``por_output_chain``'s 5
#: drawn MiM units: extraction is flat, so they land in this cell's compare too.
CELLS["temp_por_top"] = {
    "source": "temp_por_top.spice",
    "subckt": "temp_por_top",
    #: instance name in design/temp_por_top.sch -> the cell it instances.
    "assembly": [
        ("xbias", "bias_core"),
        ("xcmp", "por_comparator"),
        ("xpor", "por_output_chain"),
        ("xtemp", "temp_core"),
    ],
    # The ratified 5-pad pinout, in the ratified order (spec/target-spec.md
    # § "Electrical interface"). Checked against design/netlist/
    # temp_por_top.spice's own .subckt line by build_assembly -- the same
    # assertion design/netlist.py --check makes at the schematic level -- so
    # this list cannot silently drift from the spec. SUBSTRATE_NET is the
    # deck's own global, not a pad.
    "ports": ["VDD", "VSS", "PTAT", "CTAT", "RESETn", SUBSTRATE_NET],
    # The four nets that cross between instances and stay inside the block.
    "internal": ["IBIAS", "VREF", "BIAS_OK", "POR_RAW"],
}

#: Cells whose committed artefacts are deliberately held at an older build than
#: their sources would produce, keyed by cell name. Read by **both**
#: ``--check`` paths -- this module's and ``layout/build_cells.py``'s (which
#: imports this module) -- so a freeze is declared once and cannot drift
#: between the two gates.
#:
#: A freeze is *not* "skip the staleness check". A frozen cell's committed
#: artefact is pinned to the exact sha256 recorded here, so ``--check`` still
#: fails if that artefact changes -- what the freeze suspends is only the
#: comparison against a *fresh rebuild*, which is the thing the tracking issue
#: owns. The three states are therefore distinguishable in the output:
#:
#: * unfrozen and current            -> ``ok <artefact>``
#: * unfrozen and rebuilt-differs    -> ``FAIL ...: committed ... is stale``
#: * frozen and baseline intact      -> ``frozen <artefact> ... (see #N)``
#: * frozen and baseline **changed** -> ``FAIL ...: no longer matches the
#:   pinned frozen baseline`` (someone regenerated a frozen artefact; either
#:   restore it or land the tracking issue and delete the entry)
#:
#: Regenerating (running either script without ``--check``) also skips a frozen
#: cell unless it is named explicitly with ``--cell``, so a routine
#: whole-repo regeneration cannot quietly break the pin.
#:
#: Removal condition: delete the entry when its ``issue`` lands. Nothing else
#: has to change -- both gates fall straight back to rebuild-and-compare.
FROZEN_CELLS = {
    "temp_por_top": {
        "issue": "#97",
        "why": (
            "block assembly held at the #72 sub-cell set (#91/#99): rebuilding "
            "it against today's grown sub-cells is 92 DRC violations at the "
            "instance boundaries, which #97 owns"
        ),
        # sha256 of the committed artefacts as of c076733.
        "gds_sha256": (
            "44978656f38fd30f2968ded8ef6519344fa0271027f856af48c6c5d62040aed9"
        ),
        "reference_sha256": (
            "fd2dc1d1b5e19118045d5a76dc07ea4287d3344446414bb8ef45df00f95440f7"
        ),
    },
}


class FrozenVerdict(NamedTuple):
    """One frozen cell's artefact verdict: ``ok`` plus the line to print."""

    ok: bool
    line: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _display_path(path: Path) -> Path:
    """``path`` relative to the repo root when it is inside it, else as given."""
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def frozen_check(name: str, artefact: str, path: Path) -> FrozenVerdict | None:
    """Verify a frozen cell's committed artefact against its pinned digest.

    ``artefact`` selects the pinned digest (``"gds"`` -> ``gds_sha256``,
    ``"reference"`` -> ``reference_sha256``); ``path`` is the committed file.

    Returns ``None`` when ``name`` is not frozen, which means "do the normal
    rebuild-and-compare"; every caller must handle that case rather than
    treating a missing entry as a pass. A ``KeyError`` here means a
    :data:`FROZEN_CELLS` entry declared a freeze without pinning this artefact,
    which is a mistake in the freeze, not something to skip.
    """
    spec = FROZEN_CELLS.get(name)
    if spec is None:
        return None
    pinned = spec[f"{artefact}_sha256"]
    where = _display_path(path)
    if not path.exists():
        return FrozenVerdict(
            False,
            f"{name}: frozen for {spec['issue']} but {where} is not committed",
        )
    digest = sha256_bytes(path.read_bytes())
    if digest != pinned:
        return FrozenVerdict(
            False,
            f"{name}: committed {where} no longer matches the pinned frozen "
            f"baseline (pinned {pinned[:16]}, committed {digest[:16]}) -- "
            f"restore it, or land {spec['issue']} and drop the freeze",
        )
    return FrozenVerdict(
        True,
        f"frozen {where}  sha256={digest[:16]}  "
        f"(pinned baseline, not rebuilt: see {spec['issue']})",
    )


SUBCKT_RE = re.compile(r"^\.subckt\s+(\S+)\s+(.*)$", re.IGNORECASE)
ENDS_RE = re.compile(r"^\.ends\b", re.IGNORECASE)
UNIT_RE = re.compile(r"^([0-9.eE+-]+)\s*([a-zA-Z]*)$")

SI_SUFFIX = {"": 1.0, "u": 1e-6, "um": 1e-6, "n": 1e-9, "m": 1e-3, "p": 1e-12}


class ReferenceError(Exception):
    pass


def logical_lines(text: str) -> list[str]:
    """Join SPICE ``+`` continuations; drop comments and blanks."""
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("*"):
            continue
        if line.lstrip().startswith("+"):
            if not out:
                raise ReferenceError("continuation line with nothing to continue")
            out[-1] = f"{out[-1]} {line.lstrip()[1:].strip()}"
        else:
            out.append(line.strip())
    return out


def subckt_body(text: str, name: str) -> list[str]:
    body: list[str] = []
    inside = False
    for line in logical_lines(text):
        match = SUBCKT_RE.match(line)
        if match:
            inside = match.group(1) == name
            continue
        if ENDS_RE.match(line):
            if inside:
                return body
            inside = False
            continue
        if inside:
            body.append(line)
    raise ReferenceError(f"subcircuit {name!r} not found")


def to_um(value: str) -> float:
    match = UNIT_RE.match(value)
    if not match:
        raise ReferenceError(f"cannot parse dimension {value!r}")
    number, suffix = match.groups()
    scale = SI_SUFFIX.get(suffix.lower())
    if scale is None:
        raise ReferenceError(f"unsupported unit suffix in {value!r}")
    return float(number) * scale * 1e6


def format_um(value_um: float) -> str:
    text = f"{value_um:.4f}".rstrip("0").rstrip(".")
    return f"{text or '0'}U"


def resistor_fold(cell: str) -> ResistorFold:
    """The fold policy ``cell``'s manifest asks for (see :data:`ResistorFold`).

    One lookup for both sides of the compare: ``build_cells.py`` draws the legs
    this returns and :func:`build_passive_cards` declares them, so a cell can
    never draw one fold and declare another.
    """
    return CELLS[cell].get("resistor_fold", DEFAULT_RESISTOR_FOLD)


def resistor_segments(
    length_um: float, fold: ResistorFold = DEFAULT_RESISTOR_FOLD
) -> list[float]:
    """The drawn recognised bodies one schematic resistor becomes, in um.

    A long resistor need not be one extracted device, and in this block it is
    one or several depending on how its cell draws it (:data:`ResistorFold`):

    * ``style="serpentine"`` -- one continuous marked body. The extractor
      solves ``L``/``W`` from the region's own area and perimeter, and
      ``build_cells.py``'s ``_resistor_leg_plan`` draws the zig-zag so that
      area reconstructs ``r_length`` exactly, corners included. One body, so
      this returns ``[length_um]`` and the reference emits one card.
    * ``style="string"`` -- a series string of straight marked legs strapped
      end to end (exactly as a real PDK resistor array is), each of which
      extracts as its own two-terminal device, with the split below. It is the
      same "describe the device the way the deck can see it" move ``fingers``
      already makes for a matched MOS pair.

    Three constraints pick a *string*'s split, and this is the single place
    they are applied -- ``build_cells.py`` draws what this returns:

    * **an even leg count**, so the string's two free ends come out at the same
      end of the array (leg *i* is strapped to *i+1* alternately at the top and
      the bottom) and both terminals escape to the routing channel without
      crossing it;
    * **an exact whole number of database units per leg** -- the drawn leg and
      the declared resistance are the same number, not a rounding of one. A leg
      that did not round-trip on the 1 nm grid would make the drawn resistance
      differ from the stated one, which LVS reports as a ``device.property``
      mismatch nobody could act on. Raises rather than rounding silently;
    * no leg longer than ``fold.max_um``, and as close to ``fold.target_um`` as
      the first two allow. With no target the fewest legs win, which is the
      longest legs the ceiling permits.

    Leg length falls monotonically as the leg count rises, so the first
    candidate at or below the target is the last one worth considering.
    """
    if length_um <= 0.0:
        raise ReferenceError(f"resistor length {length_um} is not positive")
    if fold.style == "serpentine":
        return [length_um]
    if fold.style != "string":
        raise ReferenceError(f"unknown resistor fold style {fold.style!r}")
    total_nm = round(length_um * 1000.0)
    if abs(total_nm - length_um * 1000.0) > 1e-6:
        raise ReferenceError(
            f"resistor length {length_um} um is not a whole number of nm"
        )
    target_um = fold.max_um if fold.target_um is None else fold.target_um
    best: tuple[float, int, float] | None = None
    for legs in range(2, total_nm + 1, 2):
        if total_nm % legs:
            continue
        leg_um = total_nm / legs / 1000.0
        if leg_um > fold.max_um:
            continue
        distance = abs(leg_um - target_um)
        if best is None or distance < best[0]:
            best = (distance, legs, leg_um)
        if leg_um <= target_um:
            break
    if best is None:
        raise ReferenceError(
            f"cannot fold {length_um} um into an even number of legs of "
            f"<= {fold.max_um} um each on the 1nm grid -- the length has no "
            "even divisor that small"
        )
    return [best[2]] * best[1]


def parse_devices(body: list[str]) -> dict[str, dict]:
    """Parse ``X<name> d g s b <model> k=v ...`` MOS cards into a dict by name."""
    devices: dict[str, dict] = {}
    for line in body:
        fields = line.split()
        if not fields[0].upper().startswith("X"):
            continue
        params: dict[str, str] = {}
        nodes: list[str] = []
        model: str | None = None
        for field in fields[1:]:
            if "=" in field:
                key, _, value = field.partition("=")
                params[key.lower()] = value.strip("'\"")
            elif model is None and field in DEVICE_CLASS:
                model = field
            elif model is None:
                nodes.append(field)
        if model is None:
            continue  # not a device this deck can model (resistor, cap, BJT...)
        devices[fields[0]] = {"nodes": nodes, "model": model, "params": params}
    return devices


def parse_capacitors(body: list[str]) -> dict[str, dict]:
    """Parse ``X<name> p1 p2 <model> c_width=.. c_length=.. m=..`` MiM cap cards.

    Same shape as :func:`parse_devices`, scoped to :data:`CAP_CLASS` instead of
    :data:`DEVICE_CLASS` -- the one other device class the curated deck now
    recognises that this repo draws as more than one instance per manifest
    entry (``m=`` -- see :func:`cap_units`).
    """
    caps: dict[str, dict] = {}
    for line in body:
        fields = line.split()
        if not fields[0].upper().startswith("X"):
            continue
        params: dict[str, str] = {}
        nodes: list[str] = []
        model: str | None = None
        for field in fields[1:]:
            if "=" in field:
                key, _, value = field.partition("=")
                params[key.lower()] = value.strip("'\"")
            elif model is None and field in CAP_CLASS:
                model = field
            elif model is None:
                nodes.append(field)
        if model is None:
            continue  # not a capacitor this deck can model
        caps[fields[0]] = {"nodes": nodes, "model": model, "params": params}
    return caps


def parse_passives(body: list[str]) -> dict[str, dict]:
    """Parse the golden netlist's resistor and bipolar cards.

    Same shape as :func:`parse_devices`, for the two non-MOS device classes
    the curated deck grew recognition for (klayout-tools#222/#223): a
    ``ppolyf_u`` poly resistor (``X<name> a b bulk ppolyf_u r_width= r_length=``)
    and a vertical bipolar (``X<name> c b e pnp_WWpWWxHHpHH``). Everything
    else -- notably the MiM cap, whose model has no counterpart in the deck --
    is skipped here and picked up by nothing, which is exactly what
    ``layout/README.md`` records as still outside the compare.
    """
    passives: dict[str, dict] = {}
    for line in body:
        fields = line.split()
        if not fields[0].upper().startswith("X"):
            continue
        params: dict[str, str] = {}
        nodes: list[str] = []
        model: str | None = None
        for field in fields[1:]:
            if "=" in field:
                key, _, value = field.partition("=")
                params[key.lower()] = value.strip("'\"")
            elif model is not None:
                continue
            elif field in RESISTOR_CLASS or BIPOLAR_NAME_RE.match(field):
                model = field
            else:
                nodes.append(field)
        if model is None:
            continue
        kind = "resistor" if model in RESISTOR_CLASS else "bipolar"
        passives[fields[0]] = {
            "kind": kind,
            "nodes": nodes,
            "model": model,
            "params": params,
        }
    return passives


def emitter_window_um(model: str) -> tuple[float, float]:
    """The drawn emitter window a gf180mcu bipolar's device name states, in um.

    ``pnp_10p00x10p00`` -> ``(10.0, 10.0)``. Both the drawn geometry
    (``build_cells.py``) and the declared ``AE``/``PE``
    (:func:`build_passive_cards`) come from here, so a schematic that swaps to
    a different emitter size moves them together.
    """
    match = BIPOLAR_NAME_RE.match(model)
    if not match:
        raise ReferenceError(f"cannot read an emitter size out of {model!r}")
    whole_w, frac_w, whole_l, frac_l = match.groups()
    return float(f"{whole_w}.{frac_w}"), float(f"{whole_l}.{frac_l}")


def emitter_area_um2(model: str) -> float:
    """The drawn emitter area a gf180mcu bipolar's device name states."""
    width, length = emitter_window_um(model)
    return width * length


def subckt_ports(text: str, name: str) -> list[str]:
    """The formal port list of ``.subckt <name> ...`` in ``text``."""
    for line in logical_lines(text):
        match = SUBCKT_RE.match(line)
        if match and match.group(1) == name:
            return match.group(2).split()
    raise ReferenceError(f"subcircuit {name!r} not found")


class Card(NamedTuple):
    """One plain-element card, before it is numbered and formatted.

    ``prefix`` is the SPICE element letter the emitted card gets (``M`` for a
    schematic MOS, ``MD`` for a drawn-only dummy finger, ``R``, ``Q``).
    ``value`` is the positional value a SPICE ``R``/``C`` card carries between
    its nodes and its model token (``R1 a b w 3500 ppolyf_u``); ``None`` for
    an element whose value is entirely in ``params`` (``M``, ``Q``).

    A ``Q`` card **must** carry at least one ``key=value`` parameter: with a
    bare model token and nothing after it, ``NetlistSpiceReader`` reads the
    model name as a fourth (substrate) node and falls back to its built-in
    ``BJT`` device class, which then fails to pair with the extracted ``bjt``
    class for a reason no mismatch entry explains. ``AE`` is emitted for
    every bipolar, which is also the one parameter the compare checks.
    """

    prefix: str
    klass: str
    nodes: list[str]
    value: str | None = None
    params: tuple[tuple[str, str], ...] = ()


def mos_card(prefix: str, klass: str, nodes: list[str], length_um: float, width_um: float) -> Card:
    return Card(
        prefix,
        klass,
        nodes,
        None,
        (("L", format_um(length_um)), ("W", format_um(width_um))),
    )


def build_cards(
    cell: str, corrupt: str | None = None, rename=None
) -> list[Card]:
    """Every device card one manifest entry contributes, before numbering.

    ``rename`` (used only by :func:`build_assembly`) maps this cell's own net
    names into the enclosing cell's. It is applied *after* the undeclared-net
    guard below, so a sub-cell's manifest still has to declare every net its
    own devices touch -- assembling it cannot launder an undeclared net.
    """
    spec = CELLS[cell]
    source = NETLIST_DIR / spec["source"]
    devices = parse_devices(subckt_body(source.read_text(), spec["subckt"]))

    well_of: dict[str, str] = {}
    for well, members in spec.get("wells", {}).items():
        for member in members:
            well_of[member] = well

    ports = list(spec["ports"])
    known_nets = (
        set(ports) | set(spec.get("wells", {})) | set(spec.get("internal", []))
    )
    if spec.get("bjt_well"):
        known_nets.add(spec["bjt_well"])

    fingers = spec.get("fingers", {})

    def out(net: str) -> str:
        return net if rename is None else rename(net)

    cards: list[Card] = []
    for name in spec["devices"]:
        if name not in devices:
            raise ReferenceError(f"{cell}: device {name!r} not in {spec['source']}")
        device = devices[name]
        if len(device["nodes"]) != 4:
            raise ReferenceError(f"{cell}: {name} is not a 4-terminal device")
        letter, klass = DEVICE_CLASS[device["model"]]

        # The curated deck extracts one drawn device per drawn gate: it models
        # neither multi-finger (nf) nor multiplied (m) devices, so a reference
        # that quietly carried either would compare against a layout that
        # cannot represent it.
        for param in ("nf", "m"):
            value = device["params"].get(param, "1")
            if float(value) != 1.0:
                raise ReferenceError(
                    f"{cell}: {name} has {param}={value}; the curated gf180mcu "
                    "deck models only single-finger, unmultiplied devices"
                )

        drain, gate, source_node, body = device["nodes"]
        if klass == "nfet":
            body = SUBSTRATE_NET
        else:
            if name not in well_of:
                raise ReferenceError(f"{cell}: {name} is not assigned to a well")
            body = well_of[name]

        nodes = [drain, gate, source_node, body]
        unknown = [net for net in nodes if net not in known_nets]
        if unknown:
            raise ReferenceError(
                f"{cell}: {name} touches undeclared net(s) {', '.join(unknown)} "
                "-- add them to the manifest's ports/wells"
            )

        # A matched device drawn as N interleaved unit fingers extracts as N
        # devices: the curated deck runs no device-combination step, so N
        # parallel fingers never fold back into one W. The reference therefore
        # emits the same N parallel devices of W/N -- the same electrical
        # device, described the way the deck can see it. Filed upstream as
        # tool friction; see layout/README.md -> "Known deck limits".
        count = int(fingers.get(name, 1))
        for finger in range(count):
            cards.append(
                mos_card(
                    letter,
                    klass,
                    [out(net) for net in nodes],
                    to_um(device["params"]["l"]),
                    to_um(device["params"]["w"]) / count,
                )
            )
            del finger

    for dummy in spec.get("dummies", []):
        klass = dummy["class"]
        drain, gate, source_node = dummy["nets"]
        body = SUBSTRATE_NET if klass == "nfet" else dummy["well"]
        nodes = [drain, gate, source_node, body]
        cards.append(
            mos_card(
                "MD",
                klass,
                [out(net) for net in nodes],
                float(dummy["l"]),
                float(dummy["w"]),
            )
        )

    cards.extend(build_passive_cards(cell, known_nets, out))
    cards.extend(build_cap_cards(cell, out))
    return cards


def build_passive_cards(cell: str, known_nets: set[str], out) -> list[Card]:
    """The resistor and bipolar cards one manifest entry contributes.

    Both device classes were outside the curated deck when these cells were
    first drawn and are inside it now (klayout-tools#222/#223/#225); what the
    layout owns, and what this function mirrors, is the *marker* geometry that
    makes the deck recognise them.

    Two deck-imposed rewrites happen here, exactly parallel to the MOS body
    rewrites at the top of this module:

    * a poly resistor's bulk terminal goes to the substrate global, because the
      deck extracts it with ``'W' => sub`` and there is no drawn tap to derive
      anything else from;
    * a vertical bipolar's **collector** goes to the same global (the DRM's
      vertical device has no drawn collector layer -- its collector *is* the
      substrate), and its **base** goes to the anonymous net of the drawn
      Nwell it sits in, because the deck never joins ``Nwell`` to ``Contact``
      and so cannot see the base ring's tie. The schematic ties both to
      ``VSS``; the layout does too, and no check in this flow proves it.

    A resistor is drawn one of two ways, and the cell's own
    :data:`ResistorFold` decides which (not the schematic model -- both models
    are drawn both ways in this block): a **series string** of straight marked
    segments strapped end to end, which ``klt`` extracts as one device per
    segment with anonymous intermediate nodes, or one continuous body
    **serpentined**, which it extracts as a single device whose marked area
    alone reconstructs the schematic's ``r_length``
    (``build_cells.py``'s ``_resistor_leg_plan``). Both are real
    single-source-of-truth translations of the same golden
    ``r_length``/``r_width``: :func:`resistor_segments` returns the drawn
    bodies either way and one card is emitted per body.

    ``AE`` -- the drawn emitter window's area -- is declared on every ``Q``
    card and is not optional: KLayout treats it as the bipolar class's
    *primary* parameter, and a card that omits it defaults it to zero, which
    does not pair against the extracted device at all. Worse, on the circuit
    sizes this repo compares it does not surface as ``device.property``: it
    degrades into ``device.unmatched`` plus a ``net.merged``/``net.split``
    cascade, the same mis-localisation klayout-tools#282 records for a MOS
    parameter defect. It comes out of the PDK subcircuit's own name
    (:func:`emitter_window_um`), so the reference stays derived from the
    schematic.

    ``PE``/``AB``/``PB``/``AC``/``PC``/``NE`` are deliberately **not**
    declared. The extractor measures them off the drawn geometry -- the
    emitter's perimeter, and the base region ``Nwell`` ∩ ``DRC_BJT`` -- and the
    comparer does not treat any of them as primary, so declaring them would put
    drawn-geometry constants into a schematic-derived reference for no checking
    benefit. That last part is measured, not assumed: a reference built with a
    deliberately wrong ``PE`` on one bipolar still reports **match**, so a
    declared ``PE`` would be a number no check answers for. If a later ``klt``
    starts comparing them, LVS fails loudly and this is where the fix goes;
    :data:`BIPOLAR_BASE_MARGIN_UM` is what fixes the base values today.
    """
    spec = CELLS[cell]
    passives = parse_passives(
        subckt_body((NETLIST_DIR / spec["source"]).read_text(), spec["subckt"])
    )
    cards: list[Card] = []

    for name in spec.get("resistors", []):
        if name not in passives or passives[name]["kind"] != "resistor":
            raise ReferenceError(f"{cell}: resistor {name!r} not in {spec['source']}")
        device = passives[name]
        klass, sheet_rho = RESISTOR_CLASS[device["model"]]
        if len(device["nodes"]) != 3:
            raise ReferenceError(f"{cell}: {name} is not a 3-terminal resistor")
        require_unit_multiplier(cell, name, device)
        head, tail, bulk = device["nodes"]
        for net in (head, tail):
            if net not in known_nets:
                raise ReferenceError(
                    f"{cell}: {name} touches undeclared net {net} -- add it to "
                    "the manifest's ports/internal"
                )
        if bulk != "VSS":
            raise ReferenceError(
                f"{cell}: {name}'s bulk node is {bulk!r}; the deck ties every "
                "drawn resistor's bulk to its substrate global"
            )
        width = to_um(device["params"]["r_width"])
        length_um = to_um(device["params"]["r_length"])
        # One card per drawn recognised body: a serpentine is one body, a
        # string is one per segment. The series nodes between segments are
        # unlabelled straps in the layout, so they are anonymous in the
        # extracted netlist and matched by topology alone. They are *derived*
        # from the split, not declared, so a manifest can never disagree with
        # the drawn string about how many there are.
        segments = resistor_segments(length_um, resistor_fold(cell))
        nets = [head] + [f"{name}.{i}" for i in range(1, len(segments))] + [tail]
        for index, length in enumerate(segments):
            cards.append(
                Card(
                    "R",
                    klass,
                    [out(nets[index]), out(nets[index + 1]), SUBSTRATE_NET],
                    f"{length / width * sheet_rho:.10g}",
                )
            )

    for name in spec.get("bipolars", []):
        if name not in passives or passives[name]["kind"] != "bipolar":
            raise ReferenceError(f"{cell}: bipolar {name!r} not in {spec['source']}")
        device = passives[name]
        if len(device["nodes"]) != 3:
            raise ReferenceError(f"{cell}: {name} is not a 3-terminal bipolar")
        require_unit_multiplier(cell, name, device)
        collector, _base, emitter = device["nodes"]
        if collector != "VSS":
            raise ReferenceError(
                f"{cell}: {name}'s collector is {collector!r}; the deck draws no "
                "collector layer and ties every bipolar's collector to its "
                "substrate global"
            )
        if emitter not in known_nets:
            raise ReferenceError(
                f"{cell}: {name} touches undeclared net {emitter} -- add it to "
                "the manifest's ports/internal"
            )
        well = spec.get("bjt_well")
        if well is None:
            raise ReferenceError(f"{cell}: {name} needs a bjt_well in the manifest")
        area = emitter_area_um2(device["model"])
        cards.append(
            Card(
                "Q",
                BIPOLAR_CLASS,
                [SUBSTRATE_NET, out(well), out(emitter)],
                None,
                (("AE", f"{area:.10g}P"),),
            )
        )

    return cards


def require_unit_multiplier(cell: str, name: str, device: dict) -> None:
    """Reject a golden card with ``m=`` > 1 on a class drawn one-per-card.

    The curated deck runs no device-combination step and models no multiplier,
    so a multiplied resistor or bipolar would have to be drawn as *m* separate
    devices. Nothing in this block needs that yet, and guessing at it silently
    would be a drawn/declared divergence; :func:`cap_units` is where the MiM
    caps' equivalent is handled explicitly.
    """
    value = float(device["params"].get("m", "1"))
    if value != 1.0:
        raise ReferenceError(
            f"{cell}: {name} has m={device['params']['m']}; the curated "
            "gf180mcu deck models no device multiplier"
        )


def cap_units(cap: dict) -> int:
    """How many drawn devices one golden MiM card's ``m=`` multiplier is.

    The curated deck runs no device-combination step and models no multiplier,
    so ``m=4`` is four drawn capacitors of the card's own ``c_width`` x
    ``c_length`` -- the same treatment ``fingers`` gives a multi-finger MOS.
    """
    value = float(cap["params"].get("m", "1"))
    if value != int(value) or value < 1:
        raise ReferenceError(f"MiM multiplier m={value} is not a positive integer")
    return int(value)


def cap_plate_nets(name: str, cap: dict, unit: int, units: int) -> list[str]:
    """The two isolated nets one drawn MiM unit's plates extract onto.

    ``klt`` registers a recognised capacitor's plates as their own
    self-connected connectivity nodes and the top plate's layer is not in the
    deck's metal stack at all, so *no* drawn routing can put either plate on a
    schematic net (``CapacitorDevice``'s "Known limitation"; see the module
    docstring). The reference therefore names each plate after the schematic
    node it is *meant* to be on, scoped to its own instance so it stays
    isolated: ``XCDG.NDG``, ``XCTIM.3.VSS``. Reading the reference netlist shows
    the fidelity loss rather than hiding it behind an anonymous ``n17``.
    """
    tag = name if units == 1 else f"{name}.{unit}"
    return [f"{tag}.{node}" for node in cap["nodes"]]


def build_cap_cards(cell: str, rename=None) -> list[Card]:
    """Every drawn-MiM card one manifest entry contributes, before numbering.

    Plate dimensions are read out of the golden netlist's own ``c_width`` /
    ``c_length`` -- the same source ``build_cells.py`` draws the plates from --
    and the capacitance is that overlap area times :data:`MIM_AREA_CAP_F_UM2`,
    which is exactly what ``klt extract`` computes from the drawn geometry. So a
    plate drawn at the wrong size fails LVS on the value rather than passing
    against a number typed to agree with it. ``rename`` follows the same
    convention as :func:`build_cards` -- used only by :func:`build_assembly`.
    """
    spec = CELLS[cell]
    names = spec.get("caps", [])
    if not names:
        return []
    source = NETLIST_DIR / spec["source"]
    caps = parse_capacitors(subckt_body(source.read_text(), spec["subckt"]))

    cards: list[Card] = []
    for name in names:
        if name not in caps:
            raise ReferenceError(f"{cell}: MiM cap {name!r} not in {spec['source']}")
        cap = caps[name]
        if len(cap["nodes"]) != 2:
            raise ReferenceError(f"{cell}: {name} is not a 2-terminal capacitor")
        klass = CAP_CLASS[cap["model"]]
        width_um = to_um(cap["params"]["c_width"])
        length_um = to_um(cap["params"]["c_length"])
        units = cap_units(cap)
        value_f = width_um * length_um * MIM_AREA_CAP_F_UM2
        for unit in range(1, units + 1):
            nets = cap_plate_nets(name, cap, unit, units)
            plates = [net if rename is None else rename(net) for net in nets]
            cards.append(
                Card("C", klass, plates, f"{value_f:.6g}")
            )
    return cards


def build_assembly(cell: str) -> list[Card]:
    """Compose an assembly cell's cards from the cells it instances.

    Each sub-cell's own manifest supplies its devices, sizes, wells,
    dummy fingers and drawn MiM caps unchanged; the only thing this adds is the
    net renaming, taken from the golden top-level netlist itself:

    * a sub-circuit's formal port maps to whatever the top-level instance line
      wires it to (``xbias VDD VSS IBIAS VREF BIAS_OK bias_core`` ->
      ``bias_core``'s ``IBIAS`` *is* the block's ``IBIAS``),
    * every other net of that sub-circuit -- internal nodes, and the
      per-drawn-well body nets -- is prefixed with the instance name, so two
      instances that both have a net called ``PG`` keep two distinct nets,
    * the deck's substrate global is never renamed; it is global.

    Also asserts the assembled cell's own pin list against the golden
    netlist's ``.subckt`` line -- the same ratified-pinout check
    ``design/netlist.py --check`` makes at the schematic level, restated here
    because this is the artifact the layout is compared against.
    """
    spec = CELLS[cell]
    text = (NETLIST_DIR / spec["source"]).read_text()

    ratified = subckt_ports(text, spec["subckt"])
    declared = [port for port in spec["ports"] if port != SUBSTRATE_NET]
    if declared != ratified:
        raise ReferenceError(
            f"{cell}: manifest ports {declared} do not match the ratified "
            f"pinout {ratified} in design/netlist/{spec['source']}"
        )
    top_nets = set(ratified) | set(spec.get("internal", []))

    instances: dict[str, list[str]] = {}
    for line in subckt_body(text, spec["subckt"]):
        fields = line.split()
        if fields[0].lower().startswith("x"):
            instances[fields[0].lower()] = fields[1:]

    cards: list[Card] = []
    for inst, sub_cell in spec["assembly"]:
        if inst not in instances:
            raise ReferenceError(f"{cell}: no instance {inst!r} in {spec['source']}")
        *actual, model = instances[inst]
        if model != sub_cell:
            raise ReferenceError(
                f"{cell}: instance {inst} is a {model}, manifest says {sub_cell}"
            )
        formal = subckt_ports(text, sub_cell)
        if len(formal) != len(actual):
            raise ReferenceError(
                f"{cell}: {inst} passes {len(actual)} nets to {sub_cell}'s "
                f"{len(formal)} ports"
            )
        unknown = [net for net in actual if net not in top_nets]
        if unknown:
            raise ReferenceError(
                f"{cell}: {inst} wires undeclared block net(s) "
                f"{', '.join(unknown)} -- add them to the manifest's "
                "ports/internal"
            )
        mapping = dict(zip(formal, actual))

        def rename(net: str, mapping=mapping, inst=inst) -> str:
            if net == SUBSTRATE_NET:
                return net
            return mapping.get(net, f"{inst}.{net}")

        cards.extend(build_cards(sub_cell, rename=rename))
    return cards


def build(cell: str, corrupt: str | None = None) -> str:
    spec = CELLS[cell]
    ports = list(spec["ports"])
    if "assembly" in spec:
        cards = build_assembly(cell)
    else:
        cards = build_cards(cell)

    # Both controls perturb the first two cards, which are always MOS: every
    # manifest lists its schematic MOS devices first and the passives are
    # appended after them (see build_cards). That keeps the two controls
    # comparable across cells and across this change.
    if corrupt == "device-param":
        params = dict(cards[0].params)
        params["W"] = format_um(to_um(params["W"]) * 2.0)
        cards[0] = cards[0]._replace(params=tuple(params.items()))
    elif corrupt == "topology":
        if len(cards) < 2:
            raise ReferenceError(f"{cell}: topology control needs >= 2 devices")
        nodes = list(cards[0].nodes)
        nodes[2] = cards[1].nodes[2]  # re-tie device 1's source to device 2's
        cards[0] = cards[0]._replace(nodes=nodes)
    elif corrupt == "passive-param":
        # The MOS controls above say nothing about the resistor and bipolar
        # classes #93 folded in: a compare that paired them by topology and
        # never looked at a resistance or an emitter area would pass both.
        # This one doubles the first resistor's value and halves the first
        # bipolar's emitter area, so a clean run is evidence that the drawn
        # *sizes* of the passives are compared too, not just their wiring.
        first = {}
        for index, card in enumerate(cards):
            if card.prefix in ("R", "Q"):
                first.setdefault(card.prefix, index)
        if not first:
            raise ReferenceError(f"{cell}: no passive device to corrupt")
        if "R" in first:
            card = cards[first["R"]]
            cards[first["R"]] = card._replace(
                value=f"{float(card.value) * 2.0:.10g}"
            )
        if "Q" in first:
            card = cards[first["Q"]]
            params = dict(card.params)
            params["AE"] = f"{float(params['AE'].rstrip('P')) / 2.0:.10g}P"
            cards[first["Q"]] = card._replace(params=tuple(params.items()))
    elif corrupt is not None:
        raise ReferenceError(f"unknown corruption {corrupt!r}")

    lines = [
        f"* {cell} -- klt lvs reference netlist"
        + (f" [NEGATIVE CONTROL: {corrupt}]" if corrupt else ""),
        f"* generated by layout/lvs_reference.py from design/netlist/{spec['source']}",
        "* Do not edit: edit the schematic, re-run design/netlist.py, re-run this.",
        f".SUBCKT {cell} {' '.join(ports)}",
    ]
    for index, card in enumerate(cards):
        fields = [f"{card.prefix}{index + 1}", *card.nodes]
        if card.value is not None:
            fields.append(card.value)
        fields.append(card.klass)
        fields.extend(f"{key}={value}" for key, value in card.params)
        lines.append(" ".join(fields))
    lines.append(f".ENDS {cell}")
    return "\n".join(lines) + "\n"


def check_deck_hash_consistency(reports_dir: Path = REPORTS_DIR) -> list[str]:
    """Fail loudly if committed ``layout/reports/*/drc.json`` disagree on
    ``provenance.deck.content_hash``.

    ``layout/reports/`` is append-only evidence (repo ``CLAUDE.md``,
    "Verification is the product"): every committed report is supposed to
    describe a run of the *same* ``klt`` deck, so a DRC-clean verdict recorded
    for one cell means something about every other cell's report too. Nothing
    else in this flow checked that invariant, so two cells' reports could (and
    did, see #103) silently drift onto two different deck revisions with no
    error anywhere.

    Cells in :data:`FROZEN_DECK_CELLS` are excluded from the agreement check
    (their own committed report can lag while the cell is intentionally
    frozen) but still required to have a well-formed ``provenance.deck``
    block -- a frozen cell with an unreadable report is still a bug, just not
    a hash-drift one.

    Returns a list of human-readable failure strings; empty means consistent.
    """
    hashes: dict[str, str] = {}
    failures: list[str] = []
    for drc_path in sorted(reports_dir.glob("*/drc.json")):
        cell = drc_path.parent.name
        try:
            data = json.loads(drc_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            failures.append(f"{cell}: could not read {drc_path}: {error}")
            continue
        content_hash = data.get("provenance", {}).get("deck", {}).get("content_hash")
        if not content_hash:
            failures.append(
                f"{cell}: {drc_path} has no provenance.deck.content_hash"
            )
            continue
        if cell in FROZEN_DECK_CELLS:
            continue
        hashes[cell] = content_hash

    distinct = sorted(set(hashes.values()))
    if len(distinct) > 1:
        by_hash: dict[str, list[str]] = {}
        for cell, content_hash in hashes.items():
            by_hash.setdefault(content_hash, []).append(cell)
        detail = "; ".join(
            f"{content_hash} -> {', '.join(sorted(cells))}"
            for content_hash, cells in sorted(by_hash.items())
        )
        frozen = sorted(FROZEN_DECK_CELLS)
        failures.append(
            "committed layout/reports/*/drc.json disagree on "
            f"provenance.deck.content_hash: {detail}. Regenerate every "
            "non-frozen cell's reports against one deck (bash "
            f"layout/run_checks.sh) before committing. (Excluded as frozen: "
            f"{', '.join(frozen) if frozen else 'none'}.)"
        )
    return failures


def run(check: bool, only: str | None, corrupt: str | None, out: str | None) -> int:
    names = [only] if only else sorted(CELLS)
    for name in names:
        if name not in CELLS:
            print(f"unknown cell {name!r} (have: {', '.join(sorted(CELLS))})")
            return 2

    if corrupt:
        if len(names) != 1 or out is None:
            print("--corrupt requires exactly one --cell and an -o/--output path")
            return 2
        Path(out).write_text(build(names[0], corrupt))
        print(f"wrote {out} [negative control: {corrupt}]")
        return 0

    failures = []
    for name in names:
        path = CELLS_DIR / f"{name}.reference.spice"
        # A frozen cell (see FROZEN_CELLS) is held against its pinned committed
        # digest instead of against a fresh derivation, in both directions:
        # --check does not compare it to `build(name)`, and a regeneration pass
        # does not overwrite it unless it was named explicitly with --cell.
        frozen = frozen_check(name, "reference", path)
        if frozen is not None and (check or only is None):
            if check:
                if frozen.ok:
                    print(frozen.line)
                else:
                    failures.append(frozen.line)
            else:
                print(
                    f"skip {_display_path(path)}  "
                    f"(frozen for {FROZEN_CELLS[name]['issue']}; "
                    f"pass --cell {name} to regenerate it anyway)"
                )
            continue
        text = build(name)
        if check:
            if not path.exists():
                failures.append(f"{name}: not committed (run without --check)")
            elif path.read_text() != text:
                failures.append(f"{name}: committed reference netlist is stale")
            else:
                print(f"ok {_display_path(path)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            print(f"wrote {_display_path(path)}")

    for line in failures:
        print(f"FAIL {line}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate in memory and fail if the committed reference differs",
    )
    parser.add_argument("--cell", help="build/check only this cell")
    parser.add_argument(
        "--corrupt",
        choices=["device-param", "topology", "passive-param"],
        help="emit a deliberately wrong reference (LVS negative control)",
    )
    parser.add_argument("-o", "--output", help="where to write a --corrupt reference")
    parser.add_argument(
        "--check-deck-hash",
        action="store_true",
        help=(
            "fail if committed layout/reports/*/drc.json disagree on "
            "provenance.deck.content_hash (ignores --cell/--corrupt/--output; "
            f"tolerates {', '.join(sorted(FROZEN_DECK_CELLS))} while frozen)"
        ),
    )
    args = parser.parse_args(argv)
    if args.check_deck_hash:
        failures = check_deck_hash_consistency()
        for line in failures:
            print(f"FAIL {line}")
        if not failures:
            print(f"ok {REPORTS_DIR.relative_to(REPO_ROOT)}/*/drc.json: one deck hash")
        return 1 if failures else 0
    try:
        return run(args.check, args.cell, args.corrupt, args.output)
    except ReferenceError as error:
        print(f"lvs_reference: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
