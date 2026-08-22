# ADR-011: Clean Upstream Gateway Rearchitecture

**Status:** Accepted

**Date:** 2026-08-22

## Context

The legacy Hermes Personal branch and NousResearch Hermes Agent `main` have no
Git merge base. Combining them with an unrelated-history merge would obscure
ownership, make upstream updates unsafe, and carry legacy routing into the new
runtime.

## Decision

The target branch starts from upstream commit
`0012dd1e0c7efc7e86fa75b89567a492057f0c02`. Project-owned behavior is ported
through `hermes_personal`, plugins, skills, MCP adapters, and reviewed upstream
extension points. The legacy branch is a read-only migration source until data
and behavioral parity are verified.

The team must not use `git merge --allow-unrelated-histories` between these
roots. Upstream changes are fetched and reviewed against the pinned baseline;
custom changes are replayed through contract-tested commits.

## Consequences

- Upstream history and updates remain traceable.
- Existing Hermes Personal data is preserved and migrated explicitly.
- Product Intelligence and Video Factory are ported after canonical contracts
  are stable.
- Cutover requires parity tests and a rollback window.

## References

- `docs/superpowers/specs/2026-08-22-hermes-upstream-gateway-rearchitecture-design.md`
- `hermes_personal/data/upstream-baseline.json`
