# M1：Groq 文字對話與語言救援

## 前置條件

- M0 已完成。
- Ruff、mypy、pytest 全部通過。
- Core、Textual UI、SQLite 與 M0 commands 可正常使用。

實作前只需閱讀：

1. `docs/PROJECT_OVERVIEW.md`
2. `docs/ARCHITECTURE.md`
3. `docs/milestones/M1_TEXT_CHAT.md`

不得閱讀或實作 M2 之後的 milestone。

## 本次目標

完成英文文字對話及以下語言救援功能：

```text
/help <中文>
/hint <內容>
/say <中文>
/explain <英文>
```

實際 LLM 使用 Groq；一般自動測試使用 FakeLLMProvider。

## 1. 設定

新增：

```env
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
GROQ_BASE_URL=https://api.groq.com/openai/v1
LLM_TIMEOUT_SECONDS=30
```

規則：

- 真實 key 只放在本機 `.env` 或環境變數。
- `.env.example` 的 `GROQ_API_KEY` 必須為空。
- key 不得出現在程式碼、測試、exception、log 或 Git。
- 缺少 key 時，Core 必須回傳清楚且不含秘密的設定錯誤。
- 模型名稱必須由設定讀取，不得散落在 business logic。

## 2. Provider

定義：

```python
class LLMProvider(Protocol):
    async def chat(self, request: ChatRequest) -> ChatResponse: ...
    async def provide_language_help(
        self, request: LanguageHelpRequest
    ) -> LanguageHelpResponse: ...
```

實作：

- `FakeLLMProvider`：unit／integration tests。
- `GroqLLMProvider`：實際執行。

Groq provider 必須處理：

- Timeout。
- Authentication error。
- Rate limit。
- 暫時性 API／網路錯誤。
- 空回覆或格式不符。

不得無限重試。M1 最多允許一次短暫錯誤重試；authentication 與 rate limit 不自動重試。

## 3. 資料模型

新增 Alembic migration。

### conversations

- `id`
- `user_id`
- `mode`: M1 固定 `text`
- `private_mode`: M1 預設 `false`
- `started_at`
- `ended_at` nullable

### messages

- `id`
- `conversation_id`
- `role`: `user | assistant | system`
- `content`
- `language`
- `source`: M1 固定 `terminal`
- `created_at`

規則：

- 對話與訊息寫入 SQLite。
- LLM 失敗時保留使用者訊息，並回傳可重試的錯誤狀態。
- 錯誤訊息不冒充 assistant 正常回答。
- M1 不建立 people、memories 或 learning items。

## 4. API

### Conversations

```text
POST /v1/conversations
GET  /v1/conversations/{id}
POST /v1/conversations/{id}/messages
POST /v1/conversations/{id}/end
```

建立對話 response 至少包含：

```json
{
  "id": "conversation-id",
  "mode": "text",
  "started_at": "2026-07-19T20:00:00+08:00"
}
```

送出一般訊息：

```json
{
  "content": "I had a difficult day at school."
}
```

Core 將有限的近期訊息組成 context，呼叫 provider，再保存 assistant response。

M1 以最近訊息數量限制 context；上限由設定控制，預設 20 則。不要在 M1 實作摘要、RAG 或長期記憶。

### Commands

沿用：

```text
POST /v1/commands/execute
```

Request：

```json
{
  "raw": "/help 我不會說出軌，Anny 跟 Larry 出軌了",
  "conversation_id": "conversation-id"
}
```

## 5. Command 行為

### `/help <中文>`

提供：

- 一句自然英文。
- 最多兩句替代說法。
- 簡短中文語用差異。

不把產生的英文當成使用者訊息代入對話。

Response schema：

```json
{
  "command": "help",
  "natural_expression": "Anny cheated on her partner with Larry.",
  "alternatives": ["Anny and Larry had an affair."],
  "notes_zh": "前句強調對伴侶不忠，後句強調兩人有不正當關係。",
  "inserted_into_conversation": false
}
```

### `/hint <內容>`

只提供關鍵字、片語或句型，不直接提供完整答案；最多三項。

### `/say <中文>`

產生自然英文，並將該英文以使用者訊息寫入目前 conversation，再讓 AI 繼續回答。

Response 必須明確回傳實際代入的英文。

### `/explain <英文>`

以簡短中文解釋：

- 整句意思。
- 必要的語法或語用差異。

不要產生長篇英文教學。

### 驗證

- 缺少內容時回傳 usage。
- `/say` 必須有有效的 conversation ID。
- `/help`、`/hint`、`/explain` 可不依附 conversation。
- 未知 command 仍由 deterministic parser 處理。
- Command 名稱判斷不得交給 LLM。

## 6. Prompt 規則

建立集中管理的 prompt templates，不要把 prompt 分散在 route handler。

一般對話：

- 預設使用英文回答。
- 以自然日常對話為主，不要每句都糾正文法。
- 回覆簡潔，方便口說練習。
- 不假裝知道尚未提供的個人資訊。
- M1 不保存或引用長期生活記憶。

語言救援：

- 優先提供自然口語英文，不只逐字翻譯。
- 保留使用者提供的姓名，不自行更改人物。
- `/hint` 不得洩漏完整句子。
- structured response 優先使用 JSON schema／JSON mode；解析失敗時回傳受控錯誤，不猜測欄位。

## 7. Textual UI

新增：

- 建立／結束文字 conversation。
- 顯示 user 與 assistant 訊息。
- 顯示 Groq 連線／設定狀態，但不得顯示 key。
- 支援四個 M1 commands。
- `/help` 與 `/hint` 結果使用與正常對話不同的視覺標籤。
- API 錯誤顯示為 system message，UI 不 crash。
- 等待 LLM 時顯示 loading 狀態，避免重複送出。

M0 commands 必須繼續正常運作。

## 8. 測試

### Unit tests

- `LLMProvider` request／response schema。
- `/help` 不代入 conversation。
- `/hint` 最多三項且不回傳完整答案。
- `/say` 代入翻譯後英文並繼續對話。
- `/explain` response schema。
- 缺少 command content。
- `/say` 缺少或使用無效 conversation ID。
- Provider timeout、auth、rate limit、空回覆與格式錯誤。
- 確認 log／error 不包含測試用假 key。

### Integration tests

- 建立 conversation → 發送訊息 → FakeLLMProvider → 保存兩側訊息。
- Core restart → conversation history 仍存在。
- `/help` 不增加 conversation message。
- `/say` 增加 user translation 與 assistant response。
- M0 commands regression tests。

一般測試不得呼叫 Groq。

### Live smoke test

建立：

```text
tests/live/test_groq_live.py
```

只有同時滿足以下條件才執行：

```text
RUN_LIVE_API_TESTS=1
GROQ_API_KEY 已設定
```

否則自動 skip。

Live test 只驗證：

- Groq request 成功。
- 回覆非空。
- `/help` structured response 可解析。
- 不輸出 API key。

不要逐字比對模型回答。

執行：

```bash
RUN_LIVE_API_TESTS=1 pytest tests/live/test_groq_live.py
```

## M1 禁止事項

不得加入：

- 長期記憶抽取、people 或 memory tables。
- Learning item 或複習排程。
- APScheduler 或主動邀請。
- 語音、STT、TTS。
- Raspberry Pi、鏡頭、手勢或 MQTT。
- 檔案工具、shell command。
- LangChain、Letta、Mem0。
- 多 agent。

## 驗收條件

1. 可建立並完成多回合英文文字對話。
2. 四個語言救援 commands 行為符合規格。
3. M0 commands 沒有 regression。
4. 對話重啟後仍存在。
5. 沒有 key 時顯示清楚設定錯誤。
6. 一般 Ruff、mypy、pytest 全部通過，且不呼叫 Groq。
7. 使用者已設定 key 時，live Groq smoke test 通過。
8. README 更新 M1 設定、啟動與測試方式。

## 給 Codex 的任務指令

```text
請只閱讀：
1. docs/PROJECT_OVERVIEW.md
2. docs/ARCHITECTURE.md
3. docs/milestones/M1_TEXT_CHAT.md

先確認 M0 的 Ruff、mypy 與 pytest 全部通過，再依照 M1_TEXT_CHAT.md 完成 M1。不得閱讀或實作 M2 之後的 milestone。

一般測試必須使用 FakeLLMProvider，不得呼叫真實 API。本機若已設定 GROQ_API_KEY，完成後可使用 RUN_LIVE_API_TESTS=1 執行一次 Groq live smoke test；不得顯示、記錄或提交 API key。

完成後執行 Ruff、mypy 與 pytest，修正所有問題，再回報：
- 新增或修改的主要檔案
- Alembic migration
- Groq 設定方式
- Ruff、mypy、一般 pytest 實際結果
- live smoke test 是通過或因未設定 key 而 skip
- 尚未實作的後續功能
```
