# Hermes Personal Security and Authentication

## Scope

This document narrows the repository-wide [security policy](../SECURITY.md) to
the `hermes_personal` bounded context. It records implemented controls and known
limitations; it is not a certification claim.

## Trust boundaries

```mermaid
flowchart LR
    U[External user/channel] -->|untrusted envelope| A[Ingress adapter]
    A -->|authenticated subject| N[ChannelTurnNormalizer]
    N -->|owner/session lookup| DB[(SQLite identity/session store)]
    N --> T[HermesTurnService]
    T --> P[Capability policy]
    P --> X[Tool/provider boundary]
    T --> E[(Event/workflow store)]
    W[Web operator] -->|ephemeral session token/cookie| APP[Public App API]
    APP -->|Gateway Bearer key over loopback| API[Gateway FastAPI]
    API --> E
```

External channel payloads, HTTP JSON, attachment URIs, capability arguments,
provider responses, persisted metadata, and replay cursors are untrusted.

## Identity and session authentication

Ingress adapters must authenticate their platform-specific subject before
normalization. The normalizer accepts the resulting `(channel,
external_subject)` and resolves it through `IdentityRepository`; it does not
trust caller-supplied `owner_user_id` or `session_id`.

Sessions are unique per owner, channel, and external conversation. A workflow
may continue on another channel only when an explicit `workflow_handoff` exists
and both sessions belong to the same owner.

## HTTP authentication

The runnable topology has two credentials with separate trust scopes:

- The Gateway accepts `HERMES_API_KEY`, binds it to `HERMES_OWNER_ID`, and uses
  constant-time comparison. It listens on loopback by default.
- The public App API generates a random process-lifetime browser session token,
  injects it into bootstrap HTML, and sets a `SameSite=Strict` cookie. It strips
  compatibility query credentials and adds the Gateway key only on the
  server-to-server request.

The browser never receives `HERMES_API_KEY`. The direct Gateway router still
accepts `auth_token` query/body input for compatibility, so the Gateway must
remain on loopback or behind a trusted internal boundary. New clients must use
the Bearer header or the App API cookie and must not put credentials in URLs.

An unconfigured `EventsAPI` now fails closed. Custom composition must inject an
owner-bound validator; a non-empty token by itself is not accepted.

## Authorization model

Implemented authorization is owner- and policy-based:

- event replay filters by owner;
- artifact retrieval checks `artifact.owner_user_id == owner_id`;
- sessions and workflow handoffs enforce owner identity;
- capability policy checks principal mode, skill/workflow allowlists, health,
  schema version, approval status, budget, risk, and cost tier.

`PrincipalContext.roles` transports role metadata, but there is no complete RBAC
policy engine in this bounded context. Do not claim administrator/operator RBAC
until route- and capability-level role enforcement and tests are added.

## Secrets

Secrets belong in environment variables or the upstream Hermes secret store,
never in source, YAML committed to Git, command-line argv, events, workflow
payloads, or artifact metadata.

The runtime checks configured secret names for presence. Process topology also
rejects argv values that resemble common secret formats. Logging and
`CapabilityError` serialization use recursive redaction; new error paths must use
the same sanitizer.

Minimum production controls:

1. inject secrets at process start with least privilege;
2. restrict filesystem ACLs for database, artifacts, and logs;
3. rotate API and platform tokens without rebuilding images;
4. redact tokens before structured logging or telemetry export;
5. never return provider credentials in `details`, health responses, or failures;
6. remove direct-Gateway query compatibility when all internal clients support
   headers.

## Capability and provider access

All capability execution must pass the policy matrix before invocation.
High-risk, metered, or paid work requires the configured approval and budget
preconditions. Skills and workflows may only call declared capability IDs.

The product-intelligence and video-factory clients in this checkout are
deterministic local contracts. They do not perform paid provider calls and must
not be represented as production provider authentication.

## Attachments and artifacts

- Validate attachment kind, media type, size, URI scheme, and lowercase SHA-256
  when supplied.
- Resolve local paths beneath configured roots; reject path traversal and foreign
  owner references.
- Serve metadata only after owner authorization.
- Treat digests and versions as integrity metadata, not as authorization.
- Scan or sandbox active document/media content before external processing.

## Audit and observability

Security-relevant operations should retain principal, owner, session, turn,
workflow, command, approval, job, and event IDs. Audit events must record the
decision and policy reason without recording secret values or unnecessary user
content.

## Production security gate

Do not expose the application until all of these are true:

- the owner-bound Gateway validator and browser-session boundary are enabled;
- TLS terminates at the service or a trusted reverse proxy;
- database/artifact/log ACLs are verified;
- required startup callbacks and dependency probes are wired;
- CORS and trusted-proxy behavior are explicitly configured;
- rate limits and request-size limits are enforced at the edge or application;
- `/api/turn` is mounted only with the same identity and idempotency controls;
- secret redaction and negative authorization tests pass.
