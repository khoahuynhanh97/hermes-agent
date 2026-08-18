@echo off
rem Launcher for the Hermes Desktop GUI.
rem
rem Uses the installed ``hermes-gui`` entry point (defined in pyproject.toml
rem as ``hermes.channels.gui.main:main``). Falls back to
rem ``python -m hermes.channels.gui.main`` when the console script is not on
rem PATH (e.g. running from a fresh checkout that has not been re-installed).
title Hermes Desktop GUI
setlocal

set "HERMES_GUI=%~dp0.venv\Scripts\hermes-gui.exe"
if not exist "%HERMES_GUI%" set "HERMES_GUI=hermes-gui"

where "%HERMES_GUI%" >nul 2>nul
if not errorlevel 1 goto run_console_script

set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

start "" "%PYTHON%" -m hermes.channels.gui.main
goto done

:run_console_script
start "" "%HERMES_GUI%"

:done
endlocal
exit /b 0
