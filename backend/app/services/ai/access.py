from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai.conversation import Conversation
from app.services.altium.access import active_user, get_accessible_connection
from app.services.files.access import get_owned_project


async def get_owned_conversation(db: AsyncSession, conversation_id: UUID, user_id: UUID) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.is_deleted or conversation.user_id != user_id:
        raise HTTPException(404, "对话不存在")
    if conversation.project_id:
        await get_owned_project(db, conversation.project_id, user_id)
    if conversation.connection_id:
        await get_accessible_connection(db, conversation.connection_id, user_id)
    return conversation


async def authorize_chat_sources(db: AsyncSession, *, user_id: UUID, conversation_id: UUID | None,
                                 project_id: UUID | None, connection_id: UUID | None) -> Conversation | None:
    await active_user(db, user_id)
    if project_id is not None and connection_id is not None:
        raise HTTPException(422, "projectId and connectionId are mutually exclusive")
    conversation = await get_owned_conversation(db, conversation_id, user_id) if conversation_id else None
    if project_id is not None:
        await get_owned_project(db, project_id, user_id)
    if connection_id is not None:
        await get_accessible_connection(db, connection_id, user_id)
    if conversation is not None:
        if ((project_id is not None and conversation.project_id != project_id)
                or (connection_id is not None and conversation.connection_id != connection_id)):
            raise HTTPException(409, "Conversation source is fixed; create a new conversation to switch")
    return conversation
