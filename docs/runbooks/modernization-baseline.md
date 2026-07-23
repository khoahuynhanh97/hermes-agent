# Hermes Modernization Baseline

## Baseline Description

This document establishes the baseline for the Hermes modernization effort. It defines the expected behavior of the legacy configuration system, particularly regarding SQLite database path configuration, which serves as the foundation for verifying that modernization efforts do not break existing functionality.

The baseline test verifies that when the `HERMES_DB_PATH` environment variable is set, the application respects this setting for the SQLite database file location.

## Command Matrix for Smoke Tests

### Desktop Smoke Checks
```powershell
# Start Desktop GUI
.\start_gui.bat

# Verify basic functionality:
# 1. Application launches successfully
# 2. Can create/load projects
# 3. Can access local capabilities (FFmpeg, etc.)
# 4. Settings persist between sessions
```

### Web Smoke Checks
```powershell
# Start Web server
.\start_web.bat

# Verify basic functionality:
# 1. Web interface loads at http://127.0.0.1:8000
# 2. API responds to health check
# 3. Can create projects via API
# 4. Can access Prompt Studio via API
```

### Telegram Smoke Checks
```powershell
# Start Telegram bot and worker
.\start_telegram_and_worker.bat

# Verify basic functionality:
# 1. Bot responds to /start command
# 2. Bot accepts media uploads
# 3. Bot processes commands (/hoc_kien_thuc, etc.)
# 4. Worker processes incoming jobs
```

### Worker Smoke Checks
```powershell
# Start worker explicitly (if needed)
python -m workers.job_worker

# Verify basic functionality:
# 1. Worker connects to job queue
# 2. Worker processes jobs from queue
# 3. Worker reports success/failure appropriately
# 4. Worker handles connection interruptions gracefully
```

### Baseline Verification Commands
```powershell
# Run baseline contract test
.\.venv\Scripts\python.exe -m pytest tests/contract/test_legacy_baseline.py -v

# Run all contract tests
.\.venv\Scripts\python.exe -m pytest tests/contract/ -v

# Run unit tests
.\.venv\Scripts\python.exe -m pytest -m unit -v

# Run integration tests
.\.venv\Scripts\python.exe -m pytest -m integration -v

# Run web tests
.\.venv\Scripts\python.exe -m pytest -m web -v
```