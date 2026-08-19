#!/usr/bin/env python3
"""Build a simulatable **post-layout netlist** for every extracted cell.

    python3 layout/postlayout.py --extract     # re-run klt (needs klt + the deck)
    python3 layout/postlayout.py               # regenerate layout/postlayout/
    python3 layout/postlayout.py --check       # committed artifacts are current?
    python3 layout/postlayout.py --cell temp_core ...

Two stages, split on what they need, so the second one is gated in CI:

1. ``--extract`` runs ``klt extract --parasitics`` and ``klt lvs`` and records
   both under ``layout/reports/<cell>/`` (``extracted-parasitics.spice`` +
   ``extracted-parasitics.json``). Needs ``klt`` and the ``gf180mcu`` deck. It
   never touches the committed ``extracted.spice`` / ``extract.json`` that
   ``layout/run_checks.sh`` keeps byte-stable for the DRC/LVS flow.
2. everything else is **stdlib only** -- it reads those two committed
   artifacts plus the golden netlists and writes
   ``layout/postlayout/<cell>.spice``. So ``--check`` is a real staleness gate
   that runs headless, with no PDK, no ``klt`` and no ngspice.

Why a translation step exists at all
------------------------------------

``klt extract``'s output is a *comparison* netlist, not a simulation netlist.
Everything below is a mechanical, verifiable rewrite of it -- no device is
invented, no topology is changed except where this file says so and the audit
records it:

* **device cards become PDK subcircuit calls.** ``M$1 ... nfet L=10U W=1U``
  is a raw MOS card naming the deck's device *class*; ngspice needs
  ``X$1 ... nfet_03v3 L=10u W=1u`` naming the PDK's own subcircuit. Same for
  the resistors (``ppolyf_u``/``ppolyf_u_1k``), the bipolars (one generic
  ``bjt`` class) and the MiM caps.

  ``klt extract --pdk`` will do this binding itself, and it was tried first.
  It is not used here for two measured reasons, both filed upstream. Its
  bound MOS card **drops the extractor's own measured** ``AS``/``AD``/
  ``PS``/``PD``, and the PDK subcircuit defaults all four to zero -- so a
  ``--pdk`` netlist simulates with no source/drain junction capacitance at
  all, which is the opposite of what a post-layout netlist is for
  (klayout-tools#695). And it leaves a recognised bipolar on the deck's
  generic ``bjt`` class (the deck models no implant, so it cannot tell a PNP
  from an NPN), which is the documented carve-out of klayout-tools#339. So
  the binding is done here, from the *unbound* card, which carries every
  parameter the extractor measured. It also keeps this stage free of any PDK
  install, which is the property that lets the whole ``layout/`` flow run
  where ``sim/`` cannot.
* **anonymous nets get their schematic names back.** The layout labels only a
  few nets, so most extracted nets are positional (``$10``). ``klt lvs``'s
  ``net_correspondence`` (klayout-tools#311) is an LVS-*verified* map from
  every extracted net to its reference-netlist name, so ``$10`` becomes
  ``SNS``. That is what makes the result readable by a testbench written
  against the schematic -- and it is read out of the tool, not solved here.
* **body nets get tied.** The extraction deck's connectivity stack does not
  join an Nwell, a substrate ring or a bipolar base well to the routing that
  reaches it (every ``lvs.json`` records this as ``device.body_unverified``).
  Those nets come out of the extractor **isolated**, which is honest for a
  compare and fatal for a simulation -- a floating well does not converge to
  anything meaningful. A MiM plate used to come out isolated too
  (klayout-tools#314, closed and fixed upstream); since #264 and #259 every
  drawn plate here is routed onto its own schematic node, so none needs a tie. Each one is tied to the net the *schematic*
  puts it on, derived from ``lvs_reference``'s own manifest rather than typed
  in here, and every tie is listed in ``layout/postlayout/AUDIT.md``.
* **two deck substitutions are undone.** ``klt``'s curated deck models one
  sheet-rho flavour per poly family and one MiM metal-stack variant, so a
  ``ppolyf_u_3k`` body is *recognised* as ``ppolyf_u_1k`` and an
  ``..._m3m4_...`` cap as ``..._m4m5_...`` (klayout-tools#315/#323). The
  drawn geometry is the schematic's either way; only the deck's name for it
  differs. The netlist emitted here instantiates the **schematic's** model at
  the **drawn** dimensions, so the resistance is the design's and the length
  is the layout's. Leaving the deck's name in would silently simulate this
  block on a PDK variant it is not built for.

What is real and what is not
----------------------------

Real, from the layout: every device and its dimensions, the whole topology,
and the first-order interconnect R/C on every net that has drawn routing.
Not real: the body ties above (schematic), and any device the schematic has
that the layout does not draw yet -- **today, none**. ``temp_core``'s ``XCC``
MiM cap was the last one and #259 drew it (DR-028), so every cell's audit row
and netlist header now reads "No ideal device: every golden device is drawn".
The splice machinery stays because it is manifest-derived, not because
anything uses it: the day a schematic gains a device the layout has not drawn
yet, it is spliced in ideal and flagged in the audit and in the netlist header
rather than silently missing.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

LAYOUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAYOUT_DIR.parent

sys.path.insert(0, str(LAYOUT_DIR))

import lvs_reference as ref  # noqa: E402

#: The cells that carry their own extraction reports. ``lvs_reference.CELLS``
#: also holds the flow's original 2-device proof cell, which is a fragment of
#: ``por_comparator`` rather than a circuit anything simulates.
CELLS = (
    "bias_core",
    "por_comparator",
    "por_output_chain",
    "temp_core",
    "temp_por_top",
)

DECK = "gf180mcu"
REPORTS_DIR = LAYOUT_DIR / "reports"
OUT_DIR = LAYOUT_DIR / "postlayout"

#: Deck device class -> the PDK subcircuit a simulator needs. The MOS classes
#: are the deck's; ``lvs_reference.DEVICE_CLASS`` holds the same pairing from
#: the schematic side and this is its inverse, restated here because this
#: module needs it in the other direction.
MOS_MODEL = {"nfet": "nfet_03v3", "pfet": "pfet_03v3"}

#: Extracted resistor class -> the golden-netlist model it was drawn from.
#: Inverse of :data:`lvs_reference.RESISTOR_CLASS`; asserted against each
#: cell's own golden netlist in :func:`resistor_models`, so a cell that ever
#: draws two schematic flavours onto one deck class fails loudly instead of
#: picking one.
RESISTOR_MODEL = {
    klass: model for model, (klass, _rho) in ref.RESISTOR_CLASS.items()
}

#: Extracted MiM class -> the golden-netlist model. Inverse of
#: :data:`lvs_reference.CAP_CLASS`.
CAP_MODEL = {klass: model for model, klass in ref.CAP_CLASS.items()}

#: Deck sheet resistance per extracted resistor class, in ohms/square. The
#: extracted card carries a resistance, not a length; the drawn length is
#: ``R / rho * width`` and is what the emitted card declares.
SHEET_RHO = {klass: rho for _model, (klass, rho) in ref.RESISTOR_CLASS.items()}

#: The parasitic network ``--parasitics`` adds: one series R from the net to a
#: synthetic ``<net>__par`` node and one C from that node to the substrate.
PAR_SUFFIX = "__par"

HEADER_NOTE = "GENERATED by layout/postlayout.py -- do not edit."


class PostlayoutError(Exception):
    """A cell cannot be translated without guessing. Never downgraded."""


class Card(NamedTuple):
    """One parsed card of the extracted netlist."""

    prefix: str            # M / Q / R / C
    name: str              # the extractor's own instance name, minus the prefix
    nodes: tuple[str, ...]  # layout net names, unescaped
    value: str | None      # resistance / capacitance, for the classes that have one
    klass: str | None      # deck device class, None for a parasitic R/C
    params: tuple[tuple[str, str], ...] = ()


# --- reading the extractor's output -------------------------------------------


def unescape(node: str) -> str:
    """``\\$26`` -> ``$26``.

    ``klt``'s SPICE writer escapes a positional net name with a backslash, and
    spells a merged-label net with ``|`` in the netlist but ``,`` in the JSON
    report and in ``klt lvs``'s correspondence -- so neither form joins to the
    report by name as written (klayout-tools#696). Both are normalised here,
    to the report's spelling, which is the side the correspondence is keyed on.
    """
    return node.replace("\\", "").replace("|", ",")


def logical_lines(text: str) -> list[str]:
    """Card lines with ``+`` continuations folded in, comments dropped.

    Thin adapter over ``layout/lvs_reference.py``'s ``logical_lines`` -- the
    one shared parser for this SPICE primitive (see that module's docstring).
    Only the exception type is translated, so callers keep seeing this
    module's own ``PostlayoutError``.
    """
    try:
        return ref.logical_lines(text)
    except ref.ReferenceError as exc:
        raise PostlayoutError("continuation line with nothing to continue") from exc


def parse_extracted(text: str) -> tuple[str, list[str], list[Card]]:
    """Split an extracted netlist into ``(top, pins, cards)``.

    Deliberately strict: an unrecognised card is an error, not a skipped line.
    A silently dropped device would produce a netlist that simulates and lies.
    """
    top = ""
    pins: list[str] = []
    cards: list[Card] = []
    for line in logical_lines(text):
        fields = line.split()
        head = fields[0]
        upper = head.upper()
        if upper == ".SUBCKT":
            top = fields[1]
            pins = [unescape(f) for f in fields[2:]]
            continue
        if upper == ".ENDS":
            continue
        if upper.startswith("."):
            raise PostlayoutError(f"unexpected control line {line!r}")
        prefix, name = head[0].upper(), head[1:]
        nodes = tuple(unescape(f) for f in fields[1:])
        if prefix == "M":
            # M<n> d g s b <class> L=.. W=.. AS=.. AD=.. PS=.. PD=..
            params = tuple(
                tuple(field.split("=", 1)) for field in fields[6:]
            )
            cards.append(Card("M", name, nodes[:4], None, fields[5], params))
        elif prefix == "Q":
            # Q<n> c b e <class> AE=.. PE=.. ...
            params = tuple(
                tuple(field.split("=", 1)) for field in fields[5:]
            )
            cards.append(Card("Q", name, nodes[:3], None, fields[4], params))
        elif prefix == "R" and len(fields) == 6:
            # R<n> a b bulk <ohms> <class>  -- a drawn poly resistor
            cards.append(Card("R", name, nodes[:3], fields[4], fields[5]))
        elif prefix == "R" and len(fields) == 4:
            # R<net> <net> <net>__par <ohms>  -- a parasitic
            cards.append(Card("R", name, nodes[:2], fields[3], None))
        elif prefix == "C" and len(fields) == 5:
            # C<n> a b <farads> <class>  -- a drawn MiM capacitor
            cards.append(Card("C", name, nodes[:2], fields[3], fields[4]))
        elif prefix == "C" and len(fields) == 4:
            # C<net> <net>__par <substrate> <farads>  -- a parasitic
            cards.append(Card("C", name, nodes[:2], fields[3], None))
        else:
            raise PostlayoutError(f"unrecognised card {line!r}")
    if not top:
        raise PostlayoutError("no .SUBCKT line in the extracted netlist")
    return top, pins, cards


# --- what the schematic says the layout's synthetic nets are ------------------


def golden(cell: str) -> tuple[str, list[str]]:
    """``(text, body)`` of the golden netlist subcircuit one cell is drawn from."""
    spec = ref.CELLS[cell]
    text = (ref.NETLIST_DIR / spec["source"]).read_text()
    return text, ref.subckt_body(text, spec["subckt"])


def _unique(values: list[str], what: str, cell: str) -> str:
    distinct = sorted(set(values))
    if len(distinct) != 1:
        raise PostlayoutError(
            f"{cell}: {what} resolves to {distinct or ['nothing']}; the "
            "post-layout tie is only well defined when the schematic agrees "
            "on one net"
        )
    return distinct[0]


def leaf_body_ties(cell: str, rename=None) -> dict[str, str]:
    """Reference net -> the schematic net it stands for, for one leaf cell.

    Every key here is a net the extraction produces **isolated**, because the
    deck's connectivity stack does not reach it: the substrate global, each
    drawn Nwell and the bipolars' shared base well. The value is read out of
    the golden netlist through ``lvs_reference``'s own manifest, so a
    schematic change moves the tie with it.

    Every drawn MiM plate used to need an entry here too (a synthesized,
    per-instance isolated net, e.g. ``XCDG.NDG``), before #264 routed each
    cap's plates onto the schematic nodes their golden card names directly --
    now that ``lvs_reference.cap_plate_nets`` returns those nodes rather than
    a synthesized stand-in, a plate's own reference net already *is* the
    schematic net it stands for, so there is nothing left to tie.
    """
    spec = ref.CELLS[cell]
    _text, body = golden(cell)
    devices = ref.parse_devices(body)
    passives = ref.parse_passives(body)

    def out(net: str) -> str:
        return net if rename is None else rename(net)

    ties: dict[str, str] = {}

    # The substrate global: every NMOS body, every drawn resistor's bulk and
    # every bipolar collector sit on it in the reference.
    substrate = [
        device["nodes"][3]
        for name, device in devices.items()
        if ref.DEVICE_CLASS[device["model"]][1] == "nfet" and name in spec["devices"]
    ]
    substrate += [
        device["nodes"][2]
        for name, device in passives.items()
        if device["kind"] == "resistor" and name in spec.get("resistors", [])
    ]
    substrate += [
        device["nodes"][0]
        for name, device in passives.items()
        if device["kind"] == "bipolar" and name in spec.get("bipolars", [])
    ]
    if substrate:
        # ``vsubs`` is the deck's global and build_assembly never renames it,
        # so its key is unrenamed while its value follows the instance.
        ties[ref.SUBSTRATE_NET] = out(_unique(substrate, "the substrate net", cell))

    for well, names in spec.get("wells", {}).items():
        bulks = [devices[name]["nodes"][3] for name in names]
        ties[out(well)] = out(_unique(bulks, f"well {well}", cell))

    bjt_well = spec.get("bjt_well")
    if bjt_well:
        bases = [
            passives[name]["nodes"][1] for name in spec.get("bipolars", [])
        ]
        ties[out(bjt_well)] = out(_unique(bases, f"bipolar well {bjt_well}", cell))

    return ties


def body_ties(cell: str) -> dict[str, str]:
    """:func:`leaf_body_ties` for a leaf cell, or for every instance of an
    assembly, under the same renaming ``lvs_reference`` builds it with."""
    spec = ref.CELLS[cell]
    if "assembly" not in spec:
        return leaf_body_ties(cell)
    ties: dict[str, str] = {}
    for _inst, sub_cell, rename in ref.instance_renames(cell):
        ties.update(leaf_body_ties(sub_cell, rename=rename))
    return ties


def undrawn_capacitors(cell: str) -> list[dict]:
    """Golden MiM caps this cell's layout does not draw yet.

    ``lvs_reference``'s manifest lists the drawn ones; anything the golden
    netlist has and the manifest does not is reserved floor area, and is the
    only thing this module ever splices in ideal. **Empty for every cell since
    #259** (DR-028) drew ``temp_core``'s ``XCC``, the last undrawn golden
    device in this block -- kept, like the resistor and bipolar equivalents,
    so that a schematic that gains a device the layout has not caught up with
    is disclosed rather than dropped.
    """
    spec = ref.CELLS[cell]
    out: list[dict] = []
    if "assembly" in spec:
        for inst, sub_cell, rename in ref.instance_renames(cell):
            for cap in undrawn_capacitors(sub_cell):
                out.append(
                    dict(cap, instance=inst, nodes=[rename(n) for n in cap["nodes"]])
                )
        return out
    _text, body = golden(cell)
    drawn = set(spec.get("caps", []))
    for name, cap in ref.parse_capacitors(body).items():
        if name in drawn:
            continue
        out.append(
            {
                "name": name,
                "instance": None,
                "model": cap["model"],
                "nodes": list(cap["nodes"]),
                "c_width": cap["params"]["c_width"],
                "c_length": cap["params"]["c_length"],
                "units": ref.cap_units(cap),
            }
        )
    return out


def resistor_models(cell: str) -> dict[str, tuple[str, float]]:
    """Extracted resistor class -> ``(golden model, drawn width in um)``.

    Both come from the cell's own golden netlist rather than from
    :data:`RESISTOR_MODEL` alone, so the substitution this undoes is asserted
    against the schematic every run: a cell that draws two schematic flavours
    onto one deck class, or one flavour at two widths, fails here instead of
    being emitted at whichever value happened to be first.
    """
    spec = ref.CELLS[cell]
    if "assembly" in spec:
        merged: dict[str, tuple[str, float]] = {}
        for _inst, sub_cell, _rename in ref.instance_renames(cell):
            for klass, entry in resistor_models(sub_cell).items():
                if merged.setdefault(klass, entry) != entry:
                    raise PostlayoutError(
                        f"{cell}: instances disagree about {klass}: "
                        f"{merged[klass]} vs {entry}"
                    )
        return merged
    _text, body = golden(cell)
    passives = ref.parse_passives(body)
    out: dict[str, tuple[str, float]] = {}
    for name in spec.get("resistors", []):
        device = passives[name]
        klass, _rho = ref.RESISTOR_CLASS[device["model"]]
        entry = (device["model"], ref.to_um(device["params"]["r_width"]))
        if out.setdefault(klass, entry) != entry:
            raise PostlayoutError(
                f"{cell}: resistors of deck class {klass} are drawn as "
                f"{out[klass]} and {entry}; the post-layout model/width is "
                "only well defined when they agree"
            )
    return out


def bipolar_model(cell: str) -> str | None:
    """The one golden bipolar model this cell draws, or ``None``.

    The deck recognises a single generic ``bjt`` class with no implant, so the
    PDK device name cannot be read back off the extraction. It is taken from
    the schematic, and the emitter area the extractor measured is checked
    against the name (:func:`lvs_reference.emitter_area_um2`) before use -- so
    a layout drawn at the wrong emitter window fails here rather than
    simulating as the size the schematic wished for.
    """
    spec = ref.CELLS[cell]
    if "assembly" in spec:
        models = {
            model
            for _inst, sub_cell, _rename in ref.instance_renames(cell)
            if (model := bipolar_model(sub_cell))
        }
        if len(models) > 1:
            raise PostlayoutError(f"{cell}: more than one bipolar model {models}")
        return next(iter(models), None)
    names = spec.get("bipolars", [])
    if not names:
        return None
    _text, body = golden(cell)
    passives = ref.parse_passives(body)
    return _unique(
        [passives[name]["model"] for name in names], "the bipolar model", cell
    )


# --- net naming ---------------------------------------------------------------


def sanitize(net: str) -> str:
    """A reference net name as a flat SPICE node.

    An assembly's reference names carry the instance path (``xbias.NOKX``);
    ``.`` is ngspice's own hierarchy separator, so it becomes ``__``.
    """
    return net.replace(".", "__")


def instance(name: str) -> str:
    """The extractor's instance name as an ngspice subcircuit reference.

    ``klt`` writes positional instance names with a leading ``$``
    (``M$1``, ``R$19``), which ngspice reads as the start of an end-of-line
    comment rather than rejecting -- it silently builds a different element
    (klayout-tools#312). The ``$`` is dropped; the numbering is the
    extractor's own and is unique across every class in a cell, which
    :func:`emit_cards` asserts rather than assumes.
    """
    return "X" + name.replace("$", "")


def canonical_case(cell: str) -> dict[str, str]:
    """UPPERCASE reference net -> the reference netlist's own spelling.

    ``klt lvs`` reports correspondence against the netlist reader's upcased
    names (``RESETN``, ``VSUBS``), which would make the post-layout netlist
    read differently from the schematic for no reason. The reference netlist
    ``lvs_reference`` generates is the authority for the spelling.
    """
    nets: set[str] = set()
    for line in ref.logical_lines(ref.build(cell)):
        fields = line.split()
        if fields[0].upper().startswith(".SUBCKT"):
            nets.update(fields[2:])
        elif fields[0][0].upper() in "MQRC":
            count = {"M": 4, "Q": 3, "R": 3, "C": 2}[fields[0][0].upper()]
            nets.update(fields[1 : 1 + count])
    return {net.upper(): net for net in nets}


def net_map(cell: str, correspondence: dict[str, str]) -> dict[str, str]:
    """Layout net -> the node name the post-layout netlist uses for it.

    Three composed steps, each of which is checked: the LVS-verified
    correspondence, the reference netlist's own spelling, then the body ties
    that put an isolated well/plate/substrate net onto the net the schematic
    says it is.
    """
    spelling = canonical_case(cell)
    ties = {net.upper(): tied for net, tied in body_ties(cell).items()}
    mapping: dict[str, str] = {}
    for layout_net, reference_net in correspondence.items():
        if reference_net is None:
            raise PostlayoutError(
                f"{cell}: extracted net {layout_net!r} has no reference net; "
                "the LVS compare did not match every net"
            )
        key = reference_net.upper()
        target = ties.get(key, spelling.get(key, reference_net))
        mapping[layout_net] = sanitize(target)
    return mapping


# --- emission -----------------------------------------------------------------


def _num(text: str) -> float:
    return float(text)


def emit_cards(cell: str, cards: list[Card], names: dict[str, str]) -> tuple[
    list[str], dict[str, int]
]:
    """Every extracted card, as a PDK-model card. Also returns a class census."""
    resistors = resistor_models(cell)
    bjt_model = bipolar_model(cell)
    census: dict[str, int] = {}
    devices: list[str] = []
    parasitics: list[str] = []

    def node(net: str) -> str:
        if net not in names:
            raise PostlayoutError(
                f"{cell}: extracted net {net!r} is not in the LVS net "
                "correspondence -- the netlist and the compare disagree"
            )
        return names[net]

    for card in cards:
        if card.prefix == "M":
            model = MOS_MODEL.get(card.klass)
            if model is None:
                raise PostlayoutError(f"{cell}: unknown MOS class {card.klass!r}")
            params = {key.lower(): value.lower() for key, value in card.params}
            drain, gate, source, bulk = (node(n) for n in card.nodes)
            devices.append(
                f"{instance(card.name)} {drain} {gate} {source} {bulk} {model} "
                f"L={params['l']} W={params['w']} nf=1 "
                f"ad={params['ad']} as={params['as']} "
                f"pd={params['pd']} ps={params['ps']} m=1"
            )
            census[card.klass] = census.get(card.klass, 0) + 1
        elif card.prefix == "Q":
            if bjt_model is None:
                raise PostlayoutError(f"{cell}: a bipolar was extracted but the "
                                      "schematic declares none")
            params = {key.upper(): value for key, value in card.params}
            # ``AE=100P`` is the drawn emitter window in um^2 (the deck writes
            # micron-squared with SPICE's pico suffix). The schematic's device
            # name carries the same number, so a layout drawn at the wrong
            # window fails here instead of simulating as the size the
            # schematic wished for.
            drawn_um2 = _num(params["AE"].lower().rstrip("p"))
            expected = ref.emitter_area_um2(bjt_model)
            if abs(drawn_um2 - expected) > 1e-6:
                raise PostlayoutError(
                    f"{cell}: extracted emitter area {drawn_um2} um^2 does not "
                    f"match {bjt_model}'s {expected} um^2"
                )
            collector, base, emitter = (node(n) for n in card.nodes)
            devices.append(
                f"{instance(card.name)} {collector} {base} {emitter} {bjt_model}"
            )
            census[card.klass] = census.get(card.klass, 0) + 1
        elif card.prefix == "R" and card.klass:
            model, width_um = resistors.get(card.klass, (None, None))
            if model is None:
                raise PostlayoutError(
                    f"{cell}: extracted a {card.klass} resistor the schematic "
                    "does not declare"
                )
            length_um = _num(card.value) / SHEET_RHO[card.klass] * width_um
            head, tail, bulk = (node(n) for n in card.nodes)
            devices.append(
                f"{instance(card.name)} {head} {tail} {bulk} {model} "
                f"r_width={ref.format_um(width_um).lower()} "
                f"r_length={ref.format_um(length_um).lower()}"
            )
            census[card.klass] = census.get(card.klass, 0) + 1
        elif card.prefix == "C" and card.klass:
            model = CAP_MODEL.get(card.klass)
            if model is None:
                raise PostlayoutError(f"{cell}: unknown cap class {card.klass!r}")
            side_um = (_num(card.value) / ref.MIM_AREA_CAP_F_UM2) ** 0.5
            plate_a, plate_b = (node(n) for n in card.nodes)
            devices.append(
                f"{instance(card.name)} {plate_a} {plate_b} {model} "
                f"c_width={ref.format_um(side_um).lower()} "
                f"c_length={ref.format_um(side_um).lower()}"
            )
            census[card.klass] = census.get(card.klass, 0) + 1
        else:
            head, tail = (node(n) for n in card.nodes)
            parasitics.append(
                f"{card.prefix}{card.name} {head} {tail} {card.value}"
            )
    emitted = [line.split()[0] for line in devices + parasitics]
    clashes = sorted({name for name in emitted if emitted.count(name) > 1})
    if clashes:
        raise PostlayoutError(
            f"{cell}: {len(clashes)} instance name(s) collide after dropping "
            f"the extractor's '$', e.g. {clashes[:3]} -- two cards would "
            "silently become one"
        )
    return devices + [""] + parasitics, census


def parasitic_nodes(cards: list[Card], names: dict[str, str]) -> dict[str, str]:
    """``$10__par`` -> a node name derived from ``$10``'s *reference* name.

    Deliberately not derived from the tied circuit net: two isolated nets can
    tie to the same circuit net (an Nwell and ``VDD``), and their parasitic
    nodes must stay distinct or the two lumped caps collapse into one.
    """
    extra: dict[str, str] = {}
    for card in cards:
        for net in card.nodes:
            if not net.endswith(PAR_SUFFIX) or net in names:
                continue
            base = net[: -len(PAR_SUFFIX)]
            if base not in names:
                raise PostlayoutError(
                    f"parasitic node {net!r} has no parent net {base!r}"
                )
            extra[net] = f"{names[base]}{PAR_SUFFIX}"
    return extra


def ideal_cards(cell: str) -> tuple[list[str], list[dict]]:
    """The undrawn golden devices this netlist splices in, and their record."""
    lines: list[str] = []
    records: list[dict] = []
    for index, cap in enumerate(undrawn_capacitors(cell), start=1):
        nodes = [sanitize(net) for net in cap["nodes"]]
        for unit in range(1, cap["units"] + 1):
            tag = f"IDEAL{index}" if cap["units"] == 1 else f"IDEAL{index}_{unit}"
            lines.append(
                f"X{tag} {nodes[0]} {nodes[1]} {cap['model']} "
                f"c_width={cap['c_width']} c_length={cap['c_length']}"
            )
        records.append(
            {
                "name": cap["name"],
                "instance": cap["instance"],
                "model": cap["model"],
                "nodes": nodes,
                "units": cap["units"],
                "why": "not drawn in this cell's layout -- reserved floor area",
            }
        )
    return lines, records


def coverage(report: dict) -> dict:
    """The klayout-tools#283 sanity check: how much of the net graph carries
    parasitics, reported per cell so a silent-zero regression is visible."""
    parasitics = report.get("parasitics") or {}
    nets = parasitics.get("nets") or []
    total = report["net_count"]
    return {
        "nets_total": total,
        "nets_with_parasitics": len(nets),
        "fraction": round(len(nets) / total, 4) if total else 0.0,
        "total_resistance_ohm": parasitics.get("total_resistance_ohm"),
        "total_capacitance_ff": parasitics.get("total_capacitance_ff"),
    }


def build_netlist(cell: str) -> tuple[str, dict]:
    """The post-layout netlist for one cell, plus its audit record."""
    spice_path, json_path = artifact_paths(cell)
    if not spice_path.exists() or not json_path.exists():
        raise PostlayoutError(
            f"{cell}: no committed extraction at {spice_path} -- run "
            "`python3 layout/postlayout.py --extract` (needs klt)"
        )
    record = json.loads(json_path.read_text())
    text = spice_path.read_text()
    if ref.sha256_bytes(text.encode()) != record["netlist_sha256"]:
        raise PostlayoutError(
            f"{cell}: {spice_path.name} does not match the sha256 recorded in "
            f"{json_path.name}; re-run --extract"
        )

    top, _pins, cards = parse_extracted(text)
    if top != cell:
        raise PostlayoutError(f"{cell}: extracted netlist's top cell is {top!r}")

    names = net_map(cell, record["net_correspondence"])
    names.update(parasitic_nodes(cards, names))
    body_lines, census = emit_cards(cell, cards, names)
    ideal_lines, ideal_records = ideal_cards(cell)

    text_golden, _body = golden(cell)
    ports = ref.subckt_ports(text_golden, ref.CELLS[cell]["subckt"])
    emitted_nodes = {
        field
        for line in body_lines + ideal_lines
        if line
        for field in line.split()[1:4]
    }
    missing = [port for port in ports if port not in emitted_nodes]
    if missing:
        raise PostlayoutError(
            f"{cell}: schematic port(s) {missing} are on no device in the "
            "post-layout netlist"
        )

    ties = {sanitize(net): sanitize(tied) for net, tied in body_ties(cell).items()}
    audit = {
        "cell": cell,
        "device_counts": census,
        "device_total": sum(census.values()),
        "parasitic_cards": sum(1 for card in cards if card.klass is None),
        "coverage": record["coverage"],
        "ties": ties,
        "ideal_devices": ideal_records,
        "substitutions": substitutions(cell, census),
        "ports": ports,
        "provenance": record["provenance"],
        "lvs_status": record["lvs"]["status"],
    }

    stats = record["coverage"]
    lines = [
        f"* {cell} -- post-layout netlist",
        f"* {HEADER_NOTE}",
        "*",
        "* FROM THE LAYOUT: every device and its dimensions, the whole",
        f"*   topology, and first-order interconnect R/C on "
        f"{stats['nets_with_parasitics']}/{stats['nets_total']} nets",
        f"*   (sigma {stats['total_capacitance_ff']:.1f} fF). "
        f"klt {record['provenance']['klt_version']}, deck {DECK},",
        f"*   GDS sha256 {record['provenance']['gds_sha256'][:16]}...",
        "* Net names are the schematic's, restored through klt lvs's own net",
        f"*   correspondence -- {record['lvs']['status']}, "
        f"{record['lvs']['nets_matched']}/{record['lvs']['nets_layout']} nets,"
        " every one paired.",
        "*",
        "* NOT FROM THE LAYOUT -- see layout/postlayout/AUDIT.md:",
        f"*   {len(ties)} body/plate net(s) tied to the net the schematic puts",
        "*   them on. The extraction deck's connectivity stack does not reach",
        "*   an Nwell, a substrate ring, a bipolar base well or a MiM plate,",
        "*   so they extract isolated and would otherwise float.",
    ]
    if ideal_records:
        for entry in ideal_records:
            lines.append(
                f"*   {entry['name']} ({entry['model']}) is IDEAL -- "
                f"{entry['why']}."
            )
    else:
        lines.append("*   No ideal device: every golden device is drawn.")
    lines += [
        "*",
        f".subckt {cell} {' '.join(ports)}",
    ]
    if ideal_lines:
        lines += ["", "* --- schematic-ideal, not drawn ---"] + ideal_lines
    lines += ["", "* --- drawn devices ---"]
    lines += body_lines
    lines += [f".ends {cell}", ""]
    return "\n".join(lines), audit


def substitutions(cell: str, census: dict[str, int]) -> list[dict]:
    """The deck substitutions this netlist undoes.

    Driven by the cell's own device census rather than by the class tables, so
    a cell that draws none of a class does not advertise a substitution it
    never made.
    """
    out: list[dict] = []
    for klass, (model, width_um) in sorted(resistor_models(cell).items()):
        if klass != model and census.get(klass):
            out.append(
                {
                    "kind": "resistor sheet-rho flavour",
                    "extracted_as": klass,
                    "emitted_as": model,
                    "count": census[klass],
                    "width_um": width_um,
                    "why": "klayout-tools#323 -- the deck wires the PDK's "
                           "default POLY_RES option only; the drawn geometry "
                           "is the schematic's either way",
                }
            )
    for klass, model in sorted(CAP_MODEL.items()):
        if klass != model and census.get(klass):
            out.append(
                {
                    "kind": "MiM metal-stack variant",
                    "extracted_as": klass,
                    "emitted_as": model,
                    "count": census[klass],
                    "why": "klayout-tools#315 -- the deck models one stack "
                           "variant; both are the same 2.0 fF/um^2 device",
                }
            )
    return out


# --- stage 1: run klt ---------------------------------------------------------


def artifact_paths(cell: str) -> tuple[Path, Path]:
    directory = REPORTS_DIR / cell
    return (
        directory / "extracted-parasitics.spice",
        directory / "extracted-parasitics.json",
    )


def run_extraction(cell: str) -> None:
    """``klt extract --parasitics`` + ``klt lvs``, recorded side by side."""
    gds = LAYOUT_DIR / "cells" / f"{cell}.gds"
    request = LAYOUT_DIR / "cells" / f"{cell}.lvs.json"
    spice_path, json_path = artifact_paths(cell)
    spice_path.parent.mkdir(parents=True, exist_ok=True)

    flags = []
    if json.loads(request.read_text())["layout"].get("top_cell_pins", False):
        flags.append("--top-cell-pins")

    extract = subprocess.run(
        [
            "klt", "extract", str(gds), "--deck", DECK,
            "-o", str(spice_path), "--top", cell,
            *flags, "--parasitics", "--format", "json",
        ],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if extract.returncode != 0:
        raise PostlayoutError(f"{cell}: klt extract failed\n{extract.stderr}")
    report = json.loads(extract.stdout)

    lvs = subprocess.run(
        ["klt", "lvs", str(request), "--format", "json"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if lvs.returncode != 0:
        raise PostlayoutError(f"{cell}: klt lvs failed\n{lvs.stderr}")
    compare = json.loads(lvs.stdout)
    if compare["status"] != "match":
        raise PostlayoutError(f"{cell}: klt lvs reports {compare['status']}")

    stats = coverage(report)
    if not stats["nets_with_parasitics"]:
        # The exact shape of klayout-tools#283: a run that reports success and
        # loads nothing. Refusing to record it is what keeps a regression loud.
        raise PostlayoutError(f"{cell}: --parasitics loaded zero nets")

    correspondence = {
        entry["layout"]: entry["reference"] for entry in compare["net_correspondence"]
    }
    extracted_nets = {net["name"] for net in report["nets"]}
    missing = sorted(extracted_nets - set(correspondence))
    if missing:
        raise PostlayoutError(
            f"{cell}: {len(missing)} extracted net(s) absent from the LVS "
            f"correspondence, e.g. {missing[:5]}"
        )

    body = spice_path.read_text()
    record = {
        "schema_version": 1,
        "cell": cell,
        "note": "recorded by layout/postlayout.py --extract; the committed "
                "extracted.spice/extract.json of the DRC/LVS flow are not "
                "touched by this run",
        "netlist_path": str(spice_path.relative_to(REPO_ROOT)),
        "netlist_sha256": ref.sha256_bytes(body.encode()),
        "top_cell_pins": bool(flags),
        "device_count": report["device_count"],
        "device_counts": report["device_counts"],
        "net_count": report["net_count"],
        "pin_count": report["pin_count"],
        "coverage": stats,
        "warnings": report.get("warnings", []),
        "provenance": {
            "klt_version": report["provenance"]["klt_version"],
            "klayout_version": report["provenance"]["klayout_version"],
            "deck": report["provenance"]["deck"],
            "gds_sha256": ref.sha256_bytes((REPO_ROOT / gds).read_bytes()),
        },
        "lvs": {
            "status": compare["status"],
            "nets_layout": compare["counts"]["nets"]["layout"],
            "nets_matched": compare["counts"]["nets"]["matched"],
            "devices_matched": compare["counts"]["devices"]["matched"],
            "category_counts": compare["category_counts"],
        },
        "net_correspondence": correspondence,
    }
    json_path.write_text(json.dumps(record, indent=2, sort_keys=False) + "\n")


# --- audit document -----------------------------------------------------------


def audit_markdown(audits: list[dict]) -> str:
    lines = [
        "# Post-layout netlists — what is the layout's and what is not",
        "",
        f"<!-- {HEADER_NOTE} -->",
        "",
        "One netlist per extracted cell, in `layout/postlayout/<cell>.spice`,",
        "built by `layout/postlayout.py` from `klt extract --parasitics` plus",
        "`klt lvs`'s net correspondence. Read `layout/postlayout.py`'s module",
        "docstring for how, and `layout/README.md` → \"Post-layout netlists\"",
        "for where this sits in the flow.",
        "",
        "## Devices and parasitic coverage",
        "",
        "| cell | drawn devices | ideal (not drawn) | parasitic R/C cards | "
        "nets with parasitics | ΣR | ΣC |",
        "|---|---|---|---|---|---|---|",
    ]
    for audit in audits:
        stats = audit["coverage"]
        ideal = sum(entry["units"] for entry in audit["ideal_devices"]) or 0
        lines.append(
            f"| `{audit['cell']}` | {audit['device_total']} | {ideal} | "
            f"{audit['parasitic_cards']} | "
            f"{stats['nets_with_parasitics']}/{stats['nets_total']} "
            f"({stats['fraction'] * 100:.1f} %) | "
            f"{stats['total_resistance_ohm']:.0f} Ω | "
            f"{stats['total_capacitance_ff']:.1f} fF |"
        )
    lines += [
        "",
        "`nets with parasitics` is the klayout-tools#283 sanity check: a run",
        "that silently loaded nothing reads 0 here, and `--extract` refuses to",
        "record it. The nets without parasitics are the ones with no drawn",
        "interconnect of their own — isolated well/plate nets and the",
        "substrate global.",
        "",
        "## Per-cell device census",
        "",
        "| cell | " + " | ".join(sorted({
            klass for audit in audits for klass in audit["device_counts"]
        })) + " |",
    ]
    classes = sorted({klass for audit in audits for klass in audit["device_counts"]})
    lines.append("|---" * (len(classes) + 1) + "|")
    for audit in audits:
        cells = " | ".join(
            str(audit["device_counts"].get(klass, 0)) for klass in classes
        )
        lines.append(f"| `{audit['cell']}` | {cells} |")

    lines += [
        "",
        "## What is not the layout's",
        "",
        "### Body, well and plate ties",
        "",
        "The extraction deck's connectivity stack does not join an Nwell, a",
        "substrate ring or a bipolar base well to the routing that reaches",
        "it — every `lvs.json` records that as `device.body_unverified`.",
        "Those nets are extracted **isolated**, which is honest for a",
        "compare and unsimulatable. Each is tied to the net the schematic puts",
        "it on, derived from `lvs_reference`'s manifest. MiM plates used to",
        "need the same treatment (klayout-tools#314, **closed and fixed**",
        "upstream); every drawn plate in this block is now routed onto its",
        "own schematic node (#264, #259), so none is tied here:",
        "",
    ]
    for audit in audits:
        lines.append(f"* **`{audit['cell']}`** — {len(audit['ties'])} ties:")
        for net, tied in sorted(audit["ties"].items()):
            lines.append(f"  * `{net}` → `{tied}`")
    lines += [
        "",
        "### Deck substitutions undone",
        "",
        "| cell | devices | extracted as | emitted as | why |",
        "|---|---|---|---|---|",
    ]
    for audit in audits:
        for entry in audit["substitutions"]:
            lines.append(
                f"| `{audit['cell']}` | {entry['count']} | "
                f"`{entry['extracted_as']}` | "
                f"`{entry['emitted_as']}` | {entry['why']} |"
            )
    lines += [
        "",
        "The drawn geometry is the schematic's in both cases; only the deck's",
        "*name* for it differs. Emitting the deck's name would simulate this",
        "block on a PDK option it is not built for — a 3× error on every",
        "high-sheet-rho resistor.",
        "",
        "### Devices that are not drawn at all",
        "",
    ]
    ideal_any = False
    for audit in audits:
        for entry in audit["ideal_devices"]:
            ideal_any = True
            where = f"`{audit['cell']}`" + (
                f" instance `{entry['instance']}`" if entry["instance"] else ""
            )
            units = "" if entry["units"] == 1 else f" x{entry['units']}"
            lines.append(
                f"* **{where} — `{entry['name']}`** (`{entry['model']}`"
                f"{units}) on `{entry['nodes'][0]}` / `{entry['nodes'][1]}`: "
                f"{entry['why']}. Spliced in ideal, so any claim taken on this "
                "netlist that depends on it is a schematic claim, not a "
                "post-layout one."
            )
    if not ideal_any:
        lines.append("* none — every golden device is drawn in every cell.")
    lines.append("")
    return "\n".join(lines)


# --- driver -------------------------------------------------------------------


def generate(cells: list[str]) -> dict[Path, str]:
    """Every stage-2 artifact, as ``path -> content``."""
    artifacts: dict[Path, str] = {}
    audits: list[dict] = []
    for cell in cells:
        text, audit = build_netlist(cell)
        artifacts[OUT_DIR / f"{cell}.spice"] = text
        audits.append(audit)
    artifacts[OUT_DIR / "audit.json"] = (
        json.dumps({"schema_version": 1, "cells": audits}, indent=2) + "\n"
    )
    artifacts[OUT_DIR / "AUDIT.md"] = audit_markdown(audits)
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cell", action="append", choices=CELLS,
                        help="restrict to one cell (repeatable)")
    parser.add_argument("--extract", action="store_true",
                        help="re-run klt extract --parasitics / klt lvs first")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed artifacts reproduce exactly")
    args = parser.parse_args(argv)

    cells = args.cell or list(CELLS)
    try:
        if args.extract:
            for cell in cells:
                run_extraction(cell)
                print(f"ok   extracted {cell}")
        # audit.json / AUDIT.md are whole-repo documents, so they are only
        # written when every cell was regenerated.
        artifacts = generate(list(CELLS) if not args.cell else cells)
        if args.cell:
            artifacts = {
                path: text for path, text in artifacts.items()
                if path.suffix == ".spice"
            }
    except (PostlayoutError, ref.ReferenceError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.check:
        stale = [
            path for path, text in artifacts.items()
            if not path.exists() or path.read_text() != text
        ]
        for path in sorted(stale):
            print(f"STALE {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        if stale:
            print(
                "regenerate with: python3 layout/postlayout.py", file=sys.stderr
            )
            return 1
        print(f"ok   {len(artifacts)} post-layout artifact(s) are current")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, text in sorted(artifacts.items()):
        path.write_text(text)
        print(f"ok   wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
