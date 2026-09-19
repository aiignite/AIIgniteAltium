from fastapi import FastAPI

from app.routers.files.projects import router as projects_router


def register_routers(app: FastAPI) -> None:
    app.include_router(projects_router, prefix="/api/v1")
