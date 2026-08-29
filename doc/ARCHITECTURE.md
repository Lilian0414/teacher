# Teacher 系統架構

## 架構目標

Teacher 採分層式、local-first 架構。Textual UI 負責使用者互動與本機感知；FastAPI Core 統一管理 Conversation、Learning / Review、Memory、Proactive Practice、Preferences、Availability 與 Speech boundary；SQLite 保存持久化狀態。

最重要的設計原則是：**UI 不直接修改資料庫，也不直接擁有 learning policy。** 所有 grading、scheduling、persistence、retry evidence 與 lifecycle mutation 都由 Core 擁有。

---

## 技術棧

| 用途 | 技術 |
|---|---|
| Runtime | Python 3.12+ |
| API / Core | FastAPI、Uvicorn |
| Terminal UI | Textual |
| ORM / Persistence | SQLAlchemy 2.x、SQLite |
| Migration | Alembic |
| Schema / Settings | Pydantic v2、Pydantic Settings |
| LLM | Groq production provider、Fake test providers |
| Speech-to-Text | Groq Whisper (`whisper-large-v3-turbo`) |
| Embedding | OpenAI-compatible endpoint（optional） |
| Gesture | MediaPipe Gesture Recognizer |
| Camera | OpenCV |
| Tests | pytest、pytest-asyncio |
| Static quality | Ruff、strict mypy |

目前不依賴 LangChain、Mem0、Letta、vector database 或大型 agent framework。核心 learning loop 與 state mutation 都由 repository 內明確的 service / repository 邊界實作。

---

## 高階元件

```text
┌─────────────────────────────────┐
│           Textual UI            │
│                                 │
│ Chat / Commands / Intents       │
│ Review panel                    │
│ Recording state                 │
│ Gesture state                   │
│ Local camera preview            │
└───────────────┬─────────────────┘
                │ HTTP
                ▼
┌─────────────────────────────────┐
│          FastAPI Core           │
│                                 │
│ Conversation Service            │
│ Learning / Review Service       │
│ Memory Service / Context        │
│ Proactive Service               │
│ Preferences / Availability      │
│ Speech Transcription Boundary   │
│ Provider Interfaces             │
└───────────────┬─────────────────┘
                │
      ┌─────────┼─────────────┐
      │         │             │
      ▼         ▼             ▼
    Groq     Embedding      SQLite
    LLM/STT   Provider   SQLAlchemy/Alembic

Local-only path:
Camera → MediaPipe → Gesture Intent → Textual Review Interaction
       └──────────→ ephemeral terminal preview
```

---

## UI Layer

`src/terminal_ui/` 是使用者主要操作面。它負責：

- 顯示一般聊天、系統狀態與 review panel；
- Help / Hint / Review 等 intent flow；
- 錄音開始、停止、取消與 transcript 顯示；
- gesture enable / disable、camera preview 與 gesture acknowledgement；
- proactive invitation card 與 Start / Later / Not today；
- 保留輸入 focus、按鈕與 shortcut interaction；
- 將使用者操作轉成 HTTP request。

UI 不應直接：

- 寫入 SQLite；
- 修改 learning item stage；
- 計算 next review time；
- 決定 memory 是否永久保存；
- 直接呼叫 Groq 做 conversation / grading；
- 自行建立 proactive eligibility policy。

這些責任都在 Core。

---

## FastAPI Core

### Conversation

Conversation Service 管理 conversation lifecycle、user / assistant message persistence、assistant retry 與 conversation end。

一般流程：

```text
User input
→ persist user message
→ call LLM provider
→ persist assistant message
→ return result
→ post-process learning signal
```

若 assistant 生成失敗，但 user message 已成功保存，系統保留 retry evidence，使後續 retry 不需要再次插入 user message。

### Learning / Review

Learning Service 擁有：

- learning item 建立與去重；
- occurrence provenance；
- due item selection；
- deterministic grading；
- bounded semantic grading fallback；
- attempt persistence；
- stage transition；
- next review scheduling。

Review 的 canonical grading path：

```text
Typed answer / STT transcript
        ↓
Input policy
        ↓
Deterministic grading
        ↓ uncertain only
Semantic structured judge
        ↓
Learning Service state mutation
```

LLM 只能回傳 structured semantic decision，不能直接寫 stage 或 next review time。

目前 spaced-repetition interval：

```text
1 → 3 → 7 → 14 → 30 days
```

錯誤答案回到 stage 0，隔天再複習；uncertain / provider failure 使用 deferred outcome，避免不可靠判斷污染 learning state。

### Learning Signal

成功的一般英文對話可觸發 learning-signal extraction。Extraction 使用 structured response，並由 Python 驗證：

```text
source evidence
candidate correction / expression
confidence / acceptance rule
deduplication
```

系統最多接受一個高價值 signal，以降低噪音與過度糾正。

### Memory

Memory Service 在 conversation end 後處理可長期保存的使用者資訊。

Memory path：

```text
Ended conversation
→ candidate extraction
→ validation / categorization
→ persistence
→ optional embedding
→ future recall
```

一般 recall 只取回少量與當前 query 相關的 active memories。若 semantic embedding 未啟用或失敗，系統回退到 lexical / person matching。

Memory 與 Learning Item 使用不同資料模型與 prompt section，避免把教學內容誤當成使用者事實。

### Proactive Practice

Proactive Service 管理：

- eligibility；
- review priority；
- availability；
- cooldown；
- daily limit；
- invitation persistence；
- accept / snooze / dismiss；
- active practice lifecycle；
- completion / abandon / restart reconciliation。

UI 只負責「現在是否適合把 invitation 顯示出來」等 transient presentability；真正的 invitation status 與 lifecycle persistence 在 Core。

Active practice 存在時，會阻止不安全的 mode-changing command 讓 practice state 變成 orphaned。

### Preferences / Availability

Preferences Service 保存 learner-facing configuration；Availability Service 管理 `busy`、`dnd`、`available` 等 runtime state。

文件只宣稱目前確實被 runtime 消費的設定。尚未接入行為 policy 的 preference 不應被描述成已影響 learning scheduler 或 proactive strategy。

### Speech Boundary

UI 錄音後送出短 WAV，Core 透過 SpeechTranscriber 呼叫 Groq Whisper，再回傳 transcript。

Speech 只是一個 input boundary；transcript 回到既有 review path，因此 typed / spoken answer 共用同一套 correctness 與 state mutation。

---

## Provider Layer

LLM provider interface 將外部模型與 domain logic 分開。

目前：

```text
Groq provider     → production / live use
Fake providers    → deterministic tests / failure-path tests
Embedding endpoint→ optional semantic memory
```

Provider error 必須轉成受控錯誤或 retryable outcome，不應冒充成功 assistant response。

Learning policy 不依賴 provider-specific response text；需要 machine decision 的地方使用 structured schema。

---

## Persistence Layer

主要資料庫為 SQLite，透過 SQLAlchemy repository 與 Alembic migration 管理。

核心持久化概念：

```text
Conversation
Message
LearningItem
LearningOccurrence
LearningAttempt
Memory
ProactiveInvitation
Preferences / related state
```

資料庫是 learning state 的 source of truth；LLM context 只是根據當下需求組裝出的有限視圖。

---

## Camera / Gesture Boundary

Camera path 完全在 UI process 本機執行：

```text
OpenCV capture
→ latest-frame buffer
→ MediaPipe inference
→ GestureIntent
→ existing Review action
```

同一 capture 可產生 mirrored terminal preview，但 preview 僅供顯示。

目前 gesture semantics：

```text
Thumb_Down → read-only hint
Thumb_Up   → REVIEW_COMPLETE acknowledgement
```

Camera frame 不送 Core、不送 Groq、不持久化。這個功能不是一般物件辨識或場景理解。

---

## Failure / Recovery 設計

Teacher 對 optional provider 或硬體失敗採 graceful degradation：

- LLM reply 失敗：保存 user message，提供 idempotent assistant retry；
- Memory extraction 失敗：conversation 可正常結束，依 retryability 保留後續 recovery；
- Semantic grading 不確定：defer，不修改 learning state；
- Embedding 失敗：fallback lexical / person recall；
- Microphone / STT 失敗：保留 typed review；
- Camera / gesture 不可用：保留 keyboard / button interaction；
- proactive practice interrupted：以 durable state reconciliation，避免 orphaned accepted invitation。

---

## Repository 結構

```text
teacher/
├── README.md
├── AGENTS.md
├── doc/
│   ├── PROJECT_OVERVIEW.md
│   ├── ARCHITECTURE.md
│   ├── FINAL_UAT.md
│   ├── LEARNER_PREFERENCES.md
│   └── M0_...M4_*.md
├── openspec/
├── migrations/
├── src/
│   ├── companion/
│   │   ├── api/
│   │   ├── commands/
│   │   ├── conversation/
│   │   ├── learning/
│   │   ├── memory/
│   │   ├── proactive/
│   │   ├── providers/
│   │   ├── persistence/
│   │   └── settings.py
│   └── terminal_ui/
└── tests/
    ├── unit/
    ├── integration/
    └── live/
```

---

## 品質與安全規則

1. API key 只從環境變數或本機 `.env` 讀取。
2. `.env`、SQLite、對話內容、記憶、音訊與 camera frame 不提交 Git。
3. UI 不越過 Core 直接修改 persistence。
4. LLM 不直接決定或寫入 durable learning state。
5. 所有 migration 以 Alembic 管理。
6. Repository quality gates 為 Ruff、strict mypy、pytest、`git diff --check`；涉及 schema 時加 migration round-trip。
7. Hardware / live-provider acceptance 以 target-Mac UAT 驗證，不用單元測試假裝替代。

---

## Current Release Boundary

目前 v0.1.0 已完成並驗收的範圍是：local-first AI English Learning Companion、Textual UI、persistent learning loop、memory、review、proactive practice、speech review、local gesture/camera interaction。

目前不是：background OS agent、通用 vision system、多使用者 cloud SaaS、外部工具自動化平台或 autonomous browser agent。
