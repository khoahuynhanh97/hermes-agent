# Hermes Upstream Gateway Rearchitecture Program

**Authority:** `docs/superpowers/specs/2026-08-22-hermes-upstream-gateway-rearchitecture-design.md`

**Target branch:** `codex/hermes-upstream-rearchitecture`

**Target worktree:** `D:\work\hermes-upstream-rearchitecture`

**Pinned upstream base:** `NousResearch/hermes-agent@0012dd1e0c7efc7e86fa75b89567a492057f0c02`

## Objective

Build one Hermes Orchestrator based on the canonical NousResearch Hermes Agent loop. Telegram, CLI, Web, and Omni are transport/UI surfaces. Product Intelligence, Video Factory, knowledge learning, approvals, budgets, workers, and future capabilities are governed behind typed Hermes application boundaries.

## Non-Negotiable Decisions

1. Do not merge the unrelated legacy and upstream histories.
2. Implement on the clean upstream target branch and port only reviewed behavior/data contracts.
3. Natural language always enters through `AgentTurnRequest` and one upstream `AIAgent` adapter.
4. Deterministic UI controls always enter through authenticated `OperatorCommand`.
5. Stable capability IDs hide MCP provider and wire-name changes.
6. Hermes, Product Intelligence, and Video Factory retain separate canonical ownership.
7. Durable workflow state, approval, budget, job, and event records commit before effects.
8. Learning is evidence-backed memory/knowledge/skills with approval and rollback, not autonomous model-weight training.
9. No live paid-provider call is permitted in automated verification.
10. Legacy data and media remain intact until reconciliation, rollback, parity, and observation gates pass.

## Execution Order

| Gate | Plan | Required Outcome |
| --- | --- | --- |
| 1 | `2026-08-22-hermes-gateway-rearchitecture-gate-1.md` | Clean upstream baseline, provenance, canonical contracts, compatibility suite |
| 2 | `2026-08-22-hermes-gateway-rearchitecture-gate-2.md` | One Agent Turn path, global identity, per-channel sessions, explicit handoff |
| 3 | `2026-08-22-hermes-gateway-rearchitecture-gate-3.md` | Stable capability catalog, MCP snapshots, policy, Tool Search, domain skills |
| 4 | `2026-08-22-hermes-gateway-rearchitecture-gate-4.md` | Durable workflows, shared approvals, budgets, jobs, recovery |
| 5 | `2026-08-22-hermes-gateway-rearchitecture-gate-5.md` | Full Product Intelligence to Video Factory flow with HITL and migration reconciliation |
| 6 | `2026-08-22-hermes-gateway-rearchitecture-gate-6.md` | Governed learning, approved retrieval, skill publication, rollback, metrics |
| 7 | `2026-08-22-hermes-gateway-rearchitecture-gate-7.md` | `hermes start`, health/readiness, restart, four-channel cutover, retirement guards |

Gates execute sequentially. Tasks inside a gate may run in parallel only when their **Interfaces** sections show no dependency and they do not modify the same files. A gate is not started until the previous gate's exit criteria and verification commands pass.

## Gate Checkpoint Contract

At the end of every gate, the implementing agent must provide:

- commit list and exact changed files;
- focused test commands with exact pass/fail counts;
- upstream compatibility result where required;
- migration/provider/network effects, explicitly stating none when none occurred;
- unresolved risks or deviations from the plan;
- `git status --short` for the target worktree;
- a reviewer decision: `ACCEPTED` or `BLOCKED` with evidence.

Do not mark a gate accepted because code compiles. Every listed exit criterion must map to a passing test, inspected artifact, or recorded operational check.

## Antigravity Master Prompt

```text
You are the implementation lead for the Hermes Upstream Gateway Rearchitecture.

Repository context:
- Legacy source is D:\work\hermes-agent and is read-only migration/reference input.
- Clean target worktree is D:\work\hermes-upstream-rearchitecture.
- Target branch is codex/hermes-upstream-rearchitecture.
- Pinned upstream base is NousResearch/hermes-agent commit 0012dd1e0c7efc7e86fa75b89567a492057f0c02.
- Never merge unrelated histories and never reset, clean, overwrite, or delete legacy user data/media.

Authority and execution documents:
1. Read docs/superpowers/specs/2026-08-22-hermes-upstream-gateway-rearchitecture-design.md.
2. Read docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-program.md.
3. Execute the next unaccepted gate plan from docs/superpowers/plans/2026-08-22-hermes-gateway-rearchitecture-gate-N.md.

Required method:
- Use superpowers:subagent-driven-development for independent tasks; use fresh workers and review each task before accepting it.
- Follow every task in order unless its interface has no dependency and file ownership does not overlap.
- Use TDD exactly as written: failing test, confirm failure reason, minimal implementation, passing focused test, commit.
- Preserve upstream core. Put project-specific behavior in hermes_personal, plugins, skills, MCP anti-corruption adapters, and application services.
- Never add keyword semantic routing to Telegram, CLI, Web, or Omni.
- Never let workers interpret intent or cross approval/budget gates.
- Never use live paid providers in tests; inject deterministic fakes.
- Do not weaken or delete a test to make implementation pass.
- Do not continue to the next gate after any exit criterion fails.

Review requirements per task:
- First review spec/contract compliance.
- Then review code quality, security, idempotency, restart behavior, and test strength.
- Fix findings and rerun the focused suite before commit.

Gate completion report:
- List commits and changed files.
- Show exact verification commands and counts.
- Map every gate exit criterion to evidence.
- Show target worktree git status.
- State ACCEPTED only when every criterion passes; otherwise state BLOCKED and stop.

Begin by detecting the next unaccepted gate from Git history and test evidence. Gate 1 is already implemented through commit 10bb230b22; independently rerun its compatibility checks before beginning Gate 2.
```

## Final Program Acceptance

The program is complete only when all ten acceptance criteria in the approved design spec pass, the complete offline test suite passes, `hermes start --help` and the fake-provider runtime smoke test pass, migration reconciliation has no unexplained differences, and legacy retirement is separately authorized after its observation window.
