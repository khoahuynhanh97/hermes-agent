# Hermes Agent - Huong Dan Flow Su Dung

Tai lieu nay mo ta cach dung Hermes Agent theo workflow moi: GUI/Telegram tao Job Manifest, Planner tach thanh task, Worker/Codex/Antigravity tao artifact, nguoi dung duyet ket qua va bai hoc truoc khi dung lai.

## 1. Chay App

Mo terminal tai thu muc Hermes:

```powershell
cd C:\Work\Code\Hermes_download\hermes-agent
$env:PYTHONUTF8=1
python main_gui.py
```

Neu muon chay bot Telegram:

```powershell
cd C:\Work\Code\Hermes_download\hermes-agent
$env:PYTHONUTF8=1
python telegram_bot.py
```

Neu muon worker local claim task:

```powershell
cd C:\Work\Code\Hermes_download\hermes-agent
$env:PYTHONUTF8=1
python scripts\run_job_worker.py
```

Worker hien tai khong tu goi model tra phi. No claim task, ghi log, va tao prompt de Codex/Antigravity hoac nguoi dung xu ly thu cong.

## 2. Cac Khai Niem Chinh

### Project

Moi san pham nen co mot project rieng trong:

```text
projects/{product_slug}/
```

Ben trong project co:

- `Phoi/`: video phoi goc hoac prompt pack AI video.
- `clips/`: clip ngan da cat 9:16.
- `audio/`: file voice/audio.
- `scripts/`: kich ban.
- `exports/`: video xuat ra.
- `agent_outputs/`: output legacy cua agent job cu.

### Job Manifest

Moi yeu cau lon tu GUI/Telegram se tao mot manifest:

```text
jobs/pending/{job_id}/manifest.json
```

Manifest la hop dong cong viec: san pham gi, engine nao, muc tieu nao, can output nao.

### Task Queue

Planner doc manifest va sinh task:

```text
jobs/{status}/{job_id}/tasks/task_001.json
jobs/{status}/{job_id}/tasks/task_001_worker_prompt.md
```

Moi task co:

- `task_id`
- `name`
- `worker`
- `status`
- `output_file`
- `prompt_file`

### Artifact Store

Ket qua cua moi task duoc ghi vao:

```text
jobs/{status}/{job_id}/artifacts/
```

Vi du:

- `analysis.md`
- `product_lock.md`
- `storyboard.md`
- `image_prompts.md`
- `video_prompts.md`
- `workflow.json`
- `capcut_plan.md`
- `index.html`

GUI se doc artifact folder va hien nut mo file.

## 3. Flow 1 - Lam Video Tu Project San Pham

Dung khi anh da co san pham va muon lam video TikTok theo cach truyen thong.

### Buoc 1: Tao project

Trong sidebar:

1. Nhap ten san pham vao `Tao du an nhanh`.
2. Bam `Tao / mo du an`.
3. Hermes tao project trong `projects/{product_slug}`.

Hoac vao tab `San pham` de nhap thong tin day du hon:

- Ten san pham.
- Mo ta.
- Gia.
- Diem ban hang.
- Doi tuong.
- Pain point.

### Buoc 2: Tim phoi

Vao tab `Tim phoi`.

Co the lay phoi tu:

- URL thu cong.
- Pexels.
- Pixabay.
- Supplier feed.
- Custom scraper.
- AI Video Provider.

Neu dung AI Video Provider ma chua co API endpoint/key on dinh, Hermes se tao file:

```text
projects/{product_slug}/Phoi/ai_video_prompts_*.txt
```

Copy prompt nay sang Grok, Pika, Krea, Runway, Leonardo hoac tool khac de tao video thu cong.

### Buoc 3: Cat clip phoi

Vao tab `Cat clip phoi`.

Hermes se:

- Cat video thanh clip ngan.
- Crop 9:16.
- Mute audio neu can.
- Cham chat luong bang OpenCV.
- Luu clip tot vao `clips/`.

### Buoc 4: Quan ly Kho Phoi

Vao tab `Kho Phoi`.

Dung de:

- Xem clip.
- Duyet clip.
- Reject clip xau.
- Gan clip theo scene type: hook, demo, lifestyle, CTA.

### Buoc 5: Tao kich ban va audio

Vao flow AI:

1. Tab `Kich ban`: tao script, hook, CTA, caption.
2. Tab `Audio`: import file voice/audio da tao tu ElevenLabs hoac tool khac.

### Buoc 6: Dung video

Vao tab `Dung video`.

Hermes se:

- Chon clip tot/okay.
- Gheps theo audio.
- Them subtitle neu bat.
- Xuat video 9:16 vao `exports/`.

### Buoc 7: Lay video thanh pham

Vao tab `Ket qua` de mo folder export va copy caption/hashtag.

## 4. Flow 2 - Tao Job Manifest Tu GUI

Dung khi anh muon Hermes chay theo kien truc moi: Manifest -> Planner -> Task -> Artifact.

### Buoc 1: Mo tab Agent Jobs

Vao:

```text
Flow AI -> Agent Jobs
```

### Buoc 2: Nhap source

O `TikTok link / video path`, dan mot trong cac loai:

- Link TikTok/YouTube.
- Duong dan video local.
- Mo ta san pham.

### Buoc 3: Chon target project

Co 2 cach:

- `Create new project`: tao project moi.
- `Append to active/existing project`: gan job vao project dang co.

### Buoc 4: Chon engine

Engine quyet dinh Planner se sinh task nao:

- `ai_studio`: phu hop tao package cho AI Studio/Veo workflow.
- `html_video`: tao storyboard + HTML/CSS video page + render instructions.
- `mixed`: tao day du hon, gom prompt, HTML, workflow, CapCut.
- `capcut`: tap trung storyboard, voiceover, capcut plan.

### Buoc 5: Tao job

Bam:

```text
Tao Job cho Antigravity / Codex
```

Hermes se tao:

```text
jobs/pending/{job_id}/manifest.json
jobs/pending/{job_id}/tasks/*.json
jobs/pending/{job_id}/tasks/*_worker_prompt.md
jobs/pending/{job_id}/worker_prompt.md
jobs/pending/{job_id}/artifacts/
jobs/pending/{job_id}/logs/
```

### Buoc 6: Theo doi progress

Ben phai tab `Agent Jobs` co:

- Job status.
- Progress bar.
- Checklist task.
- Artifact buttons.
- Worker prompt.
- Logs.

GUI tu refresh moi 3 giay.

### Buoc 7: Xu ly task bang Codex/Antigravity

Mo file:

```text
jobs/{status}/{job_id}/tasks/task_XXX_worker_prompt.md
```

Doc prompt, tao dung file output vao:

```text
jobs/{status}/{job_id}/artifacts/{output_file}
```

Vi du task Product Lock yeu cau:

```text
artifacts/product_lock.md
```

Khi file artifact xuat hien, Hermes se tu sync va danh dau task do la `done`.

## 5. Flow 3 - Tao Job Tu Telegram

Telegram khong nen xu ly model truc tiep trong flow moi. Telegram chi tao Manifest.

### Tao review package san pham

Gui:

```text
/review Gia do dien thoai xoay 360 mau trang
```

Hermes se tao manifest engine `ai_studio`.

### Tao HTML video job

Gui:

```text
/htmlvideo Gia do dien thoai xoay 360
```

Hermes se tao manifest engine `html_video`.

### Hoc tu video

Gui link video TikTok/YouTube, hoac gui truc tiep file video/document video len Telegram. Bot se hoi chon:

```text
/hoc_kien_thuc
/hoc_hook_CTA
/len_kich_ban
```

- `/hoc_kien_thuc`: hoc kien thuc/noi dung bai chia se, gom cong cu, khai niem, quy trinh, buoc lam, luu y, cach ap dung vao Hermes.
- `/hoc_hook_CTA`: hoc cong thuc noi dung ban hang/sang tao, gom hook/body/proof/CTA, retention, goc quay, prompt/phan canh.
- `/hoc_video`: alias cua `/hoc_kien_thuc` de giu tuong thich nguoc.
- `/len_kich_ban`: phan tich video va tao kich ban moi dua tren video.
- Co the gui video voi caption `/hoc_kien_thuc` hoac `/hoc_hook_CTA`, hoac reply vao video bang lenh tuong ung.
- Video gui truc tiep se duoc luu vao `knowledge_base/video_sources/` de worker co duong dan local.

Ket qua job se duoc bot gui lai khi artifact/job done xuat hien trong outbox.

### Luu prompt tu Telegram

Dung:

```text
/luu_prompt Ten prompt | noi dung prompt
```

Hoac reply vao mot tin nhan prompt bang `/luu_prompt`.

Bot se ghi proposal vao `knowledge_base/review_queue/`. Prompt chi nen duoc dua vao `prompt_library/templates/` sau khi anh duyet.

## 6. Flow 4 - Hermes Tu Hoc Nhung Can Duyet

Hermes khong nen tu sua prompt/rule ngay lap tuc. Flow an toan la:

```text
Worker/Codex de xuat bai hoc
    -> ghi proposal vao knowledge_base/review_queue
    -> anh mo GUI tab Duyet hoc hoi
    -> xem preview
    -> Duyet hoac Tu choi
```

### Tao proposal de duyet

Worker/Codex co the ghi file vao:

```text
knowledge_base/review_queue/
```

Vi du:

```text
knowledge_base/review_queue/phone-stand-hook-pattern.md
knowledge_base/review_queue/promptD-demo-before-after.md
```

Noi dung nen gom:

- Video/source hoc tu dau.
- Bai hoc rut ra.
- Prompt/rule de xuat.
- Khi nao nen ap dung.
- Khi nao khong nen ap dung.
- Vi du output.

### Duyet trong GUI

Vao:

```text
Flow AI -> Duyet hoc hoi
```

Neu bam `Duyet va luu bai hoc`, file duoc chuyen sang:

```text
knowledge_base/approved_lessons/
```

Neu bam `Tu choi proposal`, file duoc chuyen sang:

```text
knowledge_base/rejected_lessons/
```

Chi bai hoc trong `approved_lessons` moi nen duoc xem la tri thuc chinh thuc.

## 7. Flow 5 - Tao Workflow JSON Cho AI Studio

Dung engine:

```text
ai_studio
```

Planner se sinh cac task chinh:

```text
Product Analysis -> analysis.md
Product Lock -> product_lock.md
Storyboard -> storyboard.md
Image Prompts -> image_prompts.md
Video Prompts -> video_prompts.md
AI Studio Workflow JSON -> workflow.json
CapCut Plan -> capcut_plan.md
```

Thu tu nen lam:

1. Hoan thanh `analysis.md`.
2. Hoan thanh `product_lock.md` de khoa san pham.
3. Hoan thanh `storyboard.md`.
4. Hoan thanh `video_prompts.md`.
5. Tao `workflow.json`.
6. Tao `capcut_plan.md` neu can edit ngoai.

Luu y: task `workflow.json` nen doc lai cac artifact truoc do, dac biet `product_lock.md`, `storyboard.md`, `video_prompts.md`.

## 8. Flow 6 - Tao HTML Video

Dung engine:

```text
html_video
```

Planner se sinh:

```text
HTML Storyboard -> storyboard.md
HTML/CSS Video Page -> index.html
Render Instructions -> render_instructions.md
```

Dung khi anh muon tao mot video/page co the capture/render bang browser.

Artifact can co:

- `storyboard.md`: chia scene.
- `index.html`: trang 9:16.
- `render_instructions.md`: cach render/capture.

## 9. Trang Thai Job Va Task

Job status:

```text
pending -> planning -> running -> completed
```

Neu loi:

```text
failed
```

Task status:

```text
pending -> running -> done
```

Neu loi:

```text
failed
```

Progress tinh theo:

```text
done_tasks / total_tasks * 100
```

## 10. Noi Tim File Quan Trong

### Manifest job

```text
jobs/{pending|running|done|failed}/{job_id}/manifest.json
```

### Prompt cho toan bo job

```text
jobs/{status}/{job_id}/worker_prompt.md
```

### Prompt rieng tung task

```text
jobs/{status}/{job_id}/tasks/task_XXX_worker_prompt.md
```

### Artifact output

```text
jobs/{status}/{job_id}/artifacts/
```

### Log

```text
jobs/{status}/{job_id}/logs/system.log
jobs/{status}/{job_id}/logs/worker.log
```

### Learning approval

```text
knowledge_base/review_queue/
knowledge_base/approved_lessons/
knowledge_base/rejected_lessons/
```

## 11. Cach Dung Khuyen Nghi

### Khi lam video review san pham moi

Dung:

```text
GUI -> Tao project -> Tim phoi -> Cat clip -> Agent Jobs ai_studio -> Duyet artifact -> Dung video
```

### Khi muon hoc tu video doi thu

Dung:

```text
Telegram gui link/file -> /hoc_kien_thuc -> Worker tao knowledge proposal -> Duyet hoc hoi
Telegram gui link/file -> /hoc_hook_CTA -> Worker tao hook/CTA proposal -> Duyet hoc hoi
```

### Khi muon tao bo prompt cho AI video

Dung:

```text
Agent Jobs -> engine ai_studio hoac mixed -> hoan thanh product_lock/storyboard/video_prompts
```

### Khi muon Codex va Antigravity de xuat nang cap Hermes

Dung:

```text
Telegram /de_xuat_nang_cap <noi dung can nang cap>
hoac GUI Agent Jobs -> engine upgrade_audit
```

Output can doc:

- `upgrade_audit.md`: Codex audit repo va de xuat huong nang cap.
- `antigravity_review.md`: Antigravity phan bien, bo sung rui ro va uu tien.
- `upgrade_proposal.md`: ban tong hop cuoi cung de anh duyet.
- `approval_checklist.md`: checklist approve truoc khi implement.

Quy tac: job nay chi tao proposal/artifact, khong tu sua code production khi anh chua approve.

### Khi muon lam video bang HTML/browser

Dung:

```text
Telegram /htmlvideo <san pham>
hoac GUI Agent Jobs -> engine html_video
```

## 12. Nguyen Tac Van Hanh

- Telegram/GUI chi tao Manifest, khong nen tu xu ly model truc tiep.
- Planner chi tach task, khong tao noi dung.
- Worker/Codex/Antigravity tao artifact theo prompt tung task.
- Artifact phai ghi dung vao `artifacts/`.
- Hermes chi "hoc" sau khi anh duyet trong tab `Duyet hoc hoi`.
- Khong de Hermes tu sua prompt/rule production neu chua co approval.
- Neu mot task loi, chi chay lai task do, khong can tao lai toan bo job.

## 13. Checklist Cho Mot Job Hoan Chinh

Truoc khi xem job la xong, nen co:

- Manifest co input san pham/link dung.
- Tat ca task quan trong da `done`.
- Artifact output mo duoc trong GUI.
- `product_lock.md` khoa dung san pham.
- `storyboard.md` co scene ro.
- `video_prompts.md` giu same product/same background.
- `workflow.json` la JSON hop le neu dung AI Studio.
- `capcut_plan.md` du ro neu can edit bang CapCut.
- Proposal hoc hoi, neu co, da nam trong `review_queue` va cho anh duyet.
