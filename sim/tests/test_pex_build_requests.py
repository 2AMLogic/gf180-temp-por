#!/usr/bin/env python3
"""Tests `sim/pex/build_requests.py`'s swept-axis guard (#469).

`build_requests.stage()` stages one `klt sim` request per (temperature,
supply) with `.param vdd_val` written into the body as a literal, so a staged
request must carry no swept supply/parameter axis at all. The guard that
enforced that named one request key, `corners.supply_v` -- an implementation
detail of `klt_batch._build_request`, which moved the lifted `.param` to
`corners.params` in #466. A key-specific guard goes dead the moment the key
moves, silently, and nothing covered it. These tests pin both keys.

They run on plain dict literals: no PDK, no ngspice, no klt, no network.

    python3 -m unittest discover -s sim/tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIM_DIR / "pex"))

import build_requests  # noqa: E402

SLUG = "por-trip"


def request(**over) -> dict:
    """A staged request shaped like `klt_batch._stage`'s output, with only the
    keys this guard reads. `corners` carries the two axes `stage()` does mean
    to sweep (process, temperature); the supply is a body literal.
    """
    req = {
        "corners": {
            "process": [{"name": "tt", "sections": ["typical"]}],
            "temperature_c": [27.0],
        },
        "backend": "batch",
    }
    req["corners"].update(over.pop("corners", {}))
    req.update(over)
    return req


class RefuseSweptAxis(unittest.TestCase):
    def test_trips_on_a_supply_v_axis(self):
        """The pre-#466 key for a lifted `.param`."""
        req = request(corners={"supply_v": [4.5, 5.0, 5.5]})
        with self.assertRaises(SystemExit) as cm:
            build_requests.refuse_swept_axis(SLUG, req)
        self.assertIn(SLUG, str(cm.exception))
        self.assertIn("supply_v", str(cm.exception))

    def test_trips_on_a_params_axis(self):
        """The post-#466 key: the failure the old guard could not see."""
        req = request(corners={"params": {"vdd_val": [4.5, 5.0, 5.5]}})
        with self.assertRaises(SystemExit) as cm:
            build_requests.refuse_swept_axis(SLUG, req)
        self.assertIn(SLUG, str(cm.exception))
        self.assertIn("params", str(cm.exception))

    def test_trips_on_exclude(self):
        """A sparse-grid carve-out only exists when there is an axis to carve."""
        req = request(exclude=[{"temperature_c": -40.0, "supply_v": 5.5}])
        with self.assertRaises(SystemExit) as cm:
            build_requests.refuse_swept_axis(SLUG, req)
        self.assertIn(SLUG, str(cm.exception))
        self.assertIn("exclude", str(cm.exception))

    def test_passes_on_a_request_with_no_supply_axis(self):
        """What `stage()` actually emits today (`lift_params=()`)."""
        self.assertIsNone(build_requests.refuse_swept_axis(SLUG, request()))

    def test_passes_on_empty_axis_values(self):
        """Truthiness, unchanged from the inline check: an empty mapping or
        list carries no sweep, so it is not a refusal.
        """
        req = request(corners={"supply_v": [], "params": {}}, exclude=[])
        self.assertIsNone(build_requests.refuse_swept_axis(SLUG, req))

    def test_names_every_offending_axis(self):
        req = request(corners={"supply_v": [5.0], "params": {"vdd_val": [5.0]}},
                      exclude=[{"temperature_c": -40.0}])
        with self.assertRaises(SystemExit) as cm:
            build_requests.refuse_swept_axis(SLUG, req)
        for key in ("supply_v", "params", "exclude"):
            self.assertIn(key, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
