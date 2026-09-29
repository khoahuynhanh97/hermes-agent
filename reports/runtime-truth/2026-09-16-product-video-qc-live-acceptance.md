# Product Video QC Live Acceptance Checkpoint

Date: 2026-09-16
Status: `WAITING_FOR_OPERATOR`
Decision: `CODE_READY`, not `HAPPY_CASE_COMPLETE`

## Offline Evidence

| Check | Result |
| --- | --- |
| Product Video tests | `199 passed, 4 warnings` |
| Hermes Personal tests | `775 passed, 46 warnings` |
| Video Factory MCP tests | `38 passed` |
| Ruff | clean for `hermes_personal tests/hermes_personal` |
| CLI entrypoints | `--help` and `qc --help` passed |

The offline path covers canonical PI envelopes, current media SHA binding,
strict evaluator JSON, stale/manual/fake gate rejection, scoped budget
admission, durable QC claims, scene sampling boundaries, provider reference
allowlisting, and no-resubmit recovery fixtures.

## Source Changes

- `hermes_personal/product_video/qc/normalization.py`: canonical PI unwrap,
  exact identity matching, decoded media manifest, current-byte fingerprint.
- `hermes_personal/product_video/qc/evaluator.py`, `image_qc.py`,
  `video_qc.py`: strict response contract, branding hard failures, technical
  decode, approved scene boundaries, three samples per scene.
- `hermes_personal/product_video/qc/service.py` and `repository.py`: shared
  worker/CLI producer, SQLite QC claims, scoped/expiring authorization and
  existing budget ledger admission.
- `hermes_personal/application/operator_handler.py`: current configured QC,
  coverage, eligible reference, policy and byte guards before mutation.
- `hermes_personal/integrations/video_factory/server.py`: Product Lock rejects
  internal pack IDs and source-store identities before prompt propagation.
- `hermes_personal/product_video/handlers.py`: PI summary identity is no longer
  promoted to canonical evidence when the persisted snapshot is empty. A
  configured image/video QC call with no authorization persists the completed
  stage artifact and transitions to `WaitingForOperator` rather than
  quarantining it as an invalid product; unknown, failed, or non-PASS QC still
  fails closed. Explicit QC authorization remains durable across jobs and
  human-gated approvals.
- `hermes_personal/integrations/video_factory/server.py` and
  `product_video/handlers.py`: eligible reference boundary, selected asset
  provenance, stale-byte export check, stable versioned export and metadata.
- `hermes_personal/product_video/cli.py`: official export caption only,
  governed `qc` command, explicit QC authorization flags for `start` and
  `approve`, and `qc --advance`, which creates (but never approves) the next
  human gate only after configured QC PASS for the persisted waiting artifact.
- `hermes_personal/product_video/handlers.py`: persisted PI snapshot reuse via
  `get_product_research`, with the same canonical evidence and identity guards
  as a fresh research call.

## Live Run State

No configured image QC, render, video QC, rerender, or export call was made in
this checkpoint. No operator approval was issued. Therefore there are no live
QC/render run IDs, five approval IDs, scene operation IDs, evaluator scores,
or provider spend to report.

The existing product-2 output was preserved and read-only verified:

- MP4: `D:\work\hermes-agent-data\workspaces\video-factory\exports\export_proj-pv-daily-ac0e0ef3dd90a199_composite_514919987817696726.mp4`
- SHA-256: `9e6850d66150c261f95ec681ed16121ae41d5ef43e6dc550cffbe9b6a20b1e24`
- Size: `2,529,476` bytes
- Existing caption/metadata paths were not rewritten.

The current Product-Intelligence daily source contains a usable candidate for
a fresh run: `prod_02`, Baseus Bowie WM02, three local reference images under
`D:\\work\\Personal\\Product-Intelligence\\data\\daily_runs\\2026-09-15\\images\\02_baseus_bowie-wm02`.
The existing workflow `pv-daily-88c43128656d9472` has a real PI research
snapshot but that snapshot has no canonical product evidence; its Resource
Pack build was correctly rejected and the outbox quarantined. The old project
`proj-pv-daily-ac0e0ef3dd90a199` is intentionally excluded because its locked
identity is an internal `pack_snap_...` value.

A fresh PI research checkpoint was also created without QC/render calls:
snapshot `snap_ad555885dd5e40419911c62dbd8e02d9` resolved canonical brand
`Baseus`, product name `Tai nghe Bluetooth Wireless Baseus Bowie WM02`, and
three local `reference_only` assets. Its Resource Pack
`pack_snap_ad555885dd5e40419911c62dbd8e02d9` returned `ready_to_lock`; all
three asset paths exist. It is not yet attached to the old Hermes workflow,
and no approval or paid operation was created from it.

## Operator Action Required

Provide one workflow/run scope, configured provider/model, image-QC plus one
render/video-QC scope, an explicit maximum USD amount, and an expiry. Then
approve Product Lock, Brief, Scene Plan, Storyboard with cost authorization,
and Final Video separately after reviewing each artifact. Until those inputs
arrive, the system must remain `WAITING_FOR_OPERATOR`.
