from fastapi import FastAPI

from app.routers.altium.connections import router as connections_router


def register_routers(app: FastAPI) -> None:
    app.include_router(connections_router, prefix="/api/v1")
