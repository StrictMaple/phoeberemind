# 菲比提醒

一個使用 Python + PySide6 製作的桌面提醒工具。

## 功能

- 提醒與排程功能
- 桌面圖形介面
- 自動檢查 GitHub 最新版本
- 發現新版本時顯示更新提示
- 顯示 GitHub Release 的更新內容
- 自動下載新版程式
- 使用獨立 Updater 完成程式更新
- 程式啟動後會立即檢查更新
- 之後每 1 小時自動檢查一次更新

## 使用方式

下載 GitHub Release 中的：

- `PhoebeReminder.exe`

將 `PhoebeReminder.exe` 改成自己喜歡的檔名即可，例如：

`菲比提醒.exe`

正常使用時直接啟動主程式即可，Updater 會在需要更新時由程式自動處理。

## 自動更新

程式會從 GitHub Release 檢查最新版本。

更新流程：

1. 啟動程式後檢查目前版本。
2. 如果 GitHub 有較新的 Release，顯示更新通知。
3. 顯示目前版本、最新版本以及 Release Notes。
4. 使用者選擇「立即更新」後，背景下載新版檔案。
5. 啟動 Updater。
6. Updater 替換舊版程式並重新啟動。

程式不需要每次都重新啟動才能檢查更新：

- 啟動時檢查一次
- 之後每 1 小時檢查一次
