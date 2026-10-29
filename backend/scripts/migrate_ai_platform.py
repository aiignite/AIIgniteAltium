"""AI 平台幂等迁移入口（可独立重放；与启动引导共用同一语句列表）。

用法：
    cd backend
    ..\\.venv\\Scripts\\python.exe scripts\\migrate_ai_platform.py

行为：
1. 逐条执行 ``app.database_patches.AI_PLATFORM_STATEMENTS``（全部 IF NOT EXISTS）
2. 把历史明文 api_key 加密进 api_key_enc，并补种系统预设模型
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.database import async_session_maker, engine  # noqa: E402
from app.database_patches import AI_PLATFORM_STATEMENTS  # noqa: E402


async def main() -> int:
    ok = 0
    failed: list[tuple[str, str]] = []
    async with engine.begin() as conn:
        for stmt in AI_PLATFORM_STATEMENTS:
            try:
                await conn.execute(text(stmt))
                ok += 1
            except Exception as exc:  # noqa: BLE001 —— 记录后继续，最后汇总
                failed.append((stmt, str(exc)))

    async with async_session_maker() as db:
        from app.services.ai.seed_data import seed_models, upgrade_legacy_api_keys

        upgraded = await upgrade_legacy_api_keys(db)
        await seed_models(db)

    print(f"[migrate] 成功 {ok} 条，失败 {len(failed)} 条；密钥升级 {upgraded} 条")
    for stmt, err in failed:
        print(f"  ! {stmt}\n    {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
