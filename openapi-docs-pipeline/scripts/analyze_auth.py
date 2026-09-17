#!/usr/bin/env python3
"""Inspect OpenAPI ops for auth signals (headers, cookies, body fields)."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "openapi.raw.yaml"

AUTH_HEADER_NAMES = {
    "authorization",
    "x-token",
    "x-access-token",
    "x-auth-token",
    "token",
    "access-token",
    "x-api-token",
    "x-csrf-token",
    "x-xsrf-token",
}


def walk_examples(obj, found: set[str]):
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in AUTH_HEADER_NAMES or kl in {"cookie", "set-cookie"}:
                found.add(kl)
            if kl in {"token", "access_token", "accessToken", "bearer", "api_token"}:
                found.add(f"body/field:{kl}")
            walk_examples(v, found)
    elif isinstance(obj, list):
        for i in obj:
            walk_examples(i, found)


def main() -> None:
    with RAW.open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    header_names = Counter()
    cookie_ops = []
    auth_ops = []
    all_headers_by_op = {}

    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method in ("parameters",) or str(method).startswith("x-"):
                continue
            if method.lower() == "options":
                continue
            if not isinstance(op, dict):
                continue
            key = f"{method.upper()} {path}"
            headers = []
            for p in op.get("parameters") or []:
                if p.get("in") == "header":
                    name = p.get("name") or ""
                    headers.append(name)
                    header_names[name.lower()] += 1
                    if name.lower() in AUTH_HEADER_NAMES or name.lower() == "cookie":
                        auth_ops.append((key, name, (p.get("schema") or {}).get("example")))
            # path-level params
            for p in item.get("parameters") or []:
                if p.get("in") == "header":
                    name = p.get("name") or ""
                    headers.append(name)
                    header_names[name.lower()] += 1

            signals = set()
            walk_examples(op, signals)
            all_headers_by_op[key] = sorted(set(headers))
            if signals or any(h.lower() in AUTH_HEADER_NAMES or h.lower() == "cookie" for h in headers):
                auth_ops.append((key, "signals", sorted(signals)))

    print("=== header frequency (top 40) ===")
    for name, n in header_names.most_common(40):
        print(f"{n:4} {name}")

    print("\n=== ops with auth-like headers/signals ===")
    seen = set()
    for row in auth_ops:
        if row[0] in seen:
            continue
        seen.add(row[0])
        print(row)

    # Sample Authorization / Cookie examples from a few ops
    print("\n=== sample auth header examples ===")
    count = 0
    for path, item in (spec.get("paths") or {}).items():
        for method, op in item.items():
            if not isinstance(op, dict) or method.lower() == "options":
                continue
            for p in op.get("parameters") or []:
                if p.get("in") != "header":
                    continue
                name = (p.get("name") or "").lower()
                if name in AUTH_HEADER_NAMES or name == "cookie":
                    ex = (p.get("schema") or {}).get("example")
                    print(f"{method.upper()} {path}")
                    print(f"  {p.get('name')}: {str(ex)[:200] if ex else None}")
                    count += 1
            if count >= 25:
                break
        if count >= 25:
            break

    # Check response examples for unauthenticated hints
    print("\n=== response message samples (status/message) ===")
    samples = []
    for path, item in (spec.get("paths") or {}).items():
        for method, op in item.items():
            if not isinstance(op, dict) or method.lower() == "options":
                continue
            for code, resp in (op.get("responses") or {}).items():
                if not isinstance(resp, dict):
                    continue
                for media in (resp.get("content") or {}).values():
                    ex = media.get("example")
                    if isinstance(ex, dict) and ("message" in ex or "status" in ex):
                        samples.append((f"{method.upper()} {path}", code, ex.get("status"), str(ex.get("message"))[:80]))
    for s in samples[:40]:
        print(s)


if __name__ == "__main__":
    main()
