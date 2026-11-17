#!/usr/bin/env python3
"""Assert every vertex of every committed ``layout/cells/*.gds`` sits on the
manufacturing grid (issue #553).

    python3 layout/check_gds_grid.py [cells_dir]

``layout/tests/test_grid.py`` pins the *coordinate-producing helpers* of
``build_cells.py``; this pins their **end product**. It exists because three
producers snap only part of what they draw (``_TopRoutes.box`` snaps nothing,
``hwire``/``vwire`` snap one axis each) and the deck carries no
``metal2.ongrid.*``/``metal3.ongrid.*`` rule, so an off-grid Metal2/Metal3
vertex would fire nothing at DRC time while every unit test stayed green.
This sweep is layer- and deck-version-agnostic: it reads the committed GDS
directly and asks one question of every vertex.

Counting convention (one VERTEX = one ``x, y`` point in integer DBU, never
compared as floats, the way ``test_grid.py`` compares):

* a box counts as its **two defining points** -- together they carry all
  four coordinate values of the box's four corners, so no off-grid corner
  coordinate can hide in the two that are skipped;
* a polygon counts every hull point and every hole point;
* a path counts every point of its spine;
* a text counts its anchor; an instance counts each placement origin
  (regular arrays expand to ``na * nb`` origins).

The grid pitch is re-derived per file as ``round(MFG_GRID_UM / dbu)`` --
``MFG_GRID_UM`` imported from ``build_cells`` so the constant has one source
of truth -- never hardcoded as 5 DBU.

Needs only the ``klayout`` python module and the stdlib: no PDK, no deck,
no ``klt``. Exits 0 with ``TOTAL_OFF_GRID = 0``, or 1 naming every offender.
"""

from __future__ import annotations

import sys
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAYOUT_DIR.parent

sys.path.insert(0, str(LAYOUT_DIR))

import klayout.db as kdb  # noqa: E402  (the one non-stdlib dependency)

import build_cells as bc  # noqa: E402  (klayout is imported lazily, per-cell)

DEFAULT_CELLS_DIR = REPO_ROOT / "layout" / "cells"

#: The output header names the convention so a future reader comparing
#: against issue #553's tables (which count points, not per-axis
#: coordinates) is not misled by a 2x difference.
HEADER = (
    "# grid sweep: one vertex = one (x, y) point in integer DBU;"
    " boxes count 2 defining points, polygons hull+holes,"
    " paths spine points, texts anchors, instances placement origins"
)


def grid_pitch_dbu(layout: kdb.Layout) -> int:
    """The manufacturing grid in DBU units of *this* layout.

    Derived from ``build_cells.MFG_GRID_UM`` and the layout's own ``dbu``:
    at the standard 1 nm DBU the 0.005 um grid is 5 DBU, but a layout read
    at a finer ``dbu`` must recompute, not reuse the 5.
    """
    return round(bc.MFG_GRID_UM / layout.dbu)


def _shape_points(shape: kdb.Shape):
    """Yield every ``(x, y)`` vertex of one shape, in integer DBU."""
    if shape.is_box():
        box = shape.box
        yield box.p1.x, box.p1.y
        yield box.p2.x, box.p2.y
    elif shape.is_polygon():
        poly = shape.polygon
        for point in poly.each_point_hull():
            yield point.x, point.y
        for i in range(poly.holes()):
            for point in poly.each_point_hole(i):
                yield point.x, point.y
    elif shape.is_simple_polygon():
        for point in shape.simple_polygon.each_point():
            yield point.x, point.y
    elif shape.is_path():
        for point in shape.path.each_point():
            yield point.x, point.y
    elif shape.is_text():
        text = shape.text
        yield text.x, text.y


def _instance_origins(cell: kdb.Cell):
    """Yield every placement ``(x, y)`` origin in *cell*, arrays expanded."""
    for inst in cell.each_inst():
        if inst.is_regular_array():
            base = inst.trans.disp
            for i in range(inst.na):
                for j in range(inst.nb):
                    disp = base + i * inst.a + j * inst.b
                    yield disp.x, disp.y
        else:
            disp = inst.trans.disp
            yield disp.x, disp.y


def sweep_layout(layout: kdb.Layout, grid_dbu: int) -> tuple[int, int]:
    """``(vertices, off_grid)`` over every cell in *layout*.

    Visits every cell in the file (not just the top cell) so sub-cell
    geometry counts exactly once no matter how many times it is placed.
    """
    vertices = 0
    off_grid = 0
    for cell in layout.each_cell():
        for layer_index in layout.layer_indexes():
            for shape in cell.shapes(layer_index):
                for x, y in _shape_points(shape):
                    vertices += 1
                    if x % grid_dbu or y % grid_dbu:
                        off_grid += 1
        for x, y in _instance_origins(cell):
            vertices += 1
            if x % grid_dbu or y % grid_dbu:
                off_grid += 1
    return vertices, off_grid


def sweep_file(path: Path, grid_out: dict) -> tuple[int, int]:
    """``sweep_layout`` over one GDS file, recording its derived pitch."""
    layout = kdb.Layout()
    layout.read(str(path))
    grid_dbu = grid_pitch_dbu(layout)
    grid_out[str(path)] = grid_dbu
    return sweep_layout(layout, grid_dbu)


def main(argv: list[str]) -> int:
    cells_dir = Path(argv[0]) if argv else DEFAULT_CELLS_DIR
    files = sorted(cells_dir.glob("*.gds"))
    if not files:
        print(f"check_gds_grid: no *.gds under {cells_dir}", file=sys.stderr)
        return 2

    print(HEADER)
    print(f"# grid = {bc.MFG_GRID_UM} um, re-derived per file as "
          f"round(grid / dbu) DBU; source of truth: build_cells.MFG_GRID_UM")

    total = 0
    grids: dict[str, int] = {}
    for path in files:
        vertices, off_grid = sweep_file(path, grids)
        total += off_grid
        print(f"{path.name}: vertices={vertices} off_grid={off_grid}")

    pitch_note = ""
    pitches = sorted(set(grids.values()))
    if len(pitches) > 1:
        pitch_note = (f" (grid pitch differs across files: "
                      f"{ {Path(p).name: g for p, g in grids.items()} }")
    print(f"TOTAL_OFF_GRID = {total}{pitch_note}")
    if total:
        print("off-grid vertices present: every coordinate must be a whole "
              "multiple of the manufacturing grid -- fix the producing "
              "generator, do not snap the GDS", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
