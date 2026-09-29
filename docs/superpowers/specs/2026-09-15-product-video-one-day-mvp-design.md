> **Status: Historical** — This document is superseded by [Product Video Master Spec](product-video-master-spec.md). Do not use as implementation target.

---

# Product Video â€” MVP happy case trong má»™t ngÃ y

## Má»¥c tiÃªu

Má»™t sáº£n pháº©m tá»« READY batch cá»§a Product-Intelligence cháº¡y qua Hermes vá»›i provider configured, Ä‘á»§ cÃ¡c milestone duyá»‡t, xuáº¥t MP4 xem Ä‘Æ°á»£c vÃ  ná»™i dung Ä‘Äƒng thá»§ cÃ´ng. KhÃ´ng dÃ¹ng fake provider lÃ m báº±ng chá»©ng nghiá»‡m thu.

## Thiáº¿t káº¿ Ä‘Ã£ thá»‘ng nháº¥t trong há»™i thoáº¡i

CLI lÃ  giao diá»‡n MVP. TÃ¡i sá»­ dá»¥ng coordinator, worker, SQLite outbox vÃ  operator handler hiá»‡n cÃ³. KhÃ´ng thÃªm brain, broker, dashboard, upload TikTok hoáº·c migration legacy tá»•ng quÃ¡t. UI lÃ  phÆ°Æ¡ng Ã¡n sau MVP; cháº¡y tá»«ng worker báº±ng tay lÃ  phÆ°Æ¡ng Ã¡n cháº©n Ä‘oÃ¡n, khÃ´ng pháº£i UX bÃ n giao.

Product-Intelligence chá»‰ scout vÃ  publish batch háº±ng ngÃ y; khÃ´ng khá»Ÿi Ä‘á»™ng Hermes. Hermes khá»Ÿi Ä‘á»™ng theo yÃªu cáº§u ngÆ°á»i dÃ¹ng, máº·c Ä‘á»‹nh happy case chá»‰ má»™t sáº£n pháº©m.

## Luá»“ng vÃ  giao diá»‡n

1. `hermes personal video list`: Ä‘á»c READY batch vÃ  chá»n sáº£n pháº©m cÃ³ báº±ng chá»©ng model, áº£nh phÃ¹ há»£p.
2. `hermes personal video start --product-keys <key> --provider-mode configured`: research, build Resource Pack vÃ  dá»«ng táº¡i AwaitingProductLock.
3. `status <workflow_id>`: hiá»ƒn thá»‹ stage, approval ID, artifact identity/version, evidence vÃ  Ä‘Æ°á»ng dáº«n media Ä‘á»ƒ kiá»ƒm tra.
4. `approve <approval_id>`: duyá»‡t Ä‘Ãºng artifact, cháº¡y worker cho workflow Ä‘Ã³ Ä‘áº¿n gate tiáº¿p theo. KhÃ´ng duyá»‡t tá»± Ä‘á»™ng cÃ¡c gate phÃ­a sau.
5. Product Lock â†’ Brief â†’ Scene Plan â†’ Storyboard â†’ Final: giá»¯ Ä‘á»§ nÄƒm approval. Paid render chá»‰ cháº¡y sau khi cÃ³ positive cost authorization theo contract hiá»‡n cÃ³; náº¿u chÆ°a cÃ³ UX cáº¥p quyá»n, bá»• sung vÃ o CLI trÆ°á»›c khi render.
6. Sau Final approval: export MP4, metadata vÃ  caption náº¿u provider tráº£ vá»; náº¿u caption chÆ°a Ä‘Æ°á»£c Ä‘Ã³ng gÃ³i, Ä‘Ã³ng gÃ³i tá»« brief Ä‘Ã£ duyá»‡t, khÃ´ng phÃ¡t minh claim má»›i. CLI in Ä‘Æ°á»ng dáº«n tuyá»‡t Ä‘á»‘i cá»§a káº¿t quáº£.

## An toÃ n vÃ  lá»—i

KhÃ´ng táº¡o brief trÆ°á»›c Product Lock. KhÃ´ng dÃ¹ng research result thay Resource Pack. Pack trÆ°á»›c gate pháº£i cÃ³ ID, version, tráº¡ng thÃ¡i lockable vÃ  identity/digest theo contract provider. Thiáº¿u evidence hoáº·c áº£nh sai biáº¿n thá»ƒ pháº£i dá»«ng Ä‘á»ƒ chá»n sáº£n pháº©m khÃ¡c, khÃ´ng ná»›i validation.

Lá»—i provider, timeout hoáº·c export pháº£i tráº£ exit code khÃ¡c 0, in workflow ID vÃ  nguyÃªn nhÃ¢n; khÃ´ng bÃ¡o hoÃ n táº¥t chá»‰ vÃ¬ enqueue thÃ nh cÃ´ng. Cháº¡y láº¡i khÃ´ng táº¡o workflow trÃ¹ng cho sáº£n pháº©m Ä‘ang xá»­ lÃ½ vÃ  khÃ´ng render láº¡i job Ä‘Ã£ hoÃ n táº¥t. Advance chá»‰ xá»­ lÃ½ outbox cá»§a workflow Ä‘Æ°á»£c chá»n, khÃ´ng drain workflow khÃ´ng liÃªn quan.

Backup SQLite nháº¥t quÃ¡n vÃ  liá»‡t kÃª chÃ­nh xÃ¡c workflow/approval/outbox/import rows Product Video thá»­ nghiá»‡m trÆ°á»›c clean cutover. Chá»‰ xÃ³a targets Ä‘Ã£ kiá»ƒm tra; giá»¯ nguyÃªn dá»¯ liá»‡u Hermes khÃ¡c. KhÃ´ng rewrite primary key legacy. KhÃ´ng cáº§n clean cutover Ä‘á»ƒ kiá»ƒm tra connectivity provider.

## Thá»© tá»± triá»ƒn khai hÃ´m nay

1. Preflight configured MCP vÃ  kháº£ nÄƒng research/build/lock/brief/scene/storyboard/render/export, credentials, output location vÃ  render cost. Dá»«ng bÃ¡o blocker ngay náº¿u provider chÆ°a cÃ³ chá»©c nÄƒng hoáº·c tÃ i khoáº£n khÃ´ng dÃ¹ng Ä‘Æ°á»£c.
2. TÃ¡ch PI producer-only; backup vÃ  clean cutover dá»¯ liá»‡u thá»­ nghiá»‡m cÃ³ pháº¡m vi rÃµ rÃ ng.
3. Sá»­a tá»‘i thiá»ƒu start/status/Product Lock contract vÃ  approve-to-next-gate/cost authorization báº±ng Ä‘Æ°á»ng cháº¡y hiá»‡n cÃ³.
4. Cháº¡y má»™t sáº£n pháº©m tháº­t Ä‘áº¿n MP4, duyá»‡t tá»«ng gate vá»›i ngÆ°á»i dÃ¹ng, kiá»ƒm tra media vÃ  replay.

## Nghiá»‡m thu

- CÃ³ source batch, product key, workflow ID vÃ  configured-provider artifact IDs.
- Start dá»«ng táº¡i AwaitingProductLock vÃ  chÆ°a táº¡o brief.
- Má»—i approval chá»‰ tiáº¿n Ä‘áº¿n gate tiáº¿p theo; render cÃ³ quyá»n chi phÃ­.
- MP4 tá»“n táº¡i, cÃ³ thá»i lÆ°á»£ng dÆ°Æ¡ng, má»Ÿ xem Ä‘Æ°á»£c, Ä‘Ãºng sáº£n pháº©m vÃ  tá»· lá»‡ dá»c phÃ¹ há»£p Ä‘Äƒng TikTok.
- Export hoÃ n táº¥t, in Ä‘Æ°á»ng dáº«n file; outbox workflow má»¥c tiÃªu khÃ´ng cÃ²n pending/leased/quarantined jobs.
- Replay khÃ´ng táº¡o workflow trÃ¹ng hoáº·c phÃ¡t sinh render Ä‘Ã£ hoÃ n táº¥t.
- Focused regression tests vÃ  Ruff cháº¡y xanh; ghi rÃµ live run evidence, khÃ´ng dÃ¹ng sá»‘ lÆ°á»£ng unit tests thay live proof.

## Giá»›i háº¡n cam káº¿t

ÄÃ¢y lÃ  happy-case MVP cÃ¡ nhÃ¢n, khÃ´ng pháº£i chá»©ng nháº­n production-ready. Má»¥c tiÃªu hoÃ n táº¥t hÃ´m nay phá»¥ thuá»™c provider/MCP tháº­t kháº£ dá»¥ng, render credits vÃ  ngÆ°á»i dÃ¹ng pháº£n há»“i cÃ¡c approval. KhÃ´ng tá»± mua credits hoáº·c tá»± Ä‘áº·t ngÃ¢n sÃ¡ch Ä‘Æ°á»£c phÃ©p.

