#!/usr/bin/env python3
"""OpenLane configuration README → openlane_config_catalog.json"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.openlane_config_catalog import catalog_data_path, parse_readme_markdown  # noqa: E402

README_URL = (
    "https://raw.githubusercontent.com/mattvenn/openlane/refs/heads/master/configuration/README.md"
)


def main() -> None:
    with urllib.request.urlopen(README_URL, timeout=60) as resp:
        text = resp.read().decode("utf-8")
    catalog = parse_readme_markdown(text)
    out = catalog_data_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        __import__("json").dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    n = len(catalog.get("variables", {}))
    print(f"Wrote {n} variables to {out}")


if __name__ == "__main__":
    main()
