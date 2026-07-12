---
name: seedance-product-review-generator
description: >
  Tạo kịch bản, prompt ảnh AI, prompt video AI và voice script cho video review sản phẩm bằng
  Seedance 2.0 + Nano Banana Pro + ElevenLabs. LUÔN dùng khi user upload ảnh sản phẩm + ảnh KOC
  và yêu cầu tạo video review, hoặc nhắc đến: "video review sản phẩm", "prompt Seedance review",
  "kịch bản video AI review", "TikTok/Shorts review", "review đồ ăn/thời trang/mỹ phẩm/công nghệ
  bằng AI", "video quảng cáo AI", "voiceover review", "lip sync review", "KOC nói theo audio",
  "khớp khẩu hình". Hỗ trợ 2 mode: VOICEOVER (giọng ngoài hình, KOC chỉ tương tác sản phẩm) và
  LIP-SYNC (KOC nói trực tiếp khớp khẩu hình theo audio ElevenLabs). Quy trình DBS 3 tầng:
  DIRECTION (phân tích + chọn mode) → BLUEPRINT (storyboard 5-act) → SOLUTIONS (prompt Nano
  Banana Pro, Seedance 2.0, voice script ElevenLabs tiếng Việt).
---

# Seedance Product Review Generator

Skill tạo trọn gói tài liệu sản xuất 1 video review sản phẩm bằng pipeline AI:
**Nano Banana Pro** (keyframe ảnh) → **Seedance 2.0** (image-to-video) → **ElevenLabs** (voiceover/lip-sync).

Áp dụng **DBS Framework** 3 tầng — Direction · Blueprint · Solutions — để mỗi output đều có lý do và kết nối logic với nhau, không bị rời rạc.

---

## 2 MODE HOẠT ĐỘNG

Skill hỗ trợ 2 mode cho voice. Khi user chưa nêu rõ mode, **hỏi user chọn mode ngay đầu Stage 1** bằng một câu hỏi ngắn gọn.

### MODE A — VOICEOVER (giọng ngoài hình)

```
KOC KHÔNG nói trên hình → chỉ tương tác với sản phẩm (cầm, mặc, cắn, thử...)
Voice là voiceover ngoài hình → ElevenLabs gen 1 file audio dài liền mạch
Seedance prompt: KHÔNG có dialogue, KHÔNG có lip-sync
  → prompt chỉ tả action + camera + atmosphere + audio SFX (ambient)
Pipeline ghép cuối: video + voiceover overlay trong CapCut/Premiere
```

**Ưu điểm**: Dễ hơn, ít lỗi, không phụ thuộc lip-sync accuracy
**Phù hợp**: Food ASMR, product close-up heavy, sản phẩm chủ đạo hơn KOC

### MODE B — LIP-SYNC (KOC nói trực tiếp)

```
KOC NÓI trực tiếp trên hình → miệng chuyển động khớp audio
Voice: ElevenLabs gen TỪNG SHOT RIÊNG (mỗi shot = 1 file audio)
Seedance prompt: CÓ dialogue transcript + audio reference (@Audio)
  → prompt tả action + dialogue text trong ngoặc kép + lip sync to @Audio
Pipeline: upload keyframe + audio vào Seedance → gen lip-sync per shot → ghép
```

**Ưu điểm**: Chân thật hơn, KOC sống động, engagement cao hơn trên TikTok/Reels
**Phù hợp**: Fashion try-on, skincare routine, lifestyle review, KOC-centric

### Bảng so sánh nhanh

```
                    MODE A — VOICEOVER              MODE B — LIP-SYNC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ElevenLabs output   1 file liền mạch                 N file riêng (1/shot)
ElevenLabs pace     Tự nhiên ~3-4 từ/s               Chậm ~80% (~2.5-3 từ/s)
Seedance upload     @Image1 only                     @Image1 + @Audio1
Seedance prompt     Action + camera + SFX            Action + dialogue + @Audio
                    KHÔNG dialogue ngoặc kép          CÓ transcript ngoặc kép
Seedance duration   Tự do (3-5s)                     PHẢI khớp audio duration
Ghép cuối           Video + voiceover overlay         Ghép N clip lip-synced
Nano Banana Pro     Giống nhau — Master Shot Workflow không đổi
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Pipeline tổng quan

```
[Ảnh sản phẩm] + [Ảnh KOC] + [Chọn Mode A/B]
        │
        ▼
┌─ DIRECTION ─────────────────────────────────────────┐
│ Phân tích sản phẩm + KOC → category + persona       │
│ Hỏi: Mode A (Voiceover) hay Mode B (Lip-sync)?      │
│ Hỏi thông số còn thiếu (thời lượng / angle / tone)  │
│ Output: Brief định hướng (ghi rõ mode)               │
└──────────────────┬──────────────────────────────────┘
                   ▼
┌─ BLUEPRINT ─────────────────────────────────────────┐
│ Template review 5-act theo category                  │
│ Chia shot theo thời lượng (mỗi shot 3–5s)           │
│ Mode B: ghi rõ shot nào có dialogue + face direction │
│ Output: Storyboard format theo mode                  │
└──────────────────┬──────────────────────────────────┘
                   ▼
┌─ SOLUTIONS ─────────────────────────────────────────┐
│ 3.1 Nano Banana Pro — giống nhau cả 2 mode          │
│ 3.2 Seedance 2.0 — format prompt theo mode A/B      │
│ 3.3 ElevenLabs — 1 file (A) hoặc N file (B)         │
└─────────────────────────────────────────────────────┘
```

---

## STAGE 1 — DIRECTION

### 1.1 Phân loại sản phẩm

| Category | Nhận biết | Demo beat đặc thù |
|----------|-----------|-------------------|
| **Food / Beverage** | Đồ ăn, thức uống | Cận miệng cắn, ASMR sizzle/crunch, đổ rót |
| **Fashion** | Trang phục, phụ kiện, túi, giày | Mặc thử, xoay người, cận chất liệu, walking shot |
| **Cosmetics / Skincare** | Mỹ phẩm, son, serum | Swatch tay, glide application, texture close-up |
| **Tech / Gadget** | Điện thoại, tai nghe | Unbox, hands-on, click/swipe, comparison |
| **Home / Decor** | Đồ gia dụng, decor | Setup, in-context use, lifestyle wide shot |
| **Health / Supplement** | TPCN, vitamin | Routine moment, ingredient highlight |
| **Lifestyle / Other** | Sách, đồ chơi | Open box, in-use moment, hand interaction |

### 1.2 Phân tích ảnh KOC

```
- Gender + age range
- Vibe: cute / mature / professional / cool / soft / energetic
- Style: gen Z / millennial / influencer / down-to-earth
- Đặc điểm thị giác: tóc, da, mắt, dáng
```

### 1.3 Hỏi user: Chọn Mode + Thông số

Hỏi trực tiếp bằng câu hỏi ngắn gọn. Nếu môi trường có công cụ hỏi input dạng lựa chọn thì có thể dùng, nhưng **chỉ hỏi cái user chưa nêu**.

**Câu hỏi MODE — BẮT BUỘC hỏi (trừ khi user đã nêu rõ):**

```
question: "KOC sẽ nói như thế nào trong video?"
options:
  - "🎙️ Voiceover (giọng ngoài hình, KOC chỉ tương tác sản phẩm)"
  - "👄 Lip-sync (KOC nói trực tiếp, khẩu hình khớp audio)"
```

> **Gợi ý nếu user phân vân:**
> - Food/ASMR/Product close-up → Voiceover
> - Fashion try-on/Skincare/Lifestyle → Lip-sync
> - Tech → tuỳ: voiceover nếu focus demo, lip-sync nếu focus reaction

**Thông số còn lại (gộp cùng lúc, max 3 câu tổng):**

| Thông số | Options |
|----------|---------|
| **Thời lượng** | 10s · 15s · 30s · custom |
| **Angle review** | USP · So sánh · Trải nghiệm cá nhân · Lifestyle |
| **Tone voice** | Chuyên nghiệp · Thân mật · Nhiệt tình |
| **CTA cuối** | Mua ngay · Tham khảo · Comment · Không CTA |

### 1.3.1 Reference Scene — LUÔN hỏi/tư vấn

Sau khi nhận ảnh sản phẩm + KOC, agent PHẢI đề cập reference scene:

- **Chưa có ref**: tư vấn user upload ảnh bối cảnh (bàn ăn, phòng, góc setup)
- **Đã có ref**: confirm và ghi nhận
- **Không upload**: agent tả background bằng chi tiết kiến trúc cụ thể (xem 3.1.1)

### 1.4 Output — Brief định hướng

```
🎯 BRIEF ĐỊNH HƯỚNG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sản phẩm    : [tên / mô tả]
Category    : [food / fashion / ...]
KOC         : [persona tóm tắt]
Mode        : [🎙️ VOICEOVER / 👄 LIP-SYNC]
Thời lượng  : [Xs] · Aspect: [9:16]
Angle       : [USP / lifestyle / ...]
Tone        : [thân mật / chuyên nghiệp / ...]
Vibe words  : [3-5 từ khoá]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## STAGE 2 — BLUEPRINT

### 2.1 Scale shot theo thời lượng

| Thời lượng | Số shot | Phân bổ act |
|------------|---------|-------------|
| **10s** | 3 shots | HOOK → DEMO (gộp) → VERDICT/CTA |
| **15s** | 4-5 shots | HOOK → CONTEXT → DEMO (1-2) → VERDICT/CTA |
| **30s** | 6-7 shots | HOOK → CONTEXT → DEMO×2-3 → VERDICT → CTA |
| **45s+** | 8-10 shots | Mở rộng DEMO, thêm lifestyle shot |

### 2.2 Storyboard format theo mode

**MODE A (Voiceover):**

```
SHOT N (mm:ss-mm:ss) — [ACT]
• Mục đích    : [why]
• Nội dung    : [KOC làm gì — KHÔNG nói]
• Framing     : [close-up / medium / wide]
• Mood        : [cảm xúc]
• Sensory beat: [ASMR / motion / texture]
• VO line     : [câu voiceover]
```

**MODE B (Lip-sync):**

```
SHOT N (mm:ss-mm:ss) — [ACT]
• Mục đích    : [why]
• Nội dung    : [KOC làm gì + NÓI gì]
• Dialogue    : "[câu nói chính xác]" (N từ, ~Xs)
• Face dir.   : [front / 3/4 / nhìn sản phẩm]
• Framing     : [medium/close-up — PHẢI thấy miệng]
• Mood        : [cảm xúc]

⚠️ LIP-SYNC FRAMING RULES:
- Shot có dialogue → framing PHẢI thấy miệng rõ
- Face direction: front-facing hoặc 3/4 → accuracy tốt nhất
- Shot close-up sản phẩm → KHÔNG gán dialogue, để silent
```

---

## STAGE 3 — SOLUTIONS

### 3.1 Prompt Nano Banana Pro — GIỐNG NHAU CẢ 2 MODE

Master Shot Workflow: Gen Shot 1 trước → dùng làm anchor cho shot sau.

```
SHOT 1 (Master) = [Ảnh KOC] + [Ảnh sản phẩm] + (optional) [Ảnh ref scene]
SHOT 2…N        = [Ảnh KOC] + [Ảnh sản phẩm] + [Ảnh Shot 1 đã gen]
```

**Weight chuẩn:**

| Shot | KOC | Sản phẩm | Ref scene | Master |
|------|-----|----------|-----------|--------|
| Master (có ref) | 0.85 | 0.95 | 0.70 | — |
| Master (không ref) | 0.85 | 0.95 | — | — |
| Shot 2+ (có người) | 0.85 | 0.85 | — | 0.85 |
| Pack-shot (không người) | — | 0.95 | — | 0.85 |

**Shot 2+ KHÔNG mô tả lại bối cảnh** — chỉ dùng:
`in the same scene as reference, matching background and lighting exactly`

**Template prompt:**

```
[SHOT 1 — MASTER]
A [persona KOC], [ACTION],
preserve product label exactly as reference, do not redraw text,
[SETTING: 2-3 chi tiết kiến trúc cụ thể],
[LIGHTING: 1 nhiệt màu duy nhất — 3200K/4000K/5500K],
shot on [camera body] with [lens] at [aperture], ISO 400,
natural skin texture, pores visible, no beauty filter,
9:16 vertical, casual realism
```

#### 3.1.1 Chống AI-look — 5 nguyên tắc

1. **Color discipline**: 1 nhiệt màu duy nhất (Kelvin), thêm `"skin remains natural pink not yellow"`
2. **Preserve label**: KHÔNG describe text trên packaging → dùng `preserve exactly as reference`
3. **Background cụ thể**: 2-3 chi tiết kiến trúc thật (vật liệu tường + nguồn sáng + props)
4. **Camera spec**: tên camera body thật (Fujifilm X-T5 / Sony A7 IV / Canon R6) thay vì "photorealistic"
5. **Skin texture**: `natural pores, no beauty filter` thay vì `smooth flawless skin`

#### 3.1.2 Negative prompt base

```
deformed hands, extra fingers, blurry face, plastic skin, beauty filter,
CGI character, 3D render, yellow skin, jaundice tone, oversaturated,
fake background, studio shoot, retouched, misspelled diacritics,
[Shot 2+:] different background, scene change, lighting shift, different face
```

#### 3.1.3 Output format — 1 ô copy-paste

````
**SHOT N — [TÊN] (gen thứ N)**
Refs: [KOC] + [Product] + [Master nếu có]

```
@KOC AI :0.85 @Product 01 :0.95 [@Scene Ref :0.70] [@Master :0.85]

[prompt liền 1 đoạn]

---NEGATIVE---
[negative liền 1 đoạn]
```
````

---

### 3.2 Prompt Seedance 2.0 — KHÁC NHAU THEO MODE

#### ═══ MODE A — VOICEOVER ═══

**Setup Seedance:**
```
Upload: @Image1 = keyframe
Duration: 3-5s (tự do)
Audio: ON (gen SFX + ambient)
```

**Template:**
```
@Image1 as the first frame

[00:00-00:XX] [Framing], [subject],
[SUBJECT MOTION: action cụ thể — KHÔNG dialogue],
[CAMERA MOTION: push in / static / pan / orbit],
[ATMOSPHERIC: steam / particles / fabric / none],
Sound: [SFX cụ thể — sizzle, rustle, crunch, room tone],
[STYLE: slow-mo % / natural pace, photoreal]
```

**Lưu ý đặc thù theo category (Mode A):**
- **Food**: audio cue ASMR (crunch, sizzle, pour), slow-mo trên cắn/đổ
- **Fashion**: fabric motion (twirl, walk), ambient + fabric rustle
- **Cosmetics**: glide motion, static/slow push-in camera
- **Tech**: precise hand motion, click/swipe sound, rack focus

#### ═══ MODE B — LIP-SYNC ═══

**Setup Seedance:**
```
Upload: @Image1 = keyframe, @Audio1 = audio file cho shot
Duration: PHẢI = audio duration (audio 3.5s → video 3.5s)
Audio: ON
```

**Template:**
```
@Image1 as the first frame, lip sync to @Audio1

[00:00-00:XX] [Framing — PHẢI thấy miệng],
[subject], she speaks [emotional cue] to camera:
"[TRANSCRIPT CHÍNH XÁC từ voice script]"
Mouth movements clearly synced to Vietnamese audio,
[ADDITIONAL ACTION: head tilt, hand gesture],
[CAMERA MOTION: static hoặc rất slow — tránh motion mạnh],
Sound: clear female Vietnamese voice prominent, [ambient nhẹ],
[STYLE: natural pace, photoreal]
```

**8 quy tắc lip-sync Mode B:**

1. **LUÔN ghi transcript ngoặc kép** — tip quan trọng nhất
2. **Duration video = duration audio** — lệch → model stretch → mất sync
3. **Framing thấy miệng** — không extreme close-up tay cho shot có dialogue
4. **Face front/3/4** — lip-sync accuracy tốt nhất
5. **Camera motion nhẹ** — tránh orbit/pan nhanh khi có dialogue
6. **Câu ngắn 5-10 từ** — >8s liên tục → mushy lip-sync
7. **Emotional cue trước dialogue** — "speaks warmly" > "says"
8. **Shot close-up sản phẩm** → silent, chỉ SFX

**Troubleshooting lip-sync:**

| Vấn đề | Giải pháp |
|--------|-----------|
| Lệch timing | Duration video ≠ audio → set = nhau |
| Sai từ | Thêm transcript chính xác trong prompt |
| Drift cuối | Cắt câu <8s, thêm pause |
| Miệng ít hoạt động | Face quá nghiêng → đổi front/3/4 |
| Re-gen 3 lần vẫn lỗi | Chuyển shot sang voiceover (hybrid) |

---

### 3.3 Voice Script ElevenLabs — KHÁC NHAU THEO MODE

#### ═══ MODE A — VOICEOVER ═══

- 1 file audio liền, pace markers: `[pause]` 0.3s, `[long pause]` 0.7s
- Pace: ~3-4 từ/s · Shot 3s ≈ 8-12 từ · Shot 5s ≈ 14-18 từ
- Tone: first-person tự nhiên, xen 1-2 từ Anh (max 1/10 từ Việt)

**Output format:**
```
🎙️ VOICE SCRIPT — VOICEOVER

▸ BẢN PASTE (1 file ElevenLabs):
"[script liền + pace markers]"

▸ MAP TIMING:
SHOT 1 (00:00-00:03) │ "[câu]" (N từ)
SHOT 2 (00:03-00:07) │ "[câu]" (N từ)
...
TỔNG: XX từ / Xs = X.X từ/s ✓ (target 3-4)
```

#### ═══ MODE B — LIP-SYNC ═══

- N file audio RIÊNG (1/shot) — KHÔNG thu 1 file rồi cắt
- Pace: chậm hơn ~80% (~2.5-3 từ/s)
- Thu DRY (không reverb), phát âm rõ, micro-pause giữa cụm từ
- Mỗi file có ~0.3s silence đầu và cuối

**Output format:**
```
🎙️ VOICE SCRIPT — LIP-SYNC

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUDIO FILE 1 — SHOT 1 (target: X.Xs)
"[câu nói]"
→ N từ · ~X.X từ/s · [emotional direction]
→ File: shot1_hook.mp3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUDIO FILE 2 — SHOT 2 (target: Xs)
"[câu nói]"
→ N từ · ~X.X từ/s · [emotional direction]
→ File: shot2_context.mp3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
...
TỔNG: XX từ / Xs = X.X từ/s ✓ (target 2.5-3)

⚠️ Duration mỗi audio PHẢI = target shot duration
```

---

## TECHNICAL CHECKLIST theo mode

**MODE A — VOICEOVER:**
```
- [ ] Gen Master Shot → lưu anchor
- [ ] Gen Shot 2…N với Master @ 0.85
- [ ] Scene Ref @ 0.70 (nếu có)
- [ ] Render 1 file voice ElevenLabs
- [ ] Đưa keyframe vào Seedance (KHÔNG upload audio)
- [ ] Ghép video + voiceover overlay (CapCut/Premiere)
- [ ] Fade-in voice shot 1, fade-out shot cuối
- [ ] Nhạc nền ~15-20% volume
```

**MODE B — LIP-SYNC:**
```
- [ ] Gen Master Shot → lưu anchor
- [ ] Gen Shot 2…N với Master @ 0.85
- [ ] Scene Ref @ 0.70 (nếu có)
- [ ] Thu N file audio ElevenLabs (1/shot)
- [ ] Check: duration audio = target shot duration
- [ ] Upload @Image1 + @Audio1 vào Seedance mỗi shot
- [ ] Set Seedance duration = audio duration chính xác
- [ ] Prompt có transcript ngoặc kép + "lip sync to @Audio1"
- [ ] Check lip-sync → re-gen max 3 lần nếu lệch
- [ ] Ghép N clip (CapCut/Premiere)
- [ ] Nhạc nền ~10-15% (nhẹ hơn mode A)
- [ ] Export 9:16, 1080p
```

---

## Edge cases

- **Không có ảnh KOC**: hỏi user hoặc tạo persona mặc định
- **Pack shot nền trắng**: đề xuất setting phù hợp category
- **Sản phẩm có logo**: thêm `preserve original label, brand logo intact`
- **Thời lượng custom**: round to gần nhất preset
- **Hybrid mode**: cho phép mix lip-sync + voiceover trong 1 video (shot close-up sản phẩm → VO, shot mặt KOC → lip-sync)
- **Lip-sync lỗi**: gợi ý chuyển shot đó sang voiceover hoặc chia câu ngắn hơn

