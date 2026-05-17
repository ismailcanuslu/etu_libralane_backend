"""OpenLane config.json / yaml patch — skaler ve çok boyutlu değerler."""

from __future__ import annotations

import json
from typing import Any

import yaml

from app.services.autonom_spec import AutonomCampaignSpec, ParamSpec, format_param_label


def _config_format_from_key(config_key: str) -> str:
    base = config_key.split("/")[-1].lower()
    if base.endswith(".yaml"):
        return "yaml"
    if base.endswith(".yml"):
        return "yml"
    return "json"


def parse_config_bytes(content: bytes, config_key: str) -> dict[str, Any]:
    text = content.decode("utf-8")
    fmt = _config_format_from_key(config_key)
    if fmt == "json":
        data = json.loads(text or "{}")
    else:
        data = yaml.safe_load(text or "{}")
    if not isinstance(data, dict):
        raise ValueError("Config kökü bir nesne olmalı")
    return data


def serialize_config(data: dict[str, Any], config_key: str) -> bytes:
    fmt = _config_format_from_key(config_key)
    if fmt == "json":
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    else:
        text = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
        if not text.endswith("\n"):
            text += "\n"
    return text.encode("utf-8")


def _config_value_for_param(value: Any, param: ParamSpec) -> Any:
    kind = param.get("kind") or "scalar"
    serialize_as = param.get("serialize_as")

    if kind == "scalar":
        if serialize_as == "string":
            return format_param_label(value, param)
        if isinstance(value, float) and value == int(value):
            return int(value)
        return value

    if kind == "dimension_pair":
        fmt = serialize_as or "space_pair"
        w, h = value[0], value[1]
        if fmt == "times_string":
            return format_param_label(value, param)
        if fmt == "json_array":
            return [w, h]
        return format_param_label(value, param)

    # die_area_rect → string "x1 y1 x2 y2"
    return str(value)


def patch_config_content(
    content: bytes,
    config_key: str,
    param: ParamSpec,
    iteration_value: Any,
) -> bytes:
    data = parse_config_bytes(content, config_key)
    flag = param["flag"].strip()
    data[flag] = _config_value_for_param(iteration_value, param)
    return serialize_config(data, config_key)
