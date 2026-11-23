#!/usr/bin/env python3
"""Unit tests for design/netlist.py's pure-Python invariant helpers.

    python3 -m unittest discover -s layout/tests -v

No PDK, no xschem, no klt: ``design/netlist.py --check`` is the sole pinout
gate behind spec/target-spec.md#pinout, yet none of the pure functions it
runs (``normalize``, ``symbol_pins``, ``schematic_ports``, ``subckt_ports``,
``instance_lines``, ``check_invariants``) had headless coverage -- the only
exercise was a full export needing ``klt`` and the PDK. These tests pin them
against the committed ``design/`` sources (the same files ``--check``
regenerates) and against synthetic netlists for the cases the committed
decks do not contain: sub-circuit ``.subckt`` decoys, ``+`` continuations on
``X`` cards, ``key=value`` instance parameters, and a missing
``.subckt temp_por_top``.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = LAYOUT_DIR.parent
DESIGN_DIR = REPO_ROOT / "design"
NETLIST_DIR = DESIGN_DIR / "netlist"

sys.path.insert(0, str(DESIGN_DIR))

import netlist  # noqa: E402  (inserts sim/ and layout/ on sys.path itself)

SUB_CELLS = ["bias_core", "por_comparator", "por_output_chain", "temp_core"]


def committed_netlists() -> dict[str, str]:
    return {p.stem: p.read_text() for p in sorted(NETLIST_DIR.glob("*.spice"))}


def top_deck(instance: str) -> str:
    return (
        ".subckt temp_por_top VDD VSS PTAT CTAT RESETn\n"
        f"{instance}\n"
        ".ends\n"
    )


BIAS_DECK = ".subckt bias_core VDD VSS IBIAS VREF BIAS_OK\nRM1 VDD IBIAS 1k\n.ends\n"


class NormalizeTest(unittest.TestCase):
    def test_rewrites_repo_root_and_strips_trailing_whitespace(self):
        text = f"{netlist.REPO_ROOT}{os.sep}design{os.sep}a.spice  \nline two\t\n\n"
        self.assertEqual(netlist.normalize(text), "design/a.spice\nline two\n")


class SymbolAndSchematicTest(unittest.TestCase):
    def test_top_symbol_pins_are_the_ratified_pinout(self):
        self.assertEqual(
            netlist.symbol_pins(netlist.TOP_CELL), netlist.RATIFIED_TOP_PORTS
        )

    def test_symbol_pins_match_schematic_ports_for_every_cell(self):
        for cell in netlist.cells():
            pins = netlist.symbol_pins(cell)
            self.assertIsNotNone(pins, cell)
            self.assertEqual(pins, netlist.schematic_ports(cell), cell)

    def test_symbol_pins_none_without_a_symbol(self):
        self.assertIsNone(netlist.symbol_pins("no_such_cell"))


class SubcktPortsTest(unittest.TestCase):
    def test_committed_decks_match_their_symbols(self):
        for cell, text in committed_netlists().items():
            self.assertEqual(
                netlist.subckt_ports(text, cell), netlist.symbol_pins(cell), cell
            )

    def test_picks_the_named_subckt_among_many(self):
        top = committed_netlists()[netlist.TOP_CELL]
        self.assertEqual(
            netlist.subckt_ports(top, "temp_core"),
            ["VDD", "VSS", "IBIAS", "EN", "PTAT", "CTAT"],
        )

    def test_missing_subckt_raises_export_error(self):
        with self.assertRaises(netlist.ExportError):
            netlist.subckt_ports(".subckt other a b\n.ends\n", "bias_core")


class InstanceLinesTest(unittest.TestCase):
    def test_scoped_to_top_level_subckt_block(self):
        deck = (
            ".subckt temp_por_top VDD VSS PTAT CTAT RESETn\n"
            "xa1 n1 n2 bias_core\n"
            ".ends\n"
            ".subckt wrapper a b\n"
            "xhidden p1 p2 bias_core\n"
            ".ends\n"
        )
        self.assertEqual(
            netlist.instance_lines(deck, "bias_core"),
            [["xa1", "n1", "n2", "bias_core"]],
        )

    def test_plus_continuations_are_joined(self):
        deck = (
            ".subckt temp_por_top VDD VSS PTAT CTAT RESETn\n"
            "xwrap n1\n"
            "+ n2 bias_core\n"
            ".ends\n"
        )
        self.assertEqual(
            netlist.instance_lines(deck, "bias_core"),
            [["xwrap", "n1", "n2", "bias_core"]],
        )

    def test_key_value_parameters_are_stripped(self):
        deck = (
            ".subckt temp_por_top VDD VSS PTAT CTAT RESETn\n"
            "xpar n1 n2 bias_core m=1\n"
            "xpre n1 m=2 n2 bias_core\n"
            ".ends\n"
        )
        self.assertEqual(
            netlist.instance_lines(deck, "bias_core"),
            [["xpar", "n1", "n2", "bias_core"],
             ["xpre", "n1", "n2", "bias_core"]],
        )

    def test_missing_top_subckt_raises_export_error(self):
        with self.assertRaises(netlist.ExportError):
            netlist.instance_lines("* no top block\nx1 a b bias_core\n", "bias_core")

    def test_committed_top_deck_finds_each_sub_cell(self):
        committed = committed_netlists()
        top = committed[netlist.TOP_CELL]
        for cell in SUB_CELLS:
            rows = netlist.instance_lines(top, cell)
            self.assertTrue(rows, cell)
            width = len(netlist.subckt_ports(committed[cell], cell))
            for row in rows:
                self.assertEqual(row[-1], cell)
                self.assertEqual(len(row) - 2, width, row)


class CheckInvariantsTest(unittest.TestCase):
    def test_committed_decks_pass(self):
        self.assertEqual(netlist.check_invariants(committed_netlists()), [])

    def test_parameterized_instance_still_counts_its_nets(self):
        netlists = {
            netlist.TOP_CELL: top_deck(
                "xbias VDD VSS IBIAS VREF BIAS_OK bias_core m=2"
            ),
            "bias_core": BIAS_DECK,
        }
        self.assertEqual(netlist.check_invariants(netlists), [])

    def test_instance_inside_a_sub_circuit_subckt_does_not_count(self):
        netlists = {
            netlist.TOP_CELL: (
                ".subckt temp_por_top VDD VSS PTAT CTAT RESETn\n"
                "RM1 VDD PTAT 1k\n"
                ".ends\n"
                ".subckt wrapper a b\n"
                "x1 p1 p2 p3 p4 p5 bias_core\n"
                ".ends\n"
            ),
            "bias_core": BIAS_DECK,
        }
        failures = "\n".join(netlist.check_invariants(netlists))
        self.assertIn("bias_core: not instantiated in temp_por_top", failures)

    def test_net_count_mismatch_is_reported(self):
        netlists = {
            netlist.TOP_CELL: top_deck("xbias VDD VSS IBIAS VREF bias_core"),
            "bias_core": BIAS_DECK,
        }
        failures = "\n".join(netlist.check_invariants(netlists))
        self.assertIn("connects 4 nets", failures)
        self.assertIn("5 ports", failures)

    def test_top_pinout_drift_is_reported(self):
        netlists = {
            netlist.TOP_CELL: (
                ".subckt temp_por_top VDD VSS PTAT CTAT\n"
                "xbias VDD VSS IBIAS VREF BIAS_OK bias_core\n"
                ".ends\n"
            ),
            "bias_core": BIAS_DECK,
        }
        failures = "\n".join(netlist.check_invariants(netlists))
        self.assertIn("drifted from the ratified interface", failures)


if __name__ == "__main__":
    unittest.main()
