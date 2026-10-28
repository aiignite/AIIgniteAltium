from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.altium.connection import ConnectionGrant, GatewayConnection
from app.models.system.user import User


async def active_user(db: AsyncSession, user_id: UUID) -> User:
    user = (await db.execute(select(User).where(User.id == user_id).execution_options(populate_existing=True))).scalar_one_or_none()
    if user is None or user.is_deleted or not user.is_active:
        raise HTTPException(401, "用户不存在或已停用")
    return user


def visible_connections(user: User):
    statement = select(GatewayConnection).where(GatewayConnection.is_deleted.is_(False))
    if not user.is_admin:
        statement = statement.where(exists().where(
            ConnectionGrant.connection_id == GatewayConnection.id, ConnectionGrant.user_id == user.id,
        ))
    return statement


async def get_accessible_connection(db: AsyncSession, connection_id: UUID, user_id: UUID) -> GatewayConnection:
    user = await active_user(db, user_id)
    conn = (await db.execute(visible_connections(user).where(GatewayConnection.id == connection_id))).scalar_one_or_none()
    if conn is None:
        raise HTTPException(404, "连接不存在")
    return conn
