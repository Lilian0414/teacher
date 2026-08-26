# M2：精簡版長期記憶

## 已完成範圍

M2 讓 Core 保存、搜尋、軟刪除與 recall 使用者長期記憶，並在 conversation
結束時抽取值得保留的 user facts。資料保存於 SQLite；在有配置 embedding provider
時使用混合語意檢索，未配置或 provider 暫時失敗時則保留原本的詞彙檢索行為。

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

## Hybrid recall

`MemoryContextBuilder` 在最多 200 筆近期 active memories 的 bounded candidate set 上，
組合以下 deterministic signals：

- 人物 canonical name／alias 命中。
- 英文詞彙重疊與中文 bigram 重疊。
- embedding cosine similarity（只有相似度達最低門檻時才計分）。

混合分數排序後，每次一般聊天仍最多注入五筆記憶。人物與詞彙訊號保留原有權重，
語意訊號讓「remembering new vocabulary」與「forgetting new words」這類低字面重疊
的改寫仍能被召回。deleted memories 在 candidate query 階段即被排除。

`EmbeddingProvider` 是非同步且支援 batch 的 provider-neutral protocol。Memory write／update
會先非同步產生向量再保存；conversation-end extraction 會以單一 batch 處理多筆有效
candidates。query 只產生一次向量，並只對已保存且 model 與 dimensions 完全相容的向量
rerank；recall 不寫 DB、不 commit，也不在 query path lazy backfill。一般測試使用
deterministic async fake provider，不呼叫外部 API。

未配置 provider、provider 丟出例外、回傳空值／非有限數值，或既有 memory 尚未有
embedding 時，都會安全降級成既有 lexical/person recall；普通聊天與記憶保存不會因
embedding failure 中斷。內容更新但新 embedding 失敗時會清除舊向量，避免 stale vector。

## 資料模型與遷移

- `people`：canonical name、aliases、relationship 與 timestamps。
- `memories`：category、content、nullable JSON embedding、optional person、source
  conversation、confidence、status 與 timestamps。

基礎 memory migration 位於
`migrations/versions/20260719_0003_create_long_term_memory.py`；nullable embedding 欄位由
`migrations/versions/20260822_0006_add_memory_embeddings.py` 加入，因此既有 SQLite DB
可以直接 `alembic upgrade head`，不需要資料庫重建。既有 rows 不做昂貴 backfill，
在重新寫入前繼續使用 lexical/person signals。

目前 SQLite 以 JSON 儲存向量並在 bounded candidates 內計算 cosine similarity，適合本
機里程碑但不是大型 vector index。未來遷移 PostgreSQL + pgvector 時，可在
`MemoryRepository`／`EmbeddingProvider` boundary 後替換 persistence 與 nearest-neighbor
search，不需重寫 `MemoryService` 或 prompt builder。

## 尚未實作

Private conversations、sensitivity、candidate approval、audit history、conflict／superseded
states、記憶編輯、proactive-use permissions、`/memory` 管理入口及獨立 memory CRUD
API 都不屬於目前 M2。這些功能必須透過未來 OpenSpec change 才能加入。

## 驗證重點

- `/remember`、`/memories` 與 confirmed `/forget`。
- conversation-end extraction 與重複呼叫不重複建立。
- 非 user／未知 source、一般寒暄與 exact duplicate rejection。
- provider extraction failure 的受控結果。
- semantic paraphrase、lexical/person hybrid ranking、deleted exclusion 與 Top 5 bound。
- embedding write/query failure 的 lexical fallback。
- SQLite embedding persistence 與 Alembic upgrade/downgrade。
- restart 後記憶仍存在。

一般 Ruff、strict mypy 與 pytest 不得呼叫 Groq 或任何外部 embedding API。
