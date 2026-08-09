# Auto Crawler & Scheduler — Flow Automation Module

Module tự động hóa pipeline affiliate research. User chỉ cần start một lần, hệ thống tự: đọc rules → crawl sản phẩm → sinh CSV → enqueue job → chạy worker → tạo content packages. Không hỏi lại user ở bất kỳ bước nào.

## 1. Vị trí trong hệ thống

```
crawl_rules.json (config)
      │
      ▼
auto_scheduler.py ──(poll mỗi 60s)──┐
      │                             │ due: theo giờ lịch / auto_run interval
      ▼                             ▼
auto_crawler.py ──run_once(rule)──► fetch_products → write CSV → enqueue job → run worker
      │
      ▼
crawl_rules.py (load/save rules)
```

## 2. Kiến trúc

| File | Vai trò |
|------|---------|
| `hermes/config/crawl_rules.json` | Rules config (defaults, lịch chạy, filters, video profiles) |
| `hermes/tools/crawl_rules.py` | Load/save rules. Tự tạo file default nếu chưa tồn tại, tự phục hồi nếu JSON lỗi |
| `hermes/tools/auto_crawler.py` | Pipeline chính: fetch → CSV → enqueue → worker. Entry: `python -m hermes.tools.auto_crawler` |
| `hermes/tools/auto_scheduler.py` | Scheduler: poll rules, chạy run theo lịch/interval. Entry: `python -m hermes.tools.auto_scheduler` |

## 3. Flow chi tiết (auto_crawler.run_once)

```
1/4  Load rules → merge defaults + rule (rule override defaults)
2/4  fetch_products_from_shopee(topic, no_products)
       ├─ requests gọi Shopee search API (raw HTTP, không SDK)
       └─ fallback _sample_products() khi API 403/lỗi
3/4  write_csv → import_dir/products_{topic}_{timestamp}.csv
       └─ validate 100 <= candidate count <= 200
4/4  enqueue_job → JobRepository.enqueue(affiliate_product_research)
     run_worker_once → drain hết job affiliate đang queue
```

### Scheduler (auto_scheduler.py)

- **Scheduled runs**: `scheduled_runs[]` trong rules, mỗi run có `time: "HH:MM"`, `enabled`. Chạy khi giờ hiện tại >= giờ lịch và chưa chạy hôm nay.
- **Auto run interval**: `defaults.auto_run` = true → chạy lặp mỗi `auto_run_interval_minutes` phút.
- Reload rules mỗi vòng poll (đổi config không cần restart).
- `--once` để chạy 1 pass rồi thoát (test).

## 4. Cấu trúc crawl_rules.json

```json
{
  "defaults": {
    "topic": "thiet bi cong nghe thong minh",
    "no_products": 150,            // số sản phẩm cần crawl
    "no_videos": 8,                // số content package sẽ tạo
    "platforms": ["shopee", "lazada", "tiktok"],
    "price_range_vnd": { "min": 200000, "max": 1500000, "default_max": 500000 },
    "commission_min_pct": 3.0,
    "rating_min": 4.0,
    "shortlist_limit": 25,
    "package_limit": 10,
    "auto_run": true,              // bật interval run
    "auto_run_interval_minutes": 60
  },
  "scheduled_runs": [              // lịch cố định theo giờ
    { "name": "daily_morning", "topic": "...", "no_products": 150, "no_videos": 5, "platforms": ["shopee"], "time": "09:00", "enabled": true }
  ],
  "filters": {                     // lọc sản phẩm trước khi chấm điểm
    "exclude_categories": ["adult", "gambling", "weapons"],
    "exclude_keywords": ["replica", "fake", "luxury brand"],
    "min_sold_count": 10,
    "min_review_count": 5
  },
  "video_profiles": {              // cấu hình content video
    "default_style": "review",
    "default_duration_seconds": 30,
    "languages": ["vi"],
    "require_voiceover": true,
    "generate_subtitles": true
  },
  "auto_approval": { "enabled": false, "min_rating": 4.5, "min_commission_pct": 5.0 },
  "delivery": { "telegram_chat_id": null, "send_summary_to_telegram": true }
}
```

## 5. Cách dùng

```powershell
# Chạy 1 lần theo rules mặc định
python -m hermes.tools.auto_crawler

# Dry run — chỉ xem plan, không chạy
python -m hermes.tools.auto_crawler --dry-run

# Chạy rule cụ thể trong scheduled_runs
python -m hermes.tools.auto_crawler --rule daily_morning

# Watch scheduler liên tục (poll 60s)
python -m hermes.tools.auto_scheduler

# Scheduler 1 pass rồi thoát
python -m hermes.tools.auto_scheduler --once
```

## 6. Ràng buộc business (giữ nguyên, không đơn giản hóa)

- **Candidate count 100–200** — worker `AffiliateResearchJobHandler` yêu cầu tối thiểu 100, tối đa 200 per CSV.
- **ProductPolicy categories** — sản phẩm ngoài danh sách cho phép bị loại, shortlist = 0. Categories: keyboard, mouse, headphones, earphones, mini_fan, fan, desk_light, smart_light, lamp, hub, stand, cable, desk_accessory, gaming_accessory, workspace_accessory.
- **Giá 200k–500k VND** (keyboard tối đa 1.5M) — ngoài range bị loại.
- Sample data phải dùng đúng categories + price range, nếu không toàn bộ bị reject.

## 7. Nguồn dữ liệu & hạn chế

| Nguồn | Trạng thái | Ghi chú |
|-------|-----------|---------|
| Shopee search API | **Trả 403** | Cần browser cookies để bypass. Hiện fallback sample data |
| `providers/shopee_search_provider.py` | Có cookies support | Dùng `get_browser_cookies()` đọc từ browser profile |
| crawl4ai | Chưa cài, chưa wire | Đã đánh giá trong `docs/research/2026-08-01-crawl4ai-crewai-mediacrawler-fit.md`. Hướng nâng cấp: Playwright headless crawl khi API 403 |

## 8. Trạng thái & hạn chế hiện tại

- **Đã E2E verified**: 150 products → 25 shortlisted → 8 packages `pending_review`, 0 errors.
- **Shopee live API 403** → `_sample_products` fallback (data demo đúng policy, có thể score/shortlist).
- **Telegram projection** retryable ("Event loop is closed") khi chưa cấu hình `telegram_chat_id`.
- Content packages dừng ở `pending_review`, chờ user approve (Telegram `/approve` hoặc `/approve_force`).

## 9. Hướng nâng cấp (ponytail)

- Wire **crawl4ai** (Playwright) làm fallback headless-browser cho Shopee/Lazada/TikTok khi API 403.
- Cấu hình `delivery.telegram_chat_id` để gửi summary + approve qua Telegram.
- Bật `auto_approval` cho các sản phẩm đạt ngưỡng rating + commission.
- Crawl real bằng cookies từ `providers/shopee_search_provider.py`.
