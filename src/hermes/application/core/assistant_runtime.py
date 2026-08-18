"""
Hermes Assistant runtime foundation.

This module is intentionally small and side-effect free. It classifies a user
request, splits it into assistant tasks, and returns a reviewable execution
plan. Later jobs can connect these plans to AgentJobManager, Telegram,
affiliate-product-research, and a real coding executor.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Iterable


ASSISTANT_MODULES = {
    "product_research_script": {
        "description": "Research marketplace products, export review sheets, and generate short affiliate scripts.",
        "owner_paths": [
            "hermes/application/product_research_script_workflow.py",
            "hermes/application/product_source_selector.py",
            "hermes/adapters/local/sheet_projection.py",
        ],
        "risk": "medium",
    },
    "video_factory": {
        "description": "Create, crawl, analyze, and package short-form video work.",
        "owner_paths": ["telegram_bot.py", "core/job_watcher.py", "tools/video_downloader.py"],
        "risk": "medium",
    },
    "knowledge_learner": {
        "description": "Learn from Telegram, reports, files, links, and approved proposals.",
        "owner_paths": ["knowledge_base", "core/knowledge_store.py", "core/learning_review.py"],
        "risk": "medium",
    },
    "coding_agent": {
        "description": "Plan code changes, inspect repos, propose patches, and verify commands.",
        "owner_paths": ["core", "scripts", "reports"],
        "risk": "high",
    },
    "tool_builder": {
        "description": "Create reusable local tools with manifest, runner, export, and deploy steps.",
        "owner_paths": ["tools", "docs"],
        "risk": "medium",
    },
    "assistant_core": {
        "description": "Shared routing, provider access, memory, permissions, and orchestration.",
        "owner_paths": ["core/assistant_runtime.py", "core/ai_router.py", "core/agent_jobs.py"],
        "risk": "medium",
    },
}


@dataclass
class AssistantTask:
    task_id: str
    module: str
    title: str
    action: str
    status: str = "planned"
    risk: str = "medium"


@dataclass
class AssistantPlan:
    request: str
    primary_module: str
    tasks: list[AssistantTask]
    permissions_required: list[str]
    suggested_next_command: str
    notes: list[str]


class HermesAssistantRuntime:
    """Classify requests and create reviewable Hermes Assistant plans."""

    def __init__(self, repo_root: str | Path | None = None):
        self.repo_root = Path(repo_root or Path(__file__).resolve().parent.parent).resolve()

    def classify(self, message: str) -> str:
        text = normalize_text(message)
        coding_action_terms = ["fix", "patch", "refactor", "bug", "error", "duplicate", "dedup"]
        if any(term in text for term in coding_action_terms):
            return "coding_agent"
        return "assistant_core"

    def build_plan(self, message: str) -> AssistantPlan:
        message = (message or "").strip()
        primary_module = self.classify(message)
        chunks = split_request(message)
        tasks = [
            self._build_task(index=index, text=chunk, fallback_module=primary_module)
            for index, chunk in enumerate(chunks, start=1)
        ]
        permissions = self._permissions_for(tasks)
        next_command = self._suggested_command(message, primary_module)
        notes = [
            "This is a dry plan. It does not edit code or call external providers.",
            "Coding actions must be routed through a permission layer before writing files.",
            "Use AgentJobManager later for long-running video, learning, or coding jobs.",
        ]
        return AssistantPlan(
            request=message,
            primary_module=primary_module,
            tasks=tasks,
            permissions_required=permissions,
            suggested_next_command=next_command,
            notes=notes,
        )

    def format_markdown(self, plan: AssistantPlan) -> str:
        lines = [
            "# Hermes Assistant Plan",
            "",
            f"Request: {plan.request}",
            f"Primary module: {plan.primary_module}",
            "",
            "## Tasks",
        ]
        for task in plan.tasks:
            lines.extend(
                [
                    f"- {task.task_id} [{task.module}] {task.title}",
                    f"  - Action: {task.action}",
                    f"  - Risk: {task.risk}",
                ]
            )
        lines.extend(["", "## Permissions Required"])
        for item in plan.permissions_required:
            lines.append(f"- {item}")
        lines.extend(["", "## Notes"])
        for item in plan.notes:
            lines.append(f"- {item}")
        lines.extend(["", "## Suggested Command", f"`{plan.suggested_next_command}`"])
        return "\n".join(lines) + "\n"

    def to_dict(self, plan: AssistantPlan) -> dict:
        return asdict(plan)

    def _build_task(self, index: int, text: str, fallback_module: str) -> AssistantTask:
        module = self.classify(text) if text else fallback_module
        metadata = ASSISTANT_MODULES[module]
        title = summarize_task_title(text, module)
        action = action_for_module(module, text)
        return AssistantTask(
            task_id=f"assistant_task_{index:03d}",
            module=module,
            title=title,
            action=action,
            risk=metadata["risk"],
        )

    def _permissions_for(self, tasks: Iterable[AssistantTask]) -> list[str]:
        permissions = {"read_repo"}
        for task in tasks:
            if task.module == "coding_agent":
                permissions.add("write_patch_after_approval")
                permissions.add("run_verification_commands")
            elif task.module == "product_research_script":
                permissions.add("marketplace_crawler_when_enabled")
                permissions.add("write_local_sheet_exports")
                permissions.add("optional_model_script_generation")
            elif task.module == "video_factory":
                permissions.add("network_video_fetch_when_enabled")
                permissions.add("write_project_artifacts")
            elif task.module == "knowledge_learner":
                permissions.add("read_telegram_or_uploaded_reports")
                permissions.add("write_review_queue")
            elif task.module == "tool_builder":
                permissions.add("write_tool_scaffold")
                permissions.add("package_tool_artifacts")
        return sorted(permissions)

    def _suggested_command(self, message: str, primary_module: str) -> str:
        escaped = escape_for_cmd(message)
        if primary_module == "coding_agent":
            return f"python scripts\\hermes_code_agent.py --message \"{escaped}\" --write-report"
        return f"python scripts\\hermes_assistant_cli.py --message \"{escaped}\""


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def split_request(message: str) -> list[str]:
    cleaned = (message or "").strip()
    if not cleaned:
        return ["Review the current Hermes Assistant request."]
    parts = re.split(r"\s*(?:;|\n|\band\b|\bva\b|\bvoi\b|\+)\s*", cleaned, flags=re.I)
    parts = [part.strip(" .,-") for part in parts if part.strip(" .,-")]
    return parts or [cleaned]


def summarize_task_title(text: str, module: str) -> str:
    short = re.sub(r"\s+", " ", text).strip()
    if len(short) > 90:
        short = short[:87].rstrip() + "..."
    return short or f"Handle {module} request"


def action_for_module(module: str, text: str) -> str:
    if module == "product_research_script":
        return "Run a gated product research workflow: collect products, export sheets, and generate short affiliate scripts."
    if module == "video_factory":
        return "Create or route a video-factory job with source capture, analysis, and artifacts."
    if module == "knowledge_learner":
        return "Create a learning intake, produce a proposal, and wait for review approval."
    if module == "coding_agent":
        return "Inspect source, produce a patch plan, apply approved edits, then verify syntax/tests."
    if module == "tool_builder":
        return "Create a tool manifest, scaffold runner files, and prepare export/deploy instructions."
    return "Clarify intent, choose the right Hermes module, and create a safe execution plan."


def escape_for_cmd(text: str) -> str:
    return (text or "").replace('"', '\\"')
