"""SearchOS API — FastAPI app with REST + WebSocket."""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add repo root (…/SearchOS) and web/ to path so `searchos` and `api` import.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "web"))

from contextlib import asynccontextmanager  # noqa: E402

from api import local_index_jobs, network_import_jobs, settings_store, topic_recap_jobs  # noqa: E402
from api.routes import (  # noqa: E402
    skills,
    diagnostics,
    history,
    local_search,
    models,
    search,
    settings,
    stream,
    workspace,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Apply the persisted web-settings overlay on top of the env base layer.
    settings_store.load_and_apply()
    from api.skill_creation_jobs import jobs as skill_jobs
    skill_jobs.recover()
    local_index_jobs.resume_background_indexes()
    network_import_jobs.resume_network_imports()
    topic_recap_jobs.resume_topic_recaps()
    try:
        yield
    finally:
        await skill_jobs.stop()
        await local_index_jobs.stop_background_indexes()
        await network_import_jobs.stop_network_imports()
        await topic_recap_jobs.stop_topic_recaps()


app = FastAPI(
    title="SearchOS API",
    version="0.1.0",
    description="SearchOS — agentic search harness, REST + WebSocket API",
    lifespan=lifespan,
)

# CORS for the frontend dev server (any localhost port — 3000, 3001, …)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(skills.router)
app.include_router(skills.library_router)
app.include_router(search.router)
app.include_router(workspace.router)
app.include_router(stream.router)
app.include_router(history.router)
app.include_router(local_search.router)
app.include_router(settings.router)
app.include_router(models.router)
app.include_router(diagnostics.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
