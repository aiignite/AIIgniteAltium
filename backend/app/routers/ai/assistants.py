from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.ai.ai_model import AIModelConfig
from app.models.ai.assistant import AIAssistant
from app.schemas import CamelModel
from app.security import get_current_user, require_admin

router = APIRouter(prefix="/ai/assistants", tags=["ai-assistants"])


class AssistantIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    avatar: str = "bot"
    category: str = "General"
    system_prompt: str = ""
    greeting: str = ""
    skill_codes: list[str] = []
    tool_codes: list[str] = []
    model_config_id: UUID | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    is_default: bool = False
    enabled: bool = True


class AssistantOut(AssistantIn):
    id: str
    is_system: bool
    usage_count: int
    sort_order: int = 0
    created_at: str


class PromptPreviewOut(CamelModel):
    system_prompt: str
    assistant_name: str
    skill_codes: list[str] = []


def _out(a: AIAssistant) -> AssistantOut:
    return AssistantOut(
        id=str(a.id),
        name=a.name,
        description=a.description,
        avatar=a.avatar,
        category=a.category,
        system_prompt=a.system_prompt,
        greeting=a.greeting,
        skill_codes=list(a.skill_codes or []),
        tool_codes=list(a.tool_codes or []),
        model_config_id=str(a.model_config_id) if a.model_config_id else None,
        temperature=a.temperature,
        max_tokens=a.max_tokens,
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


async def _validate_model_binding(db: AsyncSession, model_config_id: UUID | None) -> None:
    if model_config_id is None:
        return
    cfg = await db.get(AIModelConfig, model_config_id)
    if cfg is None or cfg.is_deleted:
        raise HTTPException(status_code=400, detail="绑定的模型配置不存在")


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
    _user=Depends(require_admin),
) -> AssistantOut:
    await _validate_model_binding(db, body.model_config_id)
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
    _user=Depends(require_admin),
) -> AssistantOut:
    assistant = await db.get(AIAssistant, assistant_id)
    if assistant is None or assistant.is_deleted:
        raise HTTPException(status_code=404, detail="助手不存在")
    await _validate_model_binding(db, body.model_config_id)
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
    _user=Depends(require_admin),
):
    assistant = await db.get(AIAssistant, assistant_id)
    if assistant is None or assistant.is_deleted:
        raise HTTPException(status_code=404, detail="助手不存在")
    await _clear_default(db)
    assistant.is_default = True
    await db.commit()
    return {"ok": True}


@router.post("/{assistant_id}/duplicate", response_model=AssistantOut)
@router.post("/{assistant_id}/clone", response_model=AssistantOut, include_in_schema=False)
async def duplicate_assistant(
    assistant_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> AssistantOut:
    assistant = await db.get(AIAssistant, assistant_id)
    if assistant is None or assistant.is_deleted:
        raise HTTPException(status_code=404, detail="助手不存在")
    base_name = f"{assistant.name}（副本）"
    name = base_name
    index = 2
    while (await db.execute(
        select(AIAssistant).where(AIAssistant.name == name, AIAssistant.is_deleted.is_(False))
    )).scalars().first() is not None:
        name = f"{base_name}{index}"
        index += 1

    copy = AIAssistant(
        name=name,
        description=assistant.description,
        avatar=assistant.avatar,
        category=assistant.category,
        system_prompt=assistant.system_prompt,
        greeting=assistant.greeting,
        skill_codes=list(assistant.skill_codes or []),
        tool_codes=list(assistant.tool_codes or []),
        model_config_id=assistant.model_config_id,
        temperature=assistant.temperature,
        max_tokens=assistant.max_tokens,
        is_system=False,
        is_default=False,
        enabled=assistant.enabled,
        sort_order=assistant.sort_order + 1,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return _out(copy)


@router.post("/{assistant_id}/prompt-preview", response_model=PromptPreviewOut)
async def preview_prompt(
    assistant_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> PromptPreviewOut:
    """返回该助手实际下发的系统提示词（含 BASE_PROMPT / 人设 / 技能），用于调试人设。"""
    from app.services.ai.orchestrator import compose_system_prompt, load_skills

    assistant = await db.get(AIAssistant, assistant_id)
    if assistant is None or assistant.is_deleted:
        raise HTTPException(status_code=404, detail="助手不存在")
    codes = [c for c in (assistant.skill_codes or []) if c]
    skills = await load_skills(db, codes)
    prompt = compose_system_prompt(assistant, skills, "（对话时此处注入当前工程的设计上下文）")
    return PromptPreviewOut(
        system_prompt=prompt, assistant_name=assistant.name, skill_codes=codes
    )


@router.delete("/{assistant_id}")
async def delete_assistant(
    assistant_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
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
