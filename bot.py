import sys
import os
import json
import ctypes
import uuid
import subprocess
import html
import winreg
import urllib.request
import urllib.error
import tempfile
import threading

from datetime import datetime, date

from PySide6.QtCore import (
    Qt,
    QEvent,
    QPoint,
    QRect,
    QSize,
    QTimer,
    QTime,
    QObject,
    Signal,
)

from PySide6.QtGui import (
    QFont,
    QColor,
    QPainter,
    QPen,
    QIcon,
    QAction,
    QCursor,
)

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLineEdit,
    QMenu,
    QSystemTrayIcon,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTimeEdit,
)


# =========================================================
# Windows DPI
# =========================================================

if sys.platform == "win32":

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-4)
        )
    except Exception:

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:

            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


# =========================================================
# 基本設定
# =========================================================

APP_NAME = "菲比提醒"
APP_VERSION = "1.0.0"

GITHUB_OWNER = "StrictMaple"
GITHUB_REPO = "phoeberemind"

WINDOWS_AUMID = "PhoebeReminder"

FONT_NAME = "Microsoft JhengHei"

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


# =========================================================
# 自動更新
# =========================================================

def _version_tuple(version):
    """將 v1.2.3 / 1.2.3 轉成可比較的版本 tuple。"""
    value = str(version or "").strip().lower()
    if value.startswith("v"):
        value = value[1:]

    parts = []
    for part in value.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits or "0"))

    while len(parts) < 3:
        parts.append(0)

    return tuple(parts[:3])


def _get_latest_release():
    """取得 GitHub 最新正式 Release。"""
    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    )

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "PhoebeReminder-Updater"
        }
    )

    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_file(url, destination):
    """下載檔案到指定路徑。"""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PhoebeReminder-Updater"
        }
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        with open(destination, "wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)


def _find_release_asset(assets, preferred_names):
    """
    尋找 Release Asset。
    優先使用指定名稱；若名稱不同，則依 EXE / Updater 類型判斷，
    避免 GitHub Asset 被命名成 default.exe 時無法更新。
    """
    assets = assets or []

    # 1. 精確名稱
    for preferred in preferred_names:
        for asset in assets:
            if str(asset.get("name", "")) == preferred:
                return asset

    # 2. 忽略大小寫
    preferred_lower = {
        name.lower()
        for name in preferred_names
    }

    for asset in assets:
        name = str(asset.get("name", "")).strip()
        if name.lower() in preferred_lower:
            return asset

    return None


class _UpdateController(QObject):
    """更新控制器：UI 詢問與啟動 Updater 都在 Qt 主執行緒。"""

    update_available = Signal(str, object)
    download_finished = Signal(str, str, str)
    update_error = Signal(str)

    def __init__(self):
        super().__init__()
        self._check_thread = None
        self._check_worker = None
        self._download_thread = None
        self._download_worker = None
        self._current_exe = None
        self._release = None
        self._latest_tag = None

        self.update_available.connect(self._show_update_and_continue)
        self.download_finished.connect(self._launch_updater)
        self.update_error.connect(self._show_update_error)

    def start(self):
        if not getattr(sys, "frozen", False):
            return

        self._check_thread = threading.Thread(
            target=self._check_release,
            daemon=True
        )
        self._check_thread.start()

    def _check_release(self):
        try:
            release = _get_latest_release()
            latest_tag = str(release.get("tag_name", "")).strip()

            if not latest_tag:
                return

            if _version_tuple(latest_tag) <= _version_tuple(APP_VERSION):
                return

            self.update_available.emit(latest_tag, release)
        except Exception:
            return

    def _show_update_and_continue(self, latest_tag, release):
        release_notes = str(
            release.get("body", "")
        ).strip()

        confirmed = _show_update_question(
            latest_tag,
            release_notes
        )
        if not confirmed:
            return

        self._release = release
        self._latest_tag = latest_tag
        self._current_exe = os.path.abspath(sys.executable)

        self._download_thread = threading.Thread(
            target=self._download_update,
            daemon=True
        )
        self._download_thread.start()

    def _download_update(self):
        try:
            assets = self._release.get("assets", [])

            exe_asset = _find_release_asset(
                assets,
                [
                    "PhoebeReminder.exe",
                    "菲比提醒.exe",
                    "PhoebeReminder",
                    "default.exe"
                ]
            )

            updater_asset = _find_release_asset(
                assets,
                [
                    "PhoebeReminder_Updater.exe",
                    "菲比提醒_Updater.exe",
                    "PhoebeReminder_Updater",
                    "updater.exe"
                ]
            )

            if not exe_asset or not updater_asset:
                raise RuntimeError("GitHub Release 找不到更新檔案。")

            update_dir = tempfile.mkdtemp(
                prefix="PhoebeReminder_Update_"
            )

            new_exe = os.path.join(
                update_dir,
                "PhoebeReminder.exe"
            )
            updater_exe = os.path.join(
                update_dir,
                "PhoebeReminder_Updater.exe"
            )

            _download_file(
                exe_asset["browser_download_url"],
                new_exe
            )
            _download_file(
                updater_asset["browser_download_url"],
                updater_exe
            )

            if (
                not os.path.isfile(new_exe)
                or os.path.getsize(new_exe) <= 0
                or not os.path.isfile(updater_exe)
                or os.path.getsize(updater_exe) <= 0
            ):
                raise RuntimeError("更新檔案下載失敗或檔案大小為 0。")

            self.download_finished.emit(
                self._current_exe,
                new_exe,
                updater_exe
            )

        except Exception as exc:
            message = str(exc) or "未知錯誤"
            self.update_error.emit(message)

    def _launch_updater(self, current_exe, new_exe, updater_exe):
        try:
            subprocess.Popen(
                [
                    updater_exe,
                    current_exe,
                    new_exe
                ],
                cwd=os.path.dirname(current_exe),
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0
                )
            )

            QApplication.quit()

        except Exception as exc:
            self._show_update_error(
                str(exc) or "無法啟動更新程式。"
            )

    def _show_update_error(self, message):
        try:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(
                None,
                APP_NAME,
                "更新失敗\n\n" + message
            )
        except Exception:
            pass


def _show_update_question(latest_version, release_notes):
    """在 Qt 主執行緒顯示更新詢問。"""
    try:
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox()
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("發現新版本")
        box.setInformativeText(
            f"目前版本：{APP_VERSION}\n"
            f"最新版本：{latest_version}\n\n"
            f"最新版本更新內容：\n"
            f"{release_notes or '無更新說明'}\n\n"
            "是否現在更新？"
        )

        update_button = box.addButton(
            "立即更新",
            QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(
            "稍後",
            QMessageBox.ButtonRole.RejectRole
        )

        box.exec()
        return box.clickedButton() is update_button

    except Exception:
        return False


_UPDATE_CONTROLLER = None


def check_for_updates():
    """保留舊入口，實際更新工作由背景執行緒與主執行緒控制器處理。"""
    if _UPDATE_CONTROLLER is not None:
        _UPDATE_CONTROLLER.start()


def start_update_check():
    """背景檢查 GitHub Release，不阻塞主 UI。"""
    if _UPDATE_CONTROLLER is None:
        return
    _UPDATE_CONTROLLER.start()


_UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000


def start_hourly_update_check():
    """每小時檢查一次 GitHub Release。"""
    if _UPDATE_CONTROLLER is None:
        return
    _UPDATE_CONTROLLER.start()


def setup_hourly_update_check():
    """建立每小時自動檢查更新的計時器。"""
    timer = QTimer()
    timer.timeout.connect(start_hourly_update_check)
    timer.start(_UPDATE_CHECK_INTERVAL_MS)
    return timer


# =========================================================
# Local 資料
# =========================================================

LOCAL_APP_DATA = os.environ.get(
    "LOCALAPPDATA",
    os.path.expanduser("~\\AppData\\Local")
)

APP_DATA_DIR = os.path.join(
    LOCAL_APP_DATA,
    "菲比提醒"
)

os.makedirs(
    APP_DATA_DIR,
    exist_ok=True
)

DATA_FILE = os.path.join(
    APP_DATA_DIR,
    "daily_tasks.json"
)

CONFIG_FILE = os.path.join(
    APP_DATA_DIR,
    "window_config.json"
)


# =========================================================
# 圖示
# =========================================================

if getattr(sys, "frozen", False):

    RESOURCE_DIR = getattr(
        sys,
        "_MEIPASS",
        BASE_DIR
    )

else:

    RESOURCE_DIR = BASE_DIR


ICON_FILE = os.path.join(
    RESOURCE_DIR,
    "1.png"
)


# =========================================================
# 視窗
# =========================================================

DEFAULT_WIDTH = 360
DEFAULT_HEIGHT = 240

MIN_WIDTH = 300
MIN_HEIGHT = 170

MAX_WIDTH = 800
MAX_HEIGHT = 900

RESIZE_MARGIN = 18
DRAG_THRESHOLD = 5


# =========================================================
# 版面
# =========================================================

TITLE_X = 15
TITLE_Y = 32

DATE_X = 16
DATE_Y = 58

TIME_X = 16
TIME_Y = 78

TASK_START_Y = 88
TASK_HEIGHT = 48

TASK_TEXT_X = 16

BOTTOM_PADDING = 12


# =========================================================
# Checkbox
# =========================================================

CHECKBOX_SIZE = 42

CHECKBOX_DRAW_SIZE = 30

CHECKBOX_RIGHT_MARGIN = 5

# 整個右側都可以點
CHECKBOX_HIT_WIDTH = 72


# =========================================================
# 提醒
# =========================================================

DEFAULT_REMINDER_TIME = "23:00"

REMINDER_BUTTON_WIDTH = 62
REMINDER_BUTTON_HEIGHT = 28

ADD_BUTTON_WIDTH = 80
ADD_BUTTON_HEIGHT = 28

BUTTON_GAP = 5
BUTTON_RIGHT_MARGIN = 8

REMINDER_TIME_WIDTH = 64

SWITCH_WIDTH = 48
SWITCH_HEIGHT = 28

SWITCH_RIGHT_MARGIN = 8


# =========================================================
# 顏色
# =========================================================

TITLE_COLOR = QColor(
    255,
    255,
    255,
    255
)

TITLE_SHADOW = QColor(
    0,
    0,
    0,
    235
)

DATE_COLOR = QColor(
    255,
    255,
    255,
    255
)

DATE_SHADOW = QColor(
    0,
    0,
    0,
    235
)

TIME_COLOR = QColor(
    255,
    255,
    255,
    255
)

TIME_SHADOW = QColor(
    0,
    0,
    0,
    220
)

TASK_COLOR = QColor(
    255,
    255,
    255,
    255
)

TASK_SHADOW = QColor(
    0,
    0,
    0,
    225
)

CHECKBOX_BORDER = QColor(
    250,
    250,
    255,
    250
)

CHECKBOX_CHECK = QColor(
    95,
    190,
    255,
    255
)

BUTTON_COLOR = QColor(
    75,
    135,
    225,
    230
)

BUTTON_HOVER_COLOR = QColor(
    105,
    170,
    250,
    245
)

REMINDER_COLOR = QColor(
    135,
    105,
    215,
    235
)

REMINDER_ACTIVE_COLOR = QColor(
    170,
    125,
    240,
    245
)

SWITCH_ON = QColor(
    80,
    180,
    255,
    255
)

SWITCH_OFF = QColor(
    100,
    105,
    115,
    230
)

WHITE = QColor(
    255,
    255,
    255,
    255
)

SELECTED_BACKGROUND = QColor(
    255,
    255,
    255,
    45
)

SELECTED_BORDER = QColor(
    255,
    255,
    255,
    80
)


# =========================================================
# 安全時間
# =========================================================

def safe_time_string(
    value
):

    if not value:
        return DEFAULT_REMINDER_TIME

    try:

        parts = str(
            value
        ).split(":")

        hour = int(
            parts[0]
        )

        minute = int(
            parts[1]
        )

        if (
            0 <= hour <= 23
            and
            0 <= minute <= 59
        ):

            return (
                f"{hour:02d}:"
                f"{minute:02d}"
            )

    except Exception:
        pass

    return DEFAULT_REMINDER_TIME


# =========================================================
# 事件資料正規化
# =========================================================

def normalize_tasks(
    tasks
):

    result = []

    if not isinstance(
        tasks,
        list
    ):
        return result

    for task in tasks:

        if not isinstance(
            task,
            dict
        ):
            continue

        text = str(
            task.get(
                "text",
                ""
            )
        ).strip()

        if not text:
            continue

        result.append(
            {
                "text": text,

                "completed": bool(
                    task.get(
                        "completed",
                        False
                    )
                ),

                # ★ 舊事件沒有這個值
                # 預設開啟
                "reminder_enabled": bool(
                    task.get(
                        "reminder_enabled",
                        True
                    )
                ),

                "reminder_time":
                    safe_time_string(
                        task.get(
                            "reminder_time",
                            DEFAULT_REMINDER_TIME
                        )
                    ),

                "last_reminded_date":
                    task.get(
                        "last_reminded_date",
                        None
                    ),

                "notification_tag":
                    str(
                        task.get(
                            "notification_tag",
                            uuid.uuid4().hex
                        )
                    )
            }
        )

    return result


# =========================================================
# 載入資料
# =========================================================

def load_data():

    default = {
        "tasks": [],
        "reminders_enabled": True,
        "last_reset_date": None
    }

    if not os.path.exists(
        DATA_FILE
    ):
        return default

    try:

        with open(
            DATA_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if isinstance(
            data,
            list
        ):

            return {
                "tasks":
                    normalize_tasks(
                        data
                    ),

                "reminders_enabled":
                    True,

                "last_reset_date":
                    None
            }

        if not isinstance(
            data,
            dict
        ):

            return default

        return {
            "tasks":
                normalize_tasks(
                    data.get(
                        "tasks",
                        []
                    )
                ),

            "reminders_enabled":
                bool(
                    data.get(
                        "reminders_enabled",
                        True
                    )
                ),

            "last_reset_date":
                data.get(
                    "last_reset_date",
                    None
                )
        }

    except Exception:

        return default


# =========================================================
# 儲存資料
# =========================================================

def save_data(
    tasks,
    reminders_enabled,
    last_reset_date
):

    try:

        temp_file = (
            DATA_FILE
            +
            ".tmp"
        )

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                {
                    "tasks": tasks,

                    "reminders_enabled":
                        bool(
                            reminders_enabled
                        ),

                    "last_reset_date":
                        last_reset_date
                },
                f,
                ensure_ascii=False,
                indent=4
            )

        os.replace(
            temp_file,
            DATA_FILE
        )

    except Exception:
        pass


# =========================================================
# 視窗設定
# =========================================================

def load_config():

    default = {
        "x": None,
        "y": None,
        "width":
            DEFAULT_WIDTH,
        "height":
            DEFAULT_HEIGHT
    }

    if not os.path.exists(
        CONFIG_FILE
    ):
        return default

    try:

        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        width = int(
            data.get(
                "width",
                DEFAULT_WIDTH
            )
        )

        height = int(
            data.get(
                "height",
                DEFAULT_HEIGHT
            )
        )

        width = max(
            MIN_WIDTH,
            min(
                MAX_WIDTH,
                width
            )
        )

        height = max(
            MIN_HEIGHT,
            min(
                MAX_HEIGHT,
                height
            )
        )

        x = data.get(
            "x"
        )

        y = data.get(
            "y"
        )

        if x is not None:
            x = int(x)

        if y is not None:
            y = int(y)

        return {
            "x": x,
            "y": y,
            "width": width,
            "height": height
        }

    except Exception:

        return default


# =========================================================
# 儲存視窗設定
# =========================================================

def save_config(
    window
):

    try:

        temp_file = (
            CONFIG_FILE
            +
            ".tmp"
        )

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                {
                    "x":
                        window.x(),

                    "y":
                        window.y(),

                    "width":
                        window.width(),

                    "height":
                        window.height()
                },
                f,
                ensure_ascii=False,
                indent=4
            )

        os.replace(
            temp_file,
            CONFIG_FILE
        )

    except Exception:
        pass


# =========================================================
# 系統匣圖示
# =========================================================

def create_tray_icon():

    if os.path.exists(
        ICON_FILE
    ):

        icon = QIcon(
            ICON_FILE
        )

        if not icon.isNull():

            return icon

    return QIcon()


# =========================================================
# Windows 通知註冊
# =========================================================

def setup_windows_notification_identity():
    """
    建立目前使用者的 Windows AppUserModelID 註冊資訊，
    讓 Toast 通知中心顯示「菲比提醒」而不是 Windows PowerShell。

    Windows 對未封裝桌面程式的通知需要一個 AUMID；
    新版 Windows 也支援以 AppUserModelId 註冊應用程式資訊。
    """
    if sys.platform != "win32":
        return

    try:
        # 設定目前 Python / EXE 程序的 AppUserModelID。
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            ctypes.c_wchar_p(WINDOWS_AUMID)
        )
    except Exception:
        pass

    try:
        key_path = (
            "Software\\Classes\\AppUserModelId\\"
            + WINDOWS_AUMID
        )

        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            key_path
        ) as key:
            winreg.SetValueEx(
                key,
                "DisplayName",
                0,
                winreg.REG_SZ,
                APP_NAME
            )

            # 圖示不是通知來源名稱的必要條件；
            # 有有效圖示時 Windows 會在通知中心使用它。
            if os.path.exists(ICON_FILE):
                winreg.SetValueEx(
                    key,
                    "IconUri",
                    0,
                    winreg.REG_SZ,
                    os.path.abspath(ICON_FILE)
                )
    except Exception:
        pass


def show_windows_toast(
    title,
    message,
    notification_tag=None
):
    """使用 Windows Runtime Toast，並保留可供之後移除的事件標籤。"""
    if sys.platform != "win32":
        return False

    try:
        def xml_escape(value):
            return (
                str(value)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;")
            )

        safe_title = xml_escape(title)
        safe_message = xml_escape(message)
        tag = str(notification_tag or uuid.uuid4().hex)
        safe_tag = xml_escape(tag)

        xml = (
            f"<toast launch='PhoebeReminder' tag='{safe_tag}'>"
            "<visual>"
            "<binding template='ToastGeneric'>"
            f"<text>{safe_title}</text>"
            f"<text>{safe_message}</text>"
            "</binding>"
            "</visual>"
            "</toast>"
        )

        import base64
        xml_b64 = base64.b64encode(
            xml.encode("utf-8")
        ).decode("ascii")

        ps = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$bytes = [Convert]::FromBase64String('{xml_b64}')
$xmlText = [Text.Encoding]::UTF8.GetString($bytes)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($xmlText)
$toast = New-Object Windows.UI.Notifications.ToastNotification($xml)
$toast.Tag = '{safe_tag}'
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{WINDOWS_AUMID}')
$notifier.Show($toast)
"""

        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-ExecutionPolicy", "Bypass", "-Command", ps],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        return True
    except Exception:
        return False


def remove_windows_toast(notification_tag):
    """從 Windows 通知中心移除指定事件的提醒通知。"""
    if sys.platform != "win32":
        return False

    try:
        tag = str(notification_tag or "")
        if not tag:
            return False

        ps = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$history = [Windows.UI.Notifications.ToastNotificationManager]::History
$history.Remove('{tag}', '', '{WINDOWS_AUMID}')
"""

        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
             "-ExecutionPolicy", "Bypass", "-Command", ps],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        return True
    except Exception:
        return False


# =========================================================
# 提醒時間視窗
# =========================================================

class ReminderDialog(
    QDialog
):

    def __init__(
        self,
        current_time,
        parent=None
    ):

        super().__init__(
            parent
        )

        self.setWindowTitle(
            "設定提醒時間"
        )

        self.setFixedWidth(
            300
        )

        layout = QVBoxLayout(
            self
        )

        label = QLabel(
            "設定這個事件的提醒時間"
        )

        label.setFont(
            QFont(
                FONT_NAME,
                11
            )
        )

        layout.addWidget(
            label
        )

        row = QHBoxLayout()

        time_label = QLabel(
            "提醒時間："
        )

        self.time_edit = QTimeEdit()

        self.time_edit.setDisplayFormat(
            "HH:mm"
        )

        safe = safe_time_string(
            current_time
        )

        hour, minute = map(
            int,
            safe.split(":")
        )

        self.time_edit.setTime(
            QTime(
                hour,
                minute
            )
        )

        # 讓提醒時間欄位支援 Enter 直接確定
        self.time_edit.installEventFilter(self)

        row.addWidget(
            time_label
        )

        row.addWidget(
            self.time_edit
        )

        layout.addLayout(
            row
        )

        buttons = QHBoxLayout()

        buttons.addStretch()

        cancel = QPushButton(
            "取消"
        )

        ok = QPushButton(
            "確定"
        )
        ok.setDefault(True)
        ok.setAutoDefault(True)

        cancel.clicked.connect(
            self.reject
        )

        ok.clicked.connect(
            self.accept
        )

        buttons.addWidget(
            cancel
        )

        buttons.addWidget(
            ok
        )

        layout.addLayout(
            buttons
        )

        self.setStyleSheet(
            """
            QDialog {
                background: #252525;
                color: white;
            }

            QLabel {
                color: white;
            }

            QTimeEdit {
                background: #303030;
                color: white;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 5px;
            }

            QPushButton {
                background: #454545;
                color: white;
                border: 1px solid #666;
                border-radius: 5px;
                padding: 6px 15px;
            }

            QPushButton:hover {
                background: #5a5a5a;
            }
            """
        )

    def eventFilter(
        self,
        watched,
        event
    ):
        if (
            watched is self.time_edit
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter
            )
        ):
            self.accept()
            return True

        return super().eventFilter(
            watched,
            event
        )

    def keyPressEvent(
        self,
        event
    ):
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter
        ):
            self.accept()
            return

        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return

        super().keyPressEvent(event)

    def get_time(
        self
    ):

        return (
            self.time_edit
            .time()
            .toString(
                "HH:mm"
            )
        )


# =========================================================
# 主視窗
# =========================================================

class DailyWidget(
    QWidget
):

    def __init__(self):

        super().__init__()

        # =================================================
        # 視窗
        # =================================================

        self.setWindowTitle(
            APP_NAME
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True
        )

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            |
            Qt.WindowType.Tool
        )

        self.setMouseTracking(
            True
        )

        # =================================================
        # Config
        # =================================================

        config = load_config()

        self.resize(
            config["width"],
            config["height"]
        )

        self.setMinimumSize(
            MIN_WIDTH,
            MIN_HEIGHT
        )

        if (
            config["x"] is None
            or
            config["y"] is None
        ):

            self.center_on_desktop()

        else:

            self.move(
                config["x"],
                config["y"]
            )

            self.ensure_visible()

        # =================================================
        # Data
        # =================================================

        data = load_data()

        self.tasks = data[
            "tasks"
        ]

        self.reminders_enabled = (
            data[
                "reminders_enabled"
            ]
        )

        self.last_reset_date = (
            data[
                "last_reset_date"
            ]
        )

        # =================================================
        # 舊資料修正
        # =================================================

        changed = False

        for task in self.tasks:

            if (
                "reminder_enabled"
                not in task
            ):

                task[
                    "reminder_enabled"
                ] = True

                changed = True

            if not task.get(
                "reminder_time"
            ):

                task[
                    "reminder_time"
                ] = DEFAULT_REMINDER_TIME

                changed = True

        if changed:

            self.save_all()

        # =================================================
        # 狀態
        # =================================================

        self.selected_index = -1

        self.edit_box = None

        self.edit_index = -1

        self.input_box = None

        # =================================================
        # ★ 提醒模式
        # =================================================

        self.reminder_mode = False

        # 20 秒倒數 Timer
        self.reminder_mode_timer = QTimer(
            self
        )

        self.reminder_mode_timer.setSingleShot(
            True
        )

        self.reminder_mode_timer.timeout.connect(
            self.leave_reminder_mode
        )

        # =================================================
        # Hover
        # =================================================

        self.add_button_hover = False

        self.reminder_button_hover = False

        # =================================================
        # 視窗拖曳
        # =================================================

        self.window_drag_candidate = False

        self.window_dragging = False

        self.drag_start_global = QPoint()

        self.drag_window_offset = QPoint()

        # =================================================
        # 事件拖曳
        # =================================================

        self.task_drag_candidate = False

        self.task_dragging = False

        self.task_drag_index = -1

        self.task_drag_start_global = QPoint()

        # =================================================
        # Resize
        # =================================================

        self.resizing = False

        self.resize_start_global = QPoint()

        self.resize_start_size = QSize()

        # =================================================
        # Context Menu
        # =================================================

        self.context_menu_open = False

        # =================================================
        # 系統匣
        # =================================================

        self.create_system_tray()

        # =================================================
        # Timer
        # =================================================

        self.timer = QTimer(
            self
        )

        self.timer.timeout.connect(
            self.timer_tick
        )

        self.timer.start(
            1000
        )

        # =====================================================
        # Windows 全域滑鼠左鍵監聽
        # =====================================================

        self._global_left_button_down = False

        self.global_mouse_timer = QTimer(self)

        self.global_mouse_timer.timeout.connect(
            self.check_global_mouse_click
        )

        self.global_mouse_timer.start(30)

        # =================================================
        # 每日
        # =================================================

        self.check_new_day(
            force=True
        )

        self.adjust_height_to_tasks(
            save=False
        )

        self.update()


    # =====================================================
    # Timer
    # =====================================================

    def timer_tick(
        self
    ):

        self.check_new_day()

        self.check_reminders()

        self.update()


    # =====================================================
    # 桌面置中
    # =====================================================

    def center_on_desktop(
        self
    ):

        screen = (
            QApplication.primaryScreen()
        )

        if screen is None:
            return

        rect = (
            screen.availableGeometry()
        )

        self.move(
            rect.x()
            +
            (
                rect.width()
                -
                self.width()
            )
            // 2,

            rect.y()
            +
            (
                rect.height()
                -
                self.height()
            )
            // 2
        )


    # =====================================================
    # 確保可見
    # =====================================================

    def ensure_visible(
        self
    ):

        screen = QApplication.screenAt(
            self.frameGeometry().center()
        )

        if screen is None:

            screen = (
                QApplication.primaryScreen()
            )

        if screen is None:
            return

        available = (
            screen.availableGeometry()
        )

        rect = self.frameGeometry()

        x = rect.x()
        y = rect.y()

        if rect.right() < (
            available.left()
            +
            50
        ):

            x = (
                available.left()
                +
                50
            )

        elif rect.left() > (
            available.right()
            -
            50
        ):

            x = (
                available.right()
                -
                self.width()
                +
                50
            )

        if rect.bottom() < (
            available.top()
            +
            50
        ):

            y = (
                available.top()
                +
                50
            )

        elif rect.top() > (
            available.bottom()
            -
            50
        ):

            y = (
                available.bottom()
                -
                self.height()
                +
                50
            )

        self.move(
            x,
            y
        )


    # =====================================================
    # 動態高度
    # =====================================================

    def calculate_height(
        self
    ):

        if not self.tasks:

            return MIN_HEIGHT

        height = (
            TASK_START_Y
            +
            len(self.tasks)
            *
            TASK_HEIGHT
            +
            BOTTOM_PADDING
        )

        return max(
            MIN_HEIGHT,
            min(
                MAX_HEIGHT,
                height
            )
        )


    def adjust_height_to_tasks(
        self,
        save=True
    ):

        height = (
            self.calculate_height()
        )

        if self.height() != height:

            self.resize(
                self.width(),
                height
            )

        if save:

            save_config(
                self
            )

        self.update()


    # =====================================================
    # 系統匣
    #
    # ★ 顯示／隱藏只有一個按鈕
    # =====================================================

    def create_system_tray(
        self
    ):

        self.tray = (
            QSystemTrayIcon(
                self
            )
        )

        self.tray.setIcon(
            create_tray_icon()
        )

        self.tray.setToolTip(
            APP_NAME
        )

        menu = QMenu()

        menu.setStyleSheet(
            """
            QMenu {
                background: #252525;
                color: white;
                border: 1px solid #444;
                padding: 5px;
            }

            QMenu::item {
                padding: 8px 45px 8px 20px;
            }

            QMenu::item:selected {
                background: #404040;
            }

            QMenu::separator {
                height: 1px;
                background: #444;
                margin: 5px 10px;
            }
            """
        )

        self.tray_toggle_action = QAction(
            "隱藏菲比提醒",
            self
        )

        self.tray_toggle_action.triggered.connect(
            self.toggle_widget_visibility
        )

        menu.addAction(
            self.tray_toggle_action
        )

        menu.addSeparator()

        exit_action = QAction(
            "關閉程式",
            self
        )

        exit_action.triggered.connect(
            self.exit_application
        )

        menu.addAction(
            exit_action
        )

        self.tray.setContextMenu(
            menu
        )

        self.tray.activated.connect(
            self.tray_activated
        )

        self.tray.show()


    # =====================================================
    # 系統匣切換
    # =====================================================

    def toggle_widget_visibility(
        self
    ):

        if self.isVisible():

            self.hide_to_tray()

        else:

            self.show_widget()


    def tray_activated(
        self,
        reason
    ):

        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick
        ):

            self.show_widget()


    def show_widget(
        self
    ):

        self.show()

        self.raise_()

        self.activateWindow()

        self.tray_toggle_action.setText(
            "隱藏菲比提醒"
        )


    def hide_to_tray(
        self
    ):

        self.close_edit(
            save=True
        )

        self.close_input()

        self.stop_all_mouse_operation()

        self.save_all()

        self.hide()

        self.tray_toggle_action.setText(
            "顯示菲比提醒"
        )


    def exit_application(
        self
    ):

        self.close_edit(
            save=True
        )

        self.close_input()

        self.save_all()

        self.tray.hide()

        QApplication.quit()


    # =====================================================
    # 啟用
    # =====================================================

    def activate_widget(
        self
    ):

        if not self.isVisible():
            return

        self.raise_()

        self.activateWindow()


    # =====================================================
    # 日期
    # =====================================================

    def get_date_text(
        self
    ):

        today = date.today()

        weekdays = [
            "星期一",
            "星期二",
            "星期三",
            "星期四",
            "星期五",
            "星期六",
            "星期日"
        ]

        return (
            f"{today.strftime('%Y/%m/%d')} "
            f"{weekdays[today.weekday()]}"
        )


    # =====================================================
    # 時間
    # =====================================================

    def get_time_text(
        self
    ):

        return datetime.now().strftime(
            "%H:%M:%S"
        )


    # =====================================================
    # 提醒模式計時器
    # =====================================================

    def restart_reminder_mode_timer(
        self
    ):

        if not self.reminder_mode:
            return

        self.reminder_mode_timer.start(
            20_000
        )


    def enter_reminder_mode(
        self
    ):

        self.close_edit(
            save=True
        )

        self.close_input()

        self.stop_all_mouse_operation()

        self.selected_index = -1

        self.reminder_mode = True

        # ★ 進入後開始 20 秒
        self.restart_reminder_mode_timer()

        self.update()


    def leave_reminder_mode(
        self
    ):

        self.reminder_mode_timer.stop()

        self.reminder_mode = False

        self.selected_index = -1

        self.stop_all_mouse_operation()

        self.update()


    def toggle_reminder_mode(
        self
    ):

        if self.reminder_mode:

            self.leave_reminder_mode()

        else:

            self.enter_reminder_mode()


    # =====================================================
    # 按鈕 RECT
    # =====================================================

    def get_reminder_button_rect(
        self
    ):

        add_rect = (
            self.get_add_button_rect()
        )

        return QRect(
            add_rect.x()
            -
            REMINDER_BUTTON_WIDTH
            -
            BUTTON_GAP,

            add_rect.y(),

            REMINDER_BUTTON_WIDTH,

            REMINDER_BUTTON_HEIGHT
        )


    def get_add_button_rect(
        self
    ):

        return QRect(
            self.width()
            -
            ADD_BUTTON_WIDTH
            -
            BUTTON_RIGHT_MARGIN,

            34,

            ADD_BUTTON_WIDTH,

            ADD_BUTTON_HEIGHT
        )


    # =====================================================
    # Checkbox Hit
    #
    # ★ 整個右側區域
    # =====================================================

    def get_checkbox_index(
        self,
        pos
    ):

        left = (
            self.width()
            -
            CHECKBOX_HIT_WIDTH
        )

        for index in range(
            len(self.tasks)
        ):

            top = (
                TASK_START_Y
                +
                index
                *
                TASK_HEIGHT
            )

            rect = QRect(
                left,
                top,
                CHECKBOX_HIT_WIDTH,
                TASK_HEIGHT
            )

            if rect.contains(
                pos
            ):

                return index

        return -1


    # =====================================================
    # Switch
    # =====================================================

    def get_switch_rect(
        self,
        index
    ):

        top = (
            TASK_START_Y
            +
            index
            *
            TASK_HEIGHT
        )

        return QRect(
            self.width()
            -
            SWITCH_WIDTH
            -
            SWITCH_RIGHT_MARGIN,

            top
            +
            (
                TASK_HEIGHT
                -
                SWITCH_HEIGHT
            )
            //
            2,

            SWITCH_WIDTH,

            SWITCH_HEIGHT
        )


    # =====================================================
    # Switch 整個可點區域
    # =====================================================

    def get_switch_hit_rect(
        self,
        index
    ):

        top = (
            TASK_START_Y
            +
            index
            *
            TASK_HEIGHT
        )

        return QRect(
            self.width()
            -
            85,

            top,

            85,

            TASK_HEIGHT
        )


    # =====================================================
    # Reminder Time
    # =====================================================

    def get_reminder_time_rect(
        self,
        index
    ):

        top = (
            TASK_START_Y
            +
            index
            *
            TASK_HEIGHT
        )

        return QRect(
            8,
            top + 7,
            REMINDER_TIME_WIDTH,
            TASK_HEIGHT - 14
        )


    # =====================================================
    # Task Rect
    # =====================================================

    def get_task_rect(
        self,
        index
    ):

        if not (
            0 <= index < len(self.tasks)
        ):

            return QRect()

        top = (
            TASK_START_Y
            +
            index
            *
            TASK_HEIGHT
        )

        return QRect(
            7,
            top - 3,
            self.width() - 14,
            TASK_HEIGHT - 5
        )


    def get_task_index(
        self,
        pos
    ):

        for index in range(
            len(self.tasks)
        ):

            if self.get_task_rect(
                index
            ).contains(pos):

                return index

        return -1


    # =====================================================
    # 全部提醒
    #
    # ★ 同步每個事件
    # =====================================================

    def toggle_all_reminders(
        self
    ):

        self.reminders_enabled = (
            not self.reminders_enabled
        )

        for task in self.tasks:

            task[
                "reminder_enabled"
            ] = (
                self.reminders_enabled
            )

            if not task.get(
                "reminder_time"
            ):

                task[
                    "reminder_time"
                ] = DEFAULT_REMINDER_TIME

        self.save_all()

        self.restart_reminder_mode_timer()

        self.update()


    # =====================================================
    # 單一提醒
    # =====================================================

    def toggle_task_reminder(
        self,
        index
    ):

        if not (
            0 <= index < len(self.tasks)
        ):

            return

        task = self.tasks[index]

        task[
            "reminder_enabled"
        ] = not bool(
            task.get(
                "reminder_enabled",
                True
            )
        )

        self.save_all()

        self.restart_reminder_mode_timer()

        self.update()


    # =====================================================
    # 修改提醒時間
    # =====================================================

    def edit_reminder_time(
        self,
        index
    ):

        if not (
            0 <= index < len(self.tasks)
        ):

            return

        self.restart_reminder_mode_timer()

        task = self.tasks[index]

        dialog = ReminderDialog(
            task.get(
                "reminder_time",
                DEFAULT_REMINDER_TIME
            ),
            self
        )

        if (
            dialog.exec()
            ==
            QDialog.DialogCode.Accepted
        ):

            task[
                "reminder_time"
            ] = dialog.get_time()

            task[
                "last_reminded_date"
            ] = None

            self.save_all()

        # 操作完成後重新計時
        self.restart_reminder_mode_timer()

        self.update()


    # =====================================================
    # Checkbox
    # =====================================================

    def toggle_checkbox(
        self,
        index
    ):

        if not (
            0 <= index < len(self.tasks)
        ):

            return

        task = self.tasks[index]

        task[
            "completed"
        ] = not bool(
            task.get(
                "completed",
                False
            )
        )

        # 完成事件後，立即從 Windows 通知中心移除這個事件的提醒。
        if task["completed"]:
            remove_windows_toast(
                task.get(
                    "notification_tag"
                )
            )

        self.selected_index = -1

        self.stop_all_mouse_operation()

        self.save_all()

        self.update()


    # =====================================================
    # 新增
    # =====================================================

    def start_add_task(
        self
    ):

        self.activate_widget()

        self.close_edit(
            save=True
        )

        self.close_input()

        self.input_box = QLineEdit(
            self
        )

        self.input_box.setFont(
            QFont(
                FONT_NAME,
                12
            )
        )

        self.input_box.setStyleSheet(
            """
            QLineEdit {
                background: rgba(25,25,25,245);
                color: white;
                border: 1px solid rgba(100,165,255,245);
                border-radius: 6px;
                padding: 5px 8px;
            }
            """
        )

        self.input_box.setGeometry(
            10,
            TASK_START_Y - 3,
            max(
                180,
                self.width() - 80
            ),
            34
        )

        self.input_box.returnPressed.connect(
            self.finish_add
        )

        self.input_box.show()

        self.input_box.setFocus()


    def finish_add(
        self
    ):

        if self.input_box is None:
            return

        text = (
            self.input_box
            .text()
            .strip()
        )

        if text:

            self.tasks.append(
                {
                    "text":
                        text,

                    "completed":
                        False,

                    # ★ 預設提醒開啟
                    "reminder_enabled":
                        True,

                    # ★ 預設 23:00
                    "reminder_time":
                        DEFAULT_REMINDER_TIME,

                    "last_reminded_date":
                        None,

                    "notification_tag":
                        uuid.uuid4().hex
                }
            )

            self.save_all()

            self.adjust_height_to_tasks()

        self.close_input()

        self.update()


    def close_input(
        self
    ):

        if self.input_box is not None:

            box = self.input_box

            self.input_box = None

            box.deleteLater()

            self.update()


    # =====================================================
    # 編輯
    # =====================================================

    def start_edit(
        self,
        index
    ):

        if not (
            0 <= index < len(self.tasks)
        ):

            return

        self.activate_widget()

        self.close_input()

        self.close_edit(
            save=True
        )

        self.edit_index = index

        self.edit_box = QLineEdit(
            self
        )

        self.edit_box.setText(
            self.tasks[index][
                "text"
            ]
        )

        self.edit_box.setFont(
            QFont(
                FONT_NAME,
                13
            )
        )

        self.edit_box.setStyleSheet(
            """
            QLineEdit {
                background: rgba(25,25,25,245);
                color: white;
                border: 1px solid rgba(100,165,255,245);
                border-radius: 6px;
                padding: 5px 8px;
            }
            """
        )

        self.position_edit_box()

        self.edit_box.returnPressed.connect(
            self.save_edit
        )

        self.edit_box.show()

        self.edit_box.setFocus()

        self.edit_box.selectAll()


    def position_edit_box(
        self
    ):

        if self.edit_box is None:
            return

        if not (
            0 <= self.edit_index < len(self.tasks)
        ):

            return

        top = (
            TASK_START_Y
            +
            self.edit_index
            *
            TASK_HEIGHT
        )

        left = (
            78
            if self.reminder_mode
            else 10
        )

        self.edit_box.setGeometry(
            left,
            top + 5,
            self.width()
            -
            left
            -
            75,
            TASK_HEIGHT - 10
        )


    def save_edit(
        self
    ):

        self.close_edit(
            save=True
        )


    def close_edit(
        self,
        save=True
    ):

        if self.edit_box is None:

            self.edit_index = -1

            return

        box = self.edit_box

        index = self.edit_index

        self.edit_box = None

        if save:

            text = (
                box.text()
                .strip()
            )

            if (
                text
                and
                0 <= index < len(self.tasks)
            ):

                self.tasks[index][
                    "text"
                ] = text

                self.save_all()

        box.deleteLater()

        self.edit_index = -1

        self.update()


    # =====================================================
    # 刪除
    # =====================================================

    def delete_task(
        self,
        index
    ):

        if not (
            0 <= index < len(self.tasks)
        ):

            return

        if (
            self.edit_index
            ==
            index
        ):

            self.close_edit(
                save=False
            )

        del self.tasks[
            index
        ]

        if (
            self.selected_index
            ==
            index
        ):

            self.selected_index = -1

        elif (
            self.selected_index
            >
            index
        ):

            self.selected_index -= 1

        self.save_all()

        self.adjust_height_to_tasks()

        self.update()


    # =====================================================
    # 右鍵選單
    # =====================================================

    def show_task_menu(
        self,
        global_pos,
        index
    ):

        if not (
            0 <= index < len(self.tasks)
        ):

            return

        self.context_menu_open = True

        menu = QMenu()

        menu.setStyleSheet(
            """
            QMenu {
                background: #252525;
                color: white;
                border: 1px solid #444;
                padding: 5px;
            }

            QMenu::item {
                padding: 8px 45px 8px 20px;
            }

            QMenu::item:selected {
                background: #404040;
            }
            """
        )

        edit_action = menu.addAction(
            "編輯"
        )

        delete_action = menu.addAction(
            "刪除"
        )

        action = menu.exec(
            global_pos
        )

        self.context_menu_open = False

        if action == edit_action:

            self.start_edit(
                index
            )

        elif action == delete_action:

            self.delete_task(
                index
            )


    # =====================================================
    # 每日重置
    #
    # ★ 每天 00:00 後第一次檢查
    # ★ 只重置勾選狀態
    # ★ 不刪除事件
    # ★ 不改變事件順序
    # ★ 不改變提醒設定
    # =====================================================

    def check_new_day(
        self,
        force=False
    ):

        now = datetime.now()

        today = (
            now.date()
            .isoformat()
        )

        # =================================================
        # 今天已經重置過
        # =================================================

        if (
            self.last_reset_date
            ==
            today
        ):

            return

        # =================================================
        # 新的一天
        #
        # 不再限制 12:00
        # 只要日期變了就重置
        # =================================================

        for task in self.tasks:

            # 重置完成狀態
            task[
                "completed"
            ] = False

            # 重置今日提醒紀錄
            task[
                "last_reminded_date"
            ] = None

        # =================================================
        # 記錄今天已經重置
        # =================================================

        self.last_reset_date = today

        # =================================================
        # 儲存
        # =================================================

        self.save_all()

        self.update()
    
    # =====================================================
    # 提醒檢查
    # =====================================================

    def check_reminders(
        self
    ):
        # 全域提醒開關關閉時不檢查
        now = datetime.now()
        today = now.date().isoformat()

        # 以分鐘判斷，避免 QTimer 在整分附近剛好跨秒造成漏提醒。
        current_minutes = (
            now.hour * 60
            + now.minute
        )

        changed = False

        for task in self.tasks:
            if not task.get(
                "reminder_enabled",
                True
            ):
                continue

            if task.get(
                "completed",
                False
            ):
                continue

            # 每個事件每天只提醒一次。
            if task.get(
                "last_reminded_date"
            ) == today:
                continue

            reminder_time = safe_time_string(
                task.get(
                    "reminder_time",
                    DEFAULT_REMINDER_TIME
                )
            )

            try:
                hour, minute = map(
                    int,
                    reminder_time.split(":")
                )
            except (ValueError, TypeError):
                continue

            reminder_minutes = (
                hour * 60
                + minute
            )

            # 尚未到提醒時間。
            if current_minutes < reminder_minutes:
                continue

            self.show_reminder_notification(
                task.get(
                    "text",
                    ""
                ),
                task.get(
                    "notification_tag"
                )
            )

            task[
                "last_reminded_date"
            ] = today

            changed = True

        if changed:
            self.save_all()

    # =====================================================
    # 通知
    # =====================================================

    def show_reminder_notification(
        self,
        task_name,
        notification_tag=None
    ):

        title = "菲比提醒你"
        message = f"「{task_name}」尚未完成"

        # Windows 10 / 11：使用真正的 Windows Toast。
        # AUMID 已在程式啟動時註冊為「菲比提醒」，
        # 因此通知中心的來源名稱會顯示「菲比提醒」。
        if sys.platform == "win32":
            if show_windows_toast(
                title,
                message,
                notification_tag
            ):
                return

        # 非 Windows 或 Toast 失敗時使用 Qt 系統匣通知作為備援。
        try:
            if hasattr(self, "tray"):
                self.tray.setVisible(True)
                self.tray.showMessage(
                    title,
                    message,
                    QSystemTrayIcon.MessageIcon.Information,
                    10000
                )
        except Exception:
            pass


    # =====================================================
    # Mouse Double Click
    #
    # ★ 雙擊事件名稱直接進入文字編輯
    # =====================================================

    def mouseDoubleClickEvent(
        self,
        event
    ):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return

        pos = event.position().toPoint()

        # 編輯框本身不需要再次處理。
        if self.edit_box is not None:
            return

        # 上方按鈕與縮放區域不視為事件名稱。
        if (
            self.get_add_button_rect().contains(pos)
            or
            self.get_reminder_button_rect().contains(pos)
            or
            self.is_resize_area(pos)
        ):
            return

        index = self.get_task_index(pos)
        if index < 0:
            return

        # 提醒模式下：時間與右側開關區域不進入文字編輯。
        if self.reminder_mode:
            if (
                self.get_reminder_time_rect(index).contains(pos)
                or
                self.get_switch_hit_rect(index).contains(pos)
            ):
                return

            text_left = REMINDER_TIME_WIDTH + 17
            text_right = self.width() - 90
        else:
            # 一般模式下右側 72px 是勾選區，不進入文字編輯。
            text_left = TASK_TEXT_X
            text_right = self.width() - CHECKBOX_HIT_WIDTH

        text_rect = QRect(
            text_left,
            TASK_START_Y + index * TASK_HEIGHT,
            max(1, text_right - text_left),
            TASK_HEIGHT
        )

        if text_rect.contains(pos):
            self.selected_index = index
            self.start_edit(index)
            event.accept()
            return

        super().mouseDoubleClickEvent(event)


    # =====================================================
    # Mouse Press
    #
    # ★ 所有功能集中處理
    # =====================================================

    def mousePressEvent(
        self,
        event
    ):

        pos = (
            event.position()
            .toPoint()
        )

        global_pos = (
            event.globalPosition()
            .toPoint()
        )

        # =================================================
        # 右鍵
        # =================================================

        if (
            event.button()
            ==
            Qt.MouseButton.RightButton
        ):

            self.stop_all_mouse_operation()

            self.activate_widget()

            if self.input_box is not None:

                if not self.input_box.geometry().contains(
                    pos
                ):

                    self.close_input()

                    return

            index = (
                self.get_task_index(
                    pos
                )
            )

            if index >= 0:

                self.selected_index = index

                self.update()

                self.show_task_menu(
                    global_pos,
                    index
                )

            return

        # =================================================
        # 左鍵
        # =================================================

        if (
            event.button()
            !=
            Qt.MouseButton.LeftButton
        ):

            return

        self.activate_widget()

        # =================================================
        # 編輯框外
        # =================================================

        if self.edit_box is not None:

            if not self.edit_box.geometry().contains(
                pos
            ):

                # 點擊編輯框外：儲存後離開編輯模式，
                # 並繼續處理這次點擊。
                self.close_edit(
                    save=True
                )

        # =================================================
        # 新增輸入框
        # =================================================

        if self.input_box is not None:

            if not self.input_box.geometry().contains(
                pos
            ):

                self.finish_add()

                return

        # =================================================
        # ★ 提醒按鈕
        #
        # 最優先
        # =================================================

        reminder_rect = (
            self.get_reminder_button_rect()
        )

        if reminder_rect.contains(
            pos
        ):

            self.toggle_reminder_mode()

            return

        # =================================================
        # ★ 提醒模式
        # =================================================

        if self.reminder_mode:

            # ---------------------------------------------
            # 所有提醒按鈕
            # ---------------------------------------------

            add_rect = (
                self.get_add_button_rect()
            )

            if add_rect.contains(
                pos
            ):

                self.toggle_all_reminders()

                return

            # ---------------------------------------------
            # 提醒時間
            # ---------------------------------------------

            for index in range(
                len(self.tasks)
            ):

                if (
                    self.get_reminder_time_rect(
                        index
                    )
                    .contains(
                        pos
                    )
                ):

                    self.edit_reminder_time(
                        index
                    )

                    return

            # ---------------------------------------------
            # Switch
            # ---------------------------------------------

            for index in range(
                len(self.tasks)
            ):

                if (
                    self.get_switch_hit_rect(
                        index
                    )
                    .contains(
                        pos
                    )
                ):

                    self.toggle_task_reminder(
                        index
                    )

                    return

            # ---------------------------------------------
            # 提醒模式中的其他點擊
            #
            # 任何動作都重新計時
            # ---------------------------------------------

            self.restart_reminder_mode_timer()

        # =================================================
        # 一般模式
        # =================================================

        else:

            # ---------------------------------------------
            # Checkbox
            #
            # 整個右側 72px
            # ---------------------------------------------

            checkbox_index = (
                self.get_checkbox_index(
                    pos
                )
            )

            if checkbox_index >= 0:

                self.toggle_checkbox(
                    checkbox_index
                )

                return

            # ---------------------------------------------
            # 新增
            # ---------------------------------------------

            add_rect = (
                self.get_add_button_rect()
            )

            if add_rect.contains(
                pos
            ):

                self.start_add_task()

                return

        # =================================================
        # Resize
        # =================================================

        if self.is_resize_area(
            pos
        ):

            self.resizing = True

            self.resize_start_global = (
                global_pos
            )

            self.resize_start_size = (
                self.size()
            )

            return

        # =================================================
        # Task
        # =================================================

        index = (
            self.get_task_index(
                pos
            )
        )

        if index >= 0:

            self.selected_index = index

            self.task_drag_candidate = True

            self.task_dragging = False

            self.task_drag_index = index

            self.task_drag_start_global = (
                global_pos
            )

            self.update()

            return

        # =================================================
        # 點擊桌布／空白區域
        # → 取消目前事件選取
        # =================================================
        
        task_index = self.get_task_index(pos)
        
        reminder_button = self.get_reminder_button_rect()
        add_button = self.get_add_button_rect()
        
        # 沒有點到事件
        if task_index < 0:
        
            # 也沒有點到上方功能按鈕
            if (
                not reminder_button.contains(pos)
                and
                not add_button.contains(pos)
            ):
        
                self.selected_index = -1
        
                self.stop_all_mouse_operation()
        
                self.update()
        
        # =================================================
        # Window Drag
        # =================================================
        
        self.window_drag_candidate = True
        
        self.window_dragging = False
        
        self.drag_start_global = global_pos
        
        self.drag_window_offset = (
            global_pos
            -
            self.frameGeometry().topLeft()
        )


    # =====================================================
    # Mouse Move
    # =====================================================

    def mouseMoveEvent(
        self,
        event
    ):

        pos = (
            event.position()
            .toPoint()
        )

        global_pos = (
            event.globalPosition()
            .toPoint()
        )

        # =================================================
        # Hover
        # =================================================

        old_add = (
            self.add_button_hover
        )

        old_reminder = (
            self.reminder_button_hover
        )

        self.add_button_hover = (
            self.get_add_button_rect()
            .contains(pos)
        )

        self.reminder_button_hover = (
            self.get_reminder_button_rect()
            .contains(pos)
        )

        if (
            old_add
            !=
            self.add_button_hover
            or
            old_reminder
            !=
            self.reminder_button_hover
        ):

            self.update()

        # =================================================
        # Resize
        # =================================================

        if self.resizing:

            if not (
                event.buttons()
                &
                Qt.MouseButton.LeftButton
            ):

                self.resizing = False

                self.save_all()

                return

            delta = (
                global_pos
                -
                self.resize_start_global
            )

            new_width = max(
                MIN_WIDTH,
                min(
                    MAX_WIDTH,
                    self.resize_start_size.width()
                    +
                    delta.x()
                )
            )

            # 高度仍由事件數量決定
            new_height = (
                self.calculate_height()
            )

            self.resize(
                new_width,
                new_height
            )

            return

        # =================================================
        # 事件拖曳
        # =================================================

        if (
            self.task_drag_candidate
            or
            self.task_dragging
        ):

            if not (
                event.buttons()
                &
                Qt.MouseButton.LeftButton
            ):

                self.finish_task_drag()

                return

            if self.task_drag_candidate:

                delta = (
                    global_pos
                    -
                    self.task_drag_start_global
                )

                if (
                    abs(delta.x())
                    >= DRAG_THRESHOLD
                    or
                    abs(delta.y())
                    >= DRAG_THRESHOLD
                ):

                    self.task_drag_candidate = False

                    self.task_dragging = True

            if self.task_dragging:

                self.update_task_drag(
                    global_pos
                )

            return

        # =================================================
        # 視窗拖曳
        # =================================================

        if self.window_drag_candidate:

            if not (
                event.buttons()
                &
                Qt.MouseButton.LeftButton
            ):

                self.window_drag_candidate = False

                return

            delta = (
                global_pos
                -
                self.drag_start_global
            )

            if (
                abs(delta.x())
                >= DRAG_THRESHOLD
                or
                abs(delta.y())
                >= DRAG_THRESHOLD
            ):

                self.window_drag_candidate = False

                self.window_dragging = True

        if self.window_dragging:

            if not (
                event.buttons()
                &
                Qt.MouseButton.LeftButton
            ):

                self.window_dragging = False

                self.save_all()

                return

            self.move(
                global_pos
                -
                self.drag_window_offset
            )

            return

        # =================================================
        # Cursor
        # =================================================

        if self.is_resize_area(
            pos
        ):

            self.setCursor(
                Qt.CursorShape.SizeFDiagCursor
            )

        else:

            self.setCursor(
                Qt.CursorShape.ArrowCursor
            )


    # =====================================================
    # Mouse Release
    # =====================================================

    def mouseReleaseEvent(
        self,
        event
    ):

        if (
            event.button()
            !=
            Qt.MouseButton.LeftButton
        ):

            return

        if self.resizing:

            self.resizing = False

            self.save_all()

            self.setCursor(
                Qt.CursorShape.ArrowCursor
            )

            return

        if self.task_dragging:

            self.finish_task_drag()

            return

        if self.task_drag_candidate:

            self.task_drag_candidate = False

            self.task_drag_index = -1

            self.update()

            return

        if self.window_dragging:

            self.window_dragging = False

            self.save_all()

            self.setCursor(
                Qt.CursorShape.ArrowCursor
            )

            return

        if self.window_drag_candidate:

            self.window_drag_candidate = False


    # =====================================================
    # Task Drag
    # =====================================================

    def update_task_drag(
        self,
        global_pos
    ):

        if not self.task_dragging:
            return

        if not self.tasks:
            return

        local_pos = (
            self.mapFromGlobal(
                global_pos
            )
        )

        new_index = int(
            (
                local_pos.y()
                -
                TASK_START_Y
                +
                TASK_HEIGHT // 2
            )
            //
            TASK_HEIGHT
        )

        new_index = max(
            0,
            min(
                len(self.tasks) - 1,
                new_index
            )
        )

        old_index = (
            self.task_drag_index
        )

        if (
            new_index
            ==
            old_index
        ):

            return

        task = self.tasks.pop(
            old_index
        )

        self.tasks.insert(
            new_index,
            task
        )

        self.task_drag_index = (
            new_index
        )

        self.selected_index = (
            new_index
        )

        self.save_all()

        self.update()


    def finish_task_drag(
        self
    ):

        self.task_drag_candidate = False

        self.task_dragging = False

        self.task_drag_index = -1

        self.save_all()

        self.update()


    # =====================================================
    # Resize 區域
    # =====================================================

    def is_resize_area(
        self,
        pos
    ):

        return (
            pos.x()
            >=
            self.width()
            -
            RESIZE_MARGIN
            and
            pos.y()
            >=
            self.height()
            -
            RESIZE_MARGIN
        )


    # =====================================================
    # 停止所有滑鼠操作
    # =====================================================

    def check_global_mouse_click(self):
        
        # 沒有選取事件時通常不用處理，
        # 但編輯框／新增輸入框存在時仍必須監聽，
        # 才能在點擊其他程式、桌布或工作列時自動關閉。
        if (
            self.selected_index < 0
            and self.edit_box is None
            and self.input_box is None
        ):
            return
    
        # 小工具隱藏時不用處理
        if not self.isVisible():
            return
    
        # 只處理 Windows
        if sys.platform != "win32":
            return
    
        try:
            # Windows VK_LBUTTON = 0x01
            state = ctypes.windll.user32.GetAsyncKeyState(0x01)
    
            left_button_down = bool(
                state & 0x8000
            )
    
        except Exception:
            return
    
        # 只抓左鍵「剛按下」的瞬間
        just_pressed = (
            left_button_down
            and
            not self._global_left_button_down
        )
    
        self._global_left_button_down = left_button_down
    
        if not just_pressed:
            return
    
        # Windows 全域滑鼠位置
        global_pos = QCursor.pos()
    
        # =================================================
        # 點擊小工具外部
        #
        # 包含：
        #   Windows 桌布
        #   其他程式
        #   檔案總管
        #   工作列
        # =================================================
    
        if not self.frameGeometry().contains(
            global_pos
        ):

            if self.edit_box is not None:
                self.close_edit(
                    save=True
                )

            if self.input_box is not None:
                self.finish_add()

            self.selected_index = -1

            self.stop_all_mouse_operation()

            self.update()

    def stop_all_mouse_operation(
        self
    ):

        self.window_drag_candidate = False

        self.window_dragging = False

        self.task_drag_candidate = False

        self.task_dragging = False

        self.task_drag_index = -1

        self.resizing = False

        self.setCursor(
            Qt.CursorShape.ArrowCursor
        )


    # =====================================================
    # Paint
    # =====================================================

    def paintEvent(
        self,
        event
    ):

        painter = QPainter(
            self
        )

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True
        )

        painter.setRenderHint(
            QPainter.RenderHint.TextAntialiasing,
            True
        )

        painter.fillRect(
            self.rect(),
            Qt.GlobalColor.transparent
        )

        # =================================================
        # Title
        # =================================================

        title_font = QFont(
            FONT_NAME,
            19
        )

        title_font.setBold(
            True
        )

        painter.setFont(
            title_font
        )

        painter.setPen(
            QPen(
                TITLE_SHADOW
            )
        )

        painter.drawText(
            TITLE_X + 1,
            TITLE_Y + 1,
            APP_NAME
        )

        painter.setPen(
            QPen(
                TITLE_COLOR
            )
        )

        painter.drawText(
            TITLE_X,
            TITLE_Y,
            APP_NAME
        )

        # =================================================
        # 日期
        # =================================================

        date_font = QFont(
            FONT_NAME,
            11
        )

        date_font.setBold(
            True
        )

        painter.setFont(
            date_font
        )

        painter.setPen(
            QPen(
                DATE_SHADOW
            )
        )

        painter.drawText(
            DATE_X + 1,
            DATE_Y + 1,
            self.get_date_text()
        )

        painter.setPen(
            QPen(
                DATE_COLOR
            )
        )

        painter.drawText(
            DATE_X,
            DATE_Y,
            self.get_date_text()
        )

        # =================================================
        # 時間
        # =================================================

        time_font = QFont(
            FONT_NAME,
            10
        )

        time_font.setBold(
            True
        )

        painter.setFont(
            time_font
        )

        painter.setPen(
            QPen(
                TIME_SHADOW
            )
        )

        painter.drawText(
            TIME_X + 1,
            TIME_Y + 1,
            self.get_time_text()
        )

        painter.setPen(
            QPen(
                TIME_COLOR
            )
        )

        painter.drawText(
            TIME_X,
            TIME_Y,
            self.get_time_text()
        )

        # =================================================
        # Reminder Button
        # =================================================

        reminder_rect = (
            self.get_reminder_button_rect()
        )

        if self.reminder_mode:

            reminder_color = (
                REMINDER_ACTIVE_COLOR
            )

        elif self.reminder_button_hover:

            reminder_color = (
                BUTTON_HOVER_COLOR
            )

        else:

            reminder_color = (
                REMINDER_COLOR
            )

        painter.setBrush(
            reminder_color
        )

        painter.setPen(
            Qt.PenStyle.NoPen
        )

        painter.drawRoundedRect(
            reminder_rect,
            6,
            6
        )

        button_font = QFont(
            FONT_NAME,
            9
        )

        button_font.setBold(
            True
        )

        painter.setFont(
            button_font
        )

        painter.setPen(
            QPen(
                WHITE
            )
        )

        painter.drawText(
            reminder_rect,
            Qt.AlignmentFlag.AlignCenter,
            "提醒"
        )

        # =================================================
        # Add / All Reminder
        # =================================================

        add_rect = (
            self.get_add_button_rect()
        )

        if self.reminder_mode:

            if self.reminders_enabled:

                add_text = (
                    "關閉所有提醒"
                )

            else:

                add_text = (
                    "開啟所有提醒"
                )

        else:

            add_text = (
                "＋ 新增"
            )

        add_color = (
            BUTTON_HOVER_COLOR
            if self.add_button_hover
            else BUTTON_COLOR
        )

        painter.setBrush(
            add_color
        )

        painter.setPen(
            Qt.PenStyle.NoPen
        )

        painter.drawRoundedRect(
            add_rect,
            6,
            6
        )

        painter.setPen(
            QPen(
                WHITE
            )
        )

        painter.drawText(
            add_rect,
            Qt.AlignmentFlag.AlignCenter,
            add_text
        )

        # =================================================
        # Tasks
        # =================================================

        for index, task in enumerate(
            self.tasks
        ):

            self.draw_task(
                painter,
                index,
                task
            )

        # =================================================
        # Empty
        # =================================================

        if not self.tasks:

            painter.setFont(
                QFont(
                    FONT_NAME,
                    10
                )
            )

            painter.setPen(
                QPen(
                    QColor(
                        225,
                        230,
                        240,
                        255
                    )
                )
            )

            painter.drawText(
                16,
                TASK_START_Y + 30,
                "點擊「＋ 新增」建立事件"
            )

        painter.end()


    # =====================================================
    # Draw Task
    # =====================================================

    def draw_task(
        self,
        painter,
        index,
        task
    ):

        top = (
            TASK_START_Y
            +
            index
            *
            TASK_HEIGHT
        )

        # =================================================
        # Selected
        # =================================================

        if (
            index
            ==
            self.selected_index
        ):

            selected_rect = QRect(
                7,
                top - 3,
                self.width() - 14,
                TASK_HEIGHT - 5
            )

            painter.setBrush(
                SELECTED_BACKGROUND
            )

            painter.setPen(
                QPen(
                    SELECTED_BORDER
                )
            )

            painter.drawRoundedRect(
                selected_rect,
                7,
                7
            )

        # =================================================
        # Reminder Mode
        # =================================================

        if self.reminder_mode:

            # ---------------------------------------------
            # 時間
            # ---------------------------------------------

            time_rect = (
                self.get_reminder_time_rect(
                    index
                )
            )

            painter.setBrush(
                QColor(
                    255,
                    255,
                    255,
                    20
                )
            )

            painter.setPen(
                QPen(
                    QColor(
                        255,
                        255,
                        255,
                        90
                    )
                )
            )

            painter.drawRoundedRect(
                time_rect,
                5,
                5
            )

            time_font = QFont(
                FONT_NAME,
                9
            )

            time_font.setBold(
                True
            )

            painter.setFont(
                time_font
            )

            painter.setPen(
                QPen(
                    WHITE
                )
            )

            painter.drawText(
                time_rect,
                Qt.AlignmentFlag.AlignCenter,
                safe_time_string(
                    task.get(
                        "reminder_time",
                        DEFAULT_REMINDER_TIME
                    )
                )
            )

            text_left = (
                REMINDER_TIME_WIDTH
                +
                17
            )

        else:

            text_left = (
                TASK_TEXT_X
            )

        # =================================================
        # Event Text
        #
        # ★ 不管完成與否都保持白色
        # =================================================

        text = str(
            task.get(
                "text",
                ""
            )
        )

        font = QFont(
            FONT_NAME,
            13
        )

        font.setBold(
            True
        )

        painter.setFont(
            font
        )

        if self.reminder_mode:

            text_width = (
                self.width()
                -
                text_left
                -
                90
            )

        else:

            text_width = (
                self.width()
                -
                text_left
                -
                88
            )

        text_rect = QRect(
            text_left,
            top,
            max(
                50,
                text_width
            ),
            TASK_HEIGHT
        )

        painter.setPen(
            QPen(
                TASK_SHADOW
            )
        )

        painter.drawText(
            text_rect.translated(
                1,
                1
            ),
            Qt.AlignmentFlag.AlignVCenter,
            text
        )

        painter.setPen(
            QPen(
                TASK_COLOR
            )
        )

        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter,
            text
        )

        # =================================================
        # Normal Checkbox
        # =================================================

        if not self.reminder_mode:

            # ★ 只有這個區域畫極低透明度
            # ★ 其他地方完全透明
            hit_rect = QRect(
                self.width()
                -
                CHECKBOX_HIT_WIDTH,

                top,

                CHECKBOX_HIT_WIDTH,

                TASK_HEIGHT
            )

            painter.fillRect(
                hit_rect,
                QColor(
                    255,
                    255,
                    255,
                    2
                )
            )

            offset = (
                (
                    CHECKBOX_SIZE
                    -
                    CHECKBOX_DRAW_SIZE
                )
                //
                2
            )

            rect = QRect(
                self.width()
                -
                CHECKBOX_RIGHT_MARGIN
                -
                CHECKBOX_SIZE
                +
                offset,

                top
                +
                (
                    TASK_HEIGHT
                    -
                    CHECKBOX_SIZE
                )
                //
                2
                +
                offset,

                CHECKBOX_DRAW_SIZE,
                CHECKBOX_DRAW_SIZE
            )

            checked = bool(
                task.get(
                    "completed",
                    False
                )
            )

            pen = QPen(
                CHECKBOX_CHECK
                if checked
                else CHECKBOX_BORDER
            )

            pen.setWidth(
                2
            )

            painter.setPen(
                pen
            )

            painter.setBrush(
                Qt.BrushStyle.NoBrush
            )

            painter.drawRoundedRect(
                rect,
                6,
                6
            )

            # =================================================
            # Check
            # =================================================

            if checked:

                check_pen = QPen(
                    CHECKBOX_CHECK
                )

                check_pen.setWidth(
                    4
                )

                check_pen.setCapStyle(
                    Qt.PenCapStyle.RoundCap
                )

                check_pen.setJoinStyle(
                    Qt.PenJoinStyle.RoundJoin
                )

                painter.setPen(
                    check_pen
                )

                x = rect.x()
                y = rect.y()

                painter.drawLine(
                    x + 6,
                    y + 15,
                    x + 12,
                    y + 21
                )

                painter.drawLine(
                    x + 12,
                    y + 21,
                    x + 24,
                    y + 8
                )

        # =================================================
        # Reminder Switch
        # =================================================

        else:

            switch_rect = (
                self.get_switch_rect(
                    index
                )
            )

            enabled = bool(
                task.get(
                    "reminder_enabled",
                    True
                )
            )

            painter.setPen(
                Qt.PenStyle.NoPen
            )

            painter.setBrush(
                SWITCH_ON
                if enabled
                else SWITCH_OFF
            )

            painter.drawRoundedRect(
                switch_rect,
                SWITCH_HEIGHT // 2,
                SWITCH_HEIGHT // 2
            )

            knob_size = 20

            knob_y = (
                switch_rect.y()
                +
                (
                    switch_rect.height()
                    -
                    knob_size
                )
                //
                2
            )

            if enabled:

                knob_x = (
                    switch_rect.right()
                    -
                    knob_size
                    -
                    4
                )

            else:

                knob_x = (
                    switch_rect.x()
                    +
                    4
                )

            painter.setBrush(
                QColor(
                    255,
                    255,
                    255,
                    255
                )
            )

            painter.drawEllipse(
                QRect(
                    knob_x,
                    knob_y,
                    knob_size,
                    knob_size
                )
            )


    # =====================================================
    # Keyboard
    # =====================================================

    def keyPressEvent(
        self,
        event
    ):

        # =================================================
        # 編輯
        # =================================================

        if self.edit_box is not None:

            if (
                event.key()
                ==
                Qt.Key.Key_Escape
            ):

                self.close_edit(
                    save=False
                )

                return

            if event.key() in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter
            ):

                self.close_edit(
                    save=True
                )

                return

            super().keyPressEvent(
                event
            )

            return

        # =================================================
        # 新增
        # =================================================

        if self.input_box is not None:

            if (
                event.key()
                ==
                Qt.Key.Key_Escape
            ):

                self.close_input()

                return

            super().keyPressEvent(
                event
            )

            return

        # =================================================
        # DEL
        # =================================================

        if (
            event.key()
            ==
            Qt.Key.Key_Delete
        ):

            if (
                0 <= self.selected_index
                <
                len(self.tasks)
            ):

                self.delete_task(
                    self.selected_index
                )

                self.selected_index = -1

            event.accept()

            return

        # =================================================
        # ESC
        # =================================================

        if (
            event.key()
            ==
            Qt.Key.Key_Escape
        ):

            if self.reminder_mode:

                self.leave_reminder_mode()

            else:

                self.selected_index = -1

                self.update()

            event.accept()

            return

        super().keyPressEvent(
            event
        )


    # =====================================================
    # Resize
    # =====================================================

    def resizeEvent(
        self,
        event
    ):

        super().resizeEvent(
            event
        )

        self.position_edit_box()

        if self.input_box is not None:

            self.input_box.setGeometry(
                10,
                TASK_START_Y - 3,
                max(
                    180,
                    self.width() - 80
                ),
                34
            )

        self.update()


    # =====================================================
    # 編輯框位置
    # =====================================================

    def position_edit_box(
        self
    ):

        if self.edit_box is None:
            return

        if not (
            0 <= self.edit_index < len(self.tasks)
        ):
            return

        top = (
            TASK_START_Y
            +
            self.edit_index
            *
            TASK_HEIGHT
        )

        left = (
            78
            if self.reminder_mode
            else 10
        )

        self.edit_box.setGeometry(
            left,
            top + 5,
            self.width()
            -
            left
            -
            75,
            TASK_HEIGHT - 10
        )


    # =====================================================
    # Leave
    # =====================================================

    def leaveEvent(
        self,
        event
    ):

        self.add_button_hover = False

        self.reminder_button_hover = False

        self.update()

        super().leaveEvent(
            event
        )


    # =====================================================
    # 儲存
    # =====================================================

    def save_all(
        self
    ):

        save_data(
            self.tasks,
            self.reminders_enabled,
            self.last_reset_date
        )

        save_config(
            self
        )


    # =====================================================
    # 關閉
    # =====================================================

    def closeEvent(
        self,
        event
    ):

        event.ignore()

        self.hide_to_tray()


# =========================================================
# Main
# =========================================================

if __name__ == "__main__":

    # 必須在建立 UI 前設定 Windows AppUserModelID，
    # 讓通知來源正確顯示為「菲比提醒」。
    setup_windows_notification_identity()

    app = QApplication(
        sys.argv
    )

    _UPDATE_CONTROLLER = _UpdateController()

    app.setQuitOnLastWindowClosed(
        False
    )

    app.setApplicationName(
        APP_NAME
    )

    app.setApplicationDisplayName(
        APP_NAME
    )

    app.setFont(
        QFont(
            FONT_NAME,
            10
        )
    )

    window = DailyWidget()

    window.show()

    window.raise_()

    window.activateWindow()

    QTimer.singleShot(1500, start_update_check)
    update_check_timer = setup_hourly_update_check()

    sys.exit(
        app.exec()
    )