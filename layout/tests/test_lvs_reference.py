#!/usr/bin/env python3
"""Unit tests for layout/lvs_reference.py. No PDK, no klayout, no klt required.

    python3 -m unittest discover -s layout/tests -v

The end-to-end proof that the DRC/LVS flow works lives in
``layout/run_checks.sh`` (which needs ``klt``). These tests cover the pure-python
transform underneath it: the netlist-form conversion, the deck-imposed body-net
rewrites, and the guards that are supposed to fail loudly rather than quietly
emit a reference the layout can never match.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = LAYOUT_DIR.parent
sys.path.insert(0, str(LAYOUT_DIR))

import lvs_reference as lr  # noqa: E402

CELL = "por_comparator_bias_okb_inv"


class ParsingTest(unittest.TestCase):
    def test_continuations_are_joined(self):
        text = "* comment\nXM1 d g s b nfet_03v3 L=1u\n+ W=2u nf=1\n\n.ends\n"
        self.assertEqual(
            lr.logical_lines(text),
            ["XM1 d g s b nfet_03v3 L=1u W=2u nf=1", ".ends"],
        )

    def test_subckt_body_selects_the_named_cell(self):
        text = (
            ".subckt other A B\nXM9 A B A B nfet_03v3 L=9u W=9u\n.ends\n"
            ".subckt wanted A B\nXM1 A B A B nfet_03v3 L=1u W=2u\n.ends\n"
        )
        self.assertEqual(
            lr.subckt_body(text, "wanted"), ["XM1 A B A B nfet_03v3 L=1u W=2u"]
        )
        with self.assertRaises(lr.ReferenceError):
            lr.subckt_body(text, "absent")

    def test_dimension_units(self):
        self.assertAlmostEqual(lr.to_um("0.5u"), 0.5)
        self.assertAlmostEqual(lr.to_um("2u"), 2.0)
        self.assertAlmostEqual(lr.to_um("1n"), 0.001)
        with self.assertRaises(lr.ReferenceError):
            lr.to_um("3furlongs")

    def test_format_carries_an_explicit_micrometre_suffix(self):
        # klt lvs reads a bare numeric W/L as metres; an unsuffixed reference
        # parses 1e6 off and only ever "matches relative to itself".
        self.assertEqual(lr.format_um(0.5), "0.5U")
        self.assertEqual(lr.format_um(2.0), "2U")

    def test_non_mos_cards_are_skipped_not_guessed_at(self):
        body = [
            "XR1 a b c ppolyf_u_3k r_width=2u r_length=10u m=1",
            "XM1 d g s b nfet_03v3 L=1u W=2u",
        ]
        self.assertEqual(list(lr.parse_devices(body)), ["XM1"])


class BuildTest(unittest.TestCase):
    def test_reference_matches_the_committed_file(self):
        committed = (LAYOUT_DIR / "cells" / f"{CELL}.reference.spice").read_text()
        self.assertEqual(lr.build(CELL), committed)

    def test_form_and_body_rewrites(self):
        lines = [
            line
            for line in lr.build(CELL).splitlines()
            if line and not line.startswith("*")
        ]
        self.assertEqual(
            lines,
            [
                f".SUBCKT {CELL} BIAS_OK BIAS_OKB VDD VSS vsubs",
                "M1 BIAS_OKB BIAS_OK VSS vsubs nfet L=0.5U W=1U",
                "M2 BIAS_OKB BIAS_OK VDD NW1 pfet L=0.5U W=2U",
                f".ENDS {CELL}",
            ],
        )

    def test_sizing_is_read_from_the_golden_netlist_not_retyped(self):
        golden = (REPO_ROOT / "design" / "netlist" / "por_comparator.spice").read_text()
        devices = lr.parse_devices(lr.subckt_body(golden, "por_comparator"))
        for name, card in (("XMENN", "M1"), ("XMENP", "M2")):
            width = lr.format_um(lr.to_um(devices[name]["params"]["w"]))
            length = lr.format_um(lr.to_um(devices[name]["params"]["l"]))
            self.assertIn(f"{card} ", lr.build(CELL))
            self.assertIn(f"L={length} W={width}", lr.build(CELL))


class ControlTest(unittest.TestCase):
    def test_each_control_changes_exactly_one_thing(self):
        clean = lr.build(CELL).splitlines()
        for corruption, expected_diffs in (("device-param", 1), ("topology", 1)):
            bad = lr.build(CELL, corrupt=corruption).splitlines()
            self.assertEqual(len(clean), len(bad))
            device_lines = [
                (a, b)
                for a, b in zip(clean, bad)
                if a.startswith("M") and b.startswith("M") and a != b
            ]
            self.assertEqual(
                len(device_lines), expected_diffs, f"{corruption} changed too much"
            )

    def test_device_param_control_only_touches_a_width(self):
        clean = next(l for l in lr.build(CELL).splitlines() if l.startswith("M1 "))
        bad = next(
            l
            for l in lr.build(CELL, corrupt="device-param").splitlines()
            if l.startswith("M1 ")
        )
        self.assertEqual(clean.split()[:6], bad.split()[:6])  # nets untouched
        self.assertNotEqual(clean.split()[-1], bad.split()[-1])  # W changed

    def test_topology_control_only_touches_connectivity(self):
        clean = next(l for l in lr.build(CELL).splitlines() if l.startswith("M1 "))
        bad = next(
            l
            for l in lr.build(CELL, corrupt="topology").splitlines()
            if l.startswith("M1 ")
        )
        self.assertEqual(clean.split()[-2:], bad.split()[-2:])  # L/W untouched
        self.assertNotEqual(clean.split()[1:5], bad.split()[1:5])  # a net changed

    def test_unknown_corruption_is_an_error(self):
        with self.assertRaises(lr.ReferenceError):
            lr.build(CELL, corrupt="vibes")


class GuardTest(unittest.TestCase):
    """The guards exist so a bad manifest fails loudly instead of emitting a
    reference the layout can never match (which reads as a layout bug)."""

    def setUp(self):
        self.spec = dict(lr.CELLS[CELL])
        self.addCleanup(lr.CELLS.__setitem__, CELL, lr.CELLS[CELL])

    def test_missing_device_is_an_error(self):
        lr.CELLS[CELL] = {**self.spec, "devices": ["XNOPE"]}
        with self.assertRaises(lr.ReferenceError):
            lr.build(CELL)

    def test_undeclared_net_is_an_error(self):
        lr.CELLS[CELL] = {**self.spec, "ports": ["BIAS_OK", lr.SUBSTRATE_NET]}
        with self.assertRaises(lr.ReferenceError):
            lr.build(CELL)

    def test_pmos_without_a_well_assignment_is_an_error(self):
        lr.CELLS[CELL] = {**self.spec, "wells": {}}
        with self.assertRaises(lr.ReferenceError):
            lr.build(CELL)

    def test_multi_finger_or_multiplied_devices_are_refused(self):
        # The curated deck extracts one drawn device per drawn gate, so a
        # reference carrying nf/m > 1 could never match any layout it accepts.
        body = ["XM1 d g s b nfet_03v3 L=1u W=2u nf=2"]
        devices = lr.parse_devices(body)
        self.assertEqual(devices["XM1"]["params"]["nf"], "2")

        original = lr.parse_devices
        lr.parse_devices = lambda _body: devices
        self.addCleanup(setattr, lr, "parse_devices", original)
        lr.CELLS[CELL] = {
            **self.spec,
            "devices": ["XM1"],
            "ports": ["d", "g", "s", lr.SUBSTRATE_NET],
            "wells": {},
        }
        with self.assertRaises(lr.ReferenceError) as caught:
            lr.build(CELL)
        self.assertIn("nf=2", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
