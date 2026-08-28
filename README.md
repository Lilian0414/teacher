# Teacher — 主動式 AI 英文學習陪伴助手

Teacher 是一個以「長期陪伴與持續學習」為核心的 AI English Learning Companion。

它不只希望在使用者問問題時給出答案，而是嘗試把日常對話、語言協助、長期記憶、複習排程與主動練習串成一個可以持續運作的學習循環。

目前專案以 macOS 上的文字介面為主要使用方式，已完成從一般對話、語言協助、learning item、間隔複習、長期記憶，到程式運行期間主動邀請練習的核心流程。

> 專案目前仍在持續迭代。現階段重點不是取代完整語言學習平台，而是驗證：AI 是否能在長期互動中理解「使用者正在學什麼」、保留相關脈絡，並在適當時機重新帶回學習內容。

---

## 為什麼做 Teacher？

一般聊天型 AI 很擅長回答當下的問題，但一次對話結束後，學習往往也跟著中斷。

例如使用者今天問了：

- 「這句英文怎麼講比較自然？」
- 「這個單字我一直記不起來。」
- 「我上次不是有問過這個嗎？」

傳統 chatbot 可以回答這些問題，但不一定會把它們變成之後真正會再次出現的學習內容。

Teacher 想探索的是另一種互動模式：

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

也就是把「問過一次」變成「之後還會繼續學」。

---

## 一個實際的使用流程

假設使用者在聊天時不知道一句英文要怎麼表達：

```text
/help 我昨天太累所以直接睡著了
```

Teacher 會提供自然的英文說法，並把適合學習的內容建立成 learning item。

之後使用者可以輸入：

```text
/review
```

系統會一次出一題，根據回答結果更新該 learning item 的 stage 與下一次複習時間。

答對後，複習間隔會依序延長：

```text
1 → 3 → 7 → 14 → 30 天
```

答錯則回到 stage 0，並安排隔天再次複習。

如果程式持續開啟，Teacher 也可以在符合條件時主動提出練習邀請。使用者可以選擇立即開始、稍後再說，或今天不練。

另一方面，一般對話中的部分個人資訊會在對話結束後被整理成長期 memory。之後即使使用者換一種說法聊天，系統仍可以把與目前語境相關的記憶取回，加入新的對話脈絡。

這讓 Teacher 的互動不只停留在單次 prompt-response，而是形成跨對話的連續性。

---

## 目前已完成的能力

### 1. 一般對話

- 支援持久化的文字對話。
- 使用可替換的 LLM provider interface。
- 正式環境目前可使用 Groq；測試使用 `FakeLLMProvider`。
- 對話資料儲存在本機 SQLite。

### 2. 即時語言協助

Teacher 提供三種不同用途的語言輔助：

```text
/help <內容>   解釋英文，或協助把中文／混合輸入轉成自然英文
/hint <內容>   只提供少量提示，不直接給完整答案
/say <中文>    翻譯一句話並把結果作為這次對話中的使用者訊息送出
```

`/help` 與 `/hint` 可以建立去重後的 learning item；`/say` 不會建立 learning item。

### 3. Learning item 與間隔複習

```text
/review       開始複習目前到期的 learning item
<answer>      回答目前題目
/review quit  離開複習模式
```

在 macOS 的複習畫面也可以按 **Speak answer**（或 `Ctrl+M`）錄製五秒回答。
Teacher 只在記憶體中建立短暫 WAV，交由 Core 使用既有的 `GROQ_API_KEY` 與
`whisper-large-v3-turbo` 轉錄，顯示 transcript 後再走同一條 review answer path；
錄音與轉錄失敗時仍可直接打字。第一次使用時請允許終端機存取麥克風；
若 PortAudio 無法載入，可先執行 `brew install portaudio` 再重新安裝專案。

目前 review 採本機 deterministic grading，不另外呼叫 LLM。

系統會記錄：

- prompt
- accepted answer
- review attempt
- stage
- next review time

回答正確後逐步延長間隔；回答錯誤則重新排程。

### 4. 長期記憶

Teacher 可以從已完成的對話中擷取部分使用者資訊，儲存在 SQLite 中。

目前 memory category 包含：

- `people`
- `personal`
- `school_work`
- `relationships`
- `health_fitness`
- `other`

一般聊天時，系統最多取回五筆與目前內容相關的 active memories，加入 LLM context，而不是把整個 memory database 全部送出。

除了 lexical / person matching 外，也可以選擇啟用 OpenAI-compatible embeddings，使用 hybrid semantic recall。

若 embedding provider 不可用、舊資料沒有向量、或向量 model / dimensions 不相容，系統會安全退回 lexical / person matching。

### 5. Memory 管理

```text
/remember <內容>              明確儲存一筆記憶
/memories [關鍵字]           列出或搜尋 active memories
/forget <memory_id>          預覽要刪除的記憶
/forget <memory_id> confirm  確認 soft delete
```

刪除採 soft delete，資料會保留在 SQLite 中，但不再參與一般 recall。

### 6. Learning context 回到一般對話

除了 life memory 之外，最多三筆到期的 learning goals 也可以加入一般聊天 context。

Learning data 與 life memory 在資料模型與提示中保持分離，避免把「我要學的內容」誤當成「關於我的事實」。

### 7. 主動練習邀請

Teacher 已完成程式運行期間的 proactive practice invitation。

系統會根據 Core 中的 eligibility、cooldown、daily limit、availability 與 review 狀態判斷是否適合邀請。

使用者可以選擇：

- Start
- Later
- Not today

目前主動邀請只會在 Textual UI 正在執行時出現，不包含背景 daemon、macOS notification 或關閉程式後的提醒。

---

## Teacher 與一般 Chatbot 的差異

Teacher 的目標並不是增加更多聊天功能，而是維持一個跨時間的 learning state。

目前專案特別關注四個方向：

**Conversation continuity**  
不是每段對話都從零開始，而是可以取回與目前情境相關的長期資訊。

**Learning continuity**  
語言協助不只回答一次，也可以進入 learning item 與之後的 review。

**Stateful learning**  
系統記錄學習 stage、review history 與 next review time，而不是只依賴 LLM 自己「記得」。

**Proactive interaction**  
在適合的時機由系統提出練習，而不是永遠等待使用者主動輸入指令。

---

## 可能延伸的研究／專題方向

目前 Teacher 比較像一個可運作的 prototype，也留下幾個可以繼續深入的問題：

- AI 應該如何判斷一段對話中什麼內容值得成為 learning item？
- 長期記憶與 learning state 應該如何分離、互相引用與處理衝突？
- proactive learning intervention 在什麼時間點出現才不會造成干擾？
- 個人化 retrieval 是否能改善後續學習提示與複習內容？
- deterministic scheduling 與 LLM-based adaptive scheduling 應如何取捨？
- 如何評估一個長期 AI learning companion 是否真的提升 retention，而不是只增加互動次數？

目前這些仍屬於後續探索方向，不代表專案已完成相關研究驗證。

---

## 系統架構

目前主要元件如下：

```text
┌──────────────────────┐
│      Textual UI      │
└──────────┬───────────┘
           │ HTTP
           ▼
┌──────────────────────┐
│     FastAPI Core     │
│                      │
│ Conversation         │
│ Memory               │
│ Learning / Review    │
│ Proactive Practice   │
└───────┬──────────────┘
        │
        ├──────────────► LLM Provider (Groq / Fake)
        │
        ├──────────────► Embedding Provider (optional)
        │
        ▼
┌──────────────────────┐
│ SQLite + SQLAlchemy  │
│      + Alembic       │
└──────────────────────┘
```

設計上，UI 不直接操作資料庫。資料、availability、排程與 destructive policy 由 Core 擁有。

目前技術組合主要包含：

- Python 3.12
- FastAPI
- SQLAlchemy 2.x
- Alembic
- SQLite
- Textual
- Groq / OpenAI-compatible LLM interface
- OpenAI-compatible embeddings（optional）
- pytest
- Ruff
- mypy

完整的 M0–M4 capability matrix 可參考 [`doc/PROJECT_OVERVIEW.md`](doc/PROJECT_OVERVIEW.md)。

---

## 目前邊界

Teacher 目前尚未實作：

- 關閉程式後的背景通知
- macOS launch agent / background service
- voice interaction
- webcam / hardware / file tools
- private conversation mode
- memory sensitivity level
- memory candidate approval UI
- memory audit history
- memory conflict / superseded state
- memory editing
- proactive-use permission controls

因此，目前的 proactive practice 應理解為「程式內主動邀請」，而不是背景提醒服務。

LangChain、Mem0 與 Letta 目前也不在專案架構中。

---

## 安裝與執行（Apple Silicon）

需要 Python 3.12。

如果要使用 semantic memory，另外需要安裝 Ollama。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
cp .env.example .env
```

在 `.env` 中填入自己的 `GROQ_API_KEY`。

啟動 Ollama：

```bash
ollama serve
```

下載目前使用的 embedding model：

```bash
ollama pull nomic-embed-text
```

初始化／更新資料庫：

```bash
alembic upgrade head
```

啟動 Teacher：

```bash
companion
```

`companion` 會一起啟動 Core 與 Textual UI。

開發時也可以分成兩個 process：

```bash
companion-core
```

另一個 terminal：

```bash
companion-ui
```

預設 SQLite database 位於：

```text
~/Library/Application Support/ai-learning-companion/companion.sqlite3
```

也可以透過 `COMPANION_DATABASE_URL` 指定其他絕對路徑。

---

## Groq 與 Semantic Memory 設定

範例：

```env
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-20b
GROQ_BASE_URL=https://api.groq.com/openai/v1
LLM_TIMEOUT_SECONDS=30

MEMORY_CONTEXT_LIMIT=5
LEARNING_CONTEXT_LIMIT=3

EMBEDDINGS_ENABLED=true
EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
EMBEDDING_API_KEY=
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768
EMBEDDING_TIMEOUT_SECONDS=10
```

請勿把真實 `GROQ_API_KEY` commit 到 repository。

如果不需要 semantic recall，可以設定：

```env
EMBEDDINGS_ENABLED=false
```

此時 memory recall 會使用 lexical / person matching。

---

## 驗證

`requirements.lock` 固定 Python 3.12 的 application 與 development dependencies。

安裝後可以執行與 CI 相同的主要檢查：

```bash
ruff check .
mypy .
pytest
```

一般自動測試使用 fake provider，並保持 embeddings 關閉，因此不需要 API key。

---

## 專案狀態

目前 M0–M4 核心能力已完成，包括：

- 基礎 Core / UI / persistence
- 英文對話與語言協助
- 長期 memory 與 hybrid semantic recall
- learning item 與 spaced review
- learning context retrieval
- 程式內 proactive practice invitation

下一階段的重點會放在整體使用流程、長期 learning loop 的可靠性，以及哪些能力值得進一步發展成更正式的研究或產品題目。

## Optional local review gestures (macOS)

During a review question, **Gestures** (`Ctrl+K`) can enable two local-only camera
interactions: a stable thumbs-down shows the existing hint without submitting or grading an
answer, and a stable thumbs-up dismisses the celebration shown after a correct final
answer. A thumbs-up never grades an answer or changes learning state. Incorrect final
answers skip the celebration. **Finish** (`Ctrl+F`) always exits the celebration without
a camera.

Camera support is optional. Install the gesture extra (`pip install -e '.[gestures]'`),
download a compatible MediaPipe Gesture Recognizer task model, copy
`.env.example` to `.env`, and set `COMPANION_GESTURE_MODEL`
there to absolute local paths. No shell export is needed. Camera index `0` normally selects
the built-in Mac camera; persist `COMPANION_GESTURE_CAMERA_INDEX=1` (or another tested
AVFoundation index) in `.env` if Continuity Camera occupies it. On first use, allow the
terminal camera permission in macOS System Settings. Missing packages,
models, camera hardware, or permission leave typed and spoken review available. Frames,
landmarks, and gesture history are processed ephemerally in memory and are never saved
or uploaded.

The combined `companion` launcher writes Core diagnostics to
`~/Library/Logs/ai-learning-companion/core.log`; fd-level MediaPipe diagnostics go to
`gestures.log` beside it. The `.env` log-path settings shown in `.env.example` override
these locations. Standalone `companion-core` continues to print to its own terminal.

Target-Mac UAT: verify `review -> enable Gestures -> thumbs-down -> hint -> type/speak answer`,
then complete a review correctly and verify both `thumbs-up -> finish` and the Finish
button. Repeat with camera permission denied to verify both fallbacks.
