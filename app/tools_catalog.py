import shlex
from dataclasses import dataclass, replace
from typing import Dict, List, Literal

from app.core.config import get_settings
from app.openlane1_manifest import load_openlane1_manifest

_settings = get_settings()
ToolKind = Literal["binary", "probe", "flow"]


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
    kind: ToolKind = "binary"
    requires_verilog: bool = False
    requires_config: bool = False
    requires_pdk: bool = False


_BASIC = _settings.runner_image_basic
_OPENLANE = _settings.runner_image_openlane


def _shell(script: str) -> List[str]:
    return ["sh", "-lc", script]


def _resolve_binary_script(candidates: list[str], argv: str) -> str:
    quoted_candidates = " ".join(shlex.quote(name) for name in candidates)
    return (
        "set -e; "
        f"candidates={quoted_candidates}; "
        "resolved=''; "
        "for name in $candidates; do "
        'if path=$(command -v "$name" 2>/dev/null); then resolved="$path"; break; fi; '
        "done; "
        '[ -n "$resolved" ] || { echo "binary bulunamadi"; exit 2; }; '
        f'"$resolved" {shlex.quote(argv)}'
    )


def _flow_script(design_name: str, extra_args: list[str] | None = None) -> str:
    args = ""
    if extra_args:
        args = " " + " ".join(shlex.quote(value) for value in extra_args)
    return (
        "set -e; "
        "if [ -f ./flow.tcl ]; then FLOW=./flow.tcl; "
        "elif [ -f flow.tcl ]; then FLOW=flow.tcl; "
        "else echo 'flow.tcl gerekli'; exit 2; fi; "
        f'./"$FLOW" -design {shlex.quote(design_name)}{args}'
    )


def build_tool_command(
    spec: ToolSpec,
    *,
    design_name: str | None = None,
    extra_args: list[str] | None = None,
) -> List[str]:
    if spec.kind != "flow":
        return list(spec.cmd)
    if not design_name:
        raise ValueError("design_name required for flow tools")
    return _shell(_flow_script(design_name, extra_args))


def _build_openlane1_catalog() -> Dict[str, ToolSpec]:
    catalog: Dict[str, ToolSpec] = {}
    manifest = load_openlane1_manifest()
    for entry in manifest["tools"]:
        hub_key = entry["hub_key"]
        candidates = entry["resolved_bins"]
        notes = entry.get("notes") or ""
        manifest_enabled = bool(entry.get("enabled", True))
        base_enabled = manifest_enabled and bool(candidates)

        smoke_id = f"openlane1-{hub_key}"
        catalog[smoke_id] = ToolSpec(
            id=smoke_id,
            label=entry.get("label") or hub_key,
            description=notes or f"OpenLane1 {hub_key} smoke testi.",
            image=_OPENLANE,
            cmd=_shell(_resolve_binary_script(candidates, entry["smoke_argv"])),
            group="openlane1",
            enabled=base_enabled,
            kind="binary",
        )

        probe_id = f"openlane1-{hub_key}-probe"
        catalog[probe_id] = ToolSpec(
            id=probe_id,
            label=f"{entry.get('label') or hub_key} Probe",
            description=f"PATH uzerinde {hub_key} binary varligini dogrular.",
            image=_OPENLANE,
            cmd=_shell(_resolve_binary_script(candidates, entry["probe_argv"])),
            group="openlane1",
            badge="Probe",
            enabled=base_enabled,
            kind="probe",
        )

    catalog["openlane1-flow"] = ToolSpec(
        id="openlane1-flow",
        label="OpenLane1 Flow",
        description="OpenLane1 flow.tcl ile tam tasarim akisi (design adi ve flow.tcl gerekir).",
        image=_OPENLANE,
        cmd=[],
        group="build",
        badge="PnR",
        enabled=True,
        kind="flow",
        requires_verilog=True,
        requires_config=True,
        requires_pdk=True,
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
        requires_verilog=True,
    ),
    "lint": ToolSpec(
        id="lint",
        label="RTL Lint",
        description="Verilator --lint-only ile statik analiz.",
        image=_BASIC,
        cmd=["sh", "-lc", "verilator --lint-only --Wall *.v"],
        group="tools",
        requires_verilog=True,
    ),
    "simulation": ToolSpec(
        id="simulation",
        label="Simülasyon",
        description="iverilog + vvp ile testbench koşturur (tb_*.v dosyaları beklenir).",
        image=_BASIC,
        cmd=["sh", "-lc", "set -e; iverilog -o sim *.v tb_*.v && vvp sim"],
        group="build",
        requires_verilog=True,
    ),
    "synthesis": ToolSpec(
        id="synthesis",
        label="Sentez",
        description="Yosys ile RTL → gate-level netlist (deneysel).",
        image=_BASIC,
        cmd=["sh", "-lc", "yosys -p 'read_verilog *.v; synth; write_verilog netlist.v'"],
        group="build",
        requires_verilog=True,
    ),
    "verification": ToolSpec(
        id="verification",
        label="Doğrulama",
        description="Lint + smoke testi tek geçişte.",
        image=_BASIC,
        cmd=["sh", "-lc", "set -e; verilator --lint-only --Wall *.v && iverilog -o /tmp/v.out *.v && echo 'VERIFY OK'"],
        group="build",
        requires_verilog=True,
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
        requires_verilog=True,
    ),
}
TOOL_CATALOG.update(_build_openlane1_catalog())


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
