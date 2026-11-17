#!/usr/bin/env python3
"""Unit tests for build_cells.py's SAB marker-containment invariant.

    python3 -m unittest discover -s layout/tests -v

No PDK, no klayout, no klt: the two resistor constructions under test only
ever call ``CellBuilder.box``/``CellBuilder.contact``, so a recorder with the
same surface sees the same geometry (same contract as test_grid.py, whose
docstring explains why ``klayout`` must stay lazily imported).

What these tests pin is #517's actual invariant: in both constructions that
draw a widened SAB -- ``_poly_resistor`` (the temp/bias core resistor banks)
and ``_resistor_string`` (the sense divider) -- every marker-layer rectangle
(``RES_MK``, ``PPLUS``, ``RESISTOR_ID``/``DIVIDER_RESISTOR_MK``) is strictly
contained in ``x`` by some SAB rectangle. That strict containment is what
makes SAB the wider layer at each leg's lateral boundary, so SB.10 has no
coincident Poly2 edge to report; if a future edit moves SAB back into the
coincident marker loop, these tests fail before any DRC run. The ``y``
direction is deliberately *not* asserted strict: the row-line crossings snap
outward on the manufacturing grid (#515), so SAB may equal or exceed the
markers vertically, never fall short.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = LAYOUT_DIR.parent
sys.path.insert(0, str(LAYOUT_DIR))

import build_cells as bc  # noqa: E402  (klayout is imported lazily, per-cell)


class RecordingBuilder:
    """``CellBuilder`` stand-in: records every ``box`` per layer spec.

    The real builder imports ``klayout.db`` in its constructor; these tests
    pin pure coordinates, so recording the same calls is enough.
    """

    def __init__(self) -> None:
        self.boxes: dict[tuple[int, int], list[tuple[float, float, float, float]]] = {}

    def box(self, spec, x0: float, y0: float, x1: float, y1: float) -> None:
        self.boxes.setdefault(spec, []).append((x0, y0, x1, y1))

    def contact(self, x: float, y: float) -> None:
        pass


def contained_in_x(marker, sab) -> bool:
    """``sab`` covers ``marker`` in y and strictly contains it in x."""
    mx0, my0, mx1, my1 = marker
    sx0, sy0, sx1, sy1 = sab
    return sx0 < mx0 and mx1 < sx1 and sy0 <= my0 and my1 <= sy1


class SabContainmentTest(unittest.TestCase):
    """SAB strictly contains every marker rectangle in x, in both constructions."""

    def assert_contained(self, b: RecordingBuilder, layers, context: str) -> None:
        self.assertTrue(b.boxes.get(bc.SAB), f"{context}: no SAB boxes recorded")
        for spec, name in layers:
            boxes = b.boxes.get(spec, [])
            self.assertTrue(boxes, f"{context}: no {name} boxes recorded")
            for box in boxes:
                self.assertTrue(
                    any(contained_in_x(box, sab) for sab in b.boxes[bc.SAB]),
                    f"{context}: {name} box {box} is not strictly contained "
                    "in x by any SAB rectangle",
                )

    def test_poly_resistor_markers_strictly_inside_sab(self):
        # Same shape of call as bias_core's resistor banks draw: an even leg
        # count, off-grid origin (exercising the snap), 6 legs of 1.0 um.
        b = RecordingBuilder()
        bc._poly_resistor(b, 3.217, -2.213, 1.0, 12.0, 6)
        self.assert_contained(
            b,
            [
                (bc.RES_MK, "RES_MK"),
                (bc.PPLUS, "PPLUS"),
                (bc.RESISTOR_ID, "RESISTOR_ID"),
            ],
            "_poly_resistor",
        )

    def test_resistor_string_markers_strictly_inside_sab(self):
        # The real sense divider: every segment's own plan off the golden
        # netlist, drawn exactly as por_comparator draws it.
        leg_w, lengths = bc._divider_resistor_lengths()
        for name, length in lengths.items():
            legs, leg_len, tail_extra = bc._resistor_leg_plan(length, leg_w)
            b = RecordingBuilder()
            bc._resistor_string(
                b,
                7.213,
                bc.DIVIDER_BASE_Y_UM,
                leg_w=leg_w,
                legs=legs,
                leg_len=leg_len,
                tail_extra=tail_extra,
            )
            self.assert_contained(
                b,
                [
                    (bc.RES_MK, "RES_MK"),
                    (bc.DIVIDER_RESISTOR_MK, "DIVIDER_RESISTOR_MK"),
                ],
                f"_resistor_string({name})",
            )


if __name__ == "__main__":
    unittest.main()
