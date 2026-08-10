# M2：可管理的長期記憶

## 前置條件

- M0、M1 已完成。
- Groq 文字對話與四個語言救援指令正常。
- Ruff、mypy、一般 pytest 全部通過。
- Groq live smoke test 已通過。

實作前只需閱讀：

1. `docs/PROJECT_OVERVIEW.md`
2. `docs/ARCHITECTURE.md`
3. `docs/milestones/M2_MEMORY.md`

不得閱讀或實作 M3 之後的 milestone。

## 本次目標

讓 AI 能跨 conversation 記住使用者明確提供的個人資訊、人物關係與生活事件，並讓使用者查看、確認、修正、停用或刪除記憶。

M2 不做向量資料庫、學習紀錄、複習排程或主動邀請。

## 功能地圖

| 功能 | 用途 | 觸發方式 | 是否呼叫 LLM |
|---|---|---|---|
| 明確記住 | 使用者指定一件一定要保存的事 | `/remember <內容>` | 只用於分類與敏感度建議，不改寫事實 |
| 自動抽取 | 對話結束後找出值得跨對話保存的事實 | conversation end | 是，回傳 structured candidates |
| 搜尋記憶 | 查看 AI 目前記得什麼 | `/memories [query]` | 否，SQLite 查詢 |
| 管理單筆記憶 | 查看、核准或修改指定記憶 | `/memory <action> <id>` | 否 |
| 忘記 | 軟刪除使用者指定的記憶 | `/forget <id或query>` | 否 |
| 私密對話 | 本次對話不產生長期記憶 | `/private on或off` | 否 |
| 對話取用記憶 | 新對話加入相關的 active memories | 每次一般聊天前 | 檢索不用 LLM；聊天仍使用既有 LLM |

`/remember` 與自動抽取不重複：前者是使用者明確指定，立即生效；後者是系統從自然對話中找候選資訊。

## 1. 記憶類型

M2 支援：

```text
profile        使用者基本資料與穩定偏好
people         人物及其與使用者的關係
relationship   人際關係與近期變化
school         學業事件
work           工作事件
exercise       運動事件
life           其他生活事件
custom         使用者自訂分類
```

分類用於管理，不建立實體巢狀資料夾。底層統一保存於 SQLite。

## 2. 資料模型

新增 Alembic migration。

### people

- `id`
- `user_id`
- `canonical_name`
- `aliases_json`
- `relationship_to_user` nullable
- `created_at`
- `updated_at`

規則：

- 同一使用者的 canonical name 不區分大小寫去重。
- alias 不得自動合併到既有人物，除非名稱完全一致或使用者確認。
- 不確定 Andy 與 Andrew 是否同一人時，建立候選關係，不可自行合併。

### memories

- `id`
- `user_id`
- `subject_person_id` nullable
- `category`
- `fact_text`
- `source_conversation_id` nullable
- `source_message_id` nullable
- `confidence` nullable
- `sensitivity`: `normal | private | highly_private`
- `proactive_use_allowed`
- `status`: `candidate | active | disputed | superseded | deleted`
- `created_at`
- `updated_at`
- `last_confirmed_at` nullable
- `expires_at` nullable

### memory_audit_log

- `id`
- `memory_id`
- `action`: `created | confirmed | edited | disabled | deleted | superseded | disputed`
- `old_value_json` nullable
- `new_value_json` nullable
- `source`: `user_command | automatic_extraction | system`
- `created_at`

每次記憶變更都要寫 audit log。

## 3. 建立記憶

### 3.1 使用者明確建立

```text
/remember Andy 是我的大學同學
```

明確 `/remember` 建立的記憶：

- 預設 `status = active`。
- 預設 `sensitivity = normal`。
- 預設 `proactive_use_allowed = true`。
- `last_confirmed_at` 設為建立時間。
- 必須保存原始指令作為來源。

LLM 可協助判斷 category、subject 與 sensitivity，但 `fact_text` 必須保留使用者原意，不得增加未說過的細節。若分類服務失敗，記憶仍以 `category = custom` 保存。

若內容明顯涉及健康、性、財務、帳號憑證或高度私密關係，系統必須要求確認 sensitivity 與是否允許主動使用，不得自行設為 normal。

### 3.2 對話自動抽取

conversation 結束時，由 LLMProvider 產生 structured memory candidates。

每個 candidate 至少包含：

```json
{
  "category": "people",
  "fact_text": "Andy is the user's university classmate.",
  "subject_name": "Andy",
  "sensitivity": "normal",
  "proactive_use_recommended": true,
  "source_message_ids": ["message-id"]
}
```

LLM 只能提出 candidate，Memory Policy 決定狀態：

- normal、來源明確、非重複：可自動設為 active。
- private／highly_private：維持 candidate，等待使用者確認。
- 推測、主觀判斷或來源不明：不得寫入。
- 一般寒暄、當次暫時狀態或 AI 自己的內容：不建立記憶。
- `/help`、`/hint`、`/explain` 的內容不參與生活記憶抽取。
- `/say` 代入的英文可參與抽取，但來源必須追溯至使用者原始指令。
- private conversation 不進行抽取。

不得只憑 LLM 提供的 confidence 決定敏感記憶是否啟用。

## 4. Private mode

新增：

```text
/private on
/private off
/private
```

行為：

- `/private` 無參數時顯示目前狀態。
- private mode 只影響目前 conversation。
- private conversation 仍可保存在 conversation history，但不得產生長期記憶。
- UI 必須清楚顯示 private mode。
- 切換 private mode 寫入 system message。

M2 不做「完全不保存對話」模式。

## 5. 記憶指令

### `/remember <內容>`

明確建立記憶；回傳 ID、分類、狀態與是否允許主動使用。

### `/memories [query]`

搜尋 active／candidate／disputed 記憶，預設不顯示 deleted。

支援：

```text
/memories
/memories Andy
/memories category:school
/memories status:candidate
```

輸出必須包含：

- 短 ID。
- fact text。
- category。
- status。
- sensitivity。
- proactive-use 狀態。
- 來源 conversation 或 explicit command。

### `/memory <action> <id>`

以同一個入口管理單筆記憶：

```text
/memory show <id>
/memory approve <id>
/memory edit <id> <新內容>
```

- `show`：查看完整內容、來源與 audit history。
- `approve`：將 candidate 設為 active，更新 `last_confirmed_at`。
- `edit`：修改 fact text，保留舊值於 audit log。

`proactive_use_allowed` 欄位先保存供 M4 使用；M2 不提供 enable／disable 指令，避免現在出現尚未有實際效果的功能。

### `/forget <query-or-id>`

- 精確 ID：顯示內容並要求確認。
- 模糊 query：先列出候選，不直接刪除。
- 確認後執行 soft delete，保留 audit log。
- 不得使用 LLM 決定刪除目標。

待確認 candidates 統一使用：

```text
/memories status:candidate
```

## 6. 記憶衝突與重複

### 重複

新增前以正規化文字、subject、category 與來源比較：

- 完全相同：不重複建立，只更新 `last_confirmed_at` 或來源。
- 語意可能相同但文字不同：建立 candidate 或交由使用者選擇，不自動覆寫。

M2 不加入 embedding；可由 LLM 提供重複建議，但 deterministic policy 做最終決定。

### 衝突

例如已有：

```text
Andy works at Company A.
```

新對話說：

```text
Andy changed to Company B.
```

不可直接刪除舊記憶。新記憶設為 active，舊記憶設為 superseded，兩者透過 audit log 保留演變。

若無法判斷是更新或矛盾，將相關記憶設為 disputed 並要求使用者確認。

## 7. 對話使用長期記憶

開始或進行 conversation 時，建立 `MemoryContextBuilder`。

M2 使用 SQLite 查詢，不使用 RAG 或 vector DB。

選取順序：

1. 使用者 profile 類 active 記憶。
2. 訊息中明確提及人物的 active 記憶。
3. 與訊息關鍵字或分類直接相符的 active 記憶。
4. 最近確認的少量 active 記憶。

限制：

- 只使用 `status = active`。
- 一般對話可使用 private 記憶，但 highly_private 預設不注入，除非使用者明確提及相關主題。
- M2 尚未實作主動邀請；`proactive_use_allowed` 先保存並在查詢中顯示。
- 注入數量由設定控制，預設最多 20 筆。
- 注入 prompt 時標示為「可能過時的使用者記憶」，模型不得當成不可質疑事實。
- 回答不得揭露 memory ID、confidence 或內部 policy。

新 conversation 應能延續已保存資訊，例如：

```text
User: Do you remember who Andy is?
AI: Yes. You told me Andy is your university classmate.
```

## 8. API

新增：

```text
POST   /v1/memories
GET    /v1/memories?query=&category=&status=
GET    /v1/memories/{id}
PATCH  /v1/memories/{id}
DELETE /v1/memories/{id}
POST   /v1/memories/{id}/confirm
GET    /v1/memories/{id}/audit
POST   /v1/conversations/{id}/extract-memories
```

`extract-memories` 必須 idempotent；同一 conversation 重複呼叫不得重複建立相同記憶。

## 9. Provider 擴充

在既有 LLMProvider 加入：

```python
async def extract_memory_candidates(
    self, request: MemoryExtractionRequest
) -> list[MemoryCandidate]: ...
```

要求：

- Groq 使用 structured JSON response。
- Fake provider 可回傳固定 candidates 供測試。
- 解析錯誤不得建立部分或猜測記憶。
- Provider error 不影響 conversation 結束；顯示 extraction failed，允許稍後重試。

## 10. Prompt templates

Prompt 必須集中放在 memory module，不得散落在 API route 或 UI。

### 10.1 `/remember` 分類提示詞

用途：只為使用者明確要求保存的內容建議 category、subject 與 sensitivity，不判斷內容真假，也不增加資訊。

```text
SYSTEM
You classify a memory that the user explicitly asked to save.

Rules:
1. Preserve the user's meaning exactly. Do not add, infer, correct, or embellish facts.
2. Choose exactly one category from:
   profile, people, relationship, school, work, exercise, life, custom.
3. Extract subject_name only when a named person is clearly the subject; otherwise use null.
4. Choose sensitivity:
   - normal: ordinary preferences, study, work, exercise, non-sensitive life events
   - private: relationships, gossip, health, finances, or information not normally public
   - highly_private: sexual information, credentials, precise financial secrets, or similarly sensitive data
5. Output valid JSON only.

OUTPUT SCHEMA
{
  "category": "profile|people|relationship|school|work|exercise|life|custom",
  "subject_name": "string|null",
  "sensitivity": "normal|private|highly_private"
}

USER MEMORY
{{memory_text}}
```

`fact_text` 使用原始 `memory_text`，不得使用模型改寫版。

### 10.2 對話記憶抽取提示詞

用途：對話結束後產生值得跨對話保留的 candidates。

```text
SYSTEM
Extract durable, user-provided memories from the conversation.

Save only information that could be useful in a future conversation, such as:
- stable user profile or preference
- named people and their relationship to the user
- meaningful school, work, exercise, relationship, or life events
- plans or ongoing situations likely to matter later

Do not save:
- anything stated only by the assistant
- guesses, interpretations, personality judgments, or inferred emotions
- greetings, filler, jokes, or temporary conversational wording
- language examples produced by /help, /hint, or /explain
- information from a private conversation
- secrets or credentials
- duplicate facts already supplied in EXISTING MEMORIES

For /say, treat the translated sentence as user-provided, but retain its original source message id.
Do not combine different people. Preserve exact names.
Output a JSON array only. Return [] when nothing should be saved.

OUTPUT ITEM SCHEMA
{
  "category": "profile|people|relationship|school|work|exercise|life|custom",
  "fact_text": "one concise factual statement",
  "subject_name": "string|null",
  "sensitivity": "normal|private|highly_private",
  "proactive_use_recommended": true,
  "source_message_ids": ["id"]
}

EXISTING MEMORIES
{{existing_memories_json}}

CONVERSATION
{{conversation_messages_json}}
```

程式碼必須再次驗證來源 role、private mode、schema、敏感度與重複；不得直接信任模型輸出。

### 10.3 記憶 context 注入提示詞

用途：把 SQLite 選出的相關記憶加入一般聊天，而不讓模型過度確信或主動洩漏。

```text
SYSTEM CONTEXT
The following entries are user-controlled memories from earlier conversations.
They may be incomplete or outdated.

Use them only when relevant to the user's current message.
Do not list or reveal memories without a conversational reason.
Do not mention internal IDs, categories, confidence, sensitivity, or storage.
Do not claim certainty when the user indicates that a memory has changed.
If current user input conflicts with a memory, trust the current user input and do not silently update storage.

MEMORIES
{{selected_memories_json}}
```

### 10.4 Prompt 測試要求

- 使用 FakeLLMProvider 驗證 request 中不包含 assistant-only facts。
- `/help` 範例不得進入 extraction request。
- private conversation 不得建立 extraction request。
- Prompt 中只放必要的最近對話與既有記憶，不能把整個資料庫塞入。

## 11. Textual UI

新增：

- 顯示目前 conversation 的 private mode。
- 支援全部 M2 commands。
- Memory list 顯示 status、sensitivity 與 proactive-use。
- Candidate 必須有明確的 confirm／ignore 操作。
- 模糊 `/forget` 顯示候選，不立即刪除。
- Extraction 或 provider error 顯示 system message，UI 不 crash。

## 12. 測試

### Unit tests

- Explicit `/remember` 建立 active memory。
- Private／highly_private candidate 不自動啟用。
- Private conversation 不抽取。
- `/help`、`/hint`、`/explain` 不抽取生活記憶。
- `/say` 保留來源追溯。
- Exact duplicate 去重。
- Superseded／disputed 規則。
- `/memory show／approve／edit` 共用 command namespace。
- Soft delete 與 audit log。
- 模糊 `/forget` 不直接刪除。
- Memory context 只使用允許的 active 記憶。

### Integration tests

- Conversation end → Fake extraction → policy → database。
- 相同 conversation 重複 extraction 不重複建立。
- 新 conversation 能透過 fake LLM 取得既有 memory context。
- Core restart 後 memory 與 audit 仍存在。
- M0、M1 commands regression tests。

一般測試不得呼叫 Groq。

### Live smoke test

擴充 `tests/live/`，只有以下條件才執行：

```text
RUN_LIVE_API_TESTS=1
GROQ_API_KEY 已設定
```

驗證一段短對話能產生符合 schema 的 memory candidates。測試完成後清除該測試資料，不得使用真實私人內容。

## M2 禁止事項

不得加入：

- Learning item、單字紀錄或複習排程。
- APScheduler 或主動邀請。
- Embedding、vector DB、RAG framework。
- 語音、STT、TTS。
- Raspberry Pi、鏡頭、手勢或 MQTT。
- 檔案工具、shell command。
- LangChain、Letta、Mem0。
- 多 agent。

## 驗收條件

1. 使用者可建立、搜尋、查看、確認、修改、停用及刪除記憶。
2. 新 conversation 能延續 active 長期記憶。
3. Private conversation 不建立長期記憶。
4. 敏感 candidate 不會未確認自動啟用。
5. 重複 extraction 不產生重複記憶。
6. 衝突與修改保留 audit history。
7. M0、M1 功能沒有 regression。
8. Ruff、mypy、一般 pytest 全部通過。
9. 已設定 key 時，Groq memory extraction live smoke test 通過。
10. README 更新 M2 commands、資料政策與測試方式。

## 給 Codex 的任務指令

```text
請只閱讀：
1. docs/PROJECT_OVERVIEW.md
2. docs/ARCHITECTURE.md
3. docs/milestones/M2_MEMORY.md

先確認 M0、M1 的 Ruff、mypy 與 pytest 全部通過，並確認 Groq UI command wiring 已修正，再依照 M2_MEMORY.md 完成 M2。不得閱讀或實作 M3 之後的 milestone。

一般測試必須使用 FakeLLMProvider。本機若已設定 GROQ_API_KEY，完成後可使用 RUN_LIVE_API_TESTS=1 執行一次不含真實私人資訊的 memory extraction smoke test；不得顯示、記錄或提交 API key。

完成後執行 Ruff、mypy 與 pytest，修正所有問題，再回報：
- 新增或修改的主要檔案
- Alembic migration 與資料模型
- 記憶抽取與 policy 流程
- M2 commands
- Ruff、mypy、一般 pytest 實際結果
- live smoke test 是通過或因未設定 key 而 skip
- 尚未實作的後續功能
```
