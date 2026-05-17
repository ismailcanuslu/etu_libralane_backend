"""Caravel user project dizin ve design adı yardımcıları."""

from __future__ import annotations

from pathlib import Path

from app.core.workspace_paths import project_dir

# Efabless Caravel user project ile uyumlu sabit design adları
CARAVEL_WRAPPER_DESIGN = "user_project_wrapper"
CARAVEL_USER_MODULE_DESIGN = "user_module"
CARAVEL_RTL_DIR = "verilog/rtl"
CARAVEL_HARNESS_NOTE = "caravel/README.md"


def caravel_rtl_dir(project_id: str) -> Path:
    return project_dir(project_id) / CARAVEL_RTL_DIR


def has_caravel_scaffold(project_id: str) -> bool:
    base = project_dir(project_id)
    return (base / CARAVEL_RTL_DIR / "user_project_wrapper.v").is_file()


def find_caravel_openlane_design(project_id: str) -> str | None:
    """openlane/ altında Caravel tipik design klasörünü seçer."""
    openlane_root = project_dir(project_id) / "openlane"
    if not openlane_root.is_dir():
        return None
    for preferred in (CARAVEL_WRAPPER_DESIGN, CARAVEL_USER_MODULE_DESIGN):
        cfg = openlane_root / preferred / "config.json"
        if cfg.is_file():
            return preferred
    return None
