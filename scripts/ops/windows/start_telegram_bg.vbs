Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -ExecutionPolicy Bypass -File ""D:\work\hermes-agent\start.ps1"" -Telegram -ServicesOnly", 0, False
