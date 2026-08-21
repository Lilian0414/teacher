# Mac M0–M3 共用架構

## 技術棧

| 用途 | 技術 |
|---|---|
| 語言 | Python 3.12 |
| API | FastAPI、Uvicorn |
| Terminal UI | Textual |
| Database | SQLite |
| ORM／Migration | SQLAlchemy 2.x、Alembic |
| Schema／Settings | Pydantic v2、Pydantic Settings |
| Tests | pytest、pytest-asyncio |
| Lint／Type check | Ruff、strict mypy |

目前不使用 LangChain、Letta、Mem0、向量資料庫或大型 agent framework。

## 元件與邊界

```text
Textual UI

M4 proactive checks cross the UI/Core boundary only through HTTP. Core owns deterministic
eligibility and persistence; Textual owns only transient idle/presentability state and rendering.
No polling or invitation acceptance path calls the LLM.
    │ HTTP
    ▼
FastAPI Companion Core
    ├── Availability / Command policy
    ├── Conversation Service
    ├── Memory Service / Context Builder
    ├── Learning Service / Context Builder
    ├── LLM Provider
    └── SQLite repositories
```

- UI 只透過 HTTP 呼叫 Core，不直接存取資料庫或 LLM。
- command 名稱、availability、記憶來源驗證、刪除確認與 recall limit 都由
  learning grading、review scheduling 與 recall limit 都由 deterministic code 控制。
- 外部 LLM 位於 provider interface 後方。
- 自動測試使用 fake provider；Groq 只允許在明確 opt-in 的 live tests 中使用。
- provider error 是受控錯誤，不得冒充 assistant message。

## Repository 結構

```text
teacher/
├── README.md
├── doc/
│   ├── PROJECT_OVERVIEW.md
│   ├── ARCHITECTURE.md
│   ├── M0_FOUNDATION.md
│   ├── M1_TEXT_CHAT.md
│   └── M2_MEMORY.md
├── openspec/
├── migrations/
├── src/companion/
│   ├── api/
│   ├── commands/
│   ├── conversation/
│   ├── memory/
│   ├── learning/
│   ├── providers/
│   ├── persistence/
│   ├── schemas/
│   ├── settings.py
│   └── main.py
├── terminal_ui/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── live/
└── data/
```

`learning/` 是已完成的 M3；`proactive/` 仍沒有已完成行為，其存在不代表 M4 已實作。

## 安全與品質規則

1. API key 只從環境變數或本機 `.env` 讀取。
2. `.env`、SQLite、對話、記憶、音訊與模型檔不得提交 Git。
3. 錯誤、log 與測試輸出不得包含 API key。
4. 時間以含時區的 ISO 8601 保存，預設時區為 `Asia/Taipei`。
5. 每個 milestone 必須通過 Ruff、strict mypy 與完整一般 pytest。
6. 未經新 OpenSpec change 核准，不提前實作後續 milestone。
