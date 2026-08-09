# Product Identity Evidence Contract

Use this structure for analysis before mapping confirmed details to
`ResourceIdentity`.

```json
{
  "subject": {
    "category": "observed category or unknown",
    "brand": "observed brand or unknown",
    "model_or_variant": "observed model or unknown"
  },
  "references": [
    {
      "asset_id": "source asset id",
      "view": "front | rear | side | top | bottom | open | closed | detail | unknown",
      "quality_limits": ["occluded", "blurred", "reflection", "cropped"],
      "observations": [
        {
          "attribute": "component.feature",
          "value": "atomic visual observation",
          "status": "observed | inferred | unknown | conflicting",
          "confidence": "high | medium | low",
          "evidence_region": "plain-language image region"
        }
      ]
    }
  ],
  "stable_invariants": [
    {
      "attribute": "component.feature",
      "value": "confirmed visual invariant",
      "source_asset_ids": ["asset-a", "asset-b"]
    }
  ],
  "view_dependent_features": [],
  "unknowns": [],
  "conflicts": [],
  "excluded_inferences": [],
  "lock_readiness": "ready | needs_references | needs_variant_decision"
}
```

Cover only applicable categories:

- Overall silhouette, topology, orientation, and relative proportions.
- Components, seams, openings, controls, ports, hinges, and attachments.
- Color and finish by component, including transparent or reflective regions.
- Material appearance without claiming composition that cannot be seen.
- Logos, labels, symbols, and exact placement on the product body.
- Repeated patterns, edge profiles, contours, and distinctive transitions.
- Open/closed, assembled/disassembled, powered/unpowered states.
- Packaging versus product-body details.

Do not invent physical dimensions without a calibrated scale. Do not infer rear,
underside, internal, or occluded details from product familiarity.
