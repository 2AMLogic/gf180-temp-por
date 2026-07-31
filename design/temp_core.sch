v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {temp_core -- PTAT / CTAT temperature-sensing core} -300 -330 0 0 0.5 0.5 {}
T {Owner: issue #9 (temperature-sensing core, vertical-PNP DVBE/VBE).
PLACEHOLDER: ports only, no internals yet -- see design/README.md.

Interface contract:
  VDD/VSS  3.3 V core-flavor supply pair (DR-001)
  IBIAS    bias-mirror node from bias_core (shared, DR-005)
  EN       enable, active high; driven from RESETn at the top level so
           the sensor is only enabled after POR releases (DR-005
           startup ordering, step 6). The sensor is never required to
           be valid before POR.
  PTAT     analog PTAT output pad (DR-002, wave-1 deliverable)
  CTAT     analog CTAT output pad (DR-002, wave-1 deliverable)

Accuracy is judged at these pin voltages via the published V(T)
transfer characteristic (DR-002), not at a digital code -- there is no
SAR/ADC in wave 1.} -300 -300 0 0 0.3 0.3 {}
N -300 -200 -240 -200 {lab=VDD}
N -300 -140 -240 -140 {lab=VSS}
N -300 -80 -240 -80 {lab=IBIAS}
N -300 -20 -240 -20 {lab=EN}
N 240 -200 300 -200 {lab=PTAT}
N 240 -140 300 -140 {lab=CTAT}
C {devices/iopin.sym} -300 -200 0 1 {name=p_vdd lab=VDD}
C {devices/iopin.sym} -300 -140 0 1 {name=p_vss lab=VSS}
C {devices/ipin.sym} -300 -80 0 0 {name=p_ibias lab=IBIAS}
C {devices/ipin.sym} -300 -20 0 0 {name=p_en lab=EN}
C {devices/opin.sym} 300 -200 0 0 {name=p_ptat lab=PTAT}
C {devices/opin.sym} 300 -140 0 0 {name=p_ctat lab=CTAT}
T {Placeholder terminations: 1 Tohm to VSS on each output, so the stub is
ERC-clean and DC-solvable. Delete them when the real core lands.} 400 60 0 0 0.3 0.3 {}
N 400 140 400 170 {lab=PTAT}
N 400 230 400 260 {lab=VSS}
N 520 140 520 170 {lab=CTAT}
N 520 230 520 260 {lab=VSS}
C {devices/lab_pin.sym} 400 140 0 0 {name=l_ph_ptat sig_type=std_logic lab=PTAT}
C {devices/lab_pin.sym} 400 260 0 0 {name=l_ph_vss1 sig_type=std_logic lab=VSS}
C {devices/res.sym} 400 200 0 0 {name=Rplaceholder_ptat
value=1T
footprint=1206
device=resistor
m=1}
C {devices/lab_pin.sym} 520 140 0 0 {name=l_ph_ctat sig_type=std_logic lab=CTAT}
C {devices/lab_pin.sym} 520 260 0 0 {name=l_ph_vss2 sig_type=std_logic lab=VSS}
C {devices/res.sym} 520 200 0 0 {name=Rplaceholder_ctat
value=1T
footprint=1206
device=resistor
m=1}
C {devices/code_shown.sym} -300 120 0 0 {name=STUB only_toplevel=false value="* PLACEHOLDER: temp_core has no internals yet -- they land with issue #9.
* The Rplaceholder_* devices in this cell are 1 Tohm terminations, not
* design content: they exist only so this stub is ERC-clean and DC-solvable.
* Nothing in this cell may be cited as simulation evidence."}
