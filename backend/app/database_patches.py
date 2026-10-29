"""模型扩展列的幂等迁移（create_all 不会为已存在表加列，alembic 引入前的过渡方案）。

单一事实源：``AI_PLATFORM_STATEMENTS`` 同时被启动引导与 ``backend/scripts/migrate_ai_platform.py``
复用，保证两处不会漂移。
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

_STATEMENTS = [
    "ALTER TABLE alt_connections ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ",
    "ALTER TABLE alt_connections ADD COLUMN IF NOT EXISTS last_error TEXT DEFAULT ''",
    "ALTER TABLE alt_connections ADD COLUMN IF NOT EXISTS info JSONB DEFAULT '{}'::jsonb",
    "ALTER TABLE ai_conversations ADD COLUMN IF NOT EXISTS assistant_id UUID",
]

# AI 平台（模型配置页）所需的列与索引；全部 IF NOT EXISTS，可反复执行
AI_PLATFORM_STATEMENTS = [
    # ai_model_configs：采样参数与能力
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS temperature DOUBLE PRECISION NOT NULL DEFAULT 0.4",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS max_tokens INTEGER NOT NULL DEFAULT 4096",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS top_p DOUBLE PRECISION NOT NULL DEFAULT 1.0",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS context_window VARCHAR(20) NOT NULL DEFAULT ''",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS supports_tools BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS supports_image BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS speed VARCHAR(20) NOT NULL DEFAULT 'Fast'",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS cost VARCHAR(20) NOT NULL DEFAULT '$'",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT FALSE",
    # 密钥加密
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS api_key_enc TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS key_hint VARCHAR(20) NOT NULL DEFAULT ''",
    # 连接测试结果
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS test_status VARCHAR(20) NOT NULL DEFAULT ''",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS test_latency_ms INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS tested_at TIMESTAMPTZ",
    "ALTER TABLE ai_model_configs ADD COLUMN IF NOT EXISTS last_error TEXT NOT NULL DEFAULT ''",
    # ai_assistants：采样覆盖与工具子集
    "ALTER TABLE ai_assistants ADD COLUMN IF NOT EXISTS temperature DOUBLE PRECISION",
    "ALTER TABLE ai_assistants ADD COLUMN IF NOT EXISTS max_tokens INTEGER",
    "ALTER TABLE ai_assistants ADD COLUMN IF NOT EXISTS tool_codes JSON NOT NULL DEFAULT '[]'::json",
    "ALTER TABLE ai_assistants ADD COLUMN IF NOT EXISTS greeting TEXT NOT NULL DEFAULT ''",
    # ai_skills：工具子集与优先级
    "ALTER TABLE ai_skills ADD COLUMN IF NOT EXISTS tool_codes JSON NOT NULL DEFAULT '[]'::json",
    "ALTER TABLE ai_skills ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 50",
    "ALTER TABLE ai_skills ADD COLUMN IF NOT EXISTS extra_config JSON NOT NULL DEFAULT '{}'::json",
    # ai_messages：用量统计
    "ALTER TABLE ai_messages ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ai_messages ADD COLUMN IF NOT EXISTS completion_tokens INTEGER NOT NULL DEFAULT 0",
    # 索引
    "CREATE INDEX IF NOT EXISTS ix_ai_model_configs_enabled ON ai_model_configs (is_deleted, enabled)",
    "CREATE INDEX IF NOT EXISTS ix_ai_model_configs_provider ON ai_model_configs (provider)",
]


async def ensure_extra_columns(conn: AsyncConnection) -> None:
    for stmt in [*_STATEMENTS, *AI_PLATFORM_STATEMENTS]:
        try:
            await conn.execute(text(stmt))
        except Exception as exc:  # noqa: BLE001 —— 已存在/非 PG 时忽略
            logger.debug("ensure_extra_columns skip: %s", exc)
