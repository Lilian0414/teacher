# M0：Mac 專案骨架與狀態

## 已完成範圍

M0 建立 Python 3.12 專案、FastAPI Core、Textual UI、SQLite persistence、
SQLAlchemy 2.x、Alembic、Pydantic Settings 與測試基礎。

Core 提供：

```text
GET  /health
GET  /v1/state
POST /v1/commands/execute
```

## Availability

支援三種狀態：

```text
available
busy
dnd
```

- 預設為 `available`。
- `/busy <duration>` 建立有期限的 override。
- `/dnd` 建立無期限 override。
- `/available` 清除目前 override。
- `/status` 顯示 Core、availability 與 LLM provider 狀態。
- busy 到期後，狀態查詢會恢復 available 並更新資料庫。
- override 在 Core 重啟後仍存在。

duration parser 支援 `10m`、`2h`、`1h30m` 等格式，拒絕零值、
負值、無效格式與超過設定上限的時間。command parsing 與狀態政策不使用 LLM。

## UI 與設定

Textual UI 顯示 Core 連線、availability、剩餘時間及訊息，並透過 Core API
執行 command。Core 離線時顯示錯誤而不直接存取 SQLite。

主要設定包含 Core host／port、database URL、timezone、user ID、busy 上限與版本。
`.env.example` 不含真實秘密。

## 驗證重點

- duration 與 command parser。
- busy expiry、無期限 DND 與 availability persistence。
- `/health`、`/v1/state`、command API。
- Core restart 後狀態保存。
- UI 在 Core 離線時不 crash。

後續 M1、M2 功能建立在此基礎上，但不改變上述 deterministic availability 行為。
