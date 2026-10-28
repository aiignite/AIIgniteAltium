import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models import Conversation, Message
from app.services.ai import providers
from app.services.ai.orchestrator import stream_reply


@pytest.fixture
def factory(db):
    return async_sessionmaker(db.bind, expire_on_commit=False)


def failing_stream(*_args, **_kwargs):
    async def gen():
        yield "第一段"
        raise providers.ProviderError("http", 500)

    return gen()


async def test_messages_persisted_before_stream_completes(actors, db):
    generator = stream_reply(db, user_id=actors["alice"].id, content="hi", conversation_id=None,
                             project_id=None)
    meta = await generator.__anext__()
    assert meta["type"] == "meta"
    conv_id = meta["conversationId"]
    async with async_sessionmaker(db.bind, expire_on_commit=False)() as other:
        rows = (await other.scalars(select(Message).where(Message.conversation_id == conv_id).order_by(Message.seq))).all()
        assert [m.role for m in rows] == ["user", "assistant"]
        assert rows[0].content == "hi" and rows[1].content == ""
        assert rows[1].finished_at is None
    await generator.aclose()


async def test_provider_error_persists_partial_content(actors, db, monkeypatch):
    monkeypatch.setattr(providers, "stream_chat", failing_stream)
    events = [e async for e in stream_reply(db, user_id=actors["alice"].id, content="hi", conversation_id=None,
                                            project_id=None)]
    assert events[-2]["type"] == "error"
    assert events[-1]["type"] == "done" and "messageId" in events[-1]
    conv_id = events[0]["conversationId"]
    conv = await db.get(Conversation, conv_id)
    await db.refresh(conv)
    rows = (await db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.seq))).all()
    assistant = rows[-1]
    assert assistant.content == "第一段"
    assert "provider_http" in assistant.error
    assert assistant.finished_at is not None
    assert conv.message_count == 2


async def test_client_cancel_persists_partial_content(actors, db):
    generator = stream_reply(db, user_id=actors["alice"].id, content="hi", conversation_id=None,
                             project_id=None)
    meta = await generator.__anext__()
    delta = await generator.__anext__()
    assert delta["type"] == "delta"
    await generator.aclose()
    conv_id = meta["conversationId"]
    rows = (await db.scalars(select(Message).where(Message.conversation_id == conv_id).order_by(Message.seq))).all()
    assistant = rows[-1]
    assert assistant.content
    assert assistant.error == "cancelled"
    assert assistant.finished_at is not None


async def test_successful_stream_sets_finished_at(actors, db):
    events = [e async for e in stream_reply(db, user_id=actors["alice"].id, content="hi", conversation_id=None,
                                            project_id=None)]
    done = events[-1]
    assert done["type"] == "done" and done["durationMs"] >= 0
    message = await db.get(Message, done["messageId"])
    await db.refresh(message)
    assert message.content and message.finished_at is not None and message.error == ""
