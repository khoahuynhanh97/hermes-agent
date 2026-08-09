---
name: affiliate-product-research
description: "Run authorized affiliate product research through Hermes Product MCP."
version: 1.0.0
author: Hermes Agent project
license: Internal
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [products, affiliate, research, scoring, shopee]
    related_skills: []
---

# Affiliate Product Research

Use this procedure when the user wants to import, evaluate, shortlist, or
inspect authorized affiliate product candidates.

## Procedure

1. Understand the user's research goal and identify the authorized source/input.
   Confirm `owner_user_id`, CSV path, and a stable `run_id`; ask before acting
   when any required value is missing.
2. Call `product_import_candidates` with the owner, CSV path, and run id.
3. Inspect imported, updated, rejected, error, and warning information. Do not
   score when import errors or authorization failures make the input unusable.
4. When scoring can proceed, call `product_score_shortlist` with the same owner
   and run id. Use valid bounds from 15 to 25 when the user specifies bounds.
5. Call `product_get_run` when persisted state, products, shortlist, warnings,
   or counters are needed for the answer.
6. Explain score components, evidence, ranking, and uncertainty from the tool
   output. Never invent a winner or replace deterministic scoring with a new
   business rule.
7. Preserve business approval state. Ask before any later action that would
   approve, publish, export, message, or otherwise require business approval.
8. Treat a score or shortlist recommendation as non-approval. For a reviewable
   content package, obtain explicit user intent before calling
   `product_approve_package`, `product_reject_package`, or
   `product_request_package_revision`.

## Boundaries

- Use only the Product MCP tools for this workflow.
- The CSV must be an authorized export inside the configured import directory.
- Do not scrape, call provider APIs, access the database directly, or implement
  scoring/persistence in the skill.
- Keep the same owner and run id across the workflow.
- Hermes decides which step to perform next; MCP provides capabilities only.

## Available Product MCP Tools

- `product_import_candidates`: import candidates and attach run observations.
- `product_score_shortlist`: apply existing policy/scoring and persist scores.
- `product_get_run`: read one owner's run state and counters.
- `product_list_packages`: read existing reviewable/generated packages.
- `product_approve_package`: approve one owner-scoped content package after
  explicit business approval.
- `product_reject_package`: reject one owner-scoped content package with an
  optional reason.
- `product_request_package_revision`: request a revision with feedback.
