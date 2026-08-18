# GitHub Sync Commit Plan - 2026-08-18

## Objective

Synchronize `main` and `codex/hermes-personal-assistant-core` to the recovered canonical Hermes structure, prioritizing the final `src/hermes` layout and verified Product Intelligence / Video Factory flow.

## Recent Commit Window

Relevant commits from the last two weeks:

- `c64f1b04b` / `912f278c0`: Product research script supervisor design and plan.
- `684c923be` through `11a39753b`: Product research intent parsing, local sheet export, crawler source gating, workflow orchestration, and script workflow API exposure.
- `c94984581` through `d975d948c`: Affiliate gateway fix, portable bootstrap, package init fixes, runtime consolidation, live Video Factory run, provider wiring, and safeguards.
- `af606d556`: Consolidated Hermes runtime core and custom capabilities on `codex/hermes-personal-assistant-core`.
- `f19a1494d` through `fa5541c84`: Vertex routing, media workflow fixes, canonical source runtime, Video Factory HITL completion, durable media jobs, product identity / visual QC skills, and weekly platform standardization plan.
- `50b7e76f0`: Added `video_factory_runtime_info` to canonical tools and migration support.
- `5ce03ef02`: Restored canonical repository structure after reset/clean regression.

## Merge Strategy

1. Treat `5ce03ef02` as the recovery baseline because it restores the final canonical structure.
2. Fast-forward `codex/hermes-personal-assistant-core` to the recovery baseline.
3. Fast-forward `main` to the same recovery baseline.
4. Avoid force push because both remote branches are ancestors of the recovery commit.
5. Keep runtime data and generated artifacts out of Git; use `docs/reports/` for this plan and `src/hermes/` for production Python source.

## Verification

Validated before sync:

- Python import resolves to `src/hermes`.
- `tests/hermes/test_async_video_dispatch.py` and `tests/hermes/test_platform_completion_smoke.py` passed.
- Repository structure, runtime resources, Product Research API, and Product Research script workflow tests passed.
- `compileall src/hermes` passed.
- `pnpm --dir apps/web build` passed.
