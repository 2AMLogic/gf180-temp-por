v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {por_comparator -- POR threshold comparator with hysteresis} -300 -330 0 0 0.5 0.5 {}
T {Owner: issue #10 (POR threshold comparator with hysteresis).
PLACEHOLDER: ports only, no internals yet -- see design/README.md.

Interface contract:
  VDD/VSS  3.3 V core-flavor supply pair (DR-001)
  IBIAS    bias-mirror node from bias_core (shared, DR-005)
  VREF     reference voltage from bias_core; the comparator compares a
           resistor-divided tap of VDD against it, which is what makes
           the threshold absolute rather than a rail fraction (DR-005)
  BIAS_OK  shared-core-valid flag; the comparator's decision is only
           authoritative once this is asserted (DR-005 step 4)
  POR_RAW  raw threshold decision handed to por_output_chain. Not the
           reset pin: hysteresis lives here, deglitch + pulse + output
           drive live in por_output_chain (DR-005 ownership split).

Below the comparator's own operating floor POR_RAW is undefined by
construction -- holding RESETn low in that regime is por_output_chain's
job (DR-004).} -300 -300 0 0 0.3 0.3 {}
N -300 -200 -240 -200 {lab=VDD}
N -300 -140 -240 -140 {lab=VSS}
N -300 -80 -240 -80 {lab=IBIAS}
N -300 -20 -240 -20 {lab=VREF}
N -300 40 -240 40 {lab=BIAS_OK}
N 240 -200 300 -200 {lab=POR_RAW}
C {devices/iopin.sym} -300 -200 0 1 {name=p_vdd lab=VDD}
C {devices/iopin.sym} -300 -140 0 1 {name=p_vss lab=VSS}
C {devices/ipin.sym} -300 -80 0 0 {name=p_ibias lab=IBIAS}
C {devices/ipin.sym} -300 -20 0 0 {name=p_vref lab=VREF}
C {devices/ipin.sym} -300 40 0 0 {name=p_bias_ok lab=BIAS_OK}
C {devices/opin.sym} 300 -200 0 0 {name=p_por_raw lab=POR_RAW}
T {Placeholder termination: 1 Tohm to VSS on the output, so the stub is
ERC-clean and DC-solvable. Delete it when the real comparator lands.} 400 60 0 0 0.3 0.3 {}
N 400 140 400 170 {lab=POR_RAW}
N 400 230 400 260 {lab=VSS}
C {devices/lab_pin.sym} 400 140 0 0 {name=l_ph_raw sig_type=std_logic lab=POR_RAW}
C {devices/lab_pin.sym} 400 260 0 0 {name=l_ph_vss1 sig_type=std_logic lab=VSS}
C {devices/res.sym} 400 200 0 0 {name=Rplaceholder_por_raw
value=1T
footprint=1206
device=resistor
m=1}
C {devices/code_shown.sym} -300 120 0 0 {name=STUB only_toplevel=false value="* PLACEHOLDER: por_comparator has no internals yet -- they land with issue #10.
* The Rplaceholder_* devices in this cell are 1 Tohm terminations, not
* design content: they exist only so this stub is ERC-clean and DC-solvable.
* Nothing in this cell may be cited as simulation evidence."}
