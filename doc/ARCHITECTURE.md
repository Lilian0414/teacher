# Mac M0–M4 共用架構

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
    │ HTTP
    ▼
FastAPI Companion Core
    ├── Availability / Command policy
    ├── Conversation Service
    ├── Memory Service / Context Builder
    ├── Learning Service / Context Builder
    ├── Proactive Service / Repository
    ├── LLM Provider
    └── SQLite repositories
```

- UI 只透過 HTTP 呼叫 Core，不直接存取資料庫或 LLM。
- command 名稱、availability、記憶來源驗證、刪除確認、learning grading、review
  scheduling、proactive eligibility 與 recall limits 都由 deterministic code 控制。
- M4 proactive check 只經 HTTP 跨越 UI/Core boundary。Core 管 eligibility 與 persistence；
  Textual 只管 transient idle/presentability state 與 rendering。Polling 與接受邀請不呼叫 LLM。
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
│   ├── M2_MEMORY.md
│   ├── M3_LEARNING.md
│   └── M4_PROACTIVE.md
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
├── src/terminal_ui/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── live/
└── data/
```

`learning/` 是已完成的 M3；`proactive/` 與 Textual invitation card 是已完成但僅限程式內
運作的 M4。它們不代表背景 daemon、關閉程式後通知或 macOS notification 已實作。

## 安全與品質規則

1. API key 只從環境變數或本機 `.env` 讀取。
2. `.env`、SQLite、對話、記憶、音訊與模型檔不得提交 Git。
3. 錯誤、log 與測試輸出不得包含 API key。
4. 時間以含時區的 ISO 8601 保存，預設時區為 `Asia/Taipei`。
5. 每個 milestone 必須通過 Ruff、strict mypy 與完整一般 pytest。
6. 未經新 OpenSpec change 核准，不提前實作後續 milestone。
