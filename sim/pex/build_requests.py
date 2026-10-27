#!/usr/bin/env python3
"""Stage `klt sim` request files that `klt pex` can re-point at an extracted DUT.

    python3 sim/pex/build_requests.py <outdir> <slug> [<slug> ...] [--temps -40 27 125]

WHY THIS EXISTS

`klt pex` re-runs a `klt sim` request twice: once as written (schematic DUT)
and once with only the DUT `.include` re-pointed at the netlist it extracted
from the layout. The harness's own testbenches do not have that shape -- each
`testbench/tb_<slug>.spice` is the stimulus fragment with the schematic
netlist pasted in verbatim -- so this script re-expresses the same
experiment as: stimulus fragment + one `.include "dut.spice"`.

It adds no measurement of its own. The deck is composed by the harness's own
`compose_deck`, taken apart by `klt_batch.translate_deck`, and staged by
`klt_batch._stage`, so the analysis, the `.meas` cards, the PVT grid and the
checks come from the experiment's committed `tb.json` unchanged.

MECHANICAL EDITS (all visible in the staged files)

1. The stimulus fragment is inlined into `body.spice` followed by one
   `.include "dut.spice"`; `dut.spice` is `design/netlist/temp_por_top.spice`
   unchanged. `sim/pex/measure.py` swaps that file per leg.
2. The supply is NOT a corner axis: one request per (temperature, supply),
   `.param vdd_val` a literal in the body. The batch fleet runs klt 0.7.0,
   whose `klt sim` silently drops `corners.params`, and 0.8.0 refuses
   `supply_v` on a `.param`; per-request literals need neither.
3. The harness's derived `let`/`print` rows (`m_<name>`, e.g. `v_hys_mv`) are
   re-expressed as `.meas tran <name> param='<expr>'` cards, because a klt
   `expr` measurement cannot read a `.meas` result.

The grid goes out as `klt sim` requests (one per temperature), never as a
hand-rolled ngspice loop.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "sim"))

from harness import corners as corners_mod  # noqa: E402
from harness import klt_batch, runner, testbench  # noqa: E402
from harness.pdk import find_pdk  # noqa: E402

SCHEMATIC = REPO / "design" / "netlist" / "temp_por_top.spice"


def stimulus_text(path: Path) -> str:
    return path.read_text() + '\n.include "dut.spice"\n'


def stage(slug: str, outdir: Path, temps: list[float] | None) -> list[Path]:
    pdk = find_pdk()
    tb = testbench.load(REPO / "sim" / slug / "testbench")
    exp = outdir / slug
    exp.mkdir(parents=True, exist_ok=True)
    stub = exp / "tb_pex.spice"
    stub.write_text(stimulus_text(tb.directory / "stimulus.spice"))
    tb = replace(tb, netlist=stub)

    corner_list = corners_mod.resolve_corners(list(tb.corners))
    supplies = corners_mod.supply_points(tb.nominal_supply_v, tb.supply_tolerance)
    points = corners_mod.build_grid(corner_list, temps or list(tb.temperatures_c), supplies)
    init = klt_batch.compat_init_lines()
    units = []
    for p in points:
        text = runner.compose_deck(tb, pdk, p)
        units.append(klt_batch.translate_deck(
            text, key=p.corner_id, log_path=exp / "unused.log", pdk=pdk, deck_dir=exp,
            lift_params=(), extra_init=init))
    cfg = klt_batch.BatchConfig(pdk=pdk, stage_root=exp / "req", evidence_dir=None)
    groups: dict[tuple, list] = {}
    for u in units:
        groups.setdefault(klt_batch._unit_group_key(u), []).append(u)
    out = []
    for members in groups.values():
        vdd = corners_mod.parse_corner_id(members[0].key)[2]
        name = f"T{members[0].temp_c:g}C_V{vdd}"
        req_path, request = klt_batch._stage(members, pdk, cfg, name)
        request["backend"] = "batch"
        if request["corners"].get("supply_v") or request.get("exclude"):
            raise SystemExit(f"{slug}: unexpected supply axis; vdd_val is a literal per request")
        for m in request["measurements"]:
            if "expr" in m:
                m["name"] = m["name"].removeprefix("m_")
                m["spice"] = f".meas tran {m['name']} param='{m.pop('expr')}'"
        req_path.write_text(json.dumps(request, indent=2) + "\n")
        # `klt pex` re-points the DUT `.include` in the request's own netlist,
        # so inline the stimulus stub (which holds that include) into body.spice
        body = req_path.parent / "body.spice"
        lines = body.read_text().splitlines()
        hit = [i for i, ln in enumerate(lines) if ln.strip().startswith(".include") and "tb_pex.spice" in ln]
        if len(hit) != 1:
            raise SystemExit(f"{body}: expected one include of tb_pex.spice, saw {len(hit)}")
        lines[hit[0]:hit[0] + 1] = stub.read_text().splitlines()
        body.write_text("\n".join(lines) + "\n")
        (req_path.parent / "dut.spice").write_text(SCHEMATIC.read_text())
        out.append(req_path)
        print(f"{slug}: {req_path.relative_to(outdir)} ({len(members)} corners)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("outdir", type=Path)
    ap.add_argument("slugs", nargs="+")
    ap.add_argument("--temps", type=float, nargs="+")
    a = ap.parse_args()
    for s in a.slugs:
        stage(s, a.outdir.resolve(), a.temps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
