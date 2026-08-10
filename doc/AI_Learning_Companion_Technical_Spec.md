# 主動式 AI 英文學習陪伴助手：Mac 第一版技術規格

版本：1.0  
目標平台：MacBook Pro M2  
開發語言：Python 3.12

## 1. 目標

開發一套常駐於 macOS 的 AI 英文學習陪伴助手。系統能：

1. 以文字或語音進行英文日常對話。
2. 根據使用者設定、學習進度與過往互動，在合適時間主動邀請練習。
3. 保存經篩選的長期生活記憶，延續先前話題。
4. 記錄使用者不熟悉的單字與句型，安排後續複習。
5. 提供中文救援輸入，協助使用者繼續以英文表達。
6. 允許使用者隨時拒絕、延後或停止主動互動。

本版本只開發 Mac 功能，不包含 Raspberry Pi、鏡頭、手勢辨識、螢幕監控、檔案修改、日文或國考模組。

---

## 2. 使用流程

### 2.1 主動邀請

系統依照以下資訊判斷是否邀請使用者：

- 是否處於勿擾狀態。
- 距離上次互動多久。
- 今天是否已完成練習。
- 是否有到期的複習內容。
- 最近的主動邀請是否被拒絕。
- 是否位於使用者允許主動互動的時段。

系統先提出短邀請：

```text
Do you have a minute to practice English?
```

使用者可：

- 按 Enter 或輸入 `/accept` 接受。
- 按 Esc 或輸入 `/busy 30m` 延後。
- 輸入 `/dnd` 關閉主動邀請。
- 輸入 `/available` 恢復主動邀請。

### 2.2 記憶延續對話

若系統記得：

```text
Andy is the user's university classmate.
Andy recently changed jobs.
```

可以主動詢問：

```text
How has Andy been doing since he changed jobs?
```

只有 `proactive_use_allowed = true` 的記憶可用於主動開場。

### 2.3 中文救援

使用者不知道如何用英文表達時，可輸入：

```text
/help 我不會說出軌，Anny 跟 Larry 出軌了
```

系統回覆自然英文、替代說法與簡短中文差異：

```text
Anny cheated on her partner with Larry.
Anny and Larry had an affair.
```

`/help` 只提供協助，不把英文句子自動代入目前對話。

其他模式：

```text
/hint <內容>     只提供關鍵字或句型
/say <中文>      翻成英文並代入目前對話
/explain <英文>  以中文簡短解釋
```

使用者透過 `/help` 或 `/hint` 求助的詞彙，記入學習紀錄；例句中的生活事件不得直接寫入長期記憶。

---

## 3. 第一版功能範圍

### 3.1 必做

- FastAPI 背景服務。
- Textual 終端介面。
- 文字英文對話。
- `/help`、`/hint`、`/say`、`/explain`。
- `/accept`、`/busy`、`/dnd`、`/available`。
- 對話紀錄。
- 可管理的長期記憶。
- 英文學習項目與複習日期。
- 規則式主動邀請排程。
- LLM provider abstraction。
- SQLite persistence。
- 單元與整合測試。

### 3.2 第一版後段加入

- Mac 麥克風輸入。
- Voice Activity Detection。
- 本地或可替換的 Speech-to-Text。
- macOS 語音輸出。
- `/repeat`、`/slower`。

### 3.3 不做

- Raspberry Pi、MQTT 或其他硬體。
- Webcam、手勢、臉部或情緒辨識。
- 讀取 Mac 螢幕內容。
- 任意 shell 或檔案操作。
- 多使用者。
- 多 agent。
- 日文與考試模組。
- 音素級發音評分。
- 自行訓練大型模型。

---

## 4. 系統架構

```text
Textual UI
    │
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

### 4.1 原則

- UI 不直接存取資料庫或 LLM，只呼叫 Core API。
- 主動排程、記憶權限與勿擾狀態由程式碼判斷，不交給 LLM 決定。
- 所有外部 AI 與語音服務置於 provider interface 後方。
- 測試使用 fake provider，不呼叫付費 API。
- 所有時間使用含時區的 ISO 8601，預設 `Asia/Taipei`。

---

## 5. 建議技術棧

| 用途 | 技術 |
|---|---|
| API | FastAPI、Uvicorn |
| Terminal UI | Textual |
| Database | SQLite |
| ORM | SQLAlchemy 2.x |
| Migration | Alembic |
| Schema | Pydantic v2 |
| Settings | Pydantic Settings |
| Scheduler | APScheduler 3.x |
| Tests | pytest、pytest-asyncio |
| Lint／format | Ruff |
| Type check | mypy |
| STT | whisper.cpp provider，後段加入 |
| VAD | Silero VAD，後段加入 |
| TTS | macOS system voice provider，後段加入 |

不要加入 LangChain、Letta、Mem0 或其他大型 agent framework。

---

## 6. Repository 結構

```text
companion/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── alembic.ini
├── migrations/
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
│   └── integration/
└── data/
    └── .gitkeep
```

`data/`、`.env`、對話內容、音訊與模型檔不得提交 Git。

---

## 7. 資料模型

### users

- `id`
- `display_name`
- `timezone`
- `target_language`
- `created_at`

第一版建立單一預設使用者，但資料表仍保留 `user_id`。

### people

- `id`
- `user_id`
- `canonical_name`
- `aliases_json`
- `relationship_to_user`
- `created_at`

### conversations

- `id`
- `user_id`
- `mode`: `text | voice | mixed`
- `private_mode`
- `started_at`
- `ended_at`
- `summary`

### messages

- `id`
- `conversation_id`
- `role`: `user | assistant | system`
- `content`
- `language`
- `source`: `terminal | voice | system`
- `created_at`

### memories

- `id`
- `user_id`
- `subject_person_id` nullable
- `category`
- `fact_text`
- `source_conversation_id` nullable
- `confidence`
- `sensitivity`: `normal | private | highly_private`
- `proactive_use_allowed`
- `status`: `candidate | active | disputed | superseded | deleted`
- `created_at`
- `last_confirmed_at` nullable
- `expires_at` nullable

### learning_items

- `id`
- `user_id`
- `item_type`: `vocabulary | grammar | expression`
- `key`
- `explanation_zh`
- `created_at`
- `next_review_at` nullable

### learning_attempts

- `id`
- `learning_item_id`
- `conversation_id` nullable
- `result`: `helped | incorrect | correct`
- `hint_count`
- `created_at`

### availability_overrides

- `id`
- `user_id`
- `state`: `available | busy | dnd`
- `starts_at`
- `expires_at` nullable
- `source`: `terminal | system`

### proactive_decisions

- `id`
- `user_id`
- `decision`: `invite | defer | skip`
- `reason_codes_json`
- `outcome`: `accepted | rejected | ignored | pending`
- `created_at`

---

## 8. 記憶規則

1. 原始對話與長期記憶分開保存。
2. LLM 只能產生候選記憶，Memory Service 決定是否寫入。
3. `/private` 模式不建立長期記憶。
4. `/help`、`/hint` 的例句不直接建立生活記憶。
5. 高敏感或低信心候選必須由使用者確認。
6. 新舊記憶衝突時不得直接覆寫，舊記憶標為 `disputed` 或 `superseded`。
7. 主動開場只能使用 `active` 且 `proactive_use_allowed = true` 的記憶。
8. 所有記憶可查看、修改、停用或軟刪除。

記憶指令：

```text
/remember <內容>
/memories <query>
/forget <query>
/private
```

`/forget` 必須先列出候選並要求確認，不得模糊批次刪除。

---

## 9. 主動邀請規則

第一版採可解釋規則，不訓練預測模型。

### Hard block

以下任一成立時不得邀請：

- DND 尚未到期。
- 正在進行對話。
- 不在使用者允許時段。
- 距離上次拒絕尚未超過 cooldown。

### Invite 條件

通過 hard block 後，符合下列任一條件可成為候選：

- 今天尚未練習且距離上次邀請超過設定時間。
- 有到期的 learning item。
- 使用者預約的練習時間到達。

每次決策必須保存 `reason_codes`，例如：

```json
{
  "decision": "defer",
  "reason_codes": ["recent_rejection", "cooldown_active"]
}
```

使用者拒絕後，預設 30 分鐘內不得再次主動邀請；時間由設定檔控制。

---

## 10. Slash commands

| Command | 行為 |
|---|---|
| `/help <中文>` | 提供完整英文表達，不代入對話 |
| `/hint <內容>` | 只提供關鍵字或句型 |
| `/say <中文>` | 翻成英文並代入目前對話 |
| `/explain <英文>` | 中文簡短解釋 |
| `/accept` | 接受主動邀請 |
| `/busy <duration>` | 暫時勿擾，例如 `/busy 30m` |
| `/dnd` | 無期限勿擾，直到解除 |
| `/available` | 解除 busy／dnd |
| `/remember <內容>` | 明確建立候選記憶 |
| `/memories <query>` | 搜尋記憶 |
| `/forget <query>` | 列出候選並確認刪除 |
| `/private` | 切換目前對話的私密模式 |
| `/review` | 開始到期複習 |
| `/status` | 顯示系統狀態與最近決策 |
| `/repeat` | 重播上一句，語音階段加入 |
| `/slower` | 降低 TTS 速度，語音階段加入 |

Command parser 不得使用 LLM；未知 command 回傳可用指令清單。

---

## 11. Core API

### System

```text
GET /health
GET /v1/state
```

### Conversations

```text
POST /v1/conversations
GET  /v1/conversations/{id}
POST /v1/conversations/{id}/messages
POST /v1/conversations/{id}/end
```

### Commands

```text
POST /v1/commands/execute
```

Request：

```json
{
  "raw": "/help 我不會說出軌",
  "conversation_id": "optional-id"
}
```

### Memories

```text
POST   /v1/memories
GET    /v1/memories?query=
PATCH  /v1/memories/{id}
DELETE /v1/memories/{id}
```

### Availability

```text
GET  /v1/availability
POST /v1/availability/override
```

### Proactive

```text
POST /v1/proactive/evaluate
GET  /v1/proactive/decisions
```

---

## 12. Provider interfaces

### LLMProvider

```python
class LLMProvider(Protocol):
    async def chat(self, request: ChatRequest) -> ChatResponse: ...
    async def extract_memory_candidates(
        self, request: MemoryExtractionRequest
    ) -> list[MemoryCandidate]: ...
    async def provide_language_help(
        self, request: LanguageHelpRequest
    ) -> LanguageHelpResponse: ...
```

至少提供：

- `FakeLLMProvider`：測試使用。
- 一個實際 LLM provider，由環境變數設定。

### SpeechProvider

```python
class SpeechToTextProvider(Protocol):
    async def transcribe(self, audio_path: Path) -> Transcript: ...

class TextToSpeechProvider(Protocol):
    async def synthesize(self, text: str, rate: float) -> AudioResult: ...
```

語音 provider 在文字版穩定後實作。

---

## 13. Textual UI

介面包含：

- 對話與系統訊息區。
- 固定輸入框。
- Core 與 LLM 連線狀態。
- `AVAILABLE / BUSY / DND`。
- Busy／DND 剩餘時間。
- 當前對話是否 private。
- 今天是否完成練習。

鍵盤：

- Enter：送出輸入；若有 pending invitation 且輸入為空則接受。
- Esc：若有 pending invitation 則拒絕；否則不執行破壞性操作。
- Ctrl+C：正常關閉 UI，不破壞背景資料。

---

## 14. 開發順序

### M0：骨架與狀態

完成：

- Repository 結構。
- FastAPI `/health`、`/v1/state`。
- Settings。
- SQLite、SQLAlchemy、Alembic。
- Availability state 與 override。
- 最小 Textual UI。
- pytest、Ruff、mypy。

驗收：

- Core 與 UI 可分別啟動。
- UI 顯示 Core 狀態。
- `/busy 1m`、`/dnd`、`/available` 狀態正確。
- 重啟後資料仍存在。
- lint、type check、tests 通過。

### M1：文字對話與救援

完成：

- Conversation／Message persistence。
- LLM provider abstraction。
- `/help`、`/hint`、`/say`、`/explain`。
- Fake provider tests。

驗收：

- 可進行多回合英文文字對話。
- `/help` 不自動代入對話。
- `/say` 會代入對話。
- `/help` 例句不建立生活記憶。

### M2：長期記憶

完成：

- People、Memory CRUD。
- `/remember`、`/memories`、`/forget`、`/private`。
- 候選記憶抽取與確認。
- proactive-use 權限。

驗收：

- 每筆記憶可追溯來源。
- Private conversation 不建立長期記憶。
- 禁止主動使用的記憶不進入開場 context。
- 衝突內容不直接覆寫。

### M3：英文學習閉環

完成：

- Learning item／attempt。
- `/help`、`/hint` 自動建立或更新學習項目。
- `/review`。
- 簡單間隔複習日期。
- 從允許的生活記憶與到期 learning item 產生話題。

驗收：

- 求助過的 expression 可在後續複習。
- 可查看到期項目。
- 開場內容同時符合生活記憶與學習目標。

### M4：主動邀請

完成：

- APScheduler。
- 規則式決策。
- 邀請接受／拒絕／忽略結果。
- cooldown。
- 決策理由紀錄。

驗收：

- Hard block 永遠優先。
- 拒絕後 cooldown 期間不再邀請。
- 每次 invite／defer／skip 都有 reason codes。
- 測試使用時間注入，不依賴真實等待。

### M5：Mac 語音

完成：

- 麥克風錄音。
- Silero VAD。
- STT provider。
- macOS TTS provider。
- `/repeat`、`/slower`。
- 文字與語音混合對話。

驗收：

- 可完成至少五回合語音對話。
- 語音失敗時可回到文字模式。
- 記錄 VAD、STT、LLM、TTS 各階段延遲。
- 原始錄音預設在成功轉錄後刪除。

---

## 15. 測試要求

必要 unit tests：

- Slash command parsing。
- Duration parsing。
- Availability override priority 與 expiry。
- Proactive hard blocks 與 cooldown。
- `/help` 和 `/hint` 不寫入生活記憶。
- Private conversation memory policy。
- Memory conflict handling。
- Learning item 去重與複習日期。

必要 integration tests：

- UI command → Core → database。
- Conversation → fake LLM → messages。
- Memory extraction → policy → database。
- Proactive evaluation → invitation outcome。
- Core restart → state persistence。

測試不得呼叫真實付費 API，也不得依賴實際等待時間。

---

## 16. 安全與隱私

- API key 由環境變數讀取，不提交 Git。
- `.env.example` 只放欄位名稱與假值。
- 對話、記憶、音訊與資料庫檔案不提交 Git。
- Private conversation 不建立長期記憶。
- 原始錄音預設轉錄後刪除。
- 第一版不讀取使用者檔案、螢幕或其他 App 資料。
- 第一版不執行 shell command。

---

## 17. 第一個 Codex 任務

```text
請完整閱讀本技術規格，只實作 M0，不得提前實作 M1 之後的功能。

需求：
1. 建立 Python 3.12 專案與本文件指定的 repository 結構。
2. 建立 FastAPI Companion Core，提供 GET /health 與 GET /v1/state。
3. 使用 SQLite、SQLAlchemy 2.x 與 Alembic。
4. 實作 AvailabilityState：available、busy、dnd。
5. 實作 availability override 與到期時間；DND 在解除前不得被低優先權狀態覆蓋。
6. 實作 /busy <duration>、/dnd、/available、/status 的 deterministic command parser；不要使用 LLM。
7. 建立最小 Textual UI，包含訊息區、輸入框、Core 狀態、availability 與剩餘時間。
8. 建立設定管理、.env.example 與 .gitignore。
9. 加入 pytest、pytest-asyncio、Ruff、mypy。
10. 測試 duration parsing、override priority、expiry、狀態 persistence 與未知 command。
11. 測試時使用可注入 clock，不得真的等待一分鐘。
12. 不得加入 LLM、語音、記憶抽取、scheduler、LangChain、Mem0、Letta、硬體或檔案 agent。

完成後執行 Ruff、mypy 與 pytest，回報結果、啟動方式、目錄結構及尚未實作項目。
```
