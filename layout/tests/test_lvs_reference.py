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

import collections
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
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
            "XC1 p n cap_mim_2f0_m3m4_noshield c_width=1u c_length=2u m=1",
        ]
        self.assertEqual(list(lr.parse_devices(body)), ["XM1"])

    def test_cap_cards_are_parsed_separately_from_mos_and_resistors(self):
        # parse_capacitors is the mirror image: only the one MiM model the deck
        # declares a class for, never a resistor and never a MOS.
        body = [
            "XR1 a b c ppolyf_u_3k r_width=2u r_length=10u m=1",
            "XM1 d g s b nfet_03v3 L=1u W=2u",
            "XC1 p n cap_mim_2f0_m3m4_noshield c_width=1u c_length=2u m=4",
        ]
        caps = lr.parse_capacitors(body)
        self.assertEqual(list(caps), ["XC1"])
        self.assertEqual(caps["XC1"]["nodes"], ["p", "n"])
        self.assertEqual(lr.cap_units(caps["XC1"]), 4)

    def test_a_fractional_cap_multiplier_is_an_error_not_a_rounding(self):
        with self.assertRaises(lr.ReferenceError):
            lr.cap_units({"params": {"m": "1.5"}})


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
        routed = (
            set(bc.BIAS_CORE_TRACKS)
            | set(bc.BIAS_CORE_PASSIVE_TRACKS)
            | {"VDD", "VSS"}
        )
        self.assertEqual(routed | {lr.SUBSTRATE_NET}, declared)

    def passives(self, kind=None):
        golden = (REPO_ROOT / "design" / "netlist" / "bias_core.spice").read_text()
        parsed = lr.parse_passives(lr.subckt_body(golden, "bias_core"))
        if kind is None:
            return parsed
        return {n: c for n, c in parsed.items() if c["kind"] == kind}

    def res_cards(self):
        return [card for card in lr.build_cards(self.CELL) if card.prefix == "R"]

    def test_the_reference_covers_every_non_mos_device_in_the_schematic(self):
        # The whole point of #90: no device in design/bias_core.sch is outside
        # the compare any more. Read the golden netlist's own non-MOS cards
        # rather than restating the list, so a schematic that grew one fails.
        spec = lr.CELLS[self.CELL]
        golden = (REPO_ROOT / "design" / "netlist" / "bias_core.spice").read_text()
        body = lr.subckt_body(golden, "bias_core")
        self.assertEqual(set(self.passives("bipolar")), set(spec["bipolars"]))
        self.assertEqual(set(self.passives("resistor")), set(spec["resistors"]))
        self.assertEqual(set(lr.parse_capacitors(body)), set(spec["caps"]))
        # ... and every one of them is a class the deck has a device for, so
        # nothing is silently dropped by parse_passives on the way in.
        drawn = {
            line.split()[0]
            for line in body
            if line.split()[0].upper().startswith("X")
        }
        covered = (
            set(spec["devices"])
            | set(spec["resistors"])
            | set(spec["bipolars"])
            | set(spec["caps"])
        )
        self.assertEqual(drawn, covered)

    def test_the_four_formerly_shorted_net_pairs_are_distinct(self):
        # Each drawn poly resistor used to short its own two terminal nets when
        # the deck read its body as interconnect, which is why it was not drawn.
        # Assert every one of those pairs is two different declared nets, and
        # that the reference's own chain puts one resistor between them.
        spec = lr.CELLS[self.CELL]
        declared = set(spec["ports"]) | set(spec["internal"])
        resistors = self.passives("resistor")
        cards = self.res_cards()
        for name in spec["resistors"]:
            a_node, b_node, _bulk = resistors[name]["nodes"]
            self.assertNotEqual(a_node, b_node, name)
            self.assertIn(a_node, declared)
            self.assertIn(b_node, declared)
            ends = {net for card in cards for net in card.nodes[:2]}
            self.assertTrue({a_node, b_node} <= ends, name)

    def test_the_pnp_array_is_a_common_centroid_around_the_1x_device(self):
        # The 8:1 emitter ratio is what the whole reference rests on, so the
        # 8x leg's centroid has to be the 1x leg's. Assert it from the drawn
        # slot table rather than from the picture in the docstring.
        slots = bc.BIAS_CORE_PNP_SLOTS
        centre = slots["XQ1"]
        ring = [slots[f"XQ8{letter}"] for letter in "ABCDEFGH"]
        self.assertEqual(len(set(ring)), 8)
        self.assertEqual(
            (
                sum(column for column, _row in ring) / 8.0,
                sum(row for _column, row in ring) / 8.0,
            ),
            (float(centre[0]), float(centre[1])),
        )
        # ... and every one of the eight is orthogonally adjacent to it, i.e.
        # they are the perimeter of one 3x3 block, not a scattered ring.
        for column, row in ring:
            self.assertLessEqual(abs(column - centre[0]), 1)
            self.assertLessEqual(abs(row - centre[1]), 1)

    def test_every_resistor_fold_divides_its_length_exactly(self):
        # A leg length that is not an exact division of the golden r_length is
        # a resistance the drawn layout and the reference disagree about by a
        # rounding -- silent, and exactly what LVS's device.property would have
        # to catch. Catch it here instead.
        fold = lr.resistor_fold(self.CELL)
        for name, card in self.passives("resistor").items():
            length_um = lr.to_um(card["params"]["r_length"])
            segments = lr.resistor_segments(length_um, fold)
            legs, leg_um = len(segments), segments[0]
            self.assertEqual(legs % 2, 0, f"{name}: fold must be even-legged")
            self.assertLessEqual(leg_um, fold.max_um, name)
            self.assertEqual(
                round(leg_um * 1000.0) * legs, round(length_um * 1000.0), name
            )

    def test_each_drawn_pnp_keeps_its_own_base_region(self):
        # Two neighbouring DRC_BJT marks that touched would merge into one base
        # region, and every device in the array would then report that merged
        # region's AB/PB instead of its own -- a compare that still matches, but
        # against a number no longer derivable from one device's geometry.
        self.assertGreater(bc.PNP_GAP_UM, 2 * lr.BIPOLAR_BASE_MARGIN_UM)
        # ... and the Nwell tap ring stays clear of every mark, which is both
        # what keeps `bjt.separation.comp.1` clean and what stops the tap being
        # read as an eleventh emitter.
        self.assertGreater(bc.PNP_TAP_OFFSET_UM, lr.BIPOLAR_BASE_MARGIN_UM + 0.1)
        # ... and the mark sits inside the drawn well, so AB is the mark's area.
        self.assertGreater(bc.PNP_NWELL_MARGIN_UM, lr.BIPOLAR_BASE_MARGIN_UM)

    def test_the_resistor_fold_holds_the_decks_poly_spacing_rule(self):
        # DRM PL.3a / the deck's poly2.space.1: 0.24 um between two legs.
        self.assertGreaterEqual(bc.RES_SPACE_UM, 0.24)
        # The head runs past the marked body far enough to carry its own
        # contact clear of the bend row at the same edge.
        self.assertGreater(bc.RES_HEAD_UM, 2.0)

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
        # 1 um is a mismatch trade #15's data does not ask for, so the
        # divider's own leg width is read from the schematic and pinned here.
        leg_w, _lengths = bc._divider_resistor_lengths()
        self.assertEqual(leg_w, 2.0)

    def test_each_resistor_folds_into_an_odd_number_of_legs(self):
        # An odd leg count keeps the string's two open ends on opposite sides
        # (_resistor_string's docstring) -- narrow enough to be worth pinning.
        leg_w, lengths = bc._divider_resistor_lengths()
        for name in bc.POR_DIVIDER_RESISTORS:
            legs, _leg_len, _tail_extra = bc._resistor_leg_plan(lengths[name], leg_w)
            self.assertEqual(legs % 2, 1, name)

    def test_the_folded_legs_area_reconstructs_the_schematics_length(self):
        # _resistor_leg_plan's load-bearing identity (its own docstring): the
        # folded body's marked AREA, divided by leg width, must reconstruct
        # the schematic's r_length exactly (floating-point noise aside), or
        # the drawn resistor's value silently drifts from what the schematic
        # asks for.
        leg_w, lengths = bc._divider_resistor_lengths()
        for name in bc.POR_DIVIDER_RESISTORS:
            length_um = lengths[name]
            legs, leg_len, tail_extra = bc._resistor_leg_plan(length_um, leg_w)
            reconstructed = (
                legs * leg_len
                + tail_extra
                - 2 * bc.DIVIDER_CAP_UM
                + (legs - 1) * bc.DIVIDER_LEG_SPACE_UM
            )
            self.assertAlmostEqual(reconstructed, length_um, places=6, msg=name)

    def test_the_sense_divider_is_drawn_and_is_in_the_compare(self):
        # #91: the divider used to be reserved rather than drawn (the curated
        # deck modelled no resistor class at all). It is drawn for real now,
        # extracts as the deck's ppolyf_u_1k class, and the manifest carries
        # it in "resistors" (not "devices" -- see build_passive_cards).
        text = (REPO_ROOT / "design" / "netlist" / "por_comparator.spice").read_text()
        body = lr.subckt_body(text, "por_comparator")
        self.assertTrue(
            all(any(line.startswith(f"{r} ") for line in body)
                for r in bc.POR_DIVIDER_RESISTORS)
        )
        self.assertEqual(
            list(bc.POR_DIVIDER_RESISTORS),
            lr.CELLS["por_comparator"]["resistors"],
        )
        self.assertFalse(
            set(bc.POR_DIVIDER_RESISTORS) & set(lr.CELLS["por_comparator"]["devices"])
        )


class PorOutputChainManifestTest(unittest.TestCase):
    """``por_output_chain`` is the always-on POR domain's output cell. Beyond
    the structural checks ``bias_core`` gets, it carries one contract that is
    not a layout convention but a ratified one: DR-010 requires an ungated,
    always-on diode-connected input to remain on the shared ``IBIAS`` net, and
    ``XMBD`` is it."""

    CELL = "por_output_chain"
    SOURCE = "por_output_chain.spice"

    def golden(self):
        text = (REPO_ROOT / "design" / "netlist" / self.SOURCE).read_text()
        return lr.parse_devices(lr.subckt_body(text, self.CELL))

    def test_reference_matches_the_committed_file(self):
        committed = (LAYOUT_DIR / "cells" / f"{self.CELL}.reference.spice").read_text()
        self.assertEqual(lr.build(self.CELL), committed)

    def caps(self):
        text = (REPO_ROOT / "design" / "netlist" / self.SOURCE).read_text()
        return lr.parse_capacitors(lr.subckt_body(text, self.CELL))

    def test_every_mos_device_in_the_schematic_is_in_the_manifest(self):
        # Every MOS the deck can model must be present, or the layout is being
        # compared against a quietly reduced circuit. The MiM caps live in the
        # manifest's own `caps` field, not here.
        self.assertEqual(set(self.golden()), set(lr.CELLS[self.CELL]["devices"]))

    def test_every_mim_cap_in_the_schematic_is_drawn_and_compared(self):
        # #92: no cap is left out of either the drawn cell or the reference.
        self.assertEqual(set(self.caps()), set(lr.CELLS[self.CELL]["caps"]))
        self.assertEqual(set(self.caps()), set(bc.POC_MIM_ARRAYS))

    def test_each_cap_is_drawn_as_many_times_as_its_multiplier_says(self):
        # The deck models no `m` multiplier, so m=4 has to be four drawn plates
        # and four reference cards. A drawn array that disagreed with the
        # golden `m=` would fail LVS on device count; this says so first.
        caps = self.caps()
        for name, (columns, rows) in bc.POC_MIM_ARRAYS.items():
            self.assertEqual(columns * rows, lr.cap_units(caps[name]))
        cards = lr.build_cap_cards(self.CELL)
        self.assertEqual(len(cards), sum(lr.cap_units(c) for c in caps.values()))

    def test_cap_value_comes_from_the_golden_plate_size_not_a_typed_number(self):
        # The extracted capacitance is the drawn plates' overlap area times the
        # deck's 2.0 fF/um^2, and the drawn plate size is the golden card's own
        # c_width/c_length -- so the reference has to be derived from the same
        # two numbers or it is only ever agreeing with itself.
        caps = self.caps()
        # Card.value is already the same ``.6g``-rounded string build() writes
        # (formatted once, at construction, like every other Card) -- so the
        # expected set is rounded the same way rather than compared at full
        # float precision against a value that was never emitted at it.
        expected = {
            float(
                f"{lr.to_um(cap['params']['c_width']) * lr.to_um(cap['params']['c_length']) * lr.MIM_AREA_CAP_F_UM2:.6g}"
            )
            for cap in caps.values()
        }
        for card in lr.build_cap_cards(self.CELL):
            self.assertIn(float(card.value), expected)
        self.assertIn("2.42e-13", lr.build(self.CELL))  # XCDG, 11 x 11 um

    def test_cap_cards_carry_the_decks_own_device_class_name(self):
        # Without the class name KLayout's SPICE reader builds a generic CAP
        # class and every cap compares as an unmatched device -- a class
        # mismatch that reads like a missing device, not like a naming slip.
        klass = lr.CAP_CLASS["cap_mim_2f0_m3m4_noshield"]
        for line in lr.build(self.CELL).splitlines():
            if line.startswith("C"):
                self.assertTrue(line.endswith(f" {klass}"), line)

    def test_cap_plate_nets_are_isolated_per_drawn_unit(self):
        # klt cannot connect a recognised capacitor's plates to anything (see
        # cap_plate_nets), so each drawn unit's two plates must be their own
        # nets -- sharing one would describe a layout the deck cannot produce
        # and would fail LVS on net count.
        plates = [
            net for card in lr.build_cap_cards(self.CELL) for net in card.nodes
        ]
        self.assertEqual(len(plates), len(set(plates)))
        declared = set(lr.CELLS[self.CELL]["ports"]) | set(
            lr.CELLS[self.CELL]["internal"]
        )
        self.assertFalse(set(plates) & declared)

    def test_the_caps_own_no_net_by_themselves(self):
        # bias_core's undrawn passives delete three nets from both sides of the
        # compare. Here the caps delete none: both cap nodes carry MOS terminals
        # too, so the compare still covers every net in the schematic with all
        # of its MOS connections -- which is what keeps the plate-connectivity
        # gap above from narrowing what LVS answers for. If a future schematic
        # edit ever made a cap the sole owner of a node, this fails loudly.
        mos_nets = {net for d in self.golden().values() for net in d["nodes"]}
        cap_nets = {net for cap in self.caps().values() for net in cap["nodes"]}
        self.assertEqual(cap_nets, {"NDG", "TIM", "VSS"})
        self.assertTrue(cap_nets <= mos_nets, cap_nets - mos_nets)

        declared = set(lr.CELLS[self.CELL]["ports"]) | set(
            lr.CELLS[self.CELL]["internal"]
        )
        self.assertEqual(mos_nets | {lr.SUBSTRATE_NET}, declared)

    def test_the_always_on_ibias_diode_is_ungated(self):
        # DR-010: at least one always-on diode-connected input must remain on
        # the shared IBIAS net, and XMBD is the element that defines that
        # node's operating point. Drawn, diode-connected (gate == drain ==
        # IBIAS), source straight to VSS -- no series device in either path, so
        # no placement or routing choice can gate it.
        xmbd = self.golden()["XMBD"]
        drain, gate, source, _body = xmbd["nodes"]
        self.assertEqual((drain, gate, source), ("IBIAS", "IBIAS", "VSS"))
        self.assertIn("XMBD", lr.CELLS[self.CELL]["devices"])
        self.assertIn("XMBD", bc.POR_OUTPUT_CHAIN_NMOS)
        # ... and it is the IBIAS pin's own owner, so the pin label sits on
        # XMBD's terminal rather than on some net downstream of a switch.
        self.assertEqual(bc.POR_OUTPUT_CHAIN_PIN_ON["IBIAS"], ("XMBD", "d"))
        # Nothing else in the cell touches IBIAS except XMN1's *gate* (a mirror
        # read, not a series element in XMBD's path).
        on_ibias = {
            name: device["nodes"]
            for name, device in self.golden().items()
            if "IBIAS" in device["nodes"]
        }
        self.assertEqual(set(on_ibias), {"XMBD", "XMN1"})
        self.assertEqual(on_ibias["XMN1"][1], "IBIAS")  # gate only

    def test_the_push_pull_driver_is_at_the_pad_facing_edge(self):
        # floorplan.md places this cell nearest the RESETn pad for the shortest
        # run from the push-pull driver. Inside the cell that means XMON is the
        # last drawn device and XMOP the one before it, with the RESETn pin on
        # XMON's own drain.
        drawn = (
            list(bc.POR_OUTPUT_CHAIN_NMOS)
            + list(bc.POR_OUTPUT_CHAIN_PMOS)
            + list(bc.POR_OUTPUT_CHAIN_DRIVER)
        )
        self.assertEqual(drawn[-2:], ["XMOP", "XMON"])
        self.assertEqual(bc.POR_OUTPUT_CHAIN_PIN_ON["RESETn"], ("XMON", "d"))

    def test_topology_control_has_two_different_sources_to_work_with(self):
        devices = self.golden()
        first, second = lr.CELLS[self.CELL]["devices"][:2]
        self.assertNotEqual(devices[first]["nodes"][2], devices[second]["nodes"][2])
        self.assertNotEqual(
            lr.build(self.CELL), lr.build(self.CELL, corrupt="topology")
        )

    def test_every_pfet_is_assigned_to_the_one_drawn_well(self):
        spec = lr.CELLS[self.CELL]
        devices = self.golden()
        pfets = {n for n in spec["devices"] if devices[n]["model"] == "pfet_03v3"}
        self.assertEqual(pfets, set(spec["wells"]["NW1"]))
        self.assertEqual(pfets, set(bc.POR_OUTPUT_CHAIN_PMOS))

    def test_the_drawn_row_and_the_reference_cover_the_same_devices(self):
        drawn = (
            set(bc.POR_OUTPUT_CHAIN_NMOS)
            | set(bc.POR_OUTPUT_CHAIN_PMOS)
            | set(bc.POR_OUTPUT_CHAIN_DRIVER)
        )
        self.assertEqual(drawn, set(lr.CELLS[self.CELL]["devices"]))

    def test_every_net_the_layout_routes_is_a_net_the_reference_declares(self):
        spec = lr.CELLS[self.CELL]
        declared = set(spec["ports"]) | set(spec["internal"])
        routed = set(bc.POR_OUTPUT_CHAIN_TRACKS) | {"VDD", "VSS"}
        self.assertEqual(routed | {lr.SUBSTRATE_NET}, declared)

    def test_the_drawn_mim_plates_are_the_golden_plate_sizes(self):
        # Plate area *is* the capacitance, so a plate drawn at a size the
        # golden netlist does not name is a wrong capacitor that DRC would
        # happily pass. _mim_block reads c_width/c_length; this pins it.
        caps = self.caps()
        plates, _x1, _y1 = bc._mim_block(caps, bc.POC_MIM_ARRAYS, 0.0, 0.0)
        for name, _x, _y, width, height in plates:
            self.assertEqual(width, lr.to_um(caps[name]["params"]["c_width"]))
            self.assertEqual(height, lr.to_um(caps[name]["params"]["c_length"]))

    def test_the_drawn_mim_plates_hold_the_drm_spacing_and_enclosure(self):
        # MIMTM.1 (1.2 um bottom-plate space) and MIMTM.3 (0.6 um bottom-plate
        # enclosure of the top plate) are the two rules klt's deck checks. DRC
        # is the real gate; this fails first and by name if a future array
        # shape packs the plates tighter than the DRM allows.
        self.assertGreaterEqual(bc.MIM_SPACE_UM, 1.2)
        self.assertGreaterEqual(bc.MIM_ENCLOSURE_UM, 0.6)
        edge = bc.MIM_ENCLOSURE_UM
        plates, _x1, _y1 = bc._mim_block(self.caps(), bc.POC_MIM_ARRAYS, 0.0, 0.0)
        bottoms = [
            (x - edge, y - edge, x + w + edge, y + h + edge)
            for _name, x, y, w, h in plates
        ]
        for index, first in enumerate(bottoms):
            for second in bottoms[index + 1 :]:
                gap_x = max(first[0] - second[2], second[0] - first[2])
                gap_y = max(first[1] - second[3], second[1] - first[3])
                # rounded to the stream's own 1 nm database unit -- the grid
                # the geometry is actually written on, so this compares what
                # DRC will see rather than an accumulated float.
                self.assertGreaterEqual(
                    round(max(gap_x, gap_y), 3), bc.MIM_SPACE_UM, (first, second)
                )

    def test_the_mim_array_must_agree_with_the_golden_multiplier(self):
        # A 2x2 array for an m=4 cap is right; anything else is a silently
        # wrong device count, so _mim_block refuses rather than drawing it.
        with self.assertRaises(ValueError):
            bc._mim_block(self.caps(), {"XCTIM": (2, 3)}, 0.0, 0.0)

    def test_pin_labels_land_on_a_terminal_of_that_net(self):
        # A label only becomes an extracted pin inside a Metal1 shape on its
        # own net; naming a device/terminal that does not carry the net would
        # produce a silently missing pin, not an error.
        golden = self.golden()
        index = {"d": 0, "g": 1, "s": 2}
        for net, (owner, terminal) in bc.POR_OUTPUT_CHAIN_PIN_ON.items():
            self.assertEqual(golden[owner]["nodes"][index[terminal]], net)
            self.assertIn(net, lr.CELLS[self.CELL]["ports"])


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

    def passives(self):
        golden = (REPO_ROOT / "design" / "netlist" / "temp_core.spice").read_text()
        return lr.parse_passives(lr.subckt_body(golden, "temp_core"))

    def test_the_mim_cap_is_the_only_device_left_out(self):
        # #93 folded the PNPs and the poly resistors into the compare. XCC is
        # the one device still outside it, and it is outside for two reasons
        # the layout cannot fix (the deck models only the m4m5 MiM stack, and
        # a recognised MiM's plate nets are not joined to the routing
        # connectivity graph) -- so this asserts the *whole* gap, not a list
        # someone has to remember to shrink.
        golden = (REPO_ROOT / "design" / "netlist" / "temp_core.spice").read_text()
        body = lr.subckt_body(golden, "temp_core")
        spec = lr.CELLS[self.CELL]
        covered = set(spec["devices"]) | set(spec["resistors"]) | set(spec["bipolars"])
        drawn_names = {
            line.split()[0]
            for line in body
            if line.split()[0].upper().startswith("X")
        }
        self.assertEqual(drawn_names - covered, {"XCC"})

    def test_every_resistor_is_a_series_string_of_its_own_length(self):
        # The bank draws straight bodies and strings them, so the reference has
        # to describe the same string: N segments whose lengths sum back to the
        # schematic's own r_length, at the schematic's own r_width.
        passives = self.passives()
        cards = [
            line.split()
            for line in lr.build(self.CELL).splitlines()
            if line[:1] == "R"
        ]
        index = 0
        for name in lr.CELLS[self.CELL]["resistors"]:
            device = passives[name]
            length = lr.to_um(device["params"]["r_length"])
            width = lr.to_um(device["params"]["r_width"])
            segments = lr.resistor_segments(length)
            self.assertAlmostEqual(sum(segments), length, places=9, msg=name)
            self.assertEqual(len(segments) % 2, 0, f"{name}: odd segment count")
            chain = cards[index:index + len(segments)]
            index += len(segments)
            # head -> ... -> tail, one net shared by each consecutive pair
            head, tail, _bulk = device["nodes"]
            self.assertEqual(chain[0][1], head, name)
            self.assertEqual(chain[-1][2], tail, name)
            for before, after in zip(chain, chain[1:]):
                self.assertEqual(before[2], after[1], name)
            for card, segment in zip(chain, segments):
                self.assertEqual(card[3], lr.SUBSTRATE_NET)
                self.assertEqual(card[5], "ppolyf_u")
                self.assertAlmostEqual(
                    float(card[4]), segment / width * 350.0, places=6, msg=name
                )
        self.assertEqual(index, len(cards))

    def test_every_pnp_states_its_own_drawn_emitter_area(self):
        # The 8:1 emitter ratio is the whole point of the array, and AE is the
        # one bipolar parameter the compare checks -- so it is read out of the
        # PDK device name rather than retyped.
        passives = self.passives()
        cards = [
            line.split()
            for line in lr.build(self.CELL).splitlines()
            if line[:1] == "Q"
        ]
        names = lr.CELLS[self.CELL]["bipolars"]
        self.assertEqual(len(cards), len(names))
        for card, name in zip(cards, names):
            _collector, _base, emitter = passives[name]["nodes"]
            area = lr.emitter_area_um2(passives[name]["model"])
            self.assertEqual(card[1], lr.SUBSTRATE_NET)  # collector -> substrate
            self.assertEqual(card[2], lr.CELLS[self.CELL]["bjt_well"])
            self.assertEqual(card[3], emitter)
            self.assertEqual(card[5], f"AE={area:.10g}P")
        # XQ1 alone on NA, the eight XQ8 units in parallel on NC: the ratio.
        self.assertEqual(sum(1 for card in cards if card[3] == "NA"), 1)
        self.assertEqual(sum(1 for card in cards if card[3] == "NC"), 8)

    def test_a_length_that_does_not_split_on_the_grid_raises(self):
        # Silently rounding would make the drawn resistance differ from the
        # one this reference states, which reads as an unexplainable
        # device.property mismatch rather than as the netlist edit it is.
        with self.assertRaises(lr.ReferenceError):
            lr.resistor_segments(1.0001)

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


class TempPorTopAssemblyTest(unittest.TestCase):
    """``temp_por_top`` (#72) is the one manifest entry with no devices of its
    own: it is composed from the four sub-cells and from the golden top-level
    netlist's own instance lines. These cover the composition, because a
    silently wrong net mapping there produces a reference that is internally
    consistent, generates cleanly, and describes the wrong circuit."""

    CELL = "temp_por_top"

    def golden(self):
        return (REPO_ROOT / "design" / "netlist" / "temp_por_top.spice").read_text()

    def cards(self, text=None):
        return [
            line.split()
            for line in (text or lr.build(self.CELL)).splitlines()
            if line[:1] == "M"
        ]

    def test_reference_matches_the_committed_file(self):
        committed = (LAYOUT_DIR / "cells" / f"{self.CELL}.reference.spice").read_text()
        fresh = lr.build(self.CELL)
        if fresh == committed:
            # #97 has caught temp_por_top's own GDS/reference up with every
            # sub-cell's manifest -- the documented gap this test works
            # around below has closed, and there is nothing further to check.
            return
        # Three tracked, deliberate sources of drift, all waiting on #97:
        #
        #   1. #91 drew por_comparator's sense divider as three real
        #      ppolyf_u_1k resistors (XRTOP/XRBOT/XRHYS) and added them to
        #      that cell's manifest under "resistors".
        #   2. #90 drew bias_core's 10 vertical PNPs, 4 poly resistors and 2
        #      MiM caps, adding "bipolars"/"resistors"/"caps" to its manifest.
        #   3. Issue #56 added XMRLK, por_output_chain's release latch, as the
        #      28th entry of that cell's "devices" list.
        #
        # build_assembly composes each sub-cell through the same build_cards()
        # every standalone cell uses, so all three flow into a freshly
        # generated temp_por_top reference too -- but temp_por_top's own
        # committed GDS is deliberately *not* rebuilt for any of them
        # (rebuilding it against the grown sub-cell footprints is DRC-dirty at
        # the instance boundary, reproducible on main alone; #97 reworks the
        # floorplan once for all of #56/#90/#91/#92/#93 rather than once per
        # sub-cell change). So a fresh build is legitimately ahead of the
        # committed file by exactly those cards, and this test has to know that
        # rather than asserting a match it should not expect yet. Re-derive
        # with every deferred contribution removed from the live manifests and
        # require *that* to still match byte for byte -- proving the only drift
        # is the known, tracked one, not something else silently going stale
        # alongside it.
        deferred_keys = {
            # cell -> the manifest keys #97 has not caught this assembly up
            # with yet. Remove one from this table when #97 lands, not the
            # whole workaround: the early return above retires it.
            "por_comparator": ("resistors",),
            "bias_core": ("resistors", "bipolars", "caps"),
        }
        deferred_devices = {
            # cell -> individual "devices" entries that postdate the committed
            # assembly. Unlike the passives above these are ordinary MOS, so
            # they are pruned by name rather than by manifest key.
            "por_output_chain": ("XMRLK",),
        }
        originals = {
            cell: lr.CELLS[cell] for cell in (*deferred_keys, *deferred_devices)
        }
        try:
            for cell, keys in deferred_keys.items():
                pruned = dict(lr.CELLS[cell])
                for key in keys:
                    pruned.pop(key, None)
                lr.CELLS[cell] = pruned
            for cell, names in deferred_devices.items():
                pruned = dict(lr.CELLS[cell])
                pruned["devices"] = [
                    name for name in pruned["devices"] if name not in names
                ]
                self.assertEqual(
                    len(pruned["devices"]),
                    len(originals[cell]["devices"]) - len(names),
                    f"{cell}: {', '.join(names)} no longer in the manifest -- "
                    "this work-around is stale and should be revisited",
                )
                lr.CELLS[cell] = pruned
            pre_drift = lr.build(self.CELL)
        finally:
            lr.CELLS.update(originals)
        self.assertEqual(
            pre_drift,
            committed,
            "temp_por_top's committed reference has drifted from the "
            "assembly by more than #90's and #91's drawn passives and issue "
            "#56's XMRLK release latch -- see #97",
        )

    def test_pin_list_is_the_ratified_pinout_in_the_ratified_order(self):
        # The same assertion design/netlist.py --check makes at the schematic
        # level. Order, not just membership: the pinout is a hard external
        # contract, and agents do not relax a ratified spec to make a result
        # pass (CLAUDE.md).
        ratified = lr.subckt_ports(self.golden(), "temp_por_top")
        self.assertEqual(ratified, ["VDD", "VSS", "PTAT", "CTAT", "RESETn"])
        declared = [
            port for port in lr.CELLS[self.CELL]["ports"] if port != lr.SUBSTRATE_NET
        ]
        self.assertEqual(declared, ratified)
        self.assertEqual(bc.TOP_PINOUT, tuple(ratified))
        header = next(
            line
            for line in lr.build(self.CELL).splitlines()
            if line.upper().startswith(".SUBCKT")
        )
        self.assertEqual(
            header.split()[2:], ratified + [lr.SUBSTRATE_NET]
        )

    def test_every_sub_cell_device_is_carried_into_the_assembly(self):
        expected = 0
        for _inst, sub in lr.CELLS[self.CELL]["assembly"]:
            spec = lr.CELLS[sub]
            expected += (
                len(spec["devices"])
                + sum(count - 1 for count in spec.get("fingers", {}).values())
                + len(spec.get("dummies", []))
            )
        self.assertEqual(len(self.cards()), expected)

    def test_every_sub_cell_non_mos_device_is_carried_into_the_assembly(self):
        # Extraction is flat, so a sub-cell's drawn resistors, bipolars and MiM
        # caps land in this cell's compare too. Assert the composed reference
        # carries exactly as many of each as the sub-cells' own manifests build.
        composed = collections.Counter(
            card.prefix for card in lr.build_assembly(self.CELL)
        )
        expected = collections.Counter()
        for _inst, sub in lr.CELLS[self.CELL]["assembly"]:
            known = (
                set(lr.CELLS[sub]["ports"])
                | set(lr.CELLS[sub].get("wells", {}))
                | set(lr.CELLS[sub].get("internal", []))
                | set(filter(None, [lr.CELLS[sub].get("bjt_well")]))
            )
            expected.update(
                card.prefix
                for card in lr.build_passive_cards(sub, known, lambda net: net)
            )
            expected.update(card.prefix for card in lr.build_cap_cards(sub))
        for prefix in "RQC":
            self.assertEqual(composed[prefix], expected[prefix], prefix)
        # ... and that they actually reach the emitted netlist.
        emitted = collections.Counter(
            line[:1] for line in lr.build(self.CELL).splitlines() if line[:1] in "CRQ"
        )
        self.assertEqual(dict(emitted), {k: v for k, v in expected.items() if v})

    def test_shared_nets_are_one_net_across_instances(self):
        # The whole point of the assembly: IBIAS is one node all four
        # sub-circuits sit on (DR-010), VREF/BIAS_OK/POR_RAW each join two.
        cards = self.cards()
        for net, instances in (
            ("IBIAS", {"xbias", "xcmp", "xpor", "xtemp"}),
            ("VREF", {"xbias", "xcmp"}),
            ("BIAS_OK", {"xbias", "xcmp"}),
            ("POR_RAW", {"xcmp", "xpor"}),
            ("VDD", {"xbias", "xcmp", "xpor", "xtemp"}),
            ("VSS", {"xbias", "xcmp", "xpor", "xtemp"}),
            ("RESETn", {"xpor", "xtemp"}),
        ):
            touching = {
                card[0]
                for card in cards
                if net in card[1:5]
            }
            self.assertTrue(touching, f"{net} touches no device")
            # Each such card is one instance's; identify it by the prefixed
            # nets it also carries.
            owners = {
                node.split(".", 1)[0]
                for card in cards
                if net in card[1:5]
                for node in card[1:5]
                if "." in node
            }
            self.assertEqual(
                owners, instances, f"{net} is not shared by the right instances"
            )

    def test_instance_internal_nets_stay_distinct(self):
        # bias_core, por_comparator and temp_core all have a net called PG.
        # Merging them would be a short LVS could only report as a topology
        # mismatch a long way from its cause.
        nodes = {node for card in self.cards() for node in card[1:5]}
        for net in ("PG", "NA", "NB", "N1", "N2", "NT", "NBG", "PB"):
            self.assertNotIn(net, nodes, f"{net} leaked out of its instance")
        self.assertIn("xbias.PG", nodes)
        self.assertIn("xtemp.PG", nodes)
        self.assertIn("xcmp.NW1", nodes)
        self.assertIn("xpor.NW1", nodes)

    def test_substrate_global_is_never_prefixed(self):
        nodes = {node for card in self.cards() for node in card[1:5]}
        self.assertIn(lr.SUBSTRATE_NET, nodes)
        for node in nodes:
            self.assertFalse(node.endswith(f".{lr.SUBSTRATE_NET}"))

    def test_controls_still_change_exactly_one_card(self):
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

    def test_a_wrong_pinout_is_an_error_not_a_quietly_different_block(self):
        spec = dict(lr.CELLS[self.CELL])
        self.addCleanup(lr.CELLS.__setitem__, self.CELL, lr.CELLS[self.CELL])
        lr.CELLS[self.CELL] = {
            **spec,
            "ports": ["VSS", "VDD", "PTAT", "CTAT", "RESETn", lr.SUBSTRATE_NET],
        }
        with self.assertRaises(lr.ReferenceError):
            lr.build(self.CELL)

    def test_a_wrong_instance_model_is_an_error(self):
        spec = dict(lr.CELLS[self.CELL])
        self.addCleanup(lr.CELLS.__setitem__, self.CELL, lr.CELLS[self.CELL])
        lr.CELLS[self.CELL] = {
            **spec,
            "assembly": [("xbias", "por_comparator")] + spec["assembly"][1:],
        }
        with self.assertRaises(lr.ReferenceError):
            lr.build(self.CELL)


class TempPorTopRouteCheckTest(unittest.TestCase):
    """``_TopRoutes.check`` is the only thing standing between this block and
    the two defects the automated flow provably cannot see (both demonstrated
    against ``klt drc``/``klt lvs`` in the PR for #72): a different-net overlap
    that DRC reads as one legal polygon, and a guard ring that is drawn but
    never actually joined to ``VSS``. Pure python -- no klayout needed."""

    class _FakeBuilder:
        def box(self, *_args, **_kwargs):
            pass

    def routes(self):
        return bc._TopRoutes(self._FakeBuilder())

    def test_a_clean_two_net_pattern_passes(self):
        routes = self.routes()
        routes.hwire("A", 0.0, 0.0, 10.0)
        routes.hwire("B", 5.0, 0.0, 10.0)
        routes.check()

    def test_two_nets_overlapping_on_one_layer_is_a_short(self):
        routes = self.routes()
        routes.hwire("A", 0.0, 0.0, 10.0)
        routes.hwire("B", 0.0, 5.0, 15.0)
        with self.assertRaises(AssertionError) as caught:
            routes.check()
        self.assertIn("SHORT", str(caught.exception))

    def test_two_nets_closer_than_the_deck_rule_is_a_spacing_error(self):
        routes = self.routes()
        routes.hwire("A", 0.0, 0.0, 10.0)
        routes.hwire("B", bc.TOP_WIRE_W + 0.1, 0.0, 10.0)
        with self.assertRaises(AssertionError) as caught:
            routes.check()
        self.assertIn("spacing", str(caught.exception))

    def test_a_via_may_not_bridge_two_nets(self):
        routes = self.routes()
        routes.hwire("A", 0.0, 0.0, 10.0)
        routes.vwire("B", 5.0, -10.0, 10.0)  # Metal3 crossing Metal2: legal
        routes.check()
        routes.via2("A", 5.0, 0.0)  # ... until a via lands on the crossing
        with self.assertRaises(AssertionError) as caught:
            routes.check()
        self.assertIn("more than one net", str(caught.exception))

    def test_a_net_drawn_in_two_pieces_is_an_error(self):
        # This is the floating-guard-ring case: shapes that carry the right
        # net label but are not joined to it.
        routes = self.routes()
        routes.hwire("VSS", 0.0, 0.0, 10.0)
        routes.hwire("VSS", 0.0, 50.0, 60.0)
        with self.assertRaises(AssertionError) as caught:
            routes.check()
        self.assertIn("disconnected pieces", str(caught.exception))


class TempPorTopFloorplanTest(unittest.TestCase):
    """The block-level floorplan claims that are checkable without drawing."""

    def test_every_crossing_net_is_routed_and_nothing_else_is(self):
        # Exactly the nets design/netlist/temp_por_top.spice puts on more than
        # one instance line. A net dropped from TOP_NET_PINS would extract as
        # two unconnected nets; a net added would be a wire to nowhere.
        text = (REPO_ROOT / "design" / "netlist" / "temp_por_top.spice").read_text()
        seen: dict[str, int] = {}
        for line in lr.subckt_body(text, "temp_por_top"):
            fields = line.split()
            if fields[0].lower().startswith("x"):
                for net in fields[1:-1]:
                    seen[net] = seen.get(net, 0) + 1
        crossing = {net for net, count in seen.items() if count > 1}
        self.assertEqual(set(bc.TOP_NET_PINS), crossing)

    def test_the_two_domains_are_placed_on_opposite_sides_of_the_seam(self):
        placement = {name: (dx, dy) for name, _inst, dx, dy in bc.TOP_PLACEMENT}
        self.assertEqual(placement["temp_core"], (0.0, 0.0))
        for por_cell in ("bias_core", "por_comparator", "por_output_chain"):
            self.assertLess(placement[por_cell][1], bc.TOP_SEAM_Y)
        # bias_core is the POR domain's seam-facing, leftmost cell: it is what
        # both domains consume (layout/floorplan.md, "Placement rationale").
        self.assertLess(placement["bias_core"][0], placement["por_comparator"][0])
        self.assertLess(placement["por_comparator"][0], placement["por_output_chain"][0])

    def test_each_crossing_net_has_its_own_trunk_and_column(self):
        ys = list(bc.TOP_TRUNK_Y.values())
        self.assertEqual(len(ys), len(set(ys)))
        xs = list(bc.TOP_MARGIN_X.values())
        self.assertEqual(len(xs), len(set(xs)))
        self.assertNotIn("VSS", bc.TOP_TRUNK_Y)  # VSS's trunk is the rail


class DeckHashConsistencyTest(unittest.TestCase):
    """``check_deck_hash_consistency`` is the guard #103 added so committed
    ``layout/reports/*/drc.json`` cannot silently drift onto two different
    ``klt`` deck revisions the way `por_comparator`'s did (see #102). It
    operates on a real reports directory, so every case here builds one from
    scratch under a temp dir rather than touching the committed reports."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.reports_dir = Path(self._tmp.name)

    def _write(self, cell: str, content_hash: str | None, malformed: bool = False):
        cell_dir = self.reports_dir / cell
        cell_dir.mkdir(parents=True, exist_ok=True)
        path = cell_dir / "drc.json"
        if malformed:
            path.write_text("{not json")
            return
        payload: dict = {"status": "clean", "violation_count": 0}
        if content_hash is not None:
            payload["provenance"] = {"deck": {"content_hash": content_hash}}
        else:
            payload["provenance"] = {"deck": {}}
        path.write_text(json.dumps(payload))

    def test_one_shared_hash_is_clean(self):
        self._write("por_comparator", "sha256:aaa")
        self._write("temp_core", "sha256:aaa")
        self._write("por_output_chain", "sha256:aaa")
        self.assertEqual(lr.check_deck_hash_consistency(self.reports_dir), [])

    def test_two_hashes_across_non_frozen_cells_is_a_failure(self):
        self._write("bias_core", "sha256:new")
        self._write("por_comparator", "sha256:old")
        self._write("temp_core", "sha256:old")
        failures = lr.check_deck_hash_consistency(self.reports_dir)
        self.assertEqual(len(failures), 1)
        self.assertIn("sha256:new", failures[0])
        self.assertIn("sha256:old", failures[0])
        self.assertIn("bias_core", failures[0])
        self.assertIn("por_comparator", failures[0])

    def test_temp_por_top_frozen_exception_is_tolerated(self):
        if "temp_por_top" not in lr.FROZEN_DECK_CELLS:
            self.skipTest(
                "temp_por_top is no longer frozen -- the exception this test "
                "holds has nothing to exercise (see #111)"
            )
        # temp_por_top may lag behind #97; every other cell must still agree.
        self._write("por_comparator", "sha256:current")
        self._write("temp_core", "sha256:current")
        self._write("temp_por_top", "sha256:stale-behind-97")
        self.assertEqual(lr.check_deck_hash_consistency(self.reports_dir), [])

    def test_frozen_cell_disagreement_does_not_mask_a_real_non_frozen_split(self):
        if "temp_por_top" not in lr.FROZEN_DECK_CELLS:
            self.skipTest(
                "temp_por_top is no longer frozen -- the exception this test "
                "holds has nothing to exercise (see #111)"
            )
        # The frozen exception must not become a blanket bypass: a real split
        # among the *non*-frozen cells still has to fail even with a frozen
        # cell present in the same directory.
        self._write("por_comparator", "sha256:current")
        self._write("temp_core", "sha256:different")
        self._write("temp_por_top", "sha256:stale-behind-97")
        failures = lr.check_deck_hash_consistency(self.reports_dir)
        self.assertEqual(len(failures), 1)
        # temp_por_top is only named in the "excluded as frozen" aside, never
        # as one of the disagreeing cells -- its own (different-again) hash
        # must not appear attributed to either side of the real split.
        self.assertNotIn("sha256:stale-behind-97", failures[0])
        self.assertIn("por_comparator", failures[0])
        self.assertIn("temp_core", failures[0])

    def test_missing_provenance_is_a_failure_even_when_frozen(self):
        self._write("por_comparator", "sha256:current")
        self._write("temp_por_top", None)
        failures = lr.check_deck_hash_consistency(self.reports_dir)
        self.assertEqual(len(failures), 1)
        self.assertIn("temp_por_top", failures[0])
        self.assertIn("no provenance.deck.content_hash", failures[0])

    def test_unreadable_report_is_a_failure(self):
        self._write("por_comparator", "sha256:current")
        self._write("temp_core", None, malformed=True)
        failures = lr.check_deck_hash_consistency(self.reports_dir)
        self.assertEqual(len(failures), 1)
        self.assertIn("temp_core", failures[0])

    def test_a_single_cell_is_trivially_consistent(self):
        self._write("por_comparator", "sha256:only-one")
        self.assertEqual(lr.check_deck_hash_consistency(self.reports_dir), [])

    def test_no_reports_at_all_is_not_a_failure(self):
        # An empty reports/ directory is a "nothing to check" state, not a
        # drift finding -- the per-cell checks in run_checks.sh are what
        # require reports to exist at all.
        self.assertEqual(lr.check_deck_hash_consistency(self.reports_dir), [])


class GdsHashConsistencyTest(unittest.TestCase):
    """``check_gds_hash`` is the guard #106 added: #102's `por_comparator`
    false-clean `drc.json` was textually indistinguishable from a genuine
    clean one because nothing in the report recorded which GDS bytes it was
    run against. This operates on real reports/cells directories built from
    scratch under a temp dir, exactly like ``DeckHashConsistencyTest`` above,
    so it never touches the committed evidence."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.reports_dir = Path(self._tmp.name) / "reports"
        self.cells_dir = Path(self._tmp.name) / "cells"
        self.reports_dir.mkdir()
        self.cells_dir.mkdir()

    def _gds(self, cell: str, content: bytes = b"fake gds stream") -> str:
        """Write ``<cell>.gds`` and return its sha256."""
        path = self.cells_dir / f"{cell}.gds"
        path.write_bytes(content)
        return lr.sha256_bytes(content)

    def _write(self, cell: str, name: str, payload: dict | None, malformed: bool = False):
        cell_dir = self.reports_dir / cell
        cell_dir.mkdir(parents=True, exist_ok=True)
        path = cell_dir / name
        if malformed:
            path.write_text("{not json")
            return
        path.write_text(json.dumps(payload))

    def test_matching_digests_across_all_three_reports_is_clean(self):
        digest = self._gds("por_comparator")
        self._write(
            "por_comparator", "drc.json", {"provenance": {"gds_sha256": digest}}
        )
        self._write(
            "por_comparator", "extract.json", {"provenance": {"gds_sha256": digest}}
        )
        self._write(
            "por_comparator",
            "lvs.json",
            {"environment": {"layout_sha256": digest}},
        )
        self.assertEqual(
            lr.check_gds_hash(self.reports_dir, self.cells_dir), []
        )

    def test_stale_drc_json_is_a_failure(self):
        # Reproduces the #102 scenario: a committed report whose recorded
        # digest disagrees with the actual committed GDS.
        digest = self._gds("por_comparator")
        self._write(
            "por_comparator", "drc.json", {"provenance": {"gds_sha256": "stale" * 12}}
        )
        failures = lr.check_gds_hash(self.reports_dir, self.cells_dir)
        self.assertEqual(len(failures), 1)
        self.assertIn("por_comparator", failures[0])
        self.assertIn("drc.json", failures[0])
        self.assertIn("stale", failures[0])

    def test_stale_extract_json_is_a_failure(self):
        self._gds("temp_core")
        self._write(
            "temp_core", "extract.json", {"provenance": {"gds_sha256": "b" * 64}}
        )
        failures = lr.check_gds_hash(self.reports_dir, self.cells_dir)
        self.assertEqual(len(failures), 1)
        self.assertIn("temp_core", failures[0])
        self.assertIn("extract.json", failures[0])

    def test_stale_lvs_json_is_a_failure(self):
        # lvs.json already carried environment.layout_sha256 before #106 --
        # this check must still catch drift there, not just in the two new
        # fields.
        self._gds("bias_core")
        self._write(
            "bias_core", "lvs.json", {"environment": {"layout_sha256": "c" * 64}}
        )
        failures = lr.check_gds_hash(self.reports_dir, self.cells_dir)
        self.assertEqual(len(failures), 1)
        self.assertIn("bias_core", failures[0])
        self.assertIn("lvs.json", failures[0])

    def test_missing_field_is_a_failure(self):
        self._gds("por_comparator")
        self._write("por_comparator", "drc.json", {"provenance": {}})
        failures = lr.check_gds_hash(self.reports_dir, self.cells_dir)
        self.assertEqual(len(failures), 1)
        self.assertIn("no provenance.gds_sha256", failures[0])

    def test_unreadable_report_is_a_failure(self):
        self._gds("por_comparator")
        self._write("por_comparator", "drc.json", None, malformed=True)
        failures = lr.check_gds_hash(self.reports_dir, self.cells_dir)
        self.assertEqual(len(failures), 1)
        self.assertIn("por_comparator", failures[0])

    def test_report_directory_with_no_matching_gds_is_skipped(self):
        # Not this check's invariant -- build_cells.py --check /
        # lvs_reference.py --check own "is there a committed GDS at all".
        self._write(
            "no_such_cell", "drc.json", {"provenance": {"gds_sha256": "d" * 64}}
        )
        self.assertEqual(
            lr.check_gds_hash(self.reports_dir, self.cells_dir), []
        )

    def test_no_reports_at_all_is_not_a_failure(self):
        self.assertEqual(
            lr.check_gds_hash(self.reports_dir, self.cells_dir), []
        )

    def test_multiple_cells_each_checked_independently(self):
        good_digest = self._gds("bias_core")
        bad_digest = self._gds("temp_core")
        self._write(
            "bias_core", "drc.json", {"provenance": {"gds_sha256": good_digest}}
        )
        self._write(
            "temp_core",
            "drc.json",
            {"provenance": {"gds_sha256": bad_digest[::-1]}},  # deliberately wrong
        )
        failures = lr.check_gds_hash(self.reports_dir, self.cells_dir)
        self.assertEqual(len(failures), 1)
        self.assertIn("temp_core", failures[0])


class DeckHashGateBootstrapTest(unittest.TestCase):
    """``run_checks.sh --regen-all`` (#108) is the deck-hash gate's bootstrap
    mode. The gate's own remediation is "regenerate every non-frozen cell's
    reports against one deck (bash layout/run_checks.sh)" -- but the gate ran
    before any per-cell work under ``set -e``, so it aborted the very run that
    was supposed to perform that regeneration, and *every* invocation of the
    script (single-cell runs included) was blocked once the committed reports
    had legitimately drifted onto two decks.

    The danger in fixing that is fixing it too hard: an escape hatch that
    *skips* the gate rather than *deferring* it silently retires the invariant
    #104 added it to enforce. These tests pin the difference. They are the only
    coverage of the shell's control flow -- ``DeckHashConsistencyTest`` above
    exercises the pure function against a synthetic directory and would stay
    green even if the script stopped calling it entirely."""

    SCRIPT_PATH = LAYOUT_DIR / "run_checks.sh"

    @classmethod
    def setUpClass(cls):
        cls.script = cls.SCRIPT_PATH.read_text()

    # --- the frozen-cell list is declared once, in python -------------------

    def test_list_frozen_deck_cells_prints_the_gate_s_own_exclusions(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = lr.main(["--list-frozen-deck-cells"])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().split(), sorted(lr.FROZEN_DECK_CELLS))

    def test_regen_all_reads_that_list_rather_than_keeping_its_own(self):
        # A second copy of the frozen set in the shell is a copy that drifts:
        # --regen-all would then re-stamp a cell the gate still excuses (or
        # skip one it no longer does).
        self.assertIn("--list-frozen-deck-cells", self.script)

    # --- deferred, not skipped ---------------------------------------------

    def test_the_gate_is_still_run_on_ordinary_invocations(self):
        # The pre-run gate must be guarded by "--regen-all was NOT passed",
        # not by anything weaker: a plain run and a single-cell run still gate
        # before touching a single report.
        self.assertRegex(
            self.script,
            r'if \[ "\$REGEN_ALL" -eq 0 \]; then\n'
            r'\s+info "==> checking layout/reports/ agree on one deck[^"]*"\n'
            r"\s+python3 layout/lvs_reference\.py --check-deck-hash\n",
        )

    def test_regen_all_asserts_the_gate_afterwards_instead_of_dropping_it(self):
        # Exactly two invocations: the pre-run gate for ordinary runs, and the
        # post-run assertion --regen-all defers it to. One would mean the hatch
        # waives the check; the guard here is that removing the second one
        # fails a test rather than passing review.
        #
        # Count *invocations*, not bare occurrences of the flag name: the
        # script's prose also references `--check-deck-hash` when explaining
        # the neighbouring GDS-hash gate (#109), and a comment mentioning the
        # flag must not read as a third call to it.
        self.assertEqual(
            self.script.count("python3 layout/lvs_reference.py --check-deck-hash"),
            2,
        )
        deferred = self.script.split("# --- deferred deck-hash assertion")[-1]
        self.assertIn("--check-deck-hash", deferred)

    def test_a_failed_deferred_assertion_fails_the_run(self):
        deferred = self.script.split("# --- deferred deck-hash assertion")[-1]
        # It must set the script's failure status, and must not be neutered
        # with `|| true` / `set +e`.
        self.assertIn("status=1", deferred)
        self.assertNotIn("|| true", deferred)
        self.assertNotIn("set +e", self.script)

    def test_no_environment_variable_can_switch_the_gate_off(self):
        # The hatch is a flag on one invocation, not repo state: nothing may
        # read a SKIP/BYPASS-style variable, which would outlive the run that
        # set it (a CI export, a shell rc) and disable the gate for everyone.
        self.assertNotRegex(self.script, r"(?i)\$\{?(SKIP|BYPASS|NO)_[A-Z_]*DECK")

    # --- behaviour, against a sandboxed copy of the script ------------------

    def _sandbox(self, tmp: Path) -> Path:
        """A throwaway repo root holding just ``layout/run_checks.sh`` and a
        stub ``klt``, so the argument-handling paths can be exercised for real
        without ``klt`` and without touching the committed reports."""
        (tmp / "layout").mkdir(parents=True, exist_ok=True)
        script = tmp / "layout" / "run_checks.sh"
        script.write_text(self.script)
        bindir = tmp / "bin"
        bindir.mkdir(exist_ok=True)
        stub = bindir / "klt"
        stub.write_text(
            "#!/usr/bin/env bash\n"
            'if [ "$1" = "--version" ]; then echo "klt 0.0.0-stub"; fi\nexit 0\n'
        )
        stub.chmod(0o755)
        return script

    def _run(self, tmp: Path, *args: str):
        script = self._sandbox(tmp)
        env = dict(os.environ, PATH=f"{tmp / 'bin'}:{os.environ['PATH']}")
        return subprocess.run(
            ["bash", str(script), *args],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_regen_all_refuses_a_cell_argument(self):
        # A subset regeneration is exactly what produces the drift the flag
        # exists to repair, so `--regen-all <cell>` is an error, not a
        # convenience: it must never become a per-cell gate bypass.
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(Path(tmp), "--regen-all", "bias_core")
        self.assertEqual(result.returncode, 2)
        self.assertIn("takes no cell argument", result.stdout + result.stderr)

    def test_check_env_still_works_alongside_the_new_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(Path(tmp), "--check-env")
        self.assertEqual(result.returncode, 0)
        self.assertIn("klt 0.0.0-stub", result.stdout)

    def test_the_script_is_syntactically_valid(self):
        result = subprocess.run(
            ["bash", "-n", str(self.SCRIPT_PATH)], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class FrozenCellTest(unittest.TestCase):
    """``FROZEN_CELLS`` (#102) is what lets one cell's committed artefacts stay
    behind their sources without taking the whole staleness gate down with them
    (``layout/run_checks.sh`` runs both ``--check`` gates under ``set -e``
    before any per-cell DRC/LVS runs, so one stale cell used to abort every
    check in the repo).

    A freeze must not degrade into "stop checking this cell". These cover the
    part that keeps it honest: the committed bytes are still verified on every
    run against a digest recorded in the manifest, so only the comparison
    against a *fresh rebuild* -- the thing the tracking issue owns -- is
    suspended."""

    ARTEFACTS = (("gds", ".gds"), ("reference", ".reference.spice"))

    def frozen(self, digest, artefact="reference", issue="#1"):
        """A one-entry FROZEN_CELLS patch pinning ``artefact`` to ``digest``."""
        return unittest.mock.patch.dict(
            lr.FROZEN_CELLS,
            {
                "cell_under_test": {
                    "issue": issue,
                    "why": "test fixture",
                    f"{artefact}_sha256": digest,
                }
            },
            clear=True,
        )

    def test_every_frozen_cell_is_a_real_cell_in_both_manifests(self):
        # Both --check paths read this one table, so a typo'd cell name would
        # silently freeze nothing at all.
        for name in lr.FROZEN_CELLS:
            self.assertIn(name, lr.CELLS, f"{name}: not in lvs_reference.CELLS")
            self.assertIn(name, bc.CELLS, f"{name}: not in build_cells.CELLS")

    def test_every_freeze_names_a_tracking_issue_and_pins_both_artefacts(self):
        for name, spec in lr.FROZEN_CELLS.items():
            self.assertRegex(spec["issue"], r"^#\d+$", f"{name}: no tracking issue")
            self.assertTrue(spec["why"].strip(), f"{name}: no stated reason")
            for artefact, _suffix in self.ARTEFACTS:
                self.assertRegex(
                    spec[f"{artefact}_sha256"],
                    r"^[0-9a-f]{64}$",
                    f"{name}: {artefact} is not pinned to a sha256",
                )

    def test_the_pinned_digests_are_the_committed_artefacts(self):
        # The load-bearing one, and the reason a freeze is not a bypass: this
        # runs in CI (stdlib only, no klt) and fails the moment a frozen
        # artefact is regenerated or edited without updating its pin.
        for name, spec in lr.FROZEN_CELLS.items():
            for artefact, suffix in self.ARTEFACTS:
                path = LAYOUT_DIR / "cells" / f"{name}{suffix}"
                verdict = lr.frozen_check(name, artefact, path)
                self.assertIsNotNone(verdict, f"{name}: not seen as frozen")
                self.assertTrue(verdict.ok, verdict.line)
                self.assertIn(spec["issue"], verdict.line)

    def test_an_unfrozen_cell_gets_no_verdict_at_all(self):
        # None means "run the normal rebuild-and-compare"; a truthy verdict here
        # would quietly excuse every cell.
        path = LAYOUT_DIR / "cells" / f"{CELL}.reference.spice"
        self.assertNotIn(CELL, lr.FROZEN_CELLS)
        self.assertIsNone(lr.frozen_check(CELL, "reference", path))

    def test_a_frozen_artefact_that_changed_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "frozen.spice")
            path.write_text("* the pinned baseline\n")
            pinned = lr.sha256_bytes(path.read_bytes())
            path.write_text("* somebody regenerated it\n")
            with self.frozen(pinned, issue="#42"):
                verdict = lr.frozen_check("cell_under_test", "reference", path)
        self.assertFalse(verdict.ok)
        self.assertIn("pinned frozen baseline", verdict.line)
        self.assertIn("#42", verdict.line)

    def test_a_frozen_artefact_that_is_missing_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "absent.spice")
            with self.frozen("0" * 64):
                verdict = lr.frozen_check("cell_under_test", "reference", path)
        self.assertFalse(verdict.ok)
        self.assertIn("not committed", verdict.line)

    def test_a_freeze_that_forgets_to_pin_an_artefact_raises(self):
        # Better a loud KeyError than a freeze that checks one artefact and
        # waves the other through.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "frozen.gds")
            path.write_text("x")
            with self.frozen("0" * 64, artefact="reference"):
                with self.assertRaises(KeyError):
                    lr.frozen_check("cell_under_test", "gds", path)

    def check_in_sandbox(self, name, text):
        """``lvs_reference.py --check --cell <name>`` against a fake cells/ dir
        holding exactly ``text`` as that cell's committed reference."""
        with tempfile.TemporaryDirectory() as tmp:
            cells = Path(tmp, "cells")
            cells.mkdir()
            (cells / f"{name}.reference.spice").write_text(text)
            with (
                unittest.mock.patch.object(lr, "CELLS_DIR", cells),
                unittest.mock.patch.object(lr, "REPO_ROOT", Path(tmp)),
                contextlib.redirect_stdout(io.StringIO()) as out,
            ):
                code = lr.run(check=True, only=name, corrupt=None, out=None)
        return code, out.getvalue()

    def test_check_still_fails_an_unfrozen_stale_reference(self):
        # The regression the frozen mechanism must not cause: staleness
        # checking stays live for every cell that is not explicitly frozen.
        code, output = self.check_in_sandbox(CELL, "* deliberately stale\n")
        self.assertEqual(code, 1)
        self.assertIn("committed reference netlist is stale", output)

    def test_check_passes_a_frozen_cell_whose_reference_is_stale(self):
        stale = "* deliberately stale, and deliberately pinned\n"
        digest = lr.sha256_bytes(stale.encode())
        with unittest.mock.patch.dict(
            lr.FROZEN_CELLS,
            {CELL: {"issue": "#42", "why": "test fixture", "reference_sha256": digest}},
        ):
            code, output = self.check_in_sandbox(CELL, stale)
        self.assertEqual(code, 0)
        self.assertIn("frozen", output)
        self.assertIn("#42", output)
        # ... and it says "frozen", not "ok": a reader can tell the two apart.
        self.assertNotIn("ok ", output)


class PinnedReportCellsTest(unittest.TestCase):
    """``pinned_report_cells`` (#111) is the whole decision behind the guard
    ``layout/run_checks.sh`` applies to a frozen cell's committed *reports*:
    a whole-repo run must not rewrite them (that re-stamps evidence recorded
    under an older deck onto today's, so a ``git add -A`` ends the freeze
    without anyone deciding to), while naming the cell explicitly must."""

    def test_a_whole_repo_run_pins_every_frozen_cell(self):
        self.assertEqual(lr.pinned_report_cells([]), sorted(lr.FROZEN_CELLS))

    def test_frozen_deck_cells_is_derived_from_frozen_cells_not_a_second_list(self):
        # run_checks.sh --regen-all excludes FROZEN_DECK_CELLS from the cells it
        # regenerates, then separately asks --pinned-report-cells (backed by
        # FROZEN_CELLS) which of *those* cells to still treat as read-only --
        # today that second check is a no-op only because --regen-all already
        # excluded the same cells, which holds only if the two registries name
        # exactly the same set. Asserting FROZEN_DECK_CELLS == frozenset(
        # FROZEN_CELLS) here (rather than two independently maintained
        # collections that happen to agree) is what keeps that true by
        # construction instead of by coincidence.
        self.assertEqual(lr.FROZEN_DECK_CELLS, frozenset(lr.FROZEN_CELLS))

    def test_naming_cells_explicitly_pins_nothing(self):
        # Naming a cell is the deliberate "regenerate it anyway" path, the same
        # override --cell already is for the two regeneration passes.
        for named in (["temp_por_top"], ["temp_core"], ["temp_core", CELL]):
            self.assertEqual(lr.pinned_report_cells(named), [], named)

    def test_no_frozen_cells_is_a_no_op_in_both_directions(self):
        # The removal condition: once the freezes are lifted the guard has to
        # go quiet by itself rather than needing to be taken back out.
        with unittest.mock.patch.dict(lr.FROZEN_CELLS, {}, clear=True):
            self.assertEqual(lr.pinned_report_cells([]), [])
            self.assertEqual(lr.pinned_report_cells(["temp_por_top"]), [])

    def cli(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = lr.main(["--pinned-report-cells", *argv])
        return code, out.getvalue().split()

    def test_the_cli_prints_one_cell_per_line_for_a_whole_repo_run(self):
        code, names = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual(names, sorted(lr.FROZEN_CELLS))

    def test_the_cli_prints_nothing_when_the_caller_named_cells(self):
        # run_checks.sh passes its own "$@" straight through, so this is the
        # single-cell invocation's answer.
        self.assertEqual(self.cli("temp_por_top"), (0, []))

    def test_a_bare_cell_name_is_still_rejected_by_every_other_mode(self):
        # The positional carries run_checks.sh's "$@" and nothing else; every
        # other mode takes --cell, and a bare name there used to be an
        # "unrecognized arguments" error rather than a silently ignored one.
        with contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit) as raised:
                lr.main(["--check", "temp_core"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--cell", err.getvalue())


#: A stand-in for ``klt`` used by :class:`RunChecksFrozenReportsTest`. It is
#: deliberately not a DRC/LVS engine: what is under test is which *files*
#: ``run_checks.sh`` writes, so the stub only has to honour the exit-code and
#: report-shape contract the script reads (``drc``/``extract`` clean on 0,
#: ``lvs`` reporting a mismatch with exit 3 when handed a corrupted reference
#: netlist, which is what makes the negative controls pass).
KLT_STUB = '''#!/usr/bin/env python3
import hashlib
import json
import os
import sys
from pathlib import Path

DECK = {"content_hash": "stub-deck-0000000000000000"}
argv = sys.argv[1:]


def emit(payload, code):
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\\n")
    raise SystemExit(code)


def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None


if argv[:1] == ["--version"]:
    print("klt 0.0+stub")
    raise SystemExit(0)
if argv[:1] == ["pdk"]:
    raise SystemExit(0)

command = argv[0]
if command == "drc":
    failing = os.environ.get("KLT_STUB_DRC_FAIL")
    if failing and Path(argv[1]).stem == failing:
        emit({"status": "violations", "violation_count": 1,
              "violations": [{"rule": "stub.injected.1"}],
              "provenance": {"deck": DECK}}, 3)
    emit({"status": "clean", "violation_count": 0, "violations": [],
          "provenance": {"deck": DECK}}, 0)
if command == "extract":
    Path(opt("-o")).write_text(".subckt %s\\n.ends\\n" % opt("--top"))
    emit({"status": "ok", "device_count": 0, "provenance": {"deck": DECK}}, 0)
if command == "lvs":
    request_path = Path(argv[1])
    request = json.loads(request_path.read_text())
    layout = Path(request["layout"]["file"])
    if not layout.is_absolute():
        layout = request_path.parent / layout
    reference = Path(request["reference"]["netlist"]).name
    corrupt = any(".%s." % c in reference
                  for c in ("topology", "device-param", "passive-param"))
    emit({"status": "mismatch" if corrupt else "match",
          "category_counts": {"net": 1} if corrupt else {},
          "environment": {
              "layout_sha256": hashlib.sha256(layout.read_bytes()).hexdigest()
          }}, 3 if corrupt else 0)
sys.exit("stub klt: unsupported command %r" % (argv,))
'''

#: Stands in for the interpreter ``klt`` ships beside itself. ``run_checks.sh``
#: looks for a python with the ``klayout`` module (plain ``python3``, then this
#: path, then ``uv run --with klayout``); answering the probe here keeps the
#: sandbox off the ``uv`` branch, which would go to the network in CI. The only
#: thing it is ever asked to run is the ``build_cells.py`` stub beside it.
PYTHON_SHIM = '''#!/usr/bin/env python3
import os
import sys

if sys.argv[1:] == ["-c", "import klayout.db"]:
    raise SystemExit(0)
os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
'''

#: Stands in for ``layout/build_cells.py``. The real one rebuilds every
#: committed GDS and so needs the ``klayout`` module, which these tests
#: deliberately do without: the subject here is ``run_checks.sh``'s
#: report-writing loop, and the GDS staleness gate has its own coverage in
#: :class:`FrozenCellTest`.
BUILD_CELLS_STUB = '''#!/usr/bin/env python3
raise SystemExit(0)
'''


class RunChecksFrozenReportsTest(unittest.TestCase):
    """``layout/run_checks.sh``'s frozen-cell report guard (#111), end to end.

    A whole-repo run used to re-run a frozen cell's checks and overwrite its
    committed ``layout/reports/<cell>/`` with the result -- evidence recorded
    against an older deck, silently re-stamped onto today's, so the next
    ``git add -A`` ended the freeze without anyone deciding to. The fix writes
    a pinned cell's reports to a scratch directory and diffs them instead, so
    the checks still run and still fail loudly; only the destination of the
    bytes changes.

    These run the real script against a sandbox copy of the tree with a stub
    ``klt`` (above) on ``PATH``, so they need no klt, no PDK and no klayout --
    and, importantly, cannot touch this repo's own committed reports.
    """

    #: The frozen cell under test, plus the smallest unfrozen cell as the
    #: contrast: the same run must still rewrite *its* reports normally.
    FROZEN = "temp_por_top"
    UNFROZEN = "por_comparator_bias_okb_inv"

    @classmethod
    def setUpClass(cls):
        if cls.FROZEN not in lr.FROZEN_CELLS:
            raise unittest.SkipTest(
                f"{cls.FROZEN} is no longer frozen -- the guard is a no-op and "
                "these tests have nothing left to hold (see #111)"
            )
        cls._root_ctx = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._root_ctx.cleanup)
        cls.root = build_run_checks_sandbox(
            Path(cls._root_ctx.name), (cls.FROZEN, cls.UNFROZEN)
        )
        cls.before = {
            cell: report_digests(cls.root, cell)
            for cell in (cls.FROZEN, cls.UNFROZEN)
        }
        cls.result = run_checks(cls.root)
        cls.after = {
            cell: report_digests(cls.root, cell)
            for cell in (cls.FROZEN, cls.UNFROZEN)
        }

    def section(self, output, cell):
        """The part of ``output`` between ``==> <cell>`` and the next cell."""
        self.assertIn(f"==> {cell}", output, output)
        rest = output.split(f"==> {cell}", 1)[1]
        return rest.split("==> ", 1)[0]

    def test_a_whole_repo_run_leaves_the_frozen_cells_reports_untouched(self):
        # The acceptance criterion, byte for byte: `git status --porcelain
        # layout/reports/temp_por_top/` has to come back empty.
        self.assertEqual(self.result.returncode, 0, self.result.stdout)
        self.assertEqual(self.after[self.FROZEN], self.before[self.FROZEN])
        self.assertTrue(self.before[self.FROZEN], "no committed reports to hold")

    def test_the_same_run_still_rewrites_an_unfrozen_cells_reports(self):
        # Without this the first assertion would also pass on a script that
        # wrote nothing at all.
        self.assertNotEqual(self.after[self.UNFROZEN], self.before[self.UNFROZEN])
        self.assertEqual(
            sorted(self.after[self.UNFROZEN]), sorted(self.before[self.UNFROZEN])
        )

    def test_the_frozen_cells_verdicts_are_computed_not_skipped(self):
        # A freeze is "do not compare against a fresh rebuild", never "stop
        # running DRC" -- so every verdict has to appear for the frozen cell
        # too, and be labelled as this run's own.
        section = self.section(self.result.stdout, self.FROZEN)
        for verdict in ("DRC   clean", "EXTR  ok", "LVS   match", "CTRL  topology"):
            self.assertIn(verdict, section, section)
        self.assertIn("FROZEN", section, section)

    def test_a_frozen_cells_failure_is_not_swallowed_by_the_guard(self):
        # The risk the guard has to avoid: "don't overwrite" must not shade
        # into "don't notice". A real DRC failure on the frozen cell still
        # fails the run, and still leaves the committed evidence alone.
        with tempfile.TemporaryDirectory() as tmp:
            # One cell is enough here (and much cheaper): this is still the
            # implicit whole-repo invocation, which is what arms the guard.
            root = build_run_checks_sandbox(Path(tmp), (self.FROZEN,))
            before = report_digests(root, self.FROZEN)
            result = run_checks(root, env={"KLT_STUB_DRC_FAIL": self.FROZEN})
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("DRC   FAILED", self.section(result.stdout, self.FROZEN))
            self.assertEqual(report_digests(root, self.FROZEN), before)
            # ... and the failing report it names is kept, not swept away with
            # the scratch dir, so the FAIL line points at something readable.
            kept = re.search(
                r"kept this run's frozen-cell reports[^:]*: ([^\s\x1b]+)",
                result.stdout,
            )
            self.assertIsNotNone(kept, result.stdout)
            scratch = Path(kept.group(1))
            self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
            self.assertTrue((scratch / "reports" / self.FROZEN / "drc.json").exists())

    def test_naming_the_frozen_cell_explicitly_regenerates_its_reports(self):
        # The escape hatch #97's own workflow needs, and the reason the guard
        # keys off "did the caller name cells" rather than off the freeze alone.
        with tempfile.TemporaryDirectory() as tmp:
            root = build_run_checks_sandbox(Path(tmp), (self.FROZEN,))
            before = report_digests(root, self.FROZEN)
            result = run_checks(root, self.FROZEN)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertNotEqual(report_digests(root, self.FROZEN), before)
            self.assertNotIn("FROZEN", result.stdout)


def build_run_checks_sandbox(root: Path, cells: tuple[str, ...]) -> Path:
    """A minimal copy of the tree ``run_checks.sh`` runs against.

    Only ``cells`` get a ``.gds``, so they are the whole of the script's
    whole-repo loop; every cell's ``.reference.spice`` and the golden netlists
    come along because the unscoped staleness gate rebuilds all of them.
    """
    shutil.copytree(REPO_ROOT / "design" / "netlist", root / "design" / "netlist")
    layout = root / "layout"
    (layout / "cells").mkdir(parents=True)
    for name in ("lvs_reference.py", "run_checks.sh"):
        shutil.copy(LAYOUT_DIR / name, layout / name)
    (layout / "build_cells.py").write_text(BUILD_CELLS_STUB)
    for reference in (LAYOUT_DIR / "cells").glob("*.reference.spice"):
        shutil.copy(reference, layout / "cells" / reference.name)
    for cell in cells:
        for suffix in (".gds", ".lvs.json"):
            shutil.copy(
                LAYOUT_DIR / "cells" / f"{cell}{suffix}",
                layout / "cells" / f"{cell}{suffix}",
            )
        shutil.copytree(LAYOUT_DIR / "reports" / cell, layout / "reports" / cell)
    binaries = root / "bin"
    binaries.mkdir()
    for name, text in (("klt", KLT_STUB), ("python", PYTHON_SHIM)):
        (binaries / name).write_text(text)
        (binaries / name).chmod(0o755)
    return root


def report_digests(root: Path, cell: str) -> dict[str, str]:
    """``{report name: sha256}`` for one cell's committed reports."""
    directory = root / "layout" / "reports" / cell
    return {
        path.name: lr.sha256_bytes(path.read_bytes())
        for path in sorted(directory.iterdir())
    }


def run_checks(
    root: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """``bash layout/run_checks.sh <args>`` against a sandbox from
    :func:`build_run_checks_sandbox`, with the stub ``klt`` found first."""
    environment = dict(os.environ, PATH=f"{root / 'bin'}{os.pathsep}{os.environ['PATH']}")
    environment.pop("KLT_STUB_DRC_FAIL", None)
    environment.update(env or {})
    return subprocess.run(
        ["bash", str(root / "layout" / "run_checks.sh"), *args],
        capture_output=True,
        text=True,
        env=environment,
        cwd=root,
    )


class Poly2ContactEnclosureTest(unittest.TestCase):
    """``_poly2_landing_x1`` (#102). A Poly2 routing track that simply *ends* on
    its landing contact's centre covers only the contact's west half -- the
    two ``poly2.enclosing.contact.1`` violations ``por_comparator``'s committed
    stream carried while its committed report claimed clean."""

    def test_the_overhang_clears_the_drm_enclosure(self):
        overhang = bc._poly2_landing_x1(10.0) - 10.0
        self.assertGreaterEqual(
            overhang, bc.CONTACT_SIDE_UM / 2.0 + bc.POLY2_CONT_ENC_UM
        )

    def test_the_overhang_matches_the_track_s_own_margin(self):
        # A track end that overhangs by half a track width gives its contact the
        # same margin east that the track's width already gives it north/south,
        # so the landing looks like the rest of the track rather than a stub.
        overhang = bc._poly2_landing_x1(3.0) - 3.0
        self.assertGreaterEqual(overhang, bc.TRACK_W_UM / 2.0)

    def test_the_enclosure_constant_is_the_drm_rule_the_deck_checks(self):
        # klt's curated gf180mcu deck checks poly2.enclosing.contact.1 at
        # 70 dbu; this module is stdlib-only (no klt import), so the value is
        # transcribed and asserted against the DRM number it came from.
        self.assertAlmostEqual(bc.POLY2_CONT_ENC_UM, 0.07)


if __name__ == "__main__":
    unittest.main()
