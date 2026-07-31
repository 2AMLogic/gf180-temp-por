v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {temp_por_top -- temperature sensor + power-on-reset block (top level)} -500 -320 0 0 0.5 0.5 {}
T {Ratified pinout (spec/decision-records/):
  VDD, VSS  supply pair, 3.3 V nominal +/-10%, gf180mcu 3.3 V core
            device flavor (nfet_03v3 / pfet_03v3)          -- DR-001
  PTAT      analog PTAT output                             -- DR-002
  CTAT      analog CTAT output                             -- DR-002
  RESETn    active-low, push-pull reset output             -- DR-004

No trim, config or programming pins: the reset pulse is fixed >=1 ms and
programmability is de-scoped for wave 1 (DR-003), and the temp interface
is analog-only -- no SAR/digital pairing in wave 1 (DR-002).

Hierarchy (one cell per design sub-issue, DR-005):
  xbias  bias_core         shared bias / reference          -- issue #11
  xtemp  temp_core         PTAT/CTAT sensing core           -- issue #9
  xcmp   por_comparator    threshold comparator + hysteresis-- issue #10
  xpor   por_output_chain  deglitch, pulse, output stage    -- issue #12

Internal nets:
  IBIAS/VREF/BIAS_OK  shared bias core outputs; BIAS_OK gates the
                      authoritative POR release decision (DR-005 step 5)
  POR_RAW             raw comparator decision into the output chain
  RESETn -> xtemp.EN  the sensor is enabled only after POR releases
                      (DR-005 step 6); it is never required to be valid
                      before POR, which keeps it out of the startup
                      chicken-and-egg problem entirely

All four sub-cells are PLACEHOLDERS today: correct ports, no internals.
See design/README.md.} -500 -290 0 0 0.3 0.3 {}
N -500 -100 -440 -100 {lab=VDD}
N -500 -40 -440 -40 {lab=VSS}
C {devices/iopin.sym} -500 -100 0 1 {name=p_vdd lab=VDD}
C {devices/iopin.sym} -500 -40 0 1 {name=p_vss lab=VSS}
C {devices/opin.sym} 300 230 0 0 {name=p_ptat lab=PTAT}
C {devices/opin.sym} 300 270 0 0 {name=p_ctat lab=CTAT}
C {devices/opin.sym} 700 0 0 0 {name=p_resetn lab=RESETn}
C {bias_core.sym} -200 0 0 0 {name=xbias}
C {temp_core.sym} 200 250 0 0 {name=xtemp}
C {por_comparator.sym} 200 0 0 0 {name=xcmp}
C {por_output_chain.sym} 600 0 0 0 {name=xpor}
C {devices/lab_pin.sym} -300 -20 0 0 {name=l_bias_vdd sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} -300 20 0 0 {name=l_bias_vss sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} -100 -20 0 1 {name=l_bias_ibias sig_type=std_logic lab=IBIAS}
C {devices/lab_pin.sym} -100 0 0 1 {name=l_bias_vref sig_type=std_logic lab=VREF}
C {devices/lab_pin.sym} -100 20 0 1 {name=l_bias_ok sig_type=std_logic lab=BIAS_OK}
C {devices/lab_pin.sym} 100 -40 0 0 {name=l_cmp_vdd sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 100 -20 0 0 {name=l_cmp_vss sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 100 0 0 0 {name=l_cmp_ibias sig_type=std_logic lab=IBIAS}
C {devices/lab_pin.sym} 100 20 0 0 {name=l_cmp_vref sig_type=std_logic lab=VREF}
C {devices/lab_pin.sym} 100 40 0 0 {name=l_cmp_ok sig_type=std_logic lab=BIAS_OK}
C {devices/lab_pin.sym} 300 0 0 1 {name=l_cmp_raw sig_type=std_logic lab=POR_RAW}
C {devices/lab_pin.sym} 500 -30 0 0 {name=l_por_vdd sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 500 -10 0 0 {name=l_por_vss sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 500 10 0 0 {name=l_por_ibias sig_type=std_logic lab=IBIAS}
C {devices/lab_pin.sym} 500 30 0 0 {name=l_por_raw sig_type=std_logic lab=POR_RAW}
C {devices/lab_pin.sym} 100 220 0 0 {name=l_temp_vdd sig_type=std_logic lab=VDD}
C {devices/lab_pin.sym} 100 240 0 0 {name=l_temp_vss sig_type=std_logic lab=VSS}
C {devices/lab_pin.sym} 100 260 0 0 {name=l_temp_ibias sig_type=std_logic lab=IBIAS}
C {devices/lab_pin.sym} 100 280 0 0 {name=l_temp_en sig_type=std_logic lab=RESETn}
