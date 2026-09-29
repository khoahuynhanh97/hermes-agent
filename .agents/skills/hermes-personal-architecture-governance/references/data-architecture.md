# Data and Artifact Architecture Rules

These rules govern Product Video metadata, JSON, source images, cleaned images,
keyframes, storyboards, clips, composites, QC evidence, and final exports.

## Sources of Truth

Use each store for one job:

- SQLite is authoritative for identity, ownership, workflow state, versions,
  approvals, budgets, idempotency, provider operations, artifact metadata, lineage,
  and QC records.
- The canonical workspace is authoritative for immutable artifact bytes and
  versioned manifests referenced by SQLite.
- `config.yaml` owns non-secret paths and behavior. `.env` owns credentials only.
- External exchange folders are ingestion sources, not durable Product Video state.
- In-memory objects, UI state, logs, caches, reports, and temporary folders are not
  production sources of truth.

Database rows and files form one logical record: a file without registered lineage
is orphaned, and a row whose bytes or SHA-256 do not match is invalid.

## Canonical Lifecycle

Keep this dependency chain explicit and forward-only:

`candidate -> research snapshot -> locked resource pack -> research dossier -> approved brief -> approved scene plan -> storyboard spec -> generated keyframes -> keyframe QC -> approved storyboard -> scene clips -> composite -> video QC -> final approval -> immutable export`

Each downstream artifact records stable parent artifact IDs and input digests.
Changing an upstream approved artifact creates a new version and invalidates or
supersedes dependent approvals and render plans. Never mutate history in place.

## Canonical Workspace

Resolve every path through
`hermes_personal.product_video.storage.layout.ProductVideoWorkspaceLayout`.
Do not hand-build a competing root or directory tree.

```text
<workspace>/
  projects/<project_id>/
    project-manifest.json
    assets/
      references/<sha256>.<ext>
      cleaned/<sha256>.png
    creative/v<version>/
    storyboard/v<version>/
      storyboard-manifest.json
      scenes/scene-001/
        scene.json
        image-prompt.json
        video-prompt.json
        references.json
        keyframes/attempt-001/start.png
        keyframes/attempt-001/end.png
        qc/keyframe-report.json
    renders/v<version>/
      render-batch.json
      scenes/scene-001/attempt-001/
        clip.mp4
        clip-manifest.json
        technical-probe.json
      composite/
        draft.mp4
        timeline.json
        technical-probe.json
        video-qc-report.json
  exports/export_<project_id>_<version>/
    final.mp4
    caption.txt
    metadata.json
    keyframes/
    qc/
```

Persist paths as workspace-relative POSIX strings from `to_relative_path()`. Resolve
them through `resolve_path()`. Reject absolute persisted paths, `..`, drive escapes,
and sources outside configured exchange roots.

## Artifact Identity and Registration

Every durable binary or manifest needs a registered artifact record containing at
least the fields applicable to its kind:

- `artifact_id`, `owner_user_id`, `project_id`, `kind`;
- `scene_id` and `frame_role` when scene/frame scoped;
- positive `version` and `attempt`;
- workspace-relative `relative_path`;
- canonical SHA-256, byte size, and MIME type;
- lifecycle status and creation timestamp;
- parent artifact IDs and input/content digests;
- prompt/model/provider version for generated media;
- bound QC report and approval identity where required.

IDs identify logical records. SHA-256 identifies exact bytes. Versions identify
approved evolution. Do not use a filename, URL, provider operation ID, or database
row number as a substitute for all three.

## JSON and Manifest Rules

- Use typed canonical contracts; JSON is their serialized form, not an alternative
  domain model.
- Include `schema_version` in persisted/exchanged documents and reject unsupported
  versions.
- Use stable IDs and references instead of embedding duplicate objects or base64
  media blobs.
- Store timestamps in UTC ISO 8601 and serialize deterministically when a digest is
  computed.
- Record input IDs/digests, output digest, prompt version, configured model,
  provider operation ID, QC binding, and approval binding as applicable.
- Keep provider-only payloads in adapter-owned records. Do not leak them into
  canonical manifests.
- Validate the complete document before persistence. Malformed or semantically
  inconsistent output fails closed.
- Write with same-filesystem staging and `os.replace`; never expose partial JSON.

Do not invent ad hoc JSON files in report, source, repository root, or UI folders.
Add a canonical contract and layout method first when a genuinely new artifact kind
is approved.

## Images, References, and Keyframes

- Ingest external images before Product Lock into content-addressed
  `assets/references/<sha256>.<ext>` storage.
- Verify decodability, containment, size, MIME/extension, and SHA-256 on ingestion
  and before use.
- Preserve originals. Cleaning creates a new content-addressed artifact and lineage;
  it never overwrites the reference.
- Scene references use eligible `asset_id` values selected from approved Image QC.
- Generated keyframes live under a scene and attempt. Failed attempts remain
  traceable and cannot be relabeled as approved.
- A keyframe approval/QC report binds exact keyframe bytes, approved references,
  scene version, and prompt/input digest.
- Video rendering consumes only generated, QC-passed, approved keyframes. It never
  renders directly from a seller/listing image.

## Storyboards and Scene Data

- Scene IDs are stable within a storyboard version; order is unique and contiguous.
- `scene.json` owns canonical scene intent and duration.
- `image-prompt.json` and `video-prompt.json` are separate versioned generated
  contracts; `references.json` contains IDs/digests, not copied image bytes.
- `storyboard-manifest.json` enumerates every scene, exact artifact reference,
  version, digest, QC result, and approval dependency.
- Overlay text belongs to composition. Generated keyframes and clips must not embed
  captions, prices, marketplace UI, watermarks, or seller branding.
- Any scene, prompt, keyframe, reference, order, or duration change creates a new
  storyboard version and requires the affected QC/approval chain again.

## Clips, Composite, and Final Export

- Persist an accepted provider operation ID before polling or continuing to the next
  scene. Resume accepted operations; never resubmit them blindly.
- Each clip attempt has its own bytes, digest, technical probe, request lineage, and
  status. Retries do not overwrite previous attempts.
- The composite timeline references exact ordered clip artifact IDs/digests.
- MVP composition is 720x1280, H.264, `yuv420p`, 24 FPS. Reject incompatible input
  fail-closed; do not use non-uniform stretching.
- Video QC must bind to the exact composite SHA-256 and cover every approved scene.
- Final approval binds artifact ID, version, and digest.
- Export creates a new immutable versioned directory. Never overwrite or edit an
  existing export package.
- `metadata.json` records source/parent IDs and digests, approvals, prompt/model
  versions, provider operations, technical probes, QC, and spend. `caption.txt` is
  plain publishing copy; `final.mp4` is the approved composite byte lineage.
- Manual publishing is outside the export data model unless separately approved.

## Cleanup and Retention

Cleanup is reachability-based. It may remove only temporary files and unreferenced
failed/superseded artifacts after checking SQLite lineage. It must preserve:

- source and ingested reference assets;
- current or historical approved artifacts;
- QC and approval evidence;
- artifacts referenced by active workflows, batches, timelines, or exports;
- provider operation records and spend evidence;
- every immutable export directory.

Never infer deletability from age, filename, folder name, or UI visibility alone.

## Review Checklist

Before accepting a data change, verify:

- one canonical owner and schema version exist;
- SQLite and filesystem responsibilities are explicit;
- paths are relative, contained, and resolved by the canonical layout;
- writes are atomic and outputs are immutable/versioned;
- IDs, parents, hashes, QC, approvals, and provider operations form complete lineage;
- retry, resume, crash recovery, and duplicate delivery are deterministic;
- all five HITL gates still block the corresponding transition;
- cleanup cannot reach source, approved, active, or exported artifacts;
- tests corrupt or restart the real boundary instead of only mocking it.
