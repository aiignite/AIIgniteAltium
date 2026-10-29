from fastapi import FastAPI

from app.routers.files.exports import router as exports_router
from app.routers.files.projects import router as projects_router
from app.routers.files.reviews import router as reviews_router


def register_routers(app: FastAPI) -> None:
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(reviews_router, prefix="/api/v1")
    app.include_router(exports_router, prefix="/api/v1")
