# M0：Mac 專案骨架與狀態

## 本次目標

建立可啟動、可測試的 Mac 專案骨架。M0 不包含 LLM、Groq、對話、記憶、學習、排程或語音。

實作前只需閱讀：

1. `docs/PROJECT_OVERVIEW.md`
2. `docs/ARCHITECTURE.md`
3. `docs/milestones/M0_FOUNDATION.md`

不得閱讀或實作其他 milestone。

## 功能需求

### 1. FastAPI Core

提供：

```text
GET /health
GET /v1/state
POST /v1/commands/execute
```

`GET /health` 回傳服務狀態與版本，不查外部服務。

`GET /v1/state` 至少回傳：

```json
{
  "availability": "available",
  "override_expires_at": null,
  "timezone": "Asia/Taipei"
}
```

### 2. Availability 狀態

```python
class AvailabilityState(str, Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    DND = "dnd"
```

規則：

- 預設為 `available`。
- `busy` 必須有到期時間。
- `dnd` 預設無期限，直到使用者解除。
- `available` 解除目前的 busy 或 dnd override。
- 狀態與到期時間保存至 SQLite，Core 重啟後仍存在。
- 查詢狀態時若 busy 已過期，回復 available 並更新資料庫。

### 3. Command parser

Command parser 必須是 deterministic code，不使用 LLM。

M0 支援：

```text
/busy <duration>
/dnd
/available
/status
```

Duration 至少支援：

```text
10m
2h
1h30m
```

拒絕：

- 零或負數時間。
- 無法解析的格式。
- 過大時間；上限由設定控制，預設 24 小時。

未知 command 回傳清楚錯誤及目前可用指令，不得造成未處理 exception。

`POST /v1/commands/execute` request：

```json
{
  "raw": "/busy 30m"
}
```

### 4. SQLite

使用 SQLAlchemy 2.x 與 Alembic。

M0 最少需要一個 availability override table：

- `id`
- `state`
- `starts_at`
- `expires_at` nullable
- `source`

可自行增加必要的 created／updated timestamp，但不要建立 M1 之後的資料表。

### 5. Textual UI

最小介面包含：

- 訊息／系統輸出區。
- 固定輸入框。
- Core 連線狀態。
- Availability 狀態。
- Busy 剩餘時間；無到期時間的 DND 顯示 `until cleared`。

互動：

- Enter 送出輸入。
- 支援四個 M0 commands。
- UI 只呼叫 Core API，不直接讀寫 SQLite。
- Core 無法連線時顯示錯誤，但 UI 不應 crash。

### 6. Settings

至少提供：

- App name／version。
- Core host／port。
- Database URL。
- Timezone，預設 `Asia/Taipei`。
- Busy maximum duration，預設 24 小時。

建立 `.env.example`，不得建立含真實秘密的 `.env`。

## 測試要求

必要 unit tests：

- `10m`、`2h`、`1h30m` duration parsing。
- 無效、零、負數及超過上限的 duration。
- `/busy`、`/dnd`、`/available`、`/status`。
- 未知 command。
- Busy expiry。
- DND 不會自行到期。

必要 integration tests：

- Command API 改變 availability。
- Core restart 後狀態仍存在。
- 到期 busy 回復 available。
- `/health` 與 `/v1/state` response schema。

時間相關測試使用 injectable clock，不得真的 sleep。

## M0 禁止事項

不得加入：

- Groq、任何 LLM 或 API key。
- Conversation、Message、Memory 或 Learning models。
- APScheduler。
- 語音、鏡頭、手勢或硬體。
- LangChain、Letta、Mem0。
- 檔案工具或 shell command。
- Docker；M0 直接在 Mac Python environment 執行。

## 驗收條件

M0 完成時必須：

1. Core 與 UI 可分別啟動。
2. `/busy 1m`、`/dnd`、`/available`、`/status` 正常。
3. 重啟 Core 後狀態仍存在。
4. UI 在 Core 離線時不 crash。
5. Ruff、mypy 與 pytest 全部通過。
6. README 包含安裝、migration、Core 啟動、UI 啟動與測試指令。
7. 回報實際執行的測試結果與尚未實作項目。

## 給 Codex 的任務指令

```text
請只閱讀：
1. docs/PROJECT_OVERVIEW.md
2. docs/ARCHITECTURE.md
3. docs/milestones/M0_FOUNDATION.md

依照 M0_FOUNDATION.md 完成 M0。不得閱讀或實作其他 milestone。

完成後執行 Ruff、mypy 與 pytest，修正所有問題，再回報：
- 建立的目錄與主要檔案
- 安裝與啟動方式
- migration 指令
- Ruff、mypy、pytest 實際結果
- 尚未實作的後續功能
```
