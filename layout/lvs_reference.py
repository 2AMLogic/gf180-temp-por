#!/usr/bin/env python3
"""Derive ``klt lvs`` reference netlists from the golden ``design/netlist/*.spice``.

    python3 layout/lvs_reference.py            # regenerate layout/cells/*.reference.spice
    python3 layout/lvs_reference.py --check    # verify committed references are current
    python3 layout/lvs_reference.py --cell por_comparator_bias_okb_inv
    python3 layout/lvs_reference.py --cell <name> --corrupt device-param -o /tmp/bad.spice

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

Both rewrites are *deliberate fidelity loss*: they make the reference describe
what the deck can actually see. A clean LVS here therefore proves device count,
device sizing, and signal-net topology -- **not** that wells and substrate are
correctly tied. Filed upstream as tool friction; tracked in ``layout/README.md``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAYOUT_DIR.parent
NETLIST_DIR = REPO_ROOT / "design" / "netlist"
CELLS_DIR = LAYOUT_DIR / "cells"

#: The deck ties every extracted NMOS body to this global net.
SUBSTRATE_NET = "vsubs"

#: gf180mcu PDK device subcircuit -> the curated deck's device class. The deck
#: draws one generic ``nfet``/``pfet`` class per polarity with no voltage-flavor
#: distinction, so every ``*_03v3`` core device maps onto the same pair.
DEVICE_CLASS = {
    "nfet_03v3": ("M", "nfet"),
    "pfet_03v3": ("M", "pfet"),
}

#: Layout cell -> how to build its reference netlist from a golden netlist.
#:
#: ``devices`` is in emission order and fixes ``M1``, ``M2``, ... numbering.
#: ``ports`` must match the layout's own extracted pin set (a labelled Metal1
#: net becomes a pin; the substrate net is always one). ``internal`` declares
#: the cell's remaining nets -- unlabelled in the layout, so anonymous in the
#: extracted netlist and matched by topology alone, but still spelled out here
#: so the undeclared-net guard below stays a real check rather than a rubber
#: stamp. ``wells`` groups the PMOS devices that share one drawn Nwell onto one
#: body net.
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
        # The cell's other three devices -- the sense divider XRTOP/XRBOT/XRHYS
        # (ppolyf_u_3k poly resistors) -- are outside the curated gf180mcu
        # deck's device coverage (klayout-tools#219, resistors #222) and are not
        # drawn; layout/build_cells.py's por_comparator docstring says why
        # drawing them anyway would be worse than leaving them out, and
        # layout/README.md records what that leaves unproven.
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
        # SNS and SNSB are the sense divider's taps. With XRTOP/XRBOT/XRHYS
        # outside the deck's device coverage, each keeps exactly one device
        # terminal in the MOS-only subset (XMINA's gate, XMHSW's drain) -- the
        # layout draws a routing track for each, ending at the reserved divider
        # region, so the compare still has two distinct nets to match.
        "internal": ["NBG", "SNS", "SNSB", "N1", "TN", "NA", "CMPO", "VDDA"],
        # Two drawn Nwells: one holds the parent cell's whole PMOS row, the
        # other is the one inside the instanced por_comparator_bias_okb_inv.
        "wells": {
            "NW1": ["XMLA", "XMLB", "XMENSRC", "XMI1P", "XMI2P"],
            "NW2": ["XMENP"],
        },
    },
    "bias_core": {
        "source": "bias_core.spice",
        "subckt": "bias_core",
        # Every MOS device in design/bias_core.sch -- 16 pfet + 18 nfet. The
        # cell's other 16 devices (10 vertical PNPs XQ1/XQ8A..H/XQR, 4 poly
        # resistors XR1/XR2/XRT/XRZ, 2 MiM caps XCC/XCOK) are outside the
        # curated gf180mcu deck's device coverage (klayout-tools#219/#222) and
        # are not drawn; see layout/build_cells.py's bias_core docstring and
        # layout/README.md for what that leaves unproven.
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
    # temp_core: the MOS subset of design/netlist/temp_core.spice. The cell's
    # vertical PNPs (XQ1/XQ8A..H), poly resistors (XR1/XR2*/XRISO/XRZ) and MiM
    # cap (XCC) have no device model in the curated gf180mcu extraction deck
    # (klayout-tools#219/#222), so they are drawn as sibling top cells and are
    # outside this compare -- see layout/README.md and layout/floorplan.md.
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
        # Every MOS device in design/por_output_chain.sch -- 14 pfet + 13 nfet.
        # The cell's other 2 devices (MiM caps XCDG, XCTIM) are outside the
        # curated gf180mcu deck's device coverage (klayout-tools#219) and are
        # not drawn; see layout/build_cells.py's por_output_chain docstring and
        # layout/README.md for what that leaves unproven. Unlike bias_core,
        # omitting them costs no *net*: NDG and TIM both carry MOS terminals
        # too, so every schematic net still exists on both sides of the compare.
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


def parse_devices(body: list[str]) -> dict[str, dict]:
    """Parse ``X<name> d g s b <model> k=v ...`` cards into a dict by name."""
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


def build(cell: str, corrupt: str | None = None) -> str:
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

    fingers = spec.get("fingers", {})

    cards: list[tuple[str, str, list[str], float, float]] = []
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
                (
                    f"{letter}{len(cards) + 1}",
                    klass,
                    list(nodes),
                    to_um(device["params"]["l"]),
                    to_um(device["params"]["w"]) / count,
                )
            )
            del finger

    for dummy in spec.get("dummies", []):
        klass = dummy["class"]
        drain, gate, source_node = dummy["nets"]
        body = SUBSTRATE_NET if klass == "nfet" else dummy["well"]
        cards.append(
            (
                f"MD{len(cards) + 1}",
                klass,
                [drain, gate, source_node, body],
                float(dummy["l"]),
                float(dummy["w"]),
            )
        )

    if corrupt == "device-param":
        name, klass, nodes, length, width = cards[0]
        cards[0] = (name, klass, nodes, length, width * 2.0)
    elif corrupt == "topology":
        if len(cards) < 2:
            raise ReferenceError(f"{cell}: topology control needs >= 2 devices")
        nodes = list(cards[0][2])
        nodes[2] = cards[1][2][2]  # re-tie device 1's source to device 2's
        cards[0] = (cards[0][0], cards[0][1], nodes, cards[0][3], cards[0][4])
    elif corrupt is not None:
        raise ReferenceError(f"unknown corruption {corrupt!r}")

    lines = [
        f"* {cell} -- klt lvs reference netlist"
        + (f" [NEGATIVE CONTROL: {corrupt}]" if corrupt else ""),
        f"* generated by layout/lvs_reference.py from design/netlist/{spec['source']}",
        "* Do not edit: edit the schematic, re-run design/netlist.py, re-run this.",
        f".SUBCKT {cell} {' '.join(ports)}",
    ]
    for name, klass, nodes, length, width in cards:
        lines.append(
            f"{name} {' '.join(nodes)} {klass} "
            f"L={format_um(length)} W={format_um(width)}"
        )
    lines.append(f".ENDS {cell}")
    return "\n".join(lines) + "\n"


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
        text = build(name)
        path = CELLS_DIR / f"{name}.reference.spice"
        if check:
            if not path.exists():
                failures.append(f"{name}: not committed (run without --check)")
            elif path.read_text() != text:
                failures.append(f"{name}: committed reference netlist is stale")
            else:
                print(f"ok {path.relative_to(REPO_ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            print(f"wrote {path.relative_to(REPO_ROOT)}")

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
        choices=["device-param", "topology"],
        help="emit a deliberately wrong reference (LVS negative control)",
    )
    parser.add_argument("-o", "--output", help="where to write a --corrupt reference")
    args = parser.parse_args(argv)
    try:
        return run(args.check, args.cell, args.corrupt, args.output)
    except ReferenceError as error:
        print(f"lvs_reference: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
