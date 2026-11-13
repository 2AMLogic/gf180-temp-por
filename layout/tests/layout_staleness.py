"""Skip gate for layout tests that cannot pass while ``temp_core``'s layout lags its schematic.

DR-031 changed the ``temp_core`` schematic and defers its layout (see its
Consequences section; tracked in #458). Until the LVS reference manifest
accounts for every device in ``design/netlist/temp_core.spice``, the tests that
build the reference from that netlist, or compare it with committed layout
artifacts, have nothing true to assert.

The skip is conditional on that mismatch, not unconditional: once the manifest
catches up it lifts by itself, so no stale skip outlives the layout rework.
Delete this module when #458 closes.
"""

from __future__ import annotations

import unittest

import lvs_reference as lr

TRACKING = "#458"


def _schematic_devices() -> set[str]:
    spec = lr.CELLS["temp_core"]
    body = lr.subckt_body((lr.NETLIST_DIR / spec["source"]).read_text(), spec["subckt"])
    return set(lr.parse_devices(body)) | set(lr.parse_capacitors(body)) | set(
        lr.parse_passives(body)
    )


def _manifest_devices() -> set[str]:
    spec = lr.CELLS["temp_core"]
    names: set[str] = set()
    for key in ("devices", "caps", "resistors", "bipolars"):
        value = spec.get(key, [])
        names |= set(value if not isinstance(value, dict) else value)
    return names


UNDRAWN = sorted(_schematic_devices() - _manifest_devices())

skip_while_layout_stale = unittest.skipIf(
    bool(UNDRAWN),
    f"temp_core layout predates the DR-031 schematic ({len(UNDRAWN)} undrawn devices, "
    f"e.g. {', '.join(UNDRAWN[:3])}); redraw tracked in {TRACKING}",
)
