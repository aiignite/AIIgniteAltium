import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.database import Base, engine, async_session_maker
from app.models import AIModelConfig, User  # noqa: F401 —— 确保元数据注册
from app.modules import register_all_modules
from app.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def bootstrap() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from app.database_patches import ensure_extra_columns

        await ensure_extra_columns(conn)
    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.email == settings.admin_email.lower()))
        admin = result.scalars().first()
        if admin is None:
            db.add(
                User(
                    email=settings.admin_email.lower(),
                    display_name="管理员",
                    password_hash=hash_password(settings.admin_password),
                    is_admin=True,
                )
            )
            logger.info("已创建管理员 %s", settings.admin_email)
        elif settings.admin_bootstrap_reset_password:
            admin.password_hash = hash_password(settings.admin_password)
            logger.info("已重置管理员密码")
        from app.services.ai.seed_data import seed_models, seed_skills_and_assistants, upgrade_legacy_api_keys

        await seed_models(db)
        await seed_skills_and_assistants(db)
        await upgrade_legacy_api_keys(db)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.resolve_data_dir()
    await bootstrap()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="AIDriveAltium API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3340", "http://127.0.0.1:3340", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_all_modules(app)

    @app.get("/api/v1/health")
    async def health() -> dict:
        return {"status": "ok", "app": settings.app_name, "gatewayEnabled": False}

    return app


app = create_app()
