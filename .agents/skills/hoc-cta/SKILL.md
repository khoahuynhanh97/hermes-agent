---
name: hoc-cta
description: Capture hooks, CTA, and conversion structures from media
allowed-capabilities:
  - knowledge.candidate.create
allowed-tools:
  - knowledge_candidate_create
  - knowledge_retrieve
---

# Học CTA / Conversion Capture

This skill delegates to the `learning-from-video` skill in `cta` mode.

Invoke the `learning-from-video` skill with mode `cta`:
- Load `learning-from-video` via skill_view or skill loading
- Follow the 8-step procedure contract from `skills/media/learning-from-video/references/procedure-contract.md`
- Produce `cta_analysis.md` as the required analysis artifact

The user instruction is: analyze hooks, CTA, and conversion structures from the provided media source.
