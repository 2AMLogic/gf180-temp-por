#!/usr/bin/env python3
"""Unit tests for check_gds_grid.py's off-grid *detector*.

    python3 -m unittest discover -s layout/tests -v

These exercise the sweep on synthetic in-memory geometry (one deliberately
off-grid box, polygon hole, path point, text anchor and instance origin),
so ``make test`` stays meaningful for developers. They are NOT the CI
guarantee: the ``layout/tests`` CI step runs on both matrix entries before
``klayout`` is installed, so these tests skip without it -- the end-to-end
guard is the dedicated ``layout/check_gds_grid.py`` CI step on the 3.11
entry (issue #553), which runs after the grader install that provides the
``klayout`` module.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAYOUT_DIR))

try:
    import klayout.db as kdb  # noqa: E402

    import check_gds_grid as cgg  # noqa: E402  (needs LAYOUT_DIR on sys.path)
except ImportError:  # klayout or the checker itself is not importable
    kdb = None
    cgg = None

NM = 1000  # the DBU these tests build geometry in (dbu = 0.001 um)


@unittest.skipUnless(kdb is not None, "klayout python module not available")
class DetectorTest(unittest.TestCase):
    """The sweep counts every GDS-representable vertex kind and flags
    off-grid ones, comparing in integer DBU.
    """

    def layout(self, dbu: float = 0.001) -> "kdb.Layout":
        lay = kdb.Layout()
        lay.dbu = dbu
        return lay

    def sweep(self, lay: "kdb.Layout"):
        return cgg.sweep_layout(lay, cgg.grid_pitch_dbu(lay))

    def test_on_grid_box_counted_and_clean(self):
        lay = self.layout()
        cell = lay.create_cell("on_grid")
        cell.shapes(lay.layer(34, 0)).insert(kdb.Box(0, 0, 100 * NM, 50 * NM))
        self.assertEqual(self.sweep(lay), (2, 0))

    def test_off_grid_box_flagged(self):
        lay = self.layout()
        cell = lay.create_cell("off_grid")
        # Every coordinate is a whole DBU but x=1 nm sits between the 5 nm
        # manufacturing-grid lines -- the defect family #515/#542 cleared and
        # this checker exists to keep gone (#553). p1 carries the off-grid x;
        # p2 (101 um, 50 um) is on-grid, and the two skipped corners only
        # repeat coordinates p1/p2 already carry.
        cell.shapes(lay.layer(34, 0)).insert(kdb.Box(1, 0, 101 * NM, 50 * NM))
        self.assertEqual(self.sweep(lay), (2, 1))

    def test_box_defining_points_cover_all_corner_coordinates(self):
        # A box is counted as its two defining points; together they carry
        # all four coordinate values of its four corners, so no off-grid
        # corner coordinate can hide (p2 here is on-grid, the y=3 nm edge
        # is not).
        lay = self.layout()
        cell = lay.create_cell("half_off")
        cell.shapes(lay.layer(34, 0)).insert(kdb.Box(0, 3, 100 * NM, 50 * NM))
        self.assertEqual(self.sweep(lay), (2, 1))

    def test_polygon_hull_and_hole_points(self):
        lay = self.layout()
        cell = lay.create_cell("holed")
        poly = kdb.Polygon(kdb.Box(0, 0, 500 * NM, 500 * NM))
        poly.insert_hole(kdb.Box(100 * NM + 2, 100 * NM, 200 * NM, 200 * NM))
        cell.shapes(lay.layer(30, 0)).insert(poly)
        # 4 on-grid hull points + 4 hole points, two of which (x=502 nm)
        # are off-grid.
        vertices, off_grid = self.sweep(lay)
        self.assertEqual(vertices, 8)
        self.assertEqual(off_grid, 2)

    def test_path_points(self):
        lay = self.layout()
        cell = lay.create_cell("wired")
        cell.shapes(lay.layer(34, 0)).insert(
            kdb.Path([kdb.Point(0, 0), kdb.Point(50 * NM + 1, 0),
                      kdb.Point(100 * NM, 0)], 200)
        )
        self.assertEqual(self.sweep(lay), (3, 1))

    def test_text_anchor(self):
        lay = self.layout()
        cell = lay.create_cell("labelled")
        shapes = cell.shapes(lay.layer(34, 10))
        shapes.insert(kdb.Text("on", kdb.Trans(kdb.Vector(100 * NM, 0))))
        shapes.insert(kdb.Text("off", kdb.Trans(kdb.Vector(100 * NM, 7))))
        self.assertEqual(self.sweep(lay), (2, 1))

    def test_instance_origins_and_array_expansion(self):
        lay = self.layout()
        sub = lay.create_cell("sub")
        sub.shapes(lay.layer(34, 0)).insert(kdb.Box(0, 0, 100 * NM, 100 * NM))
        top = lay.create_cell("top")
        top.insert(kdb.CellInstArray(sub.cell_index(), kdb.Trans(kdb.Vector(7, 0))))
        # A 2x2 regular array whose y-step is 3 nm: four placements, two of
        # them (the y=3 nm row) off-grid. Instance origins count per
        # placement, not per Instance handle.
        top.insert(kdb.CellInstArray(
            sub.cell_index(), kdb.Trans(kdb.Vector(0, 0)),
            kdb.Vector(200 * NM, 0), kdb.Vector(0, 3), 2, 2))
        vertices, off_grid = self.sweep(lay)
        # 2 (sub-cell box defining points) + 1 (single instance) + 4 (array
        # placements)
        self.assertEqual(vertices, 7)
        self.assertEqual(off_grid, 3)

    def test_empty_layout_is_clean_zero(self):
        lay = self.layout()
        lay.create_cell("empty")
        self.assertEqual(self.sweep(lay), (0, 0))

    def test_grid_pitch_recomputed_from_dbu(self):
        # The pitch must be re-derived from the layout's own dbu, not
        # assumed to be 5 DBU: at dbu = 0.0005 um the 0.005 um grid is 10
        # DBU, so x = 20 is on-grid and x = 7 is not.
        lay = self.layout(dbu=0.0005)
        self.assertEqual(cgg.grid_pitch_dbu(lay), 10)
        cell = lay.create_cell("other_dbu")
        shapes = cell.shapes(lay.layer(34, 0))
        shapes.insert(kdb.Box(20, 20, 4000, 2000))
        shapes.insert(kdb.Box(7, 20, 4000, 2000))
        # Second box: p1=(7, 20) has the off-grid x, p2 is on-grid.
        self.assertEqual(self.sweep(lay), (4, 1))

    def test_main_exit_code_over_a_directory(self):
        # The CLI path: a directory of written-out GDS files, one clean and
        # one off-grid -- exit 0 is the all-clean verdict, 1 the failure.
        import contextlib
        import io

        on_grid = self.layout()
        on_grid.create_cell("a").shapes(on_grid.layer(34, 0)).insert(
            kdb.Box(0, 0, 100 * NM, 50 * NM))
        off_grid = self.layout()
        off_grid.create_cell("b").shapes(off_grid.layer(34, 0)).insert(
            kdb.Box(1, 1, 100 * NM, 50 * NM))
        with tempfile.TemporaryDirectory() as tmp:
            on_grid.write(str(Path(tmp) / "a.gds"))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cgg.main([tmp]), 0)
        with tempfile.TemporaryDirectory() as tmp:
            off_grid.write(str(Path(tmp) / "b.gds"))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cgg.main([tmp]), 1)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cgg.main([tmp]), 2)


if __name__ == "__main__":
    unittest.main()
