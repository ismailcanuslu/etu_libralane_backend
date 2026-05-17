"""Atölye kampanya spec doğrulama ve iterasyon değer listesi."""

from __future__ import annotations

import json
from typing import Any, Literal, TypedDict

ParamKind = Literal["scalar", "dimension_pair", "die_area_rect"]
SerializeAs = Literal["number", "string", "space_pair", "times_string", "die_area"]


class ParamSpec(TypedDict, total=False):
    flag: str
    kind: ParamKind
    start: float | int | list[float | int]
    target: float | int | list[float | int]
    step: float | int | list[float | int]
    serialize_as: SerializeAs


class AutonomCampaignSpec(TypedDict, total=False):
    param: ParamSpec
    build_actions: list[str]
    openlane_flow_steps: list[str] | None
    input_files: list[str]


BUILD_ACTION_IDS = ("lint", "synthesis", "verification", "simulation", "openlane1-flow")


def _num(x: Any) -> float:
    if isinstance(x, (int, float)):
        return float(x)
    raise ValueError(f"Sayı bekleniyor: {x!r}")


def _as_pair(value: Any, *, label: str) -> tuple[float, float]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return _num(value[0]), _num(value[1])
    raise ValueError(f"{label} iki elemanlı liste olmalı [w, h]")


def _as_die_area(value: Any) -> tuple[float, float, float, float]:
    if isinstance(value, str):
        parts = value.split()
        if len(parts) != 4:
            raise ValueError("DIE_AREA dört sayıdan oluşmalı: x1 y1 x2 y2")
        return tuple(_num(p) for p in parts)  # type: ignore[return-value]
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return tuple(_num(p) for p in value)  # type: ignore[return-value]
    raise ValueError("die_area_rect için start/target dört sayı veya DIE_AREA string")


def _scalar_sequence(start: float, target: float, step: float) -> list[float]:
    if step == 0:
        return [start]
    values: list[float] = []
    current = start
    if step > 0:
        while current <= target + 1e-9:
            values.append(current)
            if abs(current - target) < 1e-9:
                break
            current += step
    else:
        while current >= target - 1e-9:
            values.append(current)
            if abs(current - target) < 1e-9:
                break
            current += step
    return values


def _pair_sequence(
    start: tuple[float, float],
    target: tuple[float, float],
    step: tuple[float, float],
) -> list[tuple[float, float]]:
    sw, sh = step
    if sw == 0 and sh == 0:
        return [start]
    values: list[tuple[float, float]] = []
    w, h = start
    tw, th = target
    while True:
        values.append((w, h))
        at_target = abs(w - tw) < 1e-9 and abs(h - th) < 1e-9
        if at_target:
            break
        nw, nh = w + sw, h + sh
        # Hedefe ulaşıldı mı (adım yönüne göre)
        w_done = (sw >= 0 and w >= tw) or (sw < 0 and w <= tw)
        h_done = (sh >= 0 and h >= th) or (sh < 0 and h <= th)
        if w_done and h_done:
            break
        w, h = nw, nh
        if len(values) > 10_000:
            raise ValueError("Çok fazla iterasyon; parametreleri kontrol edin")
    return values


def _die_area_sequence(
    start: tuple[float, float, float, float],
    target: tuple[float, float, float, float],
    step: tuple[float, float, float, float],
) -> list[tuple[float, float, float, float]]:
    sw, sh = step[2], step[3]
    s = (start[0], start[1], start[2], start[3])
    t = (target[0], target[1], target[2], target[3])
    pairs = _pair_sequence((s[2], s[3]), (t[2], t[3]), (sw, sh))
    return [(s[0], s[1], w, h) for w, h in pairs]


def list_iteration_values(spec: AutonomCampaignSpec) -> list[Any]:
    """Kampanyadaki tüm parametre değerlerini sırayla döndürür."""
    param = spec.get("param") or {}
    kind: ParamKind = param.get("kind") or "scalar"
    start = param["start"]
    target = param["target"]
    step = param.get("step", 0)

    if kind == "scalar":
        return _scalar_sequence(_num(start), _num(target), _num(step))

    if kind == "dimension_pair":
        sp = _as_pair(start, label="start")
        tp = _as_pair(target, label="target")
        st = _as_pair(step, label="step")
        return [list(p) for p in _pair_sequence(sp, tp, st)]

    if kind == "die_area_rect":
        sd = _as_die_area(start)
        td = _as_die_area(target)
        if isinstance(step, (list, tuple)) and len(step) == 4:
            st = tuple(_num(x) for x in step)  # type: ignore[assignment]
        else:
            st = (0.0, 0.0, _num(step), _num(step))
        return [_format_die_area(a, b, c, d) for a, b, c, d in _die_area_sequence(sd, td, st)]

    raise ValueError(f"Bilinmeyen param.kind: {kind}")


def format_param_label(value: Any, param: ParamSpec) -> str:
    kind = param.get("kind") or "scalar"
    if kind == "scalar":
        v = value
        if isinstance(v, float) and v == int(v):
            return str(int(v))
        return str(v)
    if kind == "dimension_pair":
        w, h = value[0], value[1]
        fmt = param.get("serialize_as") or "space_pair"
        if fmt == "times_string":
            return f"{_fmt_num(w)}x{_fmt_num(h)}"
        return f"{_fmt_num(w)} {_fmt_num(h)}"
    return str(value)


def _format_die_area(a: float, b: float, c: float, d: float) -> str:
    return f"{_fmt_num(a)} {_fmt_num(b)} {_fmt_num(c)} {_fmt_num(d)}"


def _fmt_num(n: float) -> str:
    if abs(n - int(n)) < 1e-9:
        return str(int(n))
    return str(n)


def validate_spec(spec: AutonomCampaignSpec) -> AutonomCampaignSpec:
    param = spec.get("param")
    if not param or not param.get("flag"):
        raise ValueError("param.flag zorunlu")
    kind = param.get("kind") or "scalar"
    if kind not in ("scalar", "dimension_pair", "die_area_rect"):
        raise ValueError(f"Geçersiz param.kind: {kind}")

    actions = spec.get("build_actions") or []
    if not actions:
        raise ValueError("En az bir build aracı seçilmeli")
    unknown = [a for a in actions if a not in BUILD_ACTION_IDS]
    if unknown:
        raise ValueError(f"Bilinmeyen build aracı: {', '.join(unknown)}")

    inputs = spec.get("input_files") or []
    if not inputs:
        raise ValueError("En az bir dosya seçilmeli")

    # Iterasyon listesi üretilebilmeli
    list_iteration_values(spec)
    return spec


def parse_spec_json(raw: str) -> AutonomCampaignSpec:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("spec bir JSON objesi olmalı")
    return validate_spec(data)  # type: ignore[arg-type]


def spec_to_json(spec: AutonomCampaignSpec) -> str:
    return json.dumps(validate_spec(spec), ensure_ascii=False)
