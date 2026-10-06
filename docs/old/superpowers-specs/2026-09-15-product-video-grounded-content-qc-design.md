> **Status: Historical** — This document is superseded by [Product Video Master Spec](product-video-master-spec.md). Do not use as implementation target.

---

# MVP Product Video â€” ná»™i dung cÃ³ cÄƒn cá»© vÃ  QC

Tráº¡ng thÃ¡i: Ä‘á» xuáº¥t Ä‘á»ƒ ngÆ°á»i dÃ¹ng duyá»‡t trÆ°á»›c implementation plan chi tiáº¿t.

## Goal

Má»™t sáº£n pháº©m tháº­t tá»« READY batch Ä‘i qua Hermes/MCP configured, cÃ³ ná»™i dung bÃ¡m Ä‘Ãºng identity vÃ  claims, QC áº£nh vÃ  QC video cÃ³ káº¿t quáº£ lÆ°u bá»n vá»¯ng, Ä‘á»§ nÄƒm human approvals, xuáº¥t video dá»c thá»±c hiá»‡n toÃ n bá»™ storyboard Ä‘Ã£ duyá»‡t cÃ¹ng caption vÃ  metadata. NgÆ°á»i dÃ¹ng Ä‘Äƒng thá»§ cÃ´ng.

## Baseline Ä‘Ã£ audit

- Workflow Jisulife Ä‘Ã£ xuáº¥t composite MP4 16 giÃ¢y, 720x1280, H.264, decode 384 frames; báº£n ghÃ©p Ä‘Æ°á»£c kiá»ƒm tra khÃ´ng cÃ³ audio stream.
- Brief váº«n dÃ¹ng tÃªn chung "Sáº£n pháº©m cÃ´ng nghá»‡ tiá»‡n Ã­ch"; claims vÃ  verified_selling_points rá»—ng.
- Storyboard prompt trá»™n Viá»‡tâ€“Anh, camera/lighting/identity constraints rá»—ng.
- Caption trÃªn Ä‘Ä©a báº¯t Ä‘áº§u báº±ng pack ID; metadata chÆ°a cÃ³ Ä‘áº§y Ä‘á»§ nÄƒm approval IDs vÃ  scene operation IDs.
- Importer dÃ¹ng match_score >= 0.5, PI matcher lÃ  text metadata matching. ChÆ°a tÃ¬m tháº¥y QC vision báº¯t buá»™c trong Ä‘Æ°á»ng cháº¡y.
- Baseline lÃ  káº¿t quáº£ audit trÆ°á»›c, khÃ´ng thay tháº¿ kiá»ƒm tra source/runtime khi báº¯t Ä‘áº§u triá»ƒn khai; source Ä‘ang Ä‘Æ°á»£c thay Ä‘á»•i ngoÃ i phiÃªn review.

## Chá»n cÃ¡ch lÃ m

1. QC vision qua adapter má»ng trong bounded Product Video (Ä‘á» xuáº¥t): tÃ¡i sá»­ dá»¥ng configured multimodal provider hoáº·c MCP Ä‘Ã¡nh giÃ¡ Ä‘Ã£ cÃ³; lÆ°u report vÃ o SQLite. Ãt háº¡ táº§ng vÃ  cÃ³ precondition tháº­t.
2. QC thá»§ cÃ´ng: nhanh hÆ¡n, nhÆ°ng chá»‰ lÃ  checkpoint ngÆ°á»i kiá»ƒm tra; khÃ´ng Ä‘áº¡t yÃªu cáº§u QC tá»± Ä‘á»™ng 80%.
3. QC agent/MCP server Ä‘á»™c láº­p má»›i: thÃªm deployment/config/recovery; khÃ´ng chá»n cho happy-case MVP.

Má»™t Hermes váº«n Ä‘iá»u phá»‘i. KhÃ´ng táº¡o general-purpose brain má»›i. Provider QC pháº£i Ä‘Æ°á»£c xÃ¡c nháº­n kháº£ dá»¥ng á»Ÿ preflight; khÃ´ng máº·c Ä‘á»‹nh Vertex Veo cÅ©ng lÃ  provider Ä‘Ã¡nh giÃ¡ áº£nh/video. Settings hÃ nh vi vÃ o config.yaml; credentials giá»¯ á»Ÿ secret store. ChÆ°a chá»n tÃªn model trÆ°á»›c khi kiá»ƒm tra provider hiá»‡n cÃ³.

## Ranh giá»›i

- Giá»¯ Ä‘á»§ Product Lock, Brief, Scene Plan, Storyboard vÃ  Final approval.
- QC khÃ´ng tá»± approve; operator lÃ  ngÆ°á»i Ä‘Æ°a quyáº¿t Ä‘á»‹nh cuá»‘i cÃ¹ng.
- KhÃ´ng phÃ¡t sinh paid render hoáº·c metered QC call trÆ°á»›c quyá»n chi phÃ­ thÃ­ch há»£p.
- KhÃ´ng thÃªm UI, broker, multi-user, upload TikTok hay sá»­a PI toÃ n diá»‡n.
- KhÃ´ng xÃ³a/reuse workflow completed hoáº·c output cÅ© Ä‘á»ƒ che lá»‹ch sá»­; live case má»›i pháº£i dÃ¹ng identity vÃ  output riÃªng, theo kháº£ nÄƒng rerun cÃ³ chá»§ Ä‘Ã­ch cá»§a source hiá»‡n táº¡i.
- KhÃ´ng bá»‹a claims; pack IDs khÃ´ng Ä‘Æ°á»£c dÃ¹ng nhÆ° tÃªn sáº£n pháº©m.

## Luá»“ng dá»¯ liá»‡u

READY product â†’ research/draft pack â†’ image QC â†’ AwaitingProductLock â†’ lock pack â†’ grounded brief â†’ AwaitingBriefApproval â†’ scenes â†’ AwaitingSceneApproval â†’ detailed storyboard/render plan â†’ AwaitingStoryboardApproval + cost authorization â†’ scene renders â†’ composition â†’ technical/visual video QC â†’ AwaitingFinalApproval â†’ deterministic export.

QC failed/unknown: lÆ°u report vÃ  lÃ½ do, cháº·n approve; khÃ´ng fake pass, khÃ´ng Ã¢m tháº§m auto-rerender. Chá»‰ Ä‘á» nghá»‹ revise/rerender vá»›i authorization má»›i khi cáº§n.

## Product identity vÃ  ná»™i dung

Táº¡o má»™t normalized product view tá»« cáº¥u trÃºc canonical cá»§a PI vÃ  source context Ä‘Ã£ Ä‘á»‘i chiáº¿u. Gá»“m brand, model, variant, display_name, approved media vÃ  evidence-backed claims. KhÃ¡c biá»‡t identity giá»¯a nguá»“n vÃ  pack pháº£i cháº·n; khÃ´ng fallback thÃ nh tÃªn chung rá»“i tiáº¿p tá»¥c live render.

Display_name dÃ¹ng brand/model/name, khÃ´ng láº¥y resource_pack_id. Náº¿u claims rá»—ng, brief chá»‰ mÃ´ táº£ danh tÃ­nh vÃ  quan sÃ¡t áº£nh Ä‘Æ°á»£c duyá»‡t; khÃ´ng thÃªm hiá»‡u nÄƒng, pin, Æ°u Ä‘Ã£i, chÃ­nh hÃ£ng hoáº·c tráº£i nghiá»‡m sá»­ dá»¥ng chÆ°a Ä‘Æ°á»£c xÃ¡c nháº­n.

Scene vÃ  prompt pháº£i chá»‰ rÃµ ná»™i dung/action/camera/lighting, identity constraints, reference asset Ä‘Ã£ duyá»‡t vÃ  duration. Prompt tiáº¿ng Anh lÃ  yÃªu cáº§u Ä‘áº§u ra Ä‘Æ°á»£c kiá»ƒm tra; khÃ´ng dÃ¹ng label tiáº¿ng Anh cá»™ng content tiáº¿ng Viá»‡t rá»“i gá»i lÃ  prompt chuyÃªn biá»‡t.

KhÃ´ng báº¯t buá»™c agent sÃ¡ng táº¡o tá»± do cho MVP. CÃ³ thá»ƒ dÃ¹ng cáº¥u trÃºc prompt cá»‘ Ä‘á»‹nh, nhÆ°ng cÃ¡c trÆ°á»ng pháº£i thá»±c sá»± bÃ¡m dá»¯ liá»‡u sáº£n pháº©m vÃ  tá»«ng cáº£nh; khÃ´ng mÃ´ táº£ template nhÆ° chuyÃªn gia AI Ä‘á»™c láº­p.

## Image QC

ÄÃ¡nh giÃ¡ tá»«ng áº£nh báº±ng vision, Ä‘á»‘i chiáº¿u identity má»¥c tiÃªu vÃ  evidence: product likeness, model/variant conflict, áº£nh rÃµ/Ä‘á»§ tháº¥y sáº£n pháº©m, cháº¥t lÆ°á»£ng sá»­ dá»¥ng lÃ m reference. Text metadata score giá»¯ riÃªng, khÃ´ng coi lÃ  vision confidence.

Rubric 0â€“100: identity/evidence 60, clarity 25, reference usability 15. Eligible khi total >= 80, khÃ´ng hard failure vÃ  káº¿t quáº£ khÃ´ng unknown. Score lÃ  rubric Ä‘Ã¡nh giÃ¡, khÃ´ng pháº£i xÃ¡c suáº¥t Ä‘Ãºng model. Wrong brand/model/variant lÃ  hard failure báº¥t ká»ƒ total.

KhÃ´ng Ä‘á»§ báº±ng chá»©ng phÃ¢n biá»‡t model tá»« áº£nh: unknown, khÃ´ng tá»± chuyá»ƒn thÃ nh pass; cáº§n evidence/áº£nh khÃ¡c vÃ  Ä‘Ã¡nh giÃ¡ láº¡i. Operator váº«n xem áº£nh vÃ  report khi Product Lock.

Chá»‰ eligible assets Ä‘Æ°á»£c dÃ¹ng render. Ãt nháº¥t hai áº£nh eligible Ä‘á»ƒ giá»¯ Ä‘iá»u kiá»‡n admission hiá»‡n cÃ³. KhÃ´ng chá»‰ sá»­a threshold 0.5 thÃ nh 0.8 rá»“i gá»i lÃ  vision QC.

## Video QC

Technical: file cÃ³ video stream, decode toÃ n bá»™ thÃ nh cÃ´ng, dimensions 720x1280, duration Ä‘Ãºng approved render plan vá»›i dung sai 0.5 giÃ¢y, scenes Ä‘á»§/thá»© tá»± Ä‘Ãºng. Audio optional cho MVP silent video; report/metadata pháº£i ghi rÃµ cÃ³ hay khÃ´ng. KhÃ´ng tuyÃªn bá»‘ voiceover hoáº·c audio náº¿u chÆ°a Ä‘Æ°á»£c kiá»ƒm tra.

Visual sampling: Ã­t nháº¥t ba thá»i Ä‘iá»ƒm trong má»—i cáº£nh (Ä‘áº§u/giá»¯a/cuá»‘i, trÃ¡nh Ä‘Ãºng boundary), Ä‘á»‘i chiáº¿u approved reference vÃ  má»¥c tiÃªu cáº£nh. Cháº¥m identity consistency 50, scene adherence 30, visual cleanliness 20; pass >= 80 vÃ  khÃ´ng hard failure. Wrong product/variant, scene missing/order wrong hoáº·c biáº¿n dáº¡ng sáº£n pháº©m nghiÃªm trá»ng lÃ  hard failure.

Visual sampling khÃ´ng chá»©ng minh má»i frame Ä‘á»u Ä‘Ãºng. Report ghi timestamps/sample coverage vÃ  giá»›i háº¡n; Final approval váº«n yÃªu cáº§u ngÆ°á»i dÃ¹ng xem video Ä‘áº§y Ä‘á»§.

KhÃ´ng cÃ³ QC report current/pass: cháº·n Final approve, ká»ƒ cáº£ file tá»“n táº¡i vÃ  cÃ³ header MP4.

## Report persistence vÃ  approval binding

QC report cÃ³ report_id, workflow_id, stage, artifact_id/version/digest, reference digests, evaluator/model version, rubric version, timestamp, score, verdict pass/fail/unknown, findings vÃ  sampled timestamps cho video. KhÃ´ng chá»©a secrets.

LÆ°u bá»n vá»¯ng vÃ o SQLite canonical. Artifact hoáº·c reference Ä‘á»•i thÃ¬ report cÅ© khÃ´ng há»£p lá»‡. Product Lock/Final operator handler kiá»ƒm tra report tÆ°Æ¡ng á»©ng trÆ°á»›c mutation/enqueue; CLI khÃ´ng pháº£i lá»›p guard duy nháº¥t.

Timeout, malformed result, provider unavailable â†’ unknown/error, khÃ´ng pass. Replay cÃ¹ng artifact reuse report há»£p lá»‡, khÃ´ng tá»± phÃ¡t sinh inference/render má»›i.

## Render, chi phÃ­ vÃ  output

Giá»¯ multi-scene renderer nhÆ°ng kiá»ƒm tra checkpoint operation ID tá»«ng scene trÆ°á»›c scene tiáº¿p theo; partial submit failure khÃ´ng Ä‘Æ°á»£c lÃ m máº¥t cÃ¡c accepted operation IDs. Resume poll scenes Ä‘Ã£ accepted, skip scenes completed. Outcome khÃ´ng rÃµ pháº£i reconcile trÆ°á»›c resubmit.

Composite/output identity dÃ¹ng digest á»•n Ä‘á»‹nh, khÃ´ng dÃ¹ng Python hash() process-randomized. Duration máº·c Ä‘á»‹nh provider khÃ´ng Ä‘Æ°á»£c Ã¢m tháº§m thay duration ngÆ°á»i dÃ¹ng duyá»‡t; render plan ghi source duration/render duration/trim rÃµ rÃ ng. Tá»•ng scene costs khÃ´ng vÆ°á»£t authorization.

Reconcile cÃ¡c budget reservation cÅ© chá»‰ khi chá»©ng minh owner/scope/provider outcome; giá»¯ vÃ  bÃ¡o unknown outcomes. PhÃ¢n biá»‡t minor units, estimated provider cost vÃ  actual bill; khÃ´ng diá»…n giáº£i amount=50 thÃ nh $50 thiáº¿u cÄƒn cá»©.

Export artifact Ä‘Ã£ Final-approved: MP4, caption vÃ  metadata cÃ³ tÃªn phÃ¢n biá»‡t theo output version. Caption dÃ¹ng Ä‘Ãºng tÃªn/claims Ä‘Ã£ duyá»‡t, khÃ´ng kháº³ng Ä‘á»‹nh cÃ³ giá» hÃ ng/Æ°u Ä‘Ã£i/chÃ­nh hÃ£ng hoáº·c gá»i video AI lÃ  review tráº£i nghiá»‡m tháº­t. Metadata cÃ³ nÄƒm approval refs, QC refs, source batch/product refs, scene operations, media properties vÃ  digest; khÃ´ng gá»i file nÃ y lÃ  chá»©ng nháº­n bÃªn ngoÃ i.

## Khung triá»ƒn khai theo thá»© tá»±

### 1. Baseline vÃ  provider QC preflight

Kiá»ƒm tra active MCP/profile/DB/output, configured multimodal evaluator, dependencies vÃ  authorization. KhÃ´ng gá»i render má»›i. ÄÃ­ch: biáº¿t provider QC cÃ³ dÃ¹ng Ä‘Æ°á»£c hay cáº§n ngÆ°á»i dÃ¹ng cáº¥u hÃ¬nh trÆ°á»›c. Náº¿u chÆ°a cÃ³ provider evaluator usable, bÃ¡o blocker thay vÃ¬ cam káº¿t 4â€“8 giá».

### 2. Identity/claims vÃ  grounded scene/prompt

Sá»­a mapping táº¡i handlers.py; cáº¥u trÃºc frame/prompt táº¡i Video Factory server.py; caption/provenance output. Regression: pack ID khÃ´ng xuáº¥t hiá»‡n nhÆ° tÃªn, mismatch cháº·n, claims rá»—ng khÃ´ng bá»‹a thÃ´ng sá»‘, prompt cÃ³ ná»™i dung cá»¥ thá»ƒ cá»§a scene.

### 3. QC report/evaluator vÃ  gate guards

TÃ¡ch module QC nhá» trong product_video, khÃ´ng tÄƒng god-file. Persistence schema additive; provider adapter reuse cáº¥u hÃ¬nh hiá»‡n cÃ³. Guards Product Lock/Final á»Ÿ operator handler. Regression: <80/unknown/critical mismatch/stale digest Ä‘á»u khÃ´ng enqueue; pass report váº«n khÃ´ng auto-approve.

### 4. Scene resume/composition/budget/output

Kiá»ƒm tra/sá»­a tá»‘i thiá»ƒu accepted-operation checkpoint, stable output naming, timing, budget cumulative/reconciliation vÃ  immutable export packaging. Regression: partial submit failure giá»¯ IDs, restart khÃ´ng resubmit completed scene, output má»›i khÃ´ng ghi Ä‘Ã¨ approved output cÅ©.

### 5. Live happy case vÃ  nghiá»‡m thu

Chá»n má»™t sáº£n pháº©m, Ã­t cáº£nh, render plan Ä‘Æ°á»£c ngÆ°á»i dÃ¹ng duyá»‡t Ä‘á»ƒ háº¡n cháº¿ chi phÃ­. NgÆ°á»i dÃ¹ng duyá»‡t Ä‘á»§ gates; thá»±c hiá»‡n configured image/video QC vÃ  render tháº­t. Decode final toÃ n bá»™, xem coverage tá»«ng cáº£nh, verify metadata/approval/QC digests vÃ  replay. Full pytest Hermes Personal + Ruff sau focused regressions. BÃ¡o cÃ¡o tÃ¡ch live proof, offline proof vÃ  pháº§n chÆ°a kiá»ƒm chá»©ng.

## Má»‘c bÃ n giao vÃ  dá»± toÃ¡n

- Má»‘c 1: ná»™i dung vÃ  output trung thá»±c; cÃ³ thá»ƒ dÃ¹ng manual review táº¡m thá»i nhÆ°ng ghi rÃµ chÆ°a Ä‘áº¡t automatic QC. Dá»± toÃ¡n 2â€“4 giá».
- Má»‘c 2: configured vision QC cÃ³ persistence/gate guards vÃ  má»™t happy case tháº­t. Dá»± toÃ¡n tá»•ng 4â€“8 giá» chá»‰ náº¿u evaluator sáºµn cÃ³ vÃ  Ä‘Æ°á»ng cháº¡y integration khÃ´ng phÃ¡t sinh sá»­a lá»›n. Náº¿u pháº£i tÃ­ch há»£p evaluator/provider má»›i, dá»± toÃ¡n 1â€“2 ngÃ y.
- CÃ¡c Æ°á»›c tÃ­nh chÆ°a báº£o Ä‘áº£m thá»i gian render, pháº£n há»“i approvals, provider quota/cost hoáº·c crash recovery phÃ¡t sinh; re-estimate sau preflight.
- Má»¥c tiÃªu cuá»‘i cÃ¹ng gá»“m cáº£ Má»‘c 2. KhÃ´ng gá»i Má»‘c 1 lÃ  hoÃ n táº¥t QC.

## Definition of Done

- TÃªn/model Ä‘Ãºng xuyÃªn suá»‘t pack â†’ brief â†’ scenes/prompts â†’ caption; claims cÃ³ evidence/approval.
- áº¢nh dÃ¹ng render cÃ³ configured vision QC >=80, khÃ´ng mismatch/unknown; Product Lock chÆ°a duyá»‡t thÃ¬ chÆ°a táº¡o brief.
- Video Ä‘á»§ approved scenes/duration, decode toÃ n bá»™; technical/visual QC pass gáº¯n artifact digest hiá»‡n táº¡i trÆ°á»›c Final approve.
- NÄƒm HITL approvals lÃ  cá»§a ngÆ°á»i dÃ¹ng, render/QC metered cÃ³ authorization; agent khÃ´ng tá»± approve.
- MP4/caption/metadata tá»“n táº¡i, refs/digests nháº¥t quÃ¡n, audio status trung thá»±c.
- Replay khÃ´ng workflow trÃ¹ng hoáº·c resubmit completed scene; reservations khÃ´ng cÃ³ orphan khÃ´ng Ä‘Æ°á»£c giáº£i thÃ­ch.
- Focused regressions, full Hermes Personal tests vÃ  Ruff xanh; live evidence Ä‘Æ°á»£c ghi riÃªng.
- KhÃ´ng tuyÃªn bá»‘ production-ready hoáº·c visual sampling báº£o Ä‘áº£m má»i frame.

## Review gate

NgÆ°á»i dÃ¹ng duyá»‡t thiáº¿t káº¿ nÃ y trÆ°á»›c khi viáº¿t implementation plan chi tiáº¿t cÃ³ exact signatures, code vÃ  test commands. File nÃ y khÃ´ng pháº£i authorization gá»i paid render/QC hoáº·c tá»± approve gates.

