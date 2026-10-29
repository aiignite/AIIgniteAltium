"""AI 平台改造自检（无需数据库）：模型字段 / provider 注册表 / 密钥加密 / 路由与端点。

用法：
    cd backend
    ..\\.venv\\Scripts\\python.exe -B ..\\test\\check_ai_platform.py

退出码 0 = 全部通过。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

CHECKED: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKED.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")


def main() -> int:
    # 1. 应用与端点
    import app.main as main_module

    app = main_module.create_app()
    spec = app.openapi()
    paths = set(spec["paths"])
    expected = {
        "/api/v1/ai/models",
        "/api/v1/ai/models/providers",
        "/api/v1/ai/models/export",
        "/api/v1/ai/models/test",
        "/api/v1/ai/models/{model_id}/test",
        "/api/v1/ai/models/{model_id}/default",
        "/api/v1/ai/models/{model_id}/duplicate",
        "/api/v1/ai/assistants/{assistant_id}/duplicate",
        "/api/v1/ai/assistants/{assistant_id}/prompt-preview",
        "/api/v1/ai/skills/{skill_id}/duplicate",
        "/api/v1/ai/skills/resolve",
        "/api/v1/ai/tools/registry",
    }
    missing = expected - paths
    check("AI 端点齐全", not missing, f"缺少 {sorted(missing)}")

    # 2. 模型列扩容
    from app.models.ai.ai_model import AIModelConfig

    columns = set(AIModelConfig.__table__.columns.keys())
    need_columns = {
        "temperature",
        "max_tokens",
        "top_p",
        "context_window",
        "supports_tools",
        "supports_image",
        "speed",
        "cost",
        "is_system",
        "api_key_enc",
        "key_hint",
        "test_status",
        "test_latency_ms",
        "tested_at",
        "last_error",
    }
    missing_columns = need_columns - columns
    check("模型表新增列", not missing_columns, f"缺少 {sorted(missing_columns)}")

    from app.models.ai.assistant import AIAssistant, AISkill

    check(
        "助手/技能新增列",
        {"temperature", "max_tokens", "tool_codes", "greeting"} <= set(AIAssistant.__table__.columns.keys())
        and {"tool_codes", "priority", "extra_config"} <= set(AISkill.__table__.columns.keys()),
    )

    # 3. 迁移语句
    from app.database_patches import AI_PLATFORM_STATEMENTS

    check(
        "迁移语句可重放",
        len(AI_PLATFORM_STATEMENTS) >= 20
        and all(s.startswith(("ALTER TABLE", "CREATE INDEX")) and "IF NOT EXISTS" in s for s in AI_PLATFORM_STATEMENTS),
        f"{len(AI_PLATFORM_STATEMENTS)} 条",
    )

    # 4. 密钥加密
    from app.services.ai.secret_crypto import decrypt_secret, encrypt_secret, mask_secret, needs_upgrade

    secret = "sk-selftest-1234567890"
    cipher = encrypt_secret(secret)
    check(
        "密钥加密往返",
        cipher.startswith("enc:v1:") and decrypt_secret(cipher) == secret and mask_secret(secret) == "****7890",
    )
    check(
        "历史明文可识别",
        decrypt_secret("plain-key") == "plain-key" and needs_upgrade("plain-key") and not needs_upgrade(cipher),
    )

    # 5. provider 注册表
    from app.services.ai import providers

    ids = [p["id"] for p in providers.list_providers()]
    check("provider 注册表", ids == ["mock", "openai", "ollama", "llamacpp", "anthropic"], str(ids))
    check("预设模板", len(providers.PRESETS) >= 6, f"{len(providers.PRESETS)} 个")
    check(
        "本地引擎免 Key",
        providers.requires_api_key("ollama") is False and providers.requires_api_key("openai") is True,
    )

    # 6. SSRF 校验 + mock 探测
    from app.services.ai.model_probe import probe, validate_target

    check(
        "私网地址策略",
        validate_target("openai", "http://localhost:11434/v1") is not None
        and validate_target("ollama", "http://localhost:11434/v1") is None
        and validate_target("openai", "https://api.deepseek.com/v1") is None,
    )
    mock_result = asyncio.run(probe(provider="mock", model="mock-1"))
    check("mock 连接测试通过", mock_result["ok"] is True, str(mock_result))

    # 7. 路由优先级函数存在
    from app.services.ai import llm_router

    check("LLMRouter 可用", hasattr(llm_router, "resolve") and hasattr(llm_router, "NoAvailableModelError"))

    failed = [name for name, ok, _ in CHECKED if not ok]
    print(f"\n{len(CHECKED) - len(failed)}/{len(CHECKED)} 项通过")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
