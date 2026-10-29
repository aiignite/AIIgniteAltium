import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import engine, async_session_maker
from app.services.system.migrations import check_schema_current
from app.models import AIModelConfig, User  # noqa: F401 —— 确保元数据注册
from app.modules import register_all_modules
from app.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def bootstrap() -> None:
    settings.validate_security()
    async with engine.connect() as conn:
        await conn.run_sync(check_schema_current)
    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.email == settings.admin_email.lower()))
        admin = result.scalars().first()
        if admin is None:
            settings.validate_bootstrap_password()
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
            settings.validate_bootstrap_password()
            admin.password_hash = hash_password(settings.admin_password)
            logger.info("已重置管理员密码")
        from app.services.ai.seed_data import seed_models, seed_skills_and_assistants, upgrade_legacy_api_keys

        await seed_models(db)
        await seed_skills_and_assistants(db)
        await upgrade_legacy_api_keys(db)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_security()
    settings.resolve_data_dir()
    await bootstrap()
    stop = asyncio.Event()
    worker: asyncio.Task | None = None
    if settings.parse_worker_enabled:
        from app.services.files import jobs, parse_service

        async with async_session_maker() as db:
            requeued = await jobs.requeue_orphans(db)
        if requeued:
            logger.info("重新排队 %s 个中断的解析任务", requeued)
        worker = asyncio.create_task(
            jobs.worker_loop(stop, async_session_maker, parse_service.run_parse_job, interval=settings.parse_poll_seconds)
        )
    try:
        yield
    finally:
        if worker is not None:
            stop.set()
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker


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

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, exc):
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": list(e["loc"]), "msg": "Invalid input", "type": e["type"]} for e in exc.errors()
        ]})

    @app.exception_handler(IntegrityError)
    async def integrity_error(_request, _exc):
        return JSONResponse(status_code=409, content={"detail": "Resource conflicts with an existing record or constraint"})

    @app.get("/api/v1/health")
    async def health() -> dict:
        return {"status": "ok", "app": settings.app_name, "gatewayEnabled": False}

    return app


app = create_app()
