---
name: hoc-kien-thuc
description: Alias for /hoc — capture grounded knowledge and source artifacts
allowed-capabilities:
  - knowledge.candidate.create
allowed-tools:
  - knowledge_candidate_create
  - knowledge_retrieve
---

# Học Kiến Thức / Knowledge Capture

Alias for `/hoc`. Delegates to the `learning-from-video` skill in `knowledge` mode.

Invoke the `learning-from-video` skill with mode `knowledge`:
- Load `learning-from-video` via skill_view or skill loading
- Follow the 8-step procedure contract from `skills/media/learning-from-video/references/procedure-contract.md`
- Produce `knowledge_analysis.md` as the required analysis artifact
