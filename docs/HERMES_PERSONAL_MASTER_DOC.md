# HERMES PERSONAL — MASTER DOCUMENTATION
## Kiến Trúc, Quy Trình Nghiệp Vụ & Cẩm Nang Vận Hành Chuẩn Hóa (SSOT)

**Phiên bản:** 1.0 (Canonical)  
**Ngày cập nhật:** 2026-09-25  
**Phạm vi áp dụng:** Bounded Context `hermes_personal` chạy trên môi trường Single-Node (Windows/Linux) của cá nhân.  
**Trật tự uy quyền (Authority Order):**  
1. Mã nguồn thực thi & SQLite migrations trong `hermes_personal/`  
2. Bộ kiểm thử tự động trong `tests/hermes_personal/`  
3. Tài liệu Master này & các tài liệu contract tại `docs/`  
4. Các bản kế hoạch canonical tại `docs/superpowers/{specs,plans}/product-video-master-*`  
5. *(Không sử dụng)* Toàn bộ các file kế hoạch/nháp lịch sử trước 2026-09-16.

---

## MỤC LỤC
1. [Tổng Quan Định Vị & Triết Lý Thiết Kế](#1-tổng-quan-định-vị--triết-lý-thiết-kế)
2. [Bản Hiến Pháp Kiến Trúc & Các Bất Biến (Architectural Invariants)](#2-bản-hiến-pháp-kiến-trúc--các-bất-biến-architectural-invariants)
3. [Vòng Đời Agent Turn & Mô Hình Đơn Não (Sole Brain Turn Lifecycle)](#3-vòng-đời-agent-turn--mô-hình-đơn-não-sole-brain-turn-lifecycle)
4. [Lưu Trữ Bền Vững, Transactional Outbox & Chính Sách No-DLQ](#4-lưu-trữ-bền-vững-transactional-outbox--chính-sách-no-dlq)
5. [Trái Tim Nghiệp Vụ 1: AI Video Factory & 5 Cổng Phê Duyệt HITL](#5-trái-tim-nghiệp-vụ-1-ai-video-factory--5-cổng-phê-duyệt-hitl)
6. [Trái Tim Nghiệp Vụ 2: Governed Learning & Thu Nạp Tri Thức (/hoc, /hoc-cta)](#6-trái-tim-nghiệp-vụ-2-governed-learning--thu-nạp-tri-thức-hoc-hoc-cta)
7. [Topology Vận Hành & Môi Trường Runtime Thực Tế Trên Windows](#7-topology-vận-hành--môi-trường-runtime-thực-tế-trên-windows)
8. [Cẩm Nang Vận Hành Hàng Ngày & Quy Trình Kiểm Thử (DevOps Playbook)](#8-cẩm-nang-vận-hành-hàng-ngày--quy-trình-kiểm-thử-devops-playbook)
9. [Bản Đồ Tài Liệu & Phân Loại Di Sản (Documentation Taxonomy)](#9-bản-đồ-tài-liệu--phân-loại-di-sản-documentation-taxonomy)
10. [Sổ Tay Xử Lý Sự Cố (Troubleshooting & Incident Triage)](#10-sổ-tay-xử-lý-sự-cố-troubleshooting--incident-triage)

---

## 1. TỔNG QUAN ĐỊNH VỊ & TRIẾT LÝ THIẾT KẾ

### 1.1 Hermes Personal là gì?
`hermes_personal` là phân vùng tái kiến trúc có giới hạn (bounded context) được tích hợp trực tiếp vào kho mã nguồn `hermes-agent`. Nó biến một AI Agent cá nhân thành một **cộng sự thông minh tự hành**, vận hành trên máy đơn (single-machine local-first) phục vụ 2 mục tiêu thương mại và tri thức:
- **Tự động hóa sản xuất Video AI (Product-to-Video Factory):** Tiếp nhận sản phẩm tiêu dùng công nghệ hàng ngày từ Product-Intelligence (PI), bóc tách claim có căn cứ, thẩm định ảnh/video qua QC thị giác, dẫn dắt qua 5 chốt chặn phê duyệt con người (HITL Gates) để xuất bản video ngắn dọc (TikTok/Reels) hoàn chỉnh.
- **Tiếp thu và quản trị tri thức bền vững (Governed Learning):** Thu nạp cấu trúc hook, CTA và kiến thức từ media thông qua kỹ năng `/hoc` và `/hoc-cta`, bảo đảm không ảo giác, có sự kiểm duyệt của chủ sở hữu trước khi đưa vào bộ nhớ dài hạn hoặc xuất bản thành procedural skill.

### 1.2 Triết lý "Narrow Waist, Capable Edges"
- **Thắt lưng hẹp (Narrow Waist):** Cốt lõi của hệ thống giữ kích thước nhỏ nhất có thể. Mỗi tool hay schema đưa vào core model đều phải trả giá bằng token trên **mỗi lần gọi API**.
- **Bộ nhớ đệm Prompt là bất khả xâm phạm (Sacred Prompt Cache):** Một phiên hội thoại lâu dài luôn tái sử dụng prefix cache. Mọi hành vi làm biến đổi quá khứ, tráo đổi toolset hay dựng lại System Prompt giữa chừng đều làm hỏng cache và tăng chi phí theo cấp số nhân $\rightarrow$ **Nghiêm cấm tuyệt đối**.
- **Không suy đoán hạ tầng phân tán (Anti-Speculative Infrastructure):** Đây là hệ thống cá nhân chạy single-node. **Tuyệt đối không đưa Kafka, RabbitMQ, Redis, Celery hay Distributed DLQ vào hệ thống**. Toàn bộ độ bền và tính bất đồng bộ được giải quyết bằng SQLite WAL, Transactional Outbox và Thread Pool nội bộ.

### 1.3 Mục tiêu vận hành Product Video hiện tại

- Mỗi ngày nhận tối đa **5 sản phẩm** từ batch Product Intelligence `READY`, cố gắng tạo **3–5 video hoàn chỉnh** từ các sản phẩm đủ căn cứ. Đây là mục tiêu best effort, không phải cam kết số lượng: thiếu nguồn, ảnh, QC, credit hoặc phê duyệt thì ghi rõ lý do và số video thực tế.
- Dùng Google Flow trước khi còn credit và thao tác phù hợp từng cảnh; khi credit không đủ, có thể chọn Vertex AI **trước** lần render trả phí kế tiếp. Quyết định provider và hạn mức được ghi theo từng operation; không tự chuyển provider hay submit lại khi kết quả trả phí chưa rõ. Người dùng có thể chỉ định provider cho một lần chạy.
- Lời dẫn tiếng Việt được đưa vào prompt cảnh khi provider hỗ trợ. Nếu file render không có audio, có thể tiếp tục bằng video không lời để người dùng thêm giọng sau; QC và export vẫn phải xác minh file thật. Năm cổng phê duyệt vẫn bắt buộc.
- Bằng chứng vận hành 2026-09-25: batch PI của ngày không có sản phẩm đủ điều kiện (`0/3`). Batch lịch sử 2026-09-18 đã khởi động 5 workflow; Tribit XSound Go qua Image QC và chờ Product Lock, Baseus trượt Image QC, ba workflow còn lại bị chặn ở research/resource pack. **Chưa có MP4 hoàn chỉnh trong lần vận hành này.** Chi tiết và lỗi cụ thể ở `reports/2026-09-25-hermes-product-video-focused-implementation.md`.

---

## 2. BẢN HIẾN PHÁP KIẾN TRÚC & CÁC BẤT BIẾN (ARCHITECTURAL INVARIANTS)

Mọi thay đổi mã nguồn trong `hermes_personal` phải tuân thủ nghiêm ngặt 8 bất biến sau:

| STT | Tên Bất Biến | Nội Dung Quy Định |
| :---: | :--- | :--- |
| **1** | **Single Brain Invariant** | Upstream `run_agent.AIAgent` là cỗ máy suy luận duy nhất. Cấm dựng brain thứ hai, router LLM phụ hoặc conversation loop riêng tại tầng Ingress/Gateway. |
| **2** | **Channel Normalization** | Mọi tương tác từ mọi kênh (CLI, Telegram, Web, Omni) đều bắt buộc phải chuẩn hóa thành contract `AgentTurnRequest` (frozen dataclass, `schema_version = 1`). Không đặt logic nghiệp vụ tại channel adapter. |
| **3** | **Gateway Single Entry** | Mọi lượt tương tác hội thoại đều phải đi qua `HermesTurnService`, kết nối upstream thông qua `UpstreamAIAgentAdapter`. |
| **4** | **Persist-Before-Yield** | Mọi sự kiện phát sinh (`AgentEvent`) **BẮT BUỘC PHẢI COMMIT VÀO SQLITE (`turn_event`) TRƯỚC KHI YIELD/STREAM** cho người dùng hoặc channel adapter. |
| **5** | **SQLite Single Source of Truth** | SQLite với foreign keys bật (`PRAGMA foreign_keys = ON`) và `BEGIN IMMEDIATE` là nguồn chân lý bền vững duy nhất. In-memory chỉ là cache/fallback phục vụ test. |
| **6** | **Owner & Session Isolation** | Toàn bộ dữ liệu, turn, event, memory, artifacts được cô lập theo `owner_user_id`. Chuyển giao xuyên kênh cần có bản ghi `workflow_handoff` tường minh giữa các session cùng chủ sở hữu. |
| **7** | **Strict HITL Gates** | 5 cổng phê duyệt của Product Video (Product Lock, Brief, Scene Plan, Storyboard + Cost Auth, Final Approval) là bất khả xâm phạm. Cấm tự ý bypass hoặc để máy tự approve. |
| **8** | **Immutable Artifacts & Strict Rollback** | Artifact gắn liền với SHA-256 digest và version nguyên dương. Thay đổi artifact là tạo version mới và hủy bỏ đệ quy các nhánh phụ thuộc con (descendants); cấm ghi đè (overwrite in-place). |

### The Footprint Ladder (Bậc thang dấu chân tính năng)
Khi cần bổ sung năng lực mới, bắt buộc chọn mức thấp nhất có thể:
1. **Mở rộng code hiện hữu** (Zero footprint).
2. **CLI Command + Skill** (Agent gõ lệnh shell qua hướng dẫn skill; zero model-tool footprint) $\rightarrow$ *Lựa chọn mặc định cho cron, workflow, webhook*.
3. **Service-Gated Tool (`check_fn`)** (Chỉ hiện khi đủ điều kiện cấu hình/token).
4. **Plugin** (Nằm ngoài core, tại `~/.hermes/plugins/`).
5. **MCP Server** (Kết nối qua FastMCP stdio/client; zero core-schema footprint).
6. **Core Model Tool** (Biện pháp cuối cùng, chỉ khi cực kỳ thiết yếu và không thể làm bằng terminal/file).

---

## 3. VÒNG ĐỜI AGENT TURN & MÔ HÌNH ĐƠN NÃO (SOLE BRAIN TURN LIFECYCLE)

### 3.1 Sơ đồ tuần tự chuẩn (Canonical Agent-Turn Flow)

```
[Channel Adapter (CLI/Web/Telegram/Omni)]
       │
       ▼ (Authenticate Subject)
[ChannelTurnNormalizer] ──> Tra cứu IdentityRepository ──> (owner_user_id, session_id)
       │
       ▼
[AgentTurnRequest] (frozen, schema_version=1)
       │
       ▼
[HermesTurnService.stream_turn()]
       │
       ├── 1. Xác thực quyền sở hữu: owner, session, channel, handoff hợp lệ
       ├── 2. Claim khóa Idempotency trong SQLite: (owner_user_id, idempotency_key)
       │       │
       │       ├── [Trùng khóa + Trùng Digest + Đã xong] ──> Exact Replay từ EventRepository
       │       ├── [Trùng khóa + Trùng Digest + Đang chạy] ──> Báo lỗi TurnInProgress
       │       └── [Trùng khóa + Sai Digest] ──> Báo lỗi IdempotencyConflict
       │
       ▼ (Turn mới hợp lệ: insert status 'in_progress')
[UpstreamAIAgentAdapter]
       │
       ▼ nạp context đã kiểm duyệt (Approved Knowledge + Active Preferences)
[AIAgent.run_conversation()] ──> (Thực thi Tool & Reasoning upstream)
       │
       ▼ (Mỗi token/event sinh ra):
       ├── BƯỚC 1: Commit Event vào SQLite `turn_event` (BỀN VỮNG)
       └── BƯỚC 2: Yield `AgentEvent` ra Channel Adapter / Client Stream (SSE)
       │
       ▼
[Đánh dấu Turn hoàn tất]: status = 'completed' / 'failed'
```

### 3.2 Chiến lược Idempotency & Replay
- **Khóa duy nhất bền vững:** `(owner_user_id, idempotency_key)`. Nếu client không truyền, mặc định dùng `turn_id`.
- **Semantic Digest:** Băm SHA-256 từ canonical JSON (loại bỏ `turn_id`, `occurred_at`, `idempotency_key`, sort keys). Toàn bộ nội dung còn lại (principal, message, attachments, history, toolsets, workflow, locale) đều cấu thành semantic digest.
- **Monotonic Global Cursor:** Bảng `owner_event_cursor` quản lý con trỏ tuần tự tăng đơn điệu toàn cục theo owner, cho phép client ngắt kết nối có thể kết nối lại và replay chính xác sự kiện qua `/api/events/replay?after_cursor=...`.

---

## 4. LƯU TRỮ BỀN VỮNG, TRANSACTIONAL OUTBOX & CHÍNH SÁCH NO-DLQ

### 4.1 Mô hình Lưu trữ Bền vững (SQLite Single-Node)
Toàn bộ trạng thái quan hệ được lưu tại một file SQLite duy nhất (`$env:HERMES_HOME\hermes.db`):
- `global_user_identity` & `conversation_session`: Định danh và phiên cách ly.
- `turn_execution` & `turn_event`: Vòng đời turn và nhật ký sự kiện bất biến.
- `owner_event_cursor`: Con trỏ đơn điệu toàn cục cho event stream.
- `workflow_aggregate`, `workflow_event`, `processed_command`: Quản lý tiến trình nghiệp vụ.
- `workflow_outbox`: Transactional outbox pattern cho background tasks.
- `budget_reservation`: Sổ cái giữ chỗ và cam kết ngân sách chi tiêu.
- `approval_request`: Trạng thái các cổng phê duyệt HITL.
- `capability_snapshot` & `capability_catalog_state`: Snapshot năng lực MCP đã khám phá.

### 4.2 Cơ chế Transactional Outbox & Worker Lease Pattern
Xử lý các tác vụ tốn thời gian (research, render, export) không thông qua message broker ngoài mà dùng bảng `workflow_outbox` nằm chung SQLite transaction với workflow:

```
[Workflow Engine Action]
       │
       ▼ (BEGIN IMMEDIATE)
Commit Aggregate State + Workflow Event + Outbox Record (status: 'pending')
       │
       ▼ (Background Worker Polling)
Worker gọi `claim_outbox_batch()`:
  - Cập nhật status: 'pending' ──> 'leased'
  - Gán worker_id, sinh lease_token ngẫu nhiên, lease_expires_at = now + 30s
  - Tăng attempt_count = attempt_count + 1
       │
       ├── [Thực thi Handler thành công] ──> gọi `ack_outbox(outbox_id, lease_token)`
       │                                     ──> Xóa record outbox an toàn.
       │
       ├── [Worker bị trễ/treo (Stale Lease)] ──> lease_expires_at hết hạn.
       │                                     ──> Worker khác claim lại.
       │                                     ──> ACK muộn từ worker cũ bị từ chối bằng StaleLeaseError.
       │
       └── [Lỗi thực thi (Failure)] ──> Tính next_attempt_at theo Exponential Backoff.
                                    ──> Nếu attempt_count > max_attempts (5):
                                        Chuyển status sang 'quarantined' (Poison Message).
```

### 4.3 Chính sách No-DLQ (No-DLQ Policy)
- **Không có DLQ trong hệ thống hiện tại.** Thuật ngữ Dead Letter Queue không phản ánh đúng kiến trúc bảng SQLite cục bộ.
- Tài liệu và giao diện chỉ được phép sử dụng từ **"workflow outbox"** hoặc **"quarantined messages"**.
- Khi một thông điệp bị `quarantined`, hệ thống không tự động vứt bỏ. Operator sử dụng lệnh `requeue_quarantined(outbox_id)` để reset trạng thái về `pending`, xóa log lỗi và đưa tác vụ trở lại hàng đợi sau khi đã khắc phục nguyên nhân gốc rễ.

---

## 5. TRÁI TIM NGHIỆP VỤ 1: AI VIDEO FACTORY & 5 CỔNG PHÊ DUYỆT HITL

Quy trình sản xuất Video AI từ dữ liệu thị trường của Product-Intelligence đi qua State Machine 16 trạng thái, được bảo vệ nghiêm ngặt bởi **5 Cổng phê duyệt con người (HITL)**:

```
[Product-Intelligence (Daily 07:00)]
       │ (products.json ──> Exchange Inbox: READY batch)
       ▼
[Hermes CLI: `hermes personal video start`]
       │
       ▼
   RESEARCHING ──> BUILDING_RESOURCE_PACK
       │
       ▼
   [Image QC (Gemini Vision ≥ 80đ, ≥ 2 eligible images, không watermark/seller logo)]
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ 🔴 GATE 1: AwaitingProductLock                              │
│    Operator duyệt Product Lock, chốt Resource Pack          │
└─────────────────────────────────────────────────────────────┘
       │ `hermes personal video approve <approval_id>`
       ▼
   LOCKING_RESOURCE_PACK ──> CREATING_BRIEF
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ 🔴 GATE 2: AwaitingBriefApproval                            │
│    Operator duyệt Kịch bản cốt lõi (Grounded claims, hook)  │
└─────────────────────────────────────────────────────────────┘
       │ `hermes personal video approve <approval_id>`
       ▼
   CREATING_SCENE_PLAN
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ 🔴 GATE 3: AwaitingSceneApproval                            │
│    Operator duyệt cấu trúc từng phân cảnh (16.0s vertical)  │
└─────────────────────────────────────────────────────────────┘
       │ `hermes personal video approve <approval_id>`
       ▼
   CREATING_STORYBOARD (Visual Prompts & Render Plan)
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ 🔴 GATE 4: AwaitingStoryboardApproval + Cost Authorization  │
│    Operator duyệt Storyboard & CẤP QUYỀN CHI PHÍ            │
│    (Bắt buộc: --campaign-max-cost-usd, --workflow-max-cost) │
└─────────────────────────────────────────────────────────────┘
       │ `hermes personal video approve <approval_id> --authorize-cost ...`
       ▼
   RENDERING (Google Flow Playwright edge when separately implemented; atomic reservation, scene checkpoints)
       │
       ▼ Composite MP4 (720×1280, H.264, 24fps)
   [Video QC (Gemini Vision sampling 3 frames/cảnh, ≥ 80đ/scene, Full Coverage)]
       │
       ▼ (LƯU Ý: QC PASS KHÔNG ĐƯỢC TỰ DUYỆT CỔNG 5)
┌─────────────────────────────────────────────────────────────┐
│ 🔴 GATE 5: AwaitingFinalApproval                            │
│    Operator BẮT BUỘC PHẢI MỞ VÀ XEM TOÀN BỘ VIDEO MP4       │
└─────────────────────────────────────────────────────────────┘
       │ `hermes personal video approve <approval_id>`
       ▼
   EXPORTING ──> COMPLETED
       │ (Xuất bản: final.mp4 + caption.txt sạch + metadata.json)
       ▼
[Operator đăng thủ công lên TikTok]
```

### Các nguyên tắc an toàn bất khả xâm phạm của Video Factory:
1. **QC Report không phải là Approval:** Đánh giá của Gemini Vision chỉ là bằng chứng kỹ thuật. Quyền duyệt luôn thuộc về con người.
2. **Không cấp ngân sách $\rightarrow$ Không render:** Cổng 4 bắt buộc phải có cờ `--authorize-cost`. Nếu thiếu, hệ thống chặn đứng không gọi GPU API.
3. **Per-Scene Rendering Checkpoints:** Product Video pin `provider_kind=google_flow` cùng transition submit và lưu `provider_operation_id` ngay khi được chấp nhận. Restart chỉ poll Google Flow; không submit lại. Row Vertex legacy hoặc row thiếu pin/ID phải chờ operator reconciliation, không được chuyển provider.
4. **Invalidation đệ quy theo nhánh:** Nếu quay lại sửa ở Cổng 1 hoặc 2, mọi artifact, bản vẽ và approval của các bước sau đều bị hủy bỏ đệ quy chính xác.

---

## 6. TRÁI TIM NGHIỆP VỤ 2: GOVERNED LEARNING & THU NẠP TRI THỨC (/hoc, /hoc-cta)

Hệ thống học tập của Hermes Personal tuân thủ kiến trúc thắt lưng hẹp: **Không fine-tune trọng số model**, mà học qua **Bộ nhớ có kiểm duyệt (Governed Memory) và Kỹ năng quy trình (Procedural Skills)**.

### 6.1 Quy trình 8 bước chống ảo giác (Anti-Hallucination Procedure)
Cả hai kỹ năng `/hoc` (bóc tách tri thức chuyên sâu) và `/hoc-cta` (bóc tách cấu trúc chuyển đổi) đều bắt buộc tuân thủ:

```
[1. Thu thập Media Thực] ──> Tải video_sample.mp4 từ link TikTok/YouTube. Thất bại thì dừng ngay.
       ↓
[2. Kiểm tra Media Vật lý] ──> Xác nhận file tồn tại, tính SHA-256, byte size, duration thực tế.
       ↓
[3. Tách Âm thanh Chuẩn] ──> Xuất audio.wav. Nếu video câm thì ghi nhận has_audio: false (cấm tạo tiếng giả).
       ↓
[4. Bóc Băng Lời thoại & Khung hình] ──> Ghi exact_transcript.txt từng giây, chụp frame đọc chữ trên màn hình.
       ↓
[5. Phân Tích Có Căn Cứ] ──> Xuất knowledge_analysis.md hoặc cta_analysis.md. Mọi luận điểm phải gắn timestamp.
                               Vẽ ít nhất 1 sơ đồ Mermaid. Đánh nhãn [inference] nếu là suy luận.
       ↓
[6. Sinh Manifest Lưu Trữ] ──> Ghi artifact_manifest.json lưu toàn bộ SHA-256 và đường dẫn file vật lý.
       ↓
[7. Đề Xuất Ứng Viên Tri Thức] ──> Gọi `knowledge_candidate_create`. Trạng thái lưu là 'pending_approval'.
                                    CẤM tự ý sửa System Prompt hay bộ nhớ chính thức.
       ↓
[8. Xác Thực Trên Đĩa & Phản Hồi] ──> Kiểm tra file thực sự tồn tại trên ổ cứng trước khi báo hoàn tất.
```

### 6.2 Quản trị Đánh giá & Xuất bản Kỹ năng
- **Chính sách phân loại rủi ro (Risk Matrix):**
  - *Sở thích rủi ro thấp* (tone giọng, format hiển thị, locale) có xác nhận của người dùng $\rightarrow$ Tự động áp dụng vào `USER.md`.
  - *Tri thức & Quy trình thao tác (Knowledge & Procedures)* $\rightarrow$ **Bắt buộc Human-In-The-Loop Approval (Gate 4)** mới được kích hoạt.
  - *Dữ liệu nhạy cảm* (API key, token, mật khẩu, PII) $\rightarrow$ Tự động từ chối và cảnh báo.
- **Xuất bản Kỹ năng An toàn (`skill_publisher.py`):** Chỉ xuất bản ra file `SKILL.md` hợp lệ với YAML frontmatter chứa `name`, `allowed-capabilities`, `digest`, và quét cấm hoàn toàn các chỉ thị nguy hiểm (`rm -rf`, `curl | bash`, `eval`).
- **Cơ chế Rollback nguyên tử:** Mỗi bản cập nhật tri thức được gán số phiên bản nguyên tăng dần. Rollback sẽ chuyển con trỏ kích hoạt về phiên bản trước mà không xóa lịch sử bằng chứng.

---

## 7. TOPOLOGY VẬN HÀNH & MÔI TRƯỜNG RUNTIME THỰC TẾ TRÊN WINDOWS

### 7.1 Mô hình Tiến trình do Supervisor Giám Sát
Khi chạy `hermes start`, tiến trình `Supervisor` sẽ quản lý vòng đời các dịch vụ:

```
                          ┌────────────────────────┐
                          │  Operator Browser      │
                          └───────────┬────────────┘
                                      │ Port 3000
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ SINGLE-NODE SUPERVISOR TOPOLOGY (Windows)                                  │
│                                                                            │
│  ┌───────────────────────┐             ┌────────────────────────────────┐  │
│  │  Web UI (Vite/React)  │             │  Public App API (:8000)        │  │
│  │  Port 3000            │             │  (Loopback Reverse Proxy)      │  │
│  └───────────────────────┘             └───────────────┬────────────────┘  │
│                                                        │ Bearer Token      │
│                                                        ▼ (Loopback Only)   │
│                                        ┌────────────────────────────────┐  │
│                                        │  Gateway Server (:8642)        │  │
│                                        │  - HermesTurnService           │  │
│                                        │  - SessionScopedAgentPool      │  │
│                                        └───────────────┬────────────────┘  │
│                                                        │                   │
│                                        ┌───────────────▼────────────────┐  │
│  ┌─────────────────────────┐           │  SQLite Database               │  │
│  │ Durable Outbox Worker   ├───────────┤  $env:HERMES_HOME\hermes.db   │  │
│  │ (Polls workflow_outbox) │           │  (WAL Mode, Atomic Tx)         │  │
│  └─────────────────────────┘           └────────────────────────────────┘  │
│                                                                            │
│  [Tùy chọn tắt trong Local Example]:                                       │
│  - MCP Standalone Runner (`enable_mcp: false`)                             │
│  - Telegram Ingress Runner (`enable_telegram: false`)                      │
└────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Phân định Cấu hình: Bí mật (.env) vs Hành vi (config.yaml)
- **`.env` (Chỉ chứa Secrets):** Lưu trữ tại `~/.hermes/.env`. Chỉ dùng cho API Keys, Service Tokens (ví dụ: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`).
- **`config.yaml` (Cấu hình Hành vi & Runtime):** Lưu trữ tại `~/.hermes/config.yaml` hoặc profile chỉ định. Chứa toàn bộ timeouts, thresholds, routing, model, provider_mode, và multiplexing.
- **Tập tin cấu hình mẫu chuẩn chạy local (`runtime-config.local.yaml.example`):**
  ```yaml
  runtime:
    mode: development
    provider_mode: fake    # Chạy kiểm thử hoàn toàn miễn phí
    gateway_port: 8642
    app_api_port: 8000
    web_port: 3000
    enable_web: true
    enable_telegram: false # Tắt nếu chưa cấu hình bot token
    enable_workers: false  # Bật khi cần worker xử lý outbox ngầm
    enable_mcp: false      # Tắt trong fake mode
  ```

---

## 8. CẨM NANG VẬN HÀNH HÀNG NGÀY & QUY TRÌNH KIỂM THỬ (DEVOPS PLAYBOOK)

### 8.1 Bộ Lệnh Khởi Động Nhanh Trên Windows PowerShell

#### Bước 1: Đồng bộ môi trường (Lần đầu hoặc sau khi kéo code)
```powershell
uv sync --extra web --extra dev
npm --prefix web install
```

#### Bước 2: Khởi động hệ thống Local Dev (Gateway + App API + Web UI)
```powershell
$env:HERMES_HOME = Join-Path $PWD ".runtime\hermes"
$env:HERMES_API_KEY = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant()
$env:HERMES_OWNER_ID = "local-owner"

uv run hermes start --config .\runtime-config.local.yaml.example --no-open-browser
```
Truy cập: `http://127.0.0.1:3000/omni`. Hệ thống chạy ở chế độ fake provider, phát sinh sự kiện giả lập chuẩn xác mà không tốn một đồng chi phí API nào.

#### Bước 3: Vận hành Outbox Worker riêng (Khi kiểm thử pipeline nền)
```powershell
$env:HERMES_PROVIDER_MODE = "fake"
uv run python -m hermes_personal.workflows.worker --db-path .runtime\hermes\hermes.db --poll-interval 1.0
```

---

### 8.2 Quy Trình Vận Hành Hàng Ngày của Operator (Daily Runbook)

#### Ca Sáng: Sản xuất Video AI từ READY Batch
```powershell
# 1. Liệt kê danh sách sản phẩm READY từ Product-Intelligence
hermes personal video list

# 2. Khởi chạy pipeline cho sản phẩm chọn lọc
hermes personal video start --product-keys <canonical_key> --provider-mode configured

# 3. Kiểm tra trạng thái và duyệt Gate 1 (Product Lock sau khi Image QC đạt)
hermes personal video status <workflow_id>
hermes personal video approve <approval_id>

# 4. Duyệt Gate 2 (Creative Brief) và Gate 3 (Scene Plan)
hermes personal video approve <approval_id> # Gate 2
hermes personal video approve <approval_id> # Gate 3

# 5. Duyệt Gate 4 (Storyboard) và CẤP QUYỀN NGÂN SÁCH RENDER
hermes personal video approve <approval_id> --authorize-cost --authorization-id auth_01 --campaign-max-cost-usd 100 --workflow-max-cost-usd 10 --authorization-expires-at 2026-09-17T00:00:00Z

# 6. Xem video MP4 thực tế và duyệt Cổng Cuối (Gate 5)
hermes personal video status <workflow_id> # Lấy đường dẫn file MP4 mở xem
hermes personal video approve <approval_id> # Gate 5 Final Approval

# 7. Nhận file xuất bản tại exports/export_{id}/ để đăng thủ công lên TikTok
```

#### Ca Chiều / Khi Có Video Mẫu: Thu Nạp Tri Thức (/hoc, /hoc-cta)
```text
# Trong khung chat (CLI, Web hoặc Telegram):
/hoc https://vt.tiktok.com/xxxx/
# hoặc
/hoc-cta https://vt.tiktok.com/yyyy/
```
Kiểm tra file xuất xưởng trong thư mục run: `exact_transcript.txt`, `knowledge_analysis.md`, `artifact_manifest.json`, sau đó xem xét ứng viên tri thức trước khi approve.

---

### 8.3 Bộ Lệnh Kiểm Thử & Kiểm Soát Chất Lượng (Zero-Cost Verification)
Trước khi commit mã nguồn hoặc tạo pull request, toàn bộ các lệnh sau bắt buộc phải xanh (100% PASS):

```powershell
# 1. Kiểm tra tĩnh & định dạng mã nguồn
uv run ruff check hermes_personal tests/hermes_personal

# 2. Chạy toàn bộ test suite hermes_personal
uv run pytest tests/hermes_personal -q

# 3. Kiểm tra các module runtime và e2e trọng yếu
uv run pytest tests/hermes_personal/runtime tests/hermes_personal/e2e -q

# 4. Typecheck và build frontend
npm --prefix web run build

# 5. Kiểm tra khoảng cách git diff
git diff --check
```

---

## 9. BẢN ĐỒ TÀI LIỆU & PHÂN LOẠI DI SẢN (DOCUMENTATION TAXONOMY)

Nhằm chấm dứt tình trạng phân mảnh tài liệu do quá trình phát triển 7 Gates trong quá khứ, toàn bộ tài liệu trong `docs/` được phân loại chính thức như sau:

### 9.1 Nhóm Tài Liệu Chuẩn Mực Đang Hoạt Động (Active & Canonical)
- **`docs/HERMES_PERSONAL_MASTER_DOC.md`:** Bản tài liệu mẹ toàn diện này (Single Source of Truth).
- **`docs/README.md`:** Index và bảng điều hướng của `hermes_personal`.
- **`docs/architecture.md`:** Chi tiết các bounded context và sơ đồ máy trạng thái.
- **`docs/infrastructure.md`:** Đặc tả hạ tầng tiến trình, SQLite và filesystem.
- **`docs/data-contracts.md`:** Chi tiết các wire dataclasses (`AgentTurnRequest`, `AgentEvent`, `OutboxLease`).
- **`docs/idempotency-strategy.md`:** Cơ chế băm semantic digest và bảng khóa duy nhất.
- **`docs/error-handling.md`:** Phân loại lỗi, retry ownership và quy tắc No-DLQ.
- **`docs/known-gaps.md`:** Bảng kiểm toán 15 technical gaps (HP-001 $\rightarrow$ HP-015 đều đạt `MVP_DONE`).
- **`docs/superpowers/specs/product-video-master-spec.md`:** Đặc tả chuẩn của Video Factory.
- **`docs/superpowers/plans/product-video-master-plan.md`:** Lộ trình cài đặt chuẩn của Video Factory.
- **`docs/hermes-personal/operations.md`:** Cẩm nang vận hành chi tiết.
- **`docs/hermes-personal/product-video-runbook.md`:** Sổ tay thao tác chi tiết cho Video Factory.

### 9.2 Nhóm Tài Liệu Di Sản / Đã Bị Thay Thế (Historical Archive: `docs/old/`)
> ⚠️ **CẢNH BÁO:** Toàn bộ các tài liệu lịch sử, báo cáo sự cố cũ và các kế hoạch ngày đã được di chuyển tập trung vào thư mục `docs/old/` để tránh gây nhiễu cho luồng phát triển chính. **TUYỆT ĐỐI KHÔNG DÙNG LÀM MỤC TIÊU CÀI ĐẶT HOẶC CĂN CỨ NGHIỆM THU HIỆN TẠI:**
- **`docs/old/legacy-root/`:** Các tài liệu phân tích và RCA cũ từ thư mục gốc (`billing-lifecycle.md`, `rca-ssl-cacert-post-git-pull.md`, `production-integrity-fixes-2026-09-18.md`).
- **`docs/old/superpowers-specs/`:** Toàn bộ tài liệu thiết kế specs có ngày cũ (thay thế bởi `docs/architecture.md` và `product-video-master-spec.md`).
- **`docs/old/superpowers-plans/`:** Toàn bộ các kế hoạch ngày cũ từ Gate 1 - Gate 7 và các plan 2026-08/2026-09 (đã được hợp nhất đầy đủ vào `product-video-master-plan.md`).

---

## 10. SỔ TAY XỬ LÝ SỰ CỐ (TROUBLESHOOTING & INCIDENT TRIAGE)

| Triệu Chứng / Lỗi | Nguyên Nhân Gốc Rễ | Hành Động Khắc Phục Chuẩn |
| :--- | :--- | :--- |
| **Xung đột cổng (Port conflict: 8642 / 8000 / 3000)** | Có tiến trình chạy ngầm từ phiên trước chưa tắt sạch. | PowerShell: `Get-Process python, node \| Stop-Process -Force` sau đó chạy lại lệnh `start`. |
| **Readiness 503 / Startup probe fail** | SQLite bị lock, hoặc một callback khởi động bị fail dependency probe. | Kiểm tra `$env:HERMES_HOME\hermes.db`, xóa file WAL tạm nếu bị lock sau crash, kiểm tra quyền ghi ổ đĩa. |
| **`IdempotencyConflict`** | Cùng một `(owner_user_id, idempotency_key)` nhưng payload gửi lên có nội dung khác lần trước. | Sửa lại đúng request gốc nếu muốn retry, hoặc sinh một `idempotency_key` mới cho hành động logic mới. |
| **`TurnInProgress`** | Request trước đó với cùng key đang được cỗ máy suy luận xử lý dở dang. | Đợi turn hoàn tất và nghe event stream; tuyệt đối không xóa claim thủ công để tránh gọi LLM hai lần. |
| **Lỗi `binding_unavailable` (`code: binding_unavailable`)** | Cơ sở dữ liệu SQLite mới khởi tạo, chưa nạp active snapshot của Capability Catalog. | Chạy lệnh reload snapshot của catalog qua admin CLI hoặc script khởi động để ghi nhận snapshot mới vào SQLite. |
| **Thông điệp bị `quarantined` trong Outbox** | Tác vụ nền (render/research) bị lỗi vượt quá 5 lần thử lại (`max_attempts`). | Tra cứu cột `last_error` trong bảng `workflow_outbox`. Sau khi sửa lỗi cấu hình/mạng, gọi `requeue_quarantined(outbox_id)` để reset trạng thái về `pending`. |
| **Trạng thái `WaitingForOperator`** | Workflow bị chặn do QC fail, QC unknown do timeout mạng, hoặc hết hạn budget. | Chạy `hermes personal video status <workflow_id>` xem lý do chi tiết, kiểm tra ảnh/video, cấp thêm budget hoặc trigger retry có chủ đích. |
| **Stream SSE không thấy event mới** | Mất kết nối client hoặc cursor bị lệch. | Gọi endpoint `/api/events/replay?after_cursor=<last_seq>` để kéo lại đầy đủ sự kiện đã commit bền vững. |

---
*Tài liệu này được biên soạn và bảo chứng bởi kết quả làm việc đồng thuận của 3 Subagents: Core Architecture Auditor, Product Automation Lead, và DevOps & Runtime Engineer.*
