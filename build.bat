@echo off
chcp 65001 >nul
setlocal

title 菲比提醒 - EXE 打包工具

echo.
echo ================================================
echo          菲比提醒 - EXE 打包工具
echo ================================================
echo.

REM ==================================================
REM 取得目前 BAT 所在資料夾
REM ==================================================

cd /d "%~dp0"

echo [目前目錄]
echo %CD%
echo.


REM ==================================================
REM 檢查 bot.py
REM ==================================================

if not exist "bot.py" (
    echo.
    echo [錯誤] 找不到 bot.py
    echo.
    echo 請確認 build.bat 和 bot.py 放在同一個資料夾。
    echo.
    pause
    exit /b 1
)


REM ==================================================
REM 檢查 1.png
REM ==================================================

if not exist "1.png" (
    echo.
    echo [錯誤] 找不到 1.png
    echo.
    echo 請確認 1.png 和 build.bat 放在同一個資料夾。
    echo.
    pause
    exit /b 1
)


REM ==================================================
REM 檢查 Python
REM ==================================================

echo [1/7] 檢查 Python...

python --version >nul 2>&1

if errorlevel 1 (
    echo.
    echo [錯誤] 找不到 Python。
    echo.
    echo 請先安裝 Python。
    echo.
    pause
    exit /b 1
)

python --version

echo.


REM ==================================================
REM 更新 pip
REM ==================================================

echo [2/7] 更新 pip...

python -m pip install --upgrade pip

if errorlevel 1 (
    echo.
    echo [警告] pip 更新失敗。
    echo 嘗試繼續打包...
    echo.
)


REM ==================================================
REM 安裝 Pillow
REM ==================================================

echo [3/7] 檢查 Pillow...

python -m pip install --upgrade Pillow

if errorlevel 1 (
    echo.
    echo [錯誤] Pillow 安裝失敗。
    echo.
    pause
    exit /b 1
)

echo.


REM ==================================================
REM 安裝 PyInstaller
REM ==================================================

echo [4/7] 檢查 PyInstaller...

python -m pip install --upgrade PyInstaller

if errorlevel 1 (
    echo.
    echo [錯誤] PyInstaller 安裝失敗。
    echo.
    pause
    exit /b 1
)

echo.


REM ==================================================
REM 確認 PySide6
REM ==================================================

echo [5/7] 檢查 PySide6...

python -c "import PySide6; print('PySide6 OK')"

if errorlevel 1 (
    echo.
    echo [錯誤] 找不到 PySide6。
    echo.
    echo 正在安裝 PySide6...
    echo.

    python -m pip install --upgrade PySide6

    if errorlevel 1 (
        echo.
        echo [錯誤] PySide6 安裝失敗。
        echo.
        pause
        exit /b 1
    )
)

echo.


REM ==================================================
REM 將 PNG 轉成 ICO
REM ==================================================

echo [6/7] 建立 EXE 圖示 1.ico...

python -c "from PIL import Image; img=Image.open('1.png').convert('RGBA'); img.save('1.ico',format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"

if errorlevel 1 (
    echo.
    echo [錯誤] 1.png 無法轉換成 1.ico。
    echo.
    pause
    exit /b 1
)

if not exist "1.ico" (
    echo.
    echo [錯誤] 1.ico 建立失敗。
    echo.
    pause
    exit /b 1
)

echo.
echo 1.ico 建立成功。
echo.


REM ==================================================
REM 清理舊打包資料
REM ==================================================

echo [清理] 移除舊的 build / dist...

if exist "build" (
    rmdir /s /q "build"
)

if exist "dist" (
    rmdir /s /q "dist"
)

if exist "菲比提醒.spec" (
    del /f /q "菲比提醒.spec"
)

echo 清理完成。
echo.


REM ==================================================
REM 開始 PyInstaller
REM ==================================================

echo [7/7] 開始打包...
echo.
echo ================================================
echo                 PyInstaller
echo ================================================
echo.

python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "菲比提醒" ^
    --icon "1.ico" ^
    --add-data "1.png;." ^
    --collect-all PySide6 ^
    "bot.py"


REM ==================================================
REM 檢查打包結果
REM ==================================================

if errorlevel 1 (
    echo.
    echo.
    echo ================================================
    echo                  打包失敗
    echo ================================================
    echo.
    echo 請查看上面的錯誤訊息。
    echo.
    pause
    exit /b 1
)


if not exist "dist\菲比提醒.exe" (
    echo.
    echo.
    echo ================================================
    echo             找不到打包後的 EXE
    echo ================================================
    echo.
    pause
    exit /b 1
)


REM ==================================================
REM 完成
REM ==================================================

echo.
echo.
echo ================================================
echo                  打包完成！
echo ================================================
echo.
echo EXE：
echo.
echo %CD%\dist\菲比提醒.exe
echo.
echo -----------------------------------------------
echo.
echo 使用者只需要：
echo.
echo     菲比提醒.exe
echo.
echo 不需要：
echo     Python
echo     pip
echo     PySide6
echo     Pillow
echo     其他 Python 套件
echo.
echo -----------------------------------------------
echo.
echo 使用者資料會放在：
echo.
echo     %%TEMP%%\DailyWidget\
echo.
echo     daily_tasks.json
echo     window_config.json
echo.
echo ================================================
echo.


REM ==================================================
REM 開啟 dist 資料夾
REM ==================================================

explorer "%CD%\dist"


echo.
echo 按任意鍵結束...
pause >nul

endlocal