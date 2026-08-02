#!/usr/bin/env python3
"""Unit tests for layout/composite_netlist.py. No PDK, no klayout, no klt, no ngspice.

    python3 -m unittest discover -s layout/tests -v

The composite netlist's whole risk is that it *looks* right: a splice attached
to the wrong node still elaborates, still converges, and still prints numbers.
So these tests are mostly about the checks that are supposed to refuse, and
about the properties of the committed artifacts that a reader would otherwise
have to take on trust:

* the committed outputs are current (the same ``--check`` staleness gate
  ``lvs_reference.py`` uses),
* the solved net correspondence is a verified bijection, and the verifier
  actually rejects a corrupted one (two negative controls),
* nothing the splice introduces collides by name with an extracted net,
* every emitted card is in a form ngspice can parse -- the extractor's own net
  names carry ``$`` and ``|``, which silently mis-parse into a different
  element,
* ``layout/README.md``'s "Consequences to carry forward" bullets still hold
  against the actual current build.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = LAYOUT_DIR.parent
sys.path.insert(0, str(LAYOUT_DIR))

import composite_netlist as cn  # noqa: E402
import lvs_reference as lr  # noqa: E402

CELLS = list(cn.CELLS)


def audit(cell: str) -> dict:
    return json.loads((cn.COMPOSITE_DIR / f"{cell}.audit.json").read_text())


def composite_text(cell: str) -> str:
    return (cn.COMPOSITE_DIR / f"{cell}.composite.spice").read_text()


class CommittedArtifactsTest(unittest.TestCase):
    def test_every_cell_has_its_extraction_and_its_composite(self):
        for cell in CELLS:
            with self.subTest(cell=cell):
                self.assertTrue(
                    (cn.REPORTS_DIR / cell / "extracted-parasitics.spice").is_file()
                )
                self.assertTrue(
                    (cn.REPORTS_DIR / cell / "extracted-parasitics.json").is_file()
                )
                self.assertTrue(
                    (cn.COMPOSITE_DIR / f"{cell}.composite.spice").is_file()
                )
                self.assertTrue((cn.COMPOSITE_DIR / f"{cell}.audit.json").is_file())

    def test_the_committed_outputs_are_current(self):
        # Same contract as lvs_reference.py --check: a committed artifact that
        # no longer matches what the generator produces is a stale evidence
        # trail, which is worse than no evidence trail.
        outputs, audits = cn.generate(CELLS)
        outputs[cn.COMPOSITE_DIR / "AUDIT.md"] = cn.render_audit(audits)
        for path, text in outputs.items():
            with self.subTest(path=path.name):
                self.assertEqual(path.read_text(), text, f"{path} is stale")

    def test_the_untouched_extraction_is_still_byte_identical(self):
        # run_checks.sh keeps extracted.spice byte-stable as the DRC/LVS
        # flow's repeatability contract; --parasitics writes a SEPARATE
        # artifact, and its device cards must be the same cards.
        for cell in CELLS:
            with self.subTest(cell=cell):
                plain = cn.parse_extracted(cn.REPORTS_DIR / cell / "extracted.spice")
                withpar = cn.parse_extracted(
                    cn.REPORTS_DIR / cell / "extracted-parasitics.spice"
                )
                self.assertEqual(plain.ports, withpar.ports)
                self.assertEqual(
                    [d.key() for d in plain.devices],
                    [d.key() for d in withpar.devices],
                )
                self.assertEqual(plain.parasitics, [])
                self.assertNotEqual(withpar.parasitics, [])


class CorrespondenceTest(unittest.TestCase):
    def solve(self, cell: str):
        extracted = cn.parse_extracted(
            cn.REPORTS_DIR / cell / "extracted-parasitics.spice"
        )
        reference = cn.parse_reference(cn.CELLS_DIR / f"{cell}.reference.spice")
        pins = cn.pin_correspondence(extracted, reference)
        mapping = cn.solve_correspondence(extracted, reference, pins)
        return extracted, reference, mapping

    def test_every_cell_solves_to_a_verified_bijection(self):
        # A drawn MiM cap's isolated plate nets (Netlist.cap_nets) are real
        # extracted nets but touch no MOS device, so they are outside the
        # net-correspondence graph entirely (Netlist.terminals) and the
        # mapping's domain is `extracted.nets - cap_nets`, not the full set.
        for cell in CELLS:
            with self.subTest(cell=cell):
                extracted, reference, mapping = self.solve(cell)
                cn.verify_correspondence(extracted, reference, mapping)
                self.assertEqual(
                    len(mapping), len(extracted.nets) - len(extracted.cap_nets)
                )
                self.assertEqual(len(set(mapping.values())), len(mapping))

    def test_negative_control_swapped_nets_are_rejected(self):
        # The verifier's whole job. Swap the two nets of one solved pair and
        # it must refuse -- otherwise "verified" means nothing and a
        # mis-splice ships.
        cell = "por_comparator"
        extracted, reference, mapping = self.solve(cell)
        anonymous = sorted(net for net in mapping if net.startswith("$"))
        first, second = anonymous[0], anonymous[1]
        corrupted = dict(mapping)
        corrupted[first], corrupted[second] = mapping[second], mapping[first]
        with self.assertRaises(cn.CompositeError):
            cn.verify_correspondence(extracted, reference, corrupted)

    def test_negative_control_a_corrupted_reference_does_not_solve(self):
        # lvs_reference.py's own topology corruption re-ties one device's
        # source. The solver must not find a "correspondence" to it.
        cell = "por_comparator"
        import tempfile

        extracted = cn.parse_extracted(
            cn.REPORTS_DIR / cell / "extracted-parasitics.spice"
        )
        with tempfile.TemporaryDirectory() as work:
            bad = Path(work) / "bad.spice"
            bad.write_text(lr.build(cell, corrupt="topology"))
            reference = cn.parse_reference(bad)
            pins = cn.pin_correspondence(extracted, reference)
            with self.assertRaises(cn.CompositeError):
                mapping = cn.solve_correspondence(extracted, reference, pins)
                cn.verify_correspondence(extracted, reference, mapping)

    def test_labelled_nets_land_on_their_own_name(self):
        # An independent cross-check on the topological solve: the solver is
        # seeded with pin names only, so a below-top label matching its
        # reference name is information it never used.
        for cell in CELLS:
            with self.subTest(cell=cell):
                _extracted, _reference, mapping = self.solve(cell)
                for net_e, net_r in mapping.items():
                    if net_e.startswith("$"):
                        continue
                    tail = net_r.rsplit(".", 1)[-1]
                    self.assertIn(tail, net_e.split("|"), f"{net_e} -> {net_r}")


class SpliceTest(unittest.TestCase):
    def test_no_spliced_node_collides_with_an_extracted_net(self):
        # The issue's own acceptance criterion, checked BY NAME rather than by
        # "it compiled": a node the splice introduces must be new, so it
        # cannot accidentally short onto an extracted net.
        for cell in CELLS:
            with self.subTest(cell=cell):
                report = audit(cell)
                layout_names = {
                    row["net"] for row in report["nets"] if row["origin"] == "layout"
                }
                for name in report["schematic_only_nets"]:
                    self.assertNotIn(name, layout_names)
                    row = next(r for r in report["nets"] if r["net"] == name)
                    self.assertEqual(row["mos_terminals"], 0)
                    self.assertGreater(row["spliced_terminals"], 0)

    def test_every_spliced_device_node_exists_in_the_netlist(self):
        for cell in CELLS:
            with self.subTest(cell=cell):
                report = audit(cell)
                names = {row["net"] for row in report["nets"]}
                for device in report["spliced_devices"]:
                    for node in device["nodes"]:
                        self.assertIn(node, names, f"{device['name']} -> {node}")

    def test_the_spliced_devices_are_exactly_the_golden_non_mos_ones(self):
        # A sub-cell whose MiM caps are drawn for real (`caps` in its
        # lvs_reference.CELLS manifest) already carries them in the extracted
        # half, so they are excluded from `_non_mos_cards` rather than
        # spliced -- otherwise the composite netlist would carry the same
        # capacitor twice.
        for cell in CELLS:
            with self.subTest(cell=cell):
                spec = lr.CELLS[cell]
                if "assembly" in spec:
                    expected = sum(
                        len(
                            cn._non_mos_cards(
                                spec["source"],
                                lr.CELLS[sub]["subckt"],
                                frozenset(lr.CELLS[sub].get("caps", [])),
                            )
                        )
                        for _inst, sub, _rename in lr.instance_renames(cell)
                    )
                else:
                    expected = len(
                        cn._non_mos_cards(
                            spec["source"],
                            spec["subckt"],
                            frozenset(spec.get("caps", [])),
                        )
                    )
                self.assertEqual(
                    audit(cell)["counts"]["spliced_devices_from_schematic"], expected
                )
                if cell == "por_output_chain":
                    # Its only two non-MOS golden devices are the MiM caps,
                    # and both are drawn for real (klayout-tools#314/#315),
                    # so nothing is left to splice.
                    self.assertEqual(expected, 0)
                else:
                    self.assertGreater(expected, 0)

    def test_the_port_list_is_the_golden_one(self):
        # A composite netlist is meant to be a drop-in for
        # design/netlist/<cell>.spice, so its .subckt line has to match.
        for cell in CELLS:
            with self.subTest(cell=cell):
                spec = lr.CELLS[cell]
                golden = lr.subckt_ports(
                    (cn.NETLIST_DIR / spec["source"]).read_text(), spec["subckt"]
                )
                header = next(
                    line
                    for line in composite_text(cell).splitlines()
                    if line.lower().startswith(".subckt")
                )
                self.assertEqual(header.split()[1:], [cell] + golden)
                self.assertEqual(audit(cell)["ports"], golden)


class EmittedFormTest(unittest.TestCase):
    """The composite netlist has to be readable by ngspice, not just by us."""

    CARD = re.compile(r"^[A-Za-z]")

    def cards(self, cell: str):
        for line, _comment in cn._cards(composite_text(cell)):
            if self.CARD.match(line):
                yield line

    def test_no_card_carries_a_character_ngspice_treats_as_syntax(self):
        # Regression guard. The extractor names devices and parasitics after
        # nets, so they arrive carrying '$' (anonymous net) and '|' (two
        # labels drawn on one net). ngspice does not reject those -- it
        # mis-parses the card into a different-arity element and fails
        # somewhere else entirely.
        for cell in CELLS:
            with self.subTest(cell=cell):
                for card in self.cards(cell):
                    for character in "$|":
                        self.assertNotIn(character, card, card)

    def test_no_flat_node_name_contains_a_hierarchy_separator(self):
        # An assembly's reference nets are 'xbias.NB'; '.' is ngspice's
        # hierarchy separator and cannot appear inside a flat node name.
        for cell in CELLS:
            with self.subTest(cell=cell):
                for row in audit(cell)["nets"]:
                    self.assertNotIn(".", row["net"])

    def test_every_mos_card_is_a_pdk_subcircuit_call(self):
        # klt writes plain-element MOS ('M1 d g s b nfet L=..U'); ngspice
        # needs the gf180mcu subcircuit form. Getting this wrong does not
        # error -- it silently reads an undefined model.
        for cell in CELLS:
            with self.subTest(cell=cell):
                mos = [
                    card
                    for card in self.cards(cell)
                    if card.upper().startswith("XM_")
                ]
                self.assertEqual(
                    len(mos), audit(cell)["counts"]["mos_devices_from_layout"]
                )
                for card in mos:
                    self.assertRegex(card, r"\s(nfet_03v3|pfet_03v3)\s")

    def test_no_mos_body_is_left_on_a_synthetic_deck_net(self):
        # lvs_reference.py rewrites bodies onto the deck's substrate global
        # and onto anonymous well nets, because that is all the deck sees. A
        # simulation netlist that kept them would have floating bodies.
        for cell in CELLS:
            with self.subTest(cell=cell):
                text = composite_text(cell)
                self.assertNotRegex(text, rf"\b{lr.SUBSTRATE_NET}\b")
                self.assertNotRegex(text, r"\bNW\d\b")

    def test_the_header_says_what_the_netlist_is_not(self):
        # CLAUDE.md: no claim without a testbench, and the spec is not
        # relaxed to make a result pass. A netlist with ideal passives that
        # does not SAY it has ideal passives is exactly how an overclaim gets
        # made by accident downstream.
        for cell in CELLS:
            with self.subTest(cell=cell):
                header = composite_text(cell).split(".subckt")[0]
                self.assertIn("NOT a parasitic-extracted analog core", header)
                self.assertIn("IDEAL SCHEMATIC DEVICES", header)
                self.assertIn("Claim field", header)


class ParasiticsTest(unittest.TestCase):
    def test_coverage_is_reported_and_is_not_a_silent_zero(self):
        # klayout-tools#283 was a silent zero on unlabelled nets. These cells
        # are mostly unlabelled nets, so a regression would land squarely on
        # them and would look like a slightly optimistic simulation rather
        # than like a bug.
        for cell in CELLS:
            with self.subTest(cell=cell):
                par = audit(cell)["parasitics"]
                self.assertGreater(par["nets_with_parasitics"], 0)
                self.assertGreater(par["coverage_pct"], 50.0)
                self.assertEqual(par["r_cards"], par["c_cards"])
                self.assertEqual(par["r_cards"], par["nets_with_parasitics"])
                self.assertGreater(par["total_capacitance_ff"], 0.0)

    def test_the_counters_agree_with_the_recorded_klt_json(self):
        for cell in CELLS:
            with self.subTest(cell=cell):
                par = audit(cell)["parasitics"]
                report = json.loads(
                    (cn.REPORTS_DIR / cell / "extracted-parasitics.json").read_text()
                )
                self.assertEqual(
                    par["nets_with_parasitics"], len(report["parasitics"]["nets"])
                )
                self.assertEqual(par["nets_in_extraction"], report["net_count"])

    def test_an_unlabelled_net_really_does_carry_parasitics(self):
        # The specific shape of the #283 regression: labelled nets fine,
        # anonymous ones silently zero. Not every cell has anonymous nets --
        # temp_core labels all 27 of its routing channels -- so this asserts
        # per cell where they exist, and globally that they exist at all.
        seen = 0
        for cell in CELLS:
            anonymous = [
                row
                for row in audit(cell)["nets"]
                if row["origin"] == "layout" and not row["labelled_in_layout"]
            ]
            if not anonymous:
                continue
            seen += len(anonymous)
            with self.subTest(cell=cell):
                self.assertTrue(
                    any(row["parasitic_c_ff"] for row in anonymous),
                    "no unlabelled net carries any capacitance",
                )
        self.assertGreater(seen, 0)


class ReadmeConsequencesTest(unittest.TestCase):
    def test_every_recorded_readme_consequence_still_holds(self):
        for cell in CELLS:
            for claim in audit(cell)["readme_claims"]:
                with self.subTest(cell=cell, claim=claim["claim"]):
                    self.assertTrue(
                        claim["holds"],
                        f"{claim['claim']} -- {'; '.join(claim['findings'])}",
                    )

    def test_the_sense_taps_are_unlabelled_and_therefore_unfindable_by_name(self):
        # The specific stale claim this work was asked to resolve rather than
        # paper over: layout/README.md read as if SNS/SNSB could be grepped
        # out of extracted.spice. They cannot -- no label is drawn on those
        # tracks -- but they DO exist, with one MOS terminal each, under
        # topologically-solved anonymous names.
        report = audit("por_comparator")
        rows = {row["net"]: row for row in report["nets"]}
        for net in ("SNS", "SNSB"):
            self.assertIn(net, rows)
            self.assertEqual(rows[net]["origin"], "layout")
            self.assertFalse(rows[net]["labelled_in_layout"])
            self.assertEqual(rows[net]["mos_terminals"], 1)
            self.assertTrue(rows[net]["extracted_nets"][0].startswith("$"))
        # 'SNSB' contains 'SNS', so one substring search covers both taps.
        for path in (
            cn.REPORTS_DIR / "por_comparator" / "extracted.spice",
            cn.REPORTS_DIR / "por_comparator" / "extracted-parasitics.spice",
            cn.REPORTS_DIR / "temp_por_top" / "extracted.spice",
            cn.REPORTS_DIR / "temp_por_top" / "extracted-parasitics.spice",
        ):
            self.assertNotIn("SNS", path.read_text().upper())


class SmokeReportTest(unittest.TestCase):
    """Reads the committed smoke reports; runs no simulation."""

    def report(self, cell: str) -> dict:
        return json.loads(
            (cn.REPORTS_DIR / cell / "composite-smoke.json").read_text()
        )

    def test_every_cell_has_a_converged_smoke_report(self):
        for cell in CELLS:
            with self.subTest(cell=cell):
                report = self.report(cell)
                self.assertEqual(report["corner_id"], "tt_27c_3.30v")
                self.assertTrue(report["converged"], report["problems"])
                self.assertEqual(report["problems"], [])
                self.assertTrue(report["measurements"])

    def test_the_schematic_control_ran_too(self):
        # A composite netlist spliced onto the wrong node still converges and
        # still prints numbers; the side-by-side against the golden schematic
        # is what makes the numbers mean something.
        for cell in CELLS:
            with self.subTest(cell=cell):
                report = self.report(cell)
                self.assertEqual(
                    sorted(report["schematic_control_measurements"]),
                    sorted(report["measurements"]),
                )
                for check in report["sanity_checks"]:
                    self.assertTrue(check["pass"], check)
                    self.assertTrue(check["control_pass"], check)

    def test_dc_quantities_track_the_schematic(self):
        # The parasitic model is one series R into one lumped C per net, so
        # every DC quantity is parasitic-invariant by construction. A DC
        # number that moved would mean the splice changed the topology.
        for cell in CELLS:
            with self.subTest(cell=cell):
                for check in self.report(cell)["sanity_checks"]:
                    if check["measurement"].startswith("t_"):
                        continue
                    self.assertIsNotNone(check["delta_pct"])
                    self.assertLess(
                        abs(check["delta_pct"]),
                        1.0,
                        f"{cell}.{check['measurement']} moved {check['delta_pct']} %",
                    )

    def test_the_parasitics_move_a_switching_edge(self):
        # ...and the converse: if NOTHING moved anywhere, the parasitics are
        # decorative and the whole exercise proved nothing.
        release = next(
            check
            for check in self.report("temp_por_top")["sanity_checks"]
            if check["measurement"] == "t_release_ms"
        )
        self.assertIsNotNone(release["delta_pct"])
        self.assertGreater(abs(release["delta_pct"]), 0.1)


if __name__ == "__main__":
    unittest.main()
