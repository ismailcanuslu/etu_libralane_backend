"""OpenLane configuration README → yapılandırılmış katalog."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROW_RE = re.compile(
    r"^\|\s*`([A-Z0-9_]+)`\s*\|\s*(.+?)\s*\|\s*$"
)
_DEFAULT_RE = re.compile(
    r"\(Default:\s*`([^`]+)`\)|\(Default:\s*([^)]+?)\)",
    re.IGNORECASE,
)
_CATEGORY_SLUG: dict[str, str] = {
    "Synthesis": "synthesis",
    "Floorplanning": "floorplanning",
    "Placement": "placement",
    "CTS": "cts",
    "Routing": "routing",
    "Magic": "magic",
    "LVS": "lvs",
    "Misc": "misc",
    "Flow control": "flow_control",
    "Checkers": "checkers",
}

_CATEGORY_LABEL_TR: dict[str, str] = {
    "required": "Zorunlu",
    "synthesis": "Sentez",
    "floorplanning": "Yerleşim planı",
    "placement": "Yerleşim",
    "cts": "CTS (saat ağacı)",
    "routing": "Yönlendirme",
    "magic": "Magic",
    "lvs": "LVS",
    "misc": "Diğer",
    "flow_control": "Akış kontrolü",
    "checkers": "Denetleyiciler",
}

# Iskelet config.json ile karşılaştırma (project_scaffold)
SCAFFOLD_RECOMMENDED_KEYS = (
    "DESIGN_NAME",
    "VERILOG_FILES",
    "CLOCK_PORT",
    "CLOCK_PERIOD",
    "FP_CORE_UTIL",
    "PL_TARGET_DENSITY",
    "DESIGN_IS_CORE",
)

OPENLANE_REQUIRED_KEYS = (
    "DESIGN_NAME",
    "VERILOG_FILES",
    "CLOCK_PERIOD",
    "CLOCK_NET",
    "CLOCK_PORT",
)


def _extract_default(desc: str) -> str | None:
    m = _DEFAULT_RE.search(desc)
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").strip().rstrip(".")


def _infer_value_kind(desc: str) -> str:
    low = desc.lower()
    if "enabled = 1" in low or "0 = disabled" in low or "1 = enabled" in low:
        return "flag"
    if "possible values" in low:
        return "enum"
    return "text"


def _to_tr(description_en: str) -> str:
    """Basit kural tabanlı TR — teknik terimler korunur."""
    tr = description_en
    rules: list[tuple[str, str]] = [
        (r"^The name of the top level module of the design$", "Tasarımın üst seviye modül adı."),
        (r"^The path of the design's verilog files$", "Tasarımın Verilog dosya yolu."),
        (r"^The clock period for the design in ns$", "Tasarımın saat periyodu (ns)."),
        (
            r"^The name of the Net input to root clock buffer used in Clock Tree Synthesis\.$",
            "Saat ağacı sentezinde kök saat tamponuna giren net adı.",
        ),
        (
            r"^The name of the design's clock port used in Static Timing Analysis\.$",
            "Statik zamanlama analizinde kullanılan saat portu adı.",
        ),
        ("Specifies whether", "Belirler:"),
        ("Specifies the", "Belirtilen:"),
        ("Specifies ", "Belirtir: "),
        ("Decides whether", "Karar verir:"),
        ("Enables ", "Etkinleştirir: "),
        ("Enable ", "Etkinleştirir: "),
        ("Points to the", "Şu dosyaya işaret eder:"),
        ("Points to ", "İşaret eder: "),
        ("The library used for synthesis", "Sentezde Yosys tarafından kullanılan kütüphane"),
        ("The desired placement density", "Hücrelerin çekirdek alanındaki hedef yerleşim yoğunluğu"),
        ("The core utilization percentage", "Çekirdek kullanım yüzdesi"),
        ("The number of lowest layer", "Yönlendirmede kullanılacak en alt metal katman numarası"),
        ("The number of highest layer", "Yönlendirmede kullanılacak en üst metal katman numarası"),
        ("Checks if", "Kontrol eder:"),
        ("Checks for", "Kontrol eder:"),
        ("A flag to", "Bayrak:"),
        ("A flag that", "Bayrak:"),
        ("Optional.", "İsteğe bağlı."),
        (" Enabled = 1, Disabled = 0", " Açık = 1, Kapalı = 0"),
        (" 1 = Enabled, 0 = Disabled", " 1 = Açık, 0 = Kapalı"),
        (" 1 = Enabled, 0 = Disabled", " 1 = Açık, 0 = Kapalı"),
        (" 0 = false, 1 = true", " 0 = hayır, 1 = evet"),
        (" 0 = Disabled, 1 = Enabled", " 0 = Kapalı, 1 = Açık"),
        ("(Default:", "(Varsayılan:"),
        ("Default:", "Varsayılan:"),
        ("percent)", "yüzde)"),
        (" in ns", " ns cinsinden"),
        ("microns", "mikron"),
    ]
    for pat, repl in rules:
        tr = re.sub(pat, repl, tr, flags=re.IGNORECASE) if pat.startswith("^") else tr.replace(pat, repl)
    return tr.strip()


def parse_readme_markdown(text: str) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    current_category = "misc"
    in_required = False

    for line in text.splitlines():
        if line.strip() == "## Required variables":
            in_required = True
            current_category = "required"
            continue
        if line.strip() == "## Optional variables":
            in_required = False
            continue
        if line.startswith("### "):
            title = line[4:].strip()
            current_category = _CATEGORY_SLUG.get(title, title.lower().replace(" ", "_"))
            in_required = False
            continue
        m = _ROW_RE.match(line)
        if not m:
            continue
        key, desc = m.group(1), m.group(2).strip()
        if key in ("Variable",):
            continue
        default = _extract_default(desc)
        variables[key] = {
            "category": "required" if in_required else current_category,
            "required": in_required,
            "default": default,
            "description_en": desc,
            "description_tr": _to_tr(desc),
            "value_kind": _infer_value_kind(desc),
        }

    categories = {
        slug: {"label_tr": label}
        for slug, label in _CATEGORY_LABEL_TR.items()
    }

    return {
        "version": "mattvenn-openlane-master",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_url": "https://raw.githubusercontent.com/mattvenn/openlane/refs/heads/master/configuration/README.md",
        "required_keys": list(OPENLANE_REQUIRED_KEYS),
        "scaffold_recommended_keys": list(SCAFFOLD_RECOMMENDED_KEYS),
        "categories": categories,
        "variables": variables,
    }


def catalog_data_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "openlane_config_catalog.json"


def load_catalog() -> dict[str, Any]:
    path = catalog_data_path()
    if not path.is_file():
        return {"variables": {}, "categories": {}, "required_keys": [], "scaffold_recommended_keys": []}
    return json.loads(path.read_text(encoding="utf-8"))


def search_variables(catalog: dict[str, Any], query: str, category: str | None = None) -> list[str]:
    q = query.strip().upper()
    if len(q) < 2:
        return []
    out: list[str] = []
    for key, meta in catalog.get("variables", {}).items():
        if category and meta.get("category") != category:
            continue
        if key.startswith(q):
            out.append(key)
    return sorted(out)[:40]
