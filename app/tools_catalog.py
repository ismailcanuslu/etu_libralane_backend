from dataclasses import dataclass, field
from typing import Dict, List

from app.core.config import get_settings

_settings = get_settings()


@dataclass(frozen=True)
class ToolSpec:
    id: str
    label: str
    description: str
    image: str
    cmd: List[str]
    group: str = "tools"
    badge: str | None = None
    enabled: bool = True


_BASIC = _settings.runner_image_basic
_OPENLANE = _settings.runner_image_openlane


TOOL_CATALOG: Dict[str, ToolSpec] = {
    "smoke-test": ToolSpec(
        id="smoke-test",
        label="Smoke Test",
        description="Tüm Verilog kaynaklarının elaborate olup olmadığını hızlıca dener.",
        image=_BASIC,
        cmd=["sh", "-lc", "set -e; ls *.v >/dev/null 2>&1 || { echo 'no .v files'; exit 1; }; iverilog -o /tmp/smoke.out *.v && echo 'SMOKE OK'"],
        group="tools",
        badge="Hızlı",
    ),
    "lint": ToolSpec(
        id="lint",
        label="RTL Lint",
        description="Verilator --lint-only ile statik analiz.",
        image=_BASIC,
        cmd=["sh", "-lc", "verilator --lint-only --Wall *.v"],
        group="tools",
    ),
    "simulation": ToolSpec(
        id="simulation",
        label="Simülasyon",
        description="iverilog + vvp ile testbench koşturur (tb_*.v dosyaları beklenir).",
        image=_BASIC,
        cmd=["sh", "-lc", "set -e; iverilog -o sim *.v tb_*.v && vvp sim"],
        group="build",
    ),
    "synthesis": ToolSpec(
        id="synthesis",
        label="Sentez",
        description="Yosys ile RTL → gate-level netlist (deneysel).",
        image=_BASIC,
        cmd=["sh", "-lc", "yosys -p 'read_verilog *.v; synth; write_verilog netlist.v'"],
        group="build",
    ),
    "verification": ToolSpec(
        id="verification",
        label="Doğrulama",
        description="Lint + smoke testi tek geçişte.",
        image=_BASIC,
        cmd=["sh", "-lc", "set -e; verilator --lint-only --Wall *.v && iverilog -o /tmp/v.out *.v && echo 'VERIFY OK'"],
        group="build",
    ),
    "formal": ToolSpec(
        id="formal",
        label="Formal Doğrulama",
        description="SymbiYosys gerektirir (henüz kurulu değil).",
        image=_BASIC,
        cmd=["sh", "-lc", "echo 'formal: not implemented yet'; exit 2"],
        group="tools",
        enabled=False,
    ),
    "timing": ToolSpec(
        id="timing",
        label="Timing Analizi",
        description="OpenSTA gerektirir (M5 / OpenLane image).",
        image=_OPENLANE,
        cmd=["sh", "-lc", "echo 'timing: openlane image required'; exit 2"],
        group="analysis",
        enabled=False,
    ),
    "power": ToolSpec(
        id="power",
        label="Güç Analizi",
        description="Statik/dinamik güç analizi (ileri).",
        image=_OPENLANE,
        cmd=["sh", "-lc", "echo 'power: not implemented yet'; exit 2"],
        group="analysis",
        enabled=False,
    ),
    "drc": ToolSpec(
        id="drc",
        label="DRC Kontrolü",
        description="Magic/KLayout DRC (ileri).",
        image=_OPENLANE,
        cmd=["sh", "-lc", "echo 'drc: not implemented yet'; exit 2"],
        group="analysis",
        enabled=False,
    ),
    "lvs": ToolSpec(
        id="lvs",
        label="LVS Kontrolü",
        description="Layout vs Schematic (ileri).",
        image=_OPENLANE,
        cmd=["sh", "-lc", "echo 'lvs: not implemented yet'; exit 2"],
        group="analysis",
        enabled=False,
    ),
    "pnr": ToolSpec(
        id="pnr",
        label="Fiziksel Tasarım",
        description="OpenLane PnR (ileri).",
        image=_OPENLANE,
        cmd=["sh", "-lc", "echo 'pnr: not implemented yet'; exit 2"],
        group="build",
        enabled=False,
    ),
    "gdsii": ToolSpec(
        id="gdsii",
        label="GDSII Dışa Aktarma",
        description="Tapeout (ileri).",
        image=_OPENLANE,
        cmd=["sh", "-lc", "echo 'gdsii: not implemented yet'; exit 2"],
        group="build",
        enabled=False,
    ),
}


def get_tool(action: str) -> ToolSpec | None:
    return TOOL_CATALOG.get(action)


def list_tools() -> List[ToolSpec]:
    return list(TOOL_CATALOG.values())
