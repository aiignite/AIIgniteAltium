"""大模型配置 API（对齐 AIDriveNote AI 模型管理）。

安全约定：
- 响应只返回 ``hasKey`` / ``keyHint``，永不回传明文密钥
- 密钥写入即加密（``api_key_enc``），历史明文列 ``api_key`` 写入后置空
- 写操作默认限管理员（``settings.ai_config_write_admin_only``）
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.ai.ai_model import AIModelConfig
from app.schemas import CamelModel
from app.security import get_current_user
from app.services.ai import providers
from app.services.ai.llm_router import effective_api_key
from app.services.ai.model_probe import probe

router = APIRouter(prefix="/ai/models", tags=["ai-models"])

PROVIDER_IDS = tuple(providers.PROVIDER_CLASSES)
SPEEDS = ("Fast", "Medium", "Slow")
COSTS = ("$", "$$", "$$$", "local")


class ModelIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    provider: str = "openai"
    base_url: str = ""
    # 写入用：留空 = 不修改；clear_api_key=True 时显式清除
    api_key: str = ""
    clear_api_key: bool = False
    model_name: str = ""
    temperature: float = Field(default=0.4, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=1_000_000)
    top_p: float = Field(default=1.0, ge=0, le=1)
    context_window: str = ""
    supports_tools: bool = True
    supports_image: bool = False
    speed: str = "Fast"
    cost: str = "$"
    is_default: bool = False
    enabled: bool = True
    remark: str = ""


class ModelOut(CamelModel):
    id: str
    name: str
    provider: str
    provider_name: str
    base_url: str
    model_name: str
    has_key: bool
    key_hint: str
    temperature: float
    max_tokens: int
    top_p: float
    context_window: str
    supports_tools: bool
    supports_image: bool
    speed: str
    cost: str
    is_system: bool
    is_default: bool
    enabled: bool
    remark: str
    sort_order: int
    test_status: str
    test_latency_ms: int
    tested_at: str | None
    last_error: str
    created_at: str


class ModelTestIn(CamelModel):
    """测试连接：传 id 复用已存配置（apiKey 留空则用库内密钥），或直接传临时配置。"""

    id: UUID | None = None
    provider: str | None = None
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""


class ModelTestOut(CamelModel):
    ok: bool
    latency_ms: int
    category: str
    status_code: int | None = None
    error: str = ""
    hint: str = ""
    provider: str = ""
    model: str = ""


def _administrator(user=Depends(get_current_user)):
    if settings.ai_config_write_admin_only and not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="仅管理员可修改 AI 模型配置")
    return user


def _provider_name(provider: str) -> str:
    meta = providers.provider_meta(provider)
    return str(meta["name"]) if meta else provider


def _out(cfg: AIModelConfig) -> ModelOut:
    return ModelOut(
        id=str(cfg.id),
        name=cfg.name,
        provider=cfg.provider,
        provider_name=_provider_name(cfg.provider),
        base_url=cfg.base_url,
        model_name=cfg.model_name,
        has_key=bool(cfg.api_key_enc or cfg.api_key),
        key_hint=cfg.key_hint,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        top_p=cfg.top_p,
        context_window=cfg.context_window,
        supports_tools=cfg.supports_tools,
        supports_image=cfg.supports_image,
        speed=cfg.speed,
        cost=cfg.cost,
        is_system=cfg.is_system,
        is_default=cfg.is_default,
        enabled=cfg.enabled,
        remark=cfg.remark,
        sort_order=cfg.sort_order,
        test_status=cfg.test_status,
        test_latency_ms=cfg.test_latency_ms,
        tested_at=cfg.tested_at.isoformat() if cfg.tested_at else None,
        last_error=cfg.last_error,
        created_at=cfg.created_at.isoformat(),
    )


async def _clear_default(db: AsyncSession, exclude_id: UUID | None = None) -> None:
    result = await db.execute(
        select(AIModelConfig).where(AIModelConfig.is_default.is_(True), AIModelConfig.is_deleted.is_(False))
    )
    for cfg in result.scalars():
        if exclude_id is None or cfg.id != exclude_id:
            cfg.is_default = False


async def _ensure_name_unique(db: AsyncSession, name: str, exclude_id: UUID | None = None) -> None:
    stmt = select(AIModelConfig).where(AIModelConfig.name == name, AIModelConfig.is_deleted.is_(False))
    found = (await db.execute(stmt)).scalars().first()
    if found is not None and (exclude_id is None or found.id != exclude_id):
        raise HTTPException(status_code=400, detail=f"模型名称已存在: {name}")


def _validate_provider(provider: str) -> None:
    if provider not in PROVIDER_IDS:
        raise HTTPException(status_code=400, detail=f"provider 须为 {'/'.join(PROVIDER_IDS)}")


async def _validated_base_url(provider: str, base_url: str) -> str:
    """保存前校验出站地址；mock 无出站，保留原值。"""
    normalized = await providers.validate_provider_base_url(provider, base_url)
    return normalized or base_url


@router.get("", response_model=list[ModelOut])
async def list_models(
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> list[ModelOut]:
    result = await db.execute(
        select(AIModelConfig)
        .where(AIModelConfig.is_deleted.is_(False))
        .order_by(AIModelConfig.sort_order, AIModelConfig.created_at)
    )
    return [_out(c) for c in result.scalars()]


@router.get("/providers")
async def list_providers(_user=Depends(get_current_user)) -> dict:
    """provider 元数据 + 一键模板（前端"快速模板"与默认值来源）。"""
    return {
        "providers": providers.list_providers(),
        "presets": providers.PRESETS,
        "speeds": list(SPEEDS),
        "costs": list(COSTS),
        "defaultTemperature": settings.ai_default_temperature,
        "defaultMaxTokens": settings.ai_default_max_tokens,
    }


@router.get("/export")
async def export_models(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
) -> PlainTextResponse:
    """导出配置（不含密钥，仅 hasKey）。"""
    result = await db.execute(
        select(AIModelConfig)
        .where(AIModelConfig.is_deleted.is_(False))
        .order_by(AIModelConfig.sort_order, AIModelConfig.created_at)
    )
    rows = list(result.scalars())
    if format == "csv":
        header = [
            "name",
            "provider",
            "modelName",
            "baseUrl",
            "temperature",
            "maxTokens",
            "topP",
            "contextWindow",
            "supportsTools",
            "supportsImage",
            "speed",
            "cost",
            "enabled",
            "isDefault",
            "hasKey",
            "remark",
        ]
        lines = [",".join(header)]
        for c in rows:
            values = [
                c.name,
                c.provider,
                c.model_name,
                c.base_url,
                str(c.temperature),
                str(c.max_tokens),
                str(c.top_p),
                c.context_window,
                "Y" if c.supports_tools else "N",
                "Y" if c.supports_image else "N",
                c.speed,
                c.cost,
                "Y" if c.enabled else "N",
                "Y" if c.is_default else "N",
                "Y" if (c.api_key_enc or c.api_key) else "N",
                c.remark,
            ]
            lines.append(",".join(f'"{v.replace(chr(34), chr(34) * 2)}"' for v in values))
        return PlainTextResponse("\ufeff" + "\n".join(lines), media_type="text/csv; charset=utf-8")

    payload = [{k: v for k, v in _out(c).model_dump(by_alias=True).items()} for c in rows]
    return PlainTextResponse(
        json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json; charset=utf-8"
    )


@router.post("/test", response_model=ModelTestOut)
async def test_model_config(
    body: ModelTestIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_administrator),
) -> ModelTestOut:
    """测试未保存/已保存配置。"""
    provider = body.provider or ""
    base_url = body.base_url
    api_key = body.api_key
    model_name = body.model_name
    if body.id is not None:
        cfg = await db.get(AIModelConfig, body.id)
        if cfg is None or cfg.is_deleted:
            raise HTTPException(status_code=404, detail="模型配置不存在")
        provider = provider or cfg.provider
        base_url = base_url or cfg.base_url
        api_key = api_key or effective_api_key(cfg)
        model_name = model_name or cfg.model_name
    if not provider:
        raise HTTPException(status_code=400, detail="缺少 provider")
    _validate_provider(provider)
    result = await probe(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model_name,
        timeout=settings.ai_model_test_timeout,
    )
    return ModelTestOut(**result)


@router.post("", response_model=ModelOut)
async def create_model(
    body: ModelIn,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_administrator),
) -> ModelOut:
    _validate_provider(body.provider)
    await _ensure_name_unique(db, body.name)
    data = body.model_dump(exclude={"api_key", "clear_api_key"})
    data["base_url"] = await _validated_base_url(body.provider, body.base_url)
    cfg = AIModelConfig(**data)
    if body.api_key:
        cfg.bind_key(body.api_key)
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
    _user=Depends(_administrator),
) -> ModelOut:
    cfg = await db.get(AIModelConfig, model_id)
    if cfg is None or cfg.is_deleted:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    _validate_provider(body.provider)
    if cfg.is_system and body.provider != cfg.provider:
        raise HTTPException(status_code=400, detail="系统预设模型不允许修改 provider")
    await _ensure_name_unique(db, body.name, exclude_id=cfg.id)

    for key, value in body.model_dump(exclude={"api_key", "clear_api_key"}).items():
        setattr(cfg, key, value)
    cfg.base_url = await _validated_base_url(body.provider, body.base_url)

    if body.clear_api_key:
        cfg.clear_key()
    elif body.api_key:
        cfg.bind_key(body.api_key)

    if body.is_default:
        await _clear_default(db, exclude_id=cfg.id)
    await db.commit()
    await db.refresh(cfg)
    return _out(cfg)


@router.post("/{model_id}/default")
async def set_default_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_administrator),
) -> dict:
    cfg = await db.get(AIModelConfig, model_id)
    if cfg is None or cfg.is_deleted:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    if not cfg.enabled:
        raise HTTPException(status_code=400, detail="已停用的模型不能设为默认")
    await _clear_default(db)
    cfg.is_default = True
    await db.commit()
    return {"ok": True}


@router.post("/{model_id}/test", response_model=ModelTestOut)
@router.post("/{model_id}/test-connection", response_model=ModelTestOut, include_in_schema=False)
async def test_saved_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_administrator),
) -> ModelTestOut:
    cfg = await db.get(AIModelConfig, model_id)
    if cfg is None or cfg.is_deleted:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    result = await probe(
        provider=cfg.provider,
        base_url=cfg.base_url,
        api_key=effective_api_key(cfg),
        model=cfg.model_name,
        timeout=settings.ai_model_test_timeout,
    )
    cfg.test_status = "ok" if result["ok"] else "fail"
    cfg.test_latency_ms = int(result["latencyMs"])
    cfg.tested_at = datetime.now(timezone.utc)
    cfg.last_error = "" if result["ok"] else str(result.get("error") or "")[:500]
    await db.commit()
    return ModelTestOut(**result)


@router.post("/{model_id}/duplicate", response_model=ModelOut)
async def duplicate_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_administrator),
) -> ModelOut:
    cfg = await db.get(AIModelConfig, model_id)
    if cfg is None or cfg.is_deleted:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    base_name = f"{cfg.name}（副本）"
    name = base_name
    index = 2
    while (await db.execute(
        select(AIModelConfig).where(AIModelConfig.name == name, AIModelConfig.is_deleted.is_(False))
    )).scalars().first() is not None:
        name = f"{base_name}{index}"
        index += 1

    copy = AIModelConfig(
        name=name,
        provider=cfg.provider,
        base_url=cfg.base_url,
        model_name=cfg.model_name,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        top_p=cfg.top_p,
        context_window=cfg.context_window,
        supports_tools=cfg.supports_tools,
        supports_image=cfg.supports_image,
        speed=cfg.speed,
        cost=cfg.cost,
        enabled=cfg.enabled,
        remark=cfg.remark,
        sort_order=cfg.sort_order + 1,
        is_default=False,
        is_system=False,
        api_key_enc=cfg.api_key_enc,
        key_hint=cfg.key_hint,
    )
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    return _out(copy)


@router.delete("/{model_id}")
async def delete_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_administrator),
):
    cfg = await db.get(AIModelConfig, model_id)
    if cfg is None or cfg.is_deleted:
        raise HTTPException(status_code=404, detail="模型配置不存在")
    if cfg.is_system:
        raise HTTPException(status_code=400, detail="系统预设模型不允许删除，可停用或复制后修改")
    cfg.is_deleted = True
    if cfg.is_default:
        cfg.is_default = False
    await db.commit()
    return {"ok": True}
