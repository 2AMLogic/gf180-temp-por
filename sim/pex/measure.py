#!/usr/bin/env python3
"""`klt pex --measure-command` driver for temp_por_top.

    klt pex layout/cells/temp_por_top.gds --deck gf180mcu --pdk gf180mcuD \\
        --pins VDD,VSS,PTAT,CTAT,RESETn --rename-declared-pins \\
        --reference-netlist design/netlist/temp_por_top.spice \\
        --measure-command 'python3 sim/pex/measure.py --stage-root DIR slug...'

`klt pex` runs this twice (schematic leg, extracted leg), appending the
netlist under measurement as the last argument. For each slug it swaps that
netlist in as `dut.spice` of the staged `klt sim` requests
(`sim/pex/build_requests.py`) and submits them with `klt sim`, honouring
`$KLT_SIM_BACKEND` (set by `klt pex --backend`). It never runs ngspice itself.
The measurement document it prints is the `klt sim` responses' corners,
corner ids prefixed with the slug.

THE EXTRACTED LEG IS PATCHED -- these are the whole of the edits, and they are
needed because klt's gf180mcu deck extracts devices that the PDK models do not
accept as written:

1. The `.SUBCKT temp_por_top` header lists the same pins in the schematic's
   order (the stimulus instantiates the DUT positionally).
2. Each extracted `Q... bjt` card (the deck has one generic bipolar class and
   cannot name the PDK device) becomes `XQ... c b e pnp_10p00x10p00`, the
   model the schematic uses, after checking AE=100P (10 um x 10 um).
3. The Nwell / bipolar-base nets that `klt pex` reports under
   `body_bias.unbiased_nets` (and the bipolar base nets) have no DC path in
   the extraction. Each gets a 0 V source to the net the schematic puts that
   well on -- `layout/postlayout.py:body_ties()`, derived from the golden
   reference -- with the layout net found through a `klt lvs` net
   correspondence. The tie list is printed to stderr.

`klt pex` still reports `body_bias.status` for the *unpatched* extraction; the
ties here are what make the comparison simulable, not a claim that the drawn
layout biases those wells.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "layout"))

SCH_PINS = ["VDD", "VSS", "PTAT", "CTAT", "RESETn"]
PDK_BJT = "pnp_10p00x10p00"


def die(msg: str) -> "NoReturn":  # noqa: F821
    print(f"measure.py: {msg}", file=sys.stderr)
    raise SystemExit(2)


def logical_cards(text: str) -> list[list[str]]:
    """Physical lines grouped so a `+` continuation stays with its card."""
    groups: list[list[str]] = []
    for line in text.splitlines():
        if line.startswith("+") and groups:
            groups[-1].append(line)
        else:
            groups.append([line])
    return groups


def lvs_correspondence(klt: str) -> dict[str, str]:
    """reference net (upper-case) -> layout net, from `klt lvs` on the top cell."""
    req = REPO / "layout" / "cells" / "temp_por_top.lvs.json"
    proc = subprocess.run([klt, "lvs", str(req), "--format", "json"],
                          capture_output=True, text=True)
    try:
        doc = json.loads(proc.stdout)
    except json.JSONDecodeError:
        die(f"klt lvs gave no JSON: {proc.stderr[-400:]}")
    if doc.get("status") != "match":
        die(f"klt lvs status {doc.get('status')!r}, expected match")
    return {e["reference"].upper(): e["layout"] for e in doc["net_correspondence"]}


def patch_extracted(text: str, klt: str) -> tuple[str, list[str]]:
    import postlayout  # layout/postlayout.py

    ties = {k: v for k, v in postlayout.body_ties("temp_por_top").items() if k != "vsubs"}
    expected_model = postlayout.bipolar_model("temp_por_top")
    if expected_model != PDK_BJT:
        die(f"schematic bipolar is {expected_model}, wrapper is written for {PDK_BJT}")
    ref_to_layout = lvs_correspondence(klt)

    def layout_net(ref_name: str) -> str:
        key = ref_name.upper().replace(".", "_")
        if key in ("VDD", "VSS"):
            return key
        if key not in ref_to_layout:
            die(f"no layout net corresponds to {ref_name} ({key})")
        return ref_to_layout[key]

    out: list[str] = []
    seen_header = False
    bjt_count = 0
    bjt_bases: list[str] = []
    tie_lines: list[str] = []
    report: list[str] = []
    for card in logical_cards(text):
        head = card[0]
        if re.match(r"^\.subckt\s+temp_por_top\b", head, re.I):
            pins = head.split()[2:]
            if sorted(p.upper() for p in pins) != sorted(p.upper() for p in SCH_PINS):
                die(f"extracted pin set {pins} != schematic {SCH_PINS}")
            card = [".SUBCKT temp_por_top " + " ".join(SCH_PINS)]
            seen_header = True
        elif re.match(r"^q", head, re.I):
            joined = " ".join(c.lstrip("+").strip() for c in card)
            m = re.match(r"^(Q\S*)\s+(\S+)\s+(\S+)\s+(\S+)\s+bjt\s+(.*)$", joined, re.I)
            if not m or not re.search(r"\bAE=100P\b", m.group(5), re.I):
                die(f"unexpected bipolar card (need `bjt` with AE=100P): {joined[:160]}")
            name, c, b, e, _rest = m.groups()
            bjt_bases.append(b)
            card = [f"X{name} {c} {b} {e} {PDK_BJT} m=1"]
            bjt_count += 1
        elif re.match(r"^\.ends\b", head, re.I) and seen_header and not tie_lines:
            for key, target in sorted(ties.items()):
                if key.upper().replace(".", "_") not in ref_to_layout:
                    # No layout net of its own: the LVS merged this well into
                    # its target net (xtemp's bipolar bases sit on VSS). The
                    # base-net check below proves it for every bipolar.
                    if target not in ("VDD", "VSS"):
                        die(f"{key} has no layout net and target {target} is not a rail")
                    report.append(f"{key}: no net of its own in the layout (merged into {target})")
                    continue
                well = layout_net(key)
                tgt = layout_net(target)
                tie_lines.append(f"Vtie_{len(tie_lines)} {well} {tgt} 0")
                report.append(f"{key}: {well} -> {target} ({tgt})")
            out.extend(tie_lines)
        out.extend(card)
    if not seen_header:
        die("no `.SUBCKT temp_por_top` in the extracted netlist")
    if bjt_count == 0:
        die("no bipolar cards found in the extracted netlist")
    tied = {line.split()[1] for line in tie_lines}
    for b in bjt_bases:
        if b not in tied and not re.match(r"^VSS(__t\d+)?$", b):
            die(f"bipolar base {b} is neither a tied well nor on the VSS net")
    report.append(f"{bjt_count} bipolar cards -> {PDK_BJT}")
    return "\n".join(out) + "\n", report


def run_leg(slug_dir: Path, work: Path, dut_text: str, backend: str | None, klt: str) -> list[dict]:
    corners: list[dict] = []
    for req_dir in sorted(p for p in (slug_dir / "req").iterdir() if p.is_dir()):
        w = work / req_dir.name
        if w.exists():
            shutil.rmtree(w)
        shutil.copytree(req_dir, w, ignore=shutil.ignore_patterns("klt"))
        (w / "dut.spice").write_text(dut_text)
        req = json.loads((w / "request.json").read_text())
        if backend:
            req["backend"] = backend
        (w / "request.json").write_text(json.dumps(req, indent=2) + "\n")
        cmd = [klt, "sim", str(w / "request.json"), "-o", str(w / "klt"), "--format", "json"]
        if backend:
            cmd += ["--backend", backend]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        try:
            doc = json.loads(proc.stdout)
        except json.JSONDecodeError:
            die(f"klt sim on {w.name} gave no JSON (rc={proc.returncode}): {proc.stderr[-600:]}")
        if "error" in doc and "corners" not in doc:
            die(f"klt sim on {w.name}: {json.dumps(doc['error'])[:600]}")
        if backend == "batch" and not (doc.get("environment") or {}).get("remote"):
            die(f"{w.name}: report carries no environment.remote -- not executed on the fleet")
        (w / "report.json").write_text(json.dumps(doc, indent=1) + "\n")
        for c in doc["corners"]:
            corners.append({
                "corner_id": f"{slug_dir.name}/{c['corner_id']}",
                "measurements": [
                    {"name": m["name"], "value": m.get("value"), "status": m.get("status")}
                    for m in c.get("measurements", [])
                ],
            })
    return corners


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage-root", type=Path, required=True)
    ap.add_argument("--klt", default=os.environ.get("KLT", "klt"))
    ap.add_argument("slugs", nargs="+")
    ap.add_argument("netlist", type=Path)
    a = ap.parse_args()

    side = os.environ.get("KLT_PEX_SIDE")
    art = Path(os.environ.get("KLT_PEX_ARTIFACTS_DIR", "."))
    backend = os.environ.get("KLT_SIM_BACKEND") or None
    text = a.netlist.read_text()
    if side == "extracted":
        text, report = patch_extracted(text, a.klt)
        (art / "extracted-patched.spice").write_text(text)
        print("extracted-leg patches:\n  " + "\n  ".join(report), file=sys.stderr)
    elif side != "schematic":
        die(f"KLT_PEX_SIDE={side!r}")

    corners: list[dict] = []
    for slug in a.slugs:
        corners += run_leg(a.stage_root.resolve() / slug, art / slug, text, backend, a.klt)
    json.dump({"corners": corners}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
