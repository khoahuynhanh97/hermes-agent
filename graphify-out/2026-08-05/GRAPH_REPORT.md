# Graph Report - .  (2026-08-05)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 4807 nodes · 12464 edges · 260 communities (229 shown, 31 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 1489 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c9498458`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- HermesTikTokVideoFactoryApp
- app_staged.py
- MaintenanceRunner
- RuntimeState
- Database
- BackupTests
- ProjectionResult
- ProductResearchIntent
- test_telegram_affiliate_review.py
- Update
- LabeledTextbox
- Job
- ProductCandidate
- SQLiteAffiliateResearchRepository
- gui/app.py
- JobWorker
- WindowsHermesProcessController
- ShopeeAffiliateCsvSource
- ContentPackage
- test_crawl4ai_pilot.py
- video_editor.py
- GoogleSheetsProjection
- CodingAgentPlanner
- WebDocument
- SQLiteKnowledgeStore
- HermesTikTokVideoFactoryApp
- PromptStudioWorkflow
- WebFetchFailure
- MemoryRepository
- auto_crawler.py
- test_telegram_learning_delivery.py
- data_health.py
- PromptStudioFlow
- Result
- main.py
- KnowledgeLifecycle
- AffiliateContentService
- test_main_navigation_config.py
- ModelRequest
- AffiliateAnalysis
- web/package.json
- apply_schema_v2
- AgentJobManager
- ToolRegistry
- TikTokPublicReferenceAdapter
- DataHealth
- compilerOptions
- telegram_review_watcher.py
- server/app.py
- ProjectManager
- ._reload
- KnowledgeLifecycleWiringTests
- test_affiliate_analysis.py
- PatchExecutor
- test_v2_modules.py
- UnifiedKnowledgeStore
- PublicWebUrlPolicy
- analyze_video
- test_affiliate_research_acceptance.py
- WebAcquisitionService
- reviewer_app.py
- telegram_bot.py
- HermesAssistantRuntime
- tiktok_media_resolver.py
- get_store
- IdeaEngineTab
- crawler/__init__.py
- db.py
- job_watcher.py
- llm_gateway.py
- ShopeePlaywrightScraper
- test_telegram_ingestion.py
- reply_html
- AIRouter
- ClipLibrary
- test_reliability_integration.py
- .success
- affiliate_analysis_runner.py
- prompt_filter.py
- web_studio.py
- default_chat_handler
- WindowsRuntimeProcessTests
- app.tsx
- task_queue.py
- AffiliateProduct
- SimpleNamespace
- ConversationMemory
- fetch_transcript
- ReferenceMetadata
- JobDedup
- _FakeResponse
- template.sh
- reviewer_app_upgrade.py
- StoryboardTab
- VerificationRunner
- generate_phone_stand_review_batch.py
- prompt_library.py
- StaticWebDocumentFetcher
- knowledge_base.py
- TaskQueue
- PendingStore
- test_affiliate_research_repository.py
- .load_project_details
- .owner
- project.py
- manifest.json
- migrate_legacy_knowledge
- BaseWorker
- handlers/knowledge.py
- ArtifactStore
- telegram_auth.py
- SQLiteProjectRepository
- recover_pending_knowledge.py
- tts_engine.py
- utils.py
- PromptCompilerTab
- AgentJobsTab
- MemoryRepository
- domain/knowledge.py
- VideoFetcherTests
- projects.py
- .lib_refresh_cards
- RetrievalService
- handle_callback
- bgm_manager.py
- affiliate_worker.py
- create_corrected_phone_stand_storyboard.py
- ._render_idea_cards
- .script_refresh_learned_dropdown
- FFmpegCapability
- create_recreated_tiktok_pngs.py
- generate_phone_stand_front_lifestyle_video.py
- test_learning_recovery.py
- knowledge_command
- match_assets_to_script
- backfill
- generate_phone_stand_storyboard_video.py
- rebackground_phone_stand_video.py
- render_duck_foldable_commercial.py
- process_inbox
- main
- test_script_generator_knowledge_injection.py
- ._run_all_checks
- affiliate_video_prompt_base.ts
- create_one
- repair_knowledge_encoding.py
- resolve_route
- .agent_create_job
- clone_repo
- analyze_assembly.py
- generate_phone_stand_tiktok_large_scene.py
- prepare_one
- FakeResponse
- publish_recycled_video
- _TextExtractor
- migration.py
- YDLLogger
- permissions
- analyze_220247.py
- analyze_detailed.py
- analyze_detailed_220124.py
- generate_phone_stand_tiktok_fullscreen.py
- scripts/test_tiktok_media_resolver.py
- DocumentExtractionTests
- _EmbeddedJsonParser
- crawl_source
- ProjectMetadata
- patch_storyboard_with_exact_mechanism.py
- test_learning_fallback.py
- test_web_studio_api.py
- bot.py
- hitl-loop.template.sh
- get_router
- test_worker_json_and_transcript.py
- test_prompt_studio_project_routing.py
- test_job_operations.py
- backup_database.py
- block-dangerous-git.sh
- .export_prompts_from_storyboard
- .finish_export_prompts
- .lib_open_dir
- .open_auto_pipeline_dialog
- ._refresh_router_status
- .start_agent_jobs_auto_refresh
- .start_idea_generation
- .start_knowledge_learning
- ._tts_load_from_script
- affiliate/__init__.py
- model/__init__.py
- load_affiliate_csv.py
- migrate_v2_to_v5.py
- tests/hermes/__init__.py
- tests/__init__.py
- verify_affiliate_results.py
- verify_migration.py

## God Nodes (most connected - your core abstractions)
1. `Database` - 202 edges
2. `HermesTikTokVideoFactoryApp` - 131 edges
3. `SQLiteAffiliateResearchRepository` - 130 edges
4. `HermesTikTokVideoFactoryApp` - 116 edges
5. `MaintenanceRunner` - 102 edges
6. `SQLiteKnowledgeStore` - 101 edges
7. `Result` - 93 edges
8. `JobWorker` - 86 edges
9. `AffiliateProduct` - 85 edges
10. `ProjectionResult` - 85 edges

## Surprising Connections (you probably didn't know these)
- `AffiliateResearchJobError` --uses--> `ShopeeAffiliateCsvSource`  [INFERRED]
  core/affiliate_research_jobs.py → hermes/adapters/affiliate/shopee_csv.py
- `AffiliateResearchJobError` --uses--> `DisabledSheetsProjection`  [INFERRED]
  core/affiliate_research_jobs.py → hermes/adapters/google/sheets_projection.py
- `AffiliateResearchJobError` --uses--> `GoogleSheetsProjection`  [INFERRED]
  core/affiliate_research_jobs.py → hermes/adapters/google/sheets_projection.py
- `AffiliateResearchJobError` --uses--> `SQLiteAffiliateResearchRepository`  [INFERRED]
  core/affiliate_research_jobs.py → hermes/adapters/sqlite/affiliate_research_repository.py
- `AffiliateResearchJobError` --uses--> `SQLiteWebDocumentRepository`  [INFERRED]
  core/affiliate_research_jobs.py → hermes/adapters/sqlite/web_document_repository.py

## Import Cycles
- None detected.

## Communities (260 total, 31 thin omitted)

### Community 0 - "HermesTikTokVideoFactoryApp"
Cohesion: 0.03
Nodes (22): HermesTikTokVideoFactoryApp, Deprecated: functionality merged into build_tab_settings_merged., Deprecated: functionality merged into build_tab_learn_and_review., Tab Kho Phôi — quản lý clip library của project., Khởi tạo ClipLibrary cho project đang active., Import nhiều file video vào Kho Phôi., Mở thư mục clip_library của project., Refresh danh sách clip cards theo filter hiện tại. (+14 more)

### Community 1 - "app_staged.py"
Cohesion: 0.04
Nodes (74): Saves the configuration parameters back to the .env file and updates current…, save_config(), extract_keywords_from_product_page(), extract_smart_keywords(), generate_keywords(), nlp_expand_keywords(), Calls the Gemini API to generate video search keywords in Vietnamese, English,…, Strips noise words (freeship, chính hãng, giá rẻ, sale...) from product… (+66 more)

### Community 2 - "MaintenanceRunner"
Cohesion: 0.08
Nodes (11): BackupVerification, _atomic_write(), _identifier_hash(), MaintenanceResult, MaintenanceRunner, Path, Fail-closed orchestration for one serialized offline maintenance run., StateValidationError (+3 more)

### Community 3 - "RuntimeState"
Cohesion: 0.08
Nodes (22): BaseException, AuditReport, Finding, RepairPlan, RepairReport, ArtifactCollisionError, DatabaseRunLock, MaintenanceBusyError (+14 more)

### Community 4 - "Database"
Cohesion: 0.06
Nodes (47): AffiliateResearchJobError, AffiliateResearchJobHandler, AffiliateResearchJobWorker, build_affiliate_research_job_handler(), Any, JobRepository, Path, ValueError (+39 more)

### Community 5 - "BackupTests"
Cohesion: 0.07
Nodes (17): BackupOperationError, _label(), Path, RuntimeError, Return whether exclusive offline access is still active., _sha256_file(), _snapshot_identity(), _snapshot_stat() (+9 more)

### Community 6 - "ProjectionResult"
Cohesion: 0.08
Nodes (31): AffiliateCatalogService, AffiliateRunRequest, AffiliateRunService, _ProjectionFailures, Commit the affiliate research run before attempting external projections., Backward-compatible aggregate of all unresolved projections., RunResult, ProjectionResult (+23 more)

### Community 7 - "ProductResearchIntent"
Cohesion: 0.06
Nodes (40): _cell(), LocalSheetProjection, Any, Path, _redact(), _safe_segment(), DisabledSheetsProjection, _extract_category() (+32 more)

### Community 8 - "test_telegram_affiliate_review.py"
Cohesion: 0.07
Nodes (43): build_review_keyboard(), parse_review_callback(), Any, Synchronous projection adapter around an injected Telegram bot client., Create Telegram delivery only when both required environment values exist., Parse only compact affiliate review callback payloads., Render untrusted package data as Telegram-safe HTML., render_package_html() (+35 more)

### Community 9 - "Update"
Cohesion: 0.08
Nodes (68): Kiểm tra các trường cấu hình quan trọng và cảnh báo nếu thiếu., verify_config(), get_mode(), Shortcut helper to get the mode string from message text., affiliate_revise_command(), approve_all_command(), approve_command(), approve_force_command() (+60 more)

### Community 10 - "LabeledTextbox"
Cohesion: 0.06
Nodes (24): Creates the sidebar with status indicators and Auto option., Creates the tabbed workbook workspace area with topbar project selection., Tab Idea Engine ΓÇö AI gß╗úi ├╜ angle video, user tick chß╗ìn., Merged tab: Bi├¬n dß╗ïch Prompt + Cß║Ñu h├¼nh hß╗ç thß╗æng., ConsoleView, LabeledEntry, LabeledTextbox, PromptStudioActionBar (+16 more)

### Community 11 - "Job"
Cohesion: 0.07
Nodes (20): JobRepository, SQLiteJobRepository, JobService, Any, JobRepository, JobRepository, VideoService, Job (+12 more)

### Community 12 - "ProductCandidate"
Cohesion: 0.06
Nodes (35): ManualProductSource, Supplies candidates explicitly entered or selected by the user., EXPERIMENTAL: Shopee public search scraper. WARNING: For research/testing only.…, Parse Shopee API item structure into ProductCandidate., Apply post-fetch filters., Enforce minimum delay between requests., Map category ID to human-readable name., Heuristic visual signal detection from product name. (+27 more)

### Community 13 - "SQLiteAffiliateResearchRepository"
Cohesion: 0.07
Nodes (10): Connection, Row, Canonical SQLite persistence for affiliate research state., SQLiteAffiliateResearchRepository, utc_now(), _dump(), _load(), Any (+2 more)

### Community 14 - "gui/app.py"
Cohesion: 0.06
Nodes (28): LearningReviewStore, Local approval queue for Hermes learning proposals., Write a learning/prompt proposal into the human review queue., MainModule, Compatibility target for checks now reported only when requested., Creates the sidebar matching Web Studio layout 100%., _SilentStatusIndicator, Merged tab: Hß╗ìc hß╗Åi tß╗½ video mß║½u + H├áng ─æß╗úi duyß╗çt b├ái hß╗ìc… (+20 more)

### Community 15 - "JobWorker"
Cohesion: 0.06
Nodes (24): JobWorker, Exception, Path, Send Telegram notification when job is complete., Resolve TikTok media through the optional local crawler first. Photo posts need…, Fetch captions/audio only after TikTok media was classified as non-photo., Run vision analysis only over downloaded Photo Mode slides., Read small local text artifacts as untrusted transcript-like input. (+16 more)

### Community 16 - "WindowsHermesProcessController"
Cohesion: 0.07
Nodes (30): ArgumentParser, BinaryIO, _default_powershell_runner(), _normalized_path(), _ProcessSnapshot, CompletedProcess, Path, Exact Windows process control for the two Hermes entrypoints. (+22 more)

### Community 17 - "ShopeeAffiliateCsvSource"
Cohesion: 0.05
Nodes (26): ImportBatch, ImportRowError, Any, Path, Parses a user-authorized Shopee affiliate export without network access., ShopeeAffiliateCsvSource, DisabledProjectionFailureStore, DisabledReferenceCollector (+18 more)

### Community 18 - "ContentPackage"
Cohesion: 0.09
Nodes (15): Any, ImportSummary, RankedProduct, ContentIdea, ContentPackage, ProductSnapshot, ResearchBrief, ScoreBreakdown (+7 more)

### Community 19 - "test_crawl4ai_pilot.py"
Cohesion: 0.11
Nodes (54): _attempt(), load_entries(), main(), _peak_rss_mb(), _percentile(), PilotInputError, PilotRuntimeError, _probe_crawl4ai() (+46 more)

### Community 20 - "video_editor.py"
Cohesion: 0.06
Nodes (39): get_audio_duration(), Returns the duration of the audio file in seconds. Uses mutagen for speed,…, analyze_clip(), Analyzes the video clip quality locally using OpenCV. Computes brightness,…, Quality Gate check for the exported final video. Checks: - Resolution & Aspect…, verify_final_video(), crop_to_9_16_vertical(), cut_materials_into_clips() (+31 more)

### Community 21 - "GoogleSheetsProjection"
Cohesion: 0.07
Nodes (24): DisabledSheetsProjection, FakeSheetsProjection, _GoogleSheetsClient, GoogleSheetsProjection, Any, Protocol, Projects canonical affiliate research rows to a Google Sheets workbook., SheetsClient (+16 more)

### Community 22 - "CodingAgentPlanner"
Cohesion: 0.08
Nodes (28): build_search_query(), candidate_score(), CodingAgentPlanner, CodingPlan, is_generated_or_runtime_path(), match_reason(), Path, Hermes coding-agent dry-run planner. This module does not edit code. It selects… (+20 more)

### Community 23 - "WebDocument"
Cohesion: 0.08
Nodes (23): SQLiteWebDocumentRepository, WebDocument, WebFetchRequest, Protocol, WebDocumentFetcher, Protocol, WebDocumentRepository, test_web_document_immutable_fields() (+15 more)

### Community 24 - "SQLiteKnowledgeStore"
Cohesion: 0.09
Nodes (13): Path, build_lesson_fts_values(), _confidence(), _fts_items(), _json_dump(), _json_load(), Any, Connection (+5 more)

### Community 25 - "HermesTikTokVideoFactoryApp"
Cohesion: 0.05
Nodes (6): HermesTikTokVideoFactoryApp, Generate TTS voice file from text in tts_text_box., Deprecated: functionality merged into build_tab_settings_merged., Deprecated: functionality merged into build_tab_learn_and_review., L╞░u c├íc angle ─æ├ú tick chß╗ìn v├áo selected_angles.json., Performs a silent check on startup.

### Community 26 - "PromptStudioWorkflow"
Cohesion: 0.11
Nodes (17): PromptStudioService, Protocol, WorkflowRepository, PromptStudioStep, PromptStudioWorkflow, Enum, str, WorkflowStep (+9 more)

### Community 27 - "WebFetchFailure"
Cohesion: 0.13
Nodes (23): Crawl4AIUnavailable, Crawl4AIWebDocumentFetcher, Any, SafeBrowserConfig, SafeCrawlerRunConfig, NormalizationResult, WebDocumentNormalizer, default_resolver() (+15 more)

### Community 28 - "MemoryRepository"
Cohesion: 0.07
Nodes (8): AssistantContext, PersonalAssistant, Build the bounded context needed by one personal-assistant response., should_search_external(), MemoryRepository, MemoryRepositoryTests, PersonalAssistantTests, FakeMessage

### Community 29 - "auto_crawler.py"
Cohesion: 0.09
Nodes (39): _csv_path(), enqueue_job(), fetch_products_from_shopee(), main(), _now_slug(), Path, Auto crawler for affiliate research pipeline. Reads crawl rules (topic,…, Deterministic policy-compliant sample products when live API unavailable. Uses… (+31 more)

### Community 30 - "test_telegram_learning_delivery.py"
Cohesion: 0.09
Nodes (27): FakeBot, FakeManager, FakeMessage, FakeQuery, FakeRecoveryManager, HtmlFailingMessage, Path, Focused checks for Telegram learning result delivery and approval callbacks. (+19 more)

### Community 31 - "data_health.py"
Cohesion: 0.12
Nodes (18): ActionStatus, _action(), ActionOutcome, _empty_counts(), _FtsDrift, _is_unknown_title(), _normalized(), Connection (+10 more)

### Community 32 - "PromptStudioFlow"
Cohesion: 0.09
Nodes (20): PromptStudioFlow, GUI-independent state for Prompt Studio's sequential workflow., Discard all step content and approvals and return to the first step., StepState, StepStatus, parametrize, test_approving_a_step_records_content_and_advances_current_step(), test_changing_a_future_step_cannot_skip_the_current_step() (+12 more)

### Community 33 - "Result"
Cohesion: 0.11
Nodes (13): TelegramNotificationAdapter, KnowledgeService, Any, Result, KnowledgeRepository, ABC, Any, Project (+5 more)

### Community 34 - "main.py"
Cohesion: 0.09
Nodes (30): check_system_status(), clean_filename(), list_downloaded_files(), list_report_files(), main(), Lọc ký tự đặc biệt để tạo tên file an toàn, Liệt kê danh sách các file đã tải xuống để người dùng chọn nhanh, Liệt kê danh sách các báo cáo phân tích đã lưu (+22 more)

### Community 35 - "KnowledgeLifecycle"
Cohesion: 0.11
Nodes (12): KnowledgeLifecycle, LifecycleActor, LifecycleCommand, LifecycleResult, _LifecycleStore, Any, Protocol, _LifecycleBatchRejected (+4 more)

### Community 36 - "AffiliateContentService"
Cohesion: 0.15
Nodes (23): AffiliateContentService, ContentValidationError, Any, FakeContentGateway, parametrize, test_claim_evidence_is_canonicalized_and_unknown_urls_are_rejected(), test_content_service_rejects_duplicate_or_high_overlap_content(), test_content_service_rejects_invalid_duration_or_storyboard() (+15 more)

### Community 37 - "test_main_navigation_config.py"
Cohesion: 0.07
Nodes (16): destination_after_project_creation(), format_system_check_report(), Keep project creation contextual; Prompt Studio returns to its input step., Build the single visible report shown by the topbar system-check action., Run all checks and surface one aggregate result after completion., Verifies if FFmpeg is configured or available in system PATH., Checks if the yt-dlp library can import and run., Performs a silent check on startup. (+8 more)

### Community 38 - "ModelRequest"
Cohesion: 0.13
Nodes (20): NineRouterGateway, Message, MessageRole, ModelRequest, ModelResponse, ModelTier, Any, Enum (+12 more)

### Community 39 - "AffiliateAnalysis"
Cohesion: 0.13
Nodes (23): _content_hash(), SQLite adapter for ``AffiliateAnalysisRepository``., _row_to_analysis(), SQLiteAffiliateAnalysisRepository, AffiliateAnalysisRepositoryPort, AffiliateAnalysisValidationError, AnalysisGatewayPort, _build_analysis() (+15 more)

### Community 40 - "web/package.json"
Cohesion: 0.06
Nodes (34): dependencies, react-router-dom, @tanstack/react-query, react-router-dom, @tanstack/react-query, @playwright/test, react, react-dom (+26 more)

### Community 41 - "apply_schema_v2"
Cohesion: 0.09
Nodes (16): Proper migration: apply schema_v4 + schema_v5 from hermes codebase. Idempotent:…, apply_schema_v2(), Connection, apply_schema_v4(), _ensure_column(), Connection, apply_schema_v5(), _ensure_column() (+8 more)

### Community 42 - "AgentJobManager"
Cohesion: 0.12
Nodes (11): AgentJobManager, Move job from inbox to processing., Complete job and save result into outbox as {job_id}.done.json., File-based job queue for external AI workers such as Antigravity or Codex., Requeue legacy jobs left in processing after a worker restart., Requeue one failed legacy job after checking its Telegram owner., Cancel a queued job. Running jobs require cooperative cancellation., Return (found, allowed) for a job before exposing its artifacts. (+3 more)

### Community 43 - "ToolRegistry"
Cohesion: 0.11
Nodes (19): normalize_tool_name(), Path, Hermes tool scaffold and export helpers., Create and package local Hermes tools., ToolExporter, is_kebab_name(), Path, Hermes tool registry. Loads manifest-first tool definitions so Hermes can list,… (+11 more)

### Community 44 - "TikTokPublicReferenceAdapter"
Cohesion: 0.11
Nodes (25): TikTok metadata adapters., _default_get_json(), InvalidTikTokReferenceError, _normalize_url(), _OneRedirectHandler, Any, RuntimeError, ValueError (+17 more)

### Community 45 - "DataHealth"
Cohesion: 0.19
Nodes (3): DataHealth, Read-only knowledge audit and deterministic transactional repair., DataHealthTests

### Community 46 - "compilerOptions"
Cohesion: 0.06
Nodes (32): DOM, DOM.Iterable, ES2020, src, compilerOptions, allowImportingTsExtensions, allowSyntheticDefaultImports, esModuleInterop (+24 more)

### Community 47 - "telegram_review_watcher.py"
Cohesion: 0.11
Nodes (29): analyze_target_context(), build_change_request(), build_review_markdown(), build_telegram_caption(), classify_report(), extract_target_hint(), get_bot_token(), get_required_env() (+21 more)

### Community 48 - "server/app.py"
Cohesion: 0.10
Nodes (25): health_check(), get, get_job_service(), get_project_repository(), get_prompt_studio_service(), get_job(), JobResponse, JobSubmitRequest (+17 more)

### Community 49 - "ProjectManager"
Cohesion: 0.05
Nodes (36): clean_filename(), create_directory_structure(), list_downloaded_materials(), list_generated_clips(), Filters special characters to make a safe filename for disk storage., Creates the standard directory structure for a project., Lists all video materials (.mp4, .mkv, .avi, etc.) in the project's materials…, Lists all video clips (.mp4, etc.) in the project's clips folder. (+28 more)

### Community 50 - "._reload"
Cohesion: 0.09
Nodes (17): _now_iso(), Reload từ disk (dùng khi nhiều process cùng chạy)., Return approved entries matching the shared duplicate policy., Thêm entry mới vào unified index với status='pending'. Nếu trùng URL và…, Tìm entry theo slug hoặc id., Return the stored detail payload for an entry, or an empty dict., Read detail without reloading the index during a write operation., Flag a pending placeholder lesson for an explicit re-analysis. (+9 more)

### Community 52 - "test_affiliate_analysis.py"
Cohesion: 0.15
Nodes (26): AffiliateAnalysisGateway, Any, Generate spec-compliant ``AffiliateAnalysis`` payloads., Validate the LLM output and normalize to the canonical shape. Raises…, validate_analysis_payload(), AffiliateAnalysisService, _good_payload(), _make_db() (+18 more)

### Community 53 - "PatchExecutor"
Cohesion: 0.13
Nodes (18): extract_patch_paths(), normalize_diff_path(), PatchExecutionResult, PatchExecutor, CompletedProcess, Path, Safe unified-diff patch executor for Hermes. Default usage should be check-…, Validate and optionally apply unified diffs inside a repo. (+10 more)

### Community 54 - "test_v2_modules.py"
Cohesion: 0.10
Nodes (28): build_profile(), extract_style_profile(), get_profile_summary(), inject_style_into_prompt(), load_knowledge_base(), load_profile(), core/style_profiler.py — Smart Learning Loop / Style Profiler Analyzes the…, Build (or load cached) style profile from the knowledge base. Args:… (+20 more)

### Community 56 - "UnifiedKnowledgeStore"
Cohesion: 0.10
Nodes (18): _ensure_dirs(), Lấy danh sách entries, có thể filter theo status và/hoặc category., Trả về các entries đã được approve (đủ điều kiện inject vào script generation)., Return a small approved-only reference block relevant to a query., Trả về các entries đang chờ duyệt., Trả về context string để inject vào AI prompt khi generate script. Chỉ dùng…, SINGLE SOURCE OF TRUTH cho toàn bộ kiến thức học được của Hermes. Unified Index…, UnifiedKnowledgeStore (+10 more)

### Community 57 - "PublicWebUrlPolicy"
Cohesion: 0.14
Nodes (17): AffiliateWebReferenceService, Exception, Raised when web reference input is invalid or not allowed for product/owner., WebReferenceRejected, PublicWebUrlPolicy, FakeResearchRepository, FakeWebAcquisitionService, FakeWebDocRepository (+9 more)

### Community 58 - "analyze_video"
Cohesion: 0.13
Nodes (20): main(), Focused checks for image-carousel analysis input validation., run_missing_vision_configuration_check(), run_tests(), MediaAnalysisContractTests, analyze_images(), analyze_video(), generate_offline_prompt() (+12 more)

### Community 59 - "test_affiliate_research_acceptance.py"
Cohesion: 0.13
Nodes (20): AffiliateResearchSettings, _boolean(), _bounded_integer(), _import_directory(), load_affiliate_research_settings(), _product_research_output_dir(), Path, Non-secret runtime settings for the affiliate research workflow. (+12 more)

### Community 60 - "WebAcquisitionService"
Cohesion: 0.18
Nodes (21): WebAcquisitionService, load_web_research_settings_from_env(), Exception, Raised when a batch of web reference URLs violates limits., validate_web_reference_batch(), WebBatchRejected, WebResearchSettings, complete_document() (+13 more)

### Community 61 - "reviewer_app.py"
Cohesion: 0.16
Nodes (27): bot_api_url(), bot_file_url(), build_codex_wakeup_prompt(), build_idle_audit_wakeup_prompt(), classify_report(), document_name(), download_document(), ensure_dirs() (+19 more)

### Community 62 - "telegram_bot.py"
Cohesion: 0.13
Nodes (24): Tests for the shared Telegram learning attachment normalizer., run_tests(), approve_source_command(), build_video_job(), configured_storage_backend(), create_learning_intake_note(), datetime_now_slug(), enqueue_learning_job() (+16 more)

### Community 63 - "HermesAssistantRuntime"
Cohesion: 0.14
Nodes (17): action_for_module(), AssistantPlan, AssistantTask, escape_for_cmd(), HermesAssistantRuntime, normalize_text(), Path, Hermes Assistant runtime foundation. This module is intentionally small and… (+9 more)

### Community 64 - "tiktok_media_resolver.py"
Cohesion: 0.15
Nodes (25): _call_crawler(), check_crawler_health(), _crawler_base_url(), _download_image(), _download_photo_carousel(), _extract_embedded_post_data(), _fetch_impersonated_page(), _fetch_public_metadata() (+17 more)

### Community 65 - "get_store"
Cohesion: 0.11
Nodes (15): approve_entry(), get_store(), get_style_context(), core/knowledge_store.py — Unified Knowledge Store (Single Source of Truth) Thay…, Return the configured knowledge backend., Convenience: lấy context string để inject vào script generation. Trả về "" nếu…, Convenience: approve một entry và rebuild style profile., build_duplicate_warning() (+7 more)

### Community 66 - "IdeaEngineTab"
Cohesion: 0.10
Nodes (17): generate_ideas(), load_ideas(), load_selected_angles(), Lưu ideas.json vào thư mục project., Tải ideas.json từ thư mục project. Trả về dict hoặc None., Lưu selected_angles.json — danh sách angle user đã chọn., Tải selected_angles.json từ thư mục project., Gọi Gemini API để sinh nhiều ý tưởng angle video TikTok từ thông tin sản phẩm.… (+9 more)

### Community 67 - "crawler/__init__.py"
Cohesion: 0.13
Nodes (12): Validation for the small set of remote learning sources Hermes supports., Return an error message, or None when a source is acceptable., Reject local/private network targets before any learning-source fetch., validate_learning_source(), validate_public_url(), FakeResponse, URLIngestionTests, get_installed_browsers() (+4 more)

### Community 68 - "db.py"
Cohesion: 0.11
Nodes (12): Fix affiliate_products schema: drop wrong test table, recreate with correct…, SQLite schema V7: additive persistence for ``AffiliateAnalysis``. Mirrors the…, _default_data_dir(), HermesPaths, load_settings(), Path, Load application settings from environment variables., _ClosingConnection (+4 more)

### Community 69 - "job_watcher.py"
Cohesion: 0.19
Nodes (9): Start continuous watching loop., Convert a validated model response into evidence-backed atomic lessons., start_watching(), EvidenceItem, LearningResult, LearningService, LessonCandidate, SourceBundle (+1 more)

### Community 70 - "llm_gateway.py"
Cohesion: 0.16
Nodes (24): complete(), _configured_base_url(), _env_bool(), _headers(), health_check(), _legacy_complete(), _legacy_task_type(), list_models() (+16 more)

### Community 71 - "ShopeePlaywrightScraper"
Cohesion: 0.12
Nodes (15): Any, Alternative: Browser-based Shopee scraper using Playwright. This approach…, Extract product cards from current page., Parse a single product card element., Post-extraction filter., Parse price string like '₫450.000' or '450k' to VND., Parse sold text like 'Đã bán 1,2k' or 'Sold 500'., Configuration for browser-based scraper. (+7 more)

### Community 72 - "test_telegram_ingestion.py"
Cohesion: 0.20
Nodes (14): FakeTelegramDocument, FakeTelegramVideo, TelegramIngestionAdapter, IngestionService, NotificationPort, Any, IngestionRequest, adapter() (+6 more)

### Community 73 - "reply_html"
Cohesion: 0.14
Nodes (22): cancel_command(), help_command(), DEFAULT_TYPE, Update, apps/telegram/handlers/admin.py — Admin & System Control Handlers. Handles…, Handle /start command., Handle /help command., Handle /status command: Show memory usage & system status. (+14 more)

### Community 74 - "AIRouter"
Cohesion: 0.13
Nodes (10): AIRouter, ProviderState, Exception, RateLimitError, core/ai_router.py — Multi-Provider AI Router (9router-style) Supports: Google…, Track rate limit state for a single provider., Multi-provider AI router with automatic fallback and rate limit tracking.…, Return ordered list of available providers for a task. (+2 more)

### Community 75 - "ClipLibrary"
Cohesion: 0.12
Nodes (11): ClipLibrary, Cập nhật metadata của clip theo clip_id., Xóa clip khỏi library (không xóa file thực)., Tìm kiếm clips theo nhiều tiêu chí., Quản lý kho phôi (Clip Library) của từng project. Library file:…, Thống kê nhanh về library., Trả về toàn bộ danh sách clips., Lọc clips theo status. (+3 more)

### Community 76 - "test_reliability_integration.py"
Cohesion: 0.17
Nodes (18): cleanup_raw_response_logs(), _now(), datetime, Path, Delete old Gemini raw response logs and cap total retained raw-log size., Write raw Gemini output with timestamped retention, plus a latest pointer file., Send an operational alert to the configured Telegram review/admin chat., record_suspicious_instruction() (+10 more)

### Community 77 - ".success"
Cohesion: 0.14
Nodes (9): Any, Any, Project, T, InMemoryKnowledgeRepository, test_approved_knowledge_is_searchable_but_rejected_proposal_is_not(), test_failure_result_keeps_a_stable_error_code(), test_failure_result_must_have_error_code() (+1 more)

### Community 78 - "affiliate_analysis_runner.py"
Cohesion: 0.12
Nodes (12): LLM gateway for the spec-compliant ``AffiliateAnalysis`` schema. Talks to…, CapabilityMismatchError, HermesLLMError, Any, RuntimeError, StructuredOutputError, build_service(), main() (+4 more)

### Community 79 - "prompt_filter.py"
Cohesion: 0.17
Nodes (22): export_json(), export_markdown(), filter_by_category(), filter_by_keywords(), filter_by_type(), group_by_type(), load_templates(), main() (+14 more)

### Community 80 - "web_studio.py"
Cohesion: 0.13
Nodes (21): main(), apps/web_studio/app.py — Web Studio Application Entrypoint. Delegates to the…, Start the Web Studio server., get_local_ip(), handle_api_create_project(), handle_api_cut_clip(), handle_api_generate_all(), handle_api_generate_audio() (+13 more)

### Community 81 - "default_chat_handler"
Cohesion: 0.15
Nodes (17): extract_repository_query(), format_repository_context(), is_repository_search_request(), Any, Small, bounded GitHub repository search tool for Hermes chat., Search only GitHub's repository endpoint; never fetch arbitrary URLs., Format API data as untrusted reference material for the LLM., search_repositories() (+9 more)

### Community 83 - "WindowsRuntimeProcessTests"
Cohesion: 0.17
Nodes (4): MaintenanceCliTests, _PowerShellResult, Path, WindowsRuntimeProcessTests

### Community 84 - "app.tsx"
Cohesion: 0.13
Nodes (15): root, Layout(), navItems, AIAnalysisPage(), AnalysisMode, modes, tiers, Knowledge (+7 more)

### Community 85 - "task_queue.py"
Cohesion: 0.20
Nodes (16): create_manifest(), new_job_id(), now_iso(), Create a normalized Hermes Job Manifest dict., save_manifest(), set_manifest_status(), build_input_context(), generate_master_prompt() (+8 more)

### Community 86 - "AffiliateProduct"
Cohesion: 0.19
Nodes (10): AffiliateProduct, EligibilityDecision, _normalize_category(), ProductPolicy, ProductScorer, product(), test_keyboard_price_score_normalizes_category_at_price_boundaries(), test_missing_history_lowers_confidence_without_inventing_growth() (+2 more)

### Community 87 - "SimpleNamespace"
Cohesion: 0.17
Nodes (3): SimpleNamespace, TelegramMemoryTests, TelegramTextLearningTests

### Community 88 - "ConversationMemory"
Cohesion: 0.15
Nodes (8): ConversationMemory, get_memory(), Path, Small bounded per-user conversation memory for Telegram chat., Compatibility adapter backed by the Hermes SQLite memory repository., SQLiteConversationMemory, Tests for bounded, per-user conversation memory., run_tests()

### Community 89 - "fetch_transcript"
Cohesion: 0.16
Nodes (20): _audio_download_command(), _fetch_metadata(), fetch_transcript(), _get_transcriber(), is_blocked_error(), parse_vtt_to_text(), Path, RuntimeError (+12 more)

### Community 90 - "ReferenceMetadata"
Cohesion: 0.18
Nodes (10): ValueError, Any, Map observable reference semantics to a controlled pattern vocabulary., ReferencePattern, ReferencePatternAbstractor, ReferenceMetadata, _reference(), test_abstractor_derives_semantic_structure_without_copying_source_wording() (+2 more)

### Community 91 - "JobDedup"
Cohesion: 0.19
Nodes (7): JobDedup, datetime, Detect and prevent duplicate jobs based on source + mode hash. Persisted to…, SHA256(chat_id + source_value + mode)[:16]., Return job info if it exists and has not expired. Return None when no entry…, Register a new job in the dedup store., Single-process atomic duplicate check + job creation + registration.

### Community 92 - "_FakeResponse"
Cohesion: 0.13
Nodes (3): _FakeResponse, TikTokCrawlerHealthTests, TikTokImageDownloadTests

### Community 93 - "template.sh"
Cohesion: 0.22
Nodes (16): ask(), ask_secret(), banner(), _clear(), finish(), note(), open_url(), pause() (+8 more)

### Community 94 - "reviewer_app_upgrade.py"
Cohesion: 0.22
Nodes (18): chat(), Convenience function — calls the global router., build_ai_review(), classify_report(), ensure_dirs(), get_required_env(), is_report_payload(), load_env() (+10 more)

### Community 95 - "StoryboardTab"
Cohesion: 0.11
Nodes (5): Saves the structured storyboard data into output_dir. Files written:…, save_storyboard_outputs(), Xuất prompts từ storyboard đã tạo (3 formats: .md / .txt / .json)., Xử lý sau khi xuất prompts xong., StoryboardTab

### Community 96 - "VerificationRunner"
Cohesion: 0.19
Nodes (11): is_allowed_command(), Path, Verification runner for Hermes coding-agent workflows. Runs focused,…, Run allowlisted verification commands and write reports., VerificationCommandResult, VerificationRun, VerificationRunner, main() (+3 more)

### Community 97 - "generate_phone_stand_review_batch.py"
Cohesion: 0.26
Nodes (18): blur_number_badge(), clean_outputs(), contain_resize(), cover_resize(), crop_phone_screenshot(), full_scene(), main(), make_segment() (+10 more)

### Community 98 - "prompt_library.py"
Cohesion: 0.22
Nodes (16): ensure_prompt_library(), extract_variables(), find_prompt_template(), list_prompt_templates(), load_prompt_template(), parse_prompt_template(), PromptTemplateError, Exception (+8 more)

### Community 99 - "StaticWebDocumentFetcher"
Cohesion: 0.23
Nodes (10): StaticWebDocumentFetcher, Session, FakeRedirectSession, FakeResponse, FakeSession, public_policy(), public_request(), test_static_fetcher_rejects_unsupported_content_type() (+2 more)

### Community 100 - "knowledge_base.py"
Cohesion: 0.16
Nodes (15): delete_learned_item(), ensure_kb_dirs(), get_learned_detail(), learn_from_url(), load_learned_list(), Xóa một video khỏi kho tri thức, Tải video/audio từ URL, gọi Gemini phân tích rút ra cấu trúc/phong cách kịch…, Đảm bảo các thư mục của Kho tri thức tồn tại (+7 more)

### Community 101 - "TaskQueue"
Cohesion: 0.24
Nodes (3): load_manifest(), Manifest-first file queue: jobs/{pending,running,done,failed}/job_id., TaskQueue

### Community 102 - "PendingStore"
Cohesion: 0.24
Nodes (4): PendingStore, datetime, Remove entries older than ttl_hours and return the number removed., Persist pending video links and files to disk as JSON. Thread-safe for asyncio…

### Community 103 - "test_affiliate_research_repository.py"
Cohesion: 0.25
Nodes (16): database(), package(), product(), fixture, parametrize, reference(), repository(), test_child_records_reject_cross_owner_parents_without_partial_writes() (+8 more)

### Community 104 - ".load_project_details"
Cohesion: 0.13
Nodes (4): Scans folder and reloads the project combobox dropdown., Triggered when user selects a different project from the dropdown list., Populates UI elements in all tabs with project configurations from metadata., Saves current input product details to create or update a project folder.

### Community 106 - "project.py"
Cohesion: 0.15
Nodes (15): Asset, Project, ProjectStatus, Enum, str, hermes/domain/project.py — Domain models for Projects, Workflows & Assets.…, Project lifecycle status., Status of a single step within a workflow. (+7 more)

### Community 107 - "manifest.json"
Cohesion: 0.13
Nodes (13): gemini, ollama, openrouter, report.md, description, entrypoint, inputs, name (+5 more)

### Community 108 - "migrate_legacy_knowledge"
Cohesion: 0.22
Nodes (7): migrate_legacy_knowledge(), MigrationReport, Path, _read_detail(), _default_owner(), main(), KnowledgeMigrationTests

### Community 109 - "BaseWorker"
Cohesion: 0.24
Nodes (7): AiStudioWorker, AntigravityWorker, BaseWorker, ManualWorkerResult, Base contract for future automatic Hermes workers., CodexWorker, HtmlVideoWorker

### Community 110 - "handlers/knowledge.py"
Cohesion: 0.24
Nodes (11): approve_command(), knowledge_command(), DEFAULT_TYPE, Update, apps/telegram/handlers/knowledge.py — Knowledge & Learning Command Handlers.…, Handle /knowledge command: List stored knowledge entries., Handle /approve <id> command., Handle /reject <id> command. (+3 more)

### Community 111 - "ArtifactStore"
Cohesion: 0.26
Nodes (3): ArtifactStore, _now(), File-backed artifact metadata helper for a single manifest job.

### Community 112 - "telegram_auth.py"
Cohesion: 0.25
Nodes (10): get_allowed_user_ids(), is_authorized_update(), is_authorized_user_id(), parse_user_ids(), Small Telegram authorization helper for the personal Hermes bot., Parse comma/space/semicolon separated Telegram numeric IDs., Return the configured allowlist, failing closed when it is absent., Focused regression checks for Telegram auth and pending lesson ownership. (+2 more)

### Community 113 - "SQLiteProjectRepository"
Cohesion: 0.22
Nodes (9): Path, SQLiteProjectRepository, in_memory_db(), project_repository(), fixture, test_project_repository_archives_project(), test_project_repository_initializes_db_schema(), test_project_repository_lists_active_projects() (+1 more)

### Community 114 - "recover_pending_knowledge.py"
Cohesion: 0.29
Nodes (12): build_needs_source_entry(), build_recovered_entry(), _is_placeholder(), main(), Path, Repair old pending lessons that were created from structured-output fallbacks., _read_json(), repair_pending_entries() (+4 more)

### Community 115 - "tts_engine.py"
Cohesion: 0.20
Nodes (13): _edge_tts_async(), tools/tts_engine.py — Text-to-Speech Engine Supports: - Edge TTS (Microsoft,…, Synthesize speech using ElevenLabs API (premium quality). Args: text: Text to…, Unified TTS synthesis function. Args: text: Text to speak voice: Voice…, Synthesize TTS and save directly into project's audio/ folder as voice.mp3.…, Async Edge TTS synthesis., Convert speed float (0.7–1.5) to Edge TTS rate string (+25%, -15%, etc.), Synthesize speech using Microsoft Edge TTS (FREE, no API key). Args: text: Text… (+5 more)

### Community 116 - "utils.py"
Cohesion: 0.22
Nodes (11): edit_html_message(), apps/telegram/utils.py — Shared Telegram utility functions. Extracted from the…, Send a standalone message (not a reply) as controlled HTML., Edit an existing inline-keyboard message with controlled HTML., Cắt nhỏ tin nhắn dài hơn giới hạn của Telegram (4096 ký tự), Escape untrusted text and render a small Telegram-safe Markdown subset., Produce a readable fallback after Telegram rejects an HTML response., render_telegram_html() (+3 more)

### Community 118 - "AgentJobsTab"
Cohesion: 0.26
Nodes (3): AgentJobsTab, Periodically refresh jobs UI in background every 3 seconds., Display content of selected output artifact file in viewer textbox.

### Community 119 - "MemoryRepository"
Cohesion: 0.17
Nodes (5): MemoryRepository, product(), fixture, reference(), repository()

### Community 120 - "domain/knowledge.py"
Cohesion: 0.18
Nodes (11): ApprovalEvent, KnowledgeDetail, KnowledgeEntry, LessonStatus, Enum, str, hermes/domain/knowledge.py — Domain models for the Knowledge Store. Defines the…, Lifecycle status of a knowledge entry. (+3 more)

### Community 122 - "projects.py"
Cohesion: 0.29
Nodes (10): delete, archive_project(), create_project(), get_project(), list_projects(), ProjectCreateRequest, ProjectResponse, BaseModel (+2 more)

### Community 123 - ".lib_refresh_cards"
Cohesion: 0.20
Nodes (5): Tab Kho Ph├┤i ΓÇö quß║ún l├╜ clip library cß╗ºa project., Khß╗ƒi tß║ío ClipLibrary cho project ─æang active., Import nhiß╗üu file video v├áo Kho Ph├┤i., Refresh danh s├ích clip cards theo filter hiß╗çn tß║íi., Cß║¡p nhß║¡t status cho clip.

### Community 124 - "RetrievalService"
Cohesion: 0.22
Nodes (6): Any, hermes/application/retrieval_service.py — Knowledge Retrieval & RAG Service.…, Service dedicated to searching, ranking, and preparing knowledge context for…, Search knowledge entries by query, optionally filtering by category and status., Build an approved reference block to inject into LLM system prompts., RetrievalService

### Community 125 - "handle_callback"
Cohesion: 0.22
Nodes (11): _affiliate_review_repository_factory(), edit_html_message(), handle_callback(), Escape untrusted text and render a small Telegram-safe Markdown subset., Produce a readable fallback after Telegram rejects an HTML response., Send a bot-originated Telegram message using the same safe HTML policy., Edit a callback message with the same HTML safety and fallback policy., Construct persistence only when an affiliate Telegram action is requested. (+3 more)

### Community 126 - "bgm_manager.py"
Cohesion: 0.22
Nodes (10): detect_tone_from_script(), download_bgm(), ensure_bgm_dirs(), mix_bgm_with_video(), pick_bgm(), tools/bgm_manager.py — Auto Background Music Manager Automatically selects and…, Mix background music into video using FFmpeg. BGM volume is ducked to…, Simple heuristic tone detection from script text. Returns: 'energetic',… (+2 more)

### Community 127 - "affiliate_worker.py"
Cohesion: 0.29
Nodes (6): main(), process_one_job(), Affiliate worker --once mode. Processes pending affiliate_jobs, simulates real…, run_once(), Optional Telegram notifier for affiliate worker. Reads token + chat_id from…, TelegramNotifier

### Community 128 - "create_corrected_phone_stand_storyboard.py"
Cohesion: 0.40
Nodes (9): FreeTypeFont, cover(), crop_phone_screenshot(), draw_panel(), load_font(), main(), open_rgb(), Image (+1 more)

### Community 129 - "._render_idea_cards"
Cohesion: 0.20
Nodes (5): Xß╗¡ l├╜ kß║┐t quß║ú tß╗½ AI v├á render cards., Render idea cards v├áo scrollable frame., Update the selected count label., Chß╗ìn top N angles theo total_score., Bß╗Å chß╗ìn tß║Ñt cß║ú.

### Community 130 - ".script_refresh_learned_dropdown"
Cohesion: 0.24
Nodes (4): Tß║úi danh s├ích c├íc video ─æ├ú hß╗ìc v├á hiß╗ân thß╗ï v├áo combobox kß╗ïch…, Xß╗¡ l├╜ kß║┐t quß║ú trß║ú vß╗ü sau khi ho├án th├ánh tiß║┐n tr├¼nh hß╗ìc., Cß║¡p nhß║¡t giao diß╗çn danh s├ích b├ái hß╗ìc ─æ├ú l╞░u., X├│a b├ái hß╗ìc khß╗Åi kho dß╗» liß╗çu.

### Community 131 - "FFmpegCapability"
Cohesion: 0.36
Nodes (3): DesktopRuntime, Any, FFmpegCapability

### Community 132 - "create_recreated_tiktok_pngs.py"
Cohesion: 0.44
Nodes (9): cover_resize(), create_image(), crop_rel(), grabcut_cutout(), main(), make_background(), paste_with_shadow(), Image (+1 more)

### Community 133 - "generate_phone_stand_front_lifestyle_video.py"
Cohesion: 0.44
Nodes (9): concat_segments(), cover(), main(), make_scene_image(), make_segment(), Image, Path, run() (+1 more)

### Community 134 - "test_learning_recovery.py"
Cohesion: 0.38
Nodes (9): Regression checks for structured-learning recovery behavior., run_normalization_check(), run_raw_recovery_payload_check(), run_recoverability_check(), run_store_reanalysis_state_check(), run_tests(), run_worker_placeholder_check(), run_worker_reanalysis_update_check() (+1 more)

### Community 135 - "knowledge_command"
Cohesion: 0.22
Nodes (10): _escape_markdown_title(), format_knowledge_listing(), format_knowledge_listing_html(), knowledge_command(), _ordered_knowledge_entries(), Use the same category ordering for display and numeric pending actions., Format a compact, topic-grouped Telegram knowledge catalogue., Format a compact, escaped HTML knowledge catalogue for Telegram. (+2 more)

### Community 136 - "match_assets_to_script"
Cohesion: 0.39
Nodes (7): match_assets_to_script(), Matches script visual keywords to local or remote assets., test_match_assets_to_script_invalid_file(), test_match_assets_to_script_invalid_json(), test_match_assets_to_script_missing_scene_id(), test_match_assets_to_script_root_list(), test_match_assets_to_script_success()

### Community 137 - "backfill"
Cohesion: 0.39
Nodes (6): backfill(), MigrationReport, Path, test_backfill_counts_knowledge_files(), test_backfill_handles_missing_legacy_root(), test_backfill_is_idempotent()

### Community 138 - "generate_phone_stand_storyboard_video.py"
Cohesion: 0.42
Nodes (8): contain_resize(), cover_resize(), draw_pill(), load_font(), main(), make_frame(), rounded_paste(), split_storyboard()

### Community 139 - "rebackground_phone_stand_video.py"
Cohesion: 0.53
Nodes (8): foreground_mask(), main(), make_background(), ndarray, Path, remove_pink_text(), render_samples(), render_video()

### Community 140 - "render_duck_foldable_commercial.py"
Cohesion: 0.44
Nodes (8): bbox_from_alpha(), camera_transform(), fit_cover(), main(), make_product_mask(), Image, ndarray, rotate_rgba()

### Community 141 - "process_inbox"
Cohesion: 0.42
Nodes (7): is_agent_enabled(), load_processed_ids(), main(), process_inbox(), save_processed_id(), main(), Entry point for the integrated 10‑minute job. It simply invokes the existing…

### Community 142 - "main"
Cohesion: 0.39
Nodes (8): compile_check(), find_py_files(), main(), Path, Run `python -m py_compile` on a file. Returns ``None`` if compilation succeeds,…, Search a file for common development markers. Returns a list of tuples:…, Recursively collect all .py files under the given root directory., scan_markers()

### Community 143 - "test_script_generator_knowledge_injection.py"
Cohesion: 0.28
Nodes (5): clean_test_env(), mock_post(), MockResponse, scripts/test_script_generator_knowledge_injection.py — Verify knowledge…, run_script_generator_tests()

### Community 144 - "._run_all_checks"
Cohesion: 0.25
Nodes (4): Run all system checks at once., Verifies if FFmpeg is configured or available in system PATH., Checks if the yt-dlp library can import and run., Actively checks if the Gemini API Key is working by hitting the endpoint.

### Community 146 - "affiliate_video_prompt_base.ts"
Cohesion: 0.29
Nodes (7): CreativeBrief, dataBlock(), GenerationProfile, JsonRecord, ProductTruthCard, PROMPTS, serializeData()

### Community 147 - "create_one"
Cohesion: 0.54
Nodes (7): cover_resize(), create_one(), main(), make_bg(), Image, Path, rounded_mask()

### Community 148 - "repair_knowledge_encoding.py"
Cohesion: 0.43
Nodes (7): main(), Path, _quality(), Repair common UTF-8/Latin-1 mojibake in the Drive knowledge store., repair_json(), repair_markdown(), repair_text()

### Community 150 - "resolve_route"
Cohesion: 0.38
Nodes (6): get_engine(), normalize_command(), Normalizes input text by matching Vietnamese/spaced command variations and…, Analyzes input message text and returns the corresponding route configuration…, Shortcut helper to get the engine target from message text., resolve_route()

### Community 153 - "clone_repo"
Cohesion: 0.48
Nodes (5): clone_repo(), clone_self(), Path, Clone the current repository to the target directory. Args: target_dir: Target…, Clone a git repository to the target directory. Args: repo_url: URL or local…

### Community 154 - "analyze_assembly.py"
Cohesion: 0.43
Nodes (5): analyze_videos_with_gemini(), get_gemini_api_key(), get_gemini_model(), Resizes image for API upload and returns base64 string., resize_and_encode_image()

### Community 155 - "generate_phone_stand_tiktok_large_scene.py"
Cohesion: 0.52
Nodes (6): cover_resize(), crop_wide_focus(), main(), make_frame(), rounded_paste(), split_storyboard()

### Community 156 - "prepare_one"
Cohesion: 0.48
Nodes (6): contain(), cover(), main(), prepare_one(), Image, Path

### Community 157 - "FakeResponse"
Cohesion: 0.33
Nodes (3): FakeResponse, Mocked tests for the Hermes text LLM gateway., run_tests()

### Community 158 - "publish_recycled_video"
Cohesion: 0.48
Nodes (5): test_publish_recycled_video(), test_publish_recycled_video_malformed_json(), test_publish_recycled_video_missing_files(), publish_recycled_video(), Publishes the finalized video to the target platform.

### Community 160 - "migration.py"
Cohesion: 0.60
Nodes (4): migrate_legacy_knowledge(), MigrationReport, Path, _read_detail()

### Community 163 - "permissions"
Cohesion: 0.33
Nodes (6): output/**, permissions, filesystem_read, filesystem_write, network, shell

### Community 164 - "analyze_220247.py"
Cohesion: 0.53
Nodes (4): analyze_220247_assembly(), get_gemini_api_key(), get_gemini_model(), resize_and_encode_image()

### Community 165 - "analyze_detailed.py"
Cohesion: 0.53
Nodes (4): analyze_detailed_assembly(), get_gemini_api_key(), get_gemini_model(), resize_and_encode_image()

### Community 166 - "analyze_detailed_220124.py"
Cohesion: 0.53
Nodes (4): analyze_220124_assembly(), get_gemini_api_key(), get_gemini_model(), resize_and_encode_image()

### Community 167 - "generate_phone_stand_tiktok_fullscreen.py"
Cohesion: 0.60
Nodes (5): cover_resize(), main(), make_frame(), portrait_crop(), split_storyboard()

### Community 168 - "scripts/test_tiktok_media_resolver.py"
Cohesion: 0.60
Nodes (5): Path, Focused checks for the optional local TikTok media resolver., run_photo_download_check(), run_tests(), run_unavailable_crawler_check()

### Community 171 - "crawl_source"
Cohesion: 0.60
Nodes (3): crawl_source(), Orchestrates downloading, transcribing, and analyzing a source video., test_crawl_source()

### Community 173 - "patch_storyboard_with_exact_mechanism.py"
Cohesion: 0.70
Nodes (4): cover(), main(), paste_panel(), Image

### Community 174 - "test_learning_fallback.py"
Cohesion: 0.70
Nodes (4): FakeProcess, Focused tests for bounded learning-source fallback behavior., run_tests(), TikTokMediaResult

### Community 177 - "bot.py"
Cohesion: 0.50
Nodes (3): main(), apps/telegram/bot.py — Telegram Bot Application Entrypoint. This module serves…, Start the Telegram bot by delegating to the root-level module.

### Community 178 - "hitl-loop.template.sh"
Cohesion: 0.83
Nodes (3): capture(), hitl-loop.template.sh script, step()

### Community 179 - "get_router"
Cohesion: 0.50
Nodes (3): get_router(), Get or create the global AIRouter singleton., Update AI Router provider status dots in settings tab.

### Community 180 - "test_worker_json_and_transcript.py"
Cohesion: 0.67
Nodes (3): clean_test_env(), scripts/test_worker_json_and_transcript.py — Tests for robust JSON parsing,…, run_worker_tests()

### Community 181 - "test_prompt_studio_project_routing.py"
Cohesion: 0.83
Nodes (3): _called_methods(), test_project_selection_routes_through_prompt_studio_project_load(), test_successful_quick_project_creation_routes_through_project_load()

## Knowledge Gaps
- **71 isolated node(s):** `block-dangerous-git.sh script`, `ProductTruthCard`, `CreativeBrief`, `GenerationProfile`, `JsonRecord` (+66 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **31 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Database` connect `Database` to `MaintenanceRunner`, `RuntimeState`, `BackupTests`, `ProjectionResult`, `ProductResearchIntent`, `ProductCandidate`, `SQLiteAffiliateResearchRepository`, `WindowsHermesProcessController`, `ContentPackage`, `GoogleSheetsProjection`, `WebDocument`, `SQLiteKnowledgeStore`, `MemoryRepository`, `auto_crawler.py`, `data_health.py`, `migration.py`, `KnowledgeLifecycle`, `AffiliateAnalysis`, `apply_schema_v2`, `AgentJobManager`, `DataHealth`, `server/app.py`, `ProjectManager`, `test_affiliate_analysis.py`, `test_affiliate_research_acceptance.py`, `telegram_bot.py`, `db.py`, `job_watcher.py`, `affiliate_analysis_runner.py`, `web_studio.py`, `ConversationMemory`, `test_affiliate_research_repository.py`, `.owner`, `migrate_legacy_knowledge`, `SQLiteProjectRepository`, `handle_callback`?**
  _High betweenness centrality (0.240) - this node is a cross-community bridge._
- **Why does `AgentJobManager` connect `AgentJobManager` to `HermesTikTokVideoFactoryApp`, `app_staged.py`, `Database`, `TaskQueue`, `job_watcher.py`, `Update`, `test_reliability_integration.py`, `gui/app.py`, `JobWorker`, `ProjectManager`, `test_worker_json_and_transcript.py`, `.create_job`, `test_job_operations.py`, `test_telegram_learning_delivery.py`, `HermesTikTokVideoFactoryApp`, `telegram_bot.py`?**
  _High betweenness centrality (0.101) - this node is a cross-community bridge._
- **Why does `SQLiteKnowledgeStore` connect `SQLiteKnowledgeStore` to `migration.py`, `get_store`, `RuntimeState`, `Database`, `job_watcher.py`, `KnowledgeLifecycle`, `BackupTests`, `migrate_legacy_knowledge`, `DataHealth`, `KnowledgeLifecycleWiringTests`, `SimpleNamespace`, `MemoryRepository`, `data_health.py`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Are the 76 inferred relationships involving `Database` (e.g. with `AffiliateResearchJobError` and `AffiliateResearchJobHandler`) actually correct?**
  _`Database` has 76 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `HermesTikTokVideoFactoryApp` (e.g. with `AgentJobManager` and `ClipLibrary`) actually correct?**
  _`HermesTikTokVideoFactoryApp` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 48 inferred relationships involving `SQLiteAffiliateResearchRepository` (e.g. with `AffiliateResearchJobError` and `AffiliateResearchJobHandler`) actually correct?**
  _`SQLiteAffiliateResearchRepository` has 48 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `HermesTikTokVideoFactoryApp` (e.g. with `AgentJobManager` and `ClipLibrary`) actually correct?**
  _`HermesTikTokVideoFactoryApp` has 20 INFERRED edges - model-reasoned connections that need verification._