"""OpenLane proje yapısı: design adı, Verilog yolları (Caravel user project oncelikli)."""

from __future__ import annotations

from pathlib import Path

from app.core.workspace_paths import project_dir
from app.services.caravel_layout import (
    CARAVEL_USER_MODULE_DESIGN,
    CARAVEL_WRAPPER_DESIGN,
    find_caravel_openlane_design,
    has_caravel_scaffold,
)


def design_slug_from_project(project_id: str) -> str:
    """openlane/<design>/ klasör adı için güvenli slug."""
    slug = project_id.strip().lower().replace("_", "-")
    return slug or "design"


def find_openlane_design(project_id: str) -> str | None:
    """openlane/<design>/config.json varsa design klasör adını döndürür."""
    caravel = find_caravel_openlane_design(project_id)
    if caravel:
        return caravel
    base = project_dir(project_id)
    openlane_root = base / "openlane"
    if not openlane_root.is_dir():
        return None
    candidates: list[str] = []
    for child in sorted(openlane_root.iterdir()):
        if not child.is_dir():
            continue
        if (child / "config.json").is_file() or (child / "config.tcl").is_file():
            candidates.append(child.name)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        for preferred in (CARAVEL_WRAPPER_DESIGN, CARAVEL_USER_MODULE_DESIGN):
            if preferred in candidates:
                return preferred
        return sorted(candidates)[0]
    if (openlane_root / "config.json").is_file():
        return design_slug_from_project(project_id)
    return None


def flow_input_keys(project_id: str, design_name: str | None = None) -> list[str]:
    """OpenLane1 Flow job workspace icin zorunlu dosya anahtarlari (Caravel oncelikli)."""
    design = resolve_design_name(project_id, design_name)
    base = project_dir(project_id)
    keys: list[str] = []

    def add_if_file(rel: str) -> None:
        if (base / rel).is_file():
            keys.append(rel)

    add_if_file("flow.tcl")
    openlane_root = base / "openlane"
    if openlane_root.is_dir():
        for cfg in sorted(openlane_root.rglob("config.json")):
            keys.append(cfg.relative_to(base).as_posix())
        for cfg in sorted(openlane_root.rglob("config.tcl")):
            keys.append(cfg.relative_to(base).as_posix())
    add_if_file(f"openlane/{design}/pin_order.cfg")
    add_if_file(f"openlane/{design}/interactive.tcl")

    rtl = base / "verilog" / "rtl"
    if rtl.is_dir():
        for path in sorted(rtl.glob("*.v")):
            keys.append(path.relative_to(base).as_posix())
    else:
        src = base / "src"
        if src.is_dir():
            for path in sorted(src.glob("*.v")):
                keys.append(path.relative_to(base).as_posix())

    return sorted(set(keys))


def resolve_design_name(project_id: str, explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    if has_caravel_scaffold(project_id):
        return CARAVEL_WRAPPER_DESIGN
    found = find_openlane_design(project_id)
    if found:
        return found
    return design_slug_from_project(project_id)


def verilog_glob_shell_var() -> str:
    """Shell: VF — Caravel verilog/rtl, sonra src/, sonra kok."""
    return (
        'VF=""; '
        "if ls verilog/rtl/*.v >/dev/null 2>&1; then VF=verilog/rtl/*.v; "
        "elif ls src/*.v >/dev/null 2>&1; then VF=src/*.v; "
        "elif ls *.v >/dev/null 2>&1; then VF=*.v; "
        "else echo 'no .v under verilog/rtl, src/ or project root'; exit 1; fi"
    )


def simulation_verilog_shell() -> str:
    """Tek testbench — tb/*.v hepsini birden derleme (counter_tb + caravel tb cakismaz)."""
    return (
        f"{verilog_glob_shell_var()}; "
        'INC="-I. -Iverilog/rtl -Itb"; '
        'if ls verilog/rtl/*.v >/dev/null 2>&1; then :; '
        'elif ls src/*.v >/dev/null 2>&1; then INC="-I. -Isrc"; fi; '
        'TB=""; if ls tb/tb_*.v >/dev/null 2>&1; then TB=tb/tb_*.v; '
        'elif ls tb/*_tb.v >/dev/null 2>&1; then TB=tb/*_tb.v; '
        'elif ls tb/*.v >/dev/null 2>&1; then TB=tb/*.v; '
        'elif ls tb_*.v >/dev/null 2>&1; then TB=tb_*.v; '
        'else echo "no testbench (tb/tb_*.v veya tb/*_tb.v)"; exit 1; fi'
    )
