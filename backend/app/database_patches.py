"""模型扩展列的幂等迁移（create_all 不会为已存在表加列，alembic 引入前的过渡方案）。"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

_STATEMENTS = [
    "ALTER TABLE alt_connections ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ",
    "ALTER TABLE alt_connections ADD COLUMN IF NOT EXISTS last_error TEXT DEFAULT ''",
    "ALTER TABLE alt_connections ADD COLUMN IF NOT EXISTS info JSONB DEFAULT '{}'::jsonb",
]


async def ensure_extra_columns(conn: AsyncConnection) -> None:
    for stmt in _STATEMENTS:
        try:
            await conn.execute(text(stmt))
        except Exception as exc:  # noqa: BLE001 —— 已存在/非 PG 时忽略
            logger.debug("ensure_extra_columns skip: %s", exc)
