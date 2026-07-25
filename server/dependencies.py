from __future__ import annotations

from fastapi import Depends

# These will be wired to real services after Phase 3 implementation. For now, we provide
# module-level placeholders so the API contract tests can verify routing works.


def get_project_repository():
    raise NotImplementedError("Project repository not yet wired in this environment")


def get_prompt_studio_service():
    raise NotImplementedError("Prompt Studio service not yet wired in this environment")


def get_job_service():
    raise NotImplementedError("Job service not yet wired in this environment")