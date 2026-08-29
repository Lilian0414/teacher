# Teacher — 主動式 AI 英文學習陪伴助手

Teacher 是一個以「長期陪伴、持續學習、低干擾介入」為核心的 AI English Learning Companion。

它不是單純把大型語言模型包成聊天介面，而是把日常對話、Learning Signal、Learning Item、間隔複習、長期記憶與主動練習串成一條可持久化的學習循環。系統的重點是：哪些內容值得留下、什麼時候應該再次出現，以及如何讓學習狀態在多次對話之間保持一致。

目前版本以 **macOS + Textual TUI** 為主要操作環境，核心功能已完成 target-Mac 實機驗收，可作為 v0.1.0 的展示與專題成果基準。

> Teacher 的核心不是「每句話都糾正」，而是只保留高價值學習訊號，並在之後真正帶回來複習與練習。

---

## 核心學習循環

```text
Conversation
    ↓
Learning Signal / Memory
    ↓
Learning Item
    ↓
Review / Practice
    ↓
Learning State Update
    ↓
Proactive Practice
    ↓
Future Conversation
```

一般聊天仍然是主要入口；學習系統在後方維持持久化狀態，而不是要求使用者一直切換到「做題模式」。

---

## 已完成的主要能力

### 一般對話與 Learning Signal

使用者可以直接用英文與 Teacher 對話。每次成功對話完成後，系統會嘗試擷取最多一個高價值 learning signal，例如明顯的時態錯誤、拼字錯誤、可重複使用的片語或其他具體且適合形成複習題的修正。

例如：

```text
I was very tired yesterday, so I sleep early.
```

系統可辨識 `sleep → slept` 這類具體錯誤。Learning Signal 使用 structured extraction，並由 Python 端再次驗證來源片段、修正內容與信心，避免把一般聊天、正確英文、專有名詞或純風格差異大量轉成 learning item。

聊天資料與 learning state 都會持久化到本機 SQLite。

### 即時語言協助

Teacher 提供三種明確的語言協助入口：

```text
/help <內容>   取得自然英文說法、修正或說明
/hint <內容>   取得部分提示，不直接暴露完整答案
/say <中文>    翻譯成自然英文並送入目前對話
```

`/help` 與 `/hint` 可建立去重後的 learning item；`/say` 只負責協助表達，不建立 learning item。

Textual UI 也提供對應的 Help、Hint、Review 操作與 contextual actions，讓使用者不必記住所有指令。

### Learning Item、Review 與間隔複習

```text
/review       開始複習目前到期的 learning item
<answer>      回答目前題目
/review quit  離開複習模式
```

目前排程間隔為：

```text
1 → 3 → 7 → 14 → 30 天
```

答對會推進 stage；答錯會回到 stage 0，隔天再次複習。Review history、stage 與 next review time 都由本機 learning service 持久化管理，不依賴 LLM 自己「記得」。

評分採兩階段設計：

1. deterministic fast path：明確的 normalized exact match、safe contraction 等案例直接判斷；
2. bounded semantic fallback：只有 deterministic path 無法確定時，才使用 goal-aware structured semantic judge。

LLM 不直接修改 stage、attempt 或 next review time。若 semantic judge timeout、rate limit、回應無效或不確定，系統採 deferred outcome，不會把不確定結果默默記成錯誤。

### Spoken Review

複習時可以使用麥克風回答：

```text
Ctrl+M  開始／停止錄音
Ctrl+X  取消本次錄音
```

錄音有 30 秒安全上限。音訊只在記憶體中暫存成短 WAV，由 Core 使用 Groq Whisper (`whisper-large-v3-turbo`) 轉錄；UI 先顯示 transcript，再送進與打字答案相同的 grading path。

麥克風或 STT 失敗時，不會破壞 review state，使用者仍可直接改用鍵盤回答。

### Local Gesture + Camera Review

Review 中可以按 **Gestures** 或 `Ctrl+K` 開啟本機手勢辨識：

```text
Thumb_Down → 顯示既有 hint；不評分、不前進題目
Thumb_Up   → 只在 REVIEW_COMPLETE 狀態完成 review celebration
```

手勢辨識使用 MediaPipe Gesture Recognizer。Camera frame 只在本機處理，不送到 Core、Groq 或其他遠端服務，也不持久化影像。

Textual UI 會顯示同一條 camera capture 的彩色 terminal preview。Preview 為 mirrored display-only view；gesture inference 使用原始 frame。影像處理採 latest-frame-only buffering 與節流，避免建立無界 frame queue。

Camera index 可透過：

```env
COMPANION_GESTURE_CAMERA_INDEX=0
```

明確指定，因此可避免 macOS Continuity Camera 自動選到不希望使用的裝置。

### 長期記憶與跨對話 Recall

Teacher 可以在對話結束後抽取部分長期使用者資訊，存入 SQLite，並在未來對話中只取回少量與目前內容相關的 active memories。

Memory category 包含：

```text
people
personal
school_work
relationships
health_fitness
other
```

Memory 管理指令：

```text
/remember <內容>              明確儲存記憶
/memories [關鍵字]           搜尋 active memories
/forget <memory_id>          預覽刪除
/forget <memory_id> confirm  確認 soft delete
```

除了 lexical / person matching，也可以選擇啟用 OpenAI-compatible embeddings 進行 hybrid semantic recall。若 embedding endpoint 不可用、舊資料沒有向量或 model / dimensions 不相容，系統會安全降級為 lexical / person matching。

Learning data 與 life memory 在資料模型與 prompt context 中分離，避免把「需要學習的內容」誤當成「關於使用者的事實」。

### 主動練習邀請

Teacher 可以在程式運行期間，根據目前狀態主動提出短練習邀請。Core 會考慮：

```text
eligibility
review priority
availability
cooldown
daily limit
目前是否已有 active practice / retry / completion state
```

使用者可以選擇：

```text
Start
Later
Not today
```

接受後會進入受控的 practice flow；practice outcome 可與之後的 learning/review state 串接。系統也會防止 active practice 被其他 mode-changing command 留下 orphaned state。

Proactive Practice 只在 Textual UI 執行期間出現。目前沒有背景 daemon、關閉程式後通知或 OS push notification。

---

## Teacher 與一般 Chatbot 的差異

Teacher 的差異不在於提供更多聊天按鈕，而在於它維持跨時間的 learning state。

**Conversation continuity**：新的對話可以取回少量相關長期記憶，而不是每次從零開始。

**Learning continuity**：一般聊天或語言協助中的高價值訊號可以轉成 learning item，未來重新出現。

**Stateful review**：stage、attempt、next review time 與 review outcome 都持久化管理。

**Selective intervention**：不把每個句子都當成 grammar exercise，只保留具體且值得再次練習的內容。

**Multimodal review input**：語音與簡單手勢是既有 review state machine 的輸入方式，不是另外建立一套獨立 voice/vision agent。

---

## 系統架構

```text
┌──────────────────────────────┐
│          Textual UI          │
│ chat / intents / review      │
│ speech / gesture / preview   │
└──────────────┬───────────────┘
               │ HTTP
               ▼
┌──────────────────────────────┐
│         FastAPI Core         │
│ Conversation                 │
│ Learning / Review            │
│ Memory / Recall              │
│ Proactive Practice           │
│ Preferences / Availability   │
│ Speech boundary              │
└──────────────┬───────────────┘
               │
               ├──► LLM Provider (Groq / Fake)
               ├──► STT (Groq Whisper)
               ├──► Embedding Provider (optional)
               ▼
┌──────────────────────────────┐
│ SQLite + SQLAlchemy + Alembic│
└──────────────────────────────┘

Local-only gesture path:
Camera → MediaPipe Gesture Recognizer → Textual interaction
       └→ ephemeral terminal preview
```

UI 不直接操作資料庫，也不直接決定 grading、review scheduling、memory persistence 或 proactive eligibility。這些 state mutation 都由 Core 擁有。

完整架構說明：[`doc/ARCHITECTURE.md`](doc/ARCHITECTURE.md)

---

## 技術棧

```text
Python 3.12+
FastAPI / Uvicorn
Textual
SQLAlchemy 2.x / Alembic
SQLite
Pydantic v2
Groq LLM
Groq Whisper STT
OpenAI-compatible Embeddings (optional)
MediaPipe + OpenCV (optional gesture path)
pytest / pytest-asyncio
Ruff
mypy strict mode
```

專案刻意不依賴大型 agent framework、LangChain、Mem0 或 vector database。Conversation、Memory、Learning、Review 與 Proactive Practice 都由 repository 內明確的 service / repository boundary 管理。

---

## 安裝與執行

建議使用 Python 3.12：

```bash
python3.12 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
cp .env.example .env
```

在本機 `.env` 填入 `GROQ_API_KEY`，不要把真實 key commit 到 repository。

初始化資料庫：

```bash
alembic upgrade head
```

啟動完整應用：

```bash
companion
```

也可以分開啟動：

```bash
companion-core
```

另一個 terminal：

```bash
companion-ui
```

預設 SQLite：

```text
~/Library/Application Support/ai-learning-companion/companion.sqlite3
```

可用 `COMPANION_DATABASE_URL` 指定其他絕對路徑。

---

## Optional Semantic Memory

若使用 Ollama 提供 OpenAI-compatible embedding endpoint：

```bash
ollama serve
ollama pull nomic-embed-text
```

`.env`：

```env
EMBEDDINGS_ENABLED=true
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768
```

不需要 semantic recall 時：

```env
EMBEDDINGS_ENABLED=false
```

Embedding 關閉或失敗不會讓基本 memory recall 停止運作。

---

## 常用操作

```text
/help <內容>
/hint <內容>
/say <中文>
/review
/review quit
/remember <內容>
/memories [關鍵字]
/forget <id>
/forget <id> confirm
/status
/busy
/dnd
/available
```

UI 同時提供對應按鈕與快捷鍵，不要求使用者只靠 slash command 操作。

---

## 資料與隱私邊界

- 對話、learning state 與 memory 預設保存在本機 SQLite。
- API key 只從環境變數或本機 `.env` 讀取。
- Camera frame 僅供本機 gesture inference / preview，不上傳、不保存。
- Review 錄音只在記憶體暫存，送往設定的 STT provider 後不作本機長期保存。
- Memory delete 採 soft delete，刪除後不再參與一般 recall。
- Provider failure 不會直接冒充成功 assistant message；可恢復流程保留 retry / fallback path。

---

## 驗收與品質

目前 release baseline 已完成 target-Mac 實機驗收，涵蓋：一般聊天與 learning capture、Help/Hint/Review、review scheduling、proactive practice、跨對話 memory recall、`/say` 與 retry、memory extraction failure recovery、UI/Core/DB consistency，以及 speech / gesture / camera fallback。

Repository 的主要自動化 quality gates：

```bash
ruff check .
mypy .
pytest
git diff --check
```

資料庫變更另外使用 Alembic migration round-trip 驗證。

驗收摘要：[`doc/FINAL_UAT.md`](doc/FINAL_UAT.md)

---

## 明確邊界

目前版本**沒有**：

- 關閉程式後仍持續執行的背景 daemon；
- macOS / iOS 系統推播通知；
- 對 camera 畫面做一般物件辨識或場景理解；
- 自動操作瀏覽器、Email、行事曆或其他外部帳號；
- 將所有對話內容上傳到獨立 vector database；
- 讓 LLM 直接改寫 review stage、資料庫或 scheduling policy。

這些都不是 v0.1.0 的既有能力，也不應在展示時被描述為已實作。

---

## 技術文件

- [`doc/PROJECT_OVERVIEW.md`](doc/PROJECT_OVERVIEW.md) — 專題定位、能力與 release 邊界
- [`doc/ARCHITECTURE.md`](doc/ARCHITECTURE.md) — 系統架構、資料流與模組責任
- [`doc/FINAL_UAT.md`](doc/FINAL_UAT.md) — 實機驗收摘要
- [`doc/LEARNER_PREFERENCES.md`](doc/LEARNER_PREFERENCES.md) — learner preferences
- [`openspec/`](openspec/) — 已規格化的系統行為與歷史變更
