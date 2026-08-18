# Repository Structure Check Runbook

This runbook documents how to run the repository layout structure guard for the Hermes Agent Platform. 

To ensure the repository root remains clean and free of untracked build outputs, mutable data files, caches, or misplaced production python files, the structure guard should be integrated into development and release validation steps.

---

## Validation Guard Command

Run the following command from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev/check-structure.ps1
```

### Script Execution & Return Codes
- **Clean State**: Exit Code `0` and outputs `[STRUCTURE GUARD] Repository structure is clean and locked.`
- **Violations State**: Non-zero Exit Code and outputs a detailed list of path violations, the rule violated, and the expected correct location.

---

## AI Agent Integration Policy

Every AI coding agent **must** execute this script before reporting completion of any task that involves:
- File creation
- File relocation or moves
- Directory restructuring
- Executing python/setuptools build artifacts
- Modifications to runtime path mappings
