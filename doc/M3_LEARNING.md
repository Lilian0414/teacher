# M3 英文學習閉環

## 已完成功能

成功的 `/help` 會把完整英文表達建立成 `expression` item；成功的 `/hint` 會把
關鍵詞、片語或句型建立成 `phrase` item。相同 user、正規化 prompt 與 kind 只保留
一筆 active learning item，重複求助會合併 accepted answers 並讓它立即到期。
`/say` 只負責把翻譯送入對話，不建立 learning item。

## 互動式複習

輸入 `/review` 後只顯示一題，不先顯示 accepted answers。下一個非 slash-command
輸入會成為該題答案；Core 回傳正誤、accepted answers、下一次複習時間與下一題。
其他 slash commands 可在複習中照常使用，且不清除未回答題目。`/review quit` 只清除
terminal 的 transient state，不新增 attempt，也不改排程。

系統不保存 review cursor。已回答題目已更新 next-review time，未回答題目仍到期，
因此程式關閉後重新輸入 `/review` 就能安全續接。

## 評分與排程

評分在 Core 本機完成，不呼叫 LLM。比對時忽略英文字母大小寫、頭尾與重複空白，
以及句尾的中英文句號、問號和驚嘆號；除此之外採 accepted answers 的精確比對。

答對會將 stage 加一，依序安排 1、3、7、14、30 天；stage 五以上維持 30 天。
答錯會把 stage 重設為零，並安排一天後複習。所有時間都取自可注入的 application
clock，item 更新與 attempt 新增在同一 transaction 中完成。

## 資料邊界

`learning_items` 保存 prompt、accepted answers、kind、source command、stage 與 due time；
`learning_attempts` 保存 append-only 作答歷史。這些資料不寫入 M2 的 `memories`，也不
參與 memory search／forget。正常對話最多取得三筆 due learning goals，並與最多五筆
relevant active memories 分開標示後交給 provider。

## 不在 M3 範圍

M3 不包含背景排程、主動提醒、勿擾時段、拒絕冷卻、語音輸入輸出、硬體或檔案工具。
