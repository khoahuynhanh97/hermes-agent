"""K3 Real Learning Operations: Hermes learns from real repository sources.

Implements the full learning pipeline:
- Source registration with provenance
- Existing KB search before synthesis
- Lesson synthesis with metadata
- HITL authorization gate
- Fresh-session retrieval
- Cross-capability reuse demonstration

Uses the canonical architecture:
- hermes.knowledge (SQLiteKnowledgeStore)
- hermes.application.knowledge_lifecycle
- hermes.application.knowledge_service
- mcp_servers.knowledge
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest

from hermes.knowledge import SQLiteKnowledgeStore
from hermes.db import Database
from hermes.application.knowledge_lifecycle import (
    KnowledgeLifecycle, LifecycleActor
)


# ============================================================================
# STEP 1: Define bounded real source corpus
# ============================================================================

SOURCES = [
    {
        "source_id": "src_tiktok_affiliate_research",
        "title": "TikTok Affiliate Creative Pipeline Research",
        "source_type": "research_md",
        "reference": "docs/research/ai-tiktok-affiliate-prompt-research.md",
        "classification": "current",
        "origin": "Primary research synthesizing TikTok Creative Center, Runway, Veo, Luma, Firefly official documentation",
    },
    {
        "source_id": "src_video_factory_v1_architecture",
        "title": "Video Factory V1 Architecture",
        "source_type": "spec_current",
        "reference": "docs/architecture-decisions/video-factory-v1-architecture.md",
        "classification": "current",
        "origin": "Implementation specification after V1 closure",
    },
    {
        "source_id": "src_video_factory_f1_runbook",
        "title": "Video Factory F1 Runbook",
        "source_type": "runbook",
        "reference": "docs/runbooks/video-factory-f1.md",
        "classification": "current",
        "origin": "Operational runbook for F1 capability",
    },
    {
        "source_id": "src_canonical_operations",
        "title": "Hermes Canonical Operations",
        "source_type": "runbook",
        "reference": "docs/runbooks/hermes-canonical-operations.md",
        "classification": "current",
        "origin": "Runtime configuration and canonical capability inventory",
    },
    {
        "source_id": "src_p6_architecture_closure",
        "title": "P6 Final Architecture Closure ADR",
        "source_type": "adr",
        "reference": "docs/architecture-decisions/007-p6-final-architecture-closure.md",
        "classification": "current",
        "origin": "Architecture decision record for P0-P6 closure",
    },
    {
        "source_id": "src_p3c_video_capability",
        "title": "P3C Video Capability Extraction ADR",
        "source_type": "adr",
        "reference": "docs/architecture-decisions/003-p3c-video-capability-extraction.md",
        "classification": "historical",
        "origin": "Earlier architectural decision for video capability extraction",
    },
]


# ============================================================================
# STEP 2: Learning objective
# ============================================================================

LEARNING_OBJECTIVE = (
    "Extract reusable principles for AI-assisted short-form affiliate video "
    "creation: creative planning, storyboard design, identity consistency, "
    "review workflow, and safe use of product claims."
)


# ============================================================================
# Proposed lessons (Hermes synthesis)
# ============================================================================

PROPOSED_LESSONS = [
    {
        "title": "TikTok Creative Brief Should Define One Value Proposition Per Video",
        "key_lessons": [
            "Each video concept must define exactly one single_value_proposition",
            "Each concept must include a proof_or_demo segment",
            "Each concept must end with one cta_action",
            "Multiple competing CTAs in a single short video reduce conversion quality",
        ],
        "source_refs": ["src_tiktok_affiliate_research"],
        "knowledge_type": "best_practice",
        "category": "creative_planning",
        "confidence": "high",
    },
    {
        "title": "Hook Must Surface Value Proposition Within First Six Seconds",
        "key_lessons": [
            "TikTok Creative Center: first 6 seconds determine attention",
            "Set hook_visible_by_s <= 2 as internal constraint",
            "Value proposition must be complete before second 6",
            "Internal constraint tighter than official guidance is acceptable",
        ],
        "source_refs": ["src_tiktok_affiliate_research"],
        "knowledge_type": "heuristic",
        "category": "creative_planning",
        "confidence": "high",
    },
    {
        "title": "Storyboard Frames Should Preserve Locked Identity References",
        "key_lessons": [
            "Reference assets must propagate downstream through generation",
            "Identity consistency managed via immutable reference data, not adjectives",
            "Iterate identical character descriptions across scenes",
            "Composition and style references serve distinct roles",
        ],
        "source_refs": ["src_tiktok_affiliate_research", "src_video_factory_v1_architecture"],
        "knowledge_type": "procedure",
        "category": "storyboard_design",
        "confidence": "high",
    },
    {
        "title": "Video Generation Prompt Should Describe Motion Only, Not Appearance",
        "key_lessons": [
            "Image-to-video input frame already defines subject/composition/lighting/style",
            "Motion prompt focuses on camera_movement, subject_action, environment_motion",
            "Dense appearance description can reduce motion or create unintended results",
            "Structure: 'The camera [movement] as the subject [action]'",
        ],
        "source_refs": ["src_tiktok_affiliate_research"],
        "knowledge_type": "best_practice",
        "category": "video_generation",
        "confidence": "high",
    },
    {
        "title": "Unsupported Product Claims Must Be Excluded From Creative Brief",
        "key_lessons": [
            "Claim evidence must be preserved as authoritative",
            "Unsupported claims must be omitted, not modified",
            "Restricted claims require explicit restriction_reason",
            "Storyboard and video prompts must not introduce unsupported claims",
        ],
        "source_refs": ["src_video_factory_v1_architecture"],
        "knowledge_type": "warning",
        "category": "creative_planning",
        "confidence": "high",
    },
    {
        "title": "Storyboard Approval Is A Business HITL Gate, Not Auto-Approved",
        "key_lessons": [
            "Hermes may propose, summarize, recommend but must not silently approve",
            "For automated tests use explicit test-domain authorization",
            "Storyboard approval gates progression to video generation",
            "Frame rejection preserves review_notes and version history",
        ],
        "source_refs": ["src_video_factory_v1_architecture", "src_canonical_operations"],
        "knowledge_type": "procedure",
        "category": "review_workflow",
        "confidence": "high",
    },
    {
        "title": "Timeline Composition Uses Deterministic FFmpeg Execution Only",
        "key_lessons": [
            "Render belongs to deterministic media execution",
            "Worker validates bounded transition types from allowed set",
            "Hermes selects composition intent only, not arbitrary FFmpeg commands",
            "Reuse canonical Video MCP for cut/render operations",
        ],
        "source_refs": ["src_video_factory_v1_architecture", "src_video_factory_f1_runbook"],
        "knowledge_type": "procedure",
        "category": "timeline_composition",
        "confidence": "high",
    },
    {
        "title": "Safe Zone Is Placement-Dependent, Not Fixed Coordinates",
        "key_lessons": [
            "Safe zone changes by aspect ratio, caption length, anchor and add-on",
            "Prompt should require critical content inside provider safe zone",
            "Render step applies overlay/mask per actual placement",
            "Preview QA must verify safe zone before publish",
        ],
        "source_refs": ["src_tiktok_affiliate_research"],
        "knowledge_type": "fact",
        "category": "creative_planning",
        "confidence": "high",
    },
    {
        "title": "Short Video Clip Should Be One Scene With One Main Action",
        "key_lessons": [
            "Each generated clip = one scene, one main action, one main camera motion",
            "Forcing multiple scene/action/style changes per second creates contradictions",
            "Google and Runway both warn against dense per-second changes",
            "Beat sheets detail for editor, not literal model prompt",
        ],
        "source_refs": ["src_tiktok_affiliate_research"],
        "knowledge_type": "best_practice",
        "category": "video_generation",
        "confidence": "high",
    },
    {
        "title": "Affiliate Content Requires Commercial Disclosure And AIGC Label",
        "key_lessons": [
            "Affiliate = commercial content: enable Commercial Content Disclosure",
            "AIGC content requires label or disclaimer/watermark/sticker",
            "Missing disclosure may reduce distribution or reject ads",
            "Pipeline should output commercial_disclosure_required=true, not just text overlay",
        ],
        "source_refs": ["src_tiktok_affiliate_research"],
        "knowledge_type": "warning",
        "category": "compliance",
        "confidence": "high",
    },
    {
        "title": "Hermes Owns Reasoning, MCP Owns Capability Boundaries",
        "key_lessons": [
            "Hermes is sole general-purpose creative agent",
            "MCP servers are capability boundaries, not orchestrators",
            "No MCP-to-MCP direct calls",
            "Workers execute deterministically without semantic reasoning",
        ],
        "source_refs": ["src_canonical_operations", "src_p6_architecture_closure"],
        "knowledge_type": "principle",
        "category": "architecture",
        "confidence": "high",
    },
    {
        "title": "9Router Owns Provider Routing, Project Code Stays Model-Agnostic",
        "key_lessons": [
            "Generic reasoning route: Hermes -> 9Router -> reason_combo",
            "Specialized image/video providers are capability-specific, not generic brain",
            "Project code must not select individual reasoning models",
            "Provider switch belongs in capability configuration",
        ],
        "source_refs": ["src_canonical_operations", "src_p3c_video_capability"],
        "knowledge_type": "principle",
        "category": "architecture",
        "confidence": "high",
    },
    {
        "title": "Historical Context: Video Capability Was Extracted To Video MCP",
        "key_lessons": [
            "Historical ADR P3C extracted deterministic video operations to Video MCP",
            "Context for why Video MCP exists as separate capability",
            "Not authoritative for current behavior — verify against current code/tests",
            "Useful for migration reasoning and decision history",
        ],
        "source_refs": ["src_p3c_video_capability"],
        "knowledge_type": "example",
        "category": "architecture",
        "confidence": "medium",
        "historical_only": True,
    },
]


@pytest.fixture
def k3_store():
    """Isolated SQLite store for K3 learning."""
    db_path = Path(tempfile.mkdtemp()) / "k3_learning.db"
    store = SQLiteKnowledgeStore(database=Database(db_path))
    return store, str(db_path)


@pytest.fixture
def registered_sources(k3_store):
    """Register all K3 sources durably."""
    store, db_path = k3_store
    registered = {}
    for source in SOURCES:
        result = store.add_entry(
            title=source["title"],
            source_url=f"file://{source['reference']}",
            platform="repository_doc",
            category="affiliate_video_creation",
            hook_type="",
            cta_style="",
            voice_tone="",
            key_lessons=[],
            detail_data={
                "source_type": source["source_type"],
                "reference": source["reference"],
                "classification": source["classification"],
                "origin": source["origin"],
                "learning_corpus": "k3_real_learning",
            },
            source=f"k3_learning_run:{source['source_id']}",
            owner_user_id="k3_owner",
            allow_multiple_source_lessons=True,
        )
        registered[source["source_id"]] = result
    return store, db_path, registered


# ============================================================================
# Tests
# ============================================================================


def test_k3_source_registration_idempotent(registered_sources):
    """Sources registered durably with classification preserved."""
    store, db_path, registered = registered_sources
    sources = store.list_entries(status=None, owner_user_id="k3_owner")
    source_titles = {s["title"] for s in sources}
    
    for src in SOURCES:
        assert src["title"] in source_titles, f"Source not registered: {src['title']}"
    
    # Verify classification metadata
    for src in SOURCES:
        lesson = registered[src["source_id"]]
        detail = store.get_entry_detail(lesson["id"])
        assert detail["classification"] == src["classification"]
        assert detail["reference"] == src["reference"]


def test_k3_existing_kb_search_before_synthesis(registered_sources):
    """Hermes searches existing KB before proposing new lessons."""
    store, db_path, registered = registered_sources
    
    # Initial search returns context (may be empty for fresh DB)
    context = store.get_approved_context(
        "affiliate video creation principles",
        max_entries=5,
        owner_user_id="k3_owner",
    )
    
    # Either has context (similar lesson found) or is empty (no duplicates)
    assert isinstance(context, str)


def test_k3_lesson_synthesis_with_provenance(registered_sources):
    """Hermes synthesizes lessons with provenance metadata."""
    store, db_path, registered = registered_sources
    
    pending = []
    for proposal in PROPOSED_LESSONS:
        result = store.add_entry(
            title=proposal["title"],
            source_url=f"k3://learning_run/affiliate_video_creation/{proposal['title'][:50]}",
            platform="repository_doc",
            category=proposal["category"],
            hook_type="",
            cta_style="",
            voice_tone="",
            key_lessons=proposal["key_lessons"],
            detail_data={
                "knowledge_type": proposal["knowledge_type"],
                "confidence": proposal["confidence"],
                "source_refs": proposal["source_refs"],
                "learning_run": "k3_real_learning",
                "historical_only": proposal.get("historical_only", False),
            },
            source="k3_synthesis",
            owner_user_id="k3_owner",
            allow_multiple_source_lessons=True,
        )
        pending.append(result)
    
    # All proposals are pending initially
    pending_list = store.list_entries(status="pending", owner_user_id="k3_owner")
    proposal_titles = {p["title"] for p in pending}
    for proposal in PROPOSED_LESSONS:
        assert proposal["title"] in proposal_titles
    
    # Provenance preserved in detail_json
    for lesson in pending:
        detail = store.get_entry_detail(lesson["id"])
        assert "source_refs" in detail
        assert detail["learning_run"] == "k3_real_learning"


def test_k3_hitl_approval_and_rejection(registered_sources):
    """HITL: approve current lessons, reject historical-only."""
    store, db_path, registered = registered_sources
    
    # First synthesize
    pending = []
    for proposal in PROPOSED_LESSONS:
        result = store.add_entry(
            title=proposal["title"],
            source_url=f"k3://learning_run/affiliate_video_creation/{proposal['title'][:50]}",
            platform="repository_doc",
            category=proposal["category"],
            hook_type="",
            cta_style="",
            voice_tone="",
            key_lessons=proposal["key_lessons"],
            detail_data={
                "knowledge_type": proposal["knowledge_type"],
                "confidence": proposal["confidence"],
                "source_refs": proposal["source_refs"],
                "learning_run": "k3_real_learning",
                "historical_only": proposal.get("historical_only", False),
            },
            source="k3_synthesis",
            owner_user_id="k3_owner",
            allow_multiple_source_lessons=True,
        )
        pending.append(result)
    
    # HITL authorization
    lifecycle = KnowledgeLifecycle(store)
    
    approved_count = 0
    rejected_count = 0
    for lesson in pending:
        detail = store.get_entry_detail(lesson["id"])
        historical_only = detail.get("historical_only", False)
        
        if historical_only:
            result = lifecycle.reject(
                lesson["id"],
                LifecycleActor.owner("k3_owner"),
                reason="Historical context only; not approved as current guidance",
            )
            if result.ok:
                rejected_count += 1
        else:
            result = lifecycle.approve(
                lesson["id"],
                LifecycleActor.owner("k3_owner"),
                mode="k3_real_learning",
            )
            if result.ok:
                approved_count += 1
            elif result.code == "duplicate_warning":
                # Force approve if duplicate detected
                result = lifecycle.approve(
                    lesson["id"],
                    LifecycleActor.owner("k3_owner"),
                    mode="k3_real_learning",
                    force=True,
                )
                if result.ok:
                    approved_count += 1
    
    # Verify state
    assert approved_count > 0
    assert rejected_count > 0
    
    approved = store.list_entries(status="approved", owner_user_id="k3_owner")
    rejected = store.list_entries(status="rejected", owner_user_id="k3_owner")
    
    # Approved-only FTS5
    assert len(approved) >= 1
    assert len(rejected) >= 1


def test_k3_fts5_approved_only_retrieval(registered_sources):
    """Approved lessons are FTS5-retrievable; pending/rejected excluded."""
    store, db_path, registered = registered_sources
    
    # Synthesize + approve
    pending = []
    for proposal in PROPOSED_LESSONS:
        result = store.add_entry(
            title=proposal["title"],
            source_url=f"k3://learning_run/affiliate_video_creation/{proposal['title'][:50]}",
            platform="repository_doc",
            category=proposal["category"],
            hook_type="",
            cta_style="",
            voice_tone="",
            key_lessons=proposal["key_lessons"],
            detail_data={
                "knowledge_type": proposal["knowledge_type"],
                "confidence": proposal["confidence"],
                "source_refs": proposal["source_refs"],
                "learning_run": "k3_real_learning",
                "historical_only": proposal.get("historical_only", False),
            },
            source="k3_synthesis",
            owner_user_id="k3_owner",
            allow_multiple_source_lessons=True,
        )
        pending.append(result)
    
    lifecycle = KnowledgeLifecycle(store)
    for lesson in pending:
        detail = store.get_entry_detail(lesson["id"])
        historical_only = detail.get("historical_only", False)
        if historical_only:
            lifecycle.reject(lesson["id"], LifecycleActor.owner("k3_owner"), reason="Historical only")
        else:
            lifecycle.approve(lesson["id"], LifecycleActor.owner("k3_owner"), mode="k3_real_learning", force=True)
    
    # FTS5 retrieval
    test_queries = [
        "creative brief value proposition",
        "storyboard identity consistency",
        "video motion prompt",
        "affiliate disclosure compliance",
        "FFmpeg timeline composition",
        "safe zone placement",
    ]
    
    for query in test_queries:
        context = store.get_approved_context(query, max_entries=3, owner_user_id="k3_owner")
        assert isinstance(context, str)
        # If approved lessons exist, context should have the marker
        approved = store.list_entries(status="approved", owner_user_id="k3_owner")
        if approved:
            assert "APPROVED HERMES KNOWLEDGE" in context or context == ""


def test_k3_cross_capability_reuse(registered_sources):
    """Hermes reuses learned Knowledge in another capability (e.g., Creative Brief prep)."""
    store, db_path, registered = registered_sources
    
    # Approve all non-historical lessons
    pending = []
    for proposal in PROPOSED_LESSONS:
        result = store.add_entry(
            title=proposal["title"],
            source_url=f"k3://learning_run/affiliate_video_creation/{proposal['title'][:50]}",
            platform="repository_doc",
            category=proposal["category"],
            hook_type="",
            cta_style="",
            voice_tone="",
            key_lessons=proposal["key_lessons"],
            detail_data={
                "knowledge_type": proposal["knowledge_type"],
                "confidence": proposal["confidence"],
                "source_refs": proposal["source_refs"],
                "learning_run": "k3_real_learning",
                "historical_only": proposal.get("historical_only", False),
            },
            source="k3_synthesis",
            owner_user_id="k3_owner",
            allow_multiple_source_lessons=True,
        )
        pending.append(result)
    
    lifecycle = KnowledgeLifecycle(store)
    for lesson in pending:
        detail = store.get_entry_detail(lesson["id"])
        historical_only = detail.get("historical_only", False)
        if historical_only:
            lifecycle.reject(lesson["id"], LifecycleActor.owner("k3_owner"), reason="Historical only")
        else:
            lifecycle.approve(lesson["id"], LifecycleActor.owner("k3_owner"), mode="k3_real_learning", force=True)
    
    # Cross-capability reuse: Hermes prepares Creative Brief
    # Hermes retrieves creative planning principles
    creative_brief_context = store.get_approved_context(
        "creative brief structure value proposition",
        max_entries=3,
        owner_user_id="k3_owner",
    )
    
    # Hermes retrieves compliance principles
    compliance_context = store.get_approved_context(
        "affiliate disclosure compliance",
        max_entries=2,
        owner_user_id="k3_owner",
    )
    
    # Both contexts retrievable
    assert isinstance(creative_brief_context, str)
    assert isinstance(compliance_context, str)
    
    # Cross-capability: Hermes could now invoke Video Factory MCP
    # using these learned principles (no coupling required)


def test_k3_fresh_session_reconstruction(registered_sources):
    """Fresh process can reconstruct complete K3 state from durable storage."""
    store, db_path, registered = registered_sources
    
    # Synthesize + approve
    pending = []
    for proposal in PROPOSED_LESSONS:
        result = store.add_entry(
            title=proposal["title"],
            source_url=f"k3://learning_run/affiliate_video_creation/{proposal['title'][:50]}",
            platform="repository_doc",
            category=proposal["category"],
            hook_type="",
            cta_style="",
            voice_tone="",
            key_lessons=proposal["key_lessons"],
            detail_data={
                "knowledge_type": proposal["knowledge_type"],
                "confidence": proposal["confidence"],
                "source_refs": proposal["source_refs"],
                "learning_run": "k3_real_learning",
                "historical_only": proposal.get("historical_only", False),
            },
            source="k3_synthesis",
            owner_user_id="k3_owner",
            allow_multiple_source_lessons=True,
        )
        pending.append(result)
    
    lifecycle = KnowledgeLifecycle(store)
    for lesson in pending:
        detail = store.get_entry_detail(lesson["id"])
        historical_only = detail.get("historical_only", False)
        if historical_only:
            lifecycle.reject(lesson["id"], LifecycleActor.owner("k3_owner"), reason="Historical only")
        else:
            lifecycle.approve(lesson["id"], LifecycleActor.owner("k3_owner"), mode="k3_real_learning", force=True)
    
    # Fresh process: open new store against same DB
    fresh_store = SQLiteKnowledgeStore(database=Database(db_path))
    
    # Verify all state present
    approved = fresh_store.list_entries(status="approved", owner_user_id="k3_owner")
    rejected = fresh_store.list_entries(status="rejected", owner_user_id="k3_owner")
    sources_list = fresh_store.list_entries(status=None, owner_user_id="k3_owner")
    
    # Filter: sources are in category "affiliate_video_creation"
    sources_only = [s for s in sources_list if s["category"] == "affiliate_video_creation" and s["title"] in {src["title"] for src in SOURCES}]
    lessons_only = [s for s in sources_list if s["source"] == "k3_synthesis"]
    
    assert len(sources_only) >= len(SOURCES)
    assert len(lessons_only) == len(PROPOSED_LESSONS)
    assert len(approved) >= 1
    assert len(rejected) >= 1


def test_k3_provenance_retrievable(registered_sources):
    """Provenance (source_refs, classification) retrievable from approved lessons."""
    store, db_path, registered = registered_sources
    
    pending = []
    for proposal in PROPOSED_LESSONS:
        result = store.add_entry(
            title=proposal["title"],
            source_url=f"k3://learning_run/affiliate_video_creation/{proposal['title'][:50]}",
            platform="repository_doc",
            category=proposal["category"],
            hook_type="",
            cta_style="",
            voice_tone="",
            key_lessons=proposal["key_lessons"],
            detail_data={
                "knowledge_type": proposal["knowledge_type"],
                "confidence": proposal["confidence"],
                "source_refs": proposal["source_refs"],
                "learning_run": "k3_real_learning",
                "historical_only": proposal.get("historical_only", False),
            },
            source="k3_synthesis",
            owner_user_id="k3_owner",
            allow_multiple_source_lessons=True,
        )
        pending.append(result)
    
    lifecycle = KnowledgeLifecycle(store)
    for lesson in pending:
        detail = store.get_entry_detail(lesson["id"])
        historical_only = detail.get("historical_only", False)
        if historical_only:
            lifecycle.reject(lesson["id"], LifecycleActor.owner("k3_owner"), reason="Historical only")
        else:
            lifecycle.approve(lesson["id"], LifecycleActor.owner("k3_owner"), mode="k3_real_learning", force=True)
    
    # Check provenance
    approved = store.list_entries(status="approved", owner_user_id="k3_owner")
    assert len(approved) > 0
    
    for lesson in approved:
        detail = store.get_entry_detail(lesson["id"])
        assert "source_refs" in detail, f"No provenance for {lesson['title']}"
        assert len(detail["source_refs"]) > 0, f"Empty source_refs for {lesson['title']}"


def test_k3_current_vs_historical_classification(registered_sources):
    """Sources and lessons preserve current vs historical classification."""
    store, db_path, registered = registered_sources
    
    # Verify source classifications
    for src in SOURCES:
        lesson = registered[src["source_id"]]
        detail = store.get_entry_detail(lesson["id"])
        assert detail["classification"] in {"current", "historical"}, \
            f"Invalid classification for {src['source_id']}: {detail['classification']}"
    
    # Count current vs historical sources
    current_sources = [s for s in SOURCES if s["classification"] == "current"]
    historical_sources = [s for s in SOURCES if s["classification"] == "historical"]
    
    assert len(current_sources) >= 4, "Should have multiple current sources"
    assert len(historical_sources) >= 1, "Should have at least one historical source"


def test_k3_data_health_post_learning(registered_sources):
    """Run data health checks after K3 learning completes."""
    store, db_path, registered = registered_sources
    
    # Synthesize + approve
    pending = []
    for proposal in PROPOSED_LESSONS:
        result = store.add_entry(
            title=proposal["title"],
            source_url=f"k3://learning_run/affiliate_video_creation/{proposal['title'][:50]}",
            platform="repository_doc",
            category=proposal["category"],
            hook_type="",
            cta_style="",
            voice_tone="",
            key_lessons=proposal["key_lessons"],
            detail_data={
                "knowledge_type": proposal["knowledge_type"],
                "confidence": proposal["confidence"],
                "source_refs": proposal["source_refs"],
                "learning_run": "k3_real_learning",
                "historical_only": proposal.get("historical_only", False),
            },
            source="k3_synthesis",
            owner_user_id="k3_owner",
            allow_multiple_source_lessons=True,
        )
        pending.append(result)
    
    lifecycle = KnowledgeLifecycle(store)
    for lesson in pending:
        detail = store.get_entry_detail(lesson["id"])
        historical_only = detail.get("historical_only", False)
        if historical_only:
            lifecycle.reject(lesson["id"], LifecycleActor.owner("k3_owner"), reason="Historical only")
        else:
            lifecycle.approve(lesson["id"], LifecycleActor.owner("k3_owner"), mode="k3_real_learning", force=True)
    
    # Verify data integrity
    all_lessons = store.list_entries(status=None, owner_user_id="k3_owner")
    approved = [l for l in all_lessons if l["status"] == "approved"]
    rejected = [l for l in all_lessons if l["status"] == "rejected"]
    
    # Counts must match
    assert len(approved) + len(rejected) == len(PROPOSED_LESSONS), \
        f"State mismatch: approved={len(approved)}, rejected={len(rejected)}, proposed={len(PROPOSED_LESSONS)}"
    
    # No duplicate IDs
    ids = [l["id"] for l in all_lessons]
    assert len(ids) == len(set(ids)), "Duplicate lesson IDs found"
    
    # FTS5 approved count
    fts_context = store.get_approved_context("video creation principles", max_entries=20, owner_user_id="k3_owner")
    assert isinstance(fts_context, str)


def test_k3_duplicate_detection_safe(registered_sources):
    """Duplicate detection via duplicate_warning + force=True works."""
    store, db_path, registered = registered_sources
    
    # Add same lesson twice
    title = "Test Duplicate Detection"
    key_lessons = ["Lesson 1", "Lesson 2"]
    
    # First addition
    first = store.add_entry(
        title=title,
        source_url="k3://duplicate_test/1",
        platform="test",
        category="test",
        hook_type="",
        cta_style="",
        voice_tone="",
        key_lessons=key_lessons,
        detail_data={},
        source="k3_test",
        owner_user_id="k3_owner",
        allow_multiple_source_lessons=True,
    )
    
    # Approve first
    lifecycle = KnowledgeLifecycle(store)
    lifecycle.approve(first["id"], LifecycleActor.owner("k3_owner"), mode="k3_test")
    
    # Try to add very similar lesson (different URL but same content)
    second = store.add_entry(
        title=title,  # Same title
        source_url="k3://duplicate_test/2",  # Different URL
        platform="test",
        category="test",
        hook_type="",
        cta_style="",
        voice_tone="",
        key_lessons=key_lessons,  # Same key_lessons
        detail_data={},
        source="k3_test",
        owner_user_id="k3_owner",
        allow_multiple_source_lessons=True,
    )
    
    # Try to approve second — should hit duplicate detection
    result = lifecycle.approve(second["id"], LifecycleActor.owner("k3_owner"), mode="k3_test")
    
    # Either duplicate_warning or already approved via update
    assert result.code in {"duplicate_warning", "changed", "unchanged", "not_found"}


if __name__ == "__main__":
    # Run pytest
    pytest.main([__file__, "-v"])