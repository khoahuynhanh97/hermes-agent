---
name: product-visual-qc
allowed-tools:
  - mcp__hermes_video__video_analyze
metadata:
  hermes:
    governed: true
    requires_tools:
      - mcp__hermes_video__video_analyze
---

# Product Visual QC

Evaluate generated media against original references and the approved identity
lock. QC is read-only: it never approves business gates or regenerates media.

## Inputs

- Canonical original reference assets and their per-image evidence metadata.
- Current locked `ResourceIdentity` and lock version.
- Generated artifact, scene/frame requirement, and generation prompt.
- Prior QC report when reviewing a revision.

Never use the generated artifact as ground truth. When lock text and original
references appear inconsistent, return `needs_human_review` and stop downstream
work.

## Image QC

1. Run deterministic checks: readable file, expected dimensions/aspect ratio,
   blank/corrupt output, duplicate frame, and unexpected baked-in text.
2. Compare the generated product with the relevant original views.
3. Check only visible applicable invariants: silhouette, topology, component
   count and relationships, relative proportions, colors, finish, logo placement,
   controls, openings, seams, and distinctive features.
4. Separate identity defects from composition or aesthetic defects.
5. Emit the report in [references/qc-contract.md](references/qc-contract.md).

## Video QC

- Inspect start, middle, end, and transition/key-motion frames.
- Check temporal stability: no morphing, component appearance/disappearance,
  logo drift, color drift, topology change, or substitution.
- Verify that every identity-critical start image passed image QC.
- A clean first frame does not compensate for later identity drift.

## Decision Rules

- `pass`: all applicable required invariants are supported and no critical
  technical or identity defect is present.
- `fail`: a visible invariant is contradicted, the product is substituted, or
  media is technically unusable.
- `needs_human_review`: evidence is insufficient, views are incomparable, or
  original references and lock disagree.

QC pass permits asking for HITL approval; it does not grant that approval. On
failure, record exact violations and suggested constraint changes, then stop.
Any new paid regeneration requires separate explicit approval.
