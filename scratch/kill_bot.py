import subprocess
import os
import re

try:
    # Use PowerShell to get Process IDs and Command Lines of python processes
    cmd = 'powershell -Command "Get-CimInstance Win32_Process -Filter \\"name = \'python.exe\'\\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"'
    output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
    
    # Try parsing as JSON
    try:
        data = json.loads(output)
        if not isinstance(data, list):
            data = [data]
    except Exception:
        # Fallback if conversion fails (e.g. single item or raw string)
        data = []
        # Let's try parsing using regex on raw output
        for line in output.splitlines():
            m = re.search(r'"ProcessId":\s*(\d+).*?"CommandLine":\s*"(.*?)"', line)
            if m:
                data.append({"ProcessId": int(m.group(1)), "CommandLine": m.group(2)})
                
    # If standard JSON loading works, let's extract
    import json
    try:
        processes = json.loads(output)
        if not isinstance(processes, list):
            processes = [processes]
    except Exception:
        processes = []

    # Alternative WMI query
    if not processes:
        wmi_cmd = 'wmic process where "name=\'python.exe\'" get ProcessId, CommandLine /format:list'
        wmi_out = subprocess.check_output(wmi_cmd, shell=True).decode('utf-8', errors='ignore')
        current_proc = {}
        for line in wmi_out.splitlines():
            line = line.strip()
            if line.startswith("CommandLine="):
                current_proc["CommandLine"] = line.split("=", 1)[1]
            elif line.startswith("ProcessId="):
                current_proc["ProcessId"] = int(line.split("=", 1)[1])
                processes.append(current_proc)
                current_proc = {}

    killed_count = 0
    for proc in processes:
        cmdline = proc.get("CommandLine") or ""
        pid = proc.get("ProcessId")
        if not pid:
            continue
        
        # Avoid killing ourselves
        if pid == os.getpid():
            continue
            
        if "telegram_bot" in cmdline.lower() or "run_job_worker" in cmdline.lower():
            print(f"Killing process PID {pid}: {cmdline}")
            os.system(f"taskkill /F /PID {pid}")
            killed_count += 1
            
    if killed_count == 0:
        print("No running bot or job worker processes found.")
    else:
        print(f"Successfully killed {killed_count} processes.")

except Exception as e:
    print("Error querying or killing processes:", e)
