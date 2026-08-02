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

import build_cells as bc  # noqa: E402  (klayout is imported lazily, per-cell)
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


class BiasCoreManifestTest(unittest.TestCase):
    """``bias_core`` is the first manifest entry with unlabelled internal nets
    and a multi-device well, and the first big enough for the negative controls
    to degrade quietly. These check the properties that make it honest."""

    CELL = "bias_core"

    def test_reference_matches_the_committed_file(self):
        committed = (LAYOUT_DIR / "cells" / f"{self.CELL}.reference.spice").read_text()
        self.assertEqual(lr.build(self.CELL), committed)

    def test_every_mos_device_in_the_schematic_is_in_the_manifest(self):
        # The non-MOS devices (PNPs, poly resistors, MiM caps) are outside the
        # curated deck's coverage and are deliberately absent; every device it
        # *can* model must be present, or the layout is being compared against
        # a quietly reduced circuit.
        golden = (REPO_ROOT / "design" / "netlist" / "bias_core.spice").read_text()
        modelled = set(lr.parse_devices(lr.subckt_body(golden, "bias_core")))
        self.assertEqual(modelled, set(lr.CELLS[self.CELL]["devices"]))

    def test_topology_control_has_two_different_sources_to_work_with(self):
        # The control re-ties devices[0]'s source to devices[1]'s. If they
        # already agreed, the "corrupted" reference would equal the clean one
        # and run_checks.sh's control would pass while controlling nothing.
        golden = (REPO_ROOT / "design" / "netlist" / "bias_core.spice").read_text()
        devices = lr.parse_devices(lr.subckt_body(golden, "bias_core"))
        first, second = lr.CELLS[self.CELL]["devices"][:2]
        self.assertNotEqual(
            devices[first]["nodes"][2], devices[second]["nodes"][2]
        )
        self.assertNotEqual(
            lr.build(self.CELL), lr.build(self.CELL, corrupt="topology")
        )

    def test_every_pfet_is_assigned_to_the_one_drawn_well(self):
        spec = lr.CELLS[self.CELL]
        golden = (REPO_ROOT / "design" / "netlist" / "bias_core.spice").read_text()
        devices = lr.parse_devices(lr.subckt_body(golden, "bias_core"))
        pfets = {n for n in spec["devices"] if devices[n]["model"] == "pfet_03v3"}
        self.assertEqual(pfets, set(spec["wells"]["NW1"]))

    def test_the_drawn_row_and_the_reference_cover_the_same_devices(self):
        # A device drawn but not referenced (or vice versa) is exactly the
        # asymmetry a clean LVS would have to catch; catch it here instead,
        # without needing klayout or klt.
        drawn = set(bc.BIAS_CORE_PMOS) | set(bc.BIAS_CORE_NMOS)
        self.assertEqual(drawn, set(lr.CELLS[self.CELL]["devices"]))
        self.assertEqual(
            set(bc.BIAS_CORE_PMOS), set(lr.CELLS[self.CELL]["wells"]["NW1"])
        )

    def test_every_net_the_layout_routes_is_a_net_the_reference_declares(self):
        spec = lr.CELLS[self.CELL]
        declared = set(spec["ports"]) | set(spec["internal"])
        routed = set(bc.BIAS_CORE_TRACKS) | {"VDD", "VSS"}
        self.assertEqual(routed | {lr.SUBSTRATE_NET}, declared)

    def test_internal_nets_are_declared_not_inferred(self):
        # Dropping an internal net from the manifest must be an error, not a
        # silently-accepted reference the layout can never match.
        spec = dict(lr.CELLS[self.CELL])
        self.addCleanup(lr.CELLS.__setitem__, self.CELL, lr.CELLS[self.CELL])
        lr.CELLS[self.CELL] = {**spec, "internal": spec["internal"][1:]}
        with self.assertRaises(lr.ReferenceError):
            lr.build(self.CELL)


class PorComparatorManifestTest(unittest.TestCase):
    """``por_comparator`` is the first manifest entry whose layout instances
    another cell, and the first with two drawn wells. These check the
    properties that make its clean compare honest."""

    CELL = "por_comparator"
    SOURCE = "por_comparator.spice"

    def golden(self):
        text = (REPO_ROOT / "design" / "netlist" / self.SOURCE).read_text()
        return lr.parse_devices(lr.subckt_body(text, "por_comparator"))

    def test_reference_matches_the_committed_file(self):
        committed = (LAYOUT_DIR / "cells" / f"{self.CELL}.reference.spice").read_text()
        self.assertEqual(lr.build(self.CELL), committed)

    def test_every_mos_device_in_the_schematic_is_in_the_manifest(self):
        # The sense divider (poly resistors) is outside the curated deck's
        # coverage and deliberately absent; every device it *can* model must be
        # present, or the layout is being compared against a quietly reduced
        # circuit.
        self.assertEqual(set(self.golden()), set(lr.CELLS[self.CELL]["devices"]))

    def test_topology_control_has_two_different_sources_to_work_with(self):
        devices = self.golden()
        first, second = lr.CELLS[self.CELL]["devices"][:2]
        self.assertNotEqual(devices[first]["nodes"][2], devices[second]["nodes"][2])
        self.assertNotEqual(
            lr.build(self.CELL), lr.build(self.CELL, corrupt="topology")
        )

    def test_every_pfet_is_assigned_to_one_of_the_two_drawn_wells(self):
        spec = lr.CELLS[self.CELL]
        devices = self.golden()
        pfets = {n for n in spec["devices"] if devices[n]["model"] == "pfet_03v3"}
        assigned = {name for members in spec["wells"].values() for name in members}
        self.assertEqual(pfets, assigned)
        # NW2 is the well inside the instanced por_comparator_bias_okb_inv --
        # separate from the parent row's NW1 because the instance is placed
        # clear of it, so the reference has to carry two body nets, not one.
        self.assertEqual(spec["wells"]["NW2"], ["XMENP"])

    def test_the_drawn_cell_and_the_reference_cover_the_same_devices(self):
        # A device drawn but not referenced (or vice versa) is exactly the
        # asymmetry a clean LVS would have to catch; catch it here instead,
        # without needing klayout or klt. The instanced sub-cell's two devices
        # count as drawn.
        instanced = set(lr.CELLS["por_comparator_bias_okb_inv"]["devices"])
        drawn = set(bc.POR_COMPARATOR_PMOS) | set(bc.POR_COMPARATOR_NMOS) | instanced
        self.assertEqual(drawn, set(lr.CELLS[self.CELL]["devices"]))

    def test_every_net_the_layout_routes_is_a_net_the_reference_declares(self):
        spec = lr.CELLS[self.CELL]
        declared = set(spec["ports"]) | set(spec["internal"])
        routed = set(bc.POR_COMPARATOR_TRACKS) | {"VDD", "VSS"}
        self.assertEqual(routed | {lr.SUBSTRATE_NET}, declared)

    def test_bias_okb_is_a_pin_because_the_instanced_sub_cell_labels_it(self):
        # Not cosmetic: the sub-cell is reused as-is, labels included, so the
        # flattened parent has a *named* BIAS_OKB net and KLayout turns every
        # named top-level net into a pin. The manifest must agree or the pin
        # counts differ and the compare fails.
        self.assertIn("BIAS_OKB", lr.CELLS[self.CELL]["ports"])
        self.assertIn("BIAS_OKB", lr.CELLS["por_comparator_bias_okb_inv"]["ports"])


class PorComparatorMatchingPlanTest(unittest.TestCase):
    """``layout/floorplan.md`` rank 4, encoded as checks.

    The rank-4 plan is a *de-prioritization* (standard practice, not
    common-centroid) justified by #15's measured yield, so its content is
    entirely "these devices are adjacent, identical and same-width". That is
    cheap to state in prose and just as cheap to lose in a later edit -- so it
    is asserted here instead of only being claimed in a PR description.
    """

    def golden(self):
        text = (REPO_ROOT / "design" / "netlist" / "por_comparator.spice").read_text()
        return lr.parse_devices(lr.subckt_body(text, "por_comparator"))

    def test_the_input_pair_is_drawn_side_by_side(self):
        row = bc.POR_COMPARATOR_NMOS
        self.assertEqual(abs(row.index("XMINA") - row.index("XMINB")), 1)

    def test_the_input_pair_is_geometrically_identical(self):
        devices = self.golden()
        for param in ("l", "w"):
            self.assertEqual(
                devices["XMINA"]["params"][param], devices["XMINB"]["params"][param]
            )

    def test_the_input_pairs_gate_and_drain_nets_share_adjacent_tracks(self):
        # "short and symmetric routing from SNS and VREF": adjacent tracks put
        # the two halves' gate runs one track pitch apart, and the same for the
        # two drains.
        tracks = bc.POR_COMPARATOR_TRACKS
        self.assertEqual(abs(tracks.index("SNS") - tracks.index("VREF")), 1)
        self.assertEqual(abs(tracks.index("NA") - tracks.index("CMPO")), 1)

    def test_the_load_mirror_pair_is_drawn_side_by_side(self):
        row = bc.POR_COMPARATOR_PMOS
        self.assertEqual(abs(row.index("XMLA") - row.index("XMLB")), 1)

    def test_the_sense_divider_keeps_the_floorplans_2um_leg_width(self):
        # floorplan.md rank 4: "This floorplan keeps W = 2 um" -- narrowing to
        # 1 um is a mismatch trade #15's data does not ask for, so the reserved
        # footprint is computed from the schematic's width and pinned here.
        *_, leg_w, _ = bc._divider_footprint()
        self.assertEqual(leg_w, 2.0)

    def test_the_reserved_area_actually_fits_the_folded_string(self):
        width, height, drawn, leg_w, legs = bc._divider_footprint()
        pitch = leg_w + bc.DIVIDER_LEG_SPACE_UM
        leg_len = height - 2 * bc.DIVIDER_LEG_END_UM
        self.assertGreaterEqual(width, legs * pitch)
        active_legs = legs - bc.DIVIDER_DUMMY_LEGS
        self.assertGreaterEqual(active_legs * leg_len, drawn)

    def test_the_sense_divider_is_left_out_of_the_compare_on_purpose(self):
        # It is in the schematic, and it is not in the manifest: the curated
        # deck models no resistor, so drawing it would short SNS/SNSB rather
        # than check them (klayout-tools#219/#222).
        text = (REPO_ROOT / "design" / "netlist" / "por_comparator.spice").read_text()
        body = lr.subckt_body(text, "por_comparator")
        self.assertTrue(
            all(any(line.startswith(f"{r} ") for line in body)
                for r in bc.POR_DIVIDER_RESISTORS)
        )
        self.assertFalse(
            set(bc.POR_DIVIDER_RESISTORS) & set(lr.CELLS["por_comparator"]["devices"])
        )


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


class TempCoreTest(unittest.TestCase):
    """``temp_core`` is drawn with interleaved unit fingers and edge dummies,
    so its reference has to describe more devices than the schematic has -- the
    same electrical devices, described the way the curated deck can see them."""

    CELL = "temp_core"

    def cards(self, text=None):
        return [
            line.split()
            for line in (text or lr.build(self.CELL)).splitlines()
            if line[:1] == "M"
        ]

    def test_reference_matches_the_committed_file(self):
        committed = (LAYOUT_DIR / "cells" / f"{self.CELL}.reference.spice").read_text()
        self.assertEqual(lr.build(self.CELL), committed)

    def test_finger_split_conserves_the_schematic_width(self):
        golden = (REPO_ROOT / "design" / "netlist" / "temp_core.spice").read_text()
        devices = lr.parse_devices(lr.subckt_body(golden, "temp_core"))
        text = lr.build(self.CELL)
        for name, count in lr.CELLS[self.CELL]["fingers"].items():
            schematic_w = lr.to_um(devices[name]["params"]["w"])
            finger_w = lr.format_um(schematic_w / count)
            length = lr.format_um(lr.to_um(devices[name]["params"]["l"]))
            drain, gate, source, _body = devices[name]["nodes"]
            matches = [
                card
                for card in self.cards(text)
                if card[1:4] == [drain, gate, source]
                and card[-2:] == [f"L={length}", f"W={finger_w}"]
            ]
            self.assertGreaterEqual(len(matches), count, f"{name}: fingers missing")

    def test_every_drawn_device_is_accounted_for(self):
        # 39 schematic MOS + 10 extra fingers + 6 edge dummies = 55 drawn.
        spec = lr.CELLS[self.CELL]
        extra = sum(count - 1 for count in spec["fingers"].values())
        expected = len(spec["devices"]) + extra + len(spec["dummies"])
        self.assertEqual(len(self.cards()), expected)

    def test_dummy_fingers_are_declared_not_derived(self):
        # Dummies are not in the schematic; a silently-derived dummy would be a
        # device LVS accepts that no golden netlist ever asked for.
        spec = lr.CELLS[self.CELL]
        for dummy in spec["dummies"]:
            self.assertEqual(len(set(dummy["nets"])), 1, "a dummy is tied off")
        self.addCleanup(lr.CELLS.__setitem__, self.CELL, spec)
        lr.CELLS[self.CELL] = {**spec, "dummies": []}
        without = len(self.cards())
        lr.CELLS[self.CELL] = spec
        self.assertEqual(len(self.cards()) - without, len(spec["dummies"]))

    def test_non_mos_devices_are_outside_this_compare(self):
        # The vertical PNPs, poly resistors and the MiM cap have no device
        # model in the curated deck (klayout-tools#219/#222).
        golden = (REPO_ROOT / "design" / "netlist" / "temp_core.spice").read_text()
        body = lr.subckt_body(golden, "temp_core")
        parsed = lr.parse_devices(body)
        for name in ("XQ1", "XQ8A", "XR1", "XR2F", "XRISO", "XRZ", "XCC"):
            self.assertIn(f"{name} ", golden)
            self.assertNotIn(name, parsed)

    def test_each_control_changes_exactly_one_card(self):
        clean = lr.build(self.CELL).splitlines()
        for corruption in ("device-param", "topology"):
            bad = lr.build(self.CELL, corrupt=corruption).splitlines()
            self.assertEqual(len(clean), len(bad))
            differing = [
                (a, b)
                for a, b in zip(clean, bad)
                if a[:1] == "M" and b[:1] == "M" and a != b
            ]
            self.assertEqual(len(differing), 1, f"{corruption} changed too much")


if __name__ == "__main__":
    unittest.main()
