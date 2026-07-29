from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.google_drive import router as google_drive_router
from app.api.health import router as health_router
from app.api.local_sources import router as local_sources_router
from app.api.search import router as search_router
from app.auth import AuthMiddleware
from app.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(google_drive_router)
    app.include_router(local_sources_router)
    app.include_router(search_router)
    return app


app = create_app()
