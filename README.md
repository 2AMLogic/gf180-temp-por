# gf180-temp-por

**PRIVATE — 2AM Logic proprietary IP. Canary block (wave 1).**

Temperature sensor + power-on-reset pair on gf180mcu (open PDK), designed by agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source analog flow. Dual purpose, per the canary model: catalog
inventory (eventually silicon-measured) and tool forcing-function
(friction issues go to the public klayout-tools tracker).

Selection rationale: Vidatronic-validated categories; tiny area rides along on any shuttle seat (matrix row 7).

## Target specification (DRAFT — engineering to ratify, see issue #1)

| Parameter | Target | Stretch |
|---|---|---|
| Temp range | −40…125 °C | — |
| Temp accuracy (untrimmed) | ±3 °C | ±1.5 °C (1-pt trim) |
| Temp interface | analog PTAT/CTAT out | digital out via SAR pairing |
| Temp Iq | < 20 µA | < 5 µA |
| POR threshold | 2.6 V ±5% | — |
| POR hysteresis | ≥ 100 mV | — |
| POR Iq | < 1 µA | < 0.3 µA |
| POR reset pulse | ≥ 1 ms | programmable |

Maturity ladder: simulation-complete → layout DRC/LVS-clean → shuttle
seat → measured silicon over temperature.

## Layout

```
spec/          ratified spec + decision records
design/        schematics / netlists (xschem)
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  silicon characterization (empty until tape-out)
```
