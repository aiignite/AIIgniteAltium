import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.ai.conversation import Conversation, Message
from app.models.system.user import User
from app.schemas import CamelModel
from app.security import get_current_user
from app.services.ai.orchestrator import stream_reply

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])


class ChatStreamIn(CamelModel):
    content: str = Field(min_length=1, max_length=20000)
    conversation_id: UUID | None = None
    project_id: UUID | None = None
    assistant_id: UUID | None = None
    skill: str | None = None  # 兼容旧客户端：单技能 code
    skills: list[str] | None = None  # 技能 code 列表（优先于 skill）
    model_config_id: UUID | None = None


class ConversationOut(CamelModel):
    id: str
    title: str
    project_id: str | None
    assistant_id: str | None
    skill: str
    message_count: int
    created_at: str
    updated_at: str


class MessageOut(CamelModel):
    id: str
    role: str
    content: str
    skill: str
    skills: list[dict] = []
    assistant_name: str = ""
    provider: str
    created_at: str
    duration_ms: int


def _conv_out(c: Conversation) -> ConversationOut:
    return ConversationOut(
        id=str(c.id),
        title=c.title,
        project_id=str(c.project_id) if c.project_id else None,
        assistant_id=str(c.assistant_id) if c.assistant_id else None,
        skill=c.skill,
        message_count=c.message_count,
        created_at=c.created_at.isoformat(),
        updated_at=c.updated_at.isoformat(),
    )


def _msg_out(m: Message) -> MessageOut:
    meta = m.meta or {}
    return MessageOut(
        id=str(m.id),
        role=m.role,
        content=m.content,
        skill=m.skill,
        skills=list(meta.get("skills") or []),
        assistant_name=str(meta.get("assistantName") or ""),
        provider=m.provider,
        created_at=m.created_at.isoformat(),
        duration_ms=m.duration_ms,
    )


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    async def event_source():
        async for event in stream_reply(
            db,
            user_id=user.id,
            content=body.content,
            conversation_id=body.conversation_id,
            project_id=body.project_id,
            skill=body.skill,
            skills=body.skills,
            assistant_id=body.assistant_id,
            model_config_id=body.model_config_id,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationOut]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.is_deleted.is_(False))
        .order_by(Conversation.updated_at.desc())
        .limit(100)
    )
    return [_conv_out(c) for c in result.scalars()]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.is_deleted or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="对话不存在")
    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.seq)
    )
    return [_msg_out(m) for m in result.scalars()]


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="对话不存在")
    conversation.is_deleted = True
    await db.commit()
    return {"ok": True}
