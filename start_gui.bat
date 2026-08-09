@echo off
title Hermes TikTok Studio GUI
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" main_gui.py
) else if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" main_gui.py
) else (
    start "" python main_gui.py
)
exit
