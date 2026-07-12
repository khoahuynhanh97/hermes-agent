import subprocess
import sys
import os

def main():
    # Simply redirect to sync_telegram_jobs.py
    script_path = os.path.join(os.path.dirname(__file__), "sync_telegram_jobs.py")
    subprocess.run([sys.executable, script_path])

if __name__ == "__main__":
    main()
