# LibreLane — seçili OpenLane 1.2 makro aşamalarını çalıştırır (flow.tcl alt kümesi).
# Ortam: LIBRALANE_FLOW_STEPS=step1,step2,...  LIBRALANE_FLOW_END=last_step_id

if {[catch {package require openlane} err]} {
    puts stderr "openlane paketi yuklenemedi: $err"
    exit 1
}

set options {
    {-design required}
}
set flags {}
parse_key_args "libralane_partial_flow" argv arg_values $options flags_map $flags

set design $arg_values(-design)
if {![info exists ::env(LIBRALANE_FLOW_STEPS)] || $::env(LIBRALANE_FLOW_STEPS) eq ""} {
    puts stderr "LIBRALANE_FLOW_STEPS bos"
    exit 2
}

set selected_raw [split $::env(LIBRALANE_FLOW_STEPS) ,]
set selected {}
foreach s $selected_raw {
    set t [string trim $s]
    if {$t ne ""} {
        lappend selected $t
    }
}

if {[llength $selected] == 0} {
    puts stderr "Secili asama yok"
    exit 2
}

set end_step $::env(LIBRALANE_FLOW_END)
if {![info exists end_step] || $end_step eq ""} {
    set end_step [lindex $selected end]
}

prep -design $design

set steps [dict create \
    verilator_lint_check run_verilator_step \
    synthesis run_synthesis \
    floorplan run_floorplan \
    placement run_placement_step \
    cts run_cts_step \
    routing run_routing_step \
    parasitics_sta run_parasitics_sta_step \
    irdrop run_irdrop_report_step \
    gds_magic run_magic_step \
    gds_klayout run_klayout_step \
    lvs [list run_lvs_step 1] \
    drc [list run_drc_step 1] \
    antenna_check [list run_antenna_check_step 1] \
]

set allowed [dict keys $steps]
foreach s $selected {
    if {[lsearch -exact $allowed $s] < 0} {
        puts stderr "Bilinmeyen asama: $s"
        exit 2
    }
}

set start_step [lindex $selected 0]
if {[lsearch -exact $selected $end_step] < 0} {
    puts stderr "Bitis asamasi ($end_step) secili listede degil"
    exit 2
}

set ::env(CURRENT_STEP) $start_step
set failed 0
set exe 0

dict for {step_name step_exe} $steps {
    if {[lsearch -exact $selected $step_name] < 0} {
        continue
    }
    if {!$exe && ![string equal $start_step $step_name]} {
        continue
    }
    set exe 1
    set ::env(CURRENT_STEP) $step_name
    puts "LibreLane: asama basliyor — $step_name"
    set step_result [catch [lindex $step_exe 0] [lindex $step_exe 1] err]
    if {$step_result} {
        set failed 1
        puts_err "Asama $step_name basarisiz: $err"
        break
    }
    if {[string equal $end_step $step_name]} {
        break
    }
}

if {$failed} {
    flow_fail
}

save_final_views
calc_total_runtime
save_state
generate_final_summary_report
puts_success "Secili OpenLane asamalari tamamlandi ($start_step → $end_step)."
