#!/usr/bin/env python3
"""Build the layout cells under ``layout/cells/`` from a deterministic source.

    python3 layout/build_cells.py            # rebuild layout/cells/*.gds
    python3 layout/build_cells.py --check    # verify committed GDS are current
    python3 layout/build_cells.py --cell por_comparator_bias_okb_inv

Needs the ``klayout`` python module (``klt``'s own runtime dependency). If it is
not importable from the interpreter you run this with, use ``klt``'s:

    uv run --with klayout python3 layout/build_cells.py

Geometry is emitted as plain drawn rectangles on the gf180mcu drawn layers, at
coordinates written out in full below rather than produced by a PCell -- this is
the DRC/LVS **flow** bring-up (#16), not the block's real layout (#17/#18). What
matters here is that the cell is a verbatim piece of a real schematic in
``design/`` so the LVS compare has a golden netlist to answer to, and that the
stream is byte-reproducible so a recorded clean run can be re-run and re-checked.

GDS timestamps are suppressed (``gds2_write_timestamps = False``) -- without
that, two builds of identical geometry differ byte-for-byte and no committed
stream can ever be ``--check``ed.

Layers are the gf180mcu drawn layers ``klt``'s curated ``gf180mcu`` deck reads
(see ``layout/README.md`` for the deck's documented coverage limits):

    Nwell 21/0 · Comp 22/0 · Poly2 30/0 · Contact 33/0 · Metal1 34/0
    Metal1 pin/label purpose 34/10 (net names -> extracted pin names)
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAYOUT_DIR.parent
CELLS_DIR = LAYOUT_DIR / "cells"

DBU_UM = 0.001

NWELL = (21, 0)
COMP = (22, 0)
POLY2 = (30, 0)
CONTACT = (33, 0)
METAL1 = (34, 0)
METAL1_LABEL = (34, 10)

#: gf180mcu DRM "CO.1": contact is a fixed 0.22 x 0.22 um square.
CONTACT_SIDE_UM = 0.22


class CellBuilder:
    """Thin wrapper over ``klayout.db`` so a cell body reads as geometry."""

    def __init__(self, name: str) -> None:
        import klayout.db as kdb  # imported late: see the module docstring

        self._kdb = kdb
        self.layout = kdb.Layout()
        self.layout.dbu = DBU_UM
        self.cell = self.layout.create_cell(name)

    def _layer(self, spec: tuple[int, int]) -> int:
        return self.layout.layer(spec[0], spec[1])

    def box(self, spec, x0: float, y0: float, x1: float, y1: float) -> None:
        self.cell.shapes(self._layer(spec)).insert(
            self._kdb.DBox(x0, y0, x1, y1).to_itype(self.layout.dbu)
        )

    def contact(self, cx: float, cy: float) -> None:
        half = CONTACT_SIDE_UM / 2.0
        self.box(CONTACT, cx - half, cy - half, cx + half, cy + half)

    def label(self, name: str, x: float, y: float) -> None:
        self.cell.shapes(self._layer(METAL1_LABEL)).insert(
            self._kdb.DText(name, self._kdb.DTrans(self._kdb.DVector(x, y))).to_itype(
                self.layout.dbu
            )
        )

    def write(self, path: Path) -> None:
        options = self._kdb.SaveLayoutOptions()
        options.gds2_write_timestamps = False
        self.layout.write(str(path), options)


def por_comparator_bias_okb_inv(b: CellBuilder) -> None:
    """``por_comparator``'s local ``BIAS_OKB`` inverter (``MENP`` / ``MENN``).

    Two devices, verbatim from ``design/por_comparator.sch``:

        MENP  pfet 2/0.5 um   MENN  nfet 1/0.5 um

    -- the "local inverter producing ``BIAS_OKB``" row of
    ``design/por_comparator.md``'s device table. Both gates are the one drawn
    poly strip (``BIAS_OK``), both drains land on the one Metal1 strap
    (``BIAS_OKB``), sources go to the ``VDD`` / ``VSS`` straps.

    Floorplan (um), source column | gate | drain column::

        y=5.6  +--------- Nwell ----------+
        y=5.0  |  +----- PMOS Comp -----+ |     W = 2.0 um
        y=3.0  |  +---------------------+ |
        y=2.4  +--------------------------+
        y=2.0        [gate contact]              -> BIAS_OK
        y=1.0     +----- NMOS Comp -----+        W = 1.0 um
        y=0.0     +---------------------+
               x=0    0.5  1.0        1.8
                      |<L>|  L = 0.5 um
    """
    # Active. NMOS on field, PMOS in the well.
    b.box(COMP, 0.0, 0.0, 1.8, 1.0)
    b.box(COMP, 0.0, 3.0, 1.8, 5.0)
    b.box(NWELL, -0.6, 2.4, 2.4, 5.6)

    # One shared gate strip through both channels: L = 0.5 um.
    b.box(POLY2, 0.5, -0.3, 1.0, 5.3)

    b.contact(0.25, 0.5)  # NMOS source
    b.contact(1.40, 0.5)  # NMOS drain
    b.contact(0.25, 4.0)  # PMOS source
    b.contact(1.40, 4.0)  # PMOS drain
    b.contact(0.75, 2.0)  # shared gate

    b.box(METAL1, -0.60, 0.25, 0.45, 0.75)  # VSS strap
    b.box(METAL1, -0.60, 3.75, 0.45, 4.25)  # VDD strap
    b.box(METAL1, -0.60, 1.80, 0.95, 2.20)  # BIAS_OK  (gate)
    b.box(METAL1, 1.20, 0.20, 1.60, 4.30)  # BIAS_OKB (drains)

    b.label("VSS", 0.0, 0.5)
    b.label("VDD", 0.0, 4.0)
    b.label("BIAS_OK", 0.0, 2.0)
    b.label("BIAS_OKB", 1.4, 2.0)


#: cell name -> body. Add a cell here and it joins ``layout/run_checks.sh``.
CELLS = {
    "por_comparator_bias_okb_inv": por_comparator_bias_okb_inv,
}


def build(name: str, out_dir: Path) -> Path:
    builder = CellBuilder(name)
    CELLS[name](builder)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.gds"
    builder.write(path)
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(check: bool, only: str | None) -> int:
    names = [only] if only else sorted(CELLS)
    for name in names:
        if name not in CELLS:
            print(f"unknown cell {name!r} (have: {', '.join(sorted(CELLS))})")
            return 2

    if not check:
        for name in names:
            path = build(name, CELLS_DIR)
            print(f"wrote {path.relative_to(REPO_ROOT)}  sha256={sha256(path)[:16]}")
        return 0

    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            fresh = build(name, Path(tmp))
            committed = CELLS_DIR / f"{name}.gds"
            if not committed.exists():
                failures.append(f"{name}: not committed (run without --check)")
                continue
            if sha256(fresh) != sha256(committed):
                failures.append(
                    f"{name}: committed GDS is stale "
                    f"(committed {sha256(committed)[:16]}, "
                    f"rebuilt {sha256(fresh)[:16]})"
                )
            else:
                print(f"ok {name}.gds  sha256={sha256(committed)[:16]}")

    for line in failures:
        print(f"FAIL {line}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild into a temp dir and fail if the committed GDS differs",
    )
    parser.add_argument("--cell", help="build/check only this cell")
    args = parser.parse_args(argv)
    return run(args.check, args.cell)


if __name__ == "__main__":
    sys.exit(main())
