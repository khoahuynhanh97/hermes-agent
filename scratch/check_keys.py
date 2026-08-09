import os
from pathlib import Path

env_path = Path(r"d:\work\hermes-agent\.env")
if env_path.exists():
    print("Checking .env configuration (Presence check only):\n")
    with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("\"'")
                print(f"  {k:<35}: {'CONFIGURED' if v else 'EMPTY'}")
else:
    print(".env file not found!")
