# OpenAPI Docs Pipeline

把 Proxyman（或同等抓包工具）匯出的 OpenAPI YAML 清乾淨，產出可在編輯器閱讀的分組 Markdown，以及「公開／需要 Token」對照表。這個作品不是 UI 測試，而是 **API 文件整理管線**。

倉庫內 `openapi.raw.yaml` 是精簡示範檔，不是真實環境匯出。

## 使用的工具（不是 pytest）

| 工具 | 用途 |
| --- | --- |
| Python 3 | 腳本入口 |
| PyYAML | 讀寫 OpenAPI |
| 自寫 scripts | 去重、去雜訊 header、標註認證、產出 Markdown |

沒有接 pytest／Playwright。驗證方式是跑分析腳本：列出公開 API、找重複 path、掃認證欄位。

## 實際作用流程

1. **匯入原始 YAML**  
   抓包工具匯出後覆蓋 `openapi.raw.yaml`（或丟進 `imports/` 再 merge）。

2. **清理**（`scripts/organize_openapi.py`）
   - 丟掉 Cloudflare、CORS、cookie、瀏覽器指紋等雜訊 header
   - 略過 `/images`、favicon 這類非 API path
   - 把 ULID／UUID 資源 id 收成 path parameter
   - 依 path 分組：登入、會員、錢包、遊戲進入…
   - 看有沒有 `Authorization`，標成公開或需 Token
   - 寫出整理後的 `openapi.yaml`
   - 寫出 `docs/README.md`、`docs/auth-matrix.md`、`docs/api/*.md`

3. **後台首頁 API**（`scripts/organize_admin_home.py`）  
   後台多半是 Cookie + CSRF，不是 Bearer。腳本只保留 `/zh-Hant/api/`、login、broadcasting，方便匯入 Apidog。

4. **輔助檢查**
   - `list_no_auth.py`：列出沒帶 Authorization 的操作
   - `analyze_auth.py`：掃 header／body 裡的 token 線索
   - `check_duplicates.py`：同樣 path+method 是否重複
   - `merge_raw_openapi.py`：新的抓包檔與舊 raw 做聯集，參數較完整的一邊勝出

```
Proxyman 匯出 YAML
        │
        ▼
  openapi.raw.yaml
        │
        ├─ organize_openapi.py  →  openapi.yaml
        │                         docs/auth-matrix.md
        │                         docs/api/*.md
        ├─ list_no_auth.py      →  公開 API 清單
        ├─ analyze_auth.py      →  認證欄位統計
        └─ check_duplicates.py  →  重複 path
```

## 怎麼跑

```bash
pip install -r requirements.txt
python scripts/organize_openapi.py
python scripts/list_no_auth.py
python scripts/analyze_auth.py
python scripts/check_duplicates.py
```

看文件時順序：認證矩陣 → 分組目錄 → 需要完整 schema 再看 `openapi.yaml`。
