#!/usr/bin/env python3
"""Unit tests for layout/postlayout.py. No PDK, no klayout, no klt, no ngspice.

    python3 -m unittest discover -s layout/tests -v

``layout/postlayout.py``'s first stage runs ``klt``; its second is a pure
transform of that stage's committed output, and this covers the transform plus
the guards that are supposed to fail loudly rather than quietly emit a netlist
that simulates and lies. Several tests assert against the **committed**
artifacts, so a regenerated extraction that changed shape fails here as well as
at ``--check``.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = LAYOUT_DIR.parent
sys.path.insert(0, str(LAYOUT_DIR))

import lvs_reference as lr  # noqa: E402
import postlayout as pl  # noqa: E402


def committed(cell: str) -> tuple[str, dict]:
    spice, record = pl.artifact_paths(cell)
    return spice.read_text(), json.loads(record.read_text())


class ParsingTest(unittest.TestCase):
    def test_continuations_are_joined(self):
        text = ".SUBCKT c A B\n+ C D\nM$1 A B C D nfet L=1U W=2U\n.ENDS c\n"
        top, pins, cards = pl.parse_extracted(text)
        self.assertEqual(top, "c")
        self.assertEqual(pins, ["A", "B", "C", "D"])
        self.assertEqual(len(cards), 1)

    def test_positional_names_are_unescaped(self):
        self.assertEqual(pl.unescape(r"\$26"), "$26")

    def test_merged_label_separator_is_normalised(self):
        # The netlist spells a merged-label net with '|' and the JSON report
        # with ',', so the two cannot be joined by name as written.
        self.assertEqual(pl.unescape("EN|RESETn"), "EN,RESETn")

    def test_drawn_and_parasitic_resistors_are_told_apart(self):
        text = (
            ".SUBCKT c A B\n"
            "R$19 A B vsubs 3948720 ppolyf_u_1k\n"
            "R_3 A A__par 1263.8\n"
            ".ENDS c\n"
        )
        _top, _pins, cards = pl.parse_extracted(text)
        self.assertEqual([card.klass for card in cards], ["ppolyf_u_1k", None])

    def test_drawn_and_parasitic_capacitors_are_told_apart(self):
        text = (
            ".SUBCKT c A B\n"
            "C$45 A B 7.2e-14 cap_mim_2f0_m4m5_noshield\n"
            "C_3 A__par vsubs 1.4e-14\n"
            ".ENDS c\n"
        )
        _top, _pins, cards = pl.parse_extracted(text)
        self.assertEqual(
            [card.klass for card in cards],
            ["cap_mim_2f0_m4m5_noshield", None],
        )

    def test_an_unknown_card_is_an_error_not_a_skipped_line(self):
        # A silently dropped device is the failure mode this parser exists to
        # avoid: the netlist would still simulate.
        with self.assertRaises(pl.PostlayoutError):
            pl.parse_extracted(".SUBCKT c A\nD$1 A vsubs diode\n.ENDS c\n")

    def test_a_control_line_is_an_error(self):
        with self.assertRaises(pl.PostlayoutError):
            pl.parse_extracted(".SUBCKT c A\n.model nfet nmos\n.ENDS c\n")


class NamingTest(unittest.TestCase):
    def test_instance_path_becomes_a_flat_node(self):
        self.assertEqual(pl.sanitize("xbias.NOKX"), "xbias__NOKX")

    def test_instance_names_lose_the_dollar(self):
        self.assertEqual(pl.instance("$19"), "X19")

    #: How many leading fields of an emitted card are node names.
    TERMINALS = {"X": None, "R": 2, "C": 2}

    def test_no_emitted_netlist_contains_a_dollar_or_a_dot_node(self):
        for cell in pl.CELLS:
            with self.subTest(cell=cell):
                text = (pl.OUT_DIR / f"{cell}.spice").read_text()
                for line in text.splitlines():
                    if not line or line.startswith("*"):
                        continue
                    self.assertNotIn("$", line, f"{cell}: {line}")
                    self.assertNotIn("\\", line, f"{cell}: {line}")
                    if line.startswith("."):
                        continue
                    fields = line.split()
                    count = self.TERMINALS[line[0]]
                    if count is None:
                        # A subcircuit call: everything up to the model name.
                        model = min(
                            index for index, field in enumerate(fields)
                            if index and "=" not in field
                            and (index + 1 == len(fields) or "=" in fields[index + 1])
                        )
                        nodes = fields[1:model]
                    else:
                        nodes = fields[1 : 1 + count]
                    for node in nodes:
                        self.assertNotIn(".", node, f"{cell}: {line}")


class BodyTieTest(unittest.TestCase):
    def test_every_well_ties_to_the_schematic_bulk(self):
        ties = pl.body_ties("por_comparator")
        # Both drawn Nwells carry PMOS whose schematic body node is VDD.
        self.assertEqual(ties["NW1"], "VDD")
        self.assertEqual(ties["NW2"], "VDD")
        self.assertEqual(ties[lr.SUBSTRATE_NET], "VSS")

    def test_bipolar_base_well_ties_to_the_schematic_base(self):
        # The block's PNPs are diode-connected substrate devices: the deck
        # extracts their shared Nwell isolated, the schematic ties it to VSS.
        self.assertEqual(pl.body_ties("bias_core")["NWQ"], "VSS")

    def test_mim_plates_no_longer_need_a_body_tie(self):
        # #264 routes bias_core's and por_output_chain's drawn MiM plates
        # onto the schematic nodes their golden cards name, so
        # lvs_reference.cap_plate_nets returns those nodes directly rather
        # than a synthesized per-instance isolated net -- a plate's own
        # reference net already *is* the schematic net it stands for, so
        # leaf_body_ties has nothing left to tie for any of them.
        ties = pl.body_ties("por_output_chain")
        self.assertFalse(
            [key for key in ties if key.startswith(("XCDG.", "XCTIM."))]
        )
        self.assertNotIn("NDG", ties)
        self.assertNotIn("TIM", ties)

    def test_assembly_ties_are_per_instance(self):
        ties = pl.body_ties("temp_por_top")
        self.assertEqual(ties["xbias.NW1"], "VDD")
        self.assertEqual(ties["xcmp.NW2"], "VDD")

    def test_a_well_tied_to_a_local_node_is_not_forced_to_the_rail(self):
        # temp_core's NW2 holds the cascode pair whose schematic body node is
        # NT, not VDD. The tie is read from the schematic, so it follows.
        self.assertEqual(pl.body_ties("temp_core")["NW2"], "NT")
        self.assertEqual(pl.body_ties("temp_por_top")["xtemp.NW2"], "xtemp.NT")


class SubstitutionTest(unittest.TestCase):
    def test_high_rho_resistors_are_emitted_as_the_schematic_flavour(self):
        models = pl.resistor_models("por_comparator")
        self.assertEqual(models["ppolyf_u_1k"], ("ppolyf_u_3k", 2.0))

    def test_plain_poly_resistors_are_not_substituted(self):
        self.assertEqual(pl.resistor_models("temp_core")["ppolyf_u"][0], "ppolyf_u")

    def test_emitted_resistor_length_reproduces_the_schematic(self):
        # por_comparator serpentines one body per schematic resistor, so each
        # emitted r_length must equal the golden netlist's own r_length --
        # which is only true if the sheet-rho substitution was undone with the
        # right rho.
        text = (pl.OUT_DIR / "por_comparator.spice").read_text()
        emitted = sorted(
            float(match) for match in
            re.findall(r"ppolyf_u_3k r_width=2u r_length=([0-9.]+)u", text)
        )
        _golden, body = pl.golden("por_comparator")
        passives = lr.parse_passives(body)
        wanted = sorted(
            lr.to_um(passives[name]["params"]["r_length"])
            for name in lr.CELLS["por_comparator"]["resistors"]
        )
        self.assertEqual(len(emitted), len(wanted))
        for got, want in zip(emitted, wanted):
            self.assertAlmostEqual(got, want, places=2)

    def test_a_cell_drawing_one_class_at_two_widths_is_rejected(self):
        spec = copy.deepcopy(lr.CELLS["por_comparator"])
        original = lr.CELLS["por_comparator"]
        try:
            lr.CELLS["por_comparator"] = spec
            source = pl.golden("por_comparator")[0]
            # Swap the golden netlist for one whose resistors disagree on
            # width. Done by monkeypatching the reader, so no file is touched.
            widened = source.replace("XRHYS VSS SNSB VSS ppolyf_u_3k r_width=2u",
                                     "XRHYS VSS SNSB VSS ppolyf_u_3k r_width=4u")
            self.assertNotEqual(widened, source)
            real_golden = pl.golden
            pl.golden = lambda cell: (widened, lr.subckt_body(widened, "por_comparator"))
            with self.assertRaises(pl.PostlayoutError):
                pl.resistor_models("por_comparator")
        finally:
            pl.golden = real_golden
            lr.CELLS["por_comparator"] = original


class UndrawnDeviceTest(unittest.TestCase):
    def test_temp_core_reports_its_one_undrawn_cap(self):
        undrawn = pl.undrawn_capacitors("temp_core")
        self.assertEqual([cap["name"] for cap in undrawn], ["XCC"])
        self.assertEqual(undrawn[0]["nodes"], ["PG", "NZ"])

    def test_cells_that_draw_everything_report_nothing(self):
        for cell in ("bias_core", "por_comparator", "por_output_chain"):
            with self.subTest(cell=cell):
                self.assertEqual(pl.undrawn_capacitors(cell), [])

    def test_the_assembly_inherits_it_under_the_instance_rename(self):
        undrawn = pl.undrawn_capacitors("temp_por_top")
        self.assertEqual([cap["instance"] for cap in undrawn], ["xtemp"])
        self.assertEqual(undrawn[0]["nodes"], ["xtemp.PG", "xtemp.NZ"])

    def test_every_ideal_card_is_flagged_in_the_netlist_header(self):
        for cell in pl.CELLS:
            text = (pl.OUT_DIR / f"{cell}.spice").read_text()
            ideal = [line for line in text.splitlines() if line.startswith("XIDEAL")]
            flagged = [line for line in text.splitlines() if "is IDEAL" in line]
            with self.subTest(cell=cell):
                self.assertEqual(bool(ideal), bool(flagged))


class CommittedArtifactTest(unittest.TestCase):
    """The committed netlists say what the committed extraction says."""

    def test_netlist_matches_the_sha256_recorded_beside_it(self):
        for cell in pl.CELLS:
            spice, record = committed(cell)
            with self.subTest(cell=cell):
                self.assertEqual(
                    lr.sha256_bytes(spice.encode()), record["netlist_sha256"]
                )

    def test_the_extraction_record_is_under_the_gds_hash_gate(self):
        # The gate is what stops a post-layout netlist outliving the GDS it
        # describes, so this asserts the artifact is enrolled in it, not just
        # that the digest happens to be right today.
        self.assertIn("extracted-parasitics.json", lr.GDS_HASH_FIELDS)
        self.assertEqual(lr.check_gds_hash(), [])

    def test_every_cell_records_an_lvs_match(self):
        for cell in pl.CELLS:
            _spice, record = committed(cell)
            with self.subTest(cell=cell):
                self.assertEqual(record["lvs"]["status"], "match")
                self.assertEqual(
                    record["lvs"]["nets_matched"], record["lvs"]["nets_layout"]
                )

    def test_parasitic_coverage_is_recorded_and_non_zero(self):
        # The exact shape of the klayout-tools#283 regression: a run that
        # reports success and loads nothing.
        for cell in pl.CELLS:
            _spice, record = committed(cell)
            with self.subTest(cell=cell):
                self.assertGreater(record["coverage"]["nets_with_parasitics"], 0)
                self.assertGreater(record["coverage"]["total_capacitance_ff"], 0)

    def test_an_unlabelled_net_carries_parasitics(self):
        # #283's failure was specifically that *unlabelled* nets came back
        # parasitic-free, which a total-only check cannot see.
        _spice, record = committed("por_comparator")
        text = (pl.artifact_paths("por_comparator")[0]).read_text()
        positional = [
            line for line in text.splitlines()
            if re.match(r"^R\\\$\d+ ", line) or re.match(r"^R_\d+ ", line)
        ]
        self.assertTrue(
            any(line.startswith("R_") for line in positional),
            "no parasitic R on a positional (unlabelled) net",
        )

    def test_device_census_matches_the_extraction(self):
        audit = json.loads((pl.OUT_DIR / "audit.json").read_text())
        by_cell = {entry["cell"]: entry for entry in audit["cells"]}
        for cell in pl.CELLS:
            _spice, record = committed(cell)
            with self.subTest(cell=cell):
                self.assertEqual(
                    by_cell[cell]["device_counts"], record["device_counts"]
                )
                self.assertEqual(
                    by_cell[cell]["device_total"], record["device_count"]
                )

    def test_every_emitted_model_is_a_golden_netlist_model(self):
        known = set()
        for path in (REPO_ROOT / "design" / "netlist").glob("*.spice"):
            known.update(re.findall(r"\b([a-z]+[a-z0-9_]*_[a-z0-9_]+)\b",
                                    path.read_text()))
        for cell in pl.CELLS:
            text = (pl.OUT_DIR / f"{cell}.spice").read_text()
            for line in text.splitlines():
                if not line.startswith("X"):
                    continue
                model = [f for f in line.split() if "=" not in f][-1]
                with self.subTest(cell=cell, model=model):
                    self.assertIn(model, known)

    def test_every_schematic_port_is_a_subckt_port(self):
        for cell in pl.CELLS:
            text = (pl.OUT_DIR / f"{cell}.spice").read_text()
            line = next(row for row in text.splitlines()
                        if row.startswith(".subckt"))
            golden_text, _body = pl.golden(cell)
            ports = lr.subckt_ports(golden_text, lr.CELLS[cell]["subckt"])
            with self.subTest(cell=cell):
                self.assertEqual(line.split()[2:], ports)

    def test_no_node_is_left_on_the_deck_substrate_global(self):
        # vsubs is not a port of any schematic subcircuit; leaving it in the
        # emitted netlist would give every parasitic cap a floating return.
        for cell in pl.CELLS:
            text = (pl.OUT_DIR / f"{cell}.spice").read_text()
            with self.subTest(cell=cell):
                for line in text.splitlines():
                    if line.startswith("*") or line.startswith("."):
                        continue
                    self.assertNotIn("vsubs", line.split())


class GuardTest(unittest.TestCase):
    def test_an_unmapped_net_is_rejected(self):
        cards = [pl.Card("R", "_1", ("$3", "$3__par"), "10", None)]
        with self.assertRaises(pl.PostlayoutError):
            pl.emit_cards("por_comparator", cards, {})

    def test_a_parasitic_node_without_a_parent_is_rejected(self):
        cards = [pl.Card("R", "_1", ("$3", "$9__par"), "10", None)]
        with self.assertRaises(pl.PostlayoutError):
            pl.parasitic_nodes(cards, {"$3": "SNS"})

    def test_a_wrong_emitter_area_is_rejected(self):
        cards = [
            pl.Card("Q", "$1", ("vsubs", "$1", "$2"), None, "bjt",
                    (("AE", "25P"),))
        ]
        names = {"vsubs": "VSS", "$1": "VSS", "$2": "NA"}
        with self.assertRaises(pl.PostlayoutError):
            pl.emit_cards("bias_core", cards, names)

    def test_colliding_instance_names_are_rejected(self):
        # Two cards whose names differ only by the '$' this module strips.
        cards = [
            pl.Card("M", "$1", ("$3",) * 4, None, "nfet",
                    (("L", "1U"), ("W", "1U"), ("AS", "1P"), ("AD", "1P"),
                     ("PS", "1U"), ("PD", "1U"))),
            pl.Card("M", "1", ("$3",) * 4, None, "nfet",
                    (("L", "1U"), ("W", "1U"), ("AS", "1P"), ("AD", "1P"),
                     ("PS", "1U"), ("PD", "1U"))),
        ]
        with self.assertRaises(pl.PostlayoutError):
            pl.emit_cards("por_comparator", cards, {"$3": "SNS"})

    def test_a_swapped_correspondence_moves_the_netlist(self):
        # Negative control for the whole rename step: the correspondence is
        # trusted, so this asserts it is *used* -- a generator that ignored it
        # would emit the same bytes for a corrupted map.
        _spice, record = committed("por_comparator")
        corrupt = dict(record["net_correspondence"])
        keys = [net for net, ref_net in corrupt.items() if ref_net in ("SNS", "TN")]
        self.assertEqual(len(keys), 2)
        corrupt[keys[0]], corrupt[keys[1]] = corrupt[keys[1]], corrupt[keys[0]]
        clean = pl.net_map("por_comparator", record["net_correspondence"])
        self.assertNotEqual(clean, pl.net_map("por_comparator", corrupt))

    def test_an_unpaired_net_is_rejected(self):
        _spice, record = committed("por_comparator")
        corrupt = dict(record["net_correspondence"])
        corrupt[next(iter(corrupt))] = None
        with self.assertRaises(pl.PostlayoutError):
            pl.net_map("por_comparator", corrupt)


class RegenerationTest(unittest.TestCase):
    def test_committed_artifacts_reproduce_exactly(self):
        for path, text in pl.generate(list(pl.CELLS)).items():
            with self.subTest(path=path.name):
                self.assertTrue(path.exists(), f"{path} is missing")
                self.assertEqual(path.read_text(), text,
                                 f"{path.name} is stale -- run "
                                 "python3 layout/postlayout.py")


if __name__ == "__main__":
    unittest.main()
