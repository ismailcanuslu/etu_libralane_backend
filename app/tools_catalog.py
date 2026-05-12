import shlex
from dataclasses import dataclass, replace
from typing import Dict, List

from app.core.config import get_settings
from app.openlane_steps import CLASSIC_OPENLANE_STEP_IDS

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


def _openlane_shell(script: str) -> List[str]:
    return ["sh", "-lc", script]


def _openlane_preflight() -> str:
    return (
        "set -e; "
        "command -v openlane >/dev/null 2>&1 || { echo 'openlane CLI bulunamadi'; exit 2; }; "
        "test -f config.json || { echo 'config.json gerekli'; exit 2; }; "
    )


def _openlane_only_cmd(step_id: str) -> List[str]:
    return _openlane_shell(f"{_openlane_preflight()}openlane --only {shlex.quote(step_id)} config.json")


def _openlane_full_cmd() -> List[str]:
    return _openlane_shell(f"{_openlane_preflight()}openlane config.json")


def _openlane_step_action_id(step_id: str) -> str:
    return "openlane-" + step_id.replace(".", "-").lower()


def _openlane_step_label(step_id: str) -> str:
    return step_id.replace(".", " · ")


def _build_openlane_step_catalog() -> Dict[str, ToolSpec]:
    catalog: Dict[str, ToolSpec] = {}
    for step_id in CLASSIC_OPENLANE_STEP_IDS:
        action_id = _openlane_step_action_id(step_id)
        catalog[action_id] = ToolSpec(
            id=action_id,
            label=_openlane_step_label(step_id),
            description=f"OpenLane Classic: yalnızca {step_id} adımı.",
            image=_OPENLANE,
            cmd=_openlane_only_cmd(step_id),
            group="openlane",
            enabled=True,
        )
    return catalog


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
        description="SymbiYosys gerektirir (runner image'ında kurulu değil).",
        image=_BASIC,
        cmd=[
            "sh",
            "-lc",
            "command -v sby >/dev/null 2>&1 || { echo 'SymbiYosys (sby) bulunamadi'; exit 2; }; echo 'formal: proje sby dosyasi gerekir'; exit 2",
        ],
        group="tools",
        enabled=False,
    ),
    "openlane-classic": ToolSpec(
        id="openlane-classic",
        label="OpenLane Classic",
        description="OpenLane2 tam Classic akışı (config.json gerekir).",
        image=_OPENLANE,
        cmd=_openlane_full_cmd(),
        group="build",
        badge="PnR",
        enabled=True,
    ),
    "timing": ToolSpec(
        id="timing",
        label="Timing Analizi",
        description="OpenLane STA adımı (OpenROAD.STAPostPNR).",
        image=_OPENLANE,
        cmd=_openlane_only_cmd("OpenROAD.STAPostPNR"),
        group="analysis",
        enabled=True,
    ),
    "power": ToolSpec(
        id="power",
        label="Güç Analizi",
        description="OpenLane IR drop raporu adımı.",
        image=_OPENLANE,
        cmd=_openlane_only_cmd("OpenROAD.IRDropReport"),
        group="analysis",
        enabled=True,
    ),
    "drc": ToolSpec(
        id="drc",
        label="DRC Kontrolü",
        description="OpenLane Magic DRC adımı.",
        image=_OPENLANE,
        cmd=_openlane_only_cmd("Magic.DRC"),
        group="analysis",
        enabled=True,
    ),
    "lvs": ToolSpec(
        id="lvs",
        label="LVS Kontrolü",
        description="OpenLane LVS adımı.",
        image=_OPENLANE,
        cmd=_openlane_only_cmd("Checker.LVS"),
        group="analysis",
        enabled=True,
    ),
    "pnr": ToolSpec(
        id="pnr",
        label="Fiziksel Tasarım",
        description="OpenLane place & route akışı (config.json gerekir).",
        image=_OPENLANE,
        cmd=_openlane_full_cmd(),
        group="build",
        enabled=True,
    ),
    "gdsii": ToolSpec(
        id="gdsii",
        label="GDSII Dışa Aktarma",
        description="OpenLane GDSII çıktı adımı.",
        image=_OPENLANE,
        cmd=_openlane_only_cmd("Magic.StreamOut"),
        group="build",
        enabled=True,
    ),
}
TOOL_CATALOG.update(_build_openlane_step_catalog())


def _effective_spec(spec: ToolSpec) -> ToolSpec:
    if spec.image == _OPENLANE and not _settings.enable_openlane_tools:
        return replace(spec, enabled=False)
    return spec


def get_tool(action: str) -> ToolSpec | None:
    spec = TOOL_CATALOG.get(action)
    if spec is None:
        return None
    return _effective_spec(spec)


def list_tools() -> List[ToolSpec]:
    return [_effective_spec(spec) for spec in TOOL_CATALOG.values()]
