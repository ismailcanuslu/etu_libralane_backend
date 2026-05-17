"""Yeni projeler için Caravel user project + OpenLane (sky130) iskeleti."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.workspace_paths import project_dir
from app.services.caravel_layout import (
    CARAVEL_HARNESS_NOTE,
    CARAVEL_RTL_DIR,
    CARAVEL_USER_MODULE_DESIGN,
    CARAVEL_WRAPPER_DESIGN,
)

_GUIDE_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "content" / "caravel_guide.md"
GUIDE_FILENAME = "guide.md"


def caravel_guide_content(project_id: str) -> str:
    template = _GUIDE_TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.replace("{{PROJECT_ID}}", project_id)


_GUIDE_MARKERS = ("GDS ≠ tape-out", "layout_klayout_1440p")


def ensure_caravel_guide(project_id: str) -> bool:
    """Proje köküne guide.md yazar; yoksa veya eski şablonsa günceller."""
    path = project_dir(project_id, create=True) / GUIDE_FILENAME
    content = caravel_guide_content(project_id)
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if all(marker in existing for marker in _GUIDE_MARKERS):
            return False
        path.write_text(content, encoding="utf-8")
        return True
    path.write_text(content, encoding="utf-8")
    return True


def _write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def scaffold_openlane_project(project_id: str) -> list[str]:
    """
    Proje boşsa Caravel user project uyumlu iskelet oluşturur.
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

    created: list[str] = []

    wrapper_config = {
        "DESIGN_NAME": CARAVEL_WRAPPER_DESIGN,
        "VERILOG_FILES": [
            f"dir::../../{CARAVEL_RTL_DIR}/defines.v",
            f"dir::../../{CARAVEL_RTL_DIR}/user_module.v",
            f"dir::../../{CARAVEL_RTL_DIR}/user_project_wrapper.v",
        ],
        "CLOCK_PORT": "wb_clk_i",
        "CLOCK_PERIOD": 25,
        "FP_CORE_UTIL": 10,
        "PL_TARGET_DENSITY": "0.35",
        "DESIGN_IS_CORE": True,
        "FP_SIZING": "absolute",
        "DIE_AREA": "0 0 2920 3520",
        "SYNTH_READ_BLACKBOX_LIB": True,
        "RUN_CVC": 0,
    }

    module_config = {
        "DESIGN_NAME": CARAVEL_USER_MODULE_DESIGN,
        "VERILOG_FILES": [
            f"dir::../../{CARAVEL_RTL_DIR}/defines.v",
            f"dir::../../{CARAVEL_RTL_DIR}/user_module.v",
        ],
        "CLOCK_PORT": "clk",
        "CLOCK_PERIOD": 10,
        "FP_CORE_UTIL": 35,
        "PL_TARGET_DENSITY": "0.35",
        "DESIGN_IS_CORE": True,
    }

    templates: list[tuple[str, str]] = [
        (
            "README.md",
            f"""# {project_id}

SkyWater **sky130** + **Caravel user project** iskeleti (Efabless MPW / tape-out yolu).

**Adım adım rehber:** [guide.md](guide.md) (GDS, macro, wrapper, tam çip).

## Caravel akışı (özet)

1. **user_module** — Kendi IP’niz (`verilog/rtl/user_module.v`).
2. **user_project_wrapper** — Caravel pinleri + IP örneği (`verilog/rtl/user_project_wrapper.v`).
3. **OpenLane** — Önce macro (`openlane/user_module/`), sonra wrapper (`openlane/user_project_wrapper/`).
4. **Tam çip** — Caravel harness + padframe (harici repo); ayrıntı: `{CARAVEL_HARNESS_NOTE}`.

## Dizinler

| Yol | Açıklama |
|-----|----------|
| `{CARAVEL_RTL_DIR}/` | Caravel RTL (wrapper + IP) |
| `openlane/user_project_wrapper/` | Wrapper hardening `config.json` |
| `openlane/user_module/` | Macro-first IP hardening |
| `tb/` | Simülasyon (`tb_*.v`) |
| `flow.tcl` | OpenLane 1 giriş |
| `caravel/` | Harness entegrasyon notları |

## Web araçları

- **Lint / Sentez / Simülasyon:** `verilog/rtl/*.v`
- **OpenLane1 Flow:** `flow.tcl` + `openlane/user_project_wrapper/config.json` (design: `user_project_wrapper`)

Resmi şablon: [caravel_user_project](https://github.com/efabless/caravel_user_project)
""",
        ),
        (
            GUIDE_FILENAME,
            caravel_guide_content(project_id),
        ),
        (
            CARAVEL_HARNESS_NOTE,
            """# Caravel harness entegrasyonu

Bu proje **Caravel user project** düzeninde başlar. Tape-out için Efabless harness ile birleştirilir.

## Resmi kaynaklar

- [Caravel User Project](https://caravel-user-project.readthedocs.io/)
- [Caravel harness](https://caravel-harness.readthedocs.io/)
- GitHub şablon: `https://github.com/efabless/caravel_user_project`

## Tipik adımlar (MPW)

1. Bu workspace’te IP + `user_project_wrapper` harden edin (LibreLane web veya OpenLane1 Flow).
2. Üretilen macro LEF/GDS’yi Caravel user project reposuna kopyalayın veya submodule ile bağlayın.
3. Caravel repo içinde `openlane/user_project_wrapper/interactive.tcl` ile padframe + tam çip entegrasyonu.
4. `USE_GPIO_PADS`, `GPIO_PADS_VERILOG`, `EXTRA_LEFS` — tam çip config’inde (harness tarafı).

## Macro-first (önerilen)

1. `openlane/user_module/config.json` → sadece `user_module` harden.
2. Wrapper config’te `EXTRA_LEFS` / `EXTRA_GDS_FILES` ile macro ekleyin (Caravel dokümantasyonu).
3. `openlane/user_project_wrapper/config.json` → wrapper harden.

Harness kaynak kodu bu iskelette **yoktur**; `git clone` / submodule ile `caravel/` altına eklenir.
""",
        ),
        (
            f"{CARAVEL_RTL_DIR}/defines.v",
            """// Caravel user project — ortak define'lar (MPRJ_IO_PADS)
`ifndef MPRJ_IO_PADS
`define MPRJ_IO_PADS 38
`endif

`ifndef USE_POWER_PINS
// Tam Caravel harness ile derlemede USE_POWER_PINS tanimlayin.
`endif
""",
        ),
        (
            f"{CARAVEL_RTL_DIR}/user_module.v",
            f"""// Kullanici IP — Caravel wrapper icinde instantiate edilir
`default_nettype none

module {CARAVEL_USER_MODULE_DESIGN} (
    input  wire clk,
    input  wire rst_n,
    input  wire [31:0] la_data_in,
    output wire [31:0] la_data_out,
    output wire [2:0]  irq
);
    reg [31:0] count;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= 32'd0;
        else
            count <= count + 32'd1;
    end
    assign la_data_out = count;
    assign irq = 3'b0;
endmodule

`default_nettype wire
""",
        ),
        (
            f"{CARAVEL_RTL_DIR}/user_project_wrapper.v",
            f"""// Caravel user_project_wrapper — Efabless pin listesi (sadelestirilmis iskelet)
`default_nettype none
`include "defines.v"

module {CARAVEL_WRAPPER_DESIGN} #(
    parameter BITS = 32
) (
`ifdef USE_POWER_PINS
    inout vdda1, vdda2, vssa1, vssa2,
    inout vccd1, vccd2, vssd1, vssd2,
`endif
    input  wb_clk_i,
    input  wb_rst_i,
    input  wbs_stb_i,
    input  wbs_cyc_i,
    input  wbs_we_i,
    input  [3:0] wbs_sel_i,
    input  [31:0] wbs_dat_i,
    input  [31:0] wbs_adr_i,
    output wbs_ack_o,
    output [31:0] wbs_dat_o,
    input  [127:0] la_data_in,
    output [127:0] la_data_out,
    input  [127:0] la_oenb,
    input  [`MPRJ_IO_PADS-1:0] io_in,
    output [`MPRJ_IO_PADS-1:0] io_out,
    output [`MPRJ_IO_PADS-1:0] io_oeb,
    input  user_clock2,
    output [2:0] user_irq
);

    {CARAVEL_USER_MODULE_DESIGN} mprj (
        .clk(wb_clk_i),
        .rst_n(~wb_rst_i),
        .la_data_in(la_data_in[31:0]),
        .la_data_out(la_data_out[31:0]),
        .irq(user_irq)
    );

    assign wbs_ack_o = 1'b0;
    assign wbs_dat_o = 32'd0;
    assign la_data_out[127:32] = 96'd0;
    assign io_out = {{`MPRJ_IO_PADS{{1'b0}}}};
    assign io_oeb = {{`MPRJ_IO_PADS{{1'b1}}}};

endmodule

`default_nettype wire
""",
        ),
        (
            "tb/tb_user_project_wrapper.v",
            """`timescale 1ns/1ps
`include "../verilog/rtl/defines.v"

module tb_user_project_wrapper;
    reg wb_clk_i = 0;
    reg wb_rst_i = 1;
    reg [127:0] la_data_in = 0;
    wire [127:0] la_data_out;
    wire [2:0] user_irq;
    wire wbs_ack_o;
    wire [31:0] wbs_dat_o;
    wire [`MPRJ_IO_PADS-1:0] io_out, io_oeb;

    always #12.5 wb_clk_i = ~wb_clk_i;

    user_project_wrapper uut (
        .wb_clk_i(wb_clk_i),
        .wb_rst_i(wb_rst_i),
        .wbs_stb_i(1'b0),
        .wbs_cyc_i(1'b0),
        .wbs_we_i(1'b0),
        .wbs_sel_i(4'b0),
        .wbs_dat_i(32'b0),
        .wbs_adr_i(32'b0),
        .la_data_in(la_data_in),
        .la_oenb(128'h0),
        .io_in({`MPRJ_IO_PADS{1'b0}}),
        .user_clock2(1'b0),
        .la_data_out(la_data_out),
        .wbs_ack_o(wbs_ack_o),
        .wbs_dat_o(wbs_dat_o),
        .io_out(io_out),
        .io_oeb(io_oeb),
        .user_irq(user_irq)
    );

    initial begin
        $dumpfile("tb/wrapper.vcd");
        $dumpvars(0, tb_user_project_wrapper);
        #50 wb_rst_i = 0;
        #500 $finish;
    end
endmodule
""",
        ),
        (
            f"openlane/{CARAVEL_WRAPPER_DESIGN}/config.json",
            json.dumps(wrapper_config, indent=2) + "\n",
        ),
        (
            f"openlane/{CARAVEL_USER_MODULE_DESIGN}/config.json",
            json.dumps(module_config, indent=2) + "\n",
        ),
        (
            f"openlane/{CARAVEL_WRAPPER_DESIGN}/pin_order.cfg",
            "# Caravel user_project_wrapper — I/O pad sirasi (harness ile uyumlu)\n"
            "# Tam liste: caravel_user_project pin_order\n",
        ),
        (
            f"openlane/{CARAVEL_WRAPPER_DESIGN}/interactive.tcl",
            f"""# Caravel — wrapper / padframe (tam cip icin harness gerekir)
# Ornek: https://github.com/efabless/caravel/blob/master/openlane/chip_io/interactive.tcl

puts "INFO: Bu dosya tam Caravel harness ile kullanilir."
puts "INFO: Once user_project_wrapper harden; sonra harness repo ile birlestirin."

if {{[info exists ::env(DESIGN_NAME)]}} {{
    puts "DESIGN_NAME=$::env(DESIGN_NAME)"
}}
""",
        ),
        (
            "flow.tcl",
            """# OpenLane 1 — Caravel user project (runner /work kokunden)
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
            f"""# Yerel simülasyon (Icarus) — Caravel RTL
RTL = {CARAVEL_RTL_DIR}/defines.v {CARAVEL_RTL_DIR}/user_module.v {CARAVEL_RTL_DIR}/user_project_wrapper.v
TB  = tb/tb_user_project_wrapper.v

.PHONY: sim
sim:
\tiverilog -o sim.vvp $(RTL) $(TB) && vvp sim.vvp
""",
        ),
        (
            "plans/.gitkeep",
            "",
        ),
        (
            "runs/.gitkeep",
            "",
        ),
        # Geriye uyumluluk: eski araclar src/*.v arayabilir
        (
            "src/.gitkeep",
            "",
        ),
        (
            "src/README.txt",
            "Caravel RTL verilog/rtl/ altindadir. Eski araclar icin buraya kopya birakmayin.\n",
        ),
    ]

    for rel, body in templates:
        path = base / rel
        if _write_if_missing(path, body):
            created.append(rel)

    return created
