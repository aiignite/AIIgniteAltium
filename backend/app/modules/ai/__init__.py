from fastapi import FastAPI

from app.routers.ai.assistants import router as assistants_router
from app.routers.ai.chat import router as chat_router
from app.routers.ai.models import router as models_router
from app.routers.ai.skills import router as skills_router


def register_routers(app: FastAPI) -> None:
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(models_router, prefix="/api/v1")
    app.include_router(skills_router, prefix="/api/v1")
    app.include_router(assistants_router, prefix="/api/v1")
