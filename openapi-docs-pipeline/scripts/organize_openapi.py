#!/usr/bin/env python3
"""Clean Proxyman/HarToOpenApi YAML and generate grouped Markdown docs."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "openapi.raw.yaml"
CLEAN = ROOT / "openapi.yaml"
DOCS_DIR = ROOT / "docs" / "api"
AUTH_MATRIX = ROOT / "docs" / "auth-matrix.md"

NOISE_HEADERS = {
    "cf-cache-status",
    "cf-ray",
    "cf-apo-via",
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
    "access-control-expose-headers",
    "vary",
    "date",
    "connection",
    "transfer-encoding",
    "content-encoding",
    "content-length",
    "etag",
    "last-modified",
    "expires",
    "cache-control",
    "pragma",
    "set-cookie",
    "cookie",
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
    "x-laravel-echo",
}

KEEP_METHODS = {"get", "post", "put", "patch", "delete", "head"}
SKIP_PATH_PREFIXES = ("/images", "/imgfly", "/img", "/favicon.ico")

# ULID / UUID / long hex-ish resource ids captured in traffic
ID_SEGMENT_RE = re.compile(
    r"^(?:"
    r"[0-9a-hjkmnp-z]{26}"  # ULID-like
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # UUID
    r"|[0-9a-f]{16,}"  # long hex
    r"|__temp__[A-Za-z0-9_-]+"  # imgfly temp
    r")$",
    re.I,
)

TAG_RULES: list[tuple[str, str, str, str]] = [
    ("/api/login", "auth", "認證與登入", "登入、驗證相關"),
    ("/api/register", "auth", "認證與登入", "註冊相關"),
    ("/api/account-verify", "auth", "認證與登入", "帳號驗證"),
    ("/api/member", "member", "會員", "會員資料與申請"),
    ("/api/mobile", "member", "會員", "手機相關"),
    ("/api/vip", "vip", "VIP", "VIP 等級與權益"),
    ("/api/station-play", "lottery", "彩票／遊戲", "遊戲啟動／場館"),
    ("/api/station-wallet", "wallet", "錢包與交易", "站內錢包"),
    ("/api/station-wallet-trade", "wallet", "錢包與交易", "錢包交易"),
    ("/api/bankbook", "wallet", "錢包與交易", "帳本"),
    ("/api/activity", "cms", "站台設定／CMS", "活動"),
    ("/api/maintenance", "settings", "設定", "維護狀態"),
    ("/play", "lottery", "彩票／遊戲", "遊戲遊玩頁"),
    ("/api/bankcard", "payment", "金流與支付", "銀行卡"),
    ("/api/creditcard", "payment", "金流與支付", "信用卡"),
    ("/api/payment-channel", "payment", "金流與支付", "支付通道"),
    ("/api/lottery", "lottery", "彩票／遊戲", "彩票相關"),
    ("/api/rank", "rank", "排行榜", "排名相關"),
    ("/api/agent-rebate", "agent", "代理", "代理返水"),
    ("/api/all-agent", "agent", "代理", "代理相關"),
    ("/api/user-market", "market", "市場", "使用者市場"),
    ("/api/bulletin", "content", "公告與內容", "公告"),
    ("/api/bulletin-category", "content", "公告與內容", "公告分類"),
    ("/api/faq", "content", "公告與內容", "FAQ"),
    ("/api/faq-category", "content", "公告與內容", "FAQ 分類"),
    ("/api/mailbox", "content", "公告與內容", "站內信"),
    ("/api/system-blog", "content", "公告與內容", "系統文章"),
    ("/api/slider", "cms", "站台設定／CMS", "輪播"),
    ("/api/floating-button", "cms", "站台設定／CMS", "浮動按鈕"),
    ("/api/pop-up-advertisement", "cms", "站台設定／CMS", "彈窗廣告"),
    ("/api/gift", "cms", "站台設定／CMS", "禮物／贈品"),
    ("/api/config", "settings", "設定", "設定檔"),
    ("/api/base-settings", "settings", "設定", "基礎設定"),
    ("/api/language", "settings", "設定", "語系"),
    ("/api/station", "settings", "設定", "站台"),
    ("/api/appurl", "settings", "設定", "App 連結"),
    ("/api/category-statistics", "stats", "統計", "分類統計"),
    ("/broadcasting", "realtime", "即時通訊", "廣播／WebSocket 相關"),
]

TAG_DESCRIPTIONS = {
    "認證與登入": "登入、註冊、帳號驗證",
    "會員": "會員資料、申請、手機",
    "VIP": "VIP 等級與權益",
    "錢包與交易": "站內錢包、交易、帳本",
    "金流與支付": "銀行卡、信用卡、支付通道",
    "彩票／遊戲": "彩票、場館啟動、遊玩頁",
    "排行榜": "排名相關",
    "代理": "代理列表、返水",
    "市場": "使用者市場",
    "公告與內容": "公告、FAQ、站內信、系統文章",
    "站台設定／CMS": "輪播、浮動按鈕、彈窗、禮物、活動",
    "設定": "站台、語系、設定檔、App 連結、維護狀態",
    "統計": "分類統計",
    "即時通訊": "廣播／WebSocket 相關",
    "其他 API": "尚未分類的 API",
    "其他": "其他路徑",
}

PATH_ZH: dict[str, str] = {
    "/api/account-verify": "帳號驗證",
    "/api/agent-rebate": "代理返水",
    "/api/all-agent": "代理列表／資訊",
    "/api/appurl": "App 下載連結",
    "/api/bankbook": "帳本／流水",
    "/api/bankcard": "銀行卡",
    "/api/base-settings": "基礎設定",
    "/api/bulletin": "公告",
    "/api/bulletin-category": "公告分類",
    "/api/category-statistics": "分類統計",
    "/api/config": "設定",
    "/api/creditcard": "信用卡",
    "/api/faq": "常見問題",
    "/api/faq-category": "FAQ 分類",
    "/api/floating-button": "浮動按鈕",
    "/api/gift": "禮物／贈品",
    "/api/language": "語系",
    "/api/login": "登入",
    "/api/lottery": "彩票",
    "/api/mailbox": "站內信",
    "/api/member": "會員",
    "/api/member-application": "會員申請",
    "/api/mobile": "手機",
    "/api/payment-channel": "支付通道",
    "/api/pop-up-advertisement": "彈窗廣告",
    "/api/rank": "排行榜",
    "/api/register": "註冊",
    "/api/register-visit-times": "註冊造訪次數",
    "/api/slider": "輪播圖",
    "/api/station": "站台資訊",
    "/api/station-play": "場館／遊戲啟動",
    "/api/station-wallet": "站內錢包",
    "/api/station-wallet-trade": "錢包交易",
    "/api/system-blog": "系統文章",
    "/api/user-market": "使用者市場",
    "/api/vip": "VIP",
    "/api/activity": "活動",
    "/api/maintenance": "維護狀態",
    "/api/config": "設定",
    "/play": "遊戲遊玩",
    "/broadcasting/auth": "廣播認證",
}

BEARER_RE = re.compile(r"Bearer\s+eyJ[\w\-_=]+\.[\w\-_=]+\.[\w\-_=]+", re.I)
TOKEN_VAR = "{{access_token}}"
BEARER_VAR = f"Bearer {TOKEN_VAR}"
BASE_URL_DEFAULT = "https://api.demo-platform.example.com"


def path_base(path: str) -> str:
    return path.split("?")[0].rstrip("/") or "/"


def should_skip_path(path: str) -> bool:
    p = path_base(path)
    return any(p == pref or p.startswith(pref + "/") for pref in SKIP_PATH_PREFIXES)


def normalize_path(path: str) -> tuple[str, list[str]]:
    """Collapse concrete resource ids into {id}; strip trailing slash."""
    raw = path.split("?")[0]
    parts = [x for x in raw.split("/") if x]
    param_names: list[str] = []
    out: list[str] = []
    for seg in parts:
        if ID_SEGMENT_RE.match(seg):
            name = "id" if "id" not in param_names else f"id{len(param_names)+1}"
            param_names.append(name)
            out.append("{" + name + "}")
        else:
            out.append(seg)
    normalized = "/" + "/".join(out) if out else "/"
    return normalized, param_names


def resolve_tag(path: str) -> tuple[str, str, str]:
    p = path_base(path)
    best = None
    for prefix, tag_id, title, desc in TAG_RULES:
        if p == prefix or p.startswith(prefix + "/") or p.startswith(prefix):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, tag_id, title, desc)
    if best:
        return best[1], best[2], best[3]
    if p.startswith("/api/"):
        return "other", "其他 API", "尚未分類的 API"
    return "other", "其他", "其他路徑"


def zh_for_path(path: str) -> str:
    p = path_base(path)
    if p in PATH_ZH:
        return PATH_ZH[p]
    for key, zh in sorted(PATH_ZH.items(), key=lambda x: -len(x[0])):
        if p.startswith(key):
            rest = p[len(key) :].strip("/")
            return f"{zh}（{rest}）" if rest else zh
    seg = p.rstrip("/").split("/")[-1]
    return seg.replace("-", " ").replace("{", "").replace("}", "")


def method_zh(method: str) -> str:
    return {
        "get": "查詢",
        "post": "提交",
        "put": "更新",
        "patch": "部分更新",
        "delete": "刪除",
    }.get(method.lower(), method.upper())


def redact_secrets(obj):
    if isinstance(obj, dict):
        return {k: redact_secrets(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_secrets(v) for v in obj]
    if isinstance(obj, str):
        if BEARER_RE.search(obj):
            return BEARER_RE.sub(BEARER_VAR, obj)
        if obj.startswith("eyJ") and obj.count(".") >= 2 and len(obj) > 40:
            return TOKEN_VAR
        # previous placeholder forms
        if obj in {"<YOUR_ACCESS_TOKEN>", "Bearer <YOUR_ACCESS_TOKEN>"}:
            return TOKEN_VAR if not obj.startswith("Bearer") else BEARER_VAR
        if "YOUR_ACCESS_TOKEN" in obj:
            return obj.replace("Bearer <YOUR_ACCESS_TOKEN>", BEARER_VAR).replace(
                "<YOUR_ACCESS_TOKEN>", TOKEN_VAR
            )
        return obj
    return obj


def op_has_bearer(op: dict, path_item: dict) -> bool:
    for source in (op.get("parameters") or [], path_item.get("parameters") or []):
        for p in source:
            if p.get("in") != "header":
                continue
            if (p.get("name") or "").lower() != "authorization":
                continue
            example = (p.get("schema") or {}).get("example") or p.get("example") or ""
            if isinstance(example, str) and "bearer" in example.lower():
                return True
            # present as Authorization header in capture
            return True
    return False


def clean_headers(headers: dict | None) -> dict | None:
    if not headers:
        return None
    cleaned = {
        k: v
        for k, v in headers.items()
        if k.lower() not in NOISE_HEADERS and not k.lower().startswith("cf-")
    }
    return cleaned or None


def clean_parameters(params: list | None, *, keep_auth_placeholder: bool = False) -> list | None:
    if not params:
        return None
    cleaned = []
    for p in params:
        name = (p.get("name") or "").lower()
        loc = p.get("in")
        if loc == "header" and name == "authorization":
            if keep_auth_placeholder:
                cleaned.append(
                    {
                        "name": "Authorization",
                        "in": "header",
                        "required": True,
                        "description": f"使用環境變數 {TOKEN_VAR}（由 POST /api/login 的 result.token 寫入）",
                        "schema": {"type": "string", "example": BEARER_VAR},
                    }
                )
            continue
        if loc == "header" and (
            name in NOISE_HEADERS
            or name.startswith("sec-")
            or name.startswith("cf-")
            or name
            in {
                "cookie",
                "user-agent",
                "accept",
                "accept-encoding",
                "accept-language",
                "host",
                "connection",
                "content-type",
            }
        ):
            continue
        item = redact_secrets(deepcopy(p))
        cleaned.append(item)
    return cleaned or None


def ensure_path_params(params: list | None, param_names: list[str]) -> list:
    params = list(params or [])
    existing = {(p.get("name"), p.get("in")) for p in params}
    for name in param_names:
        key = (name, "path")
        if key not in existing:
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


def clean_operation(method: str, path: str, op: dict, *, requires_token: bool) -> dict:
    zh = zh_for_path(path)
    _, tag_title, _ = resolve_tag(path)
    auth_label = "需要 Token" if requires_token else "不需 Token（公開）"
    out = {
        "tags": [tag_title],
        "summary": f"{method_zh(method)}{zh}",
        # 不輸出 description（只保留 summary）
        "operationId": op.get("operationId")
        or re.sub(r"[^a-zA-Z0-9_]", "_", f"{method}_{path.strip('/')}"),
        "x-requires-token": requires_token,
        "x-auth-label": auth_label,
    }
    if requires_token:
        out["security"] = [{"bearerAuth": []}]
    else:
        out["security"] = []

    params = clean_parameters(op.get("parameters"), keep_auth_placeholder=requires_token)
    if params:
        out["parameters"] = params
    if "requestBody" in op:
        out["requestBody"] = redact_secrets(deepcopy(op["requestBody"]))

    responses = {}
    for code, resp in (op.get("responses") or {}).items():
        if not isinstance(resp, dict):
            responses[code] = resp
            continue
        r = redact_secrets(deepcopy(resp))
        headers = clean_headers(r.get("headers"))
        if headers:
            r["headers"] = headers
        else:
            r.pop("headers", None)
        if not r.get("description"):
            r["description"] = "成功" if str(code).startswith("2") else f"HTTP {code}"
        responses[code] = r
    out["responses"] = responses or {"200": {"description": "成功"}}
    return out


def slugify(text: str) -> str:
    table = {
        "認證與登入": "auth",
        "會員": "member",
        "VIP": "vip",
        "錢包與交易": "wallet",
        "金流與支付": "payment",
        "彩票／遊戲": "lottery",
        "排行榜": "rank",
        "代理": "agent",
        "市場": "market",
        "公告與內容": "content",
        "站台設定／CMS": "cms",
        "設定": "settings",
        "統計": "stats",
        "即時通訊": "realtime",
        "其他 API": "other-api",
        "其他": "other",
    }
    return table.get(text, re.sub(r"[^\w\-]+", "-", text).strip("-").lower() or "misc")


def fmt_schema_props(schema: dict | None, indent: int = 0) -> list[str]:
    if not schema or not isinstance(schema, dict):
        return []
    lines = []
    pad = "  " * indent
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        for name, prop in props.items():
            if not isinstance(prop, dict):
                lines.append(f"{pad}- `{name}`")
                continue
            ptype = prop.get("type", "object")
            req = "必填" if name in required else "選填"
            lines.append(f"{pad}- `{name}` ({ptype}, {req})")
            if prop.get("type") == "object" or "properties" in prop:
                lines.extend(fmt_schema_props(prop, indent + 1))
            if prop.get("type") == "array" and isinstance(prop.get("items"), dict):
                lines.append(f"{pad}  - items:")
                lines.extend(fmt_schema_props(prop["items"], indent + 2))
    elif t == "array" and isinstance(schema.get("items"), dict):
        lines.append(f"{pad}- array of:")
        lines.extend(fmt_schema_props(schema["items"], indent + 1))
    return lines


def example_preview(example, limit: int = 800) -> str:
    try:
        text = json.dumps(example, ensure_ascii=False, indent=2)
    except TypeError:
        text = str(example)
    if len(text) > limit:
        return text[:limit] + "\n…（已截斷）"
    return text


def op_score(op: dict) -> int:
    """Prefer richer captured ops when merging duplicates."""
    score = 0
    score += len(op.get("parameters") or [])
    score += 5 if "requestBody" in op else 0
    for resp in (op.get("responses") or {}).values():
        if isinstance(resp, dict) and resp.get("content"):
            score += 3
    return score


def write_auth_matrix(rows: list[tuple[str, str, str, bool, str]]) -> None:
    """rows: method, path, tag, requires_token, summary"""
    public = [r for r in rows if not r[3]]
    token = [r for r in rows if r[3]]
    lines = [
        "# API 認證分類（Token）",
        "",
        "依 Proxyman 抓包是否帶有 `Authorization: Bearer …` 判斷。",
        "",
        "- **需要 Token**：請求有帶 Bearer JWT",
        "- **不需 Token（公開）**：請求未帶 Authorization",
        "",
        "> 注意：前端登入後可能對「其實公開」的 API 也帶 token；此表反映抓包實況，非伺服器原始碼強制規則。",
        "",
        f"統計：公開 **{len(public)}**／需 Token **{len(token)}**／合計 **{len(rows)}**",
        "",
        "## 不需 Token（公開）",
        "",
        "| Method | Path | 分組 | 說明 |",
        "|--------|------|------|------|",
    ]
    for method, path, tag, _, summary in sorted(public, key=lambda x: (x[2], x[1], x[0])):
        lines.append(f"| `{method.upper()}` | `{path}` | {tag} | {summary} |")

    lines += [
        "",
        "## 需要 Token",
        "",
        "| Method | Path | 分組 | 說明 |",
        "|--------|------|------|------|",
    ]
    for method, path, tag, _, summary in sorted(token, key=lambda x: (x[2], x[1], x[0])):
        lines.append(f"| `{method.upper()}` | `{path}` | {tag} | {summary} |")

    lines += [
        "",
        "## 使用方式",
        "",
        "登入成功後，於 Header 帶入：",
        "",
        "```http",
        f"Authorization: {BEARER_VAR}",
        "X-Sub-Domain: www",
        "```",
        "",
        f"其中 `{TOKEN_VAR}` 來自 `POST /api/login` 回應的 `result.token`。",
        "",
    ]
    AUTH_MATRIX.write_text("\n".join(lines), encoding="utf-8")


def write_markdown(
    grouped: dict[str, list[tuple[str, str, dict]]],
    tag_meta: dict[str, str],
) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    index_lines = [
        "# Demo Platform API 文件",
        "",
        "來源：Proxyman 匯出 OpenAPI（`openapi.raw.yaml`），經整理後見 `openapi.yaml`。",
        "",
        "伺服器：`https://api.demo-platform.example.com`",
        "",
        "認證總表：[`auth-matrix.md`](./auth-matrix.md)",
        "",
        "## 目錄",
        "",
    ]

    for tag_title in sorted(grouped.keys(), key=lambda t: (t == "其他 API", t == "其他", t)):
        slug = slugify(tag_title)
        ops = grouped[tag_title]
        desc = tag_meta.get(tag_title, "")
        token_n = sum(1 for _, _, op in ops if op.get("x-requires-token"))
        public_n = len(ops) - token_n
        index_lines.append(
            f"- [{tag_title}](./api/{slug}.md) — {len(ops)} 個操作"
            f"（公開 {public_n}／需 Token {token_n}）"
            + (f" — {desc}" if desc else "")
        )

        lines = [
            f"# {tag_title}",
            "",
            desc,
            "",
            f"共 **{len(ops)}** 個操作（公開 {public_n}／需 Token {token_n}）。",
            "",
        ]
        for path, method, op in ops:
            auth = "🔒 Token" if op.get("x-requires-token") else "🔓 公開"
            lines.append(
                f"- [`{method.upper()} {path}`](#{slugify(method + path)}) — {op.get('summary', '')} · {auth}"
            )
        lines.append("")

        for path, method, op in ops:
            auth = "**需要 Token**" if op.get("x-requires-token") else "**不需 Token（公開）**"
            lines.append(f"## `{method.upper()} {path}`")
            lines.append("")
            lines.append(f"**{op.get('summary', '')}** · {auth}")
            lines.append("")

            params = op.get("parameters") or []
            query = [p for p in params if p.get("in") == "query"]
            headers = [p for p in params if p.get("in") == "header"]
            path_params = [p for p in params if p.get("in") == "path"]

            if path_params:
                lines.append("### Path 參數")
                lines.append("")
                for p in path_params:
                    schema = p.get("schema") or {}
                    lines.append(f"- `{p.get('name')}` ({schema.get('type', 'string')})")
                lines.append("")

            if query:
                lines.append("### Query 參數")
                lines.append("")
                for p in query:
                    schema = p.get("schema") or {}
                    ex = schema.get("example")
                    # avoid dumping secrets/long values
                    ex_s = f" — 例：`{ex}`" if ex is not None and len(str(ex)) < 80 else ""
                    lines.append(f"- `{p.get('name')}` ({schema.get('type', 'string')}){ex_s}")
                lines.append("")

            if headers:
                lines.append("### Headers")
                lines.append("")
                for p in headers:
                    schema = p.get("schema") or {}
                    lines.append(
                        f"- `{p.get('name')}` ({schema.get('type', 'string')})"
                        + (f" — {p.get('description')}" if p.get("description") else "")
                    )
                lines.append("")

            body = op.get("requestBody")
            if body:
                lines.append("### Request Body")
                lines.append("")
                content = body.get("content") or {}
                for ctype, media in content.items():
                    lines.append(f"Content-Type: `{ctype}`")
                    lines.append("")
                    props = fmt_schema_props(media.get("schema"))
                    if props:
                        lines.append("欄位：")
                        lines.append("")
                        lines.extend(props)
                        lines.append("")
                    if "example" in media:
                        lines.append("範例：")
                        lines.append("")
                        lines.append("```json")
                        lines.append(example_preview(media["example"]))
                        lines.append("```")
                        lines.append("")

            responses = op.get("responses") or {}
            if responses:
                lines.append("### Responses")
                lines.append("")
                for code, resp in sorted(responses.items(), key=lambda x: str(x[0])):
                    if not isinstance(resp, dict):
                        continue
                    lines.append(f"#### {code} — {resp.get('description') or ''}")
                    lines.append("")
                    content = resp.get("content") or {}
                    for ctype, media in content.items():
                        lines.append(f"`{ctype}`")
                        lines.append("")
                        props = fmt_schema_props(media.get("schema"))
                        if props:
                            lines.append("欄位：")
                            lines.append("")
                            lines.extend(props)
                            lines.append("")
                        if "example" in media:
                            lines.append("範例：")
                            lines.append("")
                            lines.append("```json")
                            lines.append(example_preview(media["example"]))
                            lines.append("```")
                            lines.append("")

            lines.append("---")
            lines.append("")

        (DOCS_DIR / f"{slug}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    (ROOT / "docs" / "README.md").write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    with RAW.open(encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    # key: (method, normalized_path) -> (raw_path, path_item_op_bundle)
    merged: dict[tuple[str, str], dict] = {}

    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        if should_skip_path(path):
            continue

        norm_path, param_names = normalize_path(path)
        shared_params = item.get("parameters") or []

        for method, op in item.items():
            if method == "parameters" or str(method).startswith("x-"):
                continue
            if method.lower() not in KEEP_METHODS:
                continue
            if not isinstance(op, dict):
                continue

            key = (method.lower(), norm_path)
            requires_token = op_has_bearer(op, item)
            candidate = {
                "raw_path": path,
                "norm_path": norm_path,
                "param_names": param_names,
                "method": method.lower(),
                "op": op,
                "shared_params": shared_params,
                "requires_token": requires_token,
                "score": op_score(op) + (2 if param_names else 0),
            }
            prev = merged.get(key)
            if prev is None or candidate["score"] > prev["score"]:
                # if either capture used token, mark as requires token
                if prev and prev["requires_token"]:
                    candidate["requires_token"] = True
                merged[key] = candidate
            else:
                if requires_token:
                    prev["requires_token"] = True

    tags_set: dict[str, str] = {}
    new_paths: dict = {}
    grouped: dict[str, list] = defaultdict(list)
    matrix_rows: list[tuple[str, str, str, bool, str]] = []

    for (method, norm_path), cand in sorted(merged.items(), key=lambda x: (x[0][1], x[0][0])):
        cleaned = clean_operation(method, norm_path, cand["op"], requires_token=cand["requires_token"])
        shared = clean_parameters(cand["shared_params"], keep_auth_placeholder=False) or []
        params = cleaned.get("parameters") or []
        names = {(p.get("name"), p.get("in")) for p in params}
        for p in shared:
            key = (p.get("name"), p.get("in"))
            if key not in names:
                params.append(p)
        params = ensure_path_params(params, cand["param_names"])
        if params:
            cleaned["parameters"] = params

        new_paths.setdefault(norm_path, {})[method] = cleaned
        tag_title = cleaned["tags"][0]
        tags_set[tag_title] = TAG_DESCRIPTIONS.get(tag_title, "")
        grouped[tag_title].append((norm_path, method, cleaned))
        matrix_rows.append(
            (method, norm_path, tag_title, bool(cleaned.get("x-requires-token")), cleaned.get("summary", ""))
        )

    clean_spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Demo Platform API",
            "version": "1.0.0",
            "description": (
                "環境變數：`baseUrl`（預設 https://api.demo-platform.example.com）、"
                f"`access_token`（由 POST /api/login 的 result.token 寫入，請求使用 {BEARER_VAR}）。"
            ),
        },
        "servers": [
            {
                "url": "{baseUrl}",
                "description": "API 環境（可用環境變數切換）",
                "variables": {
                    "baseUrl": {
                        "default": BASE_URL_DEFAULT,
                        "description": "API 基底網址",
                    }
                },
            }
        ],
        # 給 Apidog / Postman 類工具辨識的環境變數
        "x-environment": {
            "name": "demo-platform",
            "variables": {
                "baseUrl": {
                    "type": "string",
                    "value": BASE_URL_DEFAULT,
                    "description": "API 基底網址",
                },
                "access_token": {
                    "type": "string",
                    "value": "",
                    "description": "登入 token。呼叫 POST /api/login 成功後，將 result.token 寫入此變數。",
                },
            },
        },
        "tags": [
            {"name": title, "description": desc}
            for title, desc in sorted(tags_set.items(), key=lambda x: x[0])
        ],
        "paths": dict(sorted(new_paths.items())),
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": (
                        f"使用環境變數 {TOKEN_VAR}。"
                        f"Header 範例：`{BEARER_VAR}`。"
                        "請先呼叫 POST /api/login，把回應 result.token 存成 access_token。"
                    ),
                }
            }
        },
    }

    # 登入成功後標註 token 寫入變數（不新增 operation description）
    login_post = clean_spec["paths"].get("/api/login", {}).get("post")
    if isinstance(login_post, dict):
        login_post["x-token-variable"] = {
            "name": "access_token",
            "from": "$.result.token",
            "description": f"登入成功後將 result.token 寫入環境變數 {TOKEN_VAR}",
        }
        # 確保 example 使用變數占位，方便辨識欄位
        try:
            ex = login_post["responses"]["200"]["content"]["application/json"]["example"]
            if isinstance(ex, dict) and isinstance(ex.get("result"), dict):
                ex["result"]["token"] = TOKEN_VAR
        except (KeyError, TypeError):
            pass

    with CLEAN.open("w", encoding="utf-8") as f:
        yaml.dump(
            clean_spec,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=100,
        )

    write_markdown(grouped, tags_set)
    write_auth_matrix(matrix_rows)

    public_n = sum(1 for *_, req, __ in ((r[0], r[1], r[2], r[3], r[4]) for r in matrix_rows) if not req)
    # clearer counts
    public_n = sum(1 for r in matrix_rows if not r[3])
    token_n = sum(1 for r in matrix_rows if r[3])
    print(f"Clean OpenAPI -> {CLEAN}")
    print(f"Operations: {len(matrix_rows)} (public {public_n}, token {token_n}), groups: {len(grouped)}")
    print(f"Auth matrix -> {AUTH_MATRIX}")
    for title, ops in sorted(grouped.items(), key=lambda x: -len(x[1])):
        print(f"  - {title}: {len(ops)}")


if __name__ == "__main__":
    main()
