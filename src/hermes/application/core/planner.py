import json
from pathlib import Path


ENGINE_TASKS = {
    "ai_studio": [
        ("Product Analysis", "codex", "analysis.md"),
        ("Product Lock", "codex", "product_lock.md"),
        ("Storyboard", "antigravity", "storyboard.md"),
        ("Image Prompts", "antigravity", "image_prompts.md"),
        ("Video Prompts", "antigravity", "video_prompts.md"),
        ("AI Studio Workflow JSON", "codex", "workflow.json"),
        ("CapCut Plan", "codex", "capcut_plan.md"),
    ],
    "html_video": [
        ("HTML Storyboard", "antigravity", "storyboard.md"),
        ("HTML/CSS Video Page", "codex", "index.html"),
        ("Render Instructions", "codex", "render_instructions.md"),
    ],
    "capcut": [
        ("Product Analysis", "codex", "analysis.md"),
        ("Storyboard", "antigravity", "storyboard.md"),
        ("Voiceover", "codex", "voiceover.txt"),
        ("CapCut Plan", "codex", "capcut_plan.md"),
    ],
    "learn_video": [
        ("Video Source Analysis", "codex", "analysis.md"),
        ("Hook Body CTA Extraction", "codex", "hook_body_cta.md"),
        ("Idea And Setup Notes", "codex", "ideas_setup.md"),
        ("Prompt Router Mapping", "codex", "prompt_router_mapping.md"),
        ("Learning Proposal", "codex", "learning_proposal.md"),
    ],
    "learn_knowledge": [
        ("Knowledge Source Analysis", "codex", "analysis.md"),
        ("Knowledge Summary", "codex", "knowledge_summary.md"),
        ("Tools And Concepts", "codex", "tools_and_concepts.md"),
        ("Workflow Steps", "codex", "workflow_steps.md"),
        ("Hermes Applications", "codex", "hermes_applications.md"),
        ("Knowledge Proposal", "codex", "knowledge_proposal.md"),
    ],
    "learn_hook_cta": [
        ("Video Source Analysis", "codex", "analysis.md"),
        ("Hook Body CTA Extraction", "codex", "hook_body_cta.md"),
        ("Idea And Setup Notes", "codex", "ideas_setup.md"),
        ("Prompt Router Mapping", "codex", "prompt_router_mapping.md"),
        ("Learning Proposal", "codex", "learning_proposal.md"),
    ],
    "upgrade_audit": [
        ("Codex Repo Upgrade Audit", "codex", "upgrade_audit.md"),
        ("Antigravity Cross Review", "antigravity", "antigravity_review.md"),
        ("Consolidated Upgrade Proposal", "codex", "upgrade_proposal.md"),
        ("Human Approval Checklist", "codex", "approval_checklist.md"),
    ],
    "mixed": [
        ("Product Analysis", "codex", "analysis.md"),
        ("Product Lock", "codex", "product_lock.md"),
        ("Storyboard", "antigravity", "storyboard.md"),
        ("Image Prompts", "antigravity", "image_prompts.md"),
        ("Video Prompts", "antigravity", "video_prompts.md"),
        ("HTML/CSS Video Page", "codex", "index.html"),
        ("AI Studio Workflow JSON", "codex", "workflow.json"),
        ("CapCut Plan", "codex", "capcut_plan.md"),
    ],
}


def plan_tasks(manifest):
    """Turn a Job Manifest into ordered task JSON objects."""
    engine = manifest.get("engine", "mixed")
    task_defs = ENGINE_TASKS.get(engine, ENGINE_TASKS["mixed"])
    tasks = []
    for index, (name, worker, output_file) in enumerate(task_defs, start=1):
        task_id = f"task_{index:03d}"
        tasks.append({
            "task_id": task_id,
            "job_id": manifest["job_id"],
            "name": name,
            "worker": worker,
            "status": "pending",
            "input_context": build_input_context(manifest, output_file),
            "output_file": output_file,
            "prompt_file": f"tasks/{task_id}_worker_prompt.md",
            "started_at": "",
            "completed_at": "",
            "error": "",
        })
    return tasks


def build_input_context(manifest, output_file):
    return {
        "job_type": manifest.get("job_type", ""),
        "engine": manifest.get("engine", ""),
        "input": manifest.get("input", {}),
        "objective": manifest.get("objective", ""),
        "constraints": manifest.get("constraints", {}),
        "outputs_required": manifest.get("outputs_required", []),
        "current_output": output_file,
    }


def write_task_files(job_dir, manifest, tasks):
    tasks_dir = Path(job_dir) / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        task_path = tasks_dir / f"{task['task_id']}.json"
        prompt_path = Path(job_dir) / task["prompt_file"]
        task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        prompt_path.write_text(generate_worker_prompt(manifest, task), encoding="utf-8")

    master_prompt = Path(job_dir) / "worker_prompt.md"
    master_prompt.write_text(generate_master_prompt(manifest, tasks), encoding="utf-8")


def generate_master_prompt(manifest, tasks):
    lines = [
        "# Hermes Manifest Worker Prompt",
        "",
        f"Job ID: {manifest.get('job_id')}",
        f"Job type: {manifest.get('job_type')}",
        f"Engine: {manifest.get('engine')}",
        f"Objective: {manifest.get('objective')}",
        "",
        "## How to work",
        "- Open each task prompt under the tasks folder.",
        "- Write every output file into the artifacts folder.",
        "- Do not overwrite unrelated project files.",
        "- After writing an artifact, Hermes GUI will detect it and mark the task done.",
        "",
        "## Tasks",
    ]
    for task in tasks:
        lines.append(f"- {task['task_id']} | {task['worker']} | {task['name']} -> artifacts/{task['output_file']}")
    return "\n".join(lines) + "\n"


def generate_worker_prompt(manifest, task):
    input_data = manifest.get("input", {})
    constraints = manifest.get("constraints", {})
    output_file = task.get("output_file", "")
    name = task.get("name", "")

    if manifest.get("engine") == "upgrade_audit" and output_file in [
        "upgrade_audit.md",
        "antigravity_review.md",
        "upgrade_proposal.md",
        "approval_checklist.md",
    ]:
        return f"""You are a Hermes Upgrade Audit Worker.

Job:
{json.dumps(manifest, ensure_ascii=False, indent=2)}

Current artifact: artifacts/{output_file}

Goal:
Create a reviewable upgrade proposal for Hermes. Do not edit production code,
configuration, prompt libraries, or approved knowledge. Only write the requested
artifact in the artifacts folder.

Collaboration protocol:
- Codex writes upgrade_audit.md first with repo findings, upgrade ideas, risks,
  affected files, and recommended priority.
- Antigravity reads upgrade_audit.md and writes antigravity_review.md with
  counterpoints, missed risks, UI/UX concerns, and priority changes.
- Codex reads both files and writes upgrade_proposal.md as the final proposal
  for the user to approve.
- Codex writes approval_checklist.md with exact checkboxes the user can use
  before implementation.

Artifact-specific requirements:
- upgrade_audit.md: include Current state, Proposed upgrades, Why it helps,
  File touch plan, Risks, Tests, Rollback plan, and Open questions.
- antigravity_review.md: include Agreement, Disagreement, Missing cases,
  Suggested priority, and Implementation cautions.
- upgrade_proposal.md: include Executive summary, Approved-by-default scope
  set to none, Proposed implementation phases, Files likely touched, Test plan,
  and "Needs human approval before code changes".
- approval_checklist.md: include concise approval checkboxes and the exact
  command/job name that should trigger implementation after approval.

Important:
- If you cannot inspect the repo, say what is missing instead of guessing.
- Keep recommendations practical for this local Hermes app.
- Write in Vietnamese without accents if your environment has encoding issues.
"""

    if output_file == "product_lock.md":
        return f"""Bạn là Product Lock Agent của Hermes.

Đầu vào:
- Product name: {input_data.get('product_name', '')}
- Product color: {input_data.get('product_color', '')}
- Images/reference: {input_data.get('product_images', [])}
- Reference video: {input_data.get('reference_video') or input_data.get('tiktok_url', '')}

Nhiệm vụ:
Tạo artifacts/product_lock.md để khóa đúng hình dáng, màu sắc, chất liệu, cơ chế hoạt động của sản phẩm.

Yêu cầu:
- Không viết storyboard.
- Không viết video prompt.
- Chỉ output markdown.
- Nhấn mạnh same product, object permanence, no morphing, no wrong color, no extra parts.
- Tôn trọng constraint: same_product={constraints.get('same_product')}, same_background={constraints.get('same_background')}.
"""

    if output_file == "workflow.json":
        return f"""Bạn là Workflow JSON Builder của Hermes.

Đầu vào cần đọc trong artifacts nếu đã có:
- product_lock.md
- storyboard.md
- video_prompts.md

Nhiệm vụ:
Tạo artifacts/workflow.json import được vào AI Studio VN PRO.

Yêu cầu:
- Node flow: Start -> Prompt Tĩnh -> Prompt Splitter -> Storyboard -> VideoGen -> Stitcher -> Upscale.
- Aspect ratio {constraints.get('aspect_ratio', '9:16')}.
- Duration {constraints.get('duration_per_scene', 8)}s.
- sceneCount đúng theo manifest: {constraints.get('scene_count', 4)}.
- JSON hợp lệ, không markdown.
"""

    if output_file == "index.html":
        return f"""Bạn là HTML Video Worker của Hermes.

Đầu vào:
- Product name: {input_data.get('product_name', '')}
- Product color: {input_data.get('product_color', '')}
- Objective: {manifest.get('objective', '')}

Nhiệm vụ:
Tạo artifacts/index.html là một trang video/storyboard 9:16 có thể render bằng browser hoặc capture tool.

Yêu cầu:
- HTML/CSS/JS nằm trong một file.
- Layout 9:16, không watermark.
- Không dùng API trả phí.
- Nếu thiếu ảnh sản phẩm, dùng placeholder rõ ràng và ghi assumption trong comment HTML.
"""

    if output_file == "video_prompts.md":
        return f"""Bạn là Video Prompt Agent của Hermes.

Nhiệm vụ:
Tạo artifacts/video_prompts.md gồm {constraints.get('scene_count', 4)} scene prompt cho AI video.

Yêu cầu:
- Mỗi scene {constraints.get('duration_per_scene', 8)} giây, format {constraints.get('aspect_ratio', '9:16')}.
- Giữ cùng sản phẩm, cùng màu, không morphing, không thêm chi tiết sai.
- Không chèn text trực tiếp trong video nếu no_text_in_video={constraints.get('no_text_in_video')}.
- Viết prompt đủ rõ để dùng cho Grok/Pika/Krea/Runway/Veo/AI Studio.
"""

    if manifest.get("engine") == "learn_knowledge" and output_file in [
        "analysis.md",
        "knowledge_summary.md",
        "tools_and_concepts.md",
        "workflow_steps.md",
        "hermes_applications.md",
        "knowledge_proposal.md",
    ]:
        return f"""Bạn là Hermes Knowledge Learning Agent.

Input:
{json.dumps(input_data, ensure_ascii=False, indent=2)}

Objective:
{manifest.get('objective', '')}

Current artifact: artifacts/{output_file}

Rules:
- Học kiến thức/nội dung bài chia sẻ trong video, không mặc định biến thành kịch bản bán hàng.
- Ưu tiên: công cụ được nhắc tới, khái niệm, quy trình, bước làm, lưu ý, giới hạn, cách Hermes có thể áp dụng.
- Không tự sửa prompt_library và không ghi vào approved_lessons.
- Nếu thiếu video/transcript, ghi rõ needs_source_media thay vì suy diễn.

Output format:
- Nếu artifact là analysis.md: tóm tắt nguồn và độ tin cậy dữ liệu.
- Nếu artifact là knowledge_summary.md: nêu nội dung chính video muốn truyền đạt.
- Nếu artifact là tools_and_concepts.md: liệt kê công cụ, khái niệm, vai trò từng công cụ.
- Nếu artifact là workflow_steps.md: ghi quy trình từng bước, đầu vào/đầu ra của mỗi bước.
- Nếu artifact là hermes_applications.md: cách đưa kiến thức này vào Hermes, lệnh nào dùng, module nào nên học.
- Nếu artifact là knowledge_proposal.md: viết proposal duyệt tri thức có Source, Facts, Workflow, Apply in Hermes, Unknowns, Review checklist.
"""

    if manifest.get("engine") in ["learn_video", "learn_hook_cta"] and output_file in [
        "analysis.md",
        "hook_body_cta.md",
        "ideas_setup.md",
        "prompt_router_mapping.md",
        "learning_proposal.md",
    ]:
        return f"""Bạn là Hermes Video Learning Agent.

Input:
{json.dumps(input_data, ensure_ascii=False, indent=2)}

Objective:
{manifest.get('objective', '')}

Current artifact: artifacts/{output_file}

Rules:
- Phân tích video/link theo hướng có thể tái sử dụng cho TikTok Shop.
- Không tự sửa prompt_library và không ghi vào approved_lessons.
- Nếu rút ra bài học hay prompt mới, viết rõ để người dùng duyệt lại.
- Nếu thiếu transcript/hình ảnh, ghi rõ assumption.

Output format:
- Viết bằng tiếng Việt, ngắn gọn nhưng đủ dùng.
- Nếu artifact là analysis.md: tóm tắt video, bối cảnh, sản phẩm, hành động, camera, edit, voice.
- Nếu artifact là hook_body_cta.md: bóc cấu trúc hook, body, proof, CTA, lý do giữ chân.
- Nếu artifact là ideas_setup.md: rút ý tưởng, cách quay, background, props, setup ánh sáng, cách dùng sản phẩm.
- Nếu artifact là prompt_router_mapping.md: map bài học vào promptA voice/script, promptB image/background, promptC AI video; đề xuất biến đầu vào.
- Nếu artifact là learning_proposal.md: viết proposal hoàn chỉnh có các mục Source, Lessons, Prompt/Rule proposal, When to use, When not to use, Example output. File này sẽ được GUI cho người dùng duyệt trước khi xem là tri thức chính thức.
"""

    return f"""Bạn là {name} Worker của Hermes.

Manifest:
{json.dumps(manifest, ensure_ascii=False, indent=2)}

Nhiệm vụ:
Tạo artifacts/{output_file}.

Yêu cầu:
- Chỉ ghi đúng artifact yêu cầu.
- Ưu tiên tiếng Việt cho nội dung creator-facing.
- Tôn trọng aspect ratio, scene count, duration và các constraint trong manifest.
- Nếu thiếu dữ liệu, ghi rõ assumption trong artifact.
"""
