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
- `PhoebeReminder_Updater.exe`

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

## 發布新版本

目前 GitHub Actions 使用 Tag 觸發自動打包。

例如發布 `1.0.2`：

```bat
git add bot.py
git commit -m "Release 1.0.2"
git push origin main
git tag v1.0.2
git push origin v1.0.2
```

GitHub Actions 會自動建立 Windows 執行檔：

```text
PhoebeReminder.exe
PhoebeReminder_Updater.exe
```

## Release Notes

每次發布新版本時，可以在 GitHub Release 的說明中填寫更新內容，例如：

```text
新增：
- 新增 XXX 功能
- 新增 XXX 設定

修正：
- 修復 XXX 問題
- 修復自動更新問題
```

程式會自動讀取 Release Notes，並在更新通知中顯示。

## 版本號

版本號位於 `bot.py`：

```python
APP_VERSION = "1.0.0"
```

發布新版本時，請同步修改版本號，例如：

```python
APP_VERSION = "1.0.2"
```

Tag 則使用：

```text
v1.0.2
```

版本號與 Tag 應保持一致。

## 專案結構

```text
菲比提醒/
├── .github/
│   └── workflows/
│       └── build.yml
├── 1.ico
├── 1.png
├── bot.py
├── build.bat
├── updater.py
└── README.md
```

## GitHub Actions

`.github/workflows/build.yml` 會在推送 `v*` Tag 時自動執行：

1. 建立 Windows 建置環境
2. 安裝 Python 3.11
3. 安裝 PySide6、Pillow、PyInstaller
4. 建立 ICO
5. 打包主程式
6. 打包 Updater
7. 驗證 EXE 是否成功產生
8. 建立 GitHub Release

## 注意事項

- 不要重複使用已發布過的 Tag。
- 新版本請使用新的版本號與 Tag。
- `PhoebeReminder.exe` 是主程式。
- `PhoebeReminder_Updater.exe` 是更新程式，不需要手動啟動。
