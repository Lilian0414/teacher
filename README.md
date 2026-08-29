# Teacher — 主動式 AI 英文學習陪伴助手

Teacher 是一個以「長期陪伴與持續學習」為核心的 AI English Learning Companion。

它不只回答當下的問題，而是嘗試把日常對話中的學習訊號、語言協助、長期記憶、間隔複習與主動練習串成一個可以跨時間持續運作的學習循環。

目前專案以 **macOS + Textual TUI** 為主要使用方式，核心功能已進入 **v0.1.0 release candidate** 階段；目前正在做最後一輪使用者驗收，而不是繼續擴張新功能。

> 核心問題不是「AI 能不能回答英文問題」，而是：AI 能不能知道哪些內容值得留下、之後重新帶回來練習，並且在長期互動中維持一致的 learning state。

---

## 核心學習循環

```text
Conversation
    ↓
Learning signal / Memory
    ↓
Learning item
    ↓
Future retrieval
    ↓
Review / Practice
    ↓
Learning state update
    ↓
Proactive practice
    ↓
Future conversation
```

Teacher 想把「問過一次」變成「之後真的還會繼續學」。

---

## 一個實際流程

使用者可以直接聊天，也可以明確請求語言協助：

```text
/help 我昨天太累所以很早就睡了
```

Teacher 會提供自然的英文說法，並在適合時建立 learning item。

一般英文對話本身也會經過 learning-signal extraction。例如：

```text
I was very tired yesterday, so I sleep early.
```

系統會嘗試辨識高信心、具體而值得複習的錯誤，例如 `sleep → slept`。learning signal 使用 evidence-first 的 structured extraction，並由 Python 端再次驗證來源片段、修正內容與信心；即使模型已看見明顯修正但沒有產生 candidate，系統也能從合法的高信心 correction evidence 建立一個最小 learning item。

之後使用者可以執行：

```text
/review
```

Teacher 會依到期順序出題，回答後更新 stage 與下一次複習時間。

目前的間隔為：

```text
1 → 3 → 7 → 14 → 30 天
```

回答錯誤則回到 stage 0，安排隔天再次複習。

---

## 目前已完成的能力

### 1. 一般對話

- 持久化文字對話。
- 可替換的 LLM provider interface。
- 正式環境目前使用 Groq；測試使用 fake provider。
- 對話資料儲存在本機 SQLite。
- 一般聊天仍是主要互動面，不會把每個錯誤都變成打斷式 grammar checker。

### 2. Learning signal

一般英文對話完成後，Teacher 可以擷取最多一個高價值 learning signal。

目前特別處理：

- 明顯 verb tense error。
- 明顯 spelling error。
- 其他高信心、具體且可形成獨立複習題的 correction。
- vocabulary / useful expression 類 learning point。

為降低噪音，correct English、一般 chitchat、harmless informal English、proper names、brands、URLs 與偏風格性的修改不應被大量記錄。

learning-signal extraction 使用 deterministic structured request (`temperature=0`)；一般聊天本身仍保留較自然的生成設定。

### 3. 即時語言協助

```text
/help <內容>   解釋英文，或把中文／混合輸入轉成自然英文
/hint <內容>   提供部分提示，不直接把完整答案交出來
/say <中文>    翻譯一句話並作為這次對話中的使用者訊息送出
```

`/help` 與 `/hint` 可以建立去重後的 learning item；`/say` 不建立 learning item。

Textual UI 也提供對應的 Help / Hint / Review 操作與 contextual actions。

### 4. Learning item 與間隔複習

```text
/review       開始複習目前到期的 learning item
<answer>      回答目前題目
/review quit  離開複習模式
```

Review 使用兩階段 grading：

1. **deterministic fast path**：normalized exact match、safe contraction 等明確案例直接判斷，不呼叫額外模型。
2. **bounded semantic fallback**：只有 deterministic path 無法確定時，才使用 goal-aware structured semantic judge 判斷自然但等價的回答。

LLM 不直接修改 stage、next review time 或 attempts。最終 learning-state mutation 仍由 Python learning service 負責。

如果 semantic judge 回傳 uncertain、timeout、rate limit 或無效回應，Teacher 會採保守的 deferred outcome，而不是把答案默默記成錯誤並改動學習狀態。

Typed answer 與 spoken transcript 共用同一條 canonical grading path。

### 5. Spoken review

在 review 畫面可以按 **Speak answer** 或 `Ctrl+M` 開始錄音：

- 第一次 `Ctrl+M`：開始錄音。
- 第二次 `Ctrl+M`：停止並送出一次。
- `Ctrl+X`：取消錄音，不送 STT、不修改 review state。
- 安全上限為 30 秒，到達上限會自動停止並送出。

音訊只在記憶體中暫存成短 WAV，交由 Core 使用現有 Groq 設定與 `whisper-large-v3-turbo` 轉錄。UI 會先顯示 transcript，再走和打字答案相同的 review grading path。

麥克風或 STT 失敗時，打字複習仍可繼續。

### 6. Local gesture + camera review

Review 中可按 **Gestures** 或 `Ctrl+K` 開啟本機手勢：

- **Thumb_Down** → 顯示既有 read-only hint，不評分、不前進題目。
- **Thumb_Up** → 只在 `REVIEW_COMPLETE` 狀態完成／關閉 review celebration。

手勢辨識使用 MediaPipe Gesture Recognizer，本機 camera frame 不送到 Core、Groq 或其他遠端服務。

Textual UI 會顯示同一條 camera capture 的彩色 terminal preview；preview 是 mirrored display-only view，gesture inference 使用原始 frame。系統採 latest-frame-only buffering 與節流，不建立無界 frame queue。

Camera index 可透過 `.env` 的 `COMPANION_GESTURE_CAMERA_INDEX` 明確設定，因此不需要為了避免 Continuity Camera 而全域停用 iPhone camera integration。

### 7. 長期記憶

Teacher 可以從已完成的對話中擷取部分使用者資訊並存入 SQLite。

目前 memory category 包含：

- `people`
- `personal`
- `school_work`
- `relationships`
- `health_fitness`
- `other`

一般聊天最多取回少量與目前內容相關的 active memories，而不是把整個 memory database 全部塞進 prompt。

除了 lexical / person matching，也可以選擇啟用 OpenAI-compatible embeddings，進行 hybrid semantic recall。若 embedding provider 不可用、舊資料沒有向量，或 model / dimensions 不相容，系統會退回 lexical / person matching。

### 8. Memory 管理

```text
/remember <內容>              明確儲存一筆記憶
/memories [關鍵字]           列出或搜尋 active memories
/forget <memory_id>          預覽要刪除的記憶
/forget <memory_id> confirm  確認 soft delete
```

刪除採 soft delete，不再參與一般 recall，但資料仍保留於 SQLite。

### 9. Learning context 回到一般對話

除了 life memory，Teacher 也可以把少量到期的 learning goals 放回一般聊天 context。

Learning data 與 life memory 在資料模型與提示中分離，避免把「我要學的內容」誤當成「關於我的事實」。

### 10. 主動練習邀請

Teacher 已完成程式運行期間的 proactive practice invitation。

Core 會依 eligibility、cooldown、daily limit、availability 與 review 狀態決定是否適合邀請。使用者可以選擇：

- Start
- Later
- Not today

目前 proactive practice 只在 Textual UI 正在執行時出現；沒有背景 daemon，也不會在程式關閉後送系統通知。

---

## Teacher 與一般 Chatbot 的差異

Teacher 的重點不是加入更多聊天功能，而是維持一個跨時間的 learning state。

**Conversation continuity**  
新的對話不一定從零開始；系統可以取回與目前情境相關的長期資訊。

**Learning continuity**  
語言協助與一般聊天中的學習訊號可以轉成 learning item，並在未來重新出現。

**Stateful learning**  
stage、review history 與 next review time 是持久化狀態，不依賴 LLM 自己「記得」。

**Selective intervention**  
Teacher 盡量只留下高價值學習訊號，並在適合的時機邀請練習，而不是每句都糾正。

**Lightweight multimodal interaction**  
Speech-to-text 與簡單 gesture 是 review interaction 的輸入方式，不是獨立的 heavyweight vision / voice agent。

---

## 系統架構

```text
┌────────────────────────┐
│       Textual UI       │
│ chat / review / speech │
│ gesture + preview      │
└───────────┬────────────┘
            │ HTTP
            ▼
┌────────────────────────┐
│      FastAPI Core      │
│                        │
│ Conversation           │
│ Learning / Review      │
│ Memory                 │
│ Proactive Practice     │
└───────────┬────────────┘
            │
            ├──────────► LLM Provider (Groq / Fake)
            ├──────────► STT (Groq Whisper)
            ├──────────► Embedding Provider (optional)
            ▼
┌────────────────────────┐
│ SQLite + SQLAlchemy    │
│       + Alembic        │
└────────────────────────┘

Local-only gesture path:
Camera → MediaPipe Gesture Recognizer → Textual interaction
       └→ ephemeral mirrored preview
```

UI 不直接操作資料庫；learning state、availability、review scheduling 與 persistence policy 由 Core 擁有。

主要技術：

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- SQLite
- Textual
- Groq / OpenAI-compatible LLM interface
- Groq Whisper STT
- OpenAI-compatible embeddings（optional）
- MediaPipe + OpenCV（optional gestures）
- pytest
- Ruff
- mypy strict mode

完整 capability matrix 可參考 [`doc/PROJECT_OVERVIEW.md`](doc/PROJECT_OVERVIEW.md)。

---

## 安裝與執行（Apple Silicon）

需要 Python 3.12 或以上。

```bash
python3.12 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .

cp .env.example .env
```

在 `.env` 中填入自己的 `GROQ_API_KEY`，不要把真實 key commit 到 repository。

初始化／更新資料庫：

```bash
alembic upgrade head
```

啟動 Teacher：

```bash
companion
```

`companion` 會一起啟動 Core 與 Textual UI。

開發時也可以分開啟動：

```bash
companion-core
```

另一個 terminal：

```bash
companion-ui
```

在 Textual UI 中，即使輸入框保持 focus，也可用 `Page Up` / `Page Down` 瀏覽對話，並用
`End` 跳回最新訊息；支援的 terminal 也可使用滑鼠或 trackpad 捲動。Textual 無法改變 terminal
emulator 的實體字體大小；需要放大時，macOS Terminal 或 iTerm2 可用 `⌘+` / `⌘-`（`⌘0`
回到預設大小）。

預設 SQLite database：

```text
~/Library/Application Support/ai-learning-companion/companion.sqlite3
```

可用 `COMPANION_DATABASE_URL` 指定其他絕對路徑。

---

## Semantic memory（optional）

`.env.example` 提供 OpenAI-compatible embedding 設定。若使用 Ollama：

```bash
ollama serve
ollama pull nomic-embed-text
```

常用設定：

```env
EMBEDDINGS_ENABLED=true
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768
```

如果不需要 semantic recall：

```env
EMBEDDINGS_ENABLED=false
```

此時 memory recall 會使用 lexical / person matching。

---

## Optional local gestures（macOS）

安裝 gesture extra：

```bash
python -m pip install -e ".[gestures]"
```

下載相容的 MediaPipe Gesture Recognizer task model，並在 `.env` 設定：

```env
COMPANION_GESTURE_MODEL=/absolute/path/to/gesture_recognizer.task
COMPANION_GESTURE_CAMERA_INDEX=0
```

如果 Continuity Camera 佔用了 index，可把 camera index 改成實際測試可用的 AVFoundation index，例如 `1`。

第一次使用時請允許 Terminal／使用中的終端程式存取 camera。

Core 與 gesture native runtime 的診斷預設寫入：

```text
~/Library/Logs/ai-learning-companion/core.log
~/Library/Logs/ai-learning-companion/gestures.log
```

也可以在 `.env` 用 `COMPANION_CORE_LOG_PATH` / `COMPANION_GESTURE_LOG_PATH` 覆寫。

---

## 常用操作

```text
/help <內容>          Help me say it
/hint <內容>          Give me a hint
/say <中文>           Translate and send as user message
/review               Start due review
/review quit          Stop review
/remember <內容>      Save memory
/memories [keyword]   Search active memories
/forget <id>          Preview memory deletion
/status               Developer / runtime status
/preferences ...      View or change learning preferences
```

Keyboard shortcuts：

```text
Ctrl+H  Help
Ctrl+G  Hint
Ctrl+R  Review
Ctrl+M  Start / stop & submit spoken review answer
Ctrl+X  Cancel current recording
Ctrl+K  Toggle gestures during review
Ctrl+F  Finish review-complete state
```

---

## Privacy / data boundary

- Conversation、learning state 與 memory 主要持久化在本機 SQLite。
- Camera frames、preview frames、gesture landmarks / history 不寫入資料庫、不存檔、不上傳。
- Review audio 是暫時資料；STT 需要送往設定的 Groq transcription endpoint，但專案不持久化原始錄音。
- `.env` 與 API key 不應 commit。
- Semantic embeddings 是否使用遠端或本機 provider，取決於你的 `.env` 設定；預設範例以本機 Ollama 為例。

---

## 目前邊界

Teacher v0.1 並不是完整語言學習平台。目前刻意不做：

- 關閉程式後的背景 daemon / 系統通知。
- Continuous voice conversation。
- TTS、發音／口音／流暢度評分。
- 情緒辨識、臉部狀態推論或通用 vision assistant。
- 任意 camera / hardware / file tool agent。
- 完整 memory 編輯、審核、敏感度與衝突管理 UI。
- LLM 自主決定 spaced-review schedule。
- 正式的 learning-outcome / retention 實驗。

這些是後續可能的研究或產品方向，不是 v0.1 release blocker。

---

## 驗證

自動測試主要使用 fake provider，因此一般 CI 不需要 API key，也不需要實體 camera / microphone。

主要 gates：

```bash
ruff check .
mypy .
pytest
```

Release 前也會做 Alembic upgrade → downgrade → upgrade smoke test 與 `git diff --check`。

真正的 camera、microphone、semantic provider 與完整 long-term interaction 仍需要 target-Mac UAT。

目前 release sign-off 追蹤於 [#101 — v0.1.0 Final user UAT and release sign-off](https://github.com/Lilian0414/teacher/issues/101)。

---

## 專題／研究定位

Teacher 不主張自己發明 AI tutoring、long-term memory、spaced repetition、proactive intervention、speech-to-text 或 webcam gestures。

目前比較合理的定位是這些能力的**系統整合與互動模型**：

> **long-term continuity + selective pedagogical intervention + spaced review + lightweight multimodal cues**

也就是：把一般對話中的學習訊號轉成持久化 learning state，透過 review 與 proactive practice 在未來重新帶回，並以語音與簡單本機 gesture 降低 review interaction 的摩擦。

相關研究與 prior art 持續整理於 [#91 — Related work and literature grounding for Teacher](https://github.com/Lilian0414/teacher/issues/91)。

---

## Project status

目前 `pyproject.toml` 版本為 **0.1.0**。

#90 / #93 / #94 / #95 對應的 UI、camera/gesture runtime、learning-signal reliability 與 semantic review grading 工作已完成並進入 `main`。

下一步不是擴充功能，而是完成 #101 的最後使用者驗收與 release sign-off；通過後可把目前版本視為：

> **v0.1.0 — first usable prototype**
