import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai.ai_model import AIModelConfig
from app.models.ai.assistant import AIAssistant, AISkill
from app.models.ai.conversation import Conversation, Message
from app.services.ai import providers
from app.services.ai.access import authorize_chat_sources
from app.services.ai.design_context import build_design_context, live_summary_to_context
from app.services.ai.skill_registry import BASE_PROMPT
from app.services.altium.access import get_accessible_connection
from app.services.altium.gateway_client import GatewayClient, GatewayError
from app.services.files.access import get_owned_project
from app.services.system.credentials import validate_credential
from app.services.system.outbound import validate_outbound_url

logger = logging.getLogger(__name__)
MAX_HISTORY_MESSAGES = 20
# 流式生成期间定期落库，客户端断开或进程崩溃时也保留已生成内容
PARTIAL_COMMIT_SECONDS = 2.0


def _finish_message(message: Message, text: str, started_at: float, *, error: str = "") -> None:
    message.content = text
    message.error = error[:4000]
    message.duration_ms = int((time.time() - started_at) * 1000)
    message.finished_at = datetime.now(timezone.utc)


async def _persist_partial(db: AsyncSession, message: Message | None, text: str, started_at: float, error: str) -> None:
    """清理失败事务后保存已生成内容；失败不影响错误事件返回。"""
    try:
        await db.rollback()
        if message is None:
            return
        _finish_message(message, text, started_at, error=error)
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("persist partial assistant message failed")
        await db.rollback()


def default_base_url(provider: str) -> str:
    return {"anthropic": "https://api.anthropic.com", "openai": "https://api.openai.com/v1"}.get(provider, "")


async def resolve_model_config(db: AsyncSession, model_config_id: UUID | None,
                               assistant: AIAssistant | None = None) -> AIModelConfig:
    candidate = model_config_id if model_config_id is not None else assistant.model_config_id if assistant else None
    if candidate is not None:
        cfg = await db.get(AIModelConfig, candidate)
        if cfg is None or cfg.is_deleted or not cfg.enabled:
            raise HTTPException(400, "Selected model is unavailable")
        return cfg
    result = await db.execute(select(AIModelConfig).where(
        AIModelConfig.is_deleted.is_(False), AIModelConfig.enabled.is_(True),
    ).order_by(AIModelConfig.is_default.desc(), AIModelConfig.sort_order, AIModelConfig.created_at).limit(1))
    cfg = result.scalars().first()
    if cfg is None:
        raise HTTPException(400, "No enabled model is configured")
    return cfg


async def resolve_assistant(db: AsyncSession, assistant_id: UUID | None) -> AIAssistant | None:
    if assistant_id is not None:
        assistant = await db.get(AIAssistant, assistant_id)
        if assistant is None or assistant.is_deleted or not assistant.enabled:
            raise HTTPException(400, "Selected assistant is unavailable")
        return assistant
    result = await db.execute(select(AIAssistant).where(
        AIAssistant.is_deleted.is_(False), AIAssistant.enabled.is_(True),
    ).order_by(AIAssistant.is_default.desc(), AIAssistant.sort_order, AIAssistant.created_at).limit(1))
    return result.scalars().first()


async def preflight_chat(db: AsyncSession, *, user_id: UUID, conversation_id: UUID | None,
                         project_id: UUID | None, connection_id: UUID | None = None,
                         assistant_id: UUID | None = None, model_config_id: UUID | None = None):
    conversation = await authorize_chat_sources(db, user_id=user_id, conversation_id=conversation_id,
                                               project_id=project_id, connection_id=connection_id)
    assistant = await resolve_assistant(db, assistant_id if assistant_id else conversation.assistant_id if conversation else None)
    cfg = await resolve_model_config(db, model_config_id if model_config_id else conversation.model_config_id if conversation else None, assistant)
    if cfg.provider not in {"mock", "openai", "anthropic"}:
        raise HTTPException(400, "Unsupported provider")
    if cfg.provider != "mock":
        await validate_outbound_url(cfg.base_url or default_base_url(cfg.provider))
        validate_credential(cfg.api_key)
    effective_connection = conversation.connection_id if conversation else connection_id
    if effective_connection:
        conn = await get_accessible_connection(db, effective_connection, user_id)
        await validate_outbound_url(conn.base_url)
        validate_credential(conn.api_token)
    return conversation, assistant, cfg


async def load_skills(db: AsyncSession, codes: list[str]) -> list:
    result = await db.execute(select(AISkill).where(AISkill.is_deleted.is_(False), AISkill.enabled.is_(True)))
    by_code = {s.code: s for s in result.scalars()}
    return [by_code[c] for c in codes if c in by_code]


def compose_system_prompt(assistant: AIAssistant | None, skills: list, context_text: str) -> str:
    parts = [BASE_PROMPT]
    if assistant is not None and assistant.system_prompt.strip():
        parts.append("【助手设定】\n" + assistant.system_prompt.strip())
    for skill in skills:
        if skill.prompt_template.strip():
            parts.append(f"【技能：{skill.name}】\n" + skill.prompt_template.strip())
    if context_text:
        parts.append("【设计上下文】\n" + context_text)
    return "\n\n".join(parts)


async def build_messages(db: AsyncSession, *, conversation: Conversation, user_id: UUID, content: str,
                         assistant: AIAssistant | None, skills: list) -> tuple[list[dict], str]:
    await authorize_chat_sources(db, user_id=user_id, conversation_id=conversation.id, project_id=None, connection_id=None)
    context_text = ""
    if conversation.project_id is not None:
        project = await get_owned_project(db, conversation.project_id, user_id)
        context_text = build_design_context(project.snapshot or {})
    elif conversation.connection_id is not None:
        conn = await get_accessible_connection(db, conversation.connection_id, user_id)
        context_text = live_summary_to_context(await GatewayClient(conn.base_url, conn.api_token).live_summary())
    system = compose_system_prompt(assistant, skills, context_text)
    result = await db.execute(select(Message).where(
        Message.conversation_id == conversation.id, Message.role.in_(["user", "assistant"]),
        Message.error == "", Message.seq <= conversation.message_count,
    ).order_by(Message.seq.desc()).limit(MAX_HISTORY_MESSAGES))
    messages = [{"role": "system", "content": system}]
    messages.extend({"role": m.role, "content": m.content} for m in list(result.scalars())[::-1])
    messages.append({"role": "user", "content": content})
    return messages, system


async def stream_reply(db: AsyncSession, *, user_id: UUID, content: str, conversation_id: UUID | None,
                       project_id: UUID | None, connection_id: UUID | None = None, skill: str | None = None,
                       skills: list[str] | None = None, assistant_id: UUID | None = None,
                       model_config_id: UUID | None = None) -> AsyncGenerator[dict, None]:
    started = time.time()
    assistant_message: Message | None = None
    accumulated: list[str] = []
    try:
        conversation, assistant, cfg = await preflight_chat(
            db, user_id=user_id, conversation_id=conversation_id, project_id=project_id,
            connection_id=connection_id, assistant_id=assistant_id, model_config_id=model_config_id,
        )
        skill_codes = list(dict.fromkeys(c for c in (skills or ([skill] if skill else [])) if c))
        loaded_skills = await load_skills(db, skill_codes)
        skill_payload = [{"code": s.code, "name": s.name, "description": s.description} for s in loaded_skills]
        if conversation is None:
            conversation = Conversation(id=uuid4(), user_id=user_id, title=content.strip()[:40] or "新对话",
                                        project_id=project_id, connection_id=connection_id, model_config_id=cfg.id,
                                        assistant_id=assistant.id if assistant else None, skill=skill_codes[0] if skill_codes else "")
            db.add(conversation)
            await db.flush()
        messages, system = await build_messages(db, conversation=conversation, user_id=user_id, content=content,
                                                assistant=assistant, skills=loaded_skills)
        conversation.assistant_id = assistant.id if assistant else None
        conversation.model_config_id = cfg.id
        conversation.skill = skill_codes[0] if skill_codes else ""
        db.add(Message(conversation_id=conversation.id, seq=conversation.message_count + 1, role="user",
                       content=content, skill=conversation.skill))
        conversation.message_count += 1
        assistant_message = Message(conversation_id=conversation.id, seq=conversation.message_count + 1,
                                    role="assistant", content="", skill=conversation.skill, model_config_id=cfg.id,
                                    provider=cfg.provider, meta={"skills": skill_payload,
                                    "assistantId": str(assistant.id) if assistant else None,
                                    "assistantName": assistant.name if assistant else "通用助手"})
        db.add(assistant_message)
        conversation.message_count += 1
        await db.flush()
        # 先提交用户消息与助手占位符，保证流中断后对话仍可见
        await db.commit()
        yield {"type": "meta", "conversationId": str(conversation.id), "title": conversation.title,
               "assistantId": str(assistant.id) if assistant else None, "assistantName": assistant.name if assistant else "通用助手"}
        if skill_payload:
            yield {"type": "skills_activated", "skills": skill_payload}
        last_flush = time.monotonic()
        async for delta in providers.stream_chat(cfg.provider, base_url=cfg.base_url or default_base_url(cfg.provider),
                                                 api_key=cfg.api_key, model=cfg.model_name or "default",
                                                 messages=messages, system=system):
            accumulated.append(delta)
            if time.monotonic() - last_flush >= PARTIAL_COMMIT_SECONDS:
                assistant_message.content = "".join(accumulated)
                assistant_message.duration_ms = int((time.time() - started) * 1000)
                await db.commit()
                last_flush = time.monotonic()
            yield {"type": "delta", "text": delta}
        _finish_message(assistant_message, "".join(accumulated), started)
        if assistant is not None:
            assistant.usage_count += 1
        await db.commit()
        yield {"type": "done", "messageId": str(assistant_message.id), "durationMs": assistant_message.duration_ms}
    except (GeneratorExit, asyncio.CancelledError):
        await _persist_partial(db, assistant_message, "".join(accumulated), started, "cancelled")
        raise
    except Exception as exc:
        request_id = uuid4().hex
        if isinstance(exc, (providers.ProviderError, GatewayError)):
            message = str(exc)
            request_id = exc.request_id
        elif isinstance(exc, HTTPException):
            message = str(exc.detail)
        else:
            message = "chat_failed"
        logger.warning("chat failed category=%s requestId=%s", type(exc).__name__, request_id)
        await _persist_partial(db, assistant_message, "".join(accumulated), started, message)
        done = {"type": "done"}
        if assistant_message is not None:
            done["messageId"] = str(assistant_message.id)
        yield {"type": "error", "message": message, "requestId": request_id}
        yield done
