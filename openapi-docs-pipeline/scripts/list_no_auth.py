#!/usr/bin/env python3
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
with (ROOT / "openapi.raw.yaml").open(encoding="utf-8") as f:
    spec = yaml.safe_load(f)

for path, item in sorted((spec.get("paths") or {}).items()):
    if not isinstance(item, dict):
        continue
    for method, op in item.items():
        if method in ("parameters",) or str(method).startswith("x-") or method.lower() == "options":
            continue
        if not isinstance(op, dict):
            continue
        headers = {
            (p.get("name") or "").lower()
            for p in (op.get("parameters") or [])
            if p.get("in") == "header"
        }
        has_auth = "authorization" in headers
        mark = "TOKEN" if has_auth else "PUBLIC"
        print(f"{mark:6} {method.upper():6} {path}")
