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
        top, pins, cards = pl.parse_extracted(text, {"$1": "nfet"})
        self.assertEqual(top, "c")
        self.assertEqual(pins, ["A", "B", "C", "D"])
        self.assertEqual(len(cards), 1)

    def test_positional_names_are_unescaped(self):
        self.assertEqual(pl.unescape(r"\$26"), "$26")

    def test_merged_label_separator_is_normalised(self):
        # The netlist spells a merged-label net with '|' and the JSON report
        # with ',', so the two cannot be joined by name as written.
        self.assertEqual(pl.unescape("EN|RESETn"), "EN,RESETn")

    def test_a_global_line_is_tolerated(self):
        # The parasitic model's own ground-reference declaration. It carries no
        # device and no topology, so it is skipped -- but the parser is strict
        # about control lines in general, so this has to be an explicit case
        # rather than a side effect.
        text = ".SUBCKT c A B\n.GLOBAL vsubs\nC_3 A vsubs 1.4e-14\n.ENDS c\n"
        top, _pins, cards = pl.parse_extracted(text, {})
        self.assertEqual(top, "c")
        self.assertEqual([card.name for card in cards], ["_3"])

    def test_drawn_and_parasitic_resistors_are_told_apart(self):
        # The drawn card carries the extractor's own measured L/W
        # (klayout-tools#1927); the parasitic one is a single star arm.
        text = (
            ".SUBCKT c A B\n"
            "R$19 A B vsubs 3948720 ppolyf_u_1k L=256.5U W=2U\n"
            "R_3_t0 A__t0 A 1263.8\n"
            ".ENDS c\n"
        )
        _top, _pins, cards = pl.parse_extracted(text, {"$19": "ppolyf_u_1k"})
        self.assertEqual([card.klass for card in cards], ["ppolyf_u_1k", None])
        self.assertEqual(cards[0].nodes, ("A", "B", "vsubs"))
        self.assertEqual(cards[0].params, (("L", "256.5U"), ("W", "2U")))
        self.assertEqual(cards[1].nodes, ("A__t0", "A"))

    def test_a_drawn_resistor_without_l_and_w_is_still_read(self):
        # The pre-#1927 shape. Accepted, with no params to cross-check.
        text = ".SUBCKT c A B\nR$19 A B vsubs 3948720 ppolyf_u_1k\n.ENDS c\n"
        _top, _pins, cards = pl.parse_extracted(text, {"$19": "ppolyf_u_1k"})
        self.assertEqual(cards[0].klass, "ppolyf_u_1k")
        self.assertEqual(cards[0].params, ())

    def test_a_bare_capacitor_card_is_told_from_a_parasitic_by_the_census(self):
        # klt writes a recognised capacitor with no class token at all
        # (klayout-tools#1558/#2386), which is the identical shape to a
        # parasitic coupling capacitor. Only the extractor's own device census
        # separates them, so the same two bytes-identical cards must come back
        # as a device and as a parasitic depending on it.
        text = (
            ".SUBCKT c A B\n"
            "C$45 A B 7.73592e-14\n"
            "C_3 A vsubs 1.4e-14\n"
            ".ENDS c\n"
        )
        _top, _pins, cards = pl.parse_extracted(
            text, {"$45": "cap_mim_2f0_m4m5_noshield"}
        )
        self.assertEqual(
            [card.klass for card in cards],
            ["cap_mim_2f0_m4m5_noshield", None],
        )
        _top, _pins, bare = pl.parse_extracted(text, {})
        self.assertEqual([card.klass for card in bare], [None, None])

    def test_a_capacitor_that_does_name_its_class_is_still_read(self):
        # The pre-#1558 shape, which the pinned klt no longer writes.
        text = (
            ".SUBCKT c A B\n"
            "C$45 A B 7.2e-14 cap_mim_2f0_m4m5_noshield\n"
            ".ENDS c\n"
        )
        _top, _pins, cards = pl.parse_extracted(
            text, {"$45": "cap_mim_2f0_m4m5_noshield"}
        )
        self.assertEqual(cards[0].klass, "cap_mim_2f0_m4m5_noshield")

    def test_a_census_the_netlist_contradicts_is_an_error(self):
        # Two directions, both of which mean the committed .spice and .json
        # describe different runs.
        wrong_class = (
            ".SUBCKT c A B\nM$1 A B A A nfet L=1U W=2U\n.ENDS c\n"
        )
        with self.assertRaises(pl.PostlayoutError):
            pl.parse_extracted(wrong_class, {"$1": "pfet"})
        with self.assertRaises(pl.PostlayoutError):
            pl.parse_extracted(wrong_class, {})

    def test_an_unknown_card_is_an_error_not_a_skipped_line(self):
        # A silently dropped device is the failure mode this parser exists to
        # avoid: the netlist would still simulate.
        with self.assertRaises(pl.PostlayoutError):
            pl.parse_extracted(".SUBCKT c A\nD$1 A vsubs diode\n.ENDS c\n", {})

    def test_a_control_line_is_an_error(self):
        with self.assertRaises(pl.PostlayoutError):
            pl.parse_extracted(".SUBCKT c A\n.model nfet nmos\n.ENDS c\n", {})


class NamingTest(unittest.TestCase):
    def test_instance_path_becomes_a_flat_node(self):
        self.assertEqual(pl.sanitize("xbias.NOKX"), "xbias__NOKX")

    def test_instance_names_lose_the_dollar(self):
        self.assertEqual(pl.instance("$19"), "X19")

    def test_the_compare_is_joined_on_its_readers_own_spelling(self):
        # klt lvs reports the reference net through its SPICE reader, which
        # upcases and (as of the pinned klt) turns an assembly's hierarchy
        # separator into '_'. The join has to follow that; the emitted name
        # must not.
        self.assertEqual(pl.correspondence_key("xbias.NW1"), "XBIAS_NW1")
        self.assertEqual(pl.correspondence_key("RESETn"), "RESETN")

    def test_an_assembly_well_is_tied_through_the_renamed_compare(self):
        # The regression that left every PMOS well floating while the netlist
        # still elaborated: joining on the raw reference name missed every tie
        # keyed on an assembly's dotted well net. Driven from the committed
        # correspondence, so it is the real spelling being joined.
        _spice, record = committed("temp_por_top")
        names = pl.net_map("temp_por_top", record["net_correspondence"])
        wells = {
            layout: reference
            for layout, reference in record["net_correspondence"].items()
            if reference.upper().endswith(("_NW1", "_NW2"))
        }
        self.assertEqual(len(wells), 6)
        for layout, reference in wells.items():
            with self.subTest(reference=reference):
                self.assertIn(names[layout], ("VDD", "xtemp__NT"))

    def test_a_reference_net_the_schematic_does_not_have_is_rejected(self):
        _spice, record = committed("por_comparator")
        corrupt = dict(record["net_correspondence"])
        corrupt[next(iter(corrupt))] = "NOT_A_NET_OF_THIS_SCHEMATIC"
        with self.assertRaises(pl.PostlayoutError):
            pl.net_map("por_comparator", corrupt)

    def test_no_emitted_node_is_an_untied_body_net(self):
        # The other end of the same claim, on the committed artifacts: a body
        # tie that silently missed leaves its own well net on a device bulk.
        audit = json.loads((pl.OUT_DIR / "audit.json").read_text())
        for entry in audit["cells"]:
            cell = entry["cell"]
            text = (pl.OUT_DIR / f"{cell}.spice").read_text()
            nodes = {
                field
                for line in text.splitlines()
                if line and not line.startswith(("*", "."))
                for field in line.split()[1:]
                if "=" not in field
            }
            for net, tied in entry["ties"].items():
                with self.subTest(cell=cell, net=net):
                    self.assertNotIn(net, nodes)
                    self.assertIn(tied, nodes)

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
    def test_temp_core_has_no_undrawn_cap_left(self):
        # #259 (DR-028) drew XCC, which was the last golden device in this
        # block the layout did not draw. It is in temp_core's manifest now, so
        # the manifest-derived splice list is empty -- and nothing in this
        # cell's post-layout netlist is ideal.
        self.assertEqual(pl.undrawn_capacitors("temp_core"), [])
        self.assertIn("XCC", lr.CELLS["temp_core"]["caps"])

    def test_no_cell_reports_an_undrawn_cap(self):
        for cell in pl.CELLS:
            with self.subTest(cell=cell):
                self.assertEqual(pl.undrawn_capacitors(cell), [])

    def test_the_assembly_inherits_nothing_ideal_from_its_instances(self):
        # The assembly's list is composed from its four sub-cells under the
        # instance rename, so this is the same claim one level up: with every
        # sub-cell drawing every golden device, temp_por_top splices nothing.
        self.assertEqual(pl.undrawn_capacitors("temp_por_top"), [])
        lines, records = pl.ideal_cards("temp_por_top")
        self.assertEqual((lines, records), ([], []))

    def test_a_cap_dropped_from_the_manifest_comes_back_as_ideal(self):
        # The empty lists above must mean "everything is drawn", not "this
        # never reports anything": drop XCC from the manifest and it reappears,
        # on its own golden nodes, under the instance rename too.
        spec = lr.CELLS["temp_core"]
        self.addCleanup(lr.CELLS.__setitem__, "temp_core", spec)
        lr.CELLS["temp_core"] = {**spec, "caps": []}
        undrawn = pl.undrawn_capacitors("temp_core")
        self.assertEqual([cap["name"] for cap in undrawn], ["XCC"])
        self.assertEqual(undrawn[0]["nodes"], ["PG", "NZ"])
        assembled = pl.undrawn_capacitors("temp_por_top")
        self.assertEqual([cap["instance"] for cap in assembled], ["xtemp"])
        self.assertEqual(assembled[0]["nodes"], ["xtemp.PG", "xtemp.NZ"])

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
        # parasitic-free, which a total-only check cannot see. A positional
        # net's star arms are named after the net ($10 -> R_10_t<k>).
        text = (pl.artifact_paths("por_comparator")[0]).read_text()
        self.assertTrue(
            any(re.match(r"^R_\d+_t\d+ ", line) for line in text.splitlines()),
            "no parasitic R on a positional (unlabelled) net",
        )

    def test_every_extraction_records_its_device_census(self):
        # A bare capacitor card cannot be read without it, so a record that
        # predates it is not usable -- and build_netlist says so rather than
        # treating a drawn MiM cap as a parasitic.
        for cell in pl.CELLS:
            _spice, record = committed(cell)
            with self.subTest(cell=cell):
                self.assertGreaterEqual(record["schema_version"], 2)
                self.assertEqual(
                    sorted(record["devices"].values()),
                    sorted(
                        klass
                        for klass, count in record["device_counts"].items()
                        for _ in range(count)
                    ),
                )

    def test_no_committed_extraction_is_distributed_rc(self):
        # --extract passes neither --distributed-rc nor --critical-net, so
        # every net's resistance is one lumped value spread as a star. Recorded
        # per cell (klayout-tools#976/#977) so "which parasitic model is this
        # evidence under" is a fact in the artifact, not an assumption about
        # the flags the generator happened to pass.
        for cell in pl.CELLS:
            _spice, record = committed(cell)
            with self.subTest(cell=cell):
                self.assertFalse(record["coverage"]["distributed_rc"])
                self.assertEqual(record["coverage"]["critical_nets"], [])

    def test_the_committed_extractions_exercise_the_new_card_shapes(self):
        # The two shapes the pinned klt introduced, asserted against the real
        # committed evidence rather than only against a synthetic fixture: a
        # `.GLOBAL` control line, and a drawn resistor card carrying the
        # extractor's own measured L/W.
        with_global = []
        with_measured_lw = []
        for cell in pl.CELLS:
            spice, _record = committed(cell)
            lines = spice.splitlines()
            if any(line.upper().startswith(".GLOBAL ") for line in lines):
                with_global.append(cell)
            if any(
                re.match(r"^R\$\S+ (\S+ ){3}\S+ \S+ L=\S+ W=\S+$", line)
                for line in lines
            ):
                with_measured_lw.append(cell)
        self.assertEqual(with_global, list(pl.CELLS))
        self.assertTrue(with_measured_lw, "no committed drawn resistor card "
                                          "carries the extractor's L/W")

    def test_a_committed_drawn_capacitor_card_names_no_class(self):
        # The shape that makes the device census load-bearing: the class token
        # is absent from the card and present only in the JSON report.
        cells = []
        for cell in pl.CELLS:
            spice, record = committed(cell)
            caps = [
                name for name, klass in record["devices"].items()
                if klass.startswith("cap")
            ]
            if not caps:
                continue
            cells.append(cell)
            for name in caps:
                card = next(
                    line for line in spice.splitlines()
                    if line.split()[:1] == [f"C{name}"]
                )
                with self.subTest(cell=cell, card=card):
                    self.assertEqual(len(card.split()), 4, card)
                    self.assertNotIn(record["devices"][name], card)
        self.assertTrue(cells, "no committed cell draws a capacitor")

    def test_every_committed_mim_plate_reconstructs_to_the_drawn_size(self):
        # The capacitance law and the evidence have to be the same deck's: the
        # plate side solved back out of the recorded capacitance must be the
        # size the extractor itself measured (area_um2 = side^2).
        for cell in pl.CELLS:
            spice, record = committed(cell)
            for name, klass in record["devices"].items():
                if not klass.startswith("cap"):
                    continue
                card = next(
                    line for line in spice.splitlines()
                    if line.split()[:1] == [f"C{name}"]
                )
                side_um = lr.mim_side_um(float(card.split()[3]))
                emitted = next(
                    line for line in
                    (pl.OUT_DIR / f"{cell}.spice").read_text().splitlines()
                    if line.startswith(f"X{name.lstrip('$')} ")
                )
                with self.subTest(cell=cell, device=name):
                    # Every MiM in this block is drawn at a whole number of
                    # um, so the law has to land on one -- not merely on a
                    # self-consistent value. Solving klt 0.6.0's capacitance
                    # under the v0.2.0 area-only law lands on 6.2193 um for a
                    # 6 um plate, which this is sized to catch.
                    self.assertAlmostEqual(side_um, round(side_um), places=6)
                    self.assertIn(
                        f"c_width={lr.format_um(side_um).lower()}", emitted
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
        cards = [pl.Card("R", "_1_t0", ("$9__t0", "$3"), "10", None)]
        with self.assertRaises(pl.PostlayoutError):
            pl.parasitic_nodes(cards, {"$3": "SNS"})

    def test_a_star_terminal_keeps_the_extractors_own_index(self):
        cards = [
            pl.Card("R", "_3_t0", ("$3__t0", "$3"), "10", None),
            pl.Card("R", "_3_t7", ("$3__t7", "$3"), "20", None),
        ]
        self.assertEqual(
            pl.parasitic_nodes(cards, {"$3": "SNS"}),
            {"$3__t0": "SNS__t0", "$3__t7": "SNS__t7"},
        )

    def test_two_terminals_renamed_onto_one_node_are_rejected(self):
        # The hazard the body ties create: two isolated nets may legitimately
        # tie to the same circuit net, and if either carried parasitics their
        # star nodes would silently merge two lumped networks into one.
        cards = [
            pl.Card("R", "_3_t0", ("$3__t0", "$3"), "10", None),
            pl.Card("R", "_9_t0", ("$9__t0", "$9"), "20", None),
        ]
        with self.assertRaises(pl.PostlayoutError):
            pl.parasitic_nodes(cards, {"$3": "VDD", "$9": "VDD"})

    def test_the_substrate_dc_tie_keeps_its_ground_return(self):
        # `Rvsubs_dctie vsubs 0 1e+12` is the only extracted card with a node
        # that is not an extracted net. It must survive with SPICE's own ground
        # on the far side, not be dropped and not raise.
        cards = [pl.Card("R", "vsubs_dctie", ("vsubs", pl.SPICE_GROUND),
                         "1e+12", None)]
        lines, census = pl.emit_cards("por_comparator", cards, {"vsubs": "VSS"})
        self.assertEqual(census, {})
        self.assertIn(f"Rvsubs_dctie VSS {pl.SPICE_GROUND} 1e+12", lines)

    def test_a_resistor_drawn_at_the_wrong_width_is_rejected(self):
        # The card's own measured W against the schematic's. A layout drawn at
        # a width the schematic does not declare would otherwise be emitted at
        # the schematic's width and a length reconstructed for it.
        nodes = ("$3", "$4", "vsubs")
        names = {"$3": "SNS", "$4": "SNSB", "vsubs": "VSS"}
        # 6000 ohm at the deck's 1000 ohm/sq, 2 um wide, is 12 um long.
        good = pl.Card("R", "$19", nodes, "6000", "ppolyf_u_1k",
                       (("L", "12U"), ("W", "2U")))
        pl.emit_cards("por_comparator", [good], names)
        bad = good._replace(params=(("L", "12U"), ("W", "4U")))
        with self.assertRaises(pl.PostlayoutError):
            pl.emit_cards("por_comparator", [bad], names)

    def test_a_resistance_the_drawn_length_contradicts_is_rejected(self):
        # The other half of the same cross-check: the deck's sheet rho has to
        # carry the card's own resistance back to the card's own drawn length.
        nodes = ("$3", "$4", "vsubs")
        names = {"$3": "SNS", "$4": "SNSB", "vsubs": "VSS"}
        card = pl.Card("R", "$19", nodes, "6000", "ppolyf_u_1k",
                       (("L", "30U"), ("W", "2U")))
        with self.assertRaises(pl.PostlayoutError):
            pl.emit_cards("por_comparator", [card], names)

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
