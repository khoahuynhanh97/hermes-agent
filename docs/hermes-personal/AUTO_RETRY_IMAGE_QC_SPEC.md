# Auto-Retry Image QC with Image Cleaner Integration - Technical Specification

**Status:** Design Review  
**Created:** 2026-09-29  
**Priority:** P0 (Tier 1 - Critical Path)  

---

## 1. Problem Statement

### Current Behavior
When Image QC returns `FAIL` verdict due to watermarks/seller branding:
```
BUILDING_RESOURCE_PACK → Image QC → FAIL (score < 80)
  ↓
Workflow STOPS at AWAITING_PRODUCT_LOCK
  ↓
Requires manual intervention (operator must approve or reject)
```

**Real Example:** `pv-daily-be6eac6be72f9bea` (JBL PartyBox 310)
- Image QC Score: 12/100
- Verdict: FAIL
- Reason: `HDRADIO` watermark, seller branding detected
- **Result:** Video production BLOCKED

### Desired Behavior
```
BUILDING_RESOURCE_PACK → Image QC → FAIL
  ↓ (Auto-trigger)
Image Cleaner (Inpainting) → Clean watermarks/logos
  ↓
Re-run Image QC on cleaned images → PASS (score >= 80)
  ↓
Continue to AWAITING_PRODUCT_LOCK (normal flow)
```

---

## 2. Architecture Design

### 2.1 Workflow State Extensions

**Add new transient state** (no HITL gate):

```python
# hermes_personal/product_video/workflow_state.py

class ProductVideoWorkflowState(str, Enum):
    # ... existing states ...
    BUILDING_RESOURCE_PACK = "building_resource_pack"
    RETRYING_IMAGE_QC = "retrying_image_qc"  # NEW: Transient cleanup state
    AWAITING_PRODUCT_LOCK = "AwaitingProductLock"
```

**State Transition:**
```
BUILDING_RESOURCE_PACK → Image QC FAIL → RETRYING_IMAGE_QC → Image QC PASS → AWAITING_PRODUCT_LOCK
                                       ↓ Image QC FAIL again ↓
                                       Terminal FAIL (manual review)
```

### 2.2 Resource Pack Job Enhancement

**Location:** `hermes_personal/product_video/handlers.py::resource_pack_job()`

**Current Flow:**
```python
def resource_pack_job(ctx, research_result, **kwargs):
    result = pi_client.build_resource_pack(research_result)
    return JobSucceeded(artifact_ref=result, next_command={"command": "lock_resource_pack"})
```

**Enhanced Flow:**
```python
def resource_pack_job(ctx, research_result, **kwargs):
    # Build resource pack
    result = pi_client.build_resource_pack(research_result)
    
    # Auto-run Image QC
    qc_report, eligible_items = run_image_qc(
        workflow_id=ctx.workflow_id,
        resource_pack=result,
        product=extract_product_from_research(research_result),
        repo=QCReportRepository(connection),
    )
    
    # Store QC report in aggregate
    updated_artifact = {**result, "initial_qc_report": qc_report.to_dict()}
    
    if qc_report.verdict == QCVerdict.FAIL:
        # Check if cleanable (has watermark/branding issues)
        if is_cleanable_failure(qc_report):
            return JobSucceeded(
                artifact_ref=updated_artifact,
                next_command={"command": "retry_image_qc_with_cleaning"}
            )
        else:
            # Terminal failure (missing files, corrupted images, etc.)
            return JobSucceeded(
                artifact_ref=updated_artifact,
                next_command={"command": "lock_resource_pack"}  # Goes to manual review
            )
    
    # QC passed on first attempt
    return JobSucceeded(
        artifact_ref=updated_artifact,
        next_command={"command": "lock_resource_pack"}
    )
```

### 2.3 New Job Handler: `retry_image_qc_job()`

```python
def retry_image_qc_job(self, ctx: JobContext, resource_pack: dict, **kwargs) -> JobSucceeded | JobFailed:
    """Auto-retry Image QC with image cleaning for recoverable failures."""
    
    # 1. Validate state
    err = self._validate_state_and_version(
        ctx,
        {ProductVideoWorkflowState.RETRYING_IMAGE_QC, ProductVideoWorkflowState.BUILDING_RESOURCE_PACK},
        {"resource_pack": resource_pack},
    )
    if err:
        return err
    
    # 2. Extract original QC report
    initial_qc = resource_pack.get("initial_qc_report")
    if not initial_qc or initial_qc.get("verdict") != "FAIL":
        return JobFailed(
            retryable=False,
            code="INVALID_STATE",
            message="retry_image_qc_job requires a FAIL QC report"
        )
    
    # 3. Check retry count (max 1 retry to avoid infinite loops)
    retry_count = resource_pack.get("image_qc_retry_count", 0)
    if retry_count >= 1:
        return JobFailed(
            retryable=False,
            code="MAX_RETRIES_EXCEEDED",
            message="Image QC already retried once; manual review required"
        )
    
    # 4. Run Image Cleaner
    from hermes_personal.product_video.preprocessing.image_cleaner import ProductImageCleaner
    
    cleaner = ProductImageCleaner()
    cleaning_result = cleaner.clean_resource_pack(
        resource_pack=resource_pack,
        output_dir=None,  # Auto-generates in workspace
        detected_artifacts=extract_artifacts_from_qc(initial_qc),
    )
    
    if not cleaning_result.get("cleaned_images"):
        return JobFailed(
            retryable=False,
            code="CLEANING_FAILED",
            message="Image Cleaner produced no cleaned images"
        )
    
    # 5. Update resource pack with cleaned images
    cleaned_pack = replace_images_in_resource_pack(
        resource_pack=resource_pack,
        cleaned_images=cleaning_result["cleaned_images"]
    )
    cleaned_pack["image_qc_retry_count"] = retry_count + 1
    cleaned_pack["cleaning_summary"] = cleaning_result.get("summary")
    
    # 6. Re-run Image QC on cleaned images
    product = extract_product_from_research(resource_pack.get("research_snapshot"))
    retry_qc_report, retry_eligible = run_image_qc(
        workflow_id=ctx.workflow_id,
        resource_pack=cleaned_pack,
        product=product,
        repo=QCReportRepository(ctx.connection),
        attempt_id=f"retry_{retry_count + 1}",
    )
    
    cleaned_pack["retry_qc_report"] = retry_qc_report.to_dict()
    
    if retry_qc_report.verdict == QCVerdict.PASS:
        # SUCCESS: Cleaned images passed QC
        return JobSucceeded(
            artifact_ref=cleaned_pack,
            next_command={"command": "lock_resource_pack"}
        )
    else:
        # FAIL: Cleaning did not fix the issue -> terminal failure
        return JobFailed(
            retryable=False,
            code="IMAGE_QC_TERMINAL_FAILURE",
            message=f"Image QC failed after cleaning: {retry_qc_report.findings.get('recovery_reason')}"
        )
```

---

## 3. Image Cleaner Integration

### 3.1 Extract Artifacts from QC Report

```python
def extract_artifacts_from_qc(qc_report: dict) -> list[dict]:
    """Extract detected artifact categories from QC findings for targeted inpainting."""
    items = qc_report.get("findings", {}).get("items", [])
    
    artifacts = []
    for item in items:
        if not item.get("eligible", False):
            risk_flags = item.get("findings", {}).get("risk_flags", [])
            
            # Map risk flags to artifact categories
            category_map = {
                "watermark": "GENERIC_WATERMARK",
                "logo": "SELLER_BRANDING",
                "text_overlay": "SPEC_CALLOUT_OVERLAY",
                "banner": "PROMOTIONAL_TAG",
                "badge": "MARKETPLACE_BADGE",
            }
            
            for flag in risk_flags:
                if flag in category_map:
                    artifacts.append({
                        "asset_id": item["asset_id"],
                        "category": category_map[flag],
                        "confidence": item.get("score", 0) / 100.0,
                    })
    
    return artifacts
```

### 3.2 Replace Images in Resource Pack

```python
def replace_images_in_resource_pack(
    resource_pack: dict,
    cleaned_images: list[dict]
) -> dict:
    """Replace original images with cleaned versions in resource pack."""
    
    cleaned_pack = dict(resource_pack)
    cleaned_by_id = {img["asset_id"]: img for img in cleaned_images}
    
    updated_assets = []
    for asset in resource_pack.get("media_assets", []):
        asset_id = asset.get("asset_id")
        
        if asset_id in cleaned_by_id:
            # Replace with cleaned version
            cleaned = cleaned_by_id[asset_id]
            updated_asset = {
                **asset,
                "local_path": cleaned["cleaned_path"],
                "sha256": cleaned["clean_sha256"],
                "original_path": asset.get("local_path"),  # Preserve original
                "cleaning_applied": True,
                "detected_artifacts": cleaned.get("detected_categories", []),
            }
            updated_assets.append(updated_asset)
        else:
            # Keep original
            updated_assets.append(asset)
    
    cleaned_pack["media_assets"] = updated_assets
    return cleaned_pack
```

---

## 4. Configuration & Policy

### 4.1 Config Options

```yaml
# config.yaml
product_video:
  image_qc:
    auto_retry_enabled: true
    max_retry_attempts: 1
    cleanable_failure_threshold: 50  # Min score to attempt cleaning
    terminal_failure_categories:
      - "missing_file"
      - "corrupted_image"
      - "insufficient_resolution"
```

### 4.2 Cleanable vs Terminal Failures

```python
def is_cleanable_failure(qc_report: QCReport) -> bool:
    """Determine if Image QC failure is recoverable via cleaning."""
    
    # Must have some eligible images (not all corrupted)
    if qc_report.score < 20:
        return False  # Too low, likely fundamental issues
    
    # Check recovery actions
    recovery_actions = qc_report.findings.get("recovery_actions", [])
    if "reacquire_references" in recovery_actions:
        return False  # Need new images, cleaning won't help
    
    # Check if failures are watermark/branding related
    items = qc_report.findings.get("items", [])
    failed_items = [it for it in items if not it.get("eligible")]
    
    cleanable_risks = {"watermark", "logo", "text_overlay", "banner", "badge"}
    for item in failed_items:
        risk_flags = set(item.get("findings", {}).get("risk_flags", []))
        if risk_flags & cleanable_risks:
            return True  # At least one cleanable issue found
    
    return False
```

---

## 5. Testing Strategy

### 5.1 Unit Tests

```python
# tests/hermes_personal/product_video/test_auto_retry_image_qc.py

def test_retry_image_qc_success(temp_db, mock_resource_pack_with_watermark):
    """Test successful QC retry after cleaning."""
    # Initial QC fails with watermark
    # Cleaning removes watermark
    # Retry QC passes
    pass

def test_retry_image_qc_terminal_failure(temp_db, mock_resource_pack_corrupted):
    """Test terminal failure (non-cleanable)."""
    # Initial QC fails with corrupted images
    # is_cleanable_failure() returns False
    # Workflow proceeds to manual review
    pass

def test_max_retry_limit(temp_db, mock_resource_pack):
    """Test max retry attempts enforced."""
    # First retry: FAIL
    # Second retry attempt: rejected (max_retries_exceeded)
    pass
```

### 5.2 Integration Test

```python
def test_e2e_auto_retry_workflow(temp_db, mock_daily_run_with_watermarked_images):
    """Test end-to-end workflow with auto-retry."""
    # Publish batch with watermarked images
    # Start workflow
    # Resource pack built
    # Image QC fails
    # Auto-cleaning triggered
    # Image QC retried and passes
    # Workflow continues to Product Lock
    pass
```

---

## 6. Rollout Plan

### Phase 1: Foundation (Days 1-2)
- [ ] Add `RETRYING_IMAGE_QC` state to workflow_state.py
- [ ] Implement `is_cleanable_failure()` logic
- [ ] Implement `extract_artifacts_from_qc()`
- [ ] Unit tests for artifact extraction

### Phase 2: Handler Implementation (Days 3-4)
- [ ] Implement `retry_image_qc_job()` handler
- [ ] Enhance `resource_pack_job()` with QC check
- [ ] Implement `replace_images_in_resource_pack()`
- [ ] Unit tests for retry handler

### Phase 3: Integration (Day 5)
- [ ] Wire handler into job dispatcher
- [ ] Add state transition logic
- [ ] Integration tests
- [ ] Test with real JBL PartyBox 310 workflow

### Phase 4: Validation (Day 6)
- [ ] Re-run failed workflow `pv-daily-be6eac6be72f9bea`
- [ ] Verify cleaning + retry succeeds
- [ ] Performance testing (retry latency)
- [ ] Documentation update

---

## 7. Success Metrics

**Before Implementation:**
- Image QC FAIL → 100% manual intervention
- Workflows blocked: ~30% (watermark/branding issues)

**After Implementation:**
- Image QC FAIL → Auto-retry → 80% success
- Manual intervention reduced to: ~6% (20% × 30%)
- Average time to recovery: < 5 minutes (vs. hours/days manual)

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Infinite retry loop | High | Max 1 retry enforced in code |
| Image Cleaner removes product features | Medium | QC validation on cleaned images |
| Increased API costs (re-running QC) | Low | Only 1 retry, ~$0.01 per image |
| State machine complexity | Medium | Clear state transition docs + tests |

---

## 9. Open Questions

1. **Should retry be synchronous or async?**
   - Recommendation: Synchronous (simpler, < 2 min latency acceptable)

2. **Preserve original images after cleaning?**
   - Recommendation: Yes, store in `original_path` field for audit

3. **Expose retry status in operator console?**
   - Recommendation: Yes, show "Cleaning applied" badge + before/after QC scores

---

## 10. Next Steps

**Approval Required:**
- [ ] Tech Lead review of state machine changes
- [ ] QA review of testing strategy
- [ ] PM review of success metrics

**Ready to Implement:**
Once approved, estimated implementation: **5-6 days** (Phase 1-4).

---

**Author:** Kiro AI  
**Reviewers:** [Pending]  
**Status:** Awaiting Approval
