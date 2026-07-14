# Learning JSON Reanalysis Design

## Goal

Keep the current Telegram learning workflow unchanged while making malformed
knowledge JSON recoverable from `/knowledge pending`.

## Scope

This change applies only when source analysis exists but Hermes cannot produce a
valid knowledge JSON object after:

1. the initial structured extraction call; and
2. the existing bounded normalization call.

Download-only failures, `needs_source` entries, and valid pending lessons do not
show `/re_analysis`.

## Data Flow

When both JSON attempts fail, the worker creates one pending placeholder entry
instead of returning only a recoverable job marker. The entry stores:

- the source URL and platform;
- the original job ID and output directory;
- the raw source-bound analysis;
- `needs_reanalysis: true`;
- the latest validation error;
- `reanalysis_count`, initially zero.

The placeholder summary states that structured extraction failed. It must not
invent a lesson from unavailable evidence.

`/knowledge pending` renders `/re_analysis <knowledge_id>` only when the entry
has `needs_reanalysis: true`. Existing approve/reject actions remain unchanged.

## Reanalysis Command

`/re_analysis <knowledge_id>`:

- requires the same Telegram owner as the knowledge entry;
- rejects valid lessons that do not need reanalysis;
- creates one new learning job from the stored source and raw analysis;
- bypasses normal source deduplication for this explicit manual action;
- records the target knowledge ID on the new job.

On success, the worker updates the same knowledge entry with validated fields,
sets `needs_reanalysis: false`, and leaves it pending for approval. It does not
create a duplicate entry.

On failure, the worker keeps the same pending placeholder, increments
`reanalysis_count`, records the latest error, and leaves `/re_analysis` visible.
There is no automatic or infinite retry loop.

## Existing Media Fallback

The current media fallback order remains in place: TikTok media resolver,
video download, transcript/audio, metadata, then an honest `needs_source`
result. This feature does not claim that metadata-only analysis is equivalent
to video or image analysis.

## Testing

Tests cover:

- placeholder creation only after two JSON failures;
- no `/re_analysis` action for valid or `needs_source` entries;
- owner authorization;
- job creation with a target knowledge ID;
- same-ID update after successful reanalysis;
- retained placeholder and incremented counter after another failure.
