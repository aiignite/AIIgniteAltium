"""编排器：助手人设 + 技能提示词 + 设计上下文 + 历史 → provider 流式输出。

模型解析统一走 ``services/ai/llm_router.resolve``（请求 → 会话 → 助手 → 默认 → 兜底）。
可靠性：用户消息与助手占位符在首个 delta 之前提交；流中断/取消时保存已生成内容。
安全：对话/工程/连接按所有者授权，出站地址与密钥在出站前校验。
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_tools import ToolContext, current_tool_context, reset_tool_context, set_tool_context
from app.models.ai.ai_model import AIModelConfig
from app.models.ai.assistant import AIAssistant, AISkill
from app.models.ai.conversation import Conversation, Message
from app.services.ai import providers
from app.services.ai.access import authorize_chat_sources
from app.services.ai.design_context import build_design_context, live_summary_to_context
from app.services.ai.llm_router import NoAvailableModelError, ProviderResolution, resolve
from app.services.ai.skill_registry import BASE_PROMPT
from app.services.altium.access import get_accessible_connection
from app.services.altium.gateway_client import GatewayClient, GatewayError
from app.services.files.access import get_owned_project
from app.services.system.credentials import CredentialError, try_decrypt, validate_credential
from app.services.system.outbound import validate_outbound_url

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 20
MAX_TOOL_ROUNDS = 5
# 流式生成期间定期落库，客户端断开或进程崩溃时也保留已生成内容
PARTIAL_COMMIT_SECONDS = 2.0

_ERROR_CODES = {
    "401": "auth",
    "403": "auth",
    "429": "rate",
    "stream_options": "usage",
}


def _error_code(exc: Exception) -> str:
    text = str(exc)
    for needle, code in _ERROR_CODES.items():
        if needle in text:
            return code
    return "provider"


def default_base_url(provider: str) -> str:
    """兼容旧引用：转发到 provider 注册表。"""
    return providers.default_base_url(provider)


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


async def resolve_assistant(db: AsyncSession, assistant_id: UUID | None) -> AIAssistant | None:
    if assistant_id is not None:
        assistant = await db.get(AIAssistant, assistant_id)
        if assistant is None or assistant.is_deleted or not assistant.enabled:
            raise HTTPException(400, "Selected assistant is unavailable")
        return assistant
    result = await db.execute(select(AIAssistant).where(
        AIAssistant.is_default.is_(True), AIAssistant.is_deleted.is_(False), AIAssistant.enabled.is_(True),
    ))
    assistant = result.scalars().first()
    if assistant is not None:
        return assistant
    result = await db.execute(select(AIAssistant).where(
        AIAssistant.is_deleted.is_(False), AIAssistant.enabled.is_(True),
    ).order_by(AIAssistant.sort_order, AIAssistant.created_at).limit(1))
    return result.scalars().first()


async def load_skills(db: AsyncSession, codes: list[str]) -> list:
    """按给定 code 顺序加载启用技能（未知 code 静默丢弃）。"""
    from app.services.ai.seed_data import SEED_SKILLS

    result = await db.execute(select(AISkill).where(AISkill.is_deleted.is_(False), AISkill.enabled.is_(True)))
    by_code = {s.code: s for s in result.scalars()}
    skills = [by_code[c] for c in codes if c in by_code]
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


async def build_messages(db: AsyncSession, *, conversation: Conversation, content: str,
                         assistant: AIAssistant | None, skills: list) -> tuple[list[dict], str]:
    context_text = ""
    if conversation.project_id is not None:
        project = await get_owned_project(db, conversation.project_id, conversation.user_id)
        if project.snapshot:
            context_text = build_design_context(project.snapshot, query=content)
    elif conversation.connection_id is not None:
        try:
            conn = await get_accessible_connection(db, conversation.connection_id, conversation.user_id)
            summary = await GatewayClient(conn.base_url, conn.api_token).live_summary()
            context_text = live_summary_to_context(summary, content)
        except Exception as exc:  # noqa: BLE001 —— 实时上下文失败不影响对话
            logger.info("live context unavailable: %s", exc)
    if conversation.connection_id is not None:
        context_text = await _append_failed_verifications(db, conversation, context_text)
    system = compose_system_prompt(assistant, skills, context_text)

    result = await db.execute(select(Message).where(
        Message.conversation_id == conversation.id, Message.role.in_(["user", "assistant"]),
        Message.error == "", Message.seq <= conversation.message_count,
    ).order_by(Message.seq.desc()).limit(MAX_HISTORY_MESSAGES))
    messages = [{"role": "system", "content": system}]
    messages.extend({"role": m.role, "content": m.content} for m in list(result.scalars())[::-1])
    messages.append({"role": "user", "content": content})
    return messages, system


async def _append_failed_verifications(db: AsyncSession, conversation: Conversation, context_text: str) -> str:
    """把本会话连接最近的「写后即查未通过」记录回喂模型，驱动自我修正（失败即降级）。"""
    from app.models.altium.audit import AltiumCommandAudit
    from app.services.altium.verification import verification_status, verification_to_context

    try:
        rows = await db.execute(
            select(AltiumCommandAudit)
            .where(
                AltiumCommandAudit.connection_id == conversation.connection_id,
                AltiumCommandAudit.status == "executed",
            )
            .order_by(AltiumCommandAudit.created_at.desc())
            .limit(20)
        )
        flagged = verification_status(list(rows.scalars()))
    except Exception as exc:  # noqa: BLE001 —— 回喂失败不影响对话
        logger.info("verification feedback unavailable: %s", exc)
        return context_text
    if not flagged:
        return context_text
    section = verification_to_context(flagged)
    return f"{context_text}\n\n{section}" if context_text else section


def _skill_tool_allowlist(assistant: AIAssistant | None, skills: list) -> set[str] | None:
    """助手 + 技能的可用工具并集；为空表示不限制。"""
    allowed: set[str] = set(assistant.tool_codes or []) if assistant is not None else set()
    for skill in skills:
        codes = skill.tool_codes if hasattr(skill, "tool_codes") else skill.get("tool_codes") or []
        allowed.update(c for c in (codes or []) if c)
    return allowed or None


async def _build_tools(assistant: AIAssistant | None, skills: list, resolution: ProviderResolution,
                       context: ToolContext) -> list[dict]:
    if not resolution.supports_tools:
        logger.info("model %s 不支持 tools，跳过工具装配", resolution.model_name)
        return []
    try:
        from app.ai_tools import sync_gateway_tools, tool_definitions

        await sync_gateway_tools(context)
        defs = tool_definitions(context)
    except Exception as exc:  # noqa: BLE001 —— 工具装配失败不影响普通对话
        logger.info("tool setup skipped: %s", exc)
        return []

    allowlist = _skill_tool_allowlist(assistant, skills)
    if allowlist is not None:
        defs = [d for d in defs if d["function"]["name"] in allowlist]
    return defs


def _assistant_meta(assistant: AIAssistant | None) -> dict:
    return {
        "assistantId": str(assistant.id) if assistant else None,
        "assistantName": assistant.name if assistant else "通用助手",
    }


def _cipher_broken(value: str) -> bool:
    return bool(value) and value.startswith("enc:v1:") and try_decrypt(value) is None


async def _raise_if_key_unreadable(db: AsyncSession, config_ids: list[UUID | None]) -> None:
    """模型不可用但存在损坏密文时按凭据故障处理（fail-closed，不静默降级）。"""
    for config_id in config_ids:
        if config_id is None:
            continue
        cfg = await db.get(AIModelConfig, config_id)
        if cfg is None:
            continue
        if _cipher_broken(cfg.api_key_enc) or _cipher_broken(cfg.api_key):
            raise CredentialError() from None


async def preflight_chat(db: AsyncSession, *, user_id: UUID, conversation_id: UUID | None,
                         project_id: UUID | None, connection_id: UUID | None = None,
                         assistant_id: UUID | None = None, model_config_id: UUID | None = None):
    """流式开始前的授权与出站校验；模型不可用返回 None 交给出流阶段降级提示。"""
    conversation = await authorize_chat_sources(db, user_id=user_id, conversation_id=conversation_id,
                                               project_id=project_id, connection_id=connection_id)
    assistant = await resolve_assistant(
        db, assistant_id if assistant_id else conversation.assistant_id if conversation else None
    )
    await _raise_if_key_unreadable(db, [
        model_config_id,
        conversation.model_config_id if conversation else None,
        assistant.model_config_id if assistant else None,
    ])
    try:
        resolution = await resolve(
            db,
            model_config_id=model_config_id if model_config_id else conversation.model_config_id if conversation else None,
            conversation=conversation,
            assistant=assistant,
        )
    except NoAvailableModelError:
        await _raise_if_key_unreadable(db, [
            model_config_id,
            conversation.model_config_id if conversation else None,
            assistant.model_config_id if assistant else None,
        ])
        return conversation, assistant, None
    selected = await db.get(AIModelConfig, UUID(resolution.config_id))
    if selected is not None and (_cipher_broken(selected.api_key_enc) or _cipher_broken(selected.api_key)):
        raise CredentialError() from None
    if resolution.provider != "mock":
        await providers.validate_provider_base_url(
            resolution.provider, resolution.base_url or default_base_url(resolution.provider)
        )
    effective_connection = conversation.connection_id if conversation else connection_id
    if effective_connection:
        conn = await get_accessible_connection(db, effective_connection, user_id)
        await validate_outbound_url(conn.base_url)
        validate_credential(conn.api_token)
    return conversation, assistant, resolution


async def stream_reply(db: AsyncSession, *, user_id: UUID, content: str, conversation_id: UUID | None,
                       project_id: UUID | None, connection_id: UUID | None = None, skill: str | None = None,
                       skills: list[str] | None = None, assistant_id: UUID | None = None,
                       model_config_id: UUID | None = None) -> AsyncGenerator[dict, None]:
    """产出事件流：meta / skills_activated / delta / tool_* / error / done（同时负责消息持久化）。"""
    started = time.time()
    assistant_message: Message | None = None
    accumulated: list[str] = []
    context_token = None
    try:
        conversation = await authorize_chat_sources(db, user_id=user_id, conversation_id=conversation_id,
                                                   project_id=project_id, connection_id=connection_id)
        assistant = await resolve_assistant(
            db, assistant_id if assistant_id else conversation.assistant_id if conversation else None
        )
        skill_codes = list(dict.fromkeys(c for c in (skills or ([skill] if skill else [])) if c))
        loaded_skills = await load_skills(db, skill_codes)
        skill_payload = [
            {
                "code": (s.code if hasattr(s, "code") else s["code"]),
                "name": (s.name if hasattr(s, "name") else s["name"]),
                "description": (s.description if hasattr(s, "description") else s.get("description", "")),
            }
            for s in loaded_skills
        ]

        if conversation is None:
            conversation = Conversation(
                id=uuid4(), user_id=user_id, title=content.strip()[:40] or "新对话",
                project_id=project_id, connection_id=connection_id,
                assistant_id=assistant.id if assistant else None, skill=skill_codes[0] if skill_codes else "",
            )
            db.add(conversation)
            await db.flush()
        conversation.assistant_id = assistant.id if assistant else None
        conversation.skill = skill_codes[0] if skill_codes else ""
        if project_id is not None:
            conversation.project_id = project_id
        if connection_id is not None:
            conversation.connection_id = connection_id
        # 工具仅能看到并操作本对话关联的连接/工程，不存在「取第一条在线连接」的隐式路由
        context_token = set_tool_context(ToolContext(user_id=user_id, connection_id=conversation.connection_id,
                                                     project_id=conversation.project_id))

        try:
            resolution = await resolve(
                db,
                model_config_id=model_config_id if model_config_id is not None else conversation.model_config_id,
                conversation=conversation,
                assistant=assistant,
            )
        except NoAvailableModelError as exc:
            await db.rollback()
            yield {"type": "error", "code": "no_model", "message": str(exc)}
            yield {"type": "done"}
            return
        conversation.model_config_id = UUID(resolution.config_id)

        user_message = Message(conversation_id=conversation.id, seq=conversation.message_count + 1, role="user",
                               content=content, skill=conversation.skill)
        db.add(user_message)
        conversation.message_count += 1
        assistant_message = Message(
            conversation_id=conversation.id, seq=conversation.message_count + 1, role="assistant", content="",
            skill=conversation.skill, model_config_id=UUID(resolution.config_id), provider=resolution.provider,
            meta={"skills": skill_payload, **_assistant_meta(assistant), "model": resolution.summary()},
        )
        db.add(assistant_message)
        conversation.message_count += 1
        await db.flush()
        # 先提交用户消息与助手占位符，保证流中断后对话仍可见
        await db.commit()

        yield {
            "type": "meta",
            "conversationId": str(conversation.id),
            "title": conversation.title,
            **_assistant_meta(assistant),
            **resolution.summary(),
        }
        if skill_payload:
            yield {"type": "skills_activated", "skills": skill_payload}

        messages, _system = await build_messages(db, conversation=conversation, content=content,
                                                 assistant=assistant, skills=loaded_skills)
        tool_defs = await _build_tools(assistant, loaded_skills, resolution, current_tool_context())

        tool_messages: list[dict] = []
        tool_log: list[dict] = []
        usage: dict | None = None
        last_flush = time.monotonic()
        for _round in range(MAX_TOOL_ROUNDS):
            pending_calls: list[dict] | None = None
            round_text: list[str] = []
            async for event in providers.stream_chat(
                resolution.provider,
                base_url=resolution.base_url or default_base_url(resolution.provider),
                api_key=resolution.api_key,
                model=resolution.model_name or "default",
                messages=messages + tool_messages,
                tools=tool_defs or None,
                temperature=resolution.temperature,
                max_tokens=resolution.max_tokens,
                top_p=resolution.top_p,
            ):
                if isinstance(event, str):
                    event = {"type": "delta", "text": event}
                if event["type"] == "delta":
                    round_text.append(event["text"])
                    accumulated.append(event["text"])
                    assistant_message.content = "".join(accumulated)
                    if time.monotonic() - last_flush >= PARTIAL_COMMIT_SECONDS:
                        assistant_message.duration_ms = int((time.time() - started) * 1000)
                        await db.commit()
                        last_flush = time.monotonic()
                    yield {"type": "delta", "text": event["text"]}
                elif event["type"] == "usage":
                    usage = event
                elif event["type"] == "tool_calls":
                    pending_calls = event["calls"]
            if not pending_calls:
                if round_text:
                    tool_messages.append({"role": "assistant", "content": "".join(round_text)})
                break
            tool_messages.append(
                {
                    "role": "assistant",
                    "content": "".join(round_text) or None,
                    "tool_calls": [
                        {
                            "id": c["id"],
                            "type": "function",
                            "function": {
                                "name": c["name"],
                                "arguments": json.dumps(c.get("arguments") or {}, ensure_ascii=False),
                            },
                        }
                        for c in pending_calls
                    ],
                }
            )
            from app.ai_tools import registry

            calls = [(call, registry.get(call.get("name", ""))) for call in pending_calls]
            for call, _meta in calls:
                yield {"type": "tool_call", "tool": call.get("name", ""), "params": call.get("arguments") or {}}

            results: list[dict] = []
            readonly = len(calls) > 1 and all(
                meta is not None and not meta["requires_confirmation"] for _call, meta in calls
            )
            if readonly:
                results = list(
                    await asyncio.gather(
                        *(
                            registry.execute(call.get("name", ""), **(call.get("arguments") or {}))
                            for call, _meta in calls
                        )
                    )
                )
                for (call, _meta), result in zip(calls, results):
                    name = call.get("name", "")
                    tool_log.append({"name": name, "params": call.get("arguments") or {}, "result": result})
                    yield {"type": "tool_result", "tool": name, "result": result}
            else:
                for call, meta in calls:
                    name = call.get("name", "")
                    args = call.get("arguments") or {}
                    if meta is None:
                        result = {"success": False, "error": f"未知工具: {name}"}
                        tool_log.append({"name": name, "params": args, "result": result})
                    elif meta["requires_confirmation"]:
                        try:
                            preview_payload = await registry.execute(name, **{**args, "dry_run": True})
                        except Exception as exc:  # noqa: BLE001
                            preview_payload = {"error": f"预览失败: {exc}"}
                        preview = preview_payload.get("preview") or preview_payload.get("error") or "（无预览）"
                        tool_log.append(
                            {"name": name, "params": args, "requiresConfirmation": True, "preview": preview}
                        )
                        yield {
                            "type": "tool_confirmation_required",
                            "tool": name,
                            "params": args,
                            "preview": preview,
                        }
                        result = {
                            "success": False,
                            "requiresConfirmation": True,
                            "preview": preview,
                            "error": "写操作待用户确认：确认后请回复「确认执行」",
                        }
                    else:
                        result = await registry.execute(name, **args)
                        tool_log.append({"name": name, "params": args, "result": result})
                        yield {"type": "tool_result", "tool": name, "result": result}
                    results.append(result)
            if tool_log:
                assistant_message.meta = {**(assistant_message.meta or {}), "toolLog": list(tool_log)}
            for (call, _meta), result in zip(calls, results):
                tool_messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)}
                )

        _finish_message(assistant_message, "".join(accumulated), started)
        if usage:
            assistant_message.prompt_tokens = int(usage.get("promptTokens") or 0)
            assistant_message.completion_tokens = int(usage.get("completionTokens") or 0)
            assistant_message.meta = {**(assistant_message.meta or {}), "usage": usage}
        if assistant is not None:
            assistant.usage_count += 1
        await db.commit()
        yield {
            "type": "done",
            "messageId": str(assistant_message.id),
            "durationMs": assistant_message.duration_ms,
            "usage": usage or None,
        }
    except (GeneratorExit, asyncio.CancelledError):
        await _persist_partial(db, assistant_message, "".join(accumulated), started, "cancelled")
        raise
    except Exception as exc:  # noqa: BLE001 —— 流式通道内兜底，错误回传前端
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
        error: dict = {"type": "error", "code": _error_code(exc), "message": message, "requestId": request_id}
        if isinstance(exc, CredentialError):
            error["code"] = "credential"
        yield error
        done: dict = {"type": "done"}
        if assistant_message is not None:
            done["messageId"] = str(assistant_message.id)
        yield done
    finally:
        if context_token is not None:
            reset_tool_context(context_token)
