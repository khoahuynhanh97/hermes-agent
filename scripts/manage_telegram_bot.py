"""Background process manager for Telegram Bot."""
import os
import sys
import time
import subprocess
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

REPO_ROOT = Path(__file__).parent.parent.resolve()
LOG_DIR = REPO_ROOT / "logs" / "runtime"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "telegram_bot.log"
ERR_LOG_FILE = LOG_DIR / "telegram_bot.err.log"
PID_FILE = LOG_DIR / "telegram_bot.pid"


def find_bot_processes():
    procs = []
    if not psutil:
        return procs
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = p.info.get('cmdline') or []
            cmd_str = " ".join(cmd)
            if "telegram_bot.py" in cmd_str and "manage_telegram_bot.py" not in cmd_str:
                procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return procs


def status_bot():
    procs = find_bot_processes()
    if procs:
        print("[OK] Telegram Bot is RUNNING in background:")
        for p in procs:
            print(f"   - Process ID (PID): {p.pid} | Command: {' '.join(p.cmdline()[:3])}")
        return True
    else:
        print("[INFO] Telegram Bot is NOT running.")
        return False


def stop_bot():
    procs = find_bot_processes()
    if not procs:
        print("[INFO] No running Telegram Bot process found.")
        return
    for p in procs:
        try:
            p.terminate()
            print(f"[OK] Terminated Telegram Bot process PID: {p.pid}")
        except Exception as e:
            print(f"[WARN] Error stopping PID {p.pid}: {e}")
    if PID_FILE.exists():
        PID_FILE.unlink(missing_ok=True)


_log_handles = []

def start_bot():
    stop_bot()
    print("[INFO] Starting Telegram Bot in background...")
    
    python_exe = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
    if not Path(python_exe).exists():
        python_exe = sys.executable

    script_path = str(REPO_ROOT / "telegram_bot.py")

    log_out = open(LOG_FILE, "a", encoding="utf-8")
    log_err = open(ERR_LOG_FILE, "a", encoding="utf-8")
    _log_handles.extend([log_out, log_err])

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = 0x00000200 | 0x08000000  # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW

    proc = subprocess.Popen(
        [python_exe, script_path],
        cwd=str(REPO_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=log_out,
        stderr=log_err,
        creationflags=creation_flags,
    )

    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    time.sleep(2)

    if proc.poll() is None:
        print(f"[OK] Telegram Bot started in BACKGROUND successfully! (PID: {proc.pid})")
        print(f"   - Log Output: {LOG_FILE}")
        print(f"   - Error Log:  {ERR_LOG_FILE}")
    else:
        print(f"[FAIL] Process exited immediately with code {proc.poll()}. Check log: {ERR_LOG_FILE}")


if __name__ == "__main__":
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "start").lower()
    if cmd == "status":
        status_bot()
    elif cmd == "stop":
        stop_bot()
    elif cmd == "start":
        start_bot()
    else:
        print("Usage: manage_telegram_bot.py [start|status|stop]")
        raise SystemExit(2)
