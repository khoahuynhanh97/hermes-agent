# Three Product Video Quality Review

**Date:** 2026-09-17  
**Artifacts:** Baseus Bowie WM02, Ugreen Uno Robot GaN 65W, Tribit XSound Go  
**Verdict:** 2 reject, 1 scene-level retry; none are publish-ready

## Product Findings

| Product | Verdict | Main failures |
| --- | --- | --- |
| Baseus Bowie WM02 | Reject | Earbud/case geometry changes between scenes; stemmed earbuds replace the compact WM02 form; transparent capsule becomes a generic opaque square case; source collage and text appear at scene starts. |
| Ugreen Uno Robot 65W | Reject | Cable is inserted into the front face below the display although the verified USB ports are on top; display/body geometry changes; multiple color variants and marketing text remain visible. |
| Tribit XSound Go | Retry scenes 3-4 | Best identity retention of the batch, but the water interaction deforms/partially duplicates the speaker, logo fidelity drifts, and every scene resets from a white-background reference. |

All three outputs are 16.0s, 720x1280, H.264, 24fps, with no audio. Most clips contain 280 black rows at both the top and bottom, leaving only a 720x720 active square image. A technically vertical file is therefore not a visually valid 9:16 composition.

## Critical Workflow Findings

### P0: Image QC is fabricated after failure

The batch script replaces a failed or insufficient Image QC result with a synthetic
95-point PASS and marks every cleaned image eligible. This converts detector/parser
failure into authorization and explains why collages, mixed variants, remaining text,
and damaged references enter generation.

Required change: never manufacture an eligible manifest. Fewer than two truthful,
distinct eligible references must block Product Lock and trigger reacquisition.

### P0: The storyboard, keyframe, and QC gates are skipped

The script sends a cleaned listing image directly to Veo. It does not generate
scene-specific keyframes, run Keyframe QC, approve Gate 4, or run Video QC. Export only
checks decodability and dimensions.

Required change: route every production run through the canonical governed workflow:

`references -> Image QC -> script -> storyboard -> generated keyframe -> Keyframe QC -> video -> Video QC -> export`

### P0: One weak hero image conditions every scene

`clean_results[0]` is used for all scenes, ignoring scene `reference_asset_ids`, viewing
angle, visible details, and selected keyframes. For Baseus and Ugreen, that first asset is
a multi-panel or multi-variant marketing collage.

Required change: reject collages and multi-variant frames, lock one SKU/color per video,
and use the approved scene-specific keyframe as the sole video start state.

### P0: Precision interactions have no geometry contract

The video prompt includes only objective, subject action, and placement. It omits the
scene's start/end state, exact contact landmark, trajectory, orientation, required
visible details, and immutable product geometry. Veo therefore invents where the cable
connects.

For high-risk actions such as inserting a cable, placing an earbud into a cradle, or
pressing a small control, require:

- a reference that clearly exposes the target port/cradle/control;
- `interaction_target`, `contact_landmark`, `approach_vector`, and `end_state`;
- start and end keyframes with matching product pose;
- QC that verifies contact occurs at the approved landmark;
- a simpler cut to an already-connected state when no reliable reference exists.

### P1: Script duration and scene plan are discarded

The generated scripts contain 5-6 scenes and 24-28 seconds, but the script slices the
first four scenes and forces every clip to four seconds. The resulting 16-second export
does not represent the approved narrative or duration.

Required change: render every approved scene with its declared 4/6/8-second duration and
verify final duration against the script digest.

### P1: Research and claim provenance are not trustworthy

Claims are hard-coded as `verified`, and source URLs are synthesized from
`official.<brand>.com/<model>`. These are not evidence records.

Required change: only pass claims and URLs persisted by Product Intelligence with real
evidence references. Unsupported claims must block the scene, not be rewritten as verified.

### P1: Presentation QC checks file shape, not active composition

The compositor produces a 720x1280 container while the generated content remains square
and letterboxed. No black-bar or active-image-area check exists.

Required change: Video QC must reject persistent borders above 2% per edge, validate
subject framing inside a true 9:16 active region, and reject raw reference flashes at
scene boundaries.

## Product-Specific Recovery

### Baseus

1. Choose one exact color variant and reject references containing other colors/models.
2. Acquire clean front, open-case, earbud-detail, and in-ear references for that variant.
3. Lock stemless earbud silhouette, transparent capsule lid, cradle geometry, LED arc,
   and logo placement in every keyframe.
4. Regenerate all four clips; the current product identity is not recoverable by editing.

### Ugreen

1. Use the single-product top-angle reference showing the two USB-C and one USB-A ports.
2. Replace the direct insertion shot with a macro start/end keyframe pair targeting one
   exact top USB-C port.
3. Lock display shape, front face, side button, magnetic feet, port count, and body color.
4. Reject any frame where a cable enters the screen/front face or where accessories
   resemble earbuds.

### Tribit

1. Keep the clean single-product reference and lock the pill silhouette and grille logo.
2. Retry the water scene with exactly one stationary speaker; animate water around it
   instead of asking the product to cross the water surface.
3. Remove the white-background reset at each cut and regenerate a full 9:16 composition.

## Acceptance Contract

- No fabricated QC result or manual eligibility override.
- Exactly one approved product variant and expected object count in every sampled frame.
- Product silhouette, color, material, logo/control/port placement remain stable.
- Precision interaction reaches the declared contact landmark and valid end state.
- No collage, seller text, source image flash, duplicate object, or unrelated accessory.
- Active content fills 9:16 with no persistent edge above 2% black-bar coverage.
- Rendered scene count and total duration match the approved script/package digest.
- Every keyframe and video clip has a fresh QC PASS bound to its bytes.

