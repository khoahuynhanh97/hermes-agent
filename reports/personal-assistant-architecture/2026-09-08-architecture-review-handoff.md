# Hermes upstream rearchitecture — Architecture review & handoff

- Ngày review: 2026-09-08, Asia/Bangkok.
- Repository: `D:\work\hermes-upstream-rearchitecture`.
- Reviewer: Codex / Planner, static read-only audit.
- Verdict: **REWORK**.
- Target: `PERSONAL_HAPPY_PATH_V1`.
- Baseline: `b110018303a2d25fc2e39c9e37a009bfc9c36bda` **cộng dirty working tree**, không chỉ HEAD.
- Report được lưu theo yêu cầu riêng của user sau lượt audit. Chỉ tạo report này; không sửa source, coordination hoặc năm report cũ; không stage/commit.

## Cách dùng cho agent tiếp theo

Đọc report này trước. Nó tổng hợp source evidence, caller chains, root causes, trạng thái các subsystem, các scenario recovery và assignment đề xuất; không cần lặp lại discovery toàn codebase.

Trước khi triển khai, chỉ cần kiểm tra HEAD/status và diff của các file thuộc slice được chọn. Line numbers dưới đây thuộc working tree ngày audit, có thể thay đổi sau edit. Symbols là anchor chính. Nếu baseline đã đổi, đối chiếu phần thay đổi liên quan; không tự biến kết luận lịch sử thành chứng nhận revision mới.

**Không xem report này là authorization triển khai hoặc chạy test/live.** User đã cho phép review và lưu report; chưa yêu cầu sửa source ở lượt lưu báo cáo. Prompt Worker cuối report là đề xuất để dùng khi được giao triển khai.

Quy tắc evidence: code tồn tại không đồng nghĩa runtime reachable; registered tool không đồng nghĩa trusted caller; UNKNOWN không phải DEAD/PASS; test fake không chứng minh production integration.

## 1. Executive verdict

| Câu hỏi | Kết luận |
|---|---|
| Kiến trúc đã chuẩn chưa? | Chưa. Cùng dùng lớp AIAgent, nhưng personal gateway, agent pool và history ownership vẫn song song upstream. |
| Happy path đã chạy được chưa? | Chưa đủ implementation để xác nhận. Configured contracts đứt từ Lock → Brief, approval → VF state, Render → Final/Export. |
| An toàn chạy fake/offline? | Có thể kiểm thử với temp HERMES_HOME, chặn mạng, explicit fake. Chưa chứng nhận hermes start mặc định là offline-safe. |
| An toàn chạy paid provider? | Chưa: direct MCP vượt budget/dispatch guard; approval thiếu exact binding; restart settlement chưa hoàn chỉnh. |
| PERSONAL_HAPPY_PATH_V1 accepted? | Không. Blocker là correctness/HITL/durability cơ bản, không phải distributed hardening có thể hoãn. |

Không ghi nhận P0 đã được chứng minh. Các P1 phía dưới đủ để REWORK, không chỉ BLOCKED_ON_EVIDENCE.

### Verification đã thực hiện và giới hạn

- Đọc source, tracked diffs, untracked code liên quan, docs, coordination, năm architecture reports và test source.
- Không chạy pytest, import runtime, MCP subprocess, Telegram, service restart hay provider.
- `git diff --check` thành công; có cảnh báo CRLF.
- Không sửa/tạo file trong lượt audit; danh sách git status cuối audit giống ban đầu. Không có baseline content hashes để tuyên bố đã hash-verify byte-for-byte.
- Lượt lưu report chỉ tạo file Markdown này. HEAD/status đã được kiểm tra lại, vẫn khớp baseline.
- Không cấp nhãn TESTED, REAL_SUBPROCESS_OBSERVED, INTEGRATION_TESTED hoặc LIVE_PROVIDER_OBSERVED mới cho revision này.
- CONFIRMED trong report nghĩa là source và caller chain đã được trace; không có nghĩa deployment đó đang chạy trên máy.

## 2. Baseline, provenance và coordination

### Git

- HEAD: `b110018303a2d25fc2e39c9e37a009bfc9c36bda`.
- HEAD subject: `feat(integration): ARCH-G3 bounded happy-path integration with FastMCP video factory and personal skills`.
- Không có staged changes.
- Sáu tracked files modified: tổng 597 insertions / 92 deletions.

| File | + / - | Dirty scope |
|---|---:|---|
| `.hermes/coordination.md` | 31 / 30 | Handoff R3-R3-RENDER-SUBMISSION-SAFETY |
| `agent/skill_commands.py` | 3 / 8 | Bỏ project skill scan ngoài trusted resolver |
| `hermes_personal/integrations/knowledge/__init__.py` | 22 / 6 | Owner, LearningKind, provenance |
| `hermes_personal/integrations/video_factory/server.py` | 294 / 18 | Input validation, approval, render/export |
| `hermes_personal/orchestration/turn_service.py` | 14 / 2 | Context handling |
| `hermes_personal/product_video/handlers.py` | 233 / 28 | Durable render intent/checkpoint/result/error handling |

### Mười commit gần nhất tại audit

```text
b110018303 feat(integration): ARCH-G3 bounded happy-path integration with FastMCP video factory and personal skills
7e41290fbd fix(test): init budget engine and fix debug cursor var in e2e http workflow test
1777832bdf docs(coordination): update ownership matrix and handoff CANONICAL-ASSISTANT-FULL-FIX-R2 to PLANNER
7626c20fa0 fix(workflows): initialize budget engine and enforce paid-outcome safety
9cb4d2dcba fix(product): ensure fail-closed external MCP research dispatch
def30c84ba feat(video): port canonical Video Factory MCP edge to hermes_personal and add compatibility shims
dccc950250 fix(knowledge,skills): repair Knowledge MCP durable persistence and make /hoc skills self-contained
fa55b6464f docs(coordination): hand off CANONICAL-ASSISTANT-FULL-FIX-R1 to PLANNER
06f4b1f20f feat(video): add canonical Video Factory MCP server under hermes_personal/integrations
f0ec94c103 refactor(skills): remove /hoc* special branches; rely on skill-command dispatch
```

Các commit trên đã có port VF, Knowledge/skills, configured research, budget initialization và ARCH-G3 tests. Dirty safety fixes không thuộc các commit này. Không lấy test counts của chúng chứng nhận dirty tree.

### Untracked trước khi lưu report

```text
.skills_prompt_snapshot.json
.todos.md
SOUL.md
agent/knowledge_capture_prompt.py
hermes_personal/gateway/platforms/telegram_runner.py
reports/audio.wav
reports/exact_transcript.txt
reports/hermes-master-idea.html
reports/hermes-project-status-2026-08-29.html
reports/knowledge_capture/artifact_manifest.json
reports/knowledge_capture/audio.wav
reports/knowledge_capture/exact_transcript.txt
reports/knowledge_capture/knowledge_analysis.md
reports/knowledge_capture/video_sample.mp4
reports/runtime-truth/gate-0-1/audit_report_gate_0_1.md
reports/runtime-truth/gate-0-1/baseline.md
reports/runtime-truth/gate-0-1/command-transcript.txt
reports/runtime-truth/gate-0-1/contradictions.md
reports/runtime-truth/gate-0-1/executive-summary.md
reports/runtime-truth/gate-0-1/gate-2-candidates.md
reports/runtime-truth/gate-0-1/gate_0_baseline.json
reports/runtime-truth/gate-0-1/gate_1_runtime_closure.json
reports/runtime-truth/gate-0-1/gate_1_test_inventory.json
reports/runtime-truth/gate-0-1/generate_audit_rework.py
reports/runtime-truth/gate-0-1/generate_manifest.py
reports/runtime-truth/gate-0-1/manifest_comparison.json
reports/runtime-truth/gate-0-1/module-inventory.csv
reports/runtime-truth/gate-0-1/preservation_manifest_end.json
reports/runtime-truth/gate-0-1/preservation_manifest_start.json
reports/runtime-truth/gate-0-1/process-topology.md
reports/runtime-truth/gate-0-1/run_audit.py
reports/runtime-truth/gate-0-1/runtime-call-path.md
reports/runtime-truth/gate-0-1/validate_and_rebuild_gate1.py
reports/tiktok_info.json
reports/tikwm_data.json
reports/video_sample.mp4
tests/agent/test_knowledge_capture_prompt.py
tests/skills/test_learning_from_video_skill.py
```

Không cần đọc lại media để xử lý các findings kiến trúc. Telegram runner tồn tại trong working tree nhưng không tồn tại trong HEAD.

### Report/coordination mismatch

- Năm architecture reports ghi baseline `b193b1d07e`; lần sửa gần nhất thư mục tại `1777832bdf`.
- Current Owner và Next Action Owner đều PLANNER; phần này nhất quán.
- Current assignment: `R3-R3-RENDER-SUBMISSION-SAFETY`, AWAITING_PLANNER_REVIEW, IMPLEMENTED_UNVERIFIED.
- Last Worker Report vẫn là `ARCH-G2-CANONICAL-OWNERSHIP-AUDIT`, rồi ghép live evidence cũ. Assignment/report không nhất quán.
- Phase 0–7 COMPLETED và known-gaps MVP_DONE không đồng nghĩa acceptance hiện tại; coordination cũng tự giữ topology, approval DB/binding và export OPEN.
- Live Veo claim ở report cũ chưa được tái xác minh, không dùng làm LIVE_PROVIDER_OBSERVED cho revision này.

## 3. Kiến trúc chuẩn dùng để đánh giá

1. `run_agent.AIAgent` là canonical conversational brain; upstream sở hữu lifecycle/session/history.
2. CLI, Telegram, Web, TUI/Desktop, Omni là ingress adapters.
3. HermesTurnService nếu giữ lại chỉ chuyển contract/projection, không second provider selection, prompt assembly, domain intent, transcript hay conversation loop.
4. Knowledge, Product Research, Video Factory là edge capabilities; skills hướng dẫn, tools/MCP thực thi.
5. Workflow chỉ giữ durable sequencing/state/jobs/approvals/budget/outbox/recovery; SQLite authoritative.
6. Prompt prefix byte-stable trong conversation; không dynamic Knowledge system injection.
7. Product Lock → Brief → Scene Plan → Storyboard → Render Budget → Final là HITL gates.
8. Model không tạo approval authority; bind exact O/P/W/A/V/J, không blind paid retry hoặc release uncertain liability.
9. Trusted skill discovery, quarantine/disabled/project_discovery phải được tôn trọng.
10. hermes start launch/reuse upstream lifecycle, readiness phải kiểm tra service thực.

## 4. Findings

Mọi path dưới đây relative với repository root; line numbers thuộc dirty tree ngày audit.

### F1 — P1: Duplicate lifecycle/session/history ownership

- Evidence: `runtime/processes.py:83` (dưới hermes_personal), `runtime/gateway_server.py:67–104,329`, `orchestration/turn_service.py:126,138,228,241–249`.
- Caller: plugin register → runtime CLI handle_start → topology → Supervisor → personal gateway → HermesTurnService/EventRepository → SessionScopedAgentPool → UpstreamAIAgentAdapter → AIAgent.
- Trigger: chạy personal topology, nhất là bật Telegram runner cùng lúc.
- Hiện tại: personal gateway giữ agent theo session và assemble persisted history riêng. Telegram runner gọi nguyên upstream gateway, nơi có agent/session ownership khác.
- Tác động: cùng lớp AIAgent nhưng hai lifecycle/history owners; vi phạm facade mỏng. Không gọi đây là hai thuật toán LLM khác nhau.
- Sửa nhỏ nhất: chọn upstream session/lifecycle owner; start launch/reuse owner đó; personal HTTP facade chỉ transport/contract/projection; workflow worker giữ ở edge.

### F2 — P1: Direct MCP render ngoài durable paid admission

- Evidence: `integrations/video_factory/server.py:872` render; `:1025` provider submit; ALL_VIDEO_FACTORY_TOOLS đăng ký render.
- Caller: configured upstream MCP tools → server.render → video_prov.submit.
- Trigger: agent gọi MCP render trực tiếp với provider configured.
- Hiện tại: chỉ storyboard guard; không workflow budget reservation, durable DISPATCHING, accepted checkpoint hoặc render-budget decision.
- Tác động: paid action/retry nằm ngoài safety guard của worker.
- Sửa: dùng cùng durable paid admission cho MCP và worker; bind operation, exact approval và reservation trước dispatch. Không dùng model-supplied approved flag làm authority.

### F3 — P1: Approval không exact-bind; Product Lock bypass

- Evidence: `integrations/video_factory/server.py:367` _verify_operator_approval; callers `:413,438,493,506`; ResourcePackInput `:91`; resource_pack_save `:283`; resource_pack_lock `:296`.
- Hiện tại: status approved bắt buộc nhưng owner/project optional; gate không so; caller không truyền expected artifact; không so version. workflow_id còn bị dùng thay project_id.
- Trigger: reuse approval khác gate/cũ, payload thiếu bindings, hoặc gọi lock/save pack có locked_at.
- Tác động: HITL bị vượt dù model không trực tiếp gọi ApprovalService.approve; approval hợp lệ cũng có thể bị reject nếu W khác P.
- Sửa: trusted receipt bind exact owner/project/workflow/gate/artifact/version; lock state do server quyết định từ receipt hợp lệ, không nhận từ input.

### F4 — P1: Upstream mutations giữ approval downstream cũ

- Evidence: `integrations/video_factory/service.py:122` save_creative_brief; `:145` save_scene_plan; `:402` save_draft_video.
- Hiện tại: brief save chỉ reset brief; scene save chỉ reset scene; draft save không clear Final. Unlock/relock cũng chưa invalidate descendants đầy đủ.
- Trigger: sửa nội dung upstream sau downstream approval qua direct MCP/service.
- Tác động: render/export nội dung mới bằng approval cũ. Binding-layer invalidation không bảo vệ đường direct service này.
- Sửa: chung descendant invalidation ở authoritative VF mutation boundary, tăng version và invalidate approvals phụ thuộc.

### F5 — P1: Export arbitrary MP4 bằng project-level Final flag

- Evidence: `integrations/video_factory/server.py:1108` export; `:1161` Final check; `:1170–1233` path/copy.
- Hiện tại: nhận caller MP4, kiểm tra exists/nonempty/suffix, copy vào exports. Không match draft/render/job/owner-artifact/digest/version. Source containment không kiểm tra; destination containment có.
- Trigger: project đã Final-approved nhưng caller gửi file khác.
- Tác động: xuất artifact chưa approved hoặc ngoài scope. copy2 chạy lại có thể overwrite; idempotency_key chỉ đặt ID.
- Sửa: resolve path từ durable completed artifact được exact Final-approved; persist export receipt, reject semantic replay khác.

### F6 — P1: Configured workflow → VF contracts bị đứt

- Evidence: `product_video/handlers.py:1720`; VF server create_brief `:547,575,587`; scene input `:675`; `application/operator_handler.py:21,112–120`.
- Hiện tại: Lock → Brief chỉ truyền resource_pack. VF đòi existing project, locked pack và caller-authored creative fields. Chưa có bootstrap/manifest transfer/creative authoring bridge. Scene cần scenes/steps mà brief output không chứa.
- Operator approval cập nhật workflow DB/outbox, không đổi VF approval state hoặc truyền approval request ID tới bước sau.
- Trigger: chạy configured components thật.
- Tác động: fail validation/approval sau khi operator đã approve workflow.
- Sửa: từng bridge nhỏ có producer/consumer contract; agent/user cung cấp content, workflow chỉ persist/sequence.

### F7 — P1: Render → Final/export mất identity, thiếu draft persistence

- Evidence: `product_video/handlers.py:691–701` normalized render result; `:722` export project resolution; VF server get_job_status `:1044,1080`; service approve_final_video `:418`.
- Hiện tại: wrapper render bỏ P; completed poll cũng thiếu O/P. Poll trả file nhưng không persist generated scene/timeline/draft association.
- Trigger: real wire render completed → Final/export.
- Tác động: PROJECT_ID_REQUIRED hoặc DRAFT_VIDEO_REQUIRED; restart không đủ association.
- Sửa: durable operation → O/P/W → A/V/J; persist draft result và preserve identity trên status/normalized artifact.

### F8 — P1: Budget owner theo worker PID; resume/replay bỏ settlement

- Evidence: `workflows/worker.py:59–66`; budgets owner lookup `workflows/budgets.py:199,223`; handlers render `:1267,1295,1410`.
- Hiện tại: global budget engine owner=durable-worker-PID; accepted resume alloc=None; COMPLETED return trước settle.
- Trigger: restart sau ACCEPTED/COMPLETED trước settle, worker PID mới hoặc nhiều workers.
- Tác động: reserved ledger treo; budget scope mới không kế thừa chủ workflow cũ.
- Sửa: stable workflow owner/scope, persist reservation ID cùng operation, lookup/settle idempotently khi resume/replay; không reserve mới để sửa settlement.

### F9 — P1: Crash sau success commit trước ACK replay sai

- Evidence: `product_video/handlers.py:1236` validation trước receipt; `:957` HITL guard; `:1790` duplicate command; `workflows/repository.py:80` DuplicateCommandError.
- Trigger: JobSucceeded/HITL đã commit, process chết trước ACK.
- Hiện tại: fresh handler gặp HITL_APPROVAL_REQUIRED; warm cache return success nhưng topic wrapper ghi command trùng.
- Tác động: success delivery bị retry/quarantine thay vì ACK.
- Sửa: receipt-first processed-message lookup trước handler/state validation; match workflow/message/action/input rồi ACK current lease.

### F10 — P1/P2: Target ownership còn thiếu

- Evidence: `application/operator_handler.py:21`; VF server render resume `:902`; get_job_status `:1044`; EventsAPI `application/events_api.py:203`.
- HTTP token được owner-bound trong stock gateway, nhưng operator handler không match owner target workflow/request với cmd owner; ghi caller owner vào next job.
- VF MCP owner là model argument; active_job_id resume trả trước project authorization; status chỉ nhận J.
- Trigger: foreign target ID trong DB/shared provider scope.
- Tác động: object authorization thiếu. Single-owner deployment hạn chế exposure nhưng không thay thế target binding; chưa quan sát exploit live.
- Sửa: trusted owner context, durable operation/project lookup ở mọi consumer; reject foreign target.

### F11 — P2: Startup/discovery và readiness chưa thật đầy đủ

- Evidence: `runtime/processes.py:153,160,179,198`; `runtime/config.py:42`; `runtime/supervisor.py:359–362`; gateway_server `:251,404–408`; capability service `:105–119`; discovery `:116–127`.
- Default enable_mcp=True launch missing `hermes_personal.capabilities.mcp_runner`.
- exec/noop probe thường chỉ is_alive, mcp_snapshot_check không execute. Worker/Telegram readiness PID-only.
- Gateway imports registry nhưng không discover MCP trước catalog.reload; lazy AIAgent init sau readiness quá muộn.
- Knowledge manifest mong mcp__learning__create_candidate/learning_create_candidate, server expose knowledge_candidate_create/knowledge_retrieve; mapping lệch.
- Parent CLI coordinator callbacks None vẫn mark completed/ready (`runtime/cli.py:65–69`, `startup.py:186–237`). Child gateway `_health_api` có migrations/recovery callbacks thật (`:259–266`); không gọi toàn bộ startup no-op.
- Sửa: upstream-owned discovery, bỏ target giả, readiness theo service/capability thật, parent chỉ báo đúng preflight.

### F12 — P2: Knowledge promotion/trust/provenance chưa khép kín

- Evidence: `integrations/knowledge/__init__.py:194,211`; `learning/promotion.py:118–149`; repository `:125`; models EvidenceRef; evaluator evaluate.
- MCP expose candidate create/retrieve nhưng create không nhận evidence dù skill yêu cầu grounded evidence.
- Chưa có production caller nối evaluation/operator/promotion. request_promotion fallback sinh approval ID không durable approval authority.
- approve_promotion nuốt approval exception rồi promote; nếu không có approval service cũng promote. Đây là internal primitive defect; không khẳng định model gọi được nó qua MCP hiện tại.
- Repository INSERT OR IGNORE identity từ candidate input, không đòi trusted identity đã tồn tại.
- Dirty owner binding chặn foreign argument trên create/retrieve, nhưng owner từ HERMES_OWNER_ID/default_user, chưa session identity transport.
- LearningKind Literal đã sửa đúng cách validate. Tuy nhiên source_type=unverified chưa trong EvidenceRef Literal; evaluator vẫn gọi evidence đó validated. Không suy diễn thành runtime type error vì dataclass không enforce Literal.
- Sửa: trusted operator receipt/promotion path, identity từ ingress, provenance contract rõ; missing source không gọi grounded.

### F13 — P2/P3: Test/report evidence overstated

- Evidence: `tests/hermes_personal/e2e/test_canonical_agent_integration.py:39,122`.
- Test tên upstream agent/MCP không tạo AIAgent; dùng fake handlers, tự set state/approve; không qua trusted operator/outbox/real VF transport/DB full chain.
- Budget init trong test không truyền durable connection. Discovery đọc private tool manager. Probe trả True từ initialize response, chưa đòi tools/list thành công hoặc usable expected tools.
- `docs/architecture.md:1` bị chèn lặp text bảng giữa các ký tự, tài liệu hỏng.
- Sửa: behavior integration test đúng boundary sau authorization; docs/report từ source hiện tại; không lấy tên/count test làm proof.

### Findings phụ cần giữ rõ scope

- P2 preflight: DISPATCHING ghi trước MCP local validation. Lỗi chắc chắn chưa provider submit (missing project/reference/approval) vẫn thành UNKNOWN và giữ hold. Tách preflight hoặc typed not_dispatched outcome có căn cứ; tuyệt đối không giải phóng uncertain charge.
- P2 export sibling: generic adapter quảng bá async export nhưng chưa có durable submission intent/completion như render. Stock VF export là local copy, không gọi đây là duplicate billing của stock exporter.
- Render dùng first storyboard frame; params có thể override approved prompt/reference. Missing một phần declared refs fail-closed; empty refs vẫn tới submit. Chưa chứng minh full multi-scene production.
- Approval DB `_canonical_approval_db_path:336` chọn env → home/hermes.db → home/data/hermes.db, rồi `_approval_service` fallback VF DB. Gateway có --db-path khác, chưa assertion same authority.

### Các nghi vấn đã loại bỏ / không được báo sai

- Không repo: render có nhánh dispatch_intent_committed=True, nhưng stock `_validate_state_and_version` chặn WORKFLOW_NOT_FOUND trước. Không báo bypass production từ riêng nhánh này.
- Telegram shim hiện gọi gateway.run.main thật, không phải no-op process; readiness của nó mới PID-only.
- `_maybe_prepend_context` hiện return history, không dynamic context injection. AgentContextAssembler definition/export còn đó nhưng chưa thấy production execution caller.
- Untracked knowledge_capture_prompt helper chưa thấy caller production; không báo live skill trust bypass từ helper.
- Worker module có main/__main__ thật, không missing như docs cũ.

## 5. Current runtime/caller map

```text
hermes CLI → HermesCLI → AIAgent.run_conversation (cli.py:16423)
Telegram adapter → gateway.run → gateway-owned AIAgent (:5752) → run_conversation (:6417)
TUI/Desktop → tui_gateway → AIAgent (:7177) → run_conversation (:11064)
Dashboard Chat → PTY → TUI → upstream TUI path

plugins/hermes_personal/__init__.py:8
  → runtime/plugin.py:register
  → runtime/cli.py:handle_start
  → processes.py:build_process_topology
  → Supervisor
      → personal gateway (required, port8642)
          → HermesTurnService + EventRepository history
          → SessionScopedAgentPool → UpstreamAIAgentAdapter → AIAgent
      → personal App API (port8000) → personal /api/turn + /api/omni/turn
      → development Web UI
      → durable worker (real main; PID readiness)
      → untracked Telegram shim → separate upstream gateway
      → missing capabilities.mcp_runner (default enabled)

durable worker → SQLite workflow/approval/budget/outbox → PI/VF MCP
configured AIAgent → standard MCP tools → direct VF server → provider
  (direct branch không tự đi qua worker budget/intent)

operator → approval/workflow DB
  - thiếu exact VF state/approval bridge → VF SQLite
provider status → local file
  - thiếu durable draft/artifact association → Final/export
```

Personal gateway chỉ web/omni normalizers (`gateway_server.py:354–359`), không CLI/Telegram cutover. Omni page còn React transcript/composer (`web/src/pages/OmniChatPage.tsx:24–30,129–155`), cần xét với upstream restriction về second dashboard chat trước khi mở rộng.

Không tính số AIAgent instances thành số brain algorithms. Vấn đề là owner lifecycle/history, không phải nhiều sessions dùng cùng class.

### Skills và MCP paths

- `agent/skill_commands.py:476` dùng trusted get_project_skills_dirs; `agent/skill_utils.py:751–767` kiểm tra project_discovery/trust.
- Quarantine/disabled tại skill_commands `:485–509`, skills_tool `:1386–1406,1489–1496`.
- `/hoc`, `/hoc_kien_thuc`, `/hoc_cta` generic skill aliases/normalization, không hardcoded core branch.
- `.agents/skills/**` là project source; `skills/**` packaged source; `get_skills_dir()` runtime install. Không tự suy ra install từ source.
- Skill allowed-capabilities hay AgentTurnRuntime text là declaration, không proof policy hook/caller.
- VF package trong pyproject package include hermes_personal. `src/hermes` có compatibility shims; không mặc định gọi toàn tree DEAD.
- Knowledge/VF packages không có __main__.py. main() trong __init__.py không làm `python -m hermes_personal.integrations.knowledge` hoặc `...video_factory` chạy được.
- VF probe dùng `python -m hermes_personal.integrations.video_factory.server` là module khác và tồn tại.
- Deployed external PI server/config chưa được xác minh; giữ UNKNOWN.

### Knowledge chain thực tế

```text
configured Knowledge MCP (deployment/discovery chưa chứng minh)
  → create_candidate(bound env/default owner)
  → LearningRepository + SQLite, draft/unverified source
  → [missing production evaluation/operator/promotion caller]
  → ApprovedLearningRetriever(active + candidate approved + same owner)
  → knowledge_retrieve MCP
  → [upstream consumption cần actual configured discovery]
```

Retriever approved-only guard tồn tại tại `learning/retrieval.py:50–55`. Không có bằng chứng production dynamic prompt assembler đang chạy.

## 6. Completion matrix

| Subsystem | Status | Evidence | Blocker |
|---|---|---|---|
| Upstream ingress | PARTIAL | CONFIRMED | Upstream paths thật, personal cutover chưa thống nhất |
| Canonical AIAgent ownership | PARTIAL | CONFIRMED | Cùng class nhưng duplicate pool/history/lifecycle |
| Skills | PARTIAL | CONFIRMED | Trust fix unverified, installed paths chưa chứng minh |
| Knowledge | PARTIAL | CONFIRMED | Promotion/trust/provenance/discovery |
| Product Research | PARTIAL | CONFIRMED | External deployment UNKNOWN, VF transfer thiếu |
| Video Factory | PARTIAL | CONFIRMED | Configured contracts/output bridge |
| HITL | OPEN | CONFIRMED | Gate/artifact/version/lock bypass |
| Budget | PARTIAL | CONFIRMED | PID owner, resume settle, direct MCP |
| Outbox/recovery | PARTIAL | CONFIRMED | Post-success/pre-ACK replay |
| Telegram | PARTIAL | CONFIRMED | Untracked shim, separate gateway, approval integration |
| hermes start | OPEN | CONFIRMED | Duplicate topology, missing module, readiness |
| Packaging/config/docs | PARTIAL | CONFIRMED / DECLARED_ONLY | Entrypoints/catalog/docs |
| Tests/runtime evidence | UNVERIFIED | UNKNOWN cho revision | Không chạy tests/runtime |

## 7. Product-to-video contract matrix

O/P/W/A/V/J = owner/project/workflow/artifact/version/provider job ID.

| Stage | Producer → consumer; schema/input/output | IDs/durable record | HITL/budget | Error/retry |
|---|---|---|---|---|
| Research | Worker → PI MCP; query/PDP → persisted snapshot | Snapshot ID required, O/W in job | Chưa live evidence | Missing configured binding fail-closed |
| Pack | Snapshot → PI build/lock → resource pack ref | ID/digest/status checks; VF manifest transfer thiếu | Workflow Product Lock có; direct VF bypass | Chưa end-to-end semantic manifest proof |
| Brief | Lock job → create_brief | VF P tồn tại + pack locked + creative fields required | Workflow approval không đổi VF | INVALID_INPUT / PROJECT_NOT_FOUND |
| Scene Plan | Brief ref → explicit scenes | P + approved brief + scenes required | Approval bridge thiếu | Adapter không truyền đủ scenes |
| Storyboard | Scene ref → frames | Persist VF storyboard/version | Receipt không exact A/V | Scene approval guard |
| Render Budget | Handler → BudgetEngine | SQLite reservation nhưng owner PID | Direct MCP ngoài gate | Resume không lookup allocation |
| Render | Storyboard → MCP/provider | Handler intent/J/result; direct MCP thiếu durable receipt | Storyboard flag, prompt/refs override | Handler UNKNOWN blocks retry |
| Poll/recovery | J → status → file | Thiếu O/P, draft/timeline persist | Giữ hold | Resume J có, settlement thiếu |
| Final | Operator → decision/workflow | VF cần draft chưa có bridge | Exact A/V thiếu | DRAFT_VIDEO_REQUIRED |
| Export | Render ref → copy | Path không từ approved A/V, có thể mất P | Chỉ project Final flag | Chưa durable export idempotency |

Payload JSON: dirty `_unpack_payload` reject corrupt JSON và merge nested result; không chứng minh mọi external response shape hợp lệ. Concrete identity loss đã chỉ ra ở F7, không gom mọi flattening thành bug suy đoán.

## 8. Paid-outcome và restart matrix

Scope: workflow handler path, không tự áp dụng direct MCP. Source anchors: `handlers.py:1234–1450`; WorkflowRepository; BudgetEngine; OutboxDispatcher.

| # | Scenario | Durable state / provider action | Budget / retry / recovery |
|---|---|---|---|
| 1 | Validation trước dispatch lỗi | Handler preflight chưa submit; VF local preflight bên trong MCP sau intent | Handler preflight không charge; VF local error có thể bị giữ UNKNOWN quá mức |
| 2 | Reservation lỗi | Không intent/provider | Nonretryable failure, sửa budget |
| 3 | Intent persistence lỗi | Không provider | Release attempt; release error bị nuốt; cần reconcile rõ |
| 4 | Crash sau intent trước call | DISPATCHING, không J | Hold retained, block resubmit, operator reconcile |
| 5 | Provider accepted response mất | DISPATCHING/UNKNOWN, không J | No blind retry ở handler; thiếu provider lookup by intent |
| 6 | Có J checkpoint lỗi | SQLite có thể chưa J | Liability retained, terminal/quarantine; J chỉ trong error |
| 7 | Crash sau ACCEPTED checkpoint | J durable, poll lại cùng J | Không submit lại; reservation cũ không settle |
| 8 | Poll timeout/lease loss | Giữ J; UNKNOWN/quarantine hoặc LEASE_LOST | Không release, reclaim/requeue resume; settle thiếu |
| 9 | Provider done, result write lỗi | Accepted J còn; chưa completion record | Commit/retain allocation; commit error có chỗ nuốt |
| 10 | Settlement hoặc ACK lỗi | COMPLETED / JobSucceeded durable | Replay bỏ settle hoặc quarantine success |
| 11 | Replay completed | Có result return nếu qua state guard | Zero submit nhưng receipt-first/settlement sai |
| 12 | Hai workers cùng operation | Lease/CAS bảo vệ outbox/intent một phần | Chưa concurrency proof; budget PID chia scope; direct MCP ngoài lease |

Window bổ sung: reserve commit riêng rồi crash trước intent có thể để orphan hold; stable owner/key reuse được nhưng PID owner mới phá continuity.

`DISPATCHING/UNKNOWN_OUTCOME` không có J được chặn resubmit — cải thiện đúng. `render_owner_user_id` được ghi nhưng chưa dùng authorize resume trong handler đã trace. UNKNOWN không được suy diễn thành chưa charge.

## 9. Test evidence inventory và giới hạn

- `tests/hermes_personal/e2e/test_canonical_agent_integration.py:39`: private tool manager + probe; không AIAgent tool selection/transport consumption.
- `:122`: fake clients, tự state/approval, budget init không durable conn; không chứng minh configured end-to-end.
- `tests/hermes_personal/product_video/test_product_to_video_e2e.py`: fake handlers/direct state approval; không production operator/VF bridge.
- `tests/hermes_personal/workflows/test_product_video_outbox.py:1740`: checkpoint before poll bằng connection thứ hai.
- `:1802`: network/resume J; `:1890`: checkpoint fail quarantine; `:2328,2390`: heartbeat failure.
- Một số restart tests reuse topic_handlers dù đổi dispatcher/connection; chưa chứng minh fresh-process handler recovery.
- Các budget initializations trong các đoạn test đã đọc không truyền durable connection; chưa chứng minh production PID-owner recovery.
- `tests/hermes_personal/product_video/test_pi_mcp_contract.py`: strict mock registry, không PI server thật.
- Không chạy test nào, không kết luận test hiện PASS hay FAIL. Code/test source observations không phải execution evidence.

## 10. Đối chiếu năm report và docs

| File | Sai lệch |
|---|---|
| canonical-ownership-matrix.csv | create_app sai symbol (đúng create_gateway_application:292); CapabilityPolicyEngine không tồn tại (Evaluator); workflows.service không tồn tại; gateway port8642/API8000; test/live cũ không cert dirty tree |
| runtime-removal-candidates.md | HTTP daemon gọi optional nhưng topology required; pool/history owner thực, không chỉ compatibility |
| target-runtime-flow.md | src/hermes path cũ, five gates, skills như executable DB/transport; target invariants trình bày vượt current proof |
| happy-path-gap-matrix.md | baseline b193b1d07e; thiếu blockers HITL/budget/export mới; worker wiring stale |
| next-implementation-slice.md | AIAgent/MCP verification kỳ vọng khác actual test; .agents/skills và skills paths lẫn nhau |

Docs thêm:

- `docs/architecture.md` malformed repeated insertion.
- `docs/README.md` và known-gaps còn mô tả worker runner optional/missing dù worker main thật.
- `docs/idempotency-strategy.md` vừa mô tả durable budget vừa còn đoạn budget in-memory; không authoritative so với source hiện tại.
- `docs/error-handling.md` còn generic workflow bugs đã được known-gaps ghi closed; cần reconcile source-specific.
- `docs/security-and-auth.md` nói clients deterministic không paid dù VF provider implementation tồn tại; không dùng mô tả này để cho phép chạy mặc định offline.

## 11. Kế hoạch tiếp theo: các slice độc lập

Thứ tự bắt buộc: audit → ownership decision → bounded fix → static verification → offline runtime verification → live chỉ sau authorization.

1. Chốt baseline và upstream lifecycle/session ownership. Không chữa happy path bằng mở rộng personal brain/gateway.
2. `VF-HITL-EXACT-BINDING-R1`: exact approval consumer bindings, một authority store. Prompt bên dưới.
3. Paid admission: direct MCP + worker dùng một durable gate/reservation/dispatch contract; Render Budget riêng.
4. Budget recovery: stable O/scope + reservation receipt + resume settlement.
5. Outbox receipt-first ACK: crash sau success commit không quarantine.
6. PI→VF bridge: project bootstrap/locked manifest + explicit creative input, chỉ chứng minh Lock→Brief trước.
7. Render→Final/export: preserve IDs, persist draft/completed artifact, export exact approved artifact.
8. Runtime consolidation/discovery/readiness: start upstream lifecycle, missing module/config mismatch, probes thật.
9. Knowledge operator promotion path + source/report/docs reconciliation.

Mỗi slice bàn giao baseline/diff/caller/evidence/remaining gaps riêng. Không gom thành một assignment “fix all”.

Offline verification khi được phép: temp HERMES_HOME, actual SQLite migration/reopen, fresh handlers/process, actual MCP transport với network-blocked provider stub, trusted operator path, artifact identity thật. Không tự set state để chứng minh full happy path. Live cần authorization/cap/operation scope riêng.

## 12. Prompt triển khai cho Worker (đề xuất, chưa dispatch)

**Assignment ID: VF-HITL-EXACT-BINDING-R1**

### Objective

Sửa bounded approval-consumption path để Creative Brief, Scene Plan, Storyboard và Final chỉ approved bằng quyết định operator đúng owner/project/workflow/gate/artifact/version. Không nhận model-supplied approval authority.

### Đọc trước

- Report này và AGENTS.md, docs security/data-contract/idempotency.
- `hermes_personal/integrations/video_factory/server.py`: `_canonical_approval_db_path`, `_approval_service`, `_verify_operator_approval`, bốn `*_approve`.
- `hermes_personal/integrations/video_factory/service.py`: get/save/approve/version liên quan.
- `hermes_personal/integrations/video_factory/domain.py`.
- `hermes_personal/workflows/approvals.py`: schema/invalidation.
- `hermes_personal/application/operator_handler.py`: producer decision.
- `hermes_personal/product_video/handlers.py`: producer pending approval payload.
- Test approval liên quan, không coi fake tests là production evidence.

### Root cause

Verifier chỉ bắt buộc approved status; owner/project optional; gate/version bỏ qua; expected artifact không truyền từ authoritative project. W bị xem như P. Approval DB heuristic fallback có thể chọn authority khác.

### Allowed scope

Approval payload producer/consumer trong các file trên, configuration resolution cần thiết cho authoritative approval store, focused tests và contract docs của slice. Bảo toàn user dirty edits. Không tự mở rộng sang runtime/core.

### Contract bắt buộc

- Expected O/P/W/A/V lấy từ trusted context/durable records; model arguments không là bằng chứng.
- Missing/mismatched binding fail-closed trước mutation.
- Không đồng nhất workflow ID với project ID.
- Configured authority unavailable không tự tạo approval DB khác.
- Approval/DB errors surfaced, không nuốt exception.
- Nếu thiếu producer contract hiện có để hoàn tất binding, bàn giao exact missing seam; không fabricate IDs hoặc auto-approve để vượt guard.

### Điều cấm

Không second brain/gateway/router; không sửa conversation loop/prompt; không auto-approve; không paid/live/Telegram/restart; không stage/commit/push nếu chưa yêu cầu. Không chạy tests nếu operator chưa cho phép.

### Success criteria

Cả bốn consumers reject missing owner, foreign O/P/W, wrong gate, wrong A, stale V, pending/rejected status, DB mismatch. Decision đúng chỉ áp dụng exact artifact/version. Failure không đổi VF approval state.

### Verification và handoff

Static trước. Khi được phép tests, dùng real temp SQLite producer/consumer, reopen connection; không chỉ mock verifier True. Bàn giao baseline/diff/caller chain/payload schema/DB resolution/negative-positive cases/evidence level. Không tests: IMPLEMENTED_UNVERIFIED.

### Remaining gaps bắt buộc OPEN

Product Lock bypass; direct render/Render Budget; settlement/recovery; outbox ACK replay; descendant invalidation ngoài slice; PI→VF bridge; render artifact/export; duplicate runtime/discovery; Knowledge promotion; live acceptance.

## 13. Tóm tắt cho người dùng

Hệ thống có nền tảng upstream AIAgent, SQLite workflow, MCP và skills; các dirty fixes đã tăng fail-closed. Tuy nhiên chưa accepted vì ba nhóm chính: (1) runtime/session ownership còn song song; (2) HITL/budget/artifact boundaries có bypass; (3) configured contract và recovery chưa nối kín. Ưu tiên exact approval bindings và paid safety trước khi chạy provider; sau đó nối từng bridge và kiểm chứng offline thật.
