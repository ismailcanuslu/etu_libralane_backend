"""Job.command alanini JSON (argv listesi veya {argv, flow_steps}) olarak kodlar."""

from __future__ import annotations

import json
from typing import Any


def encode_job_command(argv: list[str], *, flow_steps: list[str] | None = None) -> str:
    if flow_steps:
        return json.dumps({"argv": argv, "flow_steps": flow_steps})
    return json.dumps(argv)


def decode_job_command(raw: str) -> tuple[list[str], list[str] | None]:
    parsed: Any = json.loads(raw)
    if isinstance(parsed, dict) and "argv" in parsed:
        argv = parsed["argv"]
        if not isinstance(argv, list):
            raise ValueError("job command argv must be a list")
        steps = parsed.get("flow_steps")
        if steps is None:
            return [str(p) for p in argv], None
        if not isinstance(steps, list):
            raise ValueError("job command flow_steps must be a list")
        return [str(p) for p in argv], [str(s) for s in steps]
    if isinstance(parsed, list):
        return [str(p) for p in parsed], None
    raise ValueError("job command must be a JSON list or {argv, flow_steps}")
