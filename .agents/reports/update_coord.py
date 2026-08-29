from pathlib import Path
import re

path = Path('.hermes/coordination.md')
text = path.read_text(encoding='utf-8')

marker = '## Last Worker Report'
insert = """## Last Worker Report

Iteration: 101 (MCP Readiness Reconciliation on 51f2d29767)
Phase: Phase 7 Continuation - Personal Happy Path and Bounded Hardening

Implemented:
- **MCP Readiness Reconciliation Only**:
  - Docs: `docs/hermes-personal/product-video-runbook.md`.
  - Logic:
    - Replaced incorrect Section 6.1 tool contracts with adapter-actual payloads/aliases from `handlers.py:275-705`, `:438-568`, `:206-269`.
    - Distinguished external raw outputs from adapter-normalized artifacts.
    - Documented exact Video Factory alias candidates; removed stale alias-fix request already satisfied in `handlers.py`.
    - Clarified `wire_tools` is an adapter constructor mapping, not a `config.yaml` mapping.
    - Removed unsupported Free/Local, polling-cost, dollar-max, and `$90` total claims.
    - Documented reservation semantics: 5/5/10/50/20 are budget reservations, not provider prices or configured spending caps.
    - Recorded worker bootstrap launch-home divergence at `worker.py:114` vs `load_config()`/`get_hermes_home()` and marked effective launcher environment unresolved.
    - Recorded static filesystem evidence: `product_scout.mcp_server` file present; `D:/work/hermes-agent/mcp_servers/video_factory/server.py` absent at literal path, package resolution unknown.
    - Replaced unsafe broad `discover_mcp_tools()` claim with bounded selective PI/VF discovery proposal and unresolved startup-safety caveat.
    - Listed only real missing operator choices: server/package resolution, credentials, explicit authorization/spending cap, and `HERMES_HOME` launch consistency.

Files Changed:
- `docs/hermes-personal/product-video-runbook.md`

Verification:
- Static reconciliation review only.
- `git diff --check`: Clean after EOF newline normalization.

Commit: Pending on this report/handoff edit.

Remaining Issues / Blockers:
- Startup-safe selective PI/VF discovery path unresolved: if selective discovery cannot be made side-effect-free and durable-state isolated, report blocker instead of executing discovery.
- Video Factory server/package resolution unresolved: confirm installed package or alternate repo path before live setup.
- Live MVP remains OPEN. No live acceptance, no provider/runtime execution in this iteration.

Deferred Items:
- Distributed multi-worker clustering, generic outbox brokers, and HA replication remain deferred.

"""

history = """## History

### Iteration 101 Worker
WORKER reconciled MCP readiness documentation only on baseline `51f2d29767`: (1) corrected `docs/hermes-personal/product-video-runbook.md` sections 6/7 to match actual adapter payloads, alias candidates, local lock fallback, and fail-closed `build_resource_pack` behavior from `hermes_personal/product_video/handlers.py`; (2) removed unsupported Free/Local cost, polling price, and `$90` cap claims and documented budget reservation semantics instead; (3) recorded worker bootstrap/config `HERMES_HOME` divergence at `worker.py:114` vs `load_config()` as unresolved; (4) recorded static evidence that `product_scout.mcp_server` exists while `D:/work/hermes-agent/mcp_servers/video_factory/server.py` is absent at the literal checked path and package resolution remains unknown; (5) replaced unsafe broad `discover_mcp_tools()` recommendation with a bounded selective PI/VF discovery proposal and explicit unresolved startup-safety caveat; (6) verified with static review and clean `git diff --check` after EOF normalization. No business code, tests, runtime/provider calls, or MVP_DONE declaration. Handed off to PLANNER.

"""

if marker not in text:
    raise SystemExit('marker not found')

text = text.replace(marker, insert + history, 1)
path.write_text(text, encoding='utf-8')
