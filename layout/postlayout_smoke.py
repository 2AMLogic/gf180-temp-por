#!/usr/bin/env python3
"""Smoke-simulate every post-layout netlist at ``tt_27c_3.30v``.

    python3 layout/postlayout_smoke.py              # run all five, rewrite reports
    python3 layout/postlayout_smoke.py --cell temp_core
    python3 layout/postlayout_smoke.py --check      # committed reports current?

Needs ``ngspice`` and the gf180mcu PDK, both resolved through
``sim/harness/pdk.py`` so this uses exactly the install the corner runner uses.
Everything else under ``layout/`` runs without them.

**This is plumbing proof, not evidence.** It answers one question -- *does the
netlist ``layout/postlayout.py`` writes elaborate, converge, and settle where
the schematic does?* -- so the follow-on post-layout re-run issues debug
physics, not netlist plumbing. It is deliberately **not** a ``sim/`` record:

* one nominal PVT point, not the mandated matrix, so it substantiates nothing
  (``sim/README.md``: every recorded result carries the full PVT matrix);
* its bounds are loose sanity windows, not ratified spec limits, and are no
  substitute for the per-cell designer-check experiments under ``sim/``;
* it reports a *comparison against the schematic*, which is a plumbing check.

Each cell is run twice through a byte-identical deck: once on the post-layout
netlist and once on ``design/netlist/<cell>.spice``. The pair is the point. A
post-layout netlist whose body ties or net names landed on the wrong nodes
would still converge and still print numbers; only the side-by-side says
whether it is the same circuit. Where the two differ -- and on the one timing
measurement they do -- the difference is the drawn interconnect, which is
exactly what a post-layout netlist is for.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

LAYOUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAYOUT_DIR.parent

sys.path.insert(0, str(LAYOUT_DIR))
sys.path.insert(0, str(REPO_ROOT / "sim"))

import postlayout  # noqa: E402
from harness import corners as harness_corners  # noqa: E402
from harness import pdk as harness_pdk  # noqa: E402

#: The one PVT point. ``tt_27c_3.30v`` is the ratified nominal corner id
#: (``sim/README.md``); the section bundle is read from the harness's own
#: table so a corner definition cannot drift between this and a real run.
CORNER = harness_corners.CORNERS["tt"]
TEMP_C = 27.0
VDD = 3.30
CORNER_ID = f"{CORNER.name}_{TEMP_C:g}c_{VDD:.2f}v"

PREFIX = "m_"
VARIANTS = ("postlayout", "schematic")

#: Per-cell smoke deck. ``stimulus`` instantiates the cell under test as
#: ``xdut`` with the schematic's own port order -- which the post-layout
#: netlist reproduces, so one fragment drives both variants. ``measure`` is
#: ngspice ``let`` expressions; ``window`` is the loose sanity band each is
#: required to land in, and ``tolerance`` how far the two variants may differ.
SMOKE = {
    "bias_core": {
        "analyses": ["op"],
        "stimulus": [
            "vsup vdd 0 dc {vdd}",
            "vib nib ibias dc 0",
            "xdut vdd 0 nib vref bias_ok bias_core",
            "* IBIAS is a current output: mirror it into a diode-connected",
            "* load, exactly as sim/bias-core-designer-check/ does.",
            "xmld ibias ibias 0 0 nfet_03v3 L=2u W=2u nf=1 m=1",
        ],
        "measure": {
            "vref_v": "v(vref)",
            "bias_ok_v": "v(bias_ok)",
            "ibias_ua": "i(vib)*1e6",
            "pg_v": "v(xdut.pg)",
        },
        "window": {
            "vref_v": (0.9, 1.5),
            "bias_ok_v": (2.9, 3.31),
            "ibias_ua": (0.05, 5.0),
            "pg_v": (0.5, 3.31),
        },
        "tolerance": 0.02,
    },
    "por_comparator": {
        "analyses": ["op"],
        "stimulus": [
            "vsup vdd 0 dc {vdd}",
            "vok bias_ok 0 dc {vdd}",
            "vrefs vref 0 dc 1.2",
            "ibref vdd ibias dc 500n",
            "xdut vdd 0 ibias vref bias_ok por_raw por_comparator",
        ],
        "measure": {
            "por_raw_v": "v(por_raw)",
            # SNS/SNSB carry no drawn label, so they are positional in the
            # extraction ($10/$14). They are named here only because klt lvs's
            # correspondence put the schematic's name back -- which makes them
            # the sharpest check in this file: a mis-tied divider could not
            # reproduce the schematic's tap voltage to five digits.
            "sns_v": "v(xdut.sns)",
            "snsb_v": "v(xdut.snsb)",
        },
        "window": {
            "por_raw_v": (2.9, 3.31),
            "sns_v": (1.0, 2.5),
            "snsb_v": (0.05, 0.6),
        },
        "tolerance": 0.02,
    },
    "por_output_chain": {
        "analyses": [
            "tran 10u 20m",
            "meas tran trel when v(resetn)=1.65 rise=1 td=1.002m",
            "meas tran vrel find v(resetn) at=19.5m",
        ],
        "stimulus": [
            "vsup vdd 0 PWL(0 0 100u {vdd} 20m {vdd})",
            "vpr  por_raw 0 PWL(0 0 1m 0 1.002m {vdd} 20m {vdd})",
            "Bib vdd nib i='500n*min(1, max(0, (v(vdd)-1.5)/0.5))'",
            "vib nib ibias dc 0",
            "Cl resetn 0 5p",
            "Rl resetn 0 1T",
            "xdut vdd 0 ibias por_raw resetn por_output_chain",
        ],
        "measure": {
            # The deglitch + one-shot delay from POR_RAW rising to RESETn
            # releasing. This is the measurement the drawn interconnect
            # actually moves, so it is where the two variants are expected to
            # differ rather than agree.
            "t_release_ms": "(trel-1.002e-3)*1e3",
            "resetn_final_v": "vrel",
        },
        "window": {
            "t_release_ms": (0.05, 19.0),
            "resetn_final_v": (2.9, 3.31),
        },
        "tolerance": 0.15,
    },
    "temp_core": {
        "analyses": ["op"],
        "stimulus": [
            "vsup vdd 0 dc {vdd}",
            "ven  en  0 dc {vdd}",
            "ibref vdd ibias dc 500n",
            "Rlp ptat 0 1T",
            "Rlc ctat 0 1T",
            "xdut vdd 0 ibias en ptat ctat temp_core",
        ],
        "measure": {
            "ptat_v": "v(ptat)",
            "ctat_v": "v(ctat)",
            "pg_v": "v(xdut.pg)",
        },
        "window": {
            "ptat_v": (0.5, 2.5),
            "ctat_v": (0.3, 1.2),
            "pg_v": (0.5, 3.31),
        },
        "tolerance": 0.02,
    },
    "temp_por_top": {
        # The block is a timed element: a bare DC solve parks it in reset with
        # the sensor off, so the rail has to ramp. 30 ms covers the slowest
        # one-shot sim/por-output-chain-pulse/ measured.
        "analyses": [
            "tran 10u 30m",
            "meas tran trel when v(resetn)=1.65 rise=1 td=1.5m",
            "meas tran vrel find v(resetn) at=28m",
            "meas tran vptat find v(ptat) at=28m",
            "meas tran vctat find v(ctat) at=28m",
        ],
        "stimulus": [
            "vsup vdd 0 PWL(0 0 1m {vdd} 30m {vdd})",
            "Cp ptat 0 1p",
            "Cc ctat 0 1p",
            "Cr resetn 0 5p",
            "Rr resetn 0 1T",
            "xdut vdd 0 ptat ctat resetn temp_por_top",
        ],
        "measure": {
            "t_release_ms": "trel*1e3",
            "resetn_final_v": "vrel",
            "ptat_final_v": "vptat",
            "ctat_final_v": "vctat",
        },
        "window": {
            "t_release_ms": (1.0, 29.0),
            "resetn_final_v": (2.9, 3.31),
            "ptat_final_v": (0.5, 2.5),
            "ctat_final_v": (0.3, 1.2),
        },
        "tolerance": 0.15,
    },
}


class SmokeError(Exception):
    pass


def netlist_path(cell: str, variant: str) -> Path:
    if variant == "postlayout":
        return postlayout.OUT_DIR / f"{cell}.spice"
    return REPO_ROOT / "design" / "netlist" / f"{cell}.spice"


def compose_deck(cell: str, pdk, variant: str) -> str:
    smoke = SMOKE[cell]
    lines = [
        f"* {cell} {variant} smoke deck @ {CORNER_ID}",
        "* GENERATED by layout/postlayout_smoke.py -- do not edit.",
        "",
        f'.include "{pdk.design_include}"',
    ]
    for section in CORNER.sections:
        lines.append(f'.lib "{pdk.model_lib}" {section}')
    lines += [
        "",
        f".temp {TEMP_C}",
        ".options reltol=1e-5 abstol=1e-15 vntol=1e-9",
        "",
        f'.include "{netlist_path(cell, variant)}"',
        "",
    ]
    lines += [line.format(vdd=VDD) for line in smoke["stimulus"]]
    lines += ["", ".control", "set numdgt=10", "set noaskquit"]
    lines += [f"  {analysis}" for analysis in smoke["analyses"]]
    for name, expr in smoke["measure"].items():
        lines.append(f"  let {PREFIX}{name} = {expr}")
    for name in smoke["measure"]:
        lines.append(f"  print {PREFIX}{name}")
    lines += [".endc", ".end", ""]
    return "\n".join(lines)


def parse_prints(text: str, names) -> dict[str, float]:
    found: dict[str, float] = {}
    for line in text.splitlines():
        fields = line.replace("=", " ").split()
        if len(fields) < 2 or not fields[0].startswith(PREFIX):
            continue
        key = fields[0][len(PREFIX):]
        if key not in names:
            continue
        try:
            found[key] = float(fields[-1])
        except ValueError:
            continue
    missing = [name for name in names if name not in found]
    if missing:
        raise SmokeError(f"ngspice printed no value for {missing}")
    return found


def run_variant(cell: str, pdk, variant: str) -> dict[str, float]:
    deck = compose_deck(cell, pdk, variant)
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / f"{cell}.{variant}.spice"
        path.write_text(deck)
        proc = subprocess.run(
            ["ngspice", "-b", str(path)],
            capture_output=True, text=True, cwd=work,
        )
        if proc.returncode != 0:
            raise SmokeError(
                f"{cell}/{variant}: ngspice exited {proc.returncode}\n"
                f"{proc.stdout[-3000:]}\n{proc.stderr[-2000:]}"
            )
        return parse_prints(proc.stdout, SMOKE[cell]["measure"])


def run_cell(cell: str, pdk) -> dict:
    smoke = SMOKE[cell]
    results = {variant: run_variant(cell, pdk, variant) for variant in VARIANTS}
    rows = []
    ok = True
    for name in smoke["measure"]:
        post = results["postlayout"][name]
        schem = results["schematic"][name]
        low, high = smoke["window"][name]
        in_window = low <= post <= high
        delta = (post - schem) / schem if schem else (post - schem)
        agrees = abs(delta) <= smoke["tolerance"]
        ok = ok and in_window and agrees
        rows.append(
            {
                "measure": name,
                "postlayout": post,
                "schematic": schem,
                "delta_frac": delta,
                "window": [low, high],
                "in_window": in_window,
                "within_tolerance": agrees,
            }
        )
    return {
        "schema_version": 1,
        "cell": cell,
        "corner_id": CORNER_ID,
        "temp_c": TEMP_C,
        "vdd_v": VDD,
        "tolerance": smoke["tolerance"],
        "analyses": smoke["analyses"],
        "status": "pass" if ok else "fail",
        "note": "plumbing proof, not a sim/ evidence record -- one PVT point, "
                "loose sanity windows; see layout/postlayout_smoke.py",
        "netlists": {
            variant: str(netlist_path(cell, variant).relative_to(REPO_ROOT))
            for variant in VARIANTS
        },
        "measurements": rows,
    }


def smoke_markdown(reports: list[dict]) -> str:
    lines = [
        "# Post-layout smoke runs",
        "",
        f"<!-- {postlayout.HEADER_NOTE.replace('postlayout.py', 'postlayout_smoke.py')} -->",
        "",
        f"One nominal PVT point (`{CORNER_ID}`), each cell run twice through a",
        "byte-identical deck: the post-layout netlist, and the golden schematic",
        "netlist as a **control**. Not a `sim/` evidence record — see the",
        "module docstring of `layout/postlayout_smoke.py` for why.",
        "",
        "| cell | measure | post-layout | schematic | Δ | sanity window | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for report in reports:
        for row in report["measurements"]:
            verdict = "ok" if row["in_window"] and row["within_tolerance"] else "FAIL"
            lines.append(
                f"| `{report['cell']}` | `{row['measure']}` | "
                f"{row['postlayout']:.6g} | {row['schematic']:.6g} | "
                f"{row['delta_frac'] * 100:+.2f} % | "
                f"{row['window'][0]:g} … {row['window'][1]:g} | {verdict} |"
            )
    lines += [
        "",
        "## Reading the Δ column",
        "",
        "Δ ≈ 0 on a DC quantity is **not** a null result. The parasitic model",
        "is one series R into one lumped C per net, so a DC operating point is",
        "parasitic-invariant by construction; what Δ ≈ 0 proves is that the",
        "post-layout netlist is the *same circuit* — a mis-tied well, a",
        "floating MiM plate or a divider reattached to the wrong node could",
        "not reproduce the schematic's node voltages to six digits.",
        "",
        "The reset-release times are where the drawn interconnect actually",
        "bites, and they are the measurements a post-layout claim should be",
        "taken on.",
        "",
    ]
    return "\n".join(lines)


def report_path(cell: str) -> Path:
    return postlayout.REPORTS_DIR / cell / "postlayout-smoke.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cell", action="append", choices=postlayout.CELLS)
    parser.add_argument("--check", action="store_true",
                        help="re-run and require the committed reports to match")
    args = parser.parse_args(argv)
    cells = args.cell or list(postlayout.CELLS)

    try:
        pdk = harness_pdk.find_pdk()
    except harness_pdk.PdkNotFound as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    reports = []
    failures = []
    for cell in cells:
        try:
            report = run_cell(cell, pdk)
        except SmokeError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        reports.append(report)
        print(f"{report['status']:4} {cell} @ {CORNER_ID}")
        for row in report["measurements"]:
            print(
                f"       {row['measure']:<16} post={row['postlayout']:<14.6g} "
                f"schem={row['schematic']:<14.6g} "
                f"delta={row['delta_frac'] * 100:+.2f}%"
            )
        if report["status"] != "pass":
            failures.append(cell)

    artifacts = {report_path(r["cell"]): json.dumps(r, indent=2) + "\n"
                 for r in reports}
    if not args.cell:
        artifacts[postlayout.OUT_DIR / "SMOKE.md"] = smoke_markdown(reports)

    if args.check:
        stale = [
            path for path, text in artifacts.items()
            if not path.exists() or path.read_text() != text
        ]
        for path in sorted(stale):
            print(f"STALE {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        if stale or failures:
            return 1
        print(f"ok   {len(artifacts)} smoke artifact(s) are current")
        return 0

    for path, text in sorted(artifacts.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"ok   wrote {path.relative_to(REPO_ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
