# Hermes Personal Architecture Rule

## Scope

This rule is mandatory before changing `hermes_personal/` code ownership,
contracts, workflow structure, persistence, schemas, paths, JSON manifests,
images, keyframes, storyboards, clips, QC records, or final video exports.

## Required Guidance

Load and follow all three files before editing:

1. [Governance skill](../../.agents/skills/hermes-personal-architecture-governance/SKILL.md)
2. [Code architecture rules](../../.agents/skills/hermes-personal-architecture-governance/references/code-architecture.md)
3. [Data and artifact rules](../../.agents/skills/hermes-personal-architecture-governance/references/data-architecture.md)

Also follow the authority order in [`docs/README.md`](../../docs/README.md). Source
and tests outrank plans and historical reports.

## Activation Contract

Before implementation, identify and report:

- the existing owner of the code or artifact;
- the durable source of truth;
- the affected contract, version, and compatibility path;
- the artifact lineage and HITL gates that must remain valid;
- the focused tests that prove behavior and restart/recovery safety.

Do not create a parallel owner, path resolver, output tree, schema, repository, or
workflow. Do not persist absolute paths, overwrite approved/versioned artifacts,
bypass QC/HITL, or delete source and export resources. Stop and reconcile with the
canonical architecture when any requested change would require one of these.

The files under `.agents/skills/hermes-personal-architecture-governance/` are the
single source of rule details. Update them first when governance changes; keep this
file as the stable Codex activation entrypoint.
