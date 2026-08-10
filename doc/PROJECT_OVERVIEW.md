# 主動式 AI 英文學習陪伴助手

## 專題目標

開發一套常駐於 macOS 的 AI 英文學習陪伴助手。第一版只支援 MacBook Pro M2。

系統核心功能：

1. 以文字或語音進行英文日常對話。
2. 根據使用者設定、學習進度與過往互動，在合適時間主動邀請練習。
3. 保存經篩選的長期生活記憶，延續先前話題。
4. 記錄使用者不熟悉的單字與句型，安排後續複習。
5. 使用者不會用英文表達時，可透過中文指令取得協助。
6. 使用者可拒絕、延後或關閉主動邀請。

## 主要使用流程

AI 主動詢問：

```text
Do you have a minute to practice English?
```

使用者接受後，AI 可依長期記憶延續先前話題：

```text
How has Andy been doing since he changed jobs?
```

若使用者不會表達，可輸入：

```text
/help 我不會說出軌，Anny 跟 Larry 出軌了
```

AI 提供自然英文與簡短中文說明，但不自動把回答代入對話：

```text
Anny cheated on her partner with Larry.
Anny and Larry had an affair.
```

其他語言協助指令：

```text
/hint <內容>     只提供關鍵字或句型
/say <中文>      翻成英文並代入目前對話
/explain <英文>  以中文簡短解釋
```

## Mac 第一版範圍

第一版包含：

- Textual 終端介面。
- FastAPI 背景服務。
- 英文文字對話。
- 中文語言救援指令。
- 對話紀錄與長期記憶。
- 英文學習紀錄與複習。
- 規則式主動邀請。
- Mac 麥克風、語音辨識與語音輸出。

第一版不包含：

- Raspberry Pi、MQTT 或其他硬體。
- 鏡頭、手勢、臉部或情緒辨識。
- 螢幕監控。
- 檔案修改或 shell command。
- 多 agent。
- 日文、國考或其他學習模組。
- 音素級發音評分。

## 開發里程碑

| Milestone | 內容 |
|---|---|
| M0 | 專案骨架、Core、UI、SQLite、狀態與測試 |
| M1 | Groq 文字對話與 `/help` 等語言指令 |
| M2 | 可管理的長期記憶 |
| M3 | 英文學習紀錄與複習閉環 |
| M4 | 主動邀請與勿擾排程 |
| M5 | Mac 語音輸入與輸出 |

每次只能實作一個 milestone。完成、測試及檢查後，才能讀取下一個 milestone 規格。
