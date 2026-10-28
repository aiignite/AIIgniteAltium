from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.files.review_run import ReviewRun
from app.schemas import CamelModel
from app.security import get_current_user
from app.services.files.access import get_owned_project
from app.services.files.review import RULESET_VERSION, review_snapshot, summarize

router = APIRouter(prefix="/files/projects", tags=["files"])


class ReviewOut(CamelModel):
    id: str
    snapshot_version: int
    status: str
    ruleset_version: str
    counts: dict[str, int] = {}
    created_at: str


class ReviewDetailOut(ReviewOut):
    findings: list[dict] = []


def _out(run: ReviewRun, *, with_findings: bool = False) -> dict:
    data = {
        "id": str(run.id),
        "snapshot_version": run.snapshot_version,
        "status": run.status,
        "ruleset_version": run.ruleset_version,
        "counts": run.counts or {},
        "created_at": run.created_at.isoformat(),
    }
    if with_findings:
        data["findings"] = run.findings or []
    return data


async def _get_run(db: AsyncSession, project_id: UUID, run_id: UUID) -> ReviewRun:
    run = await db.get(ReviewRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(404, "审查记录不存在")
    return run


@router.post("/{project_id}/reviews", response_model=ReviewDetailOut)
async def create_review(
    project_id: UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_owned_project(db, project_id, user.id)
    if not project.current_version or not project.snapshot:
        raise HTTPException(409, "工程尚未解析完成，无法审查")
    findings = review_snapshot(project.snapshot)
    run = ReviewRun(
        project_id=project.id,
        user_id=user.id,
        snapshot_version=project.current_version,
        status="completed",
        ruleset_version=RULESET_VERSION,
        counts=summarize(findings),
        findings=findings,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return _out(run, with_findings=True)


@router.get("/{project_id}/reviews", response_model=list[ReviewOut])
async def list_reviews(
    project_id: UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    project = await get_owned_project(db, project_id, user.id)
    rows = await db.scalars(
        select(ReviewRun)
        .where(ReviewRun.project_id == project.id)
        .order_by(ReviewRun.created_at.desc())
        .limit(20)
    )
    return [_out(run) for run in rows]


@router.get("/{project_id}/reviews/{run_id}", response_model=ReviewDetailOut)
async def get_review(
    project_id: UUID,
    run_id: UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_owned_project(db, project_id, user.id)
    run = await _get_run(db, project.id, run_id)
    return _out(run, with_findings=True)
