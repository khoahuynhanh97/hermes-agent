# Gate 0 Baseline Environment and Test Verification

**Audit Scope**: Gate 0 Baseline & Verification  
**Repository Root**: `D:/work/hermes-upstream-rearchitecture`  
**Current Branch**: `codex/hermes-upstream-rearchitecture`  
**Revision (HEAD)**: `b193b1d07e800d7109e77f5ae5f61fa66f2fb454`  
**Date (UTC)**: 2026-08-29 19:05:48 UTC  
**Status**: **ACCEPTED**

---

## 1. System & Runtime Environment Metadata (Captured from Host)

| Attribute | Captured Value | Exact Command Executed | Exit Code |
| :--- | :--- | :--- | :---: |
| **Operating System** | `Microsoft Windows [Version 10.0.26200.8875]` | `cmd.exe /c ver` | `0` |
| **Python Version** | `Python 3.11.15` | `uv run python --version` | `0` |
| **Package Manager** | `uv 0.12.1 (329541a50 2026-07-31 x86_64-pc-windows-msvc)` | `uv --version` | `0` |
| **Repository Root** | `D:/work/hermes-upstream-rearchitecture` | `git rev-parse --show-toplevel` | `0` |
| **Current Branch** | `codex/hermes-upstream-rearchitecture` | `git branch --show-current` | `0` |
| **Git Revision (HEAD)**| `b193b1d07e800d7109e77f5ae5f61fa66f2fb454` | `git rev-parse HEAD` | `0` |
| **Cache Isolation** | Active | `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider` | 0 |

---

## 2. Baseline Test Execution Results

Executed and verified with raw outputs in `command-transcript.txt`:

1. **`hermes_personal` Core Test Suite**:
   - `uv run pytest tests/hermes_personal -q -p no:cacheprovider` $\rightarrow$ **663 passed in 64.36s (Exit Code: 0)**.
2. **Promoted Upstream & Capability Tests**:
   - `uv run pytest tests/agent/test_knowledge_capture_prompt.py tests/skills/test_learning_from_video_skill.py tests/gateway/test_unknown_command.py tests/hermes_cli/test_commands.py -q -p no:cacheprovider` $\rightarrow$ **85 passed in 16.91s (Exit Code: 0)**.
3. **Static Analysis**:
   - `uv run ruff check hermes_personal tests/hermes_personal` $\rightarrow$ **All checks passed (Exit Code: 0)**.
4. **Gateway Known Commands Invariant**:
   - `uv run python -c "from hermes_cli.commands import GATEWAY_KNOWN_COMMANDS, resolve_command; bad=sorted(x for x in GATEWAY_KNOWN_COMMANDS if resolve_command(x) is None); print(bad); assert not bad"` $\rightarrow$ `[]` **(Exit Code: 0)**.
