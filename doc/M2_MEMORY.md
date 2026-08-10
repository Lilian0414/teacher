# M2：精簡版長期記憶

## 已完成範圍

M2 讓 Core 保存、搜尋、軟刪除與 recall 使用者長期記憶，並在 conversation
結束時抽取值得保留的 user facts。所有資料保存於 SQLite，不使用 RAG、
embedding 或 vector database。

## 分類與狀態

支援的 category：

```text
people
personal
school_work
relationships
health_fitness
other
```

支援的 status 只有：

```text
active
deleted
```

`deleted` 是 soft delete；一般搜尋與聊天 recall 只使用 active memories。

## 記憶指令

```text
/remember <內容>              立即保存使用者指定的原始意思
/memories [關鍵字]           列出或搜尋 active memories
/forget <memory_id>          預覽目標並要求確認
/forget <memory_id> confirm  確認後 soft-delete
```

`/remember` 可由 provider 建議 category 與人物資訊；provider 失敗時仍以
`other` 保存原始內容。`/forget` 只接受可唯一辨識的 ID，且第一次呼叫不刪除。

## Conversation-end extraction

`POST /v1/conversations/{id}/end` 先結束 conversation，再請 provider 回傳
structured memory candidates。Core 只把已保存的 user messages 放入 extraction
request，並逐筆套用 deterministic policy：

- source IDs 必須全部屬於該 conversation 的 user messages。
- 只有一般寒暄時不保存。
- category 必須是上述六種之一。
- 完全重複的記憶不建立第二筆。
- candidate 可明確更新既有 active memory。
- provider extraction error 不影響 conversation 已結束的狀態，並以受控錯誤回傳。

## Recall

`MemoryContextBuilder` 以人物名稱、英文詞彙重疊與中文 bigram relevance 排序。
每次一般聊天最多選取五筆 active memories，排除無關與 deleted memories。
注入的 prompt 不含 memory ID，並提醒模型記憶可能過時。

## 資料模型

- `people`：canonical name、aliases、relationship 與 timestamps。
- `memories`：category、content、optional person、source conversation、
  confidence、status 與 timestamps。

Alembic migration 位於 `migrations/versions/20260719_0003_create_long_term_memory.py`。

## 尚未實作

Private conversations、sensitivity、candidate approval、audit history、conflict／superseded
states、記憶編輯、proactive-use permissions、`/memory` 管理入口及獨立 memory CRUD
API 都不屬於目前 M2。這些功能必須透過未來 OpenSpec change 才能加入。

## 驗證重點

- `/remember`、`/memories` 與 confirmed `/forget`。
- conversation-end extraction 與重複呼叫不重複建立。
- 非 user／未知 source、一般寒暄與 exact duplicate rejection。
- provider extraction failure 的受控結果。
- relevance recall 只選 active memories 且最多五筆。
- restart 後記憶仍存在。

一般 Ruff、strict mypy 與 pytest 不得呼叫 Groq。
