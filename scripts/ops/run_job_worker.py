import os
import sys

# Add root dir to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Force UTF-8 stdout
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from hermes.application.core.job_watcher import start_watching

if __name__ == "__main__":
    print("🚀 Khởi chạy Hermes Agent Job Worker Daemon...")
    start_watching(poll_interval=3)
