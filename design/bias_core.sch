v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {bias_core -- shared bias / reference core} -300 -330 0 0 0.5 0.5 {}
T {Owner: issue #11 (shared bias/reference generation with safe startup ordering).
PLACEHOLDER: ports only, no internals yet -- see design/README.md.

Interface contract (DR-005 "Shared infrastructure"):
  VDD/VSS  3.3 V core-flavor supply pair (DR-001)
  IBIAS    shared bias-mirror node feeding the temp core, the POR
           comparator and the POR output chain's pulse timer
  VREF     PVT-stable reference voltage the POR comparator compares
           the divided rail against
  BIAS_OK  "shared core is up and settled" flag; the POR release
           decision is gated on it (DR-005 startup ordering, step 5)} -300 -300 0 0 0.3 0.3 {}
N -300 -200 -240 -200 {lab=VDD}
N -300 -140 -240 -140 {lab=VSS}
N 240 -200 300 -200 {lab=IBIAS}
N 240 -140 300 -140 {lab=VREF}
N 240 -80 300 -80 {lab=BIAS_OK}
C {devices/iopin.sym} -300 -200 0 1 {name=p_vdd lab=VDD}
C {devices/iopin.sym} -300 -140 0 1 {name=p_vss lab=VSS}
C {devices/opin.sym} 300 -200 0 0 {name=p_ibias lab=IBIAS}
C {devices/opin.sym} 300 -140 0 0 {name=p_vref lab=VREF}
C {devices/opin.sym} 300 -80 0 0 {name=p_bias_ok lab=BIAS_OK}
T {Placeholder terminations: 1 Tohm to VSS on each output, so the stub is
ERC-clean and DC-solvable. Delete them when the real core lands.} 400 60 0 0 0.3 0.3 {}
N 400 140 400 170 {lab=IBIAS}
N 400 230 400 260 {lab=VSS}
N 520 140 520 170 {lab=VREF}
N 520 230 520 260 {lab=VSS}
N 640 140 640 170 {lab=BIAS_OK}
N 640 230 640 260 {lab=VSS}
C {devices/lab_pin.sym} 400 140 0 0 {name=l_ph_ibias sig_type=std_logic lab=IBIAS}
C {devices/lab_pin.sym} 400 260 0 0 {name=l_ph_vss1 sig_type=std_logic lab=VSS}
C {devices/res.sym} 400 200 0 0 {name=Rplaceholder_ibias
value=1T
footprint=1206
device=resistor
m=1}
C {devices/lab_pin.sym} 520 140 0 0 {name=l_ph_vref sig_type=std_logic lab=VREF}
C {devices/lab_pin.sym} 520 260 0 0 {name=l_ph_vss2 sig_type=std_logic lab=VSS}
C {devices/res.sym} 520 200 0 0 {name=Rplaceholder_vref
value=1T
footprint=1206
device=resistor
m=1}
C {devices/lab_pin.sym} 640 140 0 0 {name=l_ph_ok sig_type=std_logic lab=BIAS_OK}
C {devices/lab_pin.sym} 640 260 0 0 {name=l_ph_vss3 sig_type=std_logic lab=VSS}
C {devices/res.sym} 640 200 0 0 {name=Rplaceholder_bias_ok
value=1T
footprint=1206
device=resistor
m=1}
C {devices/code_shown.sym} -300 120 0 0 {name=STUB only_toplevel=false value="* PLACEHOLDER: bias_core has no internals yet -- they land with issue #11.
* The Rplaceholder_* devices in this cell are 1 Tohm terminations, not
* design content: they exist only so this stub is ERC-clean and DC-solvable.
* Nothing in this cell may be cited as simulation evidence."}
