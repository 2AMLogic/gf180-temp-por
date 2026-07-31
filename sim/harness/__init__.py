"""gf180-temp-por simulation harness.

Reproducible ngspice + gf180mcu PVT corner running. Ported from the
gf180-bandgap sister repo's harness (their issue #2 / PR #23); the deliberate
divergences are recorded in
``spec/decision-records/DR-006-sim-harness-port.md``.

See sim/README.md for the evidence-record convention this harness produces.
"""

HARNESS_VERSION = "0.1.0"

__all__ = ["HARNESS_VERSION"]
