# M1：Groq 文字對話與語言救援

## 已完成範圍

M1 加入英文文字 conversation、持久化訊息、LLM provider abstraction、
Groq provider、Fake provider，以及三個語言救援指令。

## Conversation API

```text
POST /v1/conversations
GET  /v1/conversations/{id}
POST /v1/conversations/{id}/messages
POST /v1/conversations/{id}/end
```

- conversation mode 為 `text`。
- user 與 assistant messages 保存於 SQLite。
- 一般對話只送出設定上限內的近期訊息，預設 20 則。
- provider 失敗時保留 user message，回傳受控錯誤及 retryable 狀態；
  錯誤不會保存成 assistant message。

## 語言救援指令

command 名稱由 deterministic parser 判斷：

```text
/help <內容>
/hint <內容>
/say <中文>
```

### `/help`

- 中文或混合內容：提供自然英文、替代說法與簡短中文說明。
- 英文內容：以中文解釋；只有原句不自然時才提供 correction。
- 不將結果加入 conversation。

### `/hint`

回傳一至三個單字、片語或未完成句型，不提供完整翻譯答案，也不加入 conversation。

### `/say`

需要有效的 conversation ID。它產生一句自然英文、以 user message 保存，
再走正常 chat flow 取得並保存 assistant response。

## Provider 與秘密

設定由 `LLM_PROVIDER`、`GROQ_API_KEY`、`GROQ_MODEL`、
`GROQ_BASE_URL` 與 `LLM_TIMEOUT_SECONDS` 提供。prompt templates 集中在
provider 模組，route handler 不保存秘密。

自動測試使用 FakeLLMProvider。只有同時設定 `RUN_LIVE_API_TESTS=1` 與
`GROQ_API_KEY` 時，`tests/live/` 才會呼叫 Groq。

## 驗證重點

- 建立 conversation、保存雙方訊息與 restart persistence。
- `/help`、`/hint` 不增加訊息。
- `/say` 增加翻譯後 user message 與 assistant response。
- timeout、authentication、rate limit、暫時性錯誤與無效回覆。
- M0 commands 無 regression。

長期記憶屬於 M2；學習複習、scheduler、主動邀請與語音仍是後續工作。
