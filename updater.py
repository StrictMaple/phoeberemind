import os
import sys
import time
import shutil
import subprocess


def main():
    if len(sys.argv) < 3:
        return

    old_exe = os.path.abspath(sys.argv[1])
    new_exe = os.path.abspath(sys.argv[2])

    # 等待主程式關閉
    time.sleep(2)

    # 等待舊 EXE 不再被使用
    for _ in range(30):
        try:
            with open(old_exe, "ab"):
                break
        except PermissionError:
            time.sleep(1)
    else:
        return

    # 備份舊版本
    backup_exe = old_exe + ".old"

    try:
        if os.path.exists(backup_exe):
            os.remove(backup_exe)

        if os.path.exists(old_exe):
            shutil.copy2(old_exe, backup_exe)

        # 替換 EXE
        shutil.copy2(new_exe, old_exe)

        # 啟動新版
        subprocess.Popen(
            [old_exe],
            cwd=os.path.dirname(old_exe),
            creationflags=getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0
            )
        )

        # 清理下載檔
        try:
            os.remove(new_exe)
        except Exception:
            pass

        # 清理備份
        try:
            os.remove(backup_exe)
        except Exception:
            pass

    except Exception:
        # 更新失敗時嘗試還原
        try:
            if os.path.exists(backup_exe):
                shutil.copy2(backup_exe, old_exe)
        except Exception:
            pass


if __name__ == "__main__":
    main()
