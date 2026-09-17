#!/usr/bin/env python3
"""Organize Proxyman OpenAPI for admin.demo-platform.example.com (home) into Apidog-friendly YAML."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW_DEFAULT = ROOT / "imports" / "admin.home.yaml"
OUT = ROOT / "backend_admin" / "openapi.admin.yaml"
OUT_DOWNLOADS = ROOT / "imports" / "openapi.admin.yaml"
IMPORTS_DIR = ROOT / "backend_admin" / "imports"

BASE_URL_DEFAULT = "https://admin.demo-platform.example.com"
CSRF_VAR = "{{csrf_token}}"
COOKIE_VAR = "{{cookie}}"

KEEP_METHODS = {"get", "post", "put", "patch", "delete", "head"}
SKIP_PREFIXES = (
    "/images",
    "/imgfly",
    "/img",
    "/favicon.ico",
    "/cdn-cgi",
    "/js",
)

# HTML 頁面（非 JSON API）略過，只保留 API / login / broadcasting
KEEP_PATH_PREFIXES = (
    "/zh-Hant/api/",
    "/zh-Hant/login",
    "/broadcasting/",
)

NOISE_HEADERS = {
    "cf-cache-status",
    "cf-ray",
    "server",
    "alt-svc",
    "nel",
    "report-to",
    "priority",
    "x-powered-by",
    "x-content-type-options",
    "x-frame-options",
    "x-xss-protection",
    "strict-transport-security",
    "content-security-policy",
    "access-control-allow-origin",
    "access-control-allow-methods",
    "access-control-allow-headers",
    "access-control-allow-credentials",
    "access-control-max-age",
    "vary",
    "date",
    "connection",
    "transfer-encoding",
    "content-encoding",
    "content-length",
    "etag",
    "set-cookie",
    "accept-encoding",
    "accept-language",
    "user-agent",
    "origin",
    "referer",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "sec-fetch-user",
    "upgrade-insecure-requests",
    "dnt",
    "x-socket-id",
    "host",
    "content-type",
    "accept",
}

ID_SEGMENT_RE = re.compile(
    r"^(?:"
    r"[0-9a-hjkmnp-z]{26}"
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"|[0-9a-f]{16,}"
    r")$",
    re.I,
)

TAG_RULES: list[tuple[str, str]] = [
    ("/zh-Hant/login", "認證與登入"),
    ("/zh-Hant/api/dashboard", "儀表板"),
    ("/zh-Hant/api/finance", "財務 API"),
    ("/zh-Hant/api/quick-menu", "選單"),
    ("/zh-Hant/api/", "其他 API"),
    ("/broadcasting", "即時通訊"),
]

PATH_ZH = {
    "/zh-Hant/login": "登入",
    "/zh-Hant/api/dashboard/fetch-all-descendant-member": "下線會員數",
    "/zh-Hant/api/dashboard/fetch-deposit": "存款統計",
    "/zh-Hant/api/dashboard/fetch-first-deposit": "首存統計",
    "/zh-Hant/api/dashboard/fetch-last-week-win-lose": "上週輸贏",
    "/zh-Hant/api/dashboard/fetch-member": "會員統計",
    "/zh-Hant/api/dashboard/fetch-this-month-win-lose": "本月輸贏",
    "/zh-Hant/api/dashboard/fetch-this-week-win-lose": "本週輸贏",
    "/zh-Hant/api/dashboard/fetch-today-win-lose": "今日輸贏",
    "/zh-Hant/api/dashboard/fetch-total-gift": "贈禮次數",
    "/zh-Hant/api/dashboard/fetch-total-gift-amount": "贈禮金額",
    "/zh-Hant/api/dashboard/fetch-withdraw": "提款統計",
    "/zh-Hant/api/finance/user-market/deposit-amount": "市商存款金額",
    "/zh-Hant/api/finance/user-market/deposit-record": "市商存款紀錄",
    "/zh-Hant/api/quick-menu/list": "快捷選單",
    "/zh-Hant/api/quick-menu/save": "儲存快捷選單",
    "/broadcasting/auth": "廣播認證",
}


def path_base(path: str) -> str:
    return path.split("?")[0].rstrip("/") or "/"


def should_skip(path: str) -> bool:
    p = path_base(path)
    if any(p == pref or p.startswith(pref + "/") or p.startswith(pref) for pref in SKIP_PREFIXES):
        return True
    if p.startswith("/zh-Hant/api/") or p == "/zh-Hant/login" or p.startswith("/broadcasting"):
        return False
    # skip HTML pages
    return True


def normalize_path(path: str) -> tuple[str, list[str]]:
    parts = [x for x in path.split("?")[0].split("/") if x]
    names: list[str] = []
    out: list[str] = []
    for seg in parts:
        if ID_SEGMENT_RE.match(seg):
            name = "id" if "id" not in names else f"id{len(names)+1}"
            names.append(name)
            out.append("{" + name + "}")
        else:
            out.append(seg)
    return ("/" + "/".join(out) if out else "/"), names


def resolve_tag(path: str) -> str:
    p = path_base(path)
    best = None
    for prefix, title in TAG_RULES:
        if p == prefix or p.startswith(prefix + "/") or p.startswith(prefix):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, title)
    return best[1] if best else "其他"


def zh_for_path(path: str) -> str:
    p = path_base(path)
    if p in PATH_ZH:
        return PATH_ZH[p]
    for key, zh in sorted(PATH_ZH.items(), key=lambda x: -len(x[0])):
        if p.startswith(key):
            rest = p[len(key) :].strip("/")
            return f"{zh}（{rest}）" if rest else zh
    return p.rstrip("/").split("/")[-1].replace("-", " ")


def method_zh(method: str) -> str:
    return {"get": "查詢", "post": "提交", "put": "更新", "patch": "部分更新", "delete": "刪除"}.get(
        method.lower(), method.upper()
    )


def redact(obj):
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        # long session / jwt-like blobs
        if len(obj) > 80 and ("session=" in obj or "XSRF-TOKEN=" in obj or "laravel_token=" in obj):
            return COOKIE_VAR
        if len(obj) > 40 and re.fullmatch(r"[A-Za-z0-9+/=_%\-]{40,}", obj):
            # likely csrf / token
            if "eyJ" in obj or len(obj) > 60:
                return CSRF_VAR if "eyJ" not in obj[:10] else CSRF_VAR
        return obj
    return obj


def op_requires_auth(op: dict, path_item: dict) -> bool:
    """admin: Cookie session; most APIs also need CSRF after login."""
    path_hint = False
    for source in (op.get("parameters") or [], path_item.get("parameters") or []):
        for p in source:
            if p.get("in") != "header":
                continue
            name = (p.get("name") or "").lower()
            if name in {"cookie", "x-csrf-token", "x-xsrf-token", "authorization"}:
                # login also has cookie pre-auth; treat login as public
                path_hint = True
    return path_hint


def clean_headers(headers: dict | None) -> dict | None:
    if not headers:
        return None
    cleaned = {
        k: v
        for k, v in headers.items()
        if k.lower() not in NOISE_HEADERS and not k.lower().startswith("cf-")
    }
    return cleaned or None


def clean_parameters(params: list | None, *, requires_auth: bool, is_login: bool) -> list:
    cleaned: list = []
    seen = set()
    for p in params or []:
        name = p.get("name") or ""
        loc = p.get("in")
        key = (name.lower(), loc)
        if key in seen:
            continue
        lname = name.lower()
        if loc == "header":
            if lname in NOISE_HEADERS or lname.startswith("sec-") or lname.startswith("cf-"):
                continue
            if lname == "cookie":
                if is_login:
                    # optional pre-login cookie; keep as variable placeholder optional
                    cleaned.append(
                        {
                            "name": "Cookie",
                            "in": "header",
                            "required": False,
                            "description": f"可選。登入後請改用環境變數 {COOKIE_VAR}",
                            "example": COOKIE_VAR,
                            "schema": {"type": "string", "example": COOKIE_VAR},
                        }
                    )
                elif requires_auth:
                    cleaned.append(
                        {
                            "name": "Cookie",
                            "in": "header",
                            "required": True,
                            "description": f"登入後 Session Cookie，使用環境變數 {COOKIE_VAR}",
                            "example": COOKIE_VAR,
                            "schema": {"type": "string", "example": COOKIE_VAR},
                        }
                    )
                seen.add(key)
                continue
            if lname in {"x-csrf-token", "x-xsrf-token"}:
                if requires_auth and not is_login:
                    cleaned.append(
                        {
                            "name": "X-CSRF-TOKEN",
                            "in": "header",
                            "required": True,
                            "description": f"CSRF Token，使用環境變數 {CSRF_VAR}（登入後從 Cookie XSRF-TOKEN 取得）",
                            "example": CSRF_VAR,
                            "schema": {"type": "string", "example": CSRF_VAR},
                        }
                    )
                seen.add(key)
                continue
            continue  # drop other headers
        # query / path / cookie
        item = redact(deepcopy(p))
        # promote schema.example to parameter-level example (Apidog)
        schema = item.get("schema") or {}
        if "example" not in item and schema.get("example") is not None:
            item["example"] = schema.get("example")
        cleaned.append(item)
        seen.add(key)

    # ensure auth headers exist for protected APIs
    if requires_auth and not is_login:
        names = {(p.get("name") or "").lower() for p in cleaned}
        if "cookie" not in names:
            cleaned.append(
                {
                    "name": "Cookie",
                    "in": "header",
                    "required": True,
                    "description": f"登入後 Session Cookie，使用環境變數 {COOKIE_VAR}",
                    "example": COOKIE_VAR,
                    "schema": {"type": "string", "example": COOKIE_VAR},
                }
            )
        if "x-csrf-token" not in names:
            cleaned.append(
                {
                    "name": "X-CSRF-TOKEN",
                    "in": "header",
                    "required": True,
                    "description": f"CSRF Token，使用環境變數 {CSRF_VAR}",
                    "example": CSRF_VAR,
                    "schema": {"type": "string", "example": CSRF_VAR},
                }
            )
    return cleaned


def ensure_path_params(params: list, param_names: list[str]) -> list:
    existing = {(p.get("name"), p.get("in")) for p in params}
    for name in param_names:
        if (name, "path") not in existing:
            params.append(
                {
                    "name": name,
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                    "description": "資源 ID",
                }
            )
    return params


def op_score(op: dict) -> int:
    score = len(op.get("parameters") or [])
    score += 5 if "requestBody" in op else 0
    for resp in (op.get("responses") or {}).values():
        if isinstance(resp, dict) and resp.get("content"):
            score += 3
    return score


def clean_operation(method: str, path: str, op: dict, *, requires_auth: bool) -> dict:
    is_login = path_base(path) == "/zh-Hant/login"
    # login is public entry
    if is_login:
        requires_auth = False

    zh = zh_for_path(path)
    tag = resolve_tag(path)
    out = {
        "tags": [tag],
        "summary": f"{method_zh(method)}{zh}",
        "operationId": op.get("operationId")
        or re.sub(r"[^a-zA-Z0-9_]", "_", f"{method}_{path.strip('/')}"),
        "x-requires-token": requires_auth,
        "x-auth-label": "需要登入（Cookie + CSRF）" if requires_auth else "不需登入（公開）",
        "security": [{"cookieAuth": []}, {"csrfAuth": []}] if requires_auth else [],
    }

    params = clean_parameters(op.get("parameters"), requires_auth=requires_auth, is_login=is_login)
    if params:
        out["parameters"] = params

    if "requestBody" in op:
        body = redact(deepcopy(op["requestBody"]))
        # login: note _token field maps to csrf
        if is_login:
            try:
                props = body["content"]["application/x-www-form-urlencoded"]["schema"]["properties"]
                if "_token" in props:
                    props["_token"]["example"] = CSRF_VAR
                    props["_token"]["description"] = f"表單 CSRF，可用 {CSRF_VAR}"
            except (KeyError, TypeError):
                pass
        out["requestBody"] = body

    responses = {}
    for code, resp in (op.get("responses") or {}).items():
        if not isinstance(resp, dict):
            responses[code] = resp
            continue
        r = redact(deepcopy(resp))
        headers = clean_headers(r.get("headers"))
        if headers:
            r["headers"] = headers
        else:
            r.pop("headers", None)
        if not r.get("description"):
            r["description"] = "成功" if str(code).startswith("2") or code == "302" else f"HTTP {code}"
        responses[code] = r
    out["responses"] = responses or {"200": {"description": "成功"}}

    if is_login:
        out["x-token-variable"] = {
            "cookie": COOKIE_VAR,
            "csrf_token": CSRF_VAR,
            "description": (
                "登入成功（302）後，從 Set-Cookie 取得 ab_session / XSRF-TOKEN，"
                f"分別寫入環境變數 {COOKIE_VAR} 與 {CSRF_VAR}"
            ),
        }
    return out


def load_and_merge_raw(raw_paths: list[Path]) -> dict:
    """Union-merge multiple Proxyman OpenAPI YAMLs by path+method (keep richer op)."""
    import shutil

    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    base: dict = {"openapi": "3.0.0", "info": {}, "paths": {}}

    for raw_path in raw_paths:
        if not raw_path.is_file():
            print(f"skip missing: {raw_path}")
            continue
        archived = IMPORTS_DIR / raw_path.name
        if archived.exists():
            archived = IMPORTS_DIR / f"{raw_path.stem}_{raw_path.stat().st_mtime_ns}{raw_path.suffix}"
        shutil.copy2(raw_path, archived)
        print(f"archived {raw_path.name} -> {archived}")

        with raw_path.open(encoding="utf-8") as f:
            incoming = yaml.safe_load(f) or {}
        if not base.get("servers") and incoming.get("servers"):
            base["servers"] = incoming["servers"]
        in_paths = incoming.get("paths") or {}
        for path, item in in_paths.items():
            if not isinstance(item, dict):
                continue
            if path not in base["paths"]:
                base["paths"][path] = deepcopy(item)
                continue
            # merge methods
            cur = base["paths"][path]
            if len(item.get("parameters") or []) > len(cur.get("parameters") or []):
                cur["parameters"] = deepcopy(item["parameters"])
            for method, op in item.items():
                if method == "parameters" or str(method).startswith("x-") or not isinstance(op, dict):
                    continue
                if method not in cur or not isinstance(cur.get(method), dict):
                    cur[method] = deepcopy(op)
                elif op_score(op) > op_score(cur[method]):
                    cur[method] = deepcopy(op)
    return base


def main(raw_paths: list[Path] | None = None) -> None:
    raw_paths = raw_paths or [RAW_DEFAULT]
    spec = load_and_merge_raw(raw_paths)

    merged: dict[tuple[str, str], dict] = {}
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict) or should_skip(path):
            continue
        norm, param_names = normalize_path(path)
        for method, op in item.items():
            if method == "parameters" or str(method).startswith("x-"):
                continue
            if method.lower() not in KEEP_METHODS or not isinstance(op, dict):
                continue
            requires = op_requires_auth(op, item)
            # API paths always need login except login itself
            if path_base(path) != "/zh-Hant/login" and (
                path.startswith("/zh-Hant/api/") or path.startswith("/broadcasting")
            ):
                requires = True
            key = (method.lower(), norm)
            cand = {
                "norm": norm,
                "param_names": param_names,
                "method": method.lower(),
                "op": op,
                "requires": requires,
                "score": op_score(op),
            }
            prev = merged.get(key)
            if prev is None or cand["score"] > prev["score"]:
                if prev and prev["requires"]:
                    cand["requires"] = True
                merged[key] = cand
            elif requires:
                prev["requires"] = True

    new_paths: dict = {}
    tags_set: set[str] = set()
    for (method, norm), cand in sorted(merged.items(), key=lambda x: (x[0][1], x[0][0])):
        cleaned = clean_operation(method, norm, cand["op"], requires_auth=cand["requires"])
        params = ensure_path_params(cleaned.get("parameters") or [], cand["param_names"])
        if params:
            cleaned["parameters"] = params
        new_paths.setdefault(norm, {})[method] = cleaned
        tags_set.add(cleaned["tags"][0])

    sources = ", ".join(p.name for p in raw_paths if p.is_file())
    clean_spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Demo Platform CTUP API",
            "version": "1.0.0",
            "description": (
                f"環境變數：`baseUrl`（預設 {BASE_URL_DEFAULT}）、"
                f"`cookie`（登入後 Session，請求用 {COOKIE_VAR}）、"
                f"`csrf_token`（CSRF，請求用 {CSRF_VAR} / Header X-CSRF-TOKEN）。"
                f"來源：{sources}；已去重並略過靜態資源／HTML 頁面。"
            ),
        },
        "servers": [
            {
                "url": "{baseUrl}",
                "description": "CTUP 後台環境",
                "variables": {
                    "baseUrl": {
                        "default": BASE_URL_DEFAULT,
                        "description": "API 基底網址",
                    }
                },
            }
        ],
        "x-environment": {
            "name": "admin-demo-platform",
            "variables": {
                "baseUrl": {
                    "type": "string",
                    "value": BASE_URL_DEFAULT,
                    "description": "API 基底網址",
                },
                "cookie": {
                    "type": "string",
                    "value": "",
                    "description": f"登入後 Cookie 字串，請求 Header Cookie: {COOKIE_VAR}",
                },
                "csrf_token": {
                    "type": "string",
                    "value": "",
                    "description": (
                        f"登入後 CSRF。Header: X-CSRF-TOKEN: {CSRF_VAR}；"
                        "通常來自 Cookie 的 XSRF-TOKEN（需 URL decode）"
                    ),
                },
            },
        },
        "tags": [{"name": t} for t in sorted(tags_set)],
        "paths": dict(sorted(new_paths.items())),
        "components": {
            "securitySchemes": {
                "cookieAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Cookie",
                    "description": f"使用環境變數 {COOKIE_VAR}",
                },
                "csrfAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-CSRF-TOKEN",
                    "description": f"使用環境變數 {CSRF_VAR}",
                },
            }
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    for dest in (OUT, OUT_DOWNLOADS):
        with dest.open("w", encoding="utf-8") as f:
            yaml.dump(
                clean_spec,
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                width=100,
            )

    pub = sum(
        1
        for item in new_paths.values()
        for m, op in item.items()
        if m != "parameters" and not op.get("x-requires-token")
    )
    tok = sum(
        1
        for item in new_paths.values()
        for m, op in item.items()
        if m != "parameters" and op.get("x-requires-token")
    )
    print(f"Wrote {OUT}")
    print(f"Wrote {OUT_DOWNLOADS}")
    print(f"paths={len(new_paths)} ops={pub+tok} public={pub} auth={tok}")
    for p in sorted(new_paths):
        methods = [m.upper() for m in new_paths[p] if m != "parameters"]
        auth = new_paths[p][methods[0].lower()].get("x-auth-label")
        print(f"  {','.join(methods):4} {p}  [{auth}]")


if __name__ == "__main__":
    import sys

    args = [Path(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else None
    main(args)
