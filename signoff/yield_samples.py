#!/usr/bin/env python3
"""Re-express the committed Monte Carlo campaigns as `klt yield` sample sets.

    python3 signoff/yield_samples.py            # write signoff/evidence/yield/*.samples.json
    python3 signoff/yield_samples.py --check    # fail if the committed sample sets are stale

T1 item 6 asks for a `klt yield` report per statistical spec row. The N=500
per-binding-point Monte Carlo campaigns already exist as raw ngspice logs
(`sim/<experiment>/corners/<record-id>/`, one file per binding point x
sample), so nothing is re-simulated here: this reads those logs through the
harness's own parser, re-applies the harness's own derive hook for the trimmed
temperature error, and writes one sample-set document per campaign in the
shape `klt yield` consumes (`{"measurements": [{name, samples, limits}]}`).

Limits come from each campaign's own `tb.json` `checks` block -- the ratified
row limits -- and are never edited here. `target_yield` is the coverage a
`[3sigma]` claim (spec/target-spec.md section 2) stands for: a Gaussian
distribution whose mean +/- 3 sigma lies inside the limits has 99.73 % of its
mass inside them. A campaign that cannot hold that grades `unmet`; that is the
honest answer, not something to relax.

Pure stdlib; needs no ngspice, PDK or klt. `klt yield` itself is run
separately (see signoff/README.md, row 6).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIM_DIR = REPO_ROOT / "sim"
OUT_DIR = REPO_ROOT / "signoff" / "evidence" / "yield"

sys.path.insert(0, str(SIM_DIR))

from harness import montecarlo, runner  # noqa: E402

#: A `[3sigma]` claim: mean +/- 3 sigma inside the limits is 99.73 % of a
#: Gaussian (erf(3/sqrt 2) = 0.99730). spec/target-spec.md section 2.
TARGET_YIELD = 0.9973

#: Schematic-level records only: the post-layout re-runs are item 7's evidence.
CAMPAIGNS = {
    "temp-accuracy-mc": {
        "record_id": "20260802-082345-989ce7a",
        # measurement in the logs / derived by the harness -> spec row id
        "rows": {
            "terr_untrim_c": "temp-accuracy-untrimmed",
            "terr_trim_c": "temp-accuracy-trimmed",
        },
    },
    "por-threshold-mc": {
        "record_id": "20260802-083749-3b9b414",
        "rows": {
            "vpor_rise_v": "por-vth-rise",
            "vpor_fall_v": "por-vth-fall",
            "v_hys_mv": "por-hysteresis",
        },
    },
}


def _tb(experiment: str) -> dict:
    return json.loads((SIM_DIR / experiment / "testbench" / "tb.json").read_text())


def _split_sample(stem: str, labels: list[str]) -> tuple[str, int]:
    """`<label>_<corner>_<T>c_<V>v_s<NNNN>` -> (label, sample index)."""
    for label in sorted(labels, key=len, reverse=True):
        if stem.startswith(label + "_"):
            return label, int(stem.rsplit("_s", 1)[1])
    raise ValueError(f"log {stem!r} matches no binding point in tb.json")


def load_samples(experiment: str) -> dict[str, dict[str, list[float]]]:
    """binding label -> measurement -> values, ordered by sample index."""
    cfg = CAMPAIGNS[experiment]
    labels = [bp["label"] for bp in _tb(experiment)["mc"]["binding_points"]]
    points = runner.load_points(SIM_DIR / experiment / "corners", cfg["record_id"])
    by_label: dict[str, dict[int, dict[str, float]]] = {label: {} for label in labels}
    for stem, measurements in points.items():
        label, sample = _split_sample(stem, labels)
        values = dict(measurements)
        if _tb(experiment)["mc"].get("derive") == "temp_trim":
            values.update(montecarlo.derive_temp_trim(values))
        by_label[label][sample] = values
    out: dict[str, dict[str, list[float]]] = {}
    for label, samples in by_label.items():
        out[label] = {}
        for name in cfg["rows"]:
            out[label][name] = [
                samples[i][name] for i in sorted(samples) if name in samples[i]
            ]
    return out


def build_sample_set(experiment: str) -> dict:
    cfg = CAMPAIGNS[experiment]
    tb = _tb(experiment)
    mc = tb["mc"]
    samples = load_samples(experiment)
    measurements = []
    for bp in mc["binding_points"]:
        for name, row in cfg["rows"].items():
            check = tb["checks"][name]
            measurements.append(
                {
                    "name": f"{name}@{bp['label']}",
                    "spec_row": row,
                    "samples": samples[bp["label"]][name],
                    "limits": {
                        "min": check["min"],
                        "max": check["max"],
                        "target_yield": TARGET_YIELD,
                    },
                    "source_corners": [
                        f"{bp['corner']}/{bp['temp_c']:g}C/{bp['vdd']:.2f}V"
                    ],
                }
            )
    return {
        "provenance": {
            "seed": mc["seed_base"],
            "rng": (
                "ngspice `.option seed=<seed_base + binding_index*100000 + "
                "sample>` per sample, local mismatch only "
                "(sw_stat_mismatch=1, sw_stat_global=0), process held at "
                f"each binding point's own corner; record {cfg['record_id']}"
            ),
            "draws_per_population": mc["n"],
            "common_random_numbers": False,
            "corner_matrix": [
                f"{bp['label']}: {bp['corner']}/{bp['temp_c']:g}C/{bp['vdd']:.2f}V"
                for bp in mc["binding_points"]
            ],
        },
        "measurements": measurements,
    }


def render(doc: dict) -> str:
    return json.dumps(doc, indent=1) + "\n"


def out_path(experiment: str) -> Path:
    return OUT_DIR / f"{experiment}.samples.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if committed sample sets differ")
    args = parser.parse_args(argv)
    rc = 0
    for experiment in CAMPAIGNS:
        text = render(build_sample_set(experiment))
        path = out_path(experiment)
        if args.check:
            if not path.is_file() or path.read_text() != text:
                print(f"FAIL {path.relative_to(REPO_ROOT)} is stale; re-run signoff/yield_samples.py")
                rc = 1
            else:
                print(f"ok   {path.relative_to(REPO_ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            print(f"wrote {path.relative_to(REPO_ROOT)}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
