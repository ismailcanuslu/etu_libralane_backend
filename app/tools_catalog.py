import shlex
from dataclasses import dataclass, replace
from typing import Dict, List, Literal

from app.core.config import get_settings
from app.services.openlane_layout import simulation_verilog_shell, verilog_glob_shell_var

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


_OPENLANE = _settings.runner_image_openlane
_RUNNER = _OPENLANE


def _require_yosys(script: str) -> List[str]:
    return _shell(
        "set -e; command -v yosys >/dev/null 2>&1 || { echo 'yosys bulunamadi'; exit 2; }; "
        f"yosys -p {shlex.quote(script)}"
    )


def _shell(script: str) -> List[str]:
    # efabless/openlane (Nix): yosys/iverilog yalnizca bash login PATH'inde; sh ile bulunamaz
    return ["bash", "-lc", script]


def _openlane_tcllib_setup_shell() -> str:
    """efabless/openlane: flow.tcl-wrapped dar tclsh kullanir; json icin tcllib gerekir."""
    return (
        "if [ -z \"${TCLLIBPATH:-}\" ]; then "
        "for _d in /nix/store/*-tcllib-*/lib/tcllib*; do "
        'if [ -d "$_d" ] && [ -f "$_d/json/json.tcl" ]; then '
        'export TCLLIBPATH="$_d"; break; '
        "fi; done; fi; "
        'if [ -z "${TCLLIBPATH:-}" ]; then '
        "echo 'TCLLIBPATH: tcllib json paketi bulunamadi (OpenLane imaji)'; exit 2; "
        "fi; "
    )


def _flow_script(design_name: str, extra_args: list[str] | None = None) -> str:
    args = ""
    if extra_args:
        args = " " + " ".join(shlex.quote(value) for value in extra_args)
    design = shlex.quote(design_name)
    tcllib = _openlane_tcllib_setup_shell()
    # Proje kokundeki flow.tcl genelde Tcl kaynak dosyasidir (+x degil); ./flow.tcl Permission denied verir.
    # efabless/openlane imajinda PATH'teki flow.tcl openlane/<design>/config.json ile calisir.
    return (
        "set -e; "
        f"{tcllib}"
        "if command -v flow.tcl >/dev/null 2>&1; then "
        f"exec flow.tcl -design {design}{args}; "
        "fi; "
        "if [ -f flow.tcl ]; then "
        "if [ -x flow.tcl ] && head -1 flow.tcl | grep -q '^#!'; then "
        f"exec ./flow.tcl -design {design}{args}; "
        "fi; "
        f"exec tclsh flow.tcl -design {design}{args}; "
        "fi; "
        "echo 'flow.tcl gerekli (OpenLane runner veya proje flow.tcl)'; exit 2"
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
    """Web katalogunda yalnizca tam OpenLane akisi; hub smoke/probe UI'dan kaldirildi."""
    return {
        "openlane1-flow": ToolSpec(
            id="openlane1-flow",
            label="OpenLane1 Flow",
            description=(
                "Caravel user_project_wrapper hardening: flow.tcl + "
                "openlane/user_project_wrapper/config.json "
                "(flow.tcl -design openlane/user_project_wrapper)."
            ),
            image=_RUNNER,
            cmd=[],
            group="build",
            badge="PnR",
            enabled=True,
            kind="flow",
            requires_verilog=True,
            requires_config=True,
            requires_pdk=True,
        ),
    }


TOOL_CATALOG: Dict[str, ToolSpec] = {
    "smoke-test": ToolSpec(
        id="smoke-test",
        label="Smoke Test",
        description="efabless/openlane imajında Yosys ile Verilog dosyalarının okunup okunamadığını dener.",
        image=_RUNNER,
        cmd=_shell(
            f"set -e; {verilog_glob_shell_var()}; "
            "command -v yosys >/dev/null 2>&1 || { echo 'yosys bulunamadi'; exit 2; }; "
            'yosys -p "read_verilog $VF; stat" && echo "SMOKE OK"'
        ),
        group="tools",
        badge="Hızlı",
        requires_verilog=True,
    ),
    "lint": ToolSpec(
        id="lint",
        label="RTL Lint",
        description="efabless/openlane imajında Yosys ile hiyerarşi ve okunabilirlik kontrolü.",
        image=_RUNNER,
        cmd=_shell(
            f"set -e; {verilog_glob_shell_var()}; "
            'yosys -p "read_verilog $VF; hierarchy -check; stat"'
        ),
        group="tools",
        requires_verilog=True,
    ),
    "simulation": ToolSpec(
        id="simulation",
        label="Simülasyon",
        description="efabless/openlane imajında iverilog/vvp varsa testbench koşturur.",
        image=_RUNNER,
        cmd=_shell(
            "set -e; "
            'echo "[librelane] simulasyon basladi"; '
            "command -v iverilog >/dev/null 2>&1 && command -v vvp >/dev/null 2>&1 || "
            '{ echo "[librelane] iverilog/vvp bulunamadi (bash PATH?)"; exit 2; }; '
            f"{simulation_verilog_shell()}; "
            'echo "[librelane] RTL=$VF TB=$TB"; '
            'echo "[librelane] iverilog derleniyor..."; '
            "iverilog -g2012 $INC -o sim.vvp $VF $TB; "
            'echo "[librelane] vvp calistiriliyor (max 600s)..."; '
            "if command -v timeout >/dev/null 2>&1; then "
            "timeout --kill-after=15 600 vvp sim.vvp; "
            "else vvp sim.vvp; fi; "
            'echo "[librelane] simulasyon bitti exit=$?"'
        ),
        group="build",
        requires_verilog=True,
    ),
    "synthesis": ToolSpec(
        id="synthesis",
        label="Sentez",
        description="efabless/openlane imajında Yosys ile gate-level netlist üretir.",
        image=_RUNNER,
        cmd=_shell(
            f"set -e; {verilog_glob_shell_var()}; "
            'yosys -p "read_verilog $VF; synth; write_verilog netlist.v"'
        ),
        group="build",
        requires_verilog=True,
    ),
    "verification": ToolSpec(
        id="verification",
        label="Doğrulama",
        description="efabless/openlane imajında Yosys ile hızlı RTL doğrulaması.",
        image=_RUNNER,
        cmd=_shell(
            f"set -e; command -v yosys >/dev/null 2>&1 || {{ echo 'yosys bulunamadi'; exit 2; }}; "
            f"{verilog_glob_shell_var()}; "
            'yosys -p "read_verilog $VF; stat" && echo "VERIFY OK"'
        ),
        group="build",
        requires_verilog=True,
    ),
}
TOOL_CATALOG.update(_build_openlane1_catalog())


def _effective_spec(spec: ToolSpec) -> ToolSpec:
    if spec.image == _RUNNER and not _settings.enable_openlane_tools:
        return replace(spec, enabled=False)
    return spec


def get_tool(action: str) -> ToolSpec | None:
    spec = TOOL_CATALOG.get(action)
    if spec is None:
        return None
    return _effective_spec(spec)


def list_tools() -> List[ToolSpec]:
    return [_effective_spec(spec) for spec in TOOL_CATALOG.values()]
