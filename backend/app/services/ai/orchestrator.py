"""编排器：技能提示词 + 设计上下文 + 历史 → provider 流式输出。"""

import logging
import time
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai.ai_model import AIModelConfig
from app.models.ai.conversation import Conversation, Message
from app.models.files.uploaded_project import UploadedProject
from app.services.ai import providers
from app.services.ai.design_context import build_design_context
from app.services.ai.skill_registry import get_skill

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 20


async def resolve_model_config(db: AsyncSession, model_config_id: UUID | None) -> AIModelConfig:
    if model_config_id is not None:
        cfg = await db.get(AIModelConfig, model_config_id)
        if cfg is not None and not cfg.is_deleted and cfg.enabled:
            return cfg
    result = await db.execute(
        select(AIModelConfig).where(
            AIModelConfig.is_default.is_(True),
            AIModelConfig.is_deleted.is_(False),
            AIModelConfig.enabled.is_(True),
        )
    )
    cfg = result.scalars().first()
    if cfg is None:
        result = await db.execute(
            select(AIModelConfig).where(AIModelConfig.is_deleted.is_(False)).limit(1)
        )
        cfg = result.scalars().first()
    if cfg is None:
        raise RuntimeError("未配置任何 AI 模型，请先在设置页添加")
    return cfg


async def build_messages(
    db: AsyncSession,
    *,
    conversation: Conversation,
    content: str,
    project_id: UUID | None,
) -> tuple[list[dict], str]:
    skill = get_skill(conversation.skill)
    system = skill.system_prompt
    if project_id is not None:
        project = await db.get(UploadedProject, project_id)
        if project is not None and project.snapshot:
            context_text = build_design_context(project.snapshot)
            if context_text:
                system += "\n\n【设计上下文】\n" + context_text

    result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.role.in_(["user", "assistant"]),
            Message.error == "",
            Message.seq < conversation.message_count,  # 排除刚插入的当前消息
        )
        .order_by(Message.seq.desc())
        .limit(MAX_HISTORY_MESSAGES)
    )
    history = list(result.scalars())[::-1]
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": content})
    return messages, system


async def stream_reply(
    db: AsyncSession,
    *,
    user_id: UUID,
    content: str,
    conversation_id: UUID | None,
    project_id: UUID | None,
    skill: str | None,
    model_config_id: UUID | None,
) -> AsyncGenerator[dict, None]:
    """产出事件流：meta / delta / error / done（同时负责消息持久化）。"""
    started = time.time()
    try:
        if conversation_id is not None:
            conversation = await db.get(Conversation, conversation_id)
            if conversation is None or conversation.is_deleted:
                yield {"type": "error", "message": "对话不存在"}
                return
        else:
            conversation = Conversation(
                id=uuid4(),
                user_id=user_id,
                title=content.strip()[:40] or "新对话",
                project_id=project_id,
                model_config_id=model_config_id,
                skill=skill or "",
            )
            db.add(conversation)
            await db.flush()
        if skill is not None and skill != conversation.skill:
            conversation.skill = skill
        if project_id is not None:
            conversation.project_id = project_id
        if model_config_id is not None:
            conversation.model_config_id = model_config_id

        cfg = await resolve_model_config(db, model_config_id if model_config_id is not None else conversation.model_config_id)
        user_message = Message(
            conversation_id=conversation.id,
            seq=conversation.message_count + 1,
            role="user",
            content=content,
            skill=conversation.skill,
        )
        db.add(user_message)
        conversation.message_count += 1
        await db.flush()

        yield {"type": "meta", "conversationId": str(conversation.id), "title": conversation.title}

        messages, _system = await build_messages(db, conversation=conversation, content=content, project_id=conversation.project_id)
        assistant_message = Message(
            conversation_id=conversation.id,
            seq=conversation.message_count + 1,
            role="assistant",
            content="",
            skill=conversation.skill,
            model_config_id=cfg.id,
            provider=cfg.provider,
        )
        db.add(assistant_message)
        conversation.message_count += 1
        await db.flush()

        accumulated: list[str] = []
        async for delta in providers.stream_chat(
            cfg.provider,
            base_url=cfg.base_url or default_base_url(cfg.provider),
            api_key=cfg.api_key,
            model=cfg.model_name or "default",
            messages=messages,
        ):
            accumulated.append(delta)
            yield {"type": "delta", "text": delta}
        full_text = "".join(accumulated)
        assistant_message.content = full_text
        assistant_message.duration_ms = int((time.time() - started) * 1000)
        await db.commit()
        yield {"type": "done", "messageId": str(assistant_message.id), "durationMs": assistant_message.duration_ms}
    except Exception as exc:  # noqa: BLE001 —— 流式通道内兜底，错误回传前端
        logger.exception("chat stream failed")
        await db.rollback()
        yield {"type": "error", "message": str(exc)}
        yield {"type": "done"}


def default_base_url(provider: str) -> str:
    if provider == "anthropic":
        return "https://api.anthropic.com"
    if provider == "openai":
        return "https://api.openai.com/v1"
    return ""
