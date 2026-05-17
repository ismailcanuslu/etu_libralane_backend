"""Yeni projeler için klasik OpenLane + sky130 iskeleti."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.workspace_paths import project_dir
from app.services.openlane_layout import design_slug_from_project


def _write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def scaffold_openlane_project(project_id: str) -> list[str]:
    """
    Proje boşsa klasik dizin yapısını oluşturur.
    Oluşturulan dosya yollarını döndürür.
    """
    base = project_dir(project_id, create=True)
    existing = list(base.rglob("*"))
    has_user_files = any(
        p.is_file()
        and not p.relative_to(base).as_posix().startswith("_jobs/")
        for p in existing
    )
    if has_user_files:
        return []

    design = design_slug_from_project(project_id)
    created: list[str] = []

    templates: list[tuple[str, str]] = [
        (
            "README.md",
            f"""# {project_id}

SkyWater 130 (sky130) + OpenLane proje iskeleti.

## Dizin yapısı

- `src/` — RTL (`.v`)
- `tb/` — testbench (`tb_*.v`)
- `openlane/{design}/` — `config.json`, `pin_order.cfg`
- `flow.tcl` — OpenLane akış girişi
- `runs/` — akış çıktıları (OpenLane oluşturur)

## Araçlar

- **Sentez / Lint / Simülasyon:** `src/*.v` (yoksa kök `*.v`)
- **OpenLane1 Flow:** `flow.tcl` + `openlane/{design}/config.json`
""",
        ),
        (
            "plans/.gitkeep",
            "",
        ),
        (
            "src/.gitkeep",
            "",
        ),
        (
            "src/top.v",
            f"""// Top-level placeholder for {project_id}
module top (
    input  wire clk,
    input  wire rst_n,
    output wire done
);
    assign done = rst_n;
endmodule
""",
        ),
        (
            "tb/.gitkeep",
            "",
        ),
        (
            "tb/tb_top.v",
            """`timescale 1ns/1ps
module tb_top;
    reg clk = 0;
    reg rst_n = 0;
    wire done;

    always #5 clk = ~clk;

    initial begin
        $dumpfile("tb/top.vcd");
        $dumpvars(0, tb_top);
        #20 rst_n = 1;
        #200 $finish;
    end

    top uut (.clk(clk), .rst_n(rst_n), .done(done));
endmodule
""",
        ),
        (
            f"openlane/{design}/config.json",
            json.dumps(
                {
                    "DESIGN_NAME": design,
                    "VERILOG_FILES": "dir::src",
                    "CLOCK_PORT": "clk",
                    "CLOCK_PERIOD": 10.0,
                    "FP_CORE_UTIL": 35,
                    "PL_TARGET_DENSITY": "0.35",
                    "DESIGN_IS_CORE": True,
                },
                indent=2,
            )
            + "\n",
        ),
        (
            f"openlane/{design}/pin_order.cfg",
            "# Pin order — OpenLane I/O pad yerleşimi\n# Örnek: clk rst_n done\n",
        ),
        (
            "flow.tcl",
            """# OpenLane 1 flow entry — runner container /work kökünden çalışır.
if {[info exists ::env(OPENLANE_ROOT)] && [file exists $::env(OPENLANE_ROOT)/flow.tcl]} {
    source $::env(OPENLANE_ROOT)/flow.tcl
} elseif {[file exists /openlane/flow.tcl]} {
    source /openlane/flow.tcl
} else {
    puts stderr "flow.tcl: OPENLANE_ROOT veya /openlane/flow.tcl bulunamadi"
    exit 2
}
""",
        ),
        (
            "Makefile",
            """# Yerel simülasyon (Icarus) — opsiyonel
SRC = $(wildcard src/*.v)
TB  = $(wildcard tb/tb_*.v)

.PHONY: sim
sim:
\tiverilog -o sim.vvp $(SRC) $(TB) && vvp sim.vvp
""",
        ),
        (
            "runs/.gitkeep",
            "",
        ),
    ]

    for rel, body in templates:
        path = base / rel
        if _write_if_missing(path, body):
            created.append(rel)

    return created
