---
name: hoc
description: Capture grounded knowledge and source artifacts (knowledge mode)
aliases:
  - hoc_kien_thuc
allowed-capabilities:
  - knowledge.candidate.create
allowed-tools:
  - knowledge_candidate_create
  - knowledge_retrieve
---

# Học / Knowledge Capture

This skill delegates to the `learning-from-video` skill in `knowledge` mode.

Invoke the `learning-from-video` skill with mode `knowledge`:
- Load `learning-from-video` via skill_view or skill loading
- Follow the 8-step procedure contract from `skills/media/learning-from-video/references/procedure-contract.md`
- Produce `knowledge_analysis.md` as the required analysis artifact

The user instruction is: capture knowledge and artifacts from the provided media source.
