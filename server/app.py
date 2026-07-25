from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.dependencies import get_job_service, get_project_repository, get_prompt_studio_service
from server.routes import projects, jobs, prompt_studio
from server.sse import router as sse_router

app = FastAPI(title="Hermes Web API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(prompt_studio.router, prefix="/api/prompt-studio", tags=["prompt_studio"])
app.include_router(sse_router, prefix="/api", tags=["events"])


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}