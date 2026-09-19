from fastapi import FastAPI

from app.routers.system.auth import router as auth_router


def register_routers(app: FastAPI) -> None:
    app.include_router(auth_router, prefix="/api/v1")
