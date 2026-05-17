"""OpenLane 1.2 flow.tcl makro aşamaları (logdaki ~80 [STEP N] alt adımı bunların içinde çalışır)."""

from __future__ import annotations

from typing import TypedDict


class FlowStage(TypedDict):
    id: str
    label_tr: str
    label_en: str
    description_tr: str


OPENLANE1_FLOW_STAGES: list[FlowStage] = [
    {
        "id": "verilator_lint_check",
        "label_en": "Verilator lint",
        "label_tr": "Verilator lint",
        "description_tr": "RTL lint (Verilator) — isteğe bağlı hızlı kontrol.",
    },
    {
        "id": "synthesis",
        "label_en": "Synthesis",
        "label_tr": "Sentez",
        "description_tr": "Yosys ile sentez ve ilk netlist.",
    },
    {
        "id": "floorplan",
        "label_en": "Floorplan",
        "label_tr": "Floorplan",
        "description_tr": "Yerleşim alanı ve güç şebekesi.",
    },
    {
        "id": "placement",
        "label_en": "Placement",
        "label_tr": "Placement",
        "description_tr": "Hücre yerleşimi ve optimizasyon.",
    },
    {
        "id": "cts",
        "label_en": "CTS",
        "label_tr": "CTS",
        "description_tr": "Clock tree sentezi.",
    },
    {
        "id": "routing",
        "label_en": "Routing",
        "label_tr": "Routing",
        "description_tr": "Detaylı yönlendirme.",
    },
    {
        "id": "parasitics_sta",
        "label_en": "Parasitics STA",
        "label_tr": "Parasitik STA",
        "description_tr": "Parasitik çıkarım ve statik zamanlama.",
    },
    {
        "id": "irdrop",
        "label_en": "IR drop",
        "label_tr": "IR drop",
        "description_tr": "IR drop raporu.",
    },
    {
        "id": "gds_magic",
        "label_en": "GDS (Magic)",
        "label_tr": "GDS (Magic)",
        "description_tr": "Magic ile GDSII üretimi.",
    },
    {
        "id": "gds_klayout",
        "label_en": "GDS (KLayout)",
        "label_tr": "GDS (KLayout)",
        "description_tr": "KLayout ile GDSII ve görselleştirme.",
    },
    {
        "id": "lvs",
        "label_en": "LVS",
        "label_tr": "LVS",
        "description_tr": "Layout vs schematic.",
    },
    {
        "id": "drc",
        "label_en": "DRC",
        "label_tr": "DRC",
        "description_tr": "Design rule check.",
    },
    {
        "id": "antenna_check",
        "label_en": "Antenna check",
        "label_tr": "Antenna",
        "description_tr": "Antenna ve son kontroller.",
    },
]

OPENLANE1_FLOW_STAGE_IDS: list[str] = [s["id"] for s in OPENLANE1_FLOW_STAGES]
OPENLANE1_GDS_STAGE_IDS: frozenset[str] = frozenset({"gds_magic", "gds_klayout"})

# Atölye / hızlı deneme: placement sonrası CTS, routing, GDS yok
OPENLANE1_PLACEMENT_PRESET_IDS: list[str] = OPENLANE1_FLOW_STAGE_IDS[
    : OPENLANE1_FLOW_STAGE_IDS.index("placement") + 1
]


def placement_flow_step_ids() -> list[str]:
    return list(OPENLANE1_PLACEMENT_PRESET_IDS)


def normalize_flow_steps(selected: list[str] | None) -> list[str] | None:
    """None veya tüm aşamalar → tam akış (flow.tcl). Aksi halde sıralı alt küme."""
    if not selected:
        return None
    cleaned = [s.strip() for s in selected if isinstance(s, str) and s.strip()]
    if not cleaned:
        return None
    unknown = [s for s in cleaned if s not in OPENLANE1_FLOW_STAGE_IDS]
    if unknown:
        raise ValueError(f"Bilinmeyen OpenLane aşaması: {', '.join(unknown)}")
    ordered = [sid for sid in OPENLANE1_FLOW_STAGE_IDS if sid in cleaned]
    if len(ordered) == len(OPENLANE1_FLOW_STAGE_IDS):
        return None
    return ordered


def flow_steps_for_api() -> list[dict]:
    return [
        {
            "id": s["id"],
            "label": s["label_tr"],
            "label_en": s["label_en"],
            "description": s["description_tr"],
        }
        for s in OPENLANE1_FLOW_STAGES
    ]
