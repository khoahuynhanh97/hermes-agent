# Hermes Agent project guidance

- Treat `.env`, API keys, tokens, and user project media as sensitive; never print or overwrite them.
- Preserve existing uncommitted changes and keep edits scoped to the requested workflow.
- Use Python 3.10+ and native PowerShell commands on Windows.
- Run the smallest relevant `pytest` target first, then broader tests when warranted.
- Do not modify generated runtime data under `jobs/`, `logs/`, `runtime_logs/`, or `projects/` unless the task explicitly requires it.
- For GUI or media-pipeline changes, verify failure handling and avoid paid provider calls during tests.
