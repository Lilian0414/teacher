# 主動式 AI 英文學習陪伴助手

## 專題目標

本專題要在 macOS 上建立一套 AI 英文學習陪伴助手。長期方向包含英文對話、
個人記憶、學習複習、主動邀請與語音互動；目前完成範圍到 M3。

## 目前完成的 M0–M3

- FastAPI Core、Textual 終端介面、SQLite、SQLAlchemy 2.x 與 Alembic。
- `available`、`busy`、`dnd` 狀態及 deterministic slash-command parser。
- 可保存 user／assistant 訊息的英文文字對話。
- `/help`、`/hint`、`/say` 三個語言救援指令。
- `/remember`、`/memories`、需確認的 `/forget`。
- 對話結束時從 user messages 抽取記憶，並由 deterministic policy 驗證來源、
  無效寒暄與完全重複內容。
- 每次聊天最多加入五筆與目前訊息相關的 active memories。
- Fake provider 自動測試，以及明確 opt-in 的 Groq live tests。
- `/help`、`/hint` 會建立獨立於生活記憶的 learning item，並以 normalized prompt
  與 kind 去重；`/say` 不會建立學習項目。
- `/review` 直接進入逐題互動複習，可中途 `/review quit`，重開後仍能依到期資料續接。
- 本機 deterministic grading 與 1／3／7／14／30 天複習間隔。
- 正常對話可同時收到分開標示的 due learning goals 與 relevant active memories。

語言救援的差異：

```text
/help <內容>  提供自然英文，或用中文解釋英文；不代入對話
/hint <內容>  只提供一至三個單字、片語或未完成句型；不代入對話
/say <中文>   翻成一句自然英文，代入目前對話並取得正常回覆
```

## 尚未完成

M3 不包含 private conversation、記憶敏感度、candidate approval、audit history、
衝突狀態、記憶編輯或 proactive-use permissions。英文學習紀錄、複習排程、
已在 M3 完成；主動邀請、背景提醒、語音、硬體、鏡頭和檔案工具仍未實作。

## 開發里程碑

| Milestone | 狀態 | 內容 |
|---|---|---|
| M0 | 已完成 | 專案骨架、Core、UI、SQLite、availability 與測試 |
| M1 | 已完成 | Groq 文字對話與三個語言救援指令 |
| M2 | 已完成 | 精簡版長期記憶、抽取、搜尋、刪除與 recall |
| M3 | 已完成 | 英文學習紀錄、逐題複習、固定間隔與 learning context |
| M4 | 未開始 | 主動邀請與排程 |
| M5 | 未開始 | Mac 語音輸入與輸出 |

每次只實作一個經核准的 milestone；完成後必須通過 Ruff、strict mypy 與 pytest。
