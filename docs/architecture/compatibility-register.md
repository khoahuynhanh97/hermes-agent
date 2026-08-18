# Compatibility Module Register

This document tracks modules originally built for compatibility purposes that need to be eventually removed or fully integrated into the canonical architecture.

| Module                                           | Current Callers | Canonical Replacement                            | Removal Condition                                   | Owner          |
|--------------------------------------------------|-----------------|--------------------------------------------------|-----------------------------------------------------|----------------|
| `src/hermes/channels/api/compatibility/web_studio.py` | None (standalone aiohttp server) | `src/hermes/channels/api/routes/prompt_studio.py` (new) | All API logic migrated to canonical FastAPI routes. | Hermes Core Team |
| `src/hermes/channels/api/compatibility/video_factory_api.py` | `web_studio.py`           | `src/hermes/channels/api/routes/video_factory.py` (existing) | All API logic migrated to canonical FastAPI routes. | Hermes Core Team |
