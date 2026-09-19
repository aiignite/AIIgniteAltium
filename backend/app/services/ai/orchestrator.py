"""编排器：助手人设 + 技能提示词 + 设计上下文 + 历史 → provider 流式输出。"""

import logging
import time
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.ai.ai_model import AIModelConfig
from app.models.ai.assistant import AIAssistant, AISkill
from app.models.ai.conversation import Conversation, Message
from app.models.files.uploaded_project import UploadedProject
from app.services.ai import providers
from app.services.ai.design_context import build_design_context
from app.services.ai.skill_registry import BASE_PROMPT

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 20


async def _try_live_context() -> str:
    """无离线工程时，尝试从已连接 gateway 取实时设计摘要（失败静默）。"""
    try:
        from sqlalchemy import select

        from app.models.altium.connection import GatewayConnection
        from app.services.ai.design_context import live_summary_to_context

        async with async_session_maker() as session:
            result = await session.execute(
                select(GatewayConnection)
                .where(GatewayConnection.status == "connected", GatewayConnection.is_deleted.is_(False))
                .order_by(GatewayConnection.created_at)
                .limit(1)
            )
            conn = result.scalars().first()
        if conn is None:
            return ""
        from app.services.altium.gateway_client import GatewayClient

        summary = await GatewayClient(conn.base_url, conn.api_token).live_summary()
        return live_summary_to_context(summary)
    except Exception as exc:  # noqa: BLE001 —— 实时上下文失败不影响对话
        logger.info("live context unavailable: %s", exc)
        return ""


async def resolve_model_config(
    db: AsyncSession, model_config_id: UUID | None, assistant: AIAssistant | None = None
) -> AIModelConfig:
    for candidate_id in (model_config_id, assistant.model_config_id if assistant else None):
        if candidate_id is not None:
            cfg = await db.get(AIModelConfig, candidate_id)
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


async def resolve_assistant(db: AsyncSession, assistant_id: UUID | None) -> AIAssistant | None:
    if assistant_id is not None:
        assistant = await db.get(AIAssistant, assistant_id)
        if assistant is not None and not assistant.is_deleted and assistant.enabled:
            return assistant
    result = await db.execute(
        select(AIAssistant)
        .where(
            AIAssistant.is_default.is_(True),
            AIAssistant.is_deleted.is_(False),
            AIAssistant.enabled.is_(True),
        )
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


async def load_skills(db: AsyncSession, codes: list[str]) -> list:
    """按给定 code 顺序加载启用技能（未知 code 静默丢弃）。"""
    from app.services.ai.seed_data import SEED_SKILLS

    result = await db.execute(
        select(AISkill).where(AISkill.is_deleted.is_(False), AISkill.enabled.is_(True))
    )
    by_code = {s.code: s for s in result.scalars()}
    skills = [by_code[c] for c in codes if c in by_code]
    # DB 无技能数据时回退种子定义（初始化前的极端情况）
    if not skills and codes:
        seed_by_code = {s["code"]: s for s in SEED_SKILLS}
        skills = [seed_by_code[c] for c in codes if c in seed_by_code]  # type: ignore[assignment]
    return skills


def compose_system_prompt(assistant: AIAssistant | None, skills: list, context_text: str) -> str:
    parts = [BASE_PROMPT]
    if assistant is not None and assistant.system_prompt.strip():
        parts.append("【助手设定】\n" + assistant.system_prompt.strip())
    for skill in skills:
        template = skill.prompt_template if hasattr(skill, "prompt_template") else skill["prompt_template"]
        name = skill.name if hasattr(skill, "name") else skill["name"]
        if template.strip():
            parts.append(f"【技能：{name}】\n" + template.strip())
    if context_text:
        parts.append("【设计上下文】\n" + context_text)
    return "\n\n".join(parts)


async def build_messages(
    db: AsyncSession,
    *,
    conversation: Conversation,
    content: str,
    project_id: UUID | None,
    assistant: AIAssistant | None,
    skills: list,
) -> tuple[list[dict], str]:
    context_text = ""
    if project_id is not None:
        project = await db.get(UploadedProject, project_id)
        if project is not None and project.snapshot:
            context_text = build_design_context(project.snapshot)
    else:
        context_text = await _try_live_context()
    system = compose_system_prompt(assistant, skills, context_text)

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
    skill: str | None = None,
    skills: list[str] | None = None,
    assistant_id: UUID | None = None,
    model_config_id: UUID | None = None,
) -> AsyncGenerator[dict, None]:
    """产出事件流：meta / skills_activated / delta / error / done（同时负责消息持久化）。"""
    started = time.time()
    try:
        assistant = await resolve_assistant(db, assistant_id)
        skill_codes = [c for c in (skills or ([skill] if skill else [])) if c]
        # 去重保序
        skill_codes = list(dict.fromkeys(skill_codes))
        loaded_skills = await load_skills(db, skill_codes)
        skill_payload = [
            {"code": (s.code if hasattr(s, "code") else s["code"]),
             "name": (s.name if hasattr(s, "name") else s["name"]),
             "description": (s.description if hasattr(s, "description") else s.get("description", ""))}
            for s in loaded_skills
        ]

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
                assistant_id=assistant.id if assistant else None,
                skill=skill_codes[0] if skill_codes else "",
            )
            db.add(conversation)
            await db.flush()
        conversation.assistant_id = assistant.id if assistant else None
        conversation.skill = skill_codes[0] if skill_codes else ""
        if project_id is not None:
            conversation.project_id = project_id
        if model_config_id is not None:
            conversation.model_config_id = model_config_id

        cfg = await resolve_model_config(
            db,
            model_config_id if model_config_id is not None else conversation.model_config_id,
            assistant,
        )
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

        yield {
            "type": "meta",
            "conversationId": str(conversation.id),
            "title": conversation.title,
            "assistantId": str(assistant.id) if assistant else None,
            "assistantName": assistant.name if assistant else "通用助手",
        }
        if skill_payload:
            yield {"type": "skills_activated", "skills": skill_payload}

        messages, _system = await build_messages(
            db,
            conversation=conversation,
            content=content,
            project_id=conversation.project_id,
            assistant=assistant,
            skills=loaded_skills,
        )
        assistant_message = Message(
            conversation_id=conversation.id,
            seq=conversation.message_count + 1,
            role="assistant",
            content="",
            skill=conversation.skill,
            model_config_id=cfg.id,
            provider=cfg.provider,
            meta={
                "skills": skill_payload,
                "assistantId": str(assistant.id) if assistant else None,
                "assistantName": assistant.name if assistant else "通用助手",
            },
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
        if assistant is not None:
            assistant.usage_count += 1
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
