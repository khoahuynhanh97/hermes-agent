# Hermes Agent project guidance

- Treat `.env`, API keys, tokens, and user project media as sensitive; never print or overwrite them.
- Preserve existing uncommitted changes and keep edits scoped to the requested workflow.
- Use Python 3.10+ and native PowerShell commands on Windows.
- Run the smallest relevant `pytest` target first, then broader tests when warranted.
- Do not modify generated runtime data under `jobs/`, `logs/`, `runtime_logs/`, or `projects/` unless the task explicitly requires it.
- For GUI or media-pipeline changes, verify failure handling and avoid paid provider calls during tests.

## Architecture & Storage Principles
- **Sole Brain**: Hermes Orchestrator (`AgentTurnRuntime` + `AIAgent`) is the single general-purpose brain. Ingress channels (Telegram, CLI, Web) are thin adapters.
- **Knowledge Base Structure**: Canonical storage is strictly organized under `knowledge_base/`:
  - `knowledge_base/approved/`: Officially approved knowledge entries & SQLite DB.
  - `knowledge_base/review_queue/`: Proposals awaiting human approval (`/approve`).
  - `knowledge_base/jobs/active/`: Active in-flight jobs.
  - `knowledge_base/jobs/archived/`: Jobs archived and cleaned up after approval.
  - `knowledge_base/memory/user_memory.json`: Long-term multi-turn conversation memory.
- **HITL Enforcement**: All major milestones (Product Lock, Creative Brief, Scene Plan, Final Video, Knowledge Lessons) require explicit human approval; never auto-approve silently.

