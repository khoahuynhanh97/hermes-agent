@echo off
start /b python web_studio.py
ping 127.0.0.1 -n 6 > nul
pytest test_web_studio_api.py -s -v
REM Find the process and kill it
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8000') do (
    taskkill /PID %%p /F
)
del test_web_studio_api.py
