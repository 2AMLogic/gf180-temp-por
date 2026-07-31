#!/usr/bin/env python3
"""run_devchar.py -- runner for issue #4's gf180mcu device-characterization
decks (pnp_vbe.spice, res_tc.spice, mos_vt_sub.spice).

Iterates corner x temperature (x device x polarity for the MOS deck), does
plain token substitution into each template deck, invokes ngspice -b,
parses the printed measurement values, and APPENDS rows to the CSV evidence
files under results/ (never truncates -- sim/ results are append-only
evidence per CLAUDE.md). Raw per-run ngspice output (Id-Vg curves, wrdata
dumps, full log) is preserved under results/raw/<run_id>/.

This script intentionally keeps zero device-specific knowledge inside the
.spice templates themselves (pure @@TOKEN@@ substitution) -- all the
corner/temperature/device sweep logic and NMOS/PMOS bias-network mirroring
lives here, so migrating onto the #2 harness later is a mechanical move of
this orchestration layer, not a rewrite of the decks.

Usage:
    python3 run_devchar.py [--pdk-root PATH] [--ngspice PATH] [--quick]

    --quick restricts the temperature grid to {-40, 27, 125} (the CLAUDE.md
    PVT-corner minimum) instead of the full 7-point grid, for a fast
    reproduction check.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = SCRIPT_DIR / "results"
RAW_DIR = RESULTS_DIR / "raw"

FULL_TEMPS = [-40, -15, 10, 27, 60, 90, 125]
QUICK_TEMPS = [-40, 27, 125]

PNP_CORNERS = ["bjt_typical", "bjt_ss", "bjt_ff"]
RES_CORNERS = ["res_typical", "res_ss", "res_ff"]
MOS_MAIN_CORNERS = ["typical", "ss", "ff", "fs", "sf"]

PNP_FIELDS = [
    "run_id", "timestamp_utc", "pdk_variant", "ngspice_version", "deck",
    "corner", "temp_c", "supply_V", "geometry", "par_effective", "bias_A",
    "vbe_V", "raw_ref",
]
RES_FIELDS = [
    "run_id", "timestamp_utc", "pdk_variant", "ngspice_version", "deck",
    "corner", "temp_c", "supply_V", "flavor", "r_length_um", "r_width_um",
    "resistance_ohm", "current_A", "raw_ref",
]
MOS_FIELDS = [
    "run_id", "timestamp_utc", "pdk_variant", "ngspice_version", "deck",
    "corner", "temp_c", "supply_V", "device", "polarity", "w_um", "l_um",
    "measurement", "vth_cc_V", "ss_mV_per_dec", "ion_A", "ion_vdd_V",
    "raw_ref",
]

# Nominal design rail this block is pinned to (DR-001: 3.3V +-10%). Not a
# per-run sweep variable for the PNP/resistor decks (see SUMMARY.md for the
# justification -- PNP bias is current-source-defined, resistor body model
# has r_vc1=r_vc2=0) but recorded on every row so "every recorded result
# states temp, corner, supply, PDK variant" holds literally, not just in
# prose.
NOMINAL_RAIL_V = 3.3
RES_TEST_V = 1.0


def utc_now_tag() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


@dataclass
class Env:
    pdk_root: Path
    ngspice: str
    pdk_variant: str = "gf180mcuD"
    ngspice_version: str = ""
    volare_commit: str = ""

    @property
    def model_dir(self) -> Path:
        return self.pdk_root / self.pdk_variant / "libs.tech" / "ngspice"


def resolve_env(args) -> Env:
    pdk_root = Path(args.pdk_root or os.environ.get("PDK_ROOT") or os.path.expanduser("~/.volare"))
    ngspice = args.ngspice or "ngspice"
    env = Env(pdk_root=pdk_root, ngspice=ngspice)

    model_file = env.model_dir / "sm141064.ngspice"
    if not model_file.exists():
        sys.exit(
            f"FATAL: model file not found at {model_file}\n"
            f"Set --pdk-root or $PDK_ROOT to the volare install root "
            f"(directory containing gf180mcuD/...)."
        )

    ver = sh([ngspice, "-v"])
    m = re.search(r"ngspice-(\S+)", ver.stdout + ver.stderr)
    env.ngspice_version = m.group(1) if m else "unknown"

    # volare symlinks gf180mcuD -> volare/gf180mcu/versions/<commit>/gf180mcuD
    link = env.pdk_root / env.pdk_variant
    if link.is_symlink():
        target = os.readlink(link)
        m = re.search(r"versions/([0-9a-f]{6,40})/", target)
        if m:
            env.volare_commit = m.group(1)

    return env


def run_deck(env: Env, template: Path, tokens: dict, raw_stem: str, run_dir: Path) -> str:
    """Substitute tokens into template, run ngspice -b, return stdout."""
    text = template.read_text()
    for k, v in tokens.items():
        text = text.replace(f"@@{k}@@", str(v))
    if "@@" in text:
        leftover = re.findall(r"@@\w+@@", text)
        raise RuntimeError(f"Unsubstituted tokens in {template.name}: {leftover}")

    run_dir.mkdir(parents=True, exist_ok=True)
    net_path = run_dir / f"{raw_stem}.spice"
    net_path.write_text(text)

    proc = sh([env.ngspice, "-b", str(net_path)])
    log_path = run_dir / f"{raw_stem}.log"
    log_path.write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr)

    bad = [
        line for line in (proc.stdout + proc.stderr).splitlines()
        if re.search(r"unknown (model|subckt)", line, re.IGNORECASE)
    ]
    if bad:
        raise RuntimeError(f"{raw_stem}: unknown model/subckt warning(s): {bad}")

    return proc.stdout


class CsvWriter:
    def __init__(self, path: Path, fields: list[str]):
        self.path = path
        self.fields = fields
        self._new = not path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "a", newline="")
        self._w = csv.DictWriter(self._fh, fieldnames=fields)
        if self._new:
            self._w.writeheader()

    def write(self, row: dict):
        self._w.writerow(row)

    def close(self):
        self._fh.close()


# ---------------------------------------------------------------------------
# PNP deck
# ---------------------------------------------------------------------------

PNP_RESULT_RE = re.compile(
    r"PNP_RESULT g1=(?P<g1>\S+) g2=(?P<g2>\S+) g3=(?P<g3>\S+) g4=(?P<g4>\S+) "
    r"i1=(?P<i1>\S+) i3=(?P<i3>\S+) r1u=(?P<r1u>\S+) r1n=(?P<r1n>\S+) "
    r"r2u=(?P<r2u>\S+) r2n=(?P<r2n>\S+)"
)


def run_pnp(env: Env, temps, run_id: str, ts: str, csvw: CsvWriter, records: list):
    template = SCRIPT_DIR / "pnp_vbe.spice"
    for corner in PNP_CORNERS:
        for temp in temps:
            stem = f"pnp_{corner}_{temp}"
            run_dir = RAW_DIR / run_id / "pnp"
            raw_data_file = run_dir / f"{stem}.wrdata"
            tokens = {
                "PDK_ROOT": env.pdk_root,
                "CORNER": corner,
                "TEMP": temp,
                "RAWTAG": raw_data_file,
            }
            out = run_deck(env, template, tokens, stem, run_dir)
            m = PNP_RESULT_RE.search(out)
            if not m:
                raise RuntimeError(f"PNP deck {stem}: could not parse PNP_RESULT line:\n{out}")
            vals = {k: float(v) for k, v in m.groupdict().items()}
            records.append({"corner": corner, "temp": temp, **vals})

            rows = [
                ("pnp_10p00x10p00", "x1", 10e-6, vals["g1"]),
                ("pnp_05p00x05p00", "x1", 10e-6, vals["g2"]),
                ("pnp_10p00x00p42", "x1", 10e-6, vals["g3"]),
                ("pnp_05p00x00p42", "x1", 10e-6, vals["g4"]),
                ("pnp_10p00x10p00", "x1", 1e-6, vals["i1"]),
                ("pnp_10p00x10p00", "x1", 100e-6, vals["i3"]),
                ("pnp_10p00x10p00", "ratio8_unit(x1)", 10e-6, vals["r1u"]),
                ("pnp_10p00x10p00", "ratio8_par(x8)", 10e-6, vals["r1n"]),
                ("pnp_10p00x10p00", "ratio4_unit(x1)", 10e-6, vals["r2u"]),
                ("pnp_10p00x10p00", "ratio4_par(x4)", 10e-6, vals["r2n"]),
            ]
            for geometry, par_eff, bias, vbe in rows:
                csvw.write({
                    "run_id": run_id, "timestamp_utc": ts,
                    "pdk_variant": env.pdk_variant,
                    "ngspice_version": env.ngspice_version,
                    "deck": "pnp_vbe.spice", "corner": corner, "temp_c": temp,
                    "supply_V": NOMINAL_RAIL_V,
                    "geometry": geometry, "par_effective": par_eff,
                    "bias_A": bias, "vbe_V": f"{vbe:.6f}",
                    "raw_ref": str(raw_data_file.relative_to(SCRIPT_DIR)),
                })


# ---------------------------------------------------------------------------
# Resistor deck
# ---------------------------------------------------------------------------

RES_RESULT_RE = re.compile(
    r"RES_RESULT ppu=(?P<ppu>\S+) ppu1k=(?P<ppu1k>\S+) ppu2k=(?P<ppu2k>\S+) "
    r"ppu3k=(?P<ppu3k>\S+) npu=(?P<npu>\S+) ppl=(?P<ppl>\S+) npf=(?P<npf>\S+) "
    r"nw=(?P<nw>\S+)"
)

RES_FLAVOR_MAP = {
    "ppu": "ppolyf_u", "ppu1k": "ppolyf_u_1k", "ppu2k": "ppolyf_u_2k",
    "ppu3k": "ppolyf_u_3k", "npu": "nplus_u", "ppl": "pplus_u",
    "npf": "npolyf_u", "nw": "nwell",
}


def run_res(env: Env, temps, run_id: str, ts: str, csvw: CsvWriter, records: list):
    template = SCRIPT_DIR / "res_tc.spice"
    for corner in RES_CORNERS:
        for temp in temps:
            stem = f"res_{corner}_{temp}"
            run_dir = RAW_DIR / run_id / "res"
            raw_data_file = run_dir / f"{stem}.wrdata"
            tokens = {
                "PDK_ROOT": env.pdk_root,
                "CORNER": corner,
                "TEMP": temp,
                "RAWTAG": raw_data_file,
            }
            out = run_deck(env, template, tokens, stem, run_dir)
            m = RES_RESULT_RE.search(out)
            if not m:
                raise RuntimeError(f"RES deck {stem}: could not parse RES_RESULT line:\n{out}")
            currents = {k: abs(float(v)) for k, v in m.groupdict().items()}
            records.append({"corner": corner, "temp": temp, **currents})

            for key, flavor in RES_FLAVOR_MAP.items():
                i = currents[key]
                r = 1.0 / i if i else float("nan")
                csvw.write({
                    "run_id": run_id, "timestamp_utc": ts,
                    "pdk_variant": env.pdk_variant,
                    "ngspice_version": env.ngspice_version,
                    "deck": "res_tc.spice", "corner": corner, "temp_c": temp,
                    "supply_V": RES_TEST_V,
                    "flavor": flavor, "r_length_um": 50, "r_width_um": 2,
                    "resistance_ohm": f"{r:.4f}", "current_A": f"{i:.6e}",
                    "raw_ref": str(raw_data_file.relative_to(SCRIPT_DIR)),
                })


# ---------------------------------------------------------------------------
# MOS deck
# ---------------------------------------------------------------------------

MOS_MEAS_RE = re.compile(
    r"vth_cc\s*=\s*(?P<vth>[-\d.eE+]+).*?"
    r"vg_sshi\s*=\s*(?P<sshi>[-\d.eE+]+).*?"
    r"vg_sslo\s*=\s*(?P<sslo>[-\d.eE+]+)",
    re.DOTALL,
)
MOS_ION_RE = re.compile(r"MOS_ION ion=(?P<ion>\S+)")


@dataclass
class MosDevice:
    name: str
    polarity: str  # "n" or "p"
    w_um: float
    l_um: float
    vg_lo: float  # sweep low bound (absolute node voltage)
    vg_hi: float  # sweep high bound (absolute node voltage)
    ion_rail: float  # rail used for the Ion op point / supply-sweep base


MOS_DEVICES_MAIN = [
    MosDevice("nfet_03v3", "n", 10, 1, 0, 3.3, 3.3),
    MosDevice("pfet_03v3", "p", 10, 1, 0, 3.3, 3.3),
    MosDevice("nfet_06v0_nvt", "n", 10, 1.8, -1, 2, 3.3),
]
MOS_DEVICES_TYPICAL_ONLY = [
    MosDevice("nfet_06v0", "n", 10, 1, 0, 6.0, 6.0),
    MosDevice("pfet_06v0", "p", 10, 1, 0, 6.0, 6.0),
    MosDevice("nfet_05v0", "n", 10, 1, 0, 5.0, 5.0),
    MosDevice("pfet_05v0", "p", 10, 1, 0, 5.0, 5.0),
]
SUPPLY_SWEEP_RAILS = [2.97, 3.30, 3.63]  # DR-001: 3.3V +-10%


def mos_tokens(env: Env, dev: MosDevice, corner: str, temp, vdd_ion: float, raw_tag: Path) -> dict:
    wl = dev.w_um / dev.l_um
    target = 1e-7 * wl  # 100nA * (W/L), constant-current Vt definition
    sshi = target * 1e-2
    sslo = target * 1e-3
    sign = -1 if dev.polarity == "n" else 1

    if dev.polarity == "n":
        body, vs, vd_lowfield = "0", 0, 0.05
        vg_start, vg_stop, vg_step = dev.vg_lo, dev.vg_hi, 0.005
        body_ion, vg_ion, vd_ion, vs_ion = "0", vdd_ion, vdd_ion, 0
    else:
        body, vs, vd_lowfield = "s", dev.vg_hi, dev.vg_hi - 0.05
        vg_start, vg_stop, vg_step = dev.vg_hi, dev.vg_lo, -0.005
        body_ion, vg_ion, vd_ion, vs_ion = "sion", 0, 0, vdd_ion

    return {
        "PDK_ROOT": env.pdk_root, "CORNER": corner, "TEMP": temp,
        "DEVICE": dev.name, "WVAL": f"{dev.w_um}u", "LVAL": f"{dev.l_um}u",
        "BODY": body, "VS": vs, "VD_LOWFIELD": vd_lowfield,
        "VG_START": vg_start, "VG_STOP": vg_stop, "VG_STEP": vg_step,
        "ITARGET_VT": sign * target, "ITARGET_SSHI": sign * sshi,
        "ITARGET_SSLO": sign * sslo,
        "BODY_ION": body_ion, "VG_ION": vg_ion, "VD_ION": vd_ion, "VS_ION": vs_ion,
        "RAWTAG": raw_tag,
    }


def run_one_mos(env, dev, corner, temp, vdd_ion, run_id, ts, csvw, tag_suffix=""):
    template = SCRIPT_DIR / "mos_vt_sub.spice"
    stem = f"mos_{dev.name}_{corner}_{temp}{tag_suffix}"
    run_dir = RAW_DIR / run_id / "mos"
    raw_data_file = run_dir / f"{stem}.wrdata"
    tokens = mos_tokens(env, dev, corner, temp, vdd_ion, raw_data_file)
    out = run_deck(env, template, tokens, stem, run_dir)

    m_meas = MOS_MEAS_RE.search(out)
    m_ion = MOS_ION_RE.search(out)
    if not (m_meas and m_ion):
        raise RuntimeError(f"MOS deck {stem}: could not parse measure/ion output:\n{out}")

    vth = float(m_meas.group("vth"))
    sshi = float(m_meas.group("sshi"))
    sslo = float(m_meas.group("sslo"))
    ion = abs(float(m_ion.group("ion")))
    ss_mv_dec = abs(sshi - sslo) * 1000.0
    vgs_th = vth - (dev.vg_hi if dev.polarity == "p" else 0.0)

    csvw.write({
        "run_id": run_id, "timestamp_utc": ts, "pdk_variant": env.pdk_variant,
        "ngspice_version": env.ngspice_version, "deck": "mos_vt_sub.spice",
        "corner": corner, "temp_c": temp, "supply_V": vdd_ion,
        "device": dev.name,
        "polarity": dev.polarity, "w_um": dev.w_um, "l_um": dev.l_um,
        "measurement": "vt_subthreshold" + tag_suffix,
        "vth_cc_V": f"{vgs_th:.6f}", "ss_mV_per_dec": f"{ss_mv_dec:.3f}",
        "ion_A": f"{ion:.6e}", "ion_vdd_V": vdd_ion,
        "raw_ref": str(raw_data_file.relative_to(SCRIPT_DIR)),
    })
    return vgs_th, ss_mv_dec, ion


def run_mos(env: Env, temps, run_id: str, ts: str, csvw: CsvWriter, records: list):
    for dev in MOS_DEVICES_MAIN:
        for corner in MOS_MAIN_CORNERS:
            for temp in temps:
                vgs_th, ss, ion = run_one_mos(env, dev, corner, temp, dev.ion_rail, run_id, ts, csvw)
                records.append({"device": dev.name, "corner": corner, "temp": temp,
                                 "vgs_th": vgs_th, "ss": ss, "ion": ion})

    for dev in MOS_DEVICES_TYPICAL_ONLY:
        for temp in temps:
            run_one_mos(env, dev, "typical", temp, dev.ion_rail, run_id, ts, csvw)

    # Supply-dependence subset (DR-001: 3.3V +-10%), 27C, typical corner,
    # the two 3.3V-rail devices that are actual signal-path candidates.
    for dev in [d for d in MOS_DEVICES_MAIN if d.name in ("nfet_03v3", "pfet_03v3")]:
        for vdd in SUPPLY_SWEEP_RAILS:
            run_one_mos(env, dev, "typical", 27, vdd, run_id, ts, csvw,
                        tag_suffix=f"_supply{vdd}")


# ---------------------------------------------------------------------------
# Derived-metrics report (physics sanity anchors)
# ---------------------------------------------------------------------------

def linfit_slope(xs, ys):
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den


def write_derived_report(pnp_records, res_records, mos_records, out_path: Path):
    lines = []
    lines.append("# Derived metrics (auto-generated by run_devchar.py)")
    lines.append("")

    # --- PNP physics sanity anchors ---
    lines.append("## PNP")
    typ = [r for r in pnp_records if r["corner"] == "bjt_typical"]
    r27 = next(r for r in typ if r["temp"] == 27)
    lines.append(f"- VBE(27C, typical, pnp_10p00x10p00, x1, 10uA) = {r27['g1']:.6f} V")
    xs = [r["temp"] for r in typ]
    ys = [r["g1"] for r in typ]
    slope = linfit_slope(xs, ys)
    lines.append(f"- dVBE/dT (typical, pnp_10p00x10p00, x1, 10uA, linear fit over "
                  f"{min(xs)}..{max(xs)} C) = {slope * 1000:.4f} mV/C")

    import math
    k = 1.380649e-23
    q = 1.602176634e-19
    T = 27 + 273.15
    vt = k * T / q
    dvbe8 = r27["r1u"] - r27["r1n"]
    dvbe4 = r27["r2u"] - r27["r2n"]
    lines.append(f"- delta-VBE(27C, typical, 8:1 ratio) = {dvbe8 * 1000:.3f} mV "
                 f"(Vt*ln(8) = {vt * math.log(8) * 1000:.3f} mV, "
                 f"error = {(dvbe8 - vt * math.log(8)) / (vt * math.log(8)) * 100:.2f}%)")
    lines.append(f"- delta-VBE(27C, typical, 4:1 ratio) = {dvbe4 * 1000:.3f} mV "
                 f"(Vt*ln(4) = {vt * math.log(4) * 1000:.3f} mV, "
                 f"error = {(dvbe4 - vt * math.log(4)) / (vt * math.log(4)) * 100:.2f}%)")

    for corner in PNP_CORNERS:
        cs = [r for r in pnp_records if r["corner"] == corner]
        c40 = next(r for r in cs if r["temp"] == min(xs))
        c125 = next(r for r in cs if r["temp"] == max(xs))
        span = c125["temp"] - c40["temp"]
        lines.append(f"- {corner}: VBE({min(xs)}C)={c40['g1']:.4f}V, "
                     f"VBE({max(xs)}C)={c125['g1']:.4f}V, "
                     f"avg dVBE/dT={((c125['g1'] - c40['g1']) / span) * 1000:.4f} mV/C")

    # --- Resistor corner-spread / TC ---
    lines.append("")
    lines.append("## Resistors")
    for key, flavor in RES_FLAVOR_MAP.items():
        row = []
        for corner in RES_CORNERS:
            cs = [r for r in res_records if r["corner"] == corner]
            c27 = next(r for r in cs if r["temp"] == 27)
            i = c27[key]
            r = 1.0 / i
            row.append((corner, r))
        lines.append(f"- {flavor}: " + ", ".join(f"{c}={r:.1f} ohm" for c, r in row))
        # TC from typical corner endpoints
        cs = [r for r in res_records if r["corner"] == "res_typical"]
        c_lo = next(r for r in cs if r["temp"] == min(xs))
        c_hi = next(r for r in cs if r["temp"] == max(xs))
        c_27 = next(r for r in cs if r["temp"] == 27)
        r_lo, r_hi, r_27 = 1.0 / c_lo[key], 1.0 / c_hi[key], 1.0 / c_27[key]
        span = c_hi["temp"] - c_lo["temp"]
        tc_ppm = (r_hi - r_lo) / (r_27 * span) * 1e6
        lines.append(f"    typical TC ({min(xs)}..{max(xs)} C, endpoint) = {tc_ppm:.1f} ppm/C")

    # --- MOS Vt / SS summary ---
    lines.append("")
    lines.append("## MOS")
    for dev_name in sorted({r["device"] for r in mos_records}):
        cs = [r for r in mos_records if r["device"] == dev_name]
        typ_rows = [r for r in cs if r["corner"] == "typical"]
        if not typ_rows:
            continue
        r27 = next((r for r in typ_rows if r["temp"] == 27), None)
        if r27 is None:
            continue
        lines.append(f"- {dev_name}: Vt(27C,typical)={r27['vgs_th']:.4f} V, "
                     f"SS(27C,typical)={r27['ss']:.2f} mV/dec, "
                     f"Ion(27C,typical)={r27['ion']:.4e} A")
        temps_present = sorted({r["temp"] for r in typ_rows})
        if len(temps_present) > 1:
            t_lo, t_hi = min(temps_present), max(temps_present)
            r_lo = next(r for r in typ_rows if r["temp"] == t_lo)
            r_hi = next(r for r in typ_rows if r["temp"] == t_hi)
            dvt = (r_hi["vgs_th"] - r_lo["vgs_th"]) / (t_hi - t_lo) * 1000
            lines.append(f"    dVt/dT ({t_lo}..{t_hi} C) = {dvt:.4f} mV/C")
        for corner in MOS_MAIN_CORNERS:
            crows = [r for r in cs if r["corner"] == corner and r["temp"] == 27]
            if crows:
                lines.append(f"    {corner}: Vt(27C)={crows[0]['vgs_th']:.4f} V")

    out_path.write_text("\n".join(lines) + "\n")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdk-root")
    ap.add_argument("--ngspice")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    env = resolve_env(args)
    temps = QUICK_TEMPS if args.quick else FULL_TEMPS
    run_id = utc_now_tag()
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    print(f"run_id={run_id} pdk_variant={env.pdk_variant} "
          f"volare_commit={env.volare_commit or 'unknown'} "
          f"ngspice={env.ngspice_version} pdk_root={env.pdk_root} temps={temps}")

    pnp_records, res_records, mos_records = [], [], []

    pnp_csv = CsvWriter(RESULTS_DIR / "pnp_vbe.csv", PNP_FIELDS)
    try:
        run_pnp(env, temps, run_id, ts, pnp_csv, pnp_records)
    finally:
        pnp_csv.close()
    print(f"PNP: {len(pnp_records)} corner/temp points recorded")

    res_csv = CsvWriter(RESULTS_DIR / "res_tc.csv", RES_FIELDS)
    try:
        run_res(env, temps, run_id, ts, res_csv, res_records)
    finally:
        res_csv.close()
    print(f"RES: {len(res_records)} corner/temp points recorded")

    mos_csv = CsvWriter(RESULTS_DIR / "mos_vt_sub.csv", MOS_FIELDS)
    try:
        run_mos(env, temps, run_id, ts, mos_csv, mos_records)
    finally:
        mos_csv.close()
    print(f"MOS: {len(mos_records)} corner/temp/device points recorded")

    report = write_derived_report(
        pnp_records, res_records, mos_records,
        RESULTS_DIR / f"derived_metrics_{run_id}.md",
    )
    print()
    print(report)


if __name__ == "__main__":
    main()
