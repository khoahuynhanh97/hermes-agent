# Product Visual QC Contract

```json
{
  "artifact_id": "generated asset id",
  "artifact_type": "image | video",
  "identity_lock_version": 1,
  "canonical_reference_asset_ids": ["asset-a"],
  "technical_checks": [
    {"check": "readable", "result": "pass | fail", "details": ""}
  ],
  "identity_checks": [
    {
      "attribute": "component.feature",
      "expected": "value from locked evidence",
      "observed": "value in generated artifact",
      "result": "pass | fail | not_visible | uncertain",
      "reference_asset_ids": ["asset-a"],
      "artifact_regions_or_timestamps": ["00:02.5"]
    }
  ],
  "temporal_checks": [],
  "violations": [],
  "decision": "pass | fail | needs_human_review",
  "revision_constraints": []
}
```

Do not hide a critical failure inside an aggregate score. A score may support
triage, but any contradiction of a defining invariant is a failure regardless
of average similarity.
