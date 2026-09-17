# 認證矩陣

| 認證 | Method | Path | 說明 |
| --- | --- | --- | --- |
| 公開 | POST | `/api/login` | 會員登入，回傳 token |
| Token | GET | `/api/member` | 會員資料 |
| Token | GET | `/api/station-wallet/get-list` | 錢包清單 |
| Token | GET | `/api/station-play/{wallet_id}` | 遊戲進入 URL |

需 Token 的請求加 `Authorization: Bearer {{access_token}}`。
