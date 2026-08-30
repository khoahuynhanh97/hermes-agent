# Next Implementation Slice Specification

**Assignment Post-Audit**: ARCH-G3 Bounded Happy-Path Integration Slice  
**Target Profile**: `PERSONAL_HAPPY_PATH_V1`  
**Prerequisite**: Planner acceptance of ARCH-G2 Canonical Ownership Audit (`reports/personal-assistant-architecture/`)

---

## 1. Objective

Implement the smallest non-speculative integration slice that connects the canonical upstream `run_agent.AIAgent` to the verified **Video Factory FastMCP Server** and **Knowledge Base Skill**, without building duplicate turn platforms or modifying core prompt caching invariants.

---

## 2. Strictly Bounded Scope

### Allowed Operations:
1. **MCP Client Stdio Wiring**:
   - Configure Video Factory FastMCP stdio server in local agent configuration so `AIAgent` auto-discovers VF tools (`video_project_create`, `create_brief`, `create_scene_plan`, `create_storyboard`, `render`, `export`).
2. **Skill Activation**:
   - Place and verify the two personal assistant skills in `skills/`:
     - `skills/hermes-personal-product-video-production/SKILL.md`
     - `skills/hermes-personal-knowledge-learning/SKILL.md`
3. **Supervisor Stdio / Capability Health Check**:
   - Add a lightweight health check in `hermes_personal/runtime/supervisor.py` to verify local Video Factory MCP stdio responsiveness on `hermes start`.

### Forbidden Operations (Out of Scope):
- ❌ Do NOT create new turn services or rewrite `run_agent.AIAgent`.
- ❌ Do NOT modify prompt caching or synthetic message injection mechanisms.
- ❌ Do NOT execute live paid provider calls during automated tests.
- ❌ Do NOT delete or destructively refactor pre-existing worktree changes.

---

## 3. Allowed Files for Next Slice

```
skills/hermes-personal-product-video-production/SKILL.md
skills/hermes-personal-knowledge-learning/SKILL.md
hermes_personal/runtime/supervisor.py
tests/hermes_personal/e2e/test_canonical_agent_integration.py
```

---

## 4. Verification Plan

1. **MCP Discovery Verification**:
   - Test that `AIAgent` initialized with enabled MCP toolsets discovers all 23 Video Factory tools over local stdio connection in an offline temporary environment.
2. **Skill Procedure Verification**:
   - Verify `AIAgent` accurately parses and executes the 5-gate procedure from `SKILL.md`.
3. **Automated Offline Test Suite**:
   ```bash
   uv run pytest tests/hermes_personal/e2e/test_canonical_agent_integration.py tests/mcp_servers/test_video_factory_server.py -v
   uv run ruff check hermes_personal src/hermes skills
   git diff --check
   ```
