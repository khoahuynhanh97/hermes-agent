# Frontend-Backend API Contract Mapping

This document details the alignment between REST endpoints called by the React frontend (`apps/web`) and the routes registered on the FastAPI backend (`src/hermes/channels/api/`).

| Frontend Caller | Method | URL | Backend Route | Status |
| :--- | :--- | :--- | :--- | :--- |
| `ProductResearchStudio.tsx` | GET | `/api/products` | `/api/products` | matched |
| `ProductResearchStudio.tsx` | GET | `/api/products/runs` | `/api/products/runs` | matched |
| `ProductResearchStudio.tsx` | GET | `/api/products/{id}` | `/api/products/{product_id}` | matched |
| `AssetsView.tsx` | GET | `/api/assets` | `/api/assets` | matched |
| `AssetsView.tsx` | POST | `/api/assets/{id}/open-file` | `/api/assets/{asset_id}/open-file` | matched |
| `AssetsView.tsx` | POST | `/api/assets/{id}/open-folder` | `/api/assets/{asset_id}/open-folder` | matched |
| `PromptStudioPage.tsx` / `VideoFactoryPage.tsx` | GET | `/api/assets/{id}/content` | `/api/assets/{asset_id}/content` | matched |
| `PromptStudioPage.tsx` | GET | `/api/prompt-studio/{id}` | `/api/prompt-studio/{project_id}` | matched |
| `PromptStudioPage.tsx` | POST | `/api/prompt-studio/{id}/approve` | `/api/prompt-studio/{project_id}/approve` | matched |
| `PromptStudioPage.tsx` | POST | `/api/prompt-studio/{id}/invalidate` | `/api/prompt-studio/{project_id}/invalidate` | matched |
| `VideoFactoryPage.tsx` | GET | `/api/vf/projects` | `/api/vf/projects` | matched |
| `VideoFactoryPage.tsx` | GET | `/api/vf/projects/{id}` | `/api/vf/projects/{project_id}` | matched |
| `VideoFactoryPage.tsx` | POST | `/api/vf/projects` | `/api/vf/projects` | matched |
| `VideoFactoryPage.tsx` | POST | `/api/vf/projects/{id}/tasks/video-generation` | `/api/vf/projects/{project_id}/tasks/video-generation` | matched |
| `JobsPage.tsx` | GET | `/api/jobs` | `/api/jobs` | matched |
| `JobsPage.tsx` | POST | `/api/jobs` | `/api/jobs` | matched |
| `AIAnalysisPage.tsx` | POST | `http://127.0.0.1:8000/api/ai/analyze` | None (Handled via local frontend mock logic for demo) | intentionally-migrated |

## Notes

- **Prompt Studio Prefixes**: Added the `/prompt-studio` prefix to `src/hermes/channels/api/routes/prompt_studio.py`'s APIRouter to align backend registration with the frontend caller.
- **Video Factory Prefixes**: Added the `/vf` prefix to `src/hermes/channels/api/routes/video_factory.py`'s APIRouter to align backend registration with the frontend and aiohttp test compatibility expectations.
- **AI Analysis Page**: The frontend caller contains built-in fallback mock logic in case the endpoint fails or is unreachable, allowing this page to remain operational without exposing a core backend router.
