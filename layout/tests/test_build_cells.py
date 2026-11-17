#!/usr/bin/env python3
"""Geometry-invariant guards for layout/build_cells.py. No PDK, no klayout, no klt required.

    python3 -m unittest discover -s layout/tests -v

The pinned ``klt`` build cannot run the ``sab.*`` rule family at all (see
``layout/toolchain.json``; ``layout/drc-newer-klt-triage.md`` records why), so
the drawn-geometry invariants the DRC run would exercise are asserted here
directly from the module constants, naming the rule each one serves.
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

SAB_SPACE_1 = 0.42  # gf180mcu SB.2: minimum SAB-to-SAB spacing, um
POLY2_SPACE_1 = 0.24  # minimum poly-to-poly spacing, um


@skip_while_layout_stale
class TempCoreResistorBankTest(unittest.TestCase):
    """The temp_core resistor bank's SAB geometry (#518).

    ``width`` is read through ``parse_passives`` from the golden netlist's own
    ``r_width`` -- the same path ``_temp_core_resistor_bank`` takes -- so the
    guard breaks if the schematic ever changes size, instead of silently
    passing against a number retyped here.
    """

    @classmethod
    def setUpClass(cls):
        golden = (REPO_ROOT / "design" / "netlist" / "temp_core.spice").read_text()
        devices = lr.parse_passives(lr.subckt_body(golden, "temp_core"))
        widths = {
            lr.to_um(d["params"]["r_width"])
            for d in devices.values()
            if d["kind"] == "resistor"
        }
        assert len(widths) == 1, f"the bank draws one width, saw {sorted(widths)}"
        cls.width = widths.pop()

    def test_sab_overhang_is_strictly_positive(self):
        # No deck rule bounds this from below: poly left uncovered by SAB is
        # silicided, so an inset (or a coincident, o = 0) SAB would shunt the
        # ~350 ohm/sq body with two low-sheet strips neither DRC nor the
        # extractor can see.
        self.assertGreater(bc._R_SAB_OVERHANG, 0.0)

    def test_neighbouring_sab_markers_keep_sab_space_1(self):
        # sab.space.1 (SB.2): segments sit _R_PITCH apart and each overhangs
        # _R_SAB_OVERHANG toward its neighbour, so the SAB-to-SAB gap is
        # _R_PITCH - width - 2*_R_SAB_OVERHANG. 49 adjacent pairs fired on
        # temp_core before #518 (0.200 um against 0.420).
        gap = bc._R_PITCH - self.width - 2.0 * bc._R_SAB_OVERHANG
        self.assertGreaterEqual(gap, SAB_SPACE_1)

    def test_poly_gap_keeps_poly2_space_1(self):
        # poly2.space.1: the drawn poly gap between segments is
        # _R_PITCH - width, independent of the SAB overhang.
        gap = bc._R_PITCH - self.width
        self.assertGreaterEqual(gap, POLY2_SPACE_1)


if __name__ == "__main__":
    unittest.main()
