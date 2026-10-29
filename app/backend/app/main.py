"""Application assembly. API handlers live in app.api.v1."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config.settings import settings
from app.core.lifecycle import lifespan
from app.core.logging import setup_logging
if settings().foundation_enabled:
    from app.foundation.api import router
else:
    from app.api.router import router

setup_logging()
app = FastAPI(title="电商智能客服系统", version="0.1.0", lifespan=lifespan)
if settings().foundation_enabled:
    from app.foundation.errors import configure_errors
    configure_errors(app)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings().cors_origins.split(",")],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
