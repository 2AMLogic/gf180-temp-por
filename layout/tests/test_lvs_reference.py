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
        for _prefix, _klass, _nodes, value_f in lr.build_cap_cards(self.CELL):
            self.assertIn(value_f, {
                lr.to_um(cap["params"]["c_width"])
                * lr.to_um(cap["params"]["c_length"])
                * lr.MIM_AREA_CAP_F_UM2
                for cap in caps.values()
            })
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
            net
            for _prefix, _klass, nodes, _value in lr.build_cap_cards(self.CELL)
            for net in nodes
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
        self.assertEqual(lr.build(self.CELL), committed)

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


if __name__ == "__main__":
    unittest.main()
