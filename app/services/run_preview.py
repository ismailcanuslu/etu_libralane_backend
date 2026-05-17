"""Job başlatmadan önce çalışma dizini ve dosya önizlemesi."""

from __future__ import annotations

import fnmatch
import json
import shlex

from app.core.config import get_settings
from app.core import storage
from app.services.openlane_layout import flow_input_keys, resolve_design_name
from app.services.pdk_info import get_pdk_runtime_info
from app.tools_catalog import build_tool_command, get_tool

# Araç → tipik çıktı dosyaları (workspace köküne göre)
_OUTPUT_HINTS: dict[str, list[str]] = {
    "synthesis": ["netlist.v"],
    "lint": [],
    "verification": [],
    "simulation": ["sim.vvp", "*.vcd", "tb/*.vcd"],
    "openlane1-flow": ["runs/", "openlane/", "netlist.v"],
}

_INPUT_PATTERNS: dict[str, list[str]] = {
    "synthesis": ["verilog/rtl/*.v", "src/*.v", "*.v"],
    "lint": ["verilog/rtl/*.v", "src/*.v", "*.v"],
    "verification": ["verilog/rtl/*.v", "src/*.v", "*.v"],
    "simulation": ["verilog/rtl/*.v", "src/*.v", "*.v", "tb/tb_*.v", "tb_*.v"],
    "openlane1-flow": [
        "flow.tcl",
        "openlane/user_project_wrapper/config.json",
        "openlane/*/config.json",
        "verilog/rtl/*.v",
        "verilog/rtl/user_project_wrapper.v",
        "src/*.v",
    ],
}


def _match_patterns(keys: list[str], patterns: list[str]) -> list[str]:
    found: list[str] = []
    for pattern in patterns:
        if "*" in pattern:
            found.extend(sorted({k for k in keys if fnmatch.fnmatch(k, pattern)}))
        elif pattern in keys or any(k == pattern or k.startswith(pattern) for k in keys):
            if pattern.endswith("/"):
                found.extend(sorted(k for k in keys if k.startswith(pattern)))
            elif pattern in keys:
                found.append(pattern)
    return sorted(set(found))


def _openlane_flow_default_files(project_id: str, matched: list[str]) -> list[str]:
    """Flow oncesi zorunlu Caravel dosyalarini varsayilan secime ekle."""
    mandatory = set(flow_input_keys(project_id))
    return sorted(set(matched) | mandatory)


def _simulation_default_files(keys: list[str], matched: list[str]) -> list[str]:
    """Caravel dizinindeyse yalnizca verilog/rtl + tb/tb_*.v oner (counter_tb ile karismasin)."""
    rtl = sorted(k for k in matched if k.startswith("verilog/rtl/") and k.endswith(".v"))
    tb_caravel = sorted(k for k in matched if fnmatch.fnmatch(k, "tb/tb_*.v"))
    if rtl:
        return sorted(set(rtl + tb_caravel))
    return list(matched)


def build_run_preview(
    project_id: str,
    action: str,
    *,
    design_name: str | None = None,
) -> dict:
    settings = get_settings()
    spec = get_tool(action)
    if spec is None:
        raise ValueError(f"unknown action: {action}")

    design = resolve_design_name(project_id, design_name) if spec.kind == "flow" else None
    try:
        command = build_tool_command(spec, design_name=design, extra_args=None)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    objects = storage.list_objects(
        project_id,
        "",
        recursive=True,
        exclude_prefixes=[f"{settings.jobs_artifacts_prefix}/"],
    )
    keys = [o.key for o in objects]

    input_patterns = _INPUT_PATTERNS.get(action, ["src/*.v", "*.v"])
    input_files = _match_patterns(keys, input_patterns)
    output_hints = _OUTPUT_HINTS.get(action, [])

    warnings: list[str] = []
    if spec.requires_verilog and not any(k.endswith(".v") for k in keys):
        warnings.append("Projede .v dosyası bulunamadı (verilog/rtl, src/ veya kök).")
    if spec.requires_config and not any(
        k.endswith("config.json") or k.endswith("config.tcl") for k in keys
    ):
        warnings.append("config.json veya config.tcl bulunamadı.")
    if spec.kind == "flow" and "flow.tcl" not in keys:
        warnings.append("flow.tcl bulunamadı (openlane1-flow için gerekli).")
    if action == "simulation":
        has_caravel_tb = any(fnmatch.fnmatch(k, "tb/tb_*.v") for k in keys)
        has_legacy_tb = any(fnmatch.fnmatch(k, "tb/*_tb.v") for k in keys)
        if has_caravel_tb and has_legacy_tb:
            warnings.append(
                "Hem Caravel testbench (tb/tb_*.v) hem eski tb/*_tb.v var; "
                "simülasyon yalnızca tb/tb_*.v kullanır. counter_tb'yi listeden çıkarabilirsiniz."
            )

    if action == "simulation":
        default_input_files = _simulation_default_files(keys, input_files)
    elif action == "openlane1-flow":
        default_input_files = _openlane_flow_default_files(project_id, input_files)
    else:
        default_input_files = list(input_files)

    pdk = get_pdk_runtime_info()
    job_workspace_template = f"{settings.jobs_host_dir}/<job_id>/workspace"

    return {
        "action": spec.id,
        "label": spec.label,
        "description": spec.description,
        "project_id": project_id,
        "design_name": design,
        "image": spec.image,
        "command": command,
        # bash -lc: script govdesini ayri satirda goster (tek satirli '"'"' kacisi kopyalamada kirilir)
        "command_display": (
            f"{command[0]} {command[1]}\n{command[2]}"
            if len(command) == 3 and command[0] == "bash" and command[1] in ("-lc", "-c")
            else " ".join(shlex.quote(p) for p in command)
        ),
        "workspace_root": str(settings.workspace_root),
        "project_path": f"{settings.workspace_root}/{project_id}",
        "job_workspace_template": job_workspace_template,
        "container_workdir": settings.jobs_workdir_in_runner,
        "pdk": pdk,
        "input_files": input_files,
        "default_input_files": default_input_files,
        "output_hints": output_hints,
        "warnings": warnings,
        "requires_pdk": spec.requires_pdk,
    }
