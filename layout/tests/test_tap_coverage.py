#!/usr/bin/env python3
"""Unit tests for build_cells.py's build-time tap/tie assertion (#532).

    python3 -m unittest discover -s layout/tests -v

The assertion under test, ``build_cells._assert_tap_coverage``, is the
mechanical stand-in for the DRM's ``DF.13_LV``/``DF.14_LV`` body-tie distance
rules (``comp.tap_distance.*`` in klt 0.8.0+; the pinned 0.6.0 deck cannot
run them) and for the tie itself, which the deck has no layer to check at
all (klayout-tools#303). A coverage assertion that can only pass is the same
defect this issue exists to fix -- "a passing check is not evidence the
structure exists" -- so every test here bites: each one builds a deliberately
wrong body and requires the raise, then a correct one and requires the pass.

``klayout`` is imported lazily inside ``CellBuilder``; the whole module skips
without it (the same pattern ``test_check_gds_grid.py`` uses). No PDK, no
klt.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAYOUT_DIR))

import build_cells as bc  # noqa: E402  (klayout is imported lazily, per-cell)

try:
    import klayout.db as kdb  # noqa: E402
except ImportError:  # pragma: no cover - exercised on hosts without klayout
    kdb = None


@unittest.skipUnless(kdb is not None, "klayout python module not available")
class PolygonDistanceTest(unittest.TestCase):
    """``_polygon_distance_um`` is a *true* distance, not a bbox one.

    ``layout/drc-newer-klt-triage.md`` 5.5 records both traps this file's
    assertion must not fall into: bounding-box distance reads 0 for anything
    inside a tap ring's bbox (the ring swallows its own array), and
    ``Region.sized(20 um)`` + ``interacting`` grows square corners, up to
    20*(sqrt(2)-1) ~= 8.3 um too permissive diagonally.
    """

    def _poly(self, box):
        return kdb.Polygon(
            kdb.Box(round(box[0] * 1000), round(box[1] * 1000),
                    round(box[2] * 1000), round(box[3] * 1000))
        )

    def test_disjoint_rectangles_measure_the_gap(self):
        self.assertEqual(
            bc._polygon_distance_um(0.001, self._poly((0, 0, 1, 1)),
                                    self._poly((1.5, 0, 2.5, 1))),
            0.5,
        )

    def test_diagonal_offset_measures_euclidean_not_coordinate(self):
        # A 3-4-5 offset: a bbox (Chebyshev) reading would say 4.
        self.assertEqual(
            bc._polygon_distance_um(0.001, self._poly((0, 0, 1, 1)),
                                    self._poly((4, 5, 5, 6))),
            5.0,
        )

    def test_a_ring_stands_its_hole_edge_from_material_inside_it(self):
        ring = kdb.Polygon(kdb.Box(0, 0, 30000, 30000))
        ring.insert_hole(kdb.Box(5000, 5000, 25000, 25000))
        inside = self._poly((10, 10, 20, 20))
        # The ring's bbox swallows `inside`, so a bbox distance reads 0; the
        # true point-set distance is to the hole's edge, 5 um away.
        self.assertEqual(bc._polygon_distance_um(0.001, ring, inside), 5.0)


@unittest.skipUnless(kdb is not None, "klayout python module not available")
class TapCoverageAssertionTest(unittest.TestCase):
    """The assertion itself, on synthetic bodies small enough to reason about.

    Every body draws one field NMOS and one in-well PMOS, both gated, plus
    whatever taps the individual test wants judged.
    """

    def _body(self):
        b = bc.CellBuilder("tap_coverage_synthetic")
        # A gated field NMOS: comp the gate poly crosses.
        b.box(bc.COMP, 0.0, 0.0, 2.0, 1.0)
        b.box(bc.POLY2, 0.0, 0.4, 2.0, 0.8)
        # A gated in-well PMOS.
        b.box(bc.NWELL, 20.0, -1.0, 30.0, 12.0)
        b.box(bc.COMP, 22.0, 0.0, 24.0, 1.0)
        b.box(bc.POLY2, 22.0, 0.4, 24.0, 0.8)
        return b

    def _sub_tap(self, b, x0, y0, x1, y1, net="VSS", contact=True, label=True):
        b.box(bc.COMP, x0, y0, x1, y1)
        b.blanket(bc.PPLUS, [(x0, y0, x1, y1)], bc.IMPLANT_OVERHANG_UM)
        b.box(bc.METAL1, x0 - 0.05, y0 - 0.05, x1 + 0.05, y1 + 0.05)
        if contact:
            b.contact((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        if label:
            b.label(net, (x0 + x1) / 2.0, (y0 + y1) / 2.0)

    def _well_tap(self, b, x0, y0, x1, y1, net="VDD"):
        b.box(bc.COMP, x0, y0, x1, y1)
        b.blanket(bc.NPLUS, [(x0, y0, x1, y1)], bc.IMPLANT_OVERHANG_UM)
        b.box(bc.METAL1, x0 - 0.05, y0 - 0.05, x1 + 0.05, y1 + 0.05)
        b.contact((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        b.label(net, (x0 + x1) / 2.0, (y0 + y1) / 2.0)

    def test_a_tapped_body_passes(self):
        b = self._body()
        self._sub_tap(b, 0.0, -2.0, 2.0, -1.0)
        self._well_tap(b, 22.0, 2.0, 24.0, 3.0)
        bc._assert_tap_coverage(b, "tap_coverage_synthetic")  # no raise

    def test_a_tap_starved_row_bites(self):
        # The substrate tap 28 um away: DF.14_LV's exact defect shape, the
        # one temp_core's 27 NMOS fingers carried before #532.
        b = self._body()
        self._sub_tap(b, 30.0, 0.0, 32.0, 1.0)
        self._well_tap(b, 22.0, 2.0, 24.0, 3.0)
        with self.assertRaises(AssertionError) as raised:
            bc._assert_tap_coverage(b, "tap_coverage_synthetic")
        self.assertIn("DF.14_LV", str(raised.exception))

    def test_a_well_without_its_own_tap_bites(self):
        # A tie in a *different* well does not serve a PMOS: DF.13_LV is
        # per-well, and two physically separate Nwells do not bridge.
        b = self._body()
        self._sub_tap(b, 0.0, -2.0, 2.0, -1.0)
        b.box(bc.NWELL, 60.0, -1.0, 70.0, 12.0)  # a second, distant well
        self._well_tap(b, 62.0, 0.0, 64.0, 1.0)  # ...whose tap serves only it
        with self.assertRaises(AssertionError) as raised:
            bc._assert_tap_coverage(b, "tap_coverage_synthetic")
        self.assertIn("DF.13_LV", str(raised.exception))

    def test_square_corner_permissiveness_is_rejected(self):
        # The device corner sits 16.5 um over and 16.5 um up from the tap's
        # corner: 23.3 um Euclidean -- outside the 20 um limit -- but inside
        # a sized(20 um) square, so a square-corner check would wave it
        # through. The true-distance assertion must not.
        b = self._body()
        self._sub_tap(b, 17.5, 17.5, 18.5, 18.5)
        self._well_tap(b, 22.0, 2.0, 24.0, 3.0)
        with self.assertRaises(AssertionError) as raised:
            bc._assert_tap_coverage(b, "tap_coverage_synthetic")
        self.assertIn("DF.14_LV", str(raised.exception))

    def test_a_floating_tap_bites(self):
        # Contacted, implanted, and metal-covered -- but its metal reaches no
        # labelled net, which is the tie defect the deck cannot see
        # (klayout-tools#303) and LVS only reports as a far-away mismatch.
        b = self._body()
        self._sub_tap(b, 0.0, -2.0, 2.0, -1.0, label=False)
        self._well_tap(b, 22.0, 2.0, 24.0, 3.0)
        with self.assertRaises(AssertionError) as raised:
            bc._assert_tap_coverage(b, "tap_coverage_synthetic")
        self.assertIn("no labelled net", str(raised.exception))

    def test_a_substrate_tap_on_the_wrong_net_bites(self):
        # A substrate tie is the VSS net; one strapped to VDD is a real
        # short the deck's rules never couple.
        b = self._body()
        self._sub_tap(b, 0.0, -2.0, 2.0, -1.0, net="VDD")
        self._well_tap(b, 22.0, 2.0, 24.0, 3.0)
        with self.assertRaises(AssertionError) as raised:
            bc._assert_tap_coverage(b, "tap_coverage_synthetic")
        self.assertIn("other than VSS", str(raised.exception))

    def test_an_uncontacted_tap_bites(self):
        # COMP + implant alone is an uncontacted junction, not a tap.
        b = self._body()
        self._sub_tap(b, 0.0, -2.0, 2.0, -1.0, contact=False)
        self._well_tap(b, 22.0, 2.0, 24.0, 3.0)
        with self.assertRaises(AssertionError) as raised:
            bc._assert_tap_coverage(b, "tap_coverage_synthetic")
        self.assertIn("no contact", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
