#!/usr/bin/env python3
"""Merge a new Proxyman OpenAPI YAML into openapi.raw.yaml (union of paths/ops)."""

from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "openapi.raw.yaml"
BACKUP_DIR = ROOT / "imports"


def op_score(op: dict) -> int:
    score = 0
    score += len(op.get("parameters") or [])
    score += 5 if "requestBody" in op else 0
    for resp in (op.get("responses") or {}).values():
        if isinstance(resp, dict) and resp.get("content"):
            score += 3
            for media in (resp.get("content") or {}).values():
                if isinstance(media, dict) and media.get("example") is not None:
                    score += 2
    return score


def merge_path_item(a: dict, b: dict) -> dict:
    out = deepcopy(a) if a else {}
    b = b or {}
    # path-level parameters: keep longer list
    if len(b.get("parameters") or []) > len(out.get("parameters") or []):
        out["parameters"] = deepcopy(b["parameters"])
    for method, op in b.items():
        if method == "parameters" or str(method).startswith("x-"):
            continue
        if not isinstance(op, dict):
            continue
        if method not in out or not isinstance(out.get(method), dict):
            out[method] = deepcopy(op)
            continue
        if op_score(op) > op_score(out[method]):
            out[method] = deepcopy(op)
    return out


def main(new_path: str) -> None:
    src = Path(new_path)
    if not src.is_file():
        raise SystemExit(f"not found: {src}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    archived = BACKUP_DIR / src.name
    if archived.exists():
        archived = BACKUP_DIR / f"{src.stem}_{src.stat().st_mtime_ns}{src.suffix}"
    shutil.copy2(src, archived)

    with src.open(encoding="utf-8") as f:
        incoming = yaml.safe_load(f) or {}

    if RAW.exists():
        with RAW.open(encoding="utf-8") as f:
            base = yaml.safe_load(f) or {}
        # also backup current raw
        shutil.copy2(RAW, BACKUP_DIR / f"openapi.raw.before_{src.stem}.yaml")
    else:
        base = {
            "openapi": incoming.get("openapi", "3.0.0"),
            "info": incoming.get("info") or {},
            "paths": {},
        }

    base_paths = base.setdefault("paths", {})
    in_paths = incoming.get("paths") or {}

    before = sum(
        1
        for item in base_paths.values()
        if isinstance(item, dict)
        for m in item
        if m != "parameters" and not str(m).startswith("x-")
    )
    added = 0
    updated = 0
    for path, item in in_paths.items():
        if not isinstance(item, dict):
            continue
        if path not in base_paths:
            base_paths[path] = deepcopy(item)
            added += 1
        else:
            old = base_paths[path]
            merged = merge_path_item(old, item)
            if merged != old:
                updated += 1
            base_paths[path] = merged

    # keep server from either
    if not base.get("servers") and incoming.get("servers"):
        base["servers"] = incoming["servers"]

    base.setdefault("info", {})
    base["info"]["title"] = base["info"].get("title") or "HarToOpenApi"
    desc = base["info"].get("description") or ""
    note = f"Merged import: {src.name}"
    if note not in desc:
        base["info"]["description"] = (desc + " | " + note).strip(" |")

    with RAW.open("w", encoding="utf-8") as f:
        yaml.dump(
            base,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        )

    after = sum(
        1
        for item in base_paths.values()
        if isinstance(item, dict)
        for m in item
        if m != "parameters" and not str(m).startswith("x-")
    )
    print(f"Archived new file -> {archived}")
    print(f"Raw paths: {len(base_paths)}")
    print(f"Ops before merge: {before}, after: {after} (path groups added: {added}, updated: {updated})")
    print(f"Wrote {RAW}")


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else ""
    if not path:
        raise SystemExit("usage: merge_raw_openapi.py <new.yaml>")
    main(path)
