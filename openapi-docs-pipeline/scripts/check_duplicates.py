#!/usr/bin/env python3
"""Report duplicate / near-duplicate API operations."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect_ops(spec: dict) -> list[tuple[str, str]]:
    ops: list[tuple[str, str]] = []
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in item:
            if method == "parameters" or method.startswith("x-"):
                continue
            ops.append((method.upper(), path))
    return ops


def main() -> None:
    for label, filename in [("cleaned", "openapi.yaml"), ("raw", "openapi.raw.yaml")]:
        spec = load(ROOT / filename)
        ops = collect_ops(spec)
        print(f"=== {label} ({filename}) ===")
        print(f"operations: {len(ops)}")
        print(f"unique path+method: {len(set(ops))}")
        exact = [k for k, v in Counter(ops).items() if v > 1]
        print(f"exact duplicate path+method: {len(exact)}")
        for d in exact:
            print(f"  {d[0]} {d[1]}")

        # trailing slash variants
        by_base: dict[str, set[str]] = defaultdict(set)
        for method, path in ops:
            by_base[path.rstrip("/") or "/"].add(path)
        slash_groups = {k: v for k, v in by_base.items() if len(v) > 1}
        print(f"trailing-slash variant groups: {len(slash_groups)}")
        for base, variants in sorted(slash_groups.items()):
            print(f"  {base}: {sorted(variants)}")

        # same resource stem with different suffixes that look related
        # e.g. /api/config and /api/config/xxx already separate
        print()

    # Compare raw vs cleaned method mix
    raw = load(ROOT / "openapi.raw.yaml")
    clean = load(ROOT / "openapi.yaml")
    raw_ops = collect_ops(raw)
    clean_ops = collect_ops(clean)
    raw_methods = Counter(m for m, _ in raw_ops)
    clean_methods = Counter(m for m, _ in clean_ops)
    print("=== method counts ===")
    print(f"raw:     {dict(raw_methods)}")
    print(f"cleaned: {dict(clean_methods)}")
    removed = set(raw_ops) - set(clean_ops)
    print(f"removed operations (raw - cleaned): {len(removed)}")
    by_method = Counter(m for m, _ in removed)
    print(f"removed by method: {dict(by_method)}")

    print("\n=== cleaned path list ===")
    for method, path in sorted(clean_ops, key=lambda x: (x[1], x[0])):
        print(f"{method:6} {path}")


if __name__ == "__main__":
    main()
