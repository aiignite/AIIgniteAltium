import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.ai.assistant import AIAssistant, AISkill
from app.schemas import CamelModel
from app.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai/skills", tags=["ai-skills"])

MIN_SCORE = 15


class SkillIn(CamelModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    category: str = "business"
    icon: str = "sparkles"
    prompt_template: str = ""
    keywords: list[str] = []
    enabled: bool = True


class SkillOut(SkillIn):
    id: str
    is_system: bool
    sort_order: int = 0
    created_at: str


class SkillResolveIn(CamelModel):
    query: str = Field(min_length=1, max_length=4000)
    assistant_id: UUID | None = None
    exclude_codes: list[str] = []
    top_k: int = 3


class SkillCandidateOut(CamelModel):
    code: str
    name: str
    description: str
    icon: str
    score: int
    reasons: list[str] = []


def _out(s: AISkill) -> SkillOut:
    return SkillOut(
        id=str(s.id),
        code=s.code,
        name=s.name,
        description=s.description,
        category=s.category,
        icon=s.icon,
        prompt_template=s.prompt_template,
        keywords=list(s.keywords or []),
        enabled=s.enabled,
        is_system=s.is_system,
        sort_order=s.sort_order,
        created_at=s.created_at.isoformat(),
    )


async def list_enabled_skills(db: AsyncSession) -> list[AISkill]:
    result = await db.execute(
        select(AISkill)
        .where(AISkill.is_deleted.is_(False), AISkill.enabled.is_(True))
        .order_by(AISkill.sort_order, AISkill.created_at)
    )
    return list(result.scalars())


async def get_skill_by_code(db: AsyncSession, code: str) -> AISkill | None:
    result = await db.execute(
        select(AISkill).where(
            AISkill.code == code, AISkill.is_deleted.is_(False), AISkill.enabled.is_(True)
        )
    )
    return result.scalars().first()


@router.get("", response_model=list[SkillOut])
async def list_skills(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[SkillOut]:
    result = await db.execute(
        select(AISkill)
        .where(AISkill.is_deleted.is_(False))
        .order_by(AISkill.sort_order, AISkill.created_at)
    )
    return [_out(s) for s in result.scalars()]


@router.post("", response_model=SkillOut)
async def create_skill(
    body: SkillIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> SkillOut:
    exists = (
        await db.execute(select(AISkill).where(AISkill.code == body.code, AISkill.is_deleted.is_(False)))
    ).scalars().first()
    if exists is not None:
        raise HTTPException(status_code=400, detail=f"技能代码已存在: {body.code}")
    skill = AISkill(is_system=False, sort_order=100, **body.model_dump())
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return _out(skill)


@router.put("/{skill_id}", response_model=SkillOut)
async def update_skill(
    skill_id: UUID,
    body: SkillIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> SkillOut:
    skill = await db.get(AISkill, skill_id)
    if skill is None or skill.is_deleted:
        raise HTTPException(status_code=404, detail="技能不存在")
    data = body.model_dump()
    if skill.is_system and data["code"] != skill.code:
        raise HTTPException(status_code=400, detail="系统技能不允许修改代码")
    if data["code"] != skill.code:
        clash = (
            await db.execute(select(AISkill).where(AISkill.code == data["code"], AISkill.is_deleted.is_(False)))
        ).scalars().first()
        if clash is not None:
            raise HTTPException(status_code=400, detail=f"技能代码已存在: {data['code']}")
    for key, value in data.items():
        setattr(skill, key, value)
    await db.commit()
    await db.refresh(skill)
    return _out(skill)


@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    skill = await db.get(AISkill, skill_id)
    if skill is None or skill.is_deleted:
        raise HTTPException(status_code=404, detail="技能不存在")
    if skill.is_system:
        raise HTTPException(status_code=400, detail="系统技能不允许删除")
    skill.is_deleted = True
    await db.commit()
    return {"ok": True}


@router.post("/resolve", response_model=list[SkillCandidateOut])
async def resolve_skills(
    body: SkillResolveIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[SkillCandidateOut]:
    """轻量技能编排：按关键词命中打分，返回 top-K 候选（对齐 AIIgnitePLM /ai/skills/resolve）。"""
    query = body.query.lower()
    if not query.strip():
        return []
    bound_codes: set[str] = set()
    if body.assistant_id is not None:
        assistant = await db.get(AIAssistant, body.assistant_id)
        if assistant is not None:
            bound_codes = set(assistant.skill_codes or [])

    candidates: list[SkillCandidateOut] = []
    for skill in await list_enabled_skills(db):
        if skill.code in body.exclude_codes:
            continue
        score = 0
        reasons: list[str] = []
        if skill.code.lower() in query:
            score += 50
            reasons.append(f"code:{skill.code}")
        if skill.name and skill.name.lower() in query:
            score += 40
            reasons.append(f"keyword:{skill.name}")
        for kw in skill.keywords or []:
            if kw and kw.lower() in query:
                score += 15
                reasons.append(f"keyword:{kw}")
        if skill.code in bound_codes:
            score += 10
            reasons.append("assistant")
        if score >= MIN_SCORE:
            candidates.append(
                SkillCandidateOut(
                    code=skill.code,
                    name=skill.name,
                    description=skill.description,
                    icon=skill.icon,
                    score=min(score, 100),
                    reasons=reasons[:4],
                )
            )
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[: max(1, body.top_k)]
