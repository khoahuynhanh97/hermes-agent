# Hermes 9Router Integration Plan

## Current Status

Hermes now uses `core/llm_gateway.py` as the text access boundary with
environment-driven endpoint/model configuration, timeout, bounded retries,
error mapping, logging, health checks, and controlled legacy fallback. The
local 9Router server responds on `/api/health`, `/v1/models`, and
`/v1/chat/completions`. Live chat is verified with Kiro-backed models:
`kr/glm-5` for chat and `kr/qwen3-coder-next` for learning/code. OpenCode is
configured through a custom `nine-router` provider against the same local
endpoint.

Plan date: 2026-07-12

Status: **VERIFIED FOR TEXT CHAT** against the local 9Router instance on
2026-07-13. Vision, tool calling, JSON mode, context limits, and server-side
fallback behavior remain unverified.

## Decision

Implement the model gateway inside Hermes first. Keep it free of Telegram, job, knowledge, and GUI dependencies so it can be extracted later only if a second real application needs it.

Do not treat the existing `core/ai_router.py` as a 9Router integration. It is an in-process provider router inspired by that idea and directly calls Gemini, Groq, Cerebras, Mistral, OpenRouter, Together, and Ollama. There is currently no connection to `http://localhost:20128/v1`.

## Goals

- Give Hermes one provider-neutral model access API.
- Let Hermes select a model alias by task type.
- Let 9Router provide model access and only the fallback behavior its running version actually supports.
- Preserve direct Gemini text access temporarily as a controlled fallback.
- Keep Hermes conversation, knowledge, permissions, and jobs local to Hermes.
- Add deterministic tests without live provider calls.

## Non-goals

- No shared PyPI/package extraction.
- No dynamic AI model selector.
- No multi-agent runtime.
- No migration of video upload in the first gateway change.
- No paid video providers or production engine.
- No assumption that 9Router supports vision, tools, structured output, usage metadata, or model fallback until verified.

## Proposed package

Use repository naming conventions, for example:

```text
core/llm/
  __init__.py
  config.py
  models.py
  errors.py
  routing.py
  client.py
  gateway.py
```

Keep the package small. `client.py` may contain both the OpenAI-compatible HTTP adapter and a temporary Gemini text adapter until a split is justified.

## Public contract

The first version only needs one synchronous method because the existing worker is synchronous:

```python
result = gateway.complete(
    prompt=prompt,
    task_type="learning",
    system=system_prompt,
    require=ModelRequirements(
        vision=False,
        tools=False,
        structured_output=True,
        min_context_tokens=16_000,
    ),
)
```

Suggested result fields:

```python
LLMResult(
    text="...",
    requested_model="reasoning",
    actual_model="...",       # optional if the service does not report it
    provider="9router",
    duration_ms=1234,
    retry_count=0,
    usage=None,
)
```

The gateway should not know about Telegram updates, job JSON, knowledge entries, or project directories.

## Environment configuration

Add documented empty/default values only; never commit credentials.

```dotenv
LLM_BASE_URL=http://127.0.0.1:20128/v1
LLM_API_KEY=
LLM_DEFAULT_MODEL=
LLM_CHAT_MODEL=
LLM_SUMMARY_MODEL=
LLM_REASONING_MODEL=
LLM_VISION_MODEL=
LLM_CODE_MODEL=
LLM_STRUCTURED_MODEL=
LLM_TIMEOUT_SECONDS=60
LLM_RETRY_COUNT=1
LLM_DIRECT_GEMINI_FALLBACK=0
```

Use `127.0.0.1` by default. Do not bind or expose 9Router publicly as part of Hermes setup.

## Task routing

Hermes chooses a configured alias; it does not ask a model to choose another model.

| Task type | Model setting | Required capability |
| --- | --- | --- |
| `chat` | `LLM_CHAT_MODEL` then default | text |
| `summarize` | `LLM_SUMMARY_MODEL` then chat/default | text, sufficient context |
| `learning` | `LLM_REASONING_MODEL` then default | text, sufficient context |
| `deep_analysis` | `LLM_REASONING_MODEL` | text, larger context |
| `vision` | `LLM_VISION_MODEL` | verified image/video capability |
| `code` | `LLM_CODE_MODEL` then reasoning | code/text |
| `structured_extraction` | `LLM_STRUCTURED_MODEL` then reasoning | reliable JSON plus local validation |

Model names stay in environment configuration. No model ID should be scattered through business modules.

## Capability policy

Start with a small local capability map loaded from configuration or code defaults. Do not infer capabilities from a model name at runtime unless 9Router exposes trustworthy metadata and that behavior is verified.

Rules:

- Reject a vision request when no configured vision-capable alias exists.
- Do not send tool calls until the selected model and endpoint are verified to support them.
- Enforce a conservative input-size estimate before choosing a fallback with lower context capacity.
- Parse and validate structured extraction locally; one repair attempt is acceptable, then fail with a typed error.
- For video learning, keep the existing transcript fallback. Do not send video to an OpenAI-compatible endpoint until its media format is verified.

## Error model

Map transport/provider failures into a few stable exceptions:

- `LLMConfigurationError`
- `LLMAuthenticationError`
- `LLMRateLimitError`
- `LLMTimeoutError`
- `LLMCapabilityError`
- `LLMResponseError`
- `LLMUnavailableError`

Business workflows should handle these errors, not HTTP status codes or provider SDK exceptions.

## Retry and fallback

- Retry only transient timeout, 429, and selected 5xx failures.
- Default to one retry with short bounded backoff.
- Never retry authentication, invalid request, capability mismatch, or schema validation indefinitely.
- Let 9Router perform provider fallback only after confirming how its installed version behaves.
- Hermes may perform model-alias fallback only when the fallback capability contract satisfies the request.
- Direct Gemini fallback remains disabled by default and explicit when enabled.

## Logging

Emit one structured event per call with:

- task type;
- requested alias/model;
- actual model/provider when returned;
- duration;
- retry count;
- success/failure category;
- correlation/job ID when supplied.

Never log:

- API keys or authorization headers;
- API keys embedded in query strings;
- full prompts, transcripts, documents, or model responses;
- Telegram tokens or private attachment URLs.

Safe prompt logging may include character count and a non-reversible hash.

## Required 9Router verification

Before enabling the adapter, start the actual local 9Router service and verify:

1. Base URL and API version prefix.
2. Authentication header requirements.
3. `GET /v1/models` availability and response shape.
4. `POST /v1/chat/completions` request and non-streaming response shape.
5. Whether `/v1/responses` exists or is required.
6. Model alias names accepted by the installed instance.
7. Timeout, 401/403, 404, 429, and 5xx response bodies.
8. Whether the response reports actual model/provider after fallback.
9. Vision message format and supported media types, if any.
10. Tool-call and JSON-mode support, if any.
11. Context limits or capability metadata, if exposed.
12. Whether router fallback is configured server-side and how failures are surfaced.

Latest result: port `20128` is open. `GET /api/health` returns `{"ok": true}`.
`GET /v1/models` returns the active model catalog. Non-streaming
`POST /v1/chat/completions` returned `OK` for `kr/qwen3-coder-next`.
OpenCode also returned `OK` through `nine-router/kr/qwen3-coder-next`.
Endpoint details for multimodal, tool-call, JSON-mode, and router fallback
remain **NOT VERIFIED**.

## Migration sequence

### Change 1: gateway foundation

- Add config, typed request/result objects, errors, routing, and mocked tests.
- Implement OpenAI-compatible non-streaming chat completions.
- Implement temporary direct Gemini text adapter using existing credentials/config.
- Do not modify video analysis.

### Change 2: first consumer

- Change `core/job_watcher.py` text calls from `ai_chat()` to the gateway.
- Map existing `analysis`, `script`, and `ideas` calls to the new task categories.
- Preserve current prompt construction and output behavior.
- Keep `core.ai_router.chat()` as a compatibility wrapper or leave it untouched for remaining consumers.

### Change 3: verified 9Router enablement

- Run the endpoint verification checklist.
- Populate local environment model aliases.
- Add a configuration/health-check command that reports availability without revealing secrets.
- Run mocked tests plus one explicit opt-in local smoke call.

### Later consumer migration

Migrate one module at a time in this order:

1. Telegram text chat commands.
2. `core/script_generator.py` and `core/storyboard_generator.py`.
3. Idea, keyword, and project helpers.
4. GUI prompt compiler.
5. Multimodal video analyzer only after the 9Router media contract is verified.

Delete direct provider code only after all consumers and tests have moved. Do not combine migration with prompt or workflow redesign.

## Phase 1 test matrix

| Test | Expected behavior |
| --- | --- |
| Missing base URL/model | Raises `LLMConfigurationError` before HTTP. |
| OpenAI-compatible success | Parses text and optional actual model/usage. |
| Authentication failure | Maps 401/403 without retry. |
| Timeout | Retries within configured bound, then raises `LLMTimeoutError`. |
| Rate limit | Performs bounded retry and maps final failure. |
| Capability mismatch | Fails before network call. |
| Task routing | Selects the environment-configured alias for each task. |
| Structured JSON success | Validates expected schema. |
| Structured JSON invalid | One bounded repair attempt or typed response failure. |
| Logging redaction | Does not contain API key, authorization header, or full prompt. |
| Gemini compatibility | Existing text behavior remains available when explicitly configured. |

Use mocked HTTP responses. Live 9Router and Gemini calls should be opt-in smoke tests, not default tests.

## Smallest safe Phase 1 change

Create the gateway package and migrate only the eight `ai_chat()` calls in `core/job_watcher.py`. Add focused unit tests and keep every prompt, learning artifact, Telegram response, and video-analysis path unchanged.

This creates the correct model boundary where it matters most without forcing a risky repo-wide migration or pretending the unavailable 9Router endpoint has already been verified.
