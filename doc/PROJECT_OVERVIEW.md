# 主動式 AI 英文學習陪伴助手

## 專題目標

本專題在 macOS 上提供以文字為主的 AI 英文學習陪伴：持久化對話與生活記憶、語言
救援、間隔複習，以及程式開啟期間的低干擾主動練習邀請。下表是 README 與各 milestone
文件共用的正式能力基準。

## M0–M4 capability matrix

| Milestone | 狀態 | 已交付能力 | 明確邊界 |
|---|---|---|---|
| M0 | 已完成 | Python 3.12 專案、FastAPI Core、Textual UI、SQLite/Alembic、availability 與 deterministic commands | 無背景 daemon 或 OS integration |
| M1 | 已完成 | 持久化英文文字對話、Groq/Fake provider、`/help`、`/hint`、`/say` | Groq 需要自行配置；一般測試不連線 |
| M2 | 已完成 | 長期記憶抽取、搜尋、soft delete、Top-5 recall；可選的 OpenAI-compatible embeddings 提供 hybrid semantic recall | embeddings 預設關閉；失敗時降級 lexical/person；無 vector database、approval/audit/edit UI |
| M3 | 已完成 | learning items、逐題 `/review`、本機評分、固定間隔排程、Top-3 learning context 與 UI intent actions | 無 LLM grading，learning data 不混入生活記憶 |
| M4 | 已完成（限程式內） | Core-owned eligibility、持久化邀請、review 優先、daily limit/cooldown、Start/Later/Not today，以及 Textual invitation card | 只在 Textual UI 執行時 polling；無關閉程式後通知、launch agent 或背景服務 |

## 共通安全與資料邊界

- UI 只透過 HTTP 呼叫 Core；Core 擁有資料庫、availability、排程與 destructive policy。
- 一般聊天最多加入五筆 relevant active memories 與三筆 due learning goals，兩者分開標示。
- semantic memory 已接入正式 runtime，但只有明確啟用並配置 embedding endpoint 時使用；
  provider 錯誤、舊資料或不相容向量都安全降級。
- proactive polling、邀請接受與 review grading 都是 deterministic local operations，不呼叫
  Groq 或 embedding API。只有使用者真正送出一般聊天內容才可能呼叫已配置的 LLM。
- 自動測試使用 fake providers；live Groq test 必須另行 opt in 並提供 key。

## 尚未實作

Private conversations、記憶敏感度、candidate approval、audit history、衝突／superseded
states、記憶編輯、proactive-use permissions、背景／macOS 通知、語音、硬體、鏡頭與檔案
工具尚未實作。M4 的程式內邀請不應被描述成 background reminder。
