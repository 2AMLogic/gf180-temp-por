#!/usr/bin/env python3
"""Tests `sim/pex/measure.py`'s three SPICE/LVS joins (#643).

`measure.py` keeps no copy of the primitives `layout/` already owns: the
`.subckt` port list comes from `lvs_reference.subckt_ports` (which joins `+`
continuations), every join against a `klt lvs` net correspondence goes
through `postlayout.correspondence_key` on both sides, and the bipolar
rewrite takes the substrate net and the emitter area from `lvs_reference`
instead of a hardcoded `vsubs` / `AE=100P`.

The cases that pin the fix:

- a `.subckt` header wrapped onto `+` lines, in the schematic and in the
  extracted netlist, keeps every pin -- splitting the first physical line
  alone drops the wrapped ones;
- a correspondence whose reference names keep the assembly's `.` (klt 0.2.0's
  spelling; the pinned klt writes `_`) still resolves every body tie.

They run on the committed schematic netlists and golden references, with a
`subprocess.run` stand-in for `klt lvs`: no PDK, no ngspice, no klt.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "sim" / "pex"))
sys.path.insert(0, str(REPO / "layout"))

import lvs_reference  # noqa: E402
import measure  # noqa: E402
import postlayout  # noqa: E402

TOP = "temp_por_top"
TEMP_CORE = "temp_core"
OUTPUT_CHAIN = "por_output_chain"
#: the tail the deck writes after `AE=` on a 10 um x 10 um emitter
#: (layout/reports/temp_core/extracted.spice)
BJT_TAIL = "PE=40U AB=144P PB=48U AC=144P PC=48U NE=1"

#: `klt lvs`'s net_correspondence for temp_core: the pins plus one net per
#: body tie of `postlayout.body_ties("temp_core")` other than the substrate
#: (NW1 -> VDD, NW2 -> NT, NWQ -> VSS). Entry shape as committed in
#: layout/reports/temp_core/lvs.json.
TEMP_CORE_LVS = [
    {"layout": "VDD", "reference": "VDD", "pin": True},
    {"layout": "VSS", "reference": "VSS", "pin": True},
    {"layout": "NT", "reference": "NT", "pin": True},
    {"layout": "\\$29", "reference": "NW1", "pin": False},
    {"layout": "\\$28", "reference": "NW2", "pin": False},
    {"layout": "NC", "reference": "NWQ", "pin": False},
]

#: temp_por_top is an assembly, so its tie nets carry the instance path
#: (`xbias.NW1`): every `postlayout.body_ties("temp_por_top")` key except the
#: substrate, with the layout net it resolves to. `xtemp.NT` is `xtemp.NW2`'s
#: target.
TOP_TIE_NETS = {
    "xbias.NW1": "\\$41",
    "xbias.NWQ": "\\$46",
    "xcmp.NW1": "\\$42",
    "xcmp.NW2": "\\$50",
    "xpor.NW1": "\\$44",
    "xtemp.NW1": "\\$97",
    "xtemp.NW2": "\\$96",
    "xtemp.NWQ": "\\$45",
    "xtemp.NT": "NT",
}

#: the ties of temp_por_top in the order `patch_extracted` emits them
#: (sorted by reference net), for any spelling of the correspondence
TOP_TIE_LINES = [
    "Vtie_0 \\$41 VDD 0",
    "Vtie_1 \\$46 VSS 0",
    "Vtie_2 \\$42 VDD 0",
    "Vtie_3 \\$50 VDD 0",
    "Vtie_4 \\$44 VDD 0",
    "Vtie_5 \\$97 VDD 0",
    "Vtie_6 \\$96 NT 0",
    "Vtie_7 \\$45 VSS 0",
]


def bjt(name: str, base: str = "VSS", ae: str = "100P") -> str:
    """A `Q` card as the deck writes it -- `collector base emitter`, the
    generic `bjt` class -- with its base on `base` and its emitter on a net
    of its own."""
    return f"{name} VSS {base} E{name} bjt AE={ae} {BJT_TAIL}"


def netlist(cell: str, header: str, *cards: str) -> str:
    """A `klt pex` netlist for `cell`: `header` (possibly wrapped onto `+`
    lines), one `* device instance` comment per card, then `.ENDS`. The
    comments and blank lines are what must pass through verbatim."""
    lines = ["* extracted by klt pex --deck gf180mcu", "", f"* cell {cell}", header]
    for n, card in enumerate(cards):
        lines += [f"* device instance ${n} r0 *1 {n},81 bjt", card]
    lines += ["", f".ENDS {cell}", ""]
    return "\n".join(lines)


def top_lvs(dotted: bool = False, without: tuple[str, ...] = ()) -> list[dict]:
    """temp_por_top's correspondence, minus the `without` reference nets.

    `dotted` spells each reference the way klt 0.2.0 reported it, hierarchy
    separator intact (`XBIAS.NW1`); otherwise the pinned spelling (`XBIAS_NW1`).
    """
    refs = [
        {"layout": "VDD", "reference": "VDD", "pin": True},
        {"layout": "VSS", "reference": "VSS", "pin": True},
    ]
    for ref, net in TOP_TIE_NETS.items():
        if ref in without:
            continue
        spelled = ref.upper()
        if not dotted:
            spelled = spelled.replace(".", "_")
        refs.append({"layout": net, "reference": spelled, "pin": False})
    return refs


def klt_lvs(correspondence: list[dict], status: str = "match") -> mock.Mock:
    """A `subprocess.run` stand-in whose `klt lvs` prints this document."""
    doc = {"status": status, "net_correspondence": correspondence}
    return mock.Mock(
        return_value=subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(doc), stderr=""
        )
    )


def dies(test: unittest.TestCase, fn, *args, **kwargs) -> str:
    """`fn` must `die()`: exit status 2, its message on stderr (which `klt
    pex` reports). Returns that message."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), test.assertRaises(SystemExit) as cm:
        fn(*args, **kwargs)
    test.assertEqual(cm.exception.code, 2)
    return err.getvalue()


class SchematicPins(unittest.TestCase):
    def test_committed_cells_in_schematic_order(self):
        """The pin lists `sim/pex/run_pex.sh` declares to `klt pex`."""
        for cell, pins in (
            (TOP, ["VDD", "VSS", "PTAT", "CTAT", "RESETn"]),
            (TEMP_CORE, ["VDD", "VSS", "IBIAS", "EN", "PTAT", "CTAT"]),
            (OUTPUT_CHAIN, ["VDD", "VSS", "IBIAS", "POR_RAW", "RESETn"]),
        ):
            with self.subTest(cell=cell):
                self.assertEqual(measure.schematic_pins(cell), pins)

    def test_keeps_pins_wrapped_onto_continuation_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            netlists = Path(tmp) / "design" / "netlist"
            netlists.mkdir(parents=True)
            # another subcircuit first: the port list is read by name
            (netlists / f"{TOP}.spice").write_text(
                "* generated\n"
                ".subckt bias_core VDD VSS IBIAS\n"
                ".ends\n"
                f".subckt {TOP} VDD VSS\n"
                "+ PTAT CTAT\n"
                "+ RESETn\n"
                ".ends\n"
            )
            with mock.patch.object(measure, "REPO", Path(tmp)):
                self.assertEqual(
                    measure.schematic_pins(TOP),
                    ["VDD", "VSS", "PTAT", "CTAT", "RESETn"],
                )

    def test_dies_without_the_subcircuit(self):
        with tempfile.TemporaryDirectory() as tmp:
            netlists = Path(tmp) / "design" / "netlist"
            netlists.mkdir(parents=True)
            (netlists / f"{TOP}.spice").write_text(".subckt other A B\n.ends\n")
            with mock.patch.object(measure, "REPO", Path(tmp)):
                msg = dies(self, measure.schematic_pins, TOP)
        self.assertIn(f"no `.subckt {TOP}` in design/netlist/{TOP}.spice", msg)


class LvsCorrespondence(unittest.TestCase):
    def test_keys_are_the_compare_spelling_of_the_reference(self):
        correspondence = [
            {"layout": "VDD", "reference": "VDD", "pin": True},
            {"layout": "VSS", "reference": "VSS", "pin": True},
            {"layout": "\\$41", "reference": "XBIAS.NW1", "pin": False},
            {"layout": "VSS", "reference": "XBIAS.NWQ", "pin": False},
            {"layout": "\\$8", "reference": "RESETn", "pin": False},
        ]
        with mock.patch.object(subprocess, "run", klt_lvs(correspondence)):
            corr = measure.lvs_correspondence("klt", TOP)
        self.assertEqual(corr, {"VDD": "VDD", "VSS": "VSS",
                                "XBIAS_NW1": "\\$41", "XBIAS_NWQ": "VSS",
                                "RESETN": "\\$8"})
        for entry in correspondence:
            self.assertIn(postlayout.correspondence_key(entry["reference"]), corr)

    def test_runs_klt_lvs_on_the_cell_request(self):
        proc = klt_lvs(TEMP_CORE_LVS)
        with mock.patch.object(subprocess, "run", proc):
            measure.lvs_correspondence("klt", TEMP_CORE)
        request = measure.REPO / "layout" / "cells" / f"{TEMP_CORE}.lvs.json"
        proc.assert_called_once_with(["klt", "lvs", str(request), "--format", "json"],
                                     capture_output=True, text=True)

    def test_dies_unless_the_compare_matches(self):
        proc = klt_lvs(TEMP_CORE_LVS, status="mismatch")
        with mock.patch.object(subprocess, "run", proc):
            msg = dies(self, measure.lvs_correspondence, "klt", TEMP_CORE)
        self.assertIn("klt lvs status 'mismatch', expected match", msg)

    def test_dies_on_a_non_json_report(self):
        proc = mock.Mock(return_value=subprocess.CompletedProcess(
            [], 1, stdout="", stderr="klt: no deck"))
        with mock.patch.object(subprocess, "run", proc):
            msg = dies(self, measure.lvs_correspondence, "klt", TEMP_CORE)
        self.assertIn("klt lvs gave no JSON: klt: no deck", msg)


class PatchExtracted(unittest.TestCase):
    HEADER = ".SUBCKT temp_core CTAT EN IBIAS PTAT VDD VSS"
    TOP_HEADER = ".SUBCKT temp_por_top CTAT PTAT VDD VSS RESETn"

    def patched(self, text: str, cell: str, lvs: list[dict]) -> tuple[str, list[str]]:
        with mock.patch.object(subprocess, "run", klt_lvs(lvs)):
            return measure.patch_extracted(text, "klt", cell)

    def refused(self, needle: str, text: str, cell: str, lvs: list[dict]) -> None:
        """`patch_extracted` exits 2 with a message naming `needle`."""
        with mock.patch.object(subprocess, "run", klt_lvs(lvs)):
            msg = dies(self, measure.patch_extracted, text, "klt", cell)
        self.assertIn(needle, msg)

    @staticmethod
    def tie_lines(out: str) -> list[str]:
        return [line for line in out.splitlines() if line.startswith("Vtie_")]

    def test_rewrites_header_bipolars_and_ties(self):
        out, report = self.patched(
            netlist(TEMP_CORE, self.HEADER, bjt("Q$56", "NC"), bjt("Q$57")),
            TEMP_CORE, TEMP_CORE_LVS,
        )
        lines = out.splitlines()
        self.assertEqual(lines[3], ".SUBCKT temp_core VDD VSS IBIAS EN PTAT CTAT")
        self.assertIn("XQ$56 VSS NC EQ$56 pnp_10p00x10p00 m=1", lines)
        self.assertIn("XQ$57 VSS VSS EQ$57 pnp_10p00x10p00 m=1", lines)
        self.assertFalse([line for line in lines if line.startswith("Q")])
        # every card, comment and blank line passes through untouched
        self.assertEqual(lines[:3], ["* extracted by klt pex --deck gf180mcu", "",
                                     "* cell temp_core"])
        self.assertEqual(lines[4], "* device instance $0 r0 *1 0,81 bjt")
        self.assertEqual(lines[-1], ".ENDS temp_core")
        self.assertTrue(out.endswith("\n"))
        # the ties go right before .ENDS: NW1 -> VDD, NW2 -> NT, NWQ -> VSS
        self.assertEqual(self.tie_lines(out),
                         ["Vtie_0 \\$29 VDD 0", "Vtie_1 \\$28 NT 0",
                          "Vtie_2 NC VSS 0"])
        self.assertEqual(lines[lines.index(".ENDS temp_core") - 1], "Vtie_2 NC VSS 0")
        self.assertEqual(report, [
            "NW1: \\$29 -> VDD (VDD)",
            "NW2: \\$28 -> NT (NT)",
            "NWQ: NC -> VSS (VSS)",
            "2 bipolar cards -> pnp_10p00x10p00",
        ])

    def test_leaves_the_substrate_to_the_deck(self):
        """`vsubs` is in `body_ties()` but is never tied here: the deck's own
        `--substrate-tie-ohms` resolves it (sim/pex/run_pex.sh)."""
        out, report = self.patched(
            netlist(TEMP_CORE, self.HEADER, bjt("Q$56")), TEMP_CORE, TEMP_CORE_LVS
        )
        ties = postlayout.body_ties(TEMP_CORE)
        self.assertIn(lvs_reference.SUBSTRATE_NET, ties)
        self.assertEqual(len(self.tie_lines(out)), len(ties) - 1)
        for line in self.tie_lines(out) + report:
            self.assertNotIn(lvs_reference.SUBSTRATE_NET, line.lower())

    def test_joins_a_header_wrapped_onto_continuation_lines(self):
        out, _report = self.patched(
            netlist(TEMP_CORE, ".SUBCKT temp_core CTAT EN IBIAS PTAT\n+ VDD VSS",
                    bjt("Q$56")),
            TEMP_CORE, TEMP_CORE_LVS,
        )
        self.assertEqual(out.splitlines()[3],
                         ".SUBCKT temp_core VDD VSS IBIAS EN PTAT CTAT")
        self.assertIn("Vtie_0 \\$29 VDD 0", out.splitlines())

    def test_joins_a_bipolar_card_wrapped_onto_continuation_lines(self):
        out, _report = self.patched(
            netlist(TEMP_CORE, self.HEADER,
                    f"Q$56 VSS NC EQ$56 bjt\n+ AE=100P {BJT_TAIL}"),
            TEMP_CORE, TEMP_CORE_LVS,
        )
        self.assertIn("XQ$56 VSS NC EQ$56 pnp_10p00x10p00 m=1", out.splitlines())

    def test_refuses_a_pin_set_other_than_the_schematic_one(self):
        text = netlist(TEMP_CORE, self.HEADER + " EXTRA", bjt("Q$56"))
        self.refused("extracted pin set ['CTAT', 'EN', 'IBIAS', 'PTAT', 'VDD', 'VSS', "
                     "'EXTRA'] != schematic", text, TEMP_CORE, TEMP_CORE_LVS)

    def test_refuses_an_emitter_area_other_than_the_schematic_models(self):
        text = netlist(TEMP_CORE, self.HEADER, bjt("Q$56", ae="25P"))
        self.refused("unexpected bipolar card (need `bjt` with AE=100P)",
                     text, TEMP_CORE, TEMP_CORE_LVS)

    def test_refuses_a_bipolar_the_schematic_does_not_have(self):
        text = netlist(OUTPUT_CHAIN,
                       ".SUBCKT por_output_chain IBIAS POR_RAW RESETn VDD VSS",
                       bjt("Q$1"))
        lvs = [{"layout": "VDD", "reference": "VDD", "pin": True},
               {"layout": "VSS", "reference": "VSS", "pin": True},
               {"layout": "\\$19", "reference": "NW1", "pin": False}]
        self.refused("extracted but the schematic has none",
                     text, OUTPUT_CHAIN, lvs)

    def test_refuses_a_base_on_an_untied_net(self):
        text = netlist(TEMP_CORE, self.HEADER, bjt("Q$56", "NA"))
        self.refused("bipolar base NA is neither a tied well nor on the VSS net",
                     text, TEMP_CORE, TEMP_CORE_LVS)

    def test_resolves_dotted_reference_names_on_both_sides(self):
        """klt 0.2.0's spelling of an assembly's tie nets: `XBIAS.NW1`."""
        # the base sits on xbias.NWQ's layout net: tied, so the base check passes
        text = netlist(TOP, self.TOP_HEADER, bjt("Q$136", "\\$46"), bjt("Q$137"))
        out, report = self.patched(text, TOP, top_lvs(dotted=True))
        self.assertEqual(self.tie_lines(out), TOP_TIE_LINES)
        self.assertIn("XQ$136 VSS \\$46 EQ$136 pnp_10p00x10p00 m=1", out.splitlines())
        self.assertIn("xtemp.NW2: \\$96 -> xtemp.NT (NT)", report)

    def test_resolves_the_pinned_reference_spelling_too(self):
        text = netlist(TOP, self.TOP_HEADER, bjt("Q$136", "\\$46"))
        out, _report = self.patched(text, TOP, top_lvs())
        self.assertEqual(self.tie_lines(out), TOP_TIE_LINES)

    def test_reports_a_well_the_compare_merged_into_a_rail(self):
        """No net of its own for `xbias.NWQ` or `xcmp.NW1`: reported, not tied."""
        lvs = top_lvs(dotted=True, without=("xbias.NWQ", "xcmp.NW1"))
        out, report = self.patched(
            netlist(TOP, self.TOP_HEADER, bjt("Q$136")), TOP, lvs
        )
        # the survivors keep their order and are renumbered from Vtie_0
        self.assertEqual(self.tie_lines(out), [
            "Vtie_0 \\$41 VDD 0",
            "Vtie_1 \\$50 VDD 0",
            "Vtie_2 \\$44 VDD 0",
            "Vtie_3 \\$97 VDD 0",
            "Vtie_4 \\$96 NT 0",
            "Vtie_5 \\$45 VSS 0",
        ])
        self.assertIn("xbias.NWQ: no net of its own in the layout (merged into VSS)",
                      report)
        self.assertIn("xcmp.NW1: no net of its own in the layout (merged into VDD)",
                      report)

    def test_refuses_a_merged_well_whose_target_is_not_a_rail(self):
        lvs = top_lvs(dotted=True, without=("xtemp.NW2",))
        self.refused("xtemp.NW2 has no layout net and target xtemp.NT is not a rail",
                     netlist(TOP, self.TOP_HEADER, bjt("Q$136")), TOP, lvs)


if __name__ == "__main__":
    unittest.main()
