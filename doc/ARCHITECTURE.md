# Mac 第一版共用架構規則

## 技術棧

| 用途 | 技術 |
|---|---|
| 語言 | Python 3.12 |
| API | FastAPI、Uvicorn |
| Terminal UI | Textual |
| Database | SQLite |
| ORM | SQLAlchemy 2.x |
| Migration | Alembic |
| Schema | Pydantic v2 |
| Settings | Pydantic Settings |
| Scheduler | APScheduler 3.x，M4 才加入 |
| Tests | pytest、pytest-asyncio |
| Lint／format | Ruff |
| Type check | mypy |

不要加入 LangChain、Letta、Mem0 或其他大型 agent framework。

## 元件

```text
Textual UI
    │ HTTP
    ▼
FastAPI Companion Core
    ├── Command Service
    ├── Conversation Service
    ├── Memory Service
    ├── Learning Service
    ├── Proactive Scheduler
    ├── LLM Provider
    ├── Speech Provider
    └── SQLite Database
```

## 必須遵守的規則

1. UI 不直接存取資料庫或外部 AI，只呼叫 Core API。
2. 勿擾、主動邀請、記憶權限與安全政策由 deterministic code 判斷，不交給 LLM。
3. 外部 LLM、STT、TTS 都置於 provider interface 後方。
4. 自動測試使用 fake provider，不呼叫真實 API。
5. 真實 API 只在明確啟用的 live smoke test 中呼叫。
6. API key 只由環境變數讀取，不可寫入程式碼、測試、log 或 Git。
7. 所有時間保存含時區的 ISO 8601，預設時區為 `Asia/Taipei`。
8. `data/`、`.env`、SQLite、對話、記憶、音訊與模型檔不得提交 Git。
9. 每個 milestone 完成時必須通過 Ruff、mypy 與 pytest。
10. 不得提前實作未被目前 milestone 要求的功能。

## Repository 結構

```text
companion/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── alembic.ini
├── migrations/
├── docs/
│   ├── PROJECT_OVERVIEW.md
│   ├── ARCHITECTURE.md
│   └── milestones/
├── src/
│   └── companion/
│       ├── api/
│       ├── commands/
│       ├── conversation/
│       ├── memory/
│       ├── learning/
│       ├── proactive/
│       ├── providers/
│       ├── persistence/
│       ├── schemas/
│       ├── settings.py
│       └── main.py
├── terminal_ui/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── live/
└── data/
    └── .gitkeep
```

尚未使用的模組目錄可以先保留空白或延後建立，不得為填滿目錄提前撰寫功能。

## Provider 原則

M1 起使用：

```python
class LLMProvider(Protocol):
    async def chat(self, request: ChatRequest) -> ChatResponse: ...
    async def provide_language_help(
        self, request: LanguageHelpRequest
    ) -> LanguageHelpResponse: ...
```

至少提供：

- `FakeLLMProvider`：自動測試。
- `GroqLLMProvider`：實際使用。

一般 pytest 不得呼叫 Groq。真實測試必須：

```bash
RUN_LIVE_API_TESTS=1 pytest tests/live/
```

未設定 `RUN_LIVE_API_TESTS=1` 時，live tests 必須自動 skip。

## 安全與隱私

- `.env.example` 只包含空白或假值。
- `.env` 必須在 `.gitignore`。
- 錯誤訊息及 log 不得包含 API key。
- 第一版不讀取使用者檔案、螢幕或其他 App 資料。
- 第一版不執行 shell command。
- Private conversation 不建立長期記憶。
- 語音階段的原始錄音預設在成功轉錄後刪除。
