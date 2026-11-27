#!/usr/bin/env python3
"""Unit tests for build_cells.py's 0.005 um manufacturing-grid guarantees.

    python3 -m unittest discover -s layout/tests -v

No PDK, no klayout, no klt: ``klayout`` is imported lazily inside
``CellBuilder``, so the coordinate helpers import clean. The end-to-end proof
that every committed cell's vertices sit on the manufacturing grid is the
0.8.0+ deck's ``*.ongrid.1`` rules (issue #515 and
``layout/drc-newer-klt-triage.md`` 5.1); these tests pin the generators that
*produce* the coordinates, so a future netlist or pitch change cannot
silently reintroduce the defect family between deck runs.
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
from layout_staleness import skip_while_layout_stale  # noqa: E402

NM_PER_UM = 1000
GRID_NM = round(bc.MFG_GRID_UM * NM_PER_UM)  # the 5 nm manufacturing pitch


def nm(values) -> list[int]:
    """Coordinates as integer nanometres, the units these tests are exact in."""
    return [round(v * NM_PER_UM) for v in values]


def on_grid(values) -> bool:
    return all(v % GRID_NM == 0 for v in nm(values))


class ConstantGridTest(unittest.TestCase):
    """The half-extents snapping relies on are grid multiples.

    ``_snap`` guarantees an on-grid *centre*; the edges derived from it are
    on-grid and exactly the rule size apart only while every half-extent is
    itself a whole multiple of the grid. This is the invariant that makes
    "snap the centre, then derive the edges" satisfy the width rules by
    construction rather than by test.
    """

    def test_half_extents_are_grid_multiples(self):
        for name, value in [
            ("CONTACT_SIDE_UM/2", bc.CONTACT_SIDE_UM / 2.0),
            ("VIA_SIDE_UM/2", bc.VIA_SIDE_UM / 2.0),
            ("TOP_WIRE_W/2", bc.TOP_WIRE_W / 2.0),
            ("TOP_PAD_HALF", bc.TOP_PAD_HALF),
            ("_M2_HALF", bc._M2_HALF),
            ("_VIA_PAD_HALF", bc._VIA_PAD_HALF),
            ("TRACK_W_UM/2", bc.TRACK_W_UM / 2.0),
            ("CONT_INSET_UM", bc.CONT_INSET_UM),
            ("SD_EXT_UM", bc.SD_EXT_UM),
            ("TILE_GAP_UM", bc.TILE_GAP_UM),
            ("REGION_GAP_UM", bc.REGION_GAP_UM),
            ("TRACK_PITCH_UM", bc.TRACK_PITCH_UM),
            ("DIVIDER_LEG_SPACE_UM", bc.DIVIDER_LEG_SPACE_UM),
            ("DIVIDER_CAP_UM", bc.DIVIDER_CAP_UM),
            ("DIVIDER_STRING_GAP_UM", bc.DIVIDER_STRING_GAP_UM),
            ("DIVIDER_BASE_Y_UM", bc.DIVIDER_BASE_Y_UM),
            ("RES_SPACE_UM", bc.RES_SPACE_UM),
            ("RES_HEAD_UM", bc.RES_HEAD_UM),
            ("_R_PITCH", bc._R_PITCH),
            ("_R_HEAD", bc._R_HEAD),
            ("PNP_CONT_PITCH_UM", bc.PNP_CONT_PITCH_UM),
            ("PNP_CONT_INSET_UM", bc.PNP_CONT_INSET_UM),
        ]:
            self.assertTrue(on_grid([value]), f"{name}={value} is off-grid")

    def test_snap_moves_at_most_half_a_grid_pitch(self):
        for v in (0.0, 0.002, 0.0025, 0.003, 1.234, -3.456, 153.902):
            self.assertLessEqual(abs(bc._snap(v) - v), bc.MFG_GRID_UM / 2.0)


class SpanHelperGridTest(unittest.TestCase):
    """``_span``/``_contact_rows`` centres land on the manufacturing grid.

    Their steps are arbitrary divisions of a span, which is exactly how the
    31,928 ``contact.ongrid.1`` markers of the 0.8.0 triage arose (#515).
    """

    # Bounds and pitches that are DBU-exact but not grid-exact, plus the
    # degenerate case.
    CASES = [
        (0.35, 1.65, 0.5),
        (0.5, 3.3, 2.0),
        (-1.2, 2.705, 0.5),
        (0.35, 10.15, 2.0),
        (5.0, 5.0, 1.0),  # high == low: midpoint fallback
        (5.0, 4.0, 1.0),  # high < low: midpoint fallback
    ]

    def test_span_centres_on_grid(self):
        for low, high, pitch in self.CASES:
            centres = bc._span(low, high, pitch)
            self.assertTrue(centres, f"_span({low}, {high}, {pitch}) is empty")
            self.assertTrue(
                on_grid(centres),
                f"_span({low}, {high}, {pitch}) -> {nm(centres)} nm has off-grid "
                "centres",
            )

    def test_contact_rows_on_grid(self):
        for width in (1.0, 2.0, 3.3, 10.15, 0.9, 0.821):
            rows = bc._contact_rows(width)
            self.assertTrue(
                on_grid(rows),
                f"_contact_rows({width}) -> {nm(rows)} nm has off-grid rows",
            )

    def test_contact_rows_narrow_fallback_snaps(self):
        # The single-contact fallback centres on width/2; a width that is an
        # odd multiple of 5 nm (here 555 nm) would put that contact on a
        # 2.5 nm offset without the snap.
        rows = bc._contact_rows(0.555)
        self.assertEqual(nm(rows), [280])  # 0.28 um, on-grid


class PlacementGridTest(unittest.TestCase):
    """Device-tile origins come out on the manufacturing grid.

    Tile x0 advances by netlist device lengths, which are DBU-exact but not
    in general grid-exact; everything a tile derives (contact columns, gate
    strips, plates) inherits its origin (#515).
    """

    def test_por_comparator_tile_origins_on_grid(self):
        devices = bc._golden_devices("por_comparator.spice", "por_comparator")
        tiles = bc._place_tiles(
            devices, (bc.POR_COMPARATOR_PMOS, bc.POR_COMPARATOR_NMOS)
        )
        self.assertTrue(tiles)
        self.assertTrue(
            on_grid([tile["x0"] for tile in tiles]),
            "tile x0 values are not all on the manufacturing grid",
        )

    def test_tiles_do_not_overlap_after_snapping(self):
        devices = bc._golden_devices("por_comparator.spice", "por_comparator")
        tiles = bc._place_tiles(
            devices, (bc.POR_COMPARATOR_PMOS, bc.POR_COMPARATOR_NMOS)
        )
        for a, b in zip(tiles, tiles[1:]):
            if a["group"] == b["group"]:
                self.assertGreaterEqual(
                    b["x0"] - a["x0"],
                    2 * bc.SD_EXT_UM + a["l"],
                    f"tiles {a['name']} and {b['name']} overlap after snapping",
                )


class DividerLegPlanGridTest(unittest.TestCase):
    """The sense divider's leg plan is on-grid *and* electrically exact.

    This is the live hazard #515 fixed: ``_resistor_leg_plan`` used to leave
    ``leg_len`` a whole number of 1 nm DBU only, putting every leg edge of
    all three divider strings off the manufacturing grid (912 on-grid
    markers across ``por_comparator`` and ``temp_por_top``). Snapping
    ``leg_len`` down and folding the per-leg remainder into the last leg
    must keep the electrical identity bit-for-bit -- the marked-body area it
    describes is what the deck's extractor solves R from, so any drift would
    surface as an LVS ``device.property`` mismatch.
    """

    def test_divider_plans_on_grid(self):
        leg_w, lengths = bc._divider_resistor_lengths()
        for name, length in lengths.items():
            legs, leg_len, tail_extra = bc._resistor_leg_plan(length, leg_w)
            self.assertTrue(
                on_grid([leg_len, tail_extra]),
                f"{name}: leg_len={nm([leg_len])[0]}nm tail={nm([tail_extra])[0]}nm "
                "off the manufacturing grid",
            )

    def test_divider_plans_electrically_exact(self):
        leg_w, lengths = bc._divider_resistor_lengths()
        for name, length in lengths.items():
            legs, leg_len, tail_extra = bc._resistor_leg_plan(length, leg_w)
            drawn_nm = (
                legs * nm([leg_len])[0]
                + nm([tail_extra])[0]
                - 2 * round(bc.DIVIDER_CAP_UM * NM_PER_UM)
                + (legs - 1) * round(bc.DIVIDER_LEG_SPACE_UM * NM_PER_UM)
            )
            self.assertEqual(
                drawn_nm,
                round(length * NM_PER_UM),
                f"{name}: the leg plan no longer reconstructs r_length exactly",
            )

    def test_off_grid_resistor_length_fails_loudly(self):
        # A length whose folded budget is not a grid multiple has no exact
        # on-grid plan; the build must refuse rather than draw off-grid.
        # (1.002 um folds to a 2602 nm budget: 2 nm off the 5 nm grid.)
        with self.assertRaises(ValueError):
            bc._resistor_leg_plan(1.002, 2.0)


class DrawnSegmentGridTest(unittest.TestCase):
    """``resistor_segments`` legs are grid multiples for the current netlist.

    ``resistor_segments`` guarantees only a whole number of 1 nm DBU per leg
    and raises rather than rounding -- so a future ``r_length`` could produce
    an off-grid leg, at which point snapping its length would shift the
    extracted resistance into an LVS mismatch. All legs are on-grid today;
    this pins that so the change cannot land silently.
    """

    def test_bias_core_segment_lengths_on_grid(self):
        cards = bc._golden_resistors("bias_core.spice", "bias_core")
        for name in bc.BIAS_CORE_RESISTOR_ORDER:
            length = lr.to_um(cards[name]["params"]["r_length"])
            segments = lr.resistor_segments(length, lr.resistor_fold("bias_core"))
            self.assertTrue(
                on_grid(segments),
                f"bias_core {name}: segments {nm(segments)} nm off-grid",
            )

    @skip_while_layout_stale
    def test_temp_core_segment_lengths_on_grid(self):
        devices = lr.parse_passives(
            lr.subckt_body(
                (REPO_ROOT / "design" / "netlist" / "temp_core.spice").read_text(),
                "temp_core",
            )
        )
        for name in lr.CELLS["temp_core"]["resistors"]:
            length = lr.to_um(devices[name]["params"]["r_length"])
            segments = lr.resistor_segments(length, lr.resistor_fold("temp_core"))
            self.assertTrue(
                on_grid(segments),
                f"temp_core {name}: segments {nm(segments)} nm off-grid",
            )


if __name__ == "__main__":
    unittest.main()
