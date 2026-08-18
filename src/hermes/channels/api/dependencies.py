import os
from pathlib import Path
from fastapi import HTTPException, status
from hermes.config import get_data_path
from hermes.adapters.sqlite.project_repository import SQLiteProjectRepository
from hermes.security.principal import current_principal, PrincipalContext


def get_authenticated_principal_context() -> PrincipalContext:
    """Canonical route dependency that strictly reads current_principal
    which was bound at ingress by APIPrincipalIngressMiddleware.

    NEVER creates identity, NEVER calls fallback identity builders.
    Fails closed with HTTP 401 Unauthorized if current_principal is missing.
    """
    principal = current_principal.get()
    if principal is None or not principal.owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="UNAUTHENTICATED_PRINCIPAL: Session principal context missing at route dependency"
        )
    return principal


def verify_owner_match(requested_owner: str | None, principal: PrincipalContext) -> str:
    """Validate optional query/body owner_user_id parameter against authenticated principal.
    If requested_owner is provided and does not match authenticated principal.owner_user_id,
    reject immediately with HTTP 403 Forbidden.
    """
    authenticated_owner = principal.owner_user_id
    if requested_owner is not None and requested_owner.strip():
        req = requested_owner.strip()
        if req != authenticated_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"PRINCIPAL_MISMATCH: Requested owner '{req}' does not match authenticated principal '{authenticated_owner}'"
            )
    return authenticated_owner


def get_project_repository():
    db_path = Path(os.environ.get("HERMES_DB_PATH", get_data_path("db", "hermes.db"))).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo = SQLiteProjectRepository(db_path)
    return repo


def get_prompt_studio_service():
    from hermes.application.prompt_studio_service import PromptStudioService
    from hermes.adapters.sqlite.workflow_repository import SQLiteWorkflowRepository
    db_path = Path(os.environ.get("HERMES_DB_PATH", get_data_path("db", "hermes.db"))).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo = SQLiteWorkflowRepository(db_path)
    return PromptStudioService(repo)


def get_job_service():
    from hermes.application.job_service import JobService
    from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
    db_path = Path(os.environ.get("HERMES_DATA_DIR", get_data_path())) / "db" / "video.sqlite"
    return JobService(CanonicalJobRepository(str(db_path)))


def get_video_factory_job_service():
    from hermes.application.job_service import JobService
    from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
    configured = os.environ.get("HERMES_VIDEO_FACTORY_DB_PATH", "").strip()
    db_path = Path(configured).expanduser().resolve() if configured else get_data_path("db", "video_factory.sqlite")
    return JobService(CanonicalJobRepository(str(db_path)))
