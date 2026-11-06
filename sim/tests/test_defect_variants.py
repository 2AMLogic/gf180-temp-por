#!/usr/bin/env python3
"""The negative-control (known-bad) Monte Carlo variants (#417).

Each ``sim/<exp>-defect/`` experiment must be its nominal sibling plus exactly
one top-level shunt resistor, an independent seed range and unchanged limits,
so a control can only differ from the nominal campaign by the declared defect.

    python3 -m unittest discover -s sim/tests -k defect
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
NODES = {"temp-accuracy-mc": "xdut.nb", "por-threshold-mc": "xdut.sns"}


def _tb(slug: str) -> dict:
    return json.loads((SIM / slug / "testbench" / "tb.json").read_text())


class DefectVariantTest(unittest.TestCase):
    def test_stimulus_is_nominal_plus_one_shunt(self):
        for nominal, node in NODES.items():
            base = (SIM / nominal / "testbench" / "stimulus.spice").read_text()
            extra = (SIM / f"{nominal}-defect" / "testbench" / "stimulus.spice").read_text()
            self.assertTrue(extra.startswith(base), nominal)
            self.assertEqual(extra[len(base):].strip(), f"Rdef {node} 0 {{rdef}}", nominal)

    def test_manifest_differs_only_in_declared_fields(self):
        for nominal in NODES:
            a, b = _tb(nominal), _tb(f"{nominal}-defect")
            self.assertEqual(a["checks"], b["checks"], "limits must stay the nominal row limits")
            self.assertEqual(a["measure"], b["measure"])
            self.assertEqual(a["mc"]["n"], b["mc"]["n"])
            self.assertEqual(a["mc"]["binding_points"], b["mc"]["binding_points"])
            self.assertIn("rdef", b["params"])
            self.assertNotIn("rdef", a.get("params", {}))

    def test_seed_ranges_cannot_overlap(self):
        for nominal in NODES:
            a, b = _tb(nominal)["mc"], _tb(f"{nominal}-defect")["mc"]
            span = len(a["binding_points"]) * 100_000 + a["n"]
            self.assertGreaterEqual(abs(b["seed_base"] - a["seed_base"]), span)


if __name__ == "__main__":
    unittest.main()
