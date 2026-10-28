"""解析任务队列：数据库持久化、崩溃恢复、单工程互斥。

任务状态存于 fls_parse_jobs；worker 以 FOR UPDATE SKIP LOCKED 领取，
因此同一任务不会被并发执行，进程重启后遗留的 running 任务会被重新排队。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.files.parse_job import ACTIVE_JOB_STATUSES, ParseJob

logger = logging.getLogger(__name__)

# 大于 worker 解析超时（300s），避免误回收仍在执行的另一实例任务
ORPHAN_STALE_SECONDS = 600


class ParseJobConflictError(Exception):
    """该工程已有排队或执行中的解析任务。"""


async def active_job(db: AsyncSession, project_id) -> ParseJob | None:
    return await db.scalar(
        select(ParseJob).where(ParseJob.project_id == project_id, ParseJob.status.in_(ACTIVE_JOB_STATUSES))
    )


async def enqueue_parse(db: AsyncSession, project_id) -> tuple[ParseJob, bool]:
    """幂等入队：已有活动任务时返回它并标记未新建。"""
    existing = await active_job(db, project_id)
    if existing is not None:
        return existing, False
    job = ParseJob(project_id=project_id)
    try:
        async with db.begin_nested():
            db.add(job)
            await db.flush()
    except IntegrityError:
        existing = await active_job(db, project_id)
        if existing is None:
            raise
        return existing, False
    return job, True


async def require_enqueue(db: AsyncSession, project_id) -> ParseJob:
    """用户显式重新解析：已有活动任务时报冲突，不静默复用。"""
    existing = await active_job(db, project_id)
    if existing is not None:
        raise ParseJobConflictError(str(existing.id))
    job, _ = await enqueue_parse(db, project_id)
    return job


async def claim_next(db: AsyncSession) -> ParseJob | None:
    job = await db.scalar(
        select(ParseJob)
        .where(ParseJob.status == "queued")
        .order_by(ParseJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = "running"
    job.attempt += 1
    job.started_at = datetime.now(timezone.utc)
    job.error = ""
    await db.commit()
    return job


async def requeue_orphans(db: AsyncSession, *, stale_after_seconds: int = ORPHAN_STALE_SECONDS) -> int:
    """进程启动时回收遗留任务；仅在超过 stale 阈值后回收，避免抢走其他实例正在执行的任务。"""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
    result = await db.execute(
        update(ParseJob)
        .where(ParseJob.status == "running", ParseJob.started_at < cutoff)
        .values(status="queued", error="", started_at=None)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return result.rowcount or 0


async def process_next(
    session_factory: async_sessionmaker[AsyncSession],
    runner: Callable[[AsyncSession, object], Awaitable[None]],
) -> bool:
    async with session_factory() as db:
        job = await claim_next(db)
        if job is None:
            return False
        job_id = job.id
        try:
            await runner(db, job_id)
        except Exception:  # noqa: BLE001
            logger.exception("parse job %s crashed", job_id)
            await db.rollback()
            fresh = await db.get(ParseJob, job_id)
            if fresh is not None and fresh.status == "running":
                fresh.status = "failed"
                fresh.error = "解析任务异常终止"
                fresh.finished_at = datetime.now(timezone.utc)
                await db.commit()
        return True


async def worker_loop(
    stop: asyncio.Event,
    session_factory: async_sessionmaker[AsyncSession],
    runner: Callable[[AsyncSession, object], Awaitable[None]],
    *,
    interval: float = 2.0,
) -> None:
    logger.info("parse worker started")
    while not stop.is_set():
        try:
            processed = await process_next(session_factory, runner)
        except Exception:  # noqa: BLE001
            logger.exception("parse worker iteration failed")
            processed = False
        if processed:
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
    logger.info("parse worker stopped")
