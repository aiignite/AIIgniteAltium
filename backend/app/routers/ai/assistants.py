from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.ai.assistant import AIAssistant
from app.models.ai.ai_model import AIModelConfig
from app.schemas import CamelModel
from app.security import get_current_user

router = APIRouter(prefix="/ai/assistants", tags=["ai-assistants"])


class AssistantIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    avatar: str = "bot"
    category: str = "General"
    system_prompt: str = ""
    skill_codes: list[str] = []
    model_config_id: UUID | None = None
    is_default: bool = False
    enabled: bool = True


class AssistantOut(AssistantIn):
    id: str
    is_system: bool
    usage_count: int
    sort_order: int = 0
    created_at: str


def _out(a: AIAssistant) -> AssistantOut:
    return AssistantOut(
        id=str(a.id),
        name=a.name,
        description=a.description,
        avatar=a.avatar,
        category=a.category,
        system_prompt=a.system_prompt,
        skill_codes=list(a.skill_codes or []),
        model_config_id=str(a.model_config_id) if a.model_config_id else None,
        is_default=a.is_default,
        enabled=a.enabled,
        is_system=a.is_system,
        usage_count=a.usage_count,
        sort_order=a.sort_order,
        created_at=a.created_at.isoformat(),
    )


async def _clear_default(db: AsyncSession, exclude_id: UUID | None = None) -> None:
    result = await db.execute(
        select(AIAssistant).where(AIAssistant.is_default.is_(True), AIAssistant.is_deleted.is_(False))
    )
    for a in result.scalars():
        if exclude_id is None or a.id != exclude_id:
            a.is_default = False


async def get_default_assistant(db: AsyncSession) -> AIAssistant | None:
    """默认助手 → 任一启用助手（供聊天无 assistant_id 时兜底）。"""
    result = await db.execute(
        select(AIAssistant)
        .where(AIAssistant.is_default.is_(True), AIAssistant.is_deleted.is_(False), AIAssistant.enabled.is_(True))
    )
    assistant = result.scalars().first()
    if assistant is not None:
        return assistant
    result = await db.execute(
        select(AIAssistant)
        .where(AIAssistant.is_deleted.is_(False), AIAssistant.enabled.is_(True))
        .order_by(AIAssistant.sort_order, AIAssistant.created_at)
        .limit(1)
    )
    return result.scalars().first()


@router.get("", response_model=list[AssistantOut])
async def list_assistants(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[AssistantOut]:
    result = await db.execute(
        select(AIAssistant)
        .where(AIAssistant.is_deleted.is_(False))
        .order_by(AIAssistant.sort_order, AIAssistant.created_at)
    )
    return [_out(a) for a in result.scalars()]


@router.post("", response_model=AssistantOut)
async def create_assistant(
    body: AssistantIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> AssistantOut:
    assistant = AIAssistant(is_system=False, sort_order=100, **body.model_dump())
    if body.is_default:
        await _clear_default(db)
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    return _out(assistant)


@router.put("/{assistant_id}", response_model=AssistantOut)
async def update_assistant(
    assistant_id: UUID,
    body: AssistantIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> AssistantOut:
    assistant = await db.get(AIAssistant, assistant_id)
    if assistant is None or assistant.is_deleted:
        raise HTTPException(status_code=404, detail="助手不存在")
    if body.model_config_id is not None:
        cfg = await db.get(AIModelConfig, body.model_config_id)
        if cfg is None or cfg.is_deleted:
            raise HTTPException(status_code=400, detail="绑定的模型配置不存在")
    for key, value in body.model_dump().items():
        setattr(assistant, key, value)
    if body.is_default:
        await _clear_default(db, exclude_id=assistant.id)
    await db.commit()
    await db.refresh(assistant)
    return _out(assistant)


@router.post("/{assistant_id}/default")
async def set_default_assistant(
    assistant_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    assistant = await db.get(AIAssistant, assistant_id)
    if assistant is None or assistant.is_deleted:
        raise HTTPException(status_code=404, detail="助手不存在")
    await _clear_default(db)
    assistant.is_default = True
    await db.commit()
    return {"ok": True}


@router.delete("/{assistant_id}")
async def delete_assistant(
    assistant_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    assistant = await db.get(AIAssistant, assistant_id)
    if assistant is None or assistant.is_deleted:
        raise HTTPException(status_code=404, detail="助手不存在")
    if assistant.is_system:
        raise HTTPException(status_code=400, detail="系统助手不允许删除")
    assistant.is_deleted = True
    if assistant.is_default:
        assistant.is_default = False
    await db.commit()
    return {"ok": True}
