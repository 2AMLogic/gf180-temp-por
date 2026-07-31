# gf180-temp-por

A temperature sensor + power-on-reset (POR) pair, targeting the
[gf180mcu](https://gf180mcu-pdk.readthedocs.io/) open PDK.

## What this is

This is one of 2AM Logic's canary blocks: a small, self-contained analog
IP block used both as a real design deliverable and as a forcing function
for the open-source analog tooling it's built with. The design work —
architecture survey, device characterization, schematic entry, testbench
authoring, simulation, and (eventually) layout — is carried out by AI
agents driving an open-source flow end to end.

## Status: early-stage, in progress

Nothing here should be read as a finished or measured result — there is
no silicon yet, and no completed layout. As of this writing the project
has:

- ratified a target specification and architecture direction through a
  series of recorded decisions (`spec/decision-records/`),
- characterized the relevant gf180mcu devices (vertical PNP, resistor
  flavors, MOS options) against a bootstrap simulation harness,
- begun recording PVT-corner simulation evidence (`sim/`), and
- entered the block's top-level schematic hierarchy and pad interface in
  xschem, with a reproducible ngspice netlist export (`design/`).

The sub-circuits inside that hierarchy are still placeholders, and full
testbench sign-off and layout have not happened yet. Every claim this
project makes is expected to be backed by a testbench and by PVT corner
data recorded in `sim/`, not asserted without
evidence — until a stage is checked off above, treat it as not yet done.

## The agent-native build

This block is designed, simulated, and verified with AI agents as the
primary workers, driving the flow directly rather than assisting a human
doing the driving. Decisions are captured as they're made
(`spec/decision-records/`), and simulation results are recorded
append-only as evidence (`sim/`) rather than overwritten, so the design
history stays auditable end to end. That's not a caveat on the work —
it's the point of the project: proving out what an agent-driven,
open-tooling analog design flow can actually deliver.

## Toolchain

- **PDK**: [gf180mcu](https://github.com/google/gf180mcu-pdk) (open PDK)
- **Design / simulation**: [xschem](https://xschem.sourceforge.io/) +
  [ngspice](https://ngspice.sourceforge.io/)
- **Layout**: [klayout-tools](https://github.com/2AMLogic/klayout-tools),
  a companion open-source project built to make KLayout-based DRC/LVS and
  layout automation workable for an agent-driven flow. Wherever
  klayout-tools proves awkward or is missing a capability this design
  needs, that friction gets filed as a public issue there — this project
  is one of the reasons that tool exists.

## Layout of this repo

```
spec/          target specification + decision records
design/        schematics / netlists (xschem)
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  silicon characterization (empty until tape-out)
```

The block's target specification — one row per spec line, with conditions,
binding corner, and the decision record each value comes from — is
[`spec/target-spec.md`](spec/target-spec.md); the decisions behind it are in
[`spec/decision-records/`](spec/decision-records/).

## Simulation

PVT corner runs go through the harness in `sim/` (stdlib python3, no venv;
needs `ngspice` and a gf180mcu PDK install):

```bash
python3 sim/run_corners.py --check-env     # is ngspice + the PDK present?
python3 sim/run_corners.py --list          # experiments, corners, corner sets
python3 sim/run_corners.py <experiment>    # run the full PVT grid, mint a record
bash sim/selftest.sh                       # prove the harness works end to end
source sim/env.sh                          # same PDK in an interactive ngspice/xschem
```

Every run writes an append-only evidence record under
`sim/<experiment-slug>/records/`. The record format is authoritative in
[`sim/README.md`](sim/README.md); how to run the harness and write a
testbench is in [`sim/harness/README.md`](sim/harness/README.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
