# Teacher 專案總覽

## 專案定位

Teacher 是一個以 macOS + Textual TUI 為主要操作環境的主動式 AI 英文學習陪伴系統。專案目標不是做一個「會聊天的英文機器人」，而是建立一個可以跨對話維持 learning state 的完整學習循環。

目前 v0.1.0 release baseline 已完成 target-Mac 實機驗收，功能重點包括：一般英文對話、Learning Signal、Learning Item、間隔複習、長期記憶、主動練習、語音回答與本機手勢互動。

核心循環：

```text
Conversation
→ Learning Signal / Memory
→ Learning Item
→ Review / Practice
→ Learning State Update
→ Proactive Practice
→ Future Conversation
```

---

## Release Capability Matrix

| 能力 | 狀態 | 實作內容 | 邊界 |
|---|---|---|---|
| Text Conversation | 已完成 | 持久化 user / assistant message、Groq provider、fake provider、retry | 無多使用者雲端帳號系統 |
| Learning Signal | 已完成 | 一般英文對話後擷取最多一個高價值 correction / vocabulary signal，含來源證據與去重 | 不做每句即時 grammar interruption |
| Help / Hint / Say | 已完成 | `/help`、`/hint`、`/say` 與 Textual intent actions | `/say` 不建立 learning item |
| Learning Item | 已完成 | correction / vocabulary 等 learning target、來源 occurrence、持久化狀態 | Learning data 與 life memory 分離 |
| Review | 已完成 | due-first review、deterministic grading、bounded semantic fallback、attempt history | LLM 不直接修改 stage / scheduling |
| Spaced Repetition | 已完成 | 1 / 3 / 7 / 14 / 30 天 stage schedule；錯誤回 stage 0 | 固定 policy，不是自適應 ML scheduler |
| Spoken Review | 已完成 | 錄音、Groq Whisper STT、transcript、typed/spoken 共用 grading path | 音訊不持久化 |
| Gesture Review | 已完成 | MediaPipe Thumb_Down hint、Thumb_Up review-complete acknowledgement | 不做自由手勢指令或一般 vision understanding |
| Camera Preview | 已完成 | 本機彩色 terminal preview、camera index 選擇、latest-frame buffering | frame 不送 Core / LLM、不保存 |
| Long-term Memory | 已完成 | 對話結束後抽取、category、search、soft delete、context recall | 不將全部 memory 塞入 prompt |
| Semantic Memory | 可選 | OpenAI-compatible embedding + lexical/person hybrid recall | embedding 失敗可安全 fallback；無 vector DB |
| Proactive Practice | 已完成（程式執行期間） | eligibility、review priority、availability、cooldown、daily limit、Start/Later/Not today、practice lifecycle | 無背景 daemon 或關閉程式後 notification |
| Preferences / Availability | 已完成 | onboarding、availability state、busy/dnd/available/status 等控制 | 不宣稱尚未消費的 preference 會改變 learning policy |
| Persistence | 已完成 | SQLite、SQLAlchemy、Alembic migration | 單機 local-first |
| Quality Gates | 已完成 | Ruff、strict mypy、pytest、migration round-trip、實機 UAT | live provider / hardware 仍需真實環境 |

---

## 主要使用流程

### 1. 一般聊天 → Learning Signal → 未來 Review

使用者直接與 Teacher 進行英文對話。成功取得 assistant reply 後，系統在不打斷聊天的情況下檢查是否存在一個高價值 learning signal。

若 signal 通過來源、信心與內容驗證，系統建立或合併 learning item，保存 occurrence provenance，之後由 `/review` 或 proactive practice 帶回。

### 2. Help / Hint → Learning Item

使用者可以在不知道怎麼說、想確認句型或需要提示時呼叫 Help / Hint。這類顯式 assistance 可建立 learning item，讓當下得到的協助不只停留在一次回答。

### 3. Review → Learning State Update

Review 只處理目前到期的 learning item。明確案例先由 deterministic grading 判斷；語意等價但字面不同的答案才進 bounded semantic fallback。

最終 stage mutation、attempt persistence 與 next review time 都由 Python learning service 處理。

### 4. Conversation End → Memory Extraction → Future Recall

對話結束後，Memory Service 嘗試抽取可長期使用的使用者資訊。未來聊天只會取回少量與當前內容相關的 active memories。

Semantic embedding 是 optional enhancement，不是基本 memory path 的必要條件。

### 5. Proactive Invitation → Practice → Outcome

當系統判斷目前適合練習時，Textual UI 可以顯示邀請。接受後 practice lifecycle 會維持單一 active state，完成、略過或中止都會留下明確 terminal state，避免 orphaned invitation。

### 6. Speech / Gesture 作為 Review Input

Speech 與 Gesture 不建立新的 learning engine，而是接到既有 review state machine：

```text
Speech → STT transcript → canonical review grading
Gesture → existing hint / review-complete action
```

因此不同輸入方式共用同一套 learning state 與 correctness policy。

---

## 系統設計原則

### Core owns state

Textual UI 負責互動、顯示、錄音狀態、手勢狀態與 camera preview；所有 grading、scheduling、memory persistence、conversation persistence、availability 與 proactive lifecycle 都由 FastAPI Core 管理。

### Evidence-first learning

Learning Signal 不只依賴「模型覺得這句有錯」，還要求來源 evidence、修正內容與可接受的 confidence / policy，降低把 style preference 或 harmless informal English 變成 learning item 的機率。

### Local-first persistence

主要狀態保存在 SQLite。LLM 是生成與判讀 provider，不是資料庫，也不是 learning state 的唯一來源。

### Graceful degradation

Embedding、camera、microphone、STT 或 provider 出現問題時，系統保留可行 fallback：lexical memory、typed review、一般 command / conversation path 等，不應因 optional capability 失敗讓整個 learning loop 無法使用。

### Explicit multimodal boundary

Camera 只做本機 gesture recognition 與 preview；Speech 只作為 review answer 的輸入方式。兩者都不被描述為通用 vision / voice agent。

---

## 資料模型概念

主要持久化資料可分為：

```text
Conversation / Message
LearningItem / LearningOccurrence / LearningAttempt
Memory
ProactiveInvitation
Availability / Preferences related state
```

Learning Item 與 Memory 刻意分開：

- Learning Item：使用者「需要再練習」的內容。
- Memory：系統「之後可能需要知道」的使用者資訊。

這個區分可避免把錯誤句型、複習答案或教學內容誤當成個人事實。

---

## v0.1.0 實機驗收狀態

Release baseline 以 target-Mac 實機操作完成為狀態基準，已涵蓋：

```text
ordinary chat + learning capture
help / hint / review flow
correct / incorrect / deferred grading
review scheduling and persistence
spoken review and typed fallback
gesture / camera local interaction
proactive invitation lifecycle
cross-conversation memory recall
/say and assistant retry
memory extraction failure recovery
UI / Core / database consistency
restart / persistence behavior
```

驗收摘要見 [`FINAL_UAT.md`](FINAL_UAT.md)。

---

## 明確未包含於目前版本的能力

為避免展示或文件過度宣稱，v0.1.0 不包含：

- 關閉應用後仍常駐的 background daemon；
- macOS / iOS push notification；
- 通用 camera object detection、OCR 或場景理解；
- 自動瀏覽網頁、寄 Email、操作行事曆等 external-agent actions；
- 多使用者 SaaS 帳號、雲端同步或跨裝置同步；
- vector database；
- 由 LLM 直接修改資料庫、review stage 或 scheduling policy。

---

## 相關文件

- [`../README.md`](../README.md)：使用者與展示入口
- [`ARCHITECTURE.md`](ARCHITECTURE.md)：技術架構與資料流
- [`FINAL_UAT.md`](FINAL_UAT.md)：release acceptance record
- [`LEARNER_PREFERENCES.md`](LEARNER_PREFERENCES.md)：偏好設定
- [`../openspec/`](../openspec/)：系統規格與變更記錄
