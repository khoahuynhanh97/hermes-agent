> **Status: Historical** — This document is superseded by [Product Video Master Plan](product-video-master-plan.md). Do not use as implementation target.

---

# Product Video MVP â€” khÃ©p kÃ­n QC vÃ  happy case

> For the implementing agent: use executing-plans to execute this plan task by task. KhÃ´ng triá»ƒn khai thÃªm pháº¡m vi ngoÃ i káº¿ hoáº¡ch; khÃ´ng tá»± duyá»‡t HITL hoáº·c gá»i API cÃ³ phÃ­ khi chÆ°a cÃ³ quyá»n chi phÃ­ phÃ¹ há»£p.

## Goal

Má»™t sáº£n pháº©m tá»« PI READY batch Ä‘i qua configured Hermes workflow, dÃ¹ng áº£nh reference sáº¡ch Ä‘Ã£ QC, táº¡o má»™t video dá»c bÃ¡m sáº£n pháº©m/storyboard, qua QC ká»¹ thuáº­t vÃ  thá»‹ giÃ¡c, Ä‘á»§ nÄƒm human approvals, xuáº¥t MP4 + caption + metadata Ä‘á»ƒ ngÆ°á»i dÃ¹ng Ä‘Äƒng thá»§ cÃ´ng.

## Architecture

Giá»¯ Hermes brain, Product Video bounded context, MCP PI/VF, SQLite workflow/outbox/approvals vÃ  provider hiá»‡n cÃ³. Ná»‘i QC vÃ o cÃ¡c Ä‘Æ°á»ng cháº¡y hiá»‡n há»¯u; khÃ´ng táº¡o agent, MCP server, broker, UI hay general-purpose orchestration má»›i. QC report khÃ´ng pháº£i approval. Gate khÃ´ng thá»ƒ tiáº¿p tá»¥c náº¿u QC tÆ°Æ¡ng á»©ng chÆ°a há»£p lá»‡.

## Tech Stack

Python, pytest, SQLite, Hermes CLI, existing MCP client, configured multimodal evaluator, Vertex video provider, PyAV. Settings hÃ nh vi náº±m trong config.yaml; credentials khÃ´ng ghi vÃ o report/log/prompt.

## Global Constraints

- Chá»‰ sá»­a Product Video/VF vÃ  interface trá»±c tiáº¿p cáº§n thiáº¿t; báº£o toÃ n dirty worktree.
- PI daily schedule khÃ´ng thuá»™c pháº§n thay Ä‘á»•i nÃ y. KhÃ´ng coi lá»‹ch cháº¡y/PI hiá»‡n Ä‘Ã£ Ä‘Æ°á»£c audit láº¡i trong phiÃªn nÃ y.
- Giá»¯ Product Lock, Brief, Scene Plan, Storyboard, Final. KhÃ´ng tá»± approve hoáº·c dÃ¹ng report QC Ä‘á»ƒ giáº£ approval.
- KhÃ´ng xÃ³a workflow/export/report cÅ©; khÃ´ng dÃ¹ng manual/fake report Ä‘á»ƒ chá»©ng minh automatic QC.
- KhÃ´ng gá»i paid QC/render, retry, rerender trÆ°á»›c quyá»n chi phÃ­ cÃ³ scope, háº¡n má»©c vÃ  thá»i háº¡n cá»¥ thá»ƒ.
- Chá»‰ chá»n má»™t happy case trÆ°á»›c. KhÃ´ng tá»± rerender hÃ ng loáº¡t cÃ¡c sáº£n pháº©m completed.
- KhÃ´ng cam káº¿t sampling QC báº£o Ä‘áº£m 100% má»i frame sáº¡ch. Final operator pháº£i xem toÃ n bá»™ MP4.
- KhÃ´ng tÃ¡ch dá»± Ã¡n, thÃªm multi-user, tá»± upload TikTok, lÃ m ná»n táº£ng QC tá»•ng quÃ¡t hoáº·c refactor toÃ n bá»™ server.py.

## Baseline audit ngÃ y 2026-09-16

ÄÃ£ Ä‘á»‘i chiáº¿u source vÃ  DB, cháº¡y láº¡i `uv run pytest tests/hermes_personal -q`: **758 passed, 46 deprecation warnings**; Ruff sáº¡ch. CÃ¡c sá»‘ nÃ y lÃ  snapshot kiá»ƒm thá»­, khÃ´ng pháº£i acceptance criterion cá»‘ Ä‘á»‹nh.

1. server.py cÃ³ render/negative prompt cáº¥m source branding vÃ  caption/export identity guard. Image rubric cÃ³ hard failure cho seller branding.
2. cli.py `_format_tiktok_caption` váº«n sinh â€œReview chÃ¢n thá»±câ€, â€œchÃ­nh hÃ£ngâ€, â€œgiá» hÃ ng TikTok Shopâ€, `#review`. status/approve gá»i template nÃ y thay vÃ¬ caption export.
3. VIDEO rubric chÆ°a coi source branding/watermark/marketplace UI lÃ  hard failure.
4. TÃ¬m runtime call sites cá»§a run_image_qc/run_video_qc chá»‰ tháº¥y definitions/exports/tests, chÆ°a tháº¥y producer trong workflow/CLI.
5. Report image mang evaluator Vertex trong DB cÃ³ zero assets/eligible_count=0; Ä‘iá»u nÃ y chá»©ng minh mapping Ä‘áº§u vÃ o khÃ´ng Ä‘á»§, KHÃ”NG chá»©ng minh má»™t Vertex request thá»±c Ä‘Ã£ tháº¥t báº¡i. Sau Ä‘Ã³ cÃ³ manual operator reports pass; cÃ¡c summary nÃ y khÃ´ng Ä‘á»§ chá»©ng minh configured automatic QC.
6. Approval guard chá»‰ kiá»ƒm tra digest/score/verdict; chÆ°a kiá»ƒm tra coverage, eligible references, current file bytes, evaluator/model/rubric policy. Cache cÃ³ thá»ƒ giá»¯ report cÅ© sau Ä‘á»•i reference/policy.
7. Renderer Ä‘á»c reference_image_assets nhÆ°ng FramePrompt dÃ¹ng reference_asset_ids; fallback cÃ³ thá»ƒ gá»­i áº£nh chÆ°a Ä‘á»§ Ä‘iá»u kiá»‡n. Provider hiá»‡n gá»­i má»™t áº£nh reference Ä‘áº§u tiÃªn.
8. JSON cá»§a PI adapter cÃ³ raw_result/assets_mapping; tests QC chá»§ yáº¿u dÃ¹ng resource_pack.assets. Fake evaluator tráº£ score nhÆ°ng consumer dÃ¹ng total_score. CÃ³ evaluator_fixed.py khÃ´ng Ä‘Æ°á»£c runtime import.

## Luá»“ng má»¥c tiÃªu vÃ  quyá»n chi phÃ­

READY â†’ research/resource pack â†’ image QC â†’ AwaitingProductLock â†’ human approve â†’ Brief gate â†’ Scene Plan gate â†’ Storyboard gate + render/video-QC authorization â†’ render/composition â†’ video QC â†’ AwaitingFinalApproval â†’ human approve â†’ export.

KhÃ´ng thÃªm HITL gate thá»© sÃ¡u. Khi chÆ°a Ä‘Æ°á»£c cáº¥p quyá»n QC, workflow cÃ³ thá»ƒ á»Ÿ waiting gate vá»›i QC=pending, nhÆ°ng approve bá»‹ cháº·n. QC fail/unknown giá»¯ workflow Ä‘á»ƒ sá»­a/re-QC cÃ³ chá»§ Ä‘Ã­ch; khÃ´ng tiáº¿p tá»¥c ná»™i dung/export.

MVP thÃªm lá»‡nh CLI `qc <workflow_id> --stage image|video` dÃ¹ng QC service cá»§a bounded context. Lá»‡nh chá»‰ cháº¡y cÃ³ phÃ­ sau xÃ¡c nháº­n scope/háº¡n má»©c; khÃ´ng approve. Worker gá»i cÃ¹ng service táº¡i cuá»‘i resource-pack/render náº¿u cÃ³ authorization há»£p lá»‡. Worker/CLI cháº¡y Ä‘á»“ng thá»i pháº£i claim cÃ¹ng idempotency key, khÃ´ng táº¡o hai láº§n evaluation.

ThÃªm `--authorize-cost --max-cost-usd <amount>` cho qc; giá»¯ Gate 4 authorization hiá»‡n há»¯u nhÆ°ng scope pháº£i bao gá»“m cÃ¡c scene render vÃ  video QC Ä‘Ã£ dá»± tÃ­nh. DÃ¹ng ledger/admission hiá»‡n cÃ³, khÃ´ng dá»±ng budget framework khÃ¡c. KhÃ´ng biáº¿t upper-bound chi phÃ­ hoáº·c model khÃ´ng kháº£ dá»¥ng: dá»«ng trÆ°á»›c call, khÃ´ng tá»± giáº£ giÃ¡. KhÃ´ng coi má»™t boolean authorization lÃ  quyá»n chi phÃ­ vÃ´ háº¡n.

## Task 1 â€” Chuáº©n hÃ³a Ä‘Ãºng há»£p Ä‘á»“ng PI vÃ  reference manifest (1â€“2 giá»)

**Modify:** hermes_personal/product_video/qc/normalization.py, models.py, handlers.py.
**Tests:** tests/hermes_personal/product_video/test_product_identity.py; create test_qc_runtime_contract.py.

- [ ] Táº¡o fixture tá»« cáº¥u trÃºc artifact PI thá»±c, Ä‘Ã£ bá» secrets vÃ  dá»¯ liá»‡u khÃ´ng cáº§n thiáº¿t; cover envelope raw_result, resource_pack, assets_mapping vÃ  media fields thá»±c cÃ³. KhÃ´ng suy Ä‘oÃ¡n má»™t schema má»›i.
- [ ] DÃ¹ng má»™t adapter Ä‘á»ƒ normalize envelope thÃ nh identity + verified claims + local media manifest. Identity báº¯t buá»™c brand/model, variant khi cÃ³; exact canonical matching vá»›i alias rÃµ rÃ ng. T13 ANC khÃ´ng Ä‘Æ°á»£c match T13 ANC2 báº±ng substring.
- [ ] Chuá»—i key_features pháº£i xá»­ lÃ½ thÃ nh claim hoÃ n chá»‰nh, khÃ´ng thÃ nh list kÃ½ tá»±. Chá»‰ dÃ¹ng claims cÃ³ tráº¡ng thÃ¡i/evidence phÃ¹ há»£p vá»›i PI contract; thiáº¿u chá»©ng cá»© thÃ¬ bá» claim, khÃ´ng bá»‹a.
- [ ] Tá»« chá»‘i display_name chung/internal ID. Khi brand/model rÃµ, táº¡o display_name tá»« canonical fields, khÃ´ng láº¥y seller/shop lÃ m tÃªn sáº£n pháº©m.
- [ ] Manifest chá»©a asset_id, local path, actual SHA-256, source provenance. File thiáº¿u/empty/khÃ´ng decode Ä‘Æ°á»£c khÃ´ng eligible. Remote assets pháº£i Ä‘Æ°á»£c materialize qua Ä‘Æ°á»ng download hiá»‡n cÃ³ trÆ°á»›c QC; khÃ´ng Ä‘á»ƒ renderer tá»± thay URL/bytes sau QC.
- [ ] Media á»Ÿ Ä‘Ã¢y lÃ  candidates, chÆ°a gá»i approved_media cho Ä‘áº¿n khi QC pass. TÃ¡ch candidate manifest vÃ  eligible manifest trong artifact.

Regression tá»‘i thiá»ƒu:

```python
def test_model_variant_is_not_substring_match():
    with pytest.raises(ValueError):
        normalize_product_identity(
            {"brand": "QCY", "model": "T13 ANC2"},
            source_context={"brand": "QCY", "model": "T13 ANC"},
        )
```

- [ ] Cháº¡y test má»›i Ä‘á», triá»ƒn khai adapter nhá» nháº¥t, cháº¡y xanh:
  `uv run pytest tests/hermes_personal/product_video/test_product_identity.py tests/hermes_personal/product_video/test_qc_runtime_contract.py -q`.

**Done:** resource pack thá»±c cho ra >=2 áº£nh candidates Ä‘á»c Ä‘Æ°á»£c, identity Ä‘Ãºng, khÃ´ng empty assets do máº¥t envelope.

## Task 2 â€” Má»™t evaluator contract nghiÃªm ngáº·t, hai rubric sáº¡ch branding (1â€“2 giá»)

**Modify:** qc/evaluator.py, rubric.py, image_qc.py, video_qc.py, models.py.
**Tests:** test_image_qc.py, test_video_qc.py; create test_qc_response_contract.py.

- [ ] Chuáº©n hÃ³a Ä‘Ãºng field `total_score` cho active evaluator vÃ  fake test evaluator. KhÃ´ng chuyá»ƒn verdict sang pass khi thiáº¿u dá»¯ liá»‡u. KhÃ´ng chá»n evaluator_fixed.py chá»‰ vÃ¬ tÃªn fixed; sau kiá»ƒm tra call sites, bá» báº£n thá»«a trong pháº¡m vi source nÃ y hoáº·c há»£p nháº¥t vá» má»™t parser.
- [ ] Validate required fields, real bool hard_failure, int score (khÃ´ng bool), component bounds, sum=total, enum verdict, source_branding_detected vÃ  identity_mismatch booleans. Parse/schema error, unavailable evaluator, timeout â†’ unknown; khÃ´ng eligible.
- [ ] Rubric version má»›i; ghi model identifier, evaluator version, provider mode, policy version vÃ o report.
- [ ] Image hard failure cho seller/shop/source watermark, marketplace UI, unrelated logos, wrong identity. Video Ã¡p dá»¥ng cÃ¹ng luáº­t cho má»—i scene, dÃ¹ tá»•ng Ä‘iá»ƒm >=80.
- [ ] Sá»­a render prompt tá»« â€œban má»i readable textâ€ thÃ nh ban source/seller overlays. Cho phÃ©p nhÃ£n/logo váº­t lÃ½ tháº­t thuá»™c approved product identity; khÃ´ng cho seller text chá»‰ vÃ¬ náº±m trÃªn áº£nh reference.
- [ ] KhÃ´ng coi â‰¥80 lÃ  xÃ¡c suáº¥t Ä‘Ãºng 80%; Ä‘Ã¢y lÃ  rubric score. PASS = Ä‘á»§ coverage + score >=80 + khÃ´ng hard failure/unknown.

Interface parser ná»™i bá»™ Ä‘á» xuáº¥t, khÃ´ng pháº£i public/core tool:

```python
validate_qc_response(raw: dict, stage: QCStage) -> dict
```

Test hÃ nh vi tá»‘i thiá»ƒu:

```python
@pytest.mark.parametrize("bad", [
    {"total_score": 95, "verdict": "pass"},
    {"total_score": 95, "verdict": "pass", "hard_failure": "false"},
])
def test_incomplete_response_never_becomes_pass(bad):
    with pytest.raises(ValueError):
        validate_qc_response(bad, QCStage.IMAGE)
```

- [ ] ThÃªm full-schema response score95 + source_branding_detected=true pháº£i FAIL; product-brand label tháº­t khÃ´ng tá»± hard-fail.
- [ ] Cháº¡y `uv run pytest tests/hermes_personal/product_video/test_qc_response_contract.py tests/hermes_personal/product_video/test_image_qc.py tests/hermes_personal/product_video/test_video_qc.py -q`.

**Done:** malformed/missing fields khÃ´ng thá»ƒ pass; seller contamination bá»‹ cháº·n á»Ÿ input láº«n output.

## Task 3 â€” Bind report vá»›i bytes/policy vÃ  siáº¿t approval guard (1â€“2 giá»)

**Modify:** qc/repository.py, models.py, image_qc.py, video_qc.py; application/operator_handler.py; storage/sqlite.py náº¿u cáº§n schema migration.
**Tests:** create test_qc_approval_guards.py; extend test_qc_runtime_contract.py.

- [ ] Schema migration additive, báº£o toÃ n report cÅ©; schema initialization khÃ´ng commit transaction approve Ä‘ang má»Ÿ. KhÃ´ng reset DB.
- [ ] Má»™t fingerprint chung cho producer/cache/guard: workflow + artifact ID/version + canonical identity/claims + current media SHA manifest + approved scene plan/storyboard digest khi video + evaluator/model/rubric/policy versions. Video thÃªm SHA thá»±c cá»§a MP4.
- [ ] Äá»c hash tá»« file hiá»‡n táº¡i, khÃ´ng chá»‰ tin sha256 trong artifact payload. DÃ¹ng cÃ¹ng envelope adapter khi resolve artifact á»Ÿ worker vÃ  guard.
- [ ] Cache reuse chá»‰ khi toÃ n fingerprint trÃ¹ng vÃ  coverage Ä‘áº¡t. Äá»•i bytes cÃ¹ng path, reference list, identity, storyboard hoáº·c policy pháº£i invalidation.
- [ ] Configured gate chá»‰ nháº­n report cá»§a evaluator configured Ä‘ang chá»n vÃ  Ä‘á»§ item/scene detail. Fake/manual operator_* summary giá»¯ lÃ m lá»‹ch sá»­ nhÆ°ng khÃ´ng thay automatic report. KhÃ´ng chá»n latest report chá»‰ dá»±a timestamp.
- [ ] Product Lock: >=2 eligible item hashes khá»›p bytes hiá»‡n táº¡i. Final: technical PASS, má»i approved scene cÃ³ Ä‘á»§ samples vÃ  visual PASS; score >=80, khÃ´ng HF/unknown.
- [ ] Verify guard trá»±c tiáº¿p backend, khÃ´ng chá»‰ CLI. Má»™t approve bá»‹ tá»« chá»‘i khÃ´ng Ä‘á»•i workflow version, approval status hoáº·c enqueue downstream job.
- [ ] Tests stale file hash, fake evaluator, manual summary, wrong model/rubric, missing coverage vÃ  concurrent expected_version.
- [ ] Cháº¡y `uv run pytest tests/hermes_personal/product_video/test_qc_approval_guards.py tests/hermes_personal/product_video/test_qc_runtime_contract.py -q`.

**Done:** pass report cá»§a dá»¯ liá»‡u khÃ¡c/cÅ© hoáº·c thiáº¿u coverage khÃ´ng má»Ÿ khÃ³a gate.

## Task 4 â€” Ná»‘i QC producer vÃ  enforce reference táº¡i provider boundary (2â€“3 giá»)

**Modify:** product_video/handlers.py, cli.py, qc/image_qc.py, qc/video_qc.py; integrations/video_factory/server.py, repository.py; use existing workflows/budgets.py admission API.
**Create:** product_video/qc/service.py (má»ng, orchestration riÃªng cá»§a QC, khÃ´ng pháº£i brain má»›i).
**Tests:** create test_qc_pipeline_e2e.py; extend test_cli_video_commands.py, test_crash_recovery_boundaries.py, tests/mcp_servers/test_video_factory_paid_contract.py.

- [ ] QC service nháº­n workflow/stage/current artifact vÃ  authorization reference; load durable inputs, claim idempotency key, reserve estimated maximum budget, execute evaluator, persist report/manifest, reconcile known spend. Missing authorization tá»« chá»‘i trÆ°á»›c evaluator call.
- [ ] CLI qc vÃ  worker gá»i cÃ¹ng service. Start/resource-pack khÃ´ng tá»± tiÃªu tiá»n khi chá»‰ cÃ³ quyá»n PI import/research. status in pending/fail/unknown/pass, reason/report ID, eligible count; khÃ´ng in READY cho gate chÆ°a QC.
- [ ] Khi image pass, lÆ°u immutable eligible-reference manifest gáº¯n pack version; lock/import VF project dÃ¹ng manifest nÃ y. KhÃ´ng gá»­i táº¥t cáº£ candidates.
- [ ] Renderer resolve reference_asset_ids Ä‘Ãºng field domain, báº¯t buá»™c náº±m trong manifest vÃ  hash cÃ²n khá»›p. Explicit reference path override cÅ©ng pháº£i kiá»ƒm tra manifest; khÃ´ng bypass qua fallback.
- [ ] VÃ¬ provider hiá»‡n dÃ¹ng má»™t reference áº£nh, chá»n deterministic má»™t eligible asset cho tá»«ng scene; lÆ°u actual selected asset ID/hash trong render provenance. KhÃ´ng tuyÃªn bá»‘ gá»­i ba áº£nh khi request chá»‰ cÃ³ má»™t.
- [ ] Video QC láº¥y boundaries tá»« approved scene durations, khÃ´ng chia Ä‘á»u máº·c Ä‘á»‹nh. Extract Ä‘Ãºng ba frames 15/50/85% cho má»—i scene; thiáº¿u frame/reference/scene intent â†’ unknown/fail, khÃ´ng ghi coverage thÃ nh cÃ´ng.
- [ ] Decode toÃ n bá»™ MP4, validate 720x1280, approved duration tolerance0.5s, codec/output requirement. Audio optional pháº£i mÃ´ táº£ lÃ  silent náº¿u khÃ´ng cÃ³, khÃ´ng tá»± ghi audio-sync pass.
- [ ] Persist má»—i accepted scene operation ID trÆ°á»›c submit tiáº¿p theo; resume poll accepted operations, khÃ´ng tá»± resubmit ambiguous jobs. Composition dÃ¹ng stable digest filename/version, khÃ´ng dÃ¹ng Python hash(). ÄÃ¢y lÃ  má»©c recovery tá»‘i thiá»ƒu trÃ¡nh duplicate paid scenes, khÃ´ng xÃ¢y retry framework má»›i.
- [ ] Rerender lÃ  version/run má»›i cÃ³ authorization má»›i; khÃ´ng overwrite MP4/export cÅ©. Má»™t scene fail khÃ´ng tá»± render cáº£ batch láº§n hai.
- [ ] Offline E2E temp HERMES_HOME + real SQLite + actual entrypoints + injected evaluator/provider transport: image pass â†’ ngÆ°á»i approve â†’ render â†’ video pass â†’ ngÆ°á»i approve â†’ export. HF branding pháº£i dá»«ng; fake mode chá»‰ chá»©ng minh wiring, khÃ´ng live cháº¥t lÆ°á»£ng.
- [ ] `uv run pytest tests/hermes_personal/product_video/test_qc_pipeline_e2e.py tests/hermes_personal/product_video/test_cli_video_commands.py tests/hermes_personal/product_video/test_crash_recovery_boundaries.py tests/mcp_servers/test_video_factory_paid_contract.py -q`.

**Done:** Ä‘Ã£ cÃ³ runtime producer thá»±c; renderer khÃ´ng thá»ƒ dÃ¹ng rejected reference; resume khÃ´ng nhÃ¢n Ä‘Ã´i accepted operation.

## Task 5 â€” Má»™t caption/export truth, provenance Ä‘á»§ dÃ¹ng (0.5â€“1 giá»)

**Modify:** integrations/video_factory/server.py; product_video/handlers.py, cli.py; docs/hermes-personal/product-video-runbook.md.
**Tests:** test_cli_video_commands.py, test_happy_path_e2e.py, test_qc_pipeline_e2e.py.

- [ ] Caption sinh tá»« locked canonical identity/verified claims, CTA trung tÃ­nh â€œXem thÃ´ng tin sáº£n pháº©mâ€. KhÃ´ng há»©a chÃ­nh hÃ£ng, tráº£i nghiá»‡m chÃ¢n thá»±c, giÃ¡/giá» hÃ ng/khuyáº¿n mÃ£i khÃ´ng Ä‘Æ°á»£c chá»©ng thá»±c; khÃ´ng seller source branding/#review.
- [ ] Bá» CLI template cÅ©. status/approve hiá»ƒn thá»‹ caption file chÃ­nh thá»©c qua export artifact; chÆ°a cÃ³ caption thÃ¬ bÃ¡o chÆ°a export, khÃ´ng sinh báº£n thay tháº¿ gÃ¢y lá»‡ch.
- [ ] Adapter export promote file_path, caption_path, metadata_path, sha256 tá»« raw result lÃªn canonical artifact; há»— trá»£ Ä‘á»c payload cÅ© Ä‘á»ƒ xem lá»‹ch sá»­, khÃ´ng rewrite lá»‹ch sá»­.
- [ ] Metadata chá»©a identity/run version, source provenance, 5 approval IDs, selected ref IDs/hashes, image/video QC report IDs vÃ  evaluator/model/policy, scene operation IDs, render plan hash, final MP4 SHA, duration/resolution/fps/audio presence.
- [ ] Validate export final bytes cÃ²n Ä‘Ãºng video-QC hash trÆ°á»›c copy; thay file sau Final/QC pháº£i bá»‹ cháº·n. Caption/metadata khÃ´ng Ä‘Æ°á»£c dÃ¹ng pack/project ID lÃ m tÃªn sáº£n pháº©m.
- [ ] Regression CLI caption output báº±ng ná»™i dung export file; fake old source_context khÃ´ng lÃ m xuáº¥t template â€œgiá» hÃ ngâ€.
- [ ] `uv run pytest tests/hermes_personal/product_video/test_cli_video_commands.py tests/hermes_personal/product_video/test_happy_path_e2e.py tests/hermes_personal/product_video/test_qc_pipeline_e2e.py -q`.

**Done:** user copy caption tá»« CLI hay file Ä‘á»u cÃ¹ng má»™t ná»™i dung sáº¡ch.

## Task 6 â€” Chá»©ng minh má»™t live happy case (operator phá»‘i há»£p, thá»i gian provider phá»¥ thuá»™c)

**Update:** docs/hermes-personal/product-video-runbook.md; create reports/runtime-truth/2026-09-16-product-video-qc-live-acceptance.md.

- [ ] TrÆ°á»›c live: cháº¡y toÃ n tests Product Video, full Hermes Personal, Ruff. Ghi counts thá»±c; khÃ´ng Ã©p counts176/758.
- [ ] Read-only preflight xÃ¡c nháº­n paths DB/workspace/config/model/ADC project; khÃ´ng in credentials. Kiá»ƒm tra candidate pack khÃ´ng rejected, identity rÃµ, >=2 áº£nh candidates tháº­t sáº¡ch. Giá»¯ job rejected/quarantined lÃ m lá»‹ch sá»­, khÃ´ng Ã©p chÃºng thÃ nh ready.
- [ ] Operator cáº¥p ngÃ¢n sÃ¡ch cá»¥ thá»ƒ cho image QC vÃ  tá»‘i Ä‘a má»™t run render/video QC; ghi run/workflow, scope, expiry, reserve/estimated maximum. Náº¿u chÆ°a cÃ³ thÃ¬ hoÃ n táº¥t pháº§n code vÃ  dá»«ng live, khÃ´ng tuyÃªn bá»‘ happy case passed.
- [ ] Cháº¡y image QC configured trÆ°á»›c, xÃ¡c nháº­n item assets/hashes vÃ  eligible refs thá»±c. Náº¿u fail/unknown: sá»­a nguá»“n/contract hoáº·c chá»n candidate sáº¡ch, khÃ´ng manual score Ä‘á»ƒ vÆ°á»£t guard.
- [ ] Operator xem vÃ  duyá»‡t riÃªng Product Lock, Brief, Scene Plan, Storyboard. Storyboard approval pháº£i kÃ¨m valid cost authorization. Chá»‰ má»™t workflow.
- [ ] Render táº¥t cáº£ approved scenes má»™t láº§n, poll/composite rá»“i configured video QC. Seller watermark/identity mismatch fail pháº£i giá»¯ Final chÆ°a duyá»‡t, khÃ´ng auto repair/rerender cÃ³ phÃ­.
- [ ] Operator xem toÃ n bá»™ MP4 vÃ  duyá»‡t Final náº¿u hÃ i lÃ²ng. Export ra paths thá»±c; verify SHA/bytes/decode/duration/resolution, caption vÃ  metadata.
- [ ] Resume/status/repeat qc vá»›i inputs khÃ´ng Ä‘á»•i khÃ´ng táº¡o duplicate render/evaluation Ä‘Ã£ hoÃ n táº¥t. DÃ¹ng offline test cho crash giá»¯a hai submits, khÃ´ng deliberately phÃ¡ live Ä‘á»ƒ tá»‘n tiá»n.
- [ ] BÃ¡o evidence table: workflow/run IDs, 5 approval IDs, image item scores/eligible hashes, scene IDs/timestamps/verdicts, actual provider/model, final paths/SHA/spec/audio, budget authorization/spend known/unknown. PhÃ¢n biá»‡t rÃµ unit/integration/live/operator visual inspection.

Verification commands (PowerShell):

```powershell
uv run pytest tests/hermes_personal/product_video -q
uv run pytest tests/hermes_personal -q
uv run ruff check hermes_personal tests/hermes_personal
uv run python -m hermes_personal.product_video.cli --help
uv run python -m hermes_personal.product_video.cli qc --help
```

Live lá»‡nh cá»¥ thá»ƒ vá»›i product/workflow IDs tháº­t vÃ  budget tháº­t pháº£i ghi vÃ o evidence sau khi operator chá»n/cáº¥p quyá»n; khÃ´ng Ä‘Æ°a placeholder command rá»“i coi lÃ  Ä‘Ã£ cháº¡y. Agent khÃ´ng tá»± chá»n giÃ¡ tiá»n hay báº¥m approve.

## Acceptance / release decision

- **Code-ready:** tasks1â€“5 pass focused + full tests, no paid API, actual producer/guard/provider path covered offline.
- **Happy-case-ready:** task6 thá»±c sá»± hoÃ n táº¥t; MP4 khÃ´ng seller branding theo configured sampling QC vÃ  operator full watch; caption Ä‘Ãºng; metadata/approvals nháº¥t quÃ¡n.
- KhÃ´ng gá»i production-ready hoáº·c daily unattended video factory. CÃ¡c gate váº«n cáº§n ngÆ°á»i approve; daily PI import vÃ  táº¡o video cÃ³ operator lÃ  hai pháº¡m vi khÃ¡c nhau.

## Thá»i gian vÃ  handoff

Æ¯á»›c lÆ°á»£ng tá»« cÃ¡c gap source hiá»‡n táº¡i: **6.5â€“11 giá» coding/offline verification**, sau Ä‘Ã³ **1â€“3 giá» live/operator/provider**, khÃ´ng pháº£i SLA. CÃ³ thá»ƒ chia má»™t ngÃ y táº­p trung + phiÃªn live; khÃ´ng há»©a hoÃ n táº¥t hÃ´m nay náº¿u quyá»n ngÃ¢n sÃ¡ch, model kháº£ dá»¥ng hoáº·c approvals chÆ°a cÃ³.

Æ¯u tiÃªn task1â€“4 trÆ°á»›c render tiáº¿p theo, task5 trÆ°á»›c export. Task6 chá»‰ khi guard/allowlist/wiring Ä‘Ã£ xanh. KhÃ´ng chá»‰ sá»­a prompt rá»“i tráº£ tiá»n rerender â€œMinh Gearâ€ ngay.

Implementing agent bÃ¡o checkpoint sau task3 vÃ  task5, kÃ¨m diff/tests/blockers; tiáº¿p tá»¥c cÃ¡c bÆ°á»›c khÃ´ng tá»‘n phÃ­ trong scope. Chá»‰ pause khi thiáº¿u quyá»n chi phÃ­, operator approval, hoáº·c cáº§n má»Ÿ rá»™ng kiáº¿n trÃºc; khÃ´ng há»i láº¡i thiáº¿t káº¿ Ä‘Ã£ chá»‘t chá»‰ Ä‘á»ƒ kÃ©o dÃ i.

