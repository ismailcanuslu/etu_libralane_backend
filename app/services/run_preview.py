"""Job başlatmadan önce çalışma dizini ve dosya önizlemesi."""

from __future__ import annotations

import json
import shlex

from app.core.config import get_settings
from app.core import storage
from app.services.openlane_layout import resolve_design_name
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
    import fnmatch

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
        "command_display": " ".join(shlex.quote(p) for p in command),
        "workspace_root": str(settings.workspace_root),
        "project_path": f"{settings.workspace_root}/{project_id}",
        "job_workspace_template": job_workspace_template,
        "container_workdir": settings.jobs_workdir_in_runner,
        "pdk": pdk,
        "input_files": input_files,
        "default_input_files": list(input_files),
        "output_hints": output_hints,
        "warnings": warnings,
        "requires_pdk": spec.requires_pdk,
    }
