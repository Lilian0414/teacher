# Teacher v0.1.0 — Target-Mac Acceptance Record

## Release status

**Overall result: PASS**

本文件記錄 Teacher v0.1.0 release baseline 的 target-Mac 實機驗收結果。驗收目的不是重複單元測試，而是確認真實 macOS、Textual UI、SQLite persistence、Groq provider、Speech-to-Text、camera / gesture 與多輪操作流程能一起工作。

Raw local logs、API key、私人對話與 memory 內容不提交 repository；本文件只保留可公開的驗收結論與行為摘要。

---

## Acceptance baseline

驗收範圍：

```text
macOS target machine
Python 3.12 environment
Textual UI + FastAPI Core
SQLite + Alembic
Groq LLM
Groq Whisper STT
optional OpenAI-compatible embedding path
local OpenCV / MediaPipe gesture path
```

Release 判定要求：

- 使用者操作能完成，而不是只有 API 或 unit test 通過；
- UI、Core response 與 SQLite durable state 一致；
- retry / failure path 不重複寫入或污染 learning state；
- optional capability 失敗時仍有可用 fallback；
- camera 與 audio 行為符合既定 privacy boundary。

---

## 1. Ordinary Chat + Learning Signal

**Result: PASS**

實機確認一般英文對話可正常建立 conversation、保存 user / assistant message 並顯示回覆。

在存在明確、高信心 correction 的情況下，conversation post-processing 可形成 learning signal / learning item；正確英文、一般 chitchat 與不值得複習的內容不會被無限制轉成 learning item。

確認項目：

```text
conversation persisted
user message persisted once
assistant message persisted once
high-value signal can be captured
source provenance remains linked
normal chat remains usable after capture
```

---

## 2. Help / Hint / Review Flow

**Result: PASS**

實機確認 Help、Hint 與 Review 可以形成完整 learning flow。

`/help` 能提供自然英文或修正，`/hint` 只提供部分提示；由 assistance 建立的 learning item 可以在之後進入 `/review`。

Review 在提交前不暴露完整 accepted answer，並能正確進入下一題或完成狀態。

---

## 3. Review Grading + Scheduling

**Result: PASS**

實機確認 typed answer 能經 canonical grading path 判定，並正確更新 durable learning state。

驗收包含：

```text
normalized correct answer
incorrect answer
semantic-equivalent answer
uncertain / deferred outcome
review quit and resume
```

Scheduling behavior 符合目前 policy：

```text
correct → stage advances through 1 / 3 / 7 / 14 / 30 day intervals
incorrect → stage 0 + next-day review
uncertain/deferred → no silent incorrect mutation
```

Stage、attempt history 與 next review time 在 restart 後仍保持一致。

---

## 4. Spoken Review

**Result: PASS**

實機確認 review 中可以使用麥克風回答。

流程：

```text
start recording
→ stop recording
→ STT transcript
→ show transcript
→ canonical review grading
```

同時確認：

- 30 秒安全上限有效；
- cancel 不送出 review answer；
- STT / microphone failure 不修改 review state；
- typed fallback 仍可繼續完成同一題；
- spoken 與 typed answer 共用相同 grading / scheduling policy。

---

## 5. Local Gesture + Camera Preview

**Result: PASS**

實機確認本機 camera、MediaPipe gesture recognition 與 Textual preview 可以在 review flow 中正常使用。

目前 gesture semantics：

```text
Thumb_Down → 顯示 read-only hint，不 grading、不前進
Thumb_Up   → 僅在 REVIEW_COMPLETE 完成 review acknowledgement
```

同時確認：

- camera preview 可正常顯示；
- camera index 可明確指定；
- gesture 不會取代 keyboard / button fallback；
- frame 只在本機 process 中使用，不送 Core / Groq；
- frame 不持久化；
- disable / leave review 後 gesture state 可正常清理。

---

## 6. Proactive Practice End-to-End

**Result: PASS**

實機確認符合 eligibility 時，Textual UI 可以收到並呈現 proactive practice invitation。

操作結果：

```text
Start     → 進入 active practice
Later     → snooze
Not today → dismiss for current policy window
```

Active practice 期間不會被一般 mode-changing slash command 留下 orphaned invitation；completion、abandon 與 restart reconciliation 均能回到明確 terminal state。

Review priority、availability、cooldown 與 daily limit 仍由 Core 控制。

---

## 7. Cross-Conversation Memory Recall

**Result: PASS**

實機確認 conversation A 結束後可抽取 durable memory，conversation B 能在相關情境中取回少量記憶作為 context。

驗收包含：

```text
memory extraction after conversation end
new-conversation recall
unrelated-query false-positive check
soft delete exclusion
restart persistence
```

啟用 embedding 時，semantic recall 可與 lexical / person matching 混合使用；embedding provider 不可用時可安全退回基本 recall path。

Learning Item 與 life memory 在 prompt 與 persistence 中維持分離。

---

## 8. `/say` + Assistant Retry

**Result: PASS**

實機確認 `/say` 先產生英文表達並插入 conversation，但不建立 learning item。

針對一般 chat、`/say` 與 proactive practice 的 assistant failure，retry path 均可在不重複 user message 的情況下補上 assistant response。

Repeated retry 不會新增重複 user turn，也不會破壞 conversation / practice linkage。

---

## 9. Memory Extraction Failure + Quit Recovery

**Result: PASS**

實機確認 conversation 已成功保存時，即使 memory extraction 因 provider configuration 或 temporary provider failure 未完成，使用者仍可正常退出應用。

Failure 會被呈現為 recovery / provider error，而不是成功訊息。

後續 provider 恢復時可重新處理未完成 extraction，且不應重複產生相同 durable memory。

---

## 10. UI / Core / SQLite Consistency

**Result: PASS**

實機確認 Textual UI 顯示的主要 durable state 與 Core / SQLite 一致，包括：

```text
conversation lifecycle
review due state
learning stage / attempts
availability
proactive invitation lifecycle
memory persistence
retry evidence
```

應用 restart 後，durable state 可由 Core / repository 重建；camera preview、gesture transient state、input focus 等 UI-only state 不被錯誤當成需要持久化的資料。

---

## Failure / Fallback Acceptance

**Result: PASS**

以下 fallback 均符合預期：

| Failure | Expected fallback | Result |
|---|---|---|
| LLM assistant reply failure | user message 保留，可 retry assistant | PASS |
| Semantic grading unavailable | deferred，不污染 stage | PASS |
| Memory extraction failure | conversation 可結束，後續 recovery | PASS |
| Embedding unavailable | lexical / person recall | PASS |
| Microphone / STT unavailable | typed review | PASS |
| Camera / gesture unavailable | keyboard / button review | PASS |
| Interrupted proactive practice | durable reconcile / terminal state | PASS |

---

## Privacy Boundary Acceptance

**Result: PASS**

確認目前 release 行為符合：

- API key 不寫入 repository；
- SQLite / private runtime data 不 commit；
- camera frame 不上傳、不保存；
- review audio 不作本機長期保存；
- optional embedding 不等於將整個對話資料庫上傳；
- LLM 不直接取得資料庫寫入權限；
- UI 不直接修改 durable learning state。

---

## Release Sign-off

Teacher v0.1.0 的 release baseline 可視為已完成 target-Mac 功能驗收。

目前可對外展示與描述的功能包括：

```text
persistent English conversation
learning-signal capture
help / hint / say
learning items + spaced review
semantic grading fallback
spoken review
local gesture + camera preview
long-term memory + optional semantic recall
proactive practice invitation
retry / recovery paths
SQLite persistence and restart continuity
```

不應宣稱為本次 release 能力的項目包括：background daemon、OS push notification、通用 camera scene understanding、多使用者 cloud sync、自動瀏覽器 / Email / Calendar 操作，以及任何未接入 runtime 的規劃中功能。
