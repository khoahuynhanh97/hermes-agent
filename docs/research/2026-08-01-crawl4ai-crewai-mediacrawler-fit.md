# Đánh giá mức độ phù hợp của Crawl4AI, CrewAI và MediaCrawler với Hermes Agent

Ngày đánh giá: 2026-08-01

## Kết luận điều hành

| Repository | Fit tổng thể | TikTok quốc tế | Mức chồng lấn với Hermes | Rủi ro chính | Khuyến nghị |
|---|---:|---:|---:|---|---|
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | **Cao cho web, thấp cho media** | Thấp | Thấp đến vừa | Browser runtime nặng; lịch sử lỗ hổng ở Docker API | **ADAPTER**: dùng adapter tùy chọn cho website/article ingestion; không thay `yt-dlp` hoặc TikTok resolver |
| [CrewAI](https://github.com/crewAIInc/crewAI) | **Thấp ở thời điểm hiện tại** | Không áp dụng | Rất cao | Trùng job orchestration, state, LLM routing và persistence; dependency lớn | **PATTERN-ONLY**: học mô hình Flow/state; không thêm dependency vào Hermes core |
| [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | **Thấp cho production Hermes** | Rất thấp | Vừa | License phi thương mại; nhắm Douyin; phụ thuộc login/cookie/browser | **REJECT** cho production; chỉ tham khảo kiến trúc trong phạm vi license |

Quyết định đề xuất:

1. Thử nghiệm **Crawl4AI bằng một adapter độc lập**, chỉ nhận URL công khai và trả về Markdown/metadata chuẩn hóa.
2. Không đưa **CrewAI** vào runtime. Hermes đã sở hữu các primitive quan trọng mà CrewAI cung cấp.
3. Không tích hợp hoặc sao chép code **MediaCrawler** vào Hermes production vì license và sai lệch nền tảng Douyin/TikTok.

## Phạm vi và phương pháp

Báo cáo chỉ dùng nguồn gốc:

- README, tài liệu, source code, manifest dependency, license và security policy chính thức của ba repository.
- Code hiện tại trong workspace Hermes tại `D:\work\hermes-agent`.
- Không clone repository, không chạy crawler, không gọi API trả phí và không chạy code phụ thuộc mạng.

Các mức khuyến nghị:

- **ADOPT**: dependency/runtime chính thức trong Hermes.
- **ADAPTER**: tích hợp qua interface hẹp, có thể thay thế và cô lập dependency.
- **PATTERN-ONLY**: học thiết kế, không lấy dependency hoặc code.
- **REJECT**: không dùng cho production theo mục tiêu hiện tại.

## Baseline của Hermes

Hermes không còn là một script crawler đơn lẻ:

- Video ingestion đã dùng `yt-dlp`, retry với cookie Chrome và local `faster-whisper` tại [`core/video_fetcher.py`](../../core/video_fetcher.py).
- TikTok ingestion có adapter localhost giới hạn host, giới hạn response, kiểm tra OpenAPI, fallback đọc metadata trang công khai và tải carousel có quota tại [`tools/tiktok_media_resolver.py`](../../tools/tiktok_media_resolver.py).
- Job orchestration đã có SQLite queue, atomic claim, retry, cancellation và recovery tại [`hermes/jobs.py`](../../hermes/jobs.py) và [`core/job_watcher.py`](../../core/job_watcher.py).
- LLM được đi qua gateway có task capability và structured-output validation tại [`hermes/llm.py`](../../hermes/llm.py).
- Quyết định approve/reject/reanalysis đi qua [`KnowledgeLifecycle`](../../hermes/application/knowledge_lifecycle.py).
- Audit, deterministic repair và maintenance offline đã có tại [`hermes/data_health.py`](../../hermes/data_health.py) và [`hermes/maintenance.py`](../../hermes/maintenance.py).

Do đó, repository bên ngoài chỉ phù hợp nếu bổ sung một capability còn thiếu mà không giành quyền sở hữu job state, LLM routing, knowledge state hoặc maintenance.

## Ma trận fit chi tiết

Thang điểm 1-5, trong đó 5 là phù hợp nhất. Điểm effort càng cao càng tốn công.

| Tiêu chí | Crawl4AI | CrewAI | MediaCrawler |
|---|---:|---:|---:|
| Bổ sung chức năng còn thiếu | 5 cho web | 2 | 2 cho Douyin, 1 cho TikTok |
| API/interface để bọc adapter | 5 | 4 | 2 |
| Tương thích Python Hermes | 4 | 3 | 3 |
| Khả năng chạy Windows | 3 | 3 | 3 |
| Ít chồng lấn kiến trúc | 4 | 1 | 3 |
| An toàn dependency/runtime | 3 | 2 | 2 |
| Phù hợp TikTok quốc tế | 1 | Không áp dụng | 1 |
| License phù hợp production | 5 | 5 | 1 |
| Integration effort | 2-3 ngày | 2-4 tuần nếu thay orchestration | 1-2 tuần nhưng không nên làm |
| Adoption level | **ADAPTER** | **PATTERN-ONLY** | **REJECT** |

Các ước lượng effort là suy luận từ interface và dependency hiện tại, không phải cam kết từ upstream.

## 1. Crawl4AI

### Chức năng và interface

Crawl4AI tập trung vào chuyển trang web thành Markdown phù hợp cho RAG/data pipeline, cung cấp `AsyncWebCrawler`, `BrowserConfig`, `CrawlerRunConfig`, Markdown filtering và CSS/XPath extraction. Interface Python tối thiểu là `await crawler.arun(url)` và kết quả có Markdown trực tiếp ([official quickstart](https://docs.crawl4ai.com/core/quickstart/)).

Các điểm phù hợp với Hermes:

- Lấp đúng khoảng trống **website/article ingestion**: HTML động, JavaScript, session, cookie, proxy và HTML-to-Markdown ([README features](https://github.com/unclecode/crawl4ai#-features)).
- Có extraction không dùng LLM bằng CSS/XPath, phù hợp nguyên tắc để Hermes giữ LLM routing và chi phí ở gateway của mình ([no-LLM extraction example](https://docs.crawl4ai.com/core/quickstart/#5-simple-data-extraction-css-based)).
- API async đủ hẹp để bọc thành một capability adapter mà không thay `JobRepository`, `KnowledgeLifecycle` hoặc `HermesLLMGateway`.
- License Apache-2.0 cho phép sử dụng và sửa đổi trong sản phẩm với nghĩa vụ thông báo/license thông thường ([LICENSE](https://github.com/unclecode/crawl4ai/blob/main/LICENSE)).

Các điểm không phù hợp:

- Đây là **web crawler**, không phải media downloader hoặc TikTok API. Việc README nói có thể phát hiện media URL không đồng nghĩa với khả năng tải video, subtitle, carousel hoặc vượt giới hạn nền tảng ([README crawling features](https://github.com/unclecode/crawl4ai#-features)).
- Dependency mặc định khá rộng: Playwright, Patchright, stealth, `aiohttp`, `aiosqlite`, `pydantic`, `httpx`, `numpy`, NLP/filtering và package LiteLLM riêng ([pyproject.toml](https://github.com/unclecode/crawl4ai/blob/main/pyproject.toml)).
- Cài đặt cần browser setup, thông thường qua `crawl4ai-setup` hoặc `python -m playwright install chromium` ([official installation](https://github.com/unclecode/crawl4ai#installation-)).

### Runtime và Windows

Upstream yêu cầu Python `>=3.10` và khai báo Python 3.10-3.13, phù hợp baseline Python 3.10+ của Hermes ([pyproject.toml](https://github.com/unclecode/crawl4ai/blob/main/pyproject.toml)).

Windows có thể chạy theo đường Python/Playwright, nhưng tài liệu chính thức chủ yếu mô tả quy trình đa nền tảng, không đưa ra cam kết Windows-specific. Rủi ro thực tế là browser binary, antivirus, profile lock và tài nguyên Chromium, không phải syntax Python.

### Security và vận hành

Upstream đã công bố và vá các lỗi nghiêm trọng ở Docker API, gồm RCE qua deserialization, SSRF, auth bypass và file write. Các bản mới bổ sung allowlist, URL scheme validation, hook opt-in và restricted builtins ([security policy](https://github.com/unclecode/crawl4ai/security), [release notes in README](https://github.com/unclecode/crawl4ai#readme)).

Hệ quả cho Hermes:

- Không expose Docker/API server ra LAN/Internet ở giai đoạn đầu.
- Ưu tiên **in-process adapter trong worker riêng** hoặc service chỉ bind localhost.
- Không nhận raw Crawl4AI config từ người dùng. Hermes phải allowlist URL, timeout, browser options và output size.
- Tắt LLM extraction của Crawl4AI; chỉ dùng deterministic extraction rồi chuyển nội dung về `HermesLLMGateway`.
- Pin version đã vá và kiểm tra release/security notes trước khi nâng cấp.

### Thiết kế tích hợp đề xuất

```text
Hermes JobWorker
  -> WebDocumentFetcher port
     -> Requests/basic HTML adapter
     -> Crawl4AI adapter (optional, dynamic-page fallback)
  -> normalized WebDocument
  -> HermesLLMGateway
  -> KnowledgeLifecycle
```

Contract tối thiểu nên do Hermes sở hữu:

```python
fetch(url, *, timeout_seconds, max_bytes) -> WebDocument
```

`WebDocument` chỉ chứa final URL đã xác thực, title, Markdown, metadata allowlist, acquisition method và warnings. Không để object Crawl4AI rò vào domain layer.

### Recommendation

**ADAPTER**, ưu tiên cao cho website/article ingestion.

Không dùng Crawl4AI để thay:

- `yt-dlp`/subtitle/audio extraction trong `core/video_fetcher.py`;
- TikTok localhost resolver và carousel fallback;
- Hermes LLM router;
- Hermes job queue hoặc lifecycle.

Pilot nên giới hạn 10-20 URL website công khai, không login, không proxy, không LLM extraction, có timeout và snapshot test cho Markdown normalization.

## 2. CrewAI

### Chức năng và interface

CrewAI cung cấp hai abstraction chính:

- **Crews**: nhiều agent theo role, tự phân công và cộng tác.
- **Flows**: workflow event-driven, branching, shared state và tích hợp agent với Python code ([official README](https://github.com/crewAIInc/crewAI#understanding-flows-and-crews)).

Flow có decorator `@start`, `@listen`, state có ID, và có persistence mặc định bằng SQLite khi dùng `@persist` ([official Flow docs](https://docs.crewai.com/en/concepts/flows)).

Đây là thiết kế tốt để tham khảo, nhưng gần như trùng với phần Hermes đã sở hữu:

| CrewAI concern | Hermes owner hiện tại |
|---|---|
| Task queue/run state | `JobRepository`, `AgentJobManager`, `JobWorker` |
| Retry/recovery/cancel | `JobRepository`, `JobWorker` |
| LLM dispatch | `HermesLLMGateway`, shared gateway/router |
| Persisted state | Hermes SQLite schema |
| Knowledge state transition | `KnowledgeLifecycle` |
| Maintenance/recovery | `DataHealth`, `MaintenanceRunner` |

### Dependency và runtime

Package `crewai` yêu cầu Python `>=3.10,<3.14`, phù hợp phiên bản Python nhưng kéo theo một dependency graph lớn: OpenAI SDK, Instructor, OpenTelemetry, ChromaDB, tokenizers, LanceDB, MCP, SQLite và nhiều utility khác ([package pyproject](https://github.com/crewAIInc/crewAI/blob/main/lib/crewai/pyproject.toml)).

Các xung đột/rủi ro cụ thể:

- CrewAI pin Pydantic `<2.13`, trong khi upstream khác và Hermes dependency chưa pin toàn bộ graph; thêm trực tiếp làm tăng nguy cơ resolver conflict.
- CrewAI có OpenAI SDK và cấu hình LLM riêng, dễ tạo đường gọi model ngoài `HermesLLMGateway`.
- ChromaDB, LanceDB và SQLite persistence tạo thêm storage authority cạnh SQLite của Hermes.
- OpenTelemetry và control-plane integrations làm tăng bề mặt observability/configuration cần quản trị.

CrewAI hỗ trợ cài trên Windows qua `uv`, nhưng tài liệu chính thức cảnh báo lỗi build `chroma-hnswlib` có thể cần Visual Studio Build Tools C++ ([installation docs](https://docs.crewai.com/en/installation)).

License MIT phù hợp production ([LICENSE](https://github.com/crewAIInc/crewAI/blob/main/LICENSE)), nên vấn đề không phải license mà là ownership và complexity.

### Khi nào CrewAI mới đáng dùng

Chỉ xem xét lại nếu Hermes có một use case mà workflow tĩnh hiện tại không đáp ứng, ví dụ:

- nhiều agent thực sự tự phân công công việc;
- cần delegation động giữa role;
- cần một sandbox riêng cho research workflow;
- workflow đó không được quyền trực tiếp mutate Hermes DB.

Ngay cả khi đó, nên chạy CrewAI như **bounded external capability**:

```text
Hermes job -> CrewAI sandbox -> structured result -> validation -> Hermes lifecycle
```

CrewAI không được sở hữu canonical job state, API key policy, knowledge approval hoặc maintenance.

### Pattern nên học

- Typed flow state có ID.
- Event/listener rõ ràng giữa các bước.
- Resume/fork semantics cho persisted flow.
- Phân biệt deterministic flow control và autonomous crew.

Hermes có thể áp dụng các pattern này vào code hiện hữu mà không lấy dependency.

### Recommendation

**PATTERN-ONLY**.

Không thêm `crewai` vào `requirements.txt`, không thay `JobWorker`, không để agent gọi provider trực tiếp và không dùng CrewAI persistence trên database Hermes.

## 3. MediaCrawler

### Chức năng và phạm vi nền tảng

MediaCrawler là crawler cho các nền tảng Trung Quốc: Xiaohongshu, **Douyin**, Kuaishou, Bilibili, Weibo, Tieba và Zhihu; README mô tả search, post detail, comments, creator page, login cache và proxy ([official README](https://github.com/NanmiCoder/MediaCrawler#readme)).

Source config liệt kê platform `xhs | dy | ks | bili | wb | tieba | zhihu`, không có TikTok quốc tế; `dy` được triển khai bằng `DouYinCrawler` và `DouYinClient` ([base_config.py](https://github.com/NanmiCoder/MediaCrawler/blob/main/config/base_config.py), [Douyin crawler](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/douyin/core.py)).

Kết luận: **Douyin không phải adapter thay thế cho TikTok international**. Hai sản phẩm có domain, login state, endpoint, signature và anti-bot behavior khác nhau. Không có bằng chứng trong source chính thức được rà rằng open-source MediaCrawler hỗ trợ `tiktok.com`.

### Interface và integration effort

Repository có `AbstractCrawler`, nhưng entrypoint chính đọc global config, parse CLI, chọn crawler bằng factory, tự khởi tạo database/store và gọi `crawler.start()` ([main.py](https://github.com/NanmiCoder/MediaCrawler/blob/main/main.py), [base crawler](https://github.com/NanmiCoder/MediaCrawler/blob/main/base/base_crawler.py)).

Điều này làm adapter khó hơn Crawl4AI:

- Interface không trả một result object chuẩn hóa cho caller.
- Crawler ghi trực tiếp qua store layer riêng.
- Config và login state mang tính global.
- Muốn nhúng phải tách fetch khỏi persistence, browser ownership và CLI lifecycle.

Dependency cũng lớn: Python `>=3.11`, Playwright, FastAPI, SQLAlchemy, Redis, MySQL/Mongo/Postgres clients, OpenCV, Pandas, Matplotlib, wordcloud, Node/ExecJS và storage exporters ([pyproject.toml](https://github.com/NanmiCoder/MediaCrawler/blob/main/pyproject.toml)).

### Windows support

README có hướng dẫn kích hoạt venv trên Windows và mặc định khuyến nghị kết nối Chrome qua CDP, tái sử dụng cookie/login state. Douyin và Zhihu cần Node.js; standard Playwright mode cần browser driver ([official setup](https://github.com/NanmiCoder/MediaCrawler#readme)).

Vì vậy Windows có đường chạy được mô tả, nhưng vận hành không headless hoàn toàn:

- cần Chrome/remote debugging hoặc Playwright browser;
- có thể cần QR/phone/cookie login;
- session và cookie trở thành secret vận hành;
- browser/profile lock và anti-bot challenge có thể làm job không deterministic.

### License, legal và security

Đây là blocker quyết định. License là **NON-COMMERCIAL LEARNING LICENSE 1.1**, chỉ cấp quyền dùng/copy/modify/merge cho mục đích học tập phi thương mại ([LICENSE](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE)).

README và source còn yêu cầu:

- không dùng thương mại;
- tuân thủ terms/robots;
- không crawl quy mô lớn;
- kiểm soát request rate;
- không gây ảnh hưởng vận hành nền tảng ([README disclaimer](https://github.com/NanmiCoder/MediaCrawler#readme), [main.py notice](https://github.com/NanmiCoder/MediaCrawler/blob/main/main.py)).

Ngay cả nếu Hermes hiện dùng cá nhân, việc đưa code vào sản phẩm có thể sử dụng cho affiliate/content operations tạo rủi ro vượt phạm vi “non-commercial learning”. Cần ý kiến pháp lý hoặc license thương mại riêng trước mọi reuse code.

CDP remote debugging và tái sử dụng cookie/login state cũng mở bề mặt nhạy cảm. Hermes hiện giới hạn TikTok crawler endpoint ở localhost và không cần nhập cookie vào domain model; tích hợp MediaCrawler sẽ làm secret/session management phức tạp hơn.

### Giá trị có thể học mà không tích hợp

Trong giới hạn license, có thể tham khảo ở mức ý tưởng:

- platform factory;
- abstract crawler/client/store separation;
- bounded concurrency;
- checkpoint/resume;
- login state abstraction;
- comment pagination và rate limiting.

Không copy source, JS signature, login workflow hoặc store implementation vào Hermes production.

### Recommendation

**REJECT** cho direct dependency, code reuse và production adapter.

**PATTERN-ONLY** cho nghiên cứu kiến trúc. Nếu sau này Hermes cần Douyin thật sự, cần:

1. xác nhận use case và jurisdiction;
2. có license thương mại rõ ràng;
3. chạy service tách biệt;
4. không chia sẻ profile Chrome chính;
5. output qua schema allowlist;
6. vẫn để Hermes sở hữu job/lifecycle.

## TikTok international và Douyin

| Năng lực | Hermes hiện tại | Crawl4AI | MediaCrawler |
|---|---|---|---|
| Nhận diện `tiktok.com` | Có | Generic web URL | Không được khai báo |
| Subtitle/audio | `yt-dlp` + local Whisper | Không phải capability chính | Không phải interface tích hợp được xác minh |
| Photo carousel | Local API + embedded-page fallback | Có thể đọc HTML nhưng không contract TikTok | Douyin-specific |
| Login/session | Cookie retry có giới hạn | Browser session generic | QR/phone/cookie/CDP cho platform Trung Quốc |
| Video download | Có qua pipeline hiện tại | Không nên dùng | Có logic platform-specific nhưng license/Douyin blocker |
| Fit recommendation | Giữ làm authority | Web fallback phụ | Không dùng cho TikTok international |

Crawl4AI có thể hỗ trợ lấy metadata/HTML công khai khi trang render bằng JavaScript, nhưng không nên được quảng bá như TikTok fallback “đảm bảo”. MediaCrawler không giải quyết TikTok international chỉ vì Douyin cùng công ty mẹ.

## Kiến trúc adoption đề xuất

```text
                    +-----------------------+
URL/job ---------->| Hermes JobRepository  |
                    +-----------+-----------+
                                |
                    +-----------v-----------+
                    | Hermes ingestion port |
                    +----+-------------+----+
                         |             |
              website/article      video/social
                         |             |
             +-----------v--+     +----v----------------+
             | Crawl4AI     |     | Existing resolver   |
             | optional     |     | + yt-dlp + Whisper  |
             | adapter      |     +---------------------+
             +-----------+--+
                         |
                    normalized content
                         |
              +----------v-----------+
              | HermesLLMGateway     |
              +----------+-----------+
                         |
              +----------v-----------+
              | KnowledgeLifecycle   |
              +----------------------+
```

Nguyên tắc:

- External crawler chỉ sở hữu **acquisition**, không sở hữu workflow.
- Mọi LLM call đi qua Hermes.
- Mọi knowledge mutation đi qua lifecycle.
- Mọi output đều bị giới hạn size, timeout, redirect, content type và schema.
- Browser profile/cookie không đi vào report, lesson metadata hoặc log.

## Kế hoạch adoption thực tế

### Giai đoạn A: Crawl4AI spike

- Tạo `WebDocumentFetcher` port và một Crawl4AI adapter tùy chọn.
- Chạy trong virtual environment hoặc worker process riêng nếu dependency resolver xung đột.
- Chỉ hỗ trợ public URL, không login/proxy/remote hooks.
- Tắt Crawl4AI LLM extraction.
- Test fixture bằng HTML/local server; không phụ thuộc mạng trong CI.
- Đo: tỷ lệ lấy Markdown, độ sạch, thời gian, memory, failure classification.

Go/no-go:

- Go nếu cải thiện rõ website động so với requests hiện tại và không làm worker mất ổn định.
- No-go nếu browser overhead lớn hơn lợi ích hoặc output không deterministic.

### Giai đoạn B: Pattern từ CrewAI

- Bổ sung typed job-stage/result contract trong Hermes nếu còn thiếu.
- Chuẩn hóa resume/fork semantics ở job layer.
- Không cài CrewAI.

### Giai đoạn C: MediaCrawler

- Không triển khai.
- Chỉ mở lại quyết định khi có yêu cầu Douyin cụ thể và license thương mại phù hợp.

## Quyết định cuối

| Repository | Quyết định | Phạm vi được phép |
|---|---|---|
| Crawl4AI | **ADAPTER** | Website/article dynamic rendering và Markdown extraction |
| CrewAI | **PATTERN-ONLY** | Flow/state/resume ideas; không dependency |
| MediaCrawler | **REJECT** | Chỉ đọc/tham khảo trong phạm vi license |

Ưu tiên kỹ thuật tiếp theo của Hermes nên là một `WebDocumentFetcher` port với Crawl4AI adapter tùy chọn. Không có repository nào trong ba lựa chọn nên thay pipeline TikTok/video hiện tại.

## Nguồn chính thức

### Crawl4AI

- [Repository và README](https://github.com/unclecode/crawl4ai)
- [Official documentation](https://docs.crawl4ai.com/)
- [Quickstart/API](https://docs.crawl4ai.com/core/quickstart/)
- [pyproject.toml](https://github.com/unclecode/crawl4ai/blob/main/pyproject.toml)
- [LICENSE](https://github.com/unclecode/crawl4ai/blob/main/LICENSE)
- [Security policy/advisories](https://github.com/unclecode/crawl4ai/security)

### CrewAI

- [Repository và README](https://github.com/crewAIInc/crewAI)
- [Official installation](https://docs.crewai.com/en/installation)
- [Official Flows documentation](https://docs.crewai.com/en/concepts/flows)
- [Package pyproject.toml](https://github.com/crewAIInc/crewAI/blob/main/lib/crewai/pyproject.toml)
- [LICENSE](https://github.com/crewAIInc/crewAI/blob/main/LICENSE)
- [Security policy](https://github.com/crewAIInc/crewAI/security)

### MediaCrawler

- [Repository và README](https://github.com/NanmiCoder/MediaCrawler)
- [pyproject.toml](https://github.com/NanmiCoder/MediaCrawler/blob/main/pyproject.toml)
- [main.py](https://github.com/NanmiCoder/MediaCrawler/blob/main/main.py)
- [AbstractCrawler](https://github.com/NanmiCoder/MediaCrawler/blob/main/base/base_crawler.py)
- [Douyin crawler](https://github.com/NanmiCoder/MediaCrawler/blob/main/media_platform/douyin/core.py)
- [Base config](https://github.com/NanmiCoder/MediaCrawler/blob/main/config/base_config.py)
- [LICENSE](https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE)
- [Security page](https://github.com/NanmiCoder/MediaCrawler/security)
