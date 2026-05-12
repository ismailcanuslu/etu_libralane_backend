from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict


class OpenLane1ToolEntry(TypedDict):
    hub_key: str
    label: str
    resolved_bins: list[str]
    probe_argv: str
    smoke_argv: str
    enabled: bool
    notes: str


class OpenLane1Manifest(TypedDict):
    image: str
    platform: str
    tools: list[OpenLane1ToolEntry]


_MANIFEST_PATH = Path(__file__).with_name("openlane1_manifest.json")


@lru_cache(maxsize=1)
def load_openlane1_manifest() -> OpenLane1Manifest:
    with _MANIFEST_PATH.open(encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    tools = data.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("openlane1_manifest.json tools listesi bos")
    return {
        "image": str(data.get("image", "")),
        "platform": str(data.get("platform", "")),
        "tools": tools,
    }


def manifest_hub_keys() -> list[str]:
    return [entry["hub_key"] for entry in load_openlane1_manifest()["tools"]]
