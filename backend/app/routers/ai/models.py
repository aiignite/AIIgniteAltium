from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.ai.ai_model import AIModelConfig
from app.schemas import CamelModel
from app.security import get_current_user

router = APIRouter(prefix="/ai/models", tags=["ai-models"])

PROVIDERS = {"mock": "演示引擎", "openai": "OpenAI 兼容", "anthropic": "Anthropic"}


class ModelIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    provider: str
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""
    is_default: bool = False
    enabled: bool = True
    remark: str = ""


class ModelOut(ModelIn):
    id: str
    created_at: str


def _out(cfg: AIModelConfig) -> ModelOut:
    return ModelOut(
        id=str(cfg.id),
        name=cfg.name,
        provider=cfg.provider,
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model_name=cfg.model_name,
        is_default=cfg.is_default,
        enabled=cfg.enabled,
        remark=cfg.remark,
        created_at=cfg.created_at.isoformat(),
    )


async def _clear_default(db: AsyncSession, exclude_id: UUID | None = None) -> None:
    result = await db.execute(
        select(AIModelConfig).where(AIModelConfig.is_default.is_(True), AIModelConfig.is_deleted.is_(False))
    )
    for cfg in result.scalars():
        if exclude_id is None or cfg.id != exclude_id:
            cfg.is_default = False


@router.get("", response_model=list[ModelOut])
async def list_models(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[ModelOut]:
    result = await db.execute(
        select(AIModelConfig).where(AIModelConfig.is_deleted.is_(False)).order_by(AIModelConfig.sort_order, AIModelConfig.created_at)
    )
    return [_out(c) for c in result.scalars()]


@router.post("", response_model=ModelOut)
async def create_model(
    body: ModelIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> ModelOut:
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"provider 须为 {'/'.join(PROVIDERS)}")
    cfg = AIModelConfig(**body.model_dump())
    if body.is_default:
        await _clear_default(db)
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return _out(cfg)


@router.put("/{model_id}", response_model=ModelOut)
async def update_model(
    model_id: UUID,
    body: ModelIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> ModelOut:
    cfg = await db.get(AIModelConfig, model_id)
    if cfg is None or cfg.is_deleted:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"provider 须为 {'/'.join(PROVIDERS)}")
    for key, value in body.model_dump().items():
        setattr(cfg, key, value)
    if body.is_default:
        await _clear_default(db, exclude_id=cfg.id)
    await db.commit()
    await db.refresh(cfg)
    return _out(cfg)


@router.delete("/{model_id}")
async def delete_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    cfg = await db.get(AIModelConfig, model_id)
    if cfg is None or cfg.is_deleted:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    cfg.is_deleted = True
    if cfg.is_default:
        cfg.is_default = False
    await db.commit()
    return {"ok": True}
