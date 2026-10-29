"""AI 平台端到端冒烟（临时 SQLite 库，不依赖 PostgreSQL）。

用法（在仓库根目录执行）：
    .venv\\Scripts\\python.exe -B test\\smoke_ai_platform.py

执行内容：启动 lifespan（建表 + 幂等迁移 + 种子）→ 登录 → 模型 CRUD/测试/导出/默认 →
技能解析 → 助手提示词预览 → mock 模型流式对话。退出码 0 = 全部通过。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 临时库放仓库根（子进程在 backend/ 等子目录被沙箱限制写；根目录可写）
DB_PATH = ROOT / "_smoke_ai.db"
DATA_DIR = ROOT

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["ADMIN_EMAIL"] = "smoke@example.com"
os.environ["ADMIN_PASSWORD"] = "smoke-pass-123"

sys.path.insert(0, str(ROOT / "backend"))

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")


def main() -> int:
    if DB_PATH.exists():
        DB_PATH.unlink()

    from fastapi.testclient import TestClient

    from app.main import app

    try:
        with TestClient(app) as client:
            # 1) 登录（bootstrap 管理员）
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": "smoke@example.com", "password": "smoke-pass-123"},
            )
            check("管理员登录", resp.status_code == 200, f"{resp.status_code} {resp.text[:200]}")
            token = resp.json()["accessToken"]
            headers = {"Authorization": f"Bearer {token}"}

            # 2) providers 元数据
            resp = client.get("/api/v1/ai/models/providers", headers=headers)
            body = resp.json()
            check(
                "provider 元数据与预设",
                resp.status_code == 200 and len(body["providers"]) == 5 and len(body["presets"]) >= 6,
                resp.text[:200],
            )

            # 2.1) 工具注册表（助手/技能工具选择器数据源）
            resp = client.get("/api/v1/ai/tools/registry", headers=headers)
            tool_names = [t["name"] for t in resp.json()] if resp.status_code == 200 else []
            check(
                "工具注册表可用",
                resp.status_code == 200 and "get_live_design_summary" in tool_names,
                resp.text[:200],
            )

            # 3) 种子模型（mock + 3 个预设），响应不含明文密钥
            resp = client.get("/api/v1/ai/models", headers=headers)
            models = resp.json()
            names = {m["name"] for m in models}
            check("种子模型已补种", len(models) >= 4 and "演示引擎（无需 Key）" in names, str(sorted(names)))
            check(
                "响应不含密钥字段",
                all("apiKey" not in m and "apiKeyEnc" not in m for m in models)
                and all("hasKey" in m and "keyHint" in m for m in models),
            )

            # 4) 新建模型 + 密钥加密 + 掩码
            resp = client.post(
                "/api/v1/ai/models",
                headers=headers,
                json={
                    "name": "冒烟-OpenAI",
                    "provider": "openai",
                    "baseUrl": "https://api.openai.com/v1",
                    "modelName": "gpt-4o-mini",
                    "apiKey": "sk-smoke-abcdefgh1234",
                    "temperature": 0.3,
                    "maxTokens": 2048,
                    "supportsTools": True,
                    "remark": "smoke",
                },
            )
            created = resp.json()
            check(
                "新建模型（密钥掩码）",
                resp.status_code == 200 and created["hasKey"] is True and created["keyHint"] == "****1234",
                resp.text[:300],
            )
            model_id = created["id"]

            # 5) 密钥未以明文回传
            resp = client.get("/api/v1/ai/models", headers=headers)
            raw = resp.text
            check("列表中无明文密钥", "sk-smoke" not in raw and "****1234" in raw)

            # 6) 设置为默认
            resp = client.post(f"/api/v1/ai/models/{model_id}/default", headers=headers)
            resp2 = client.get("/api/v1/ai/models", headers=headers)
            defaults = [m for m in resp2.json() if m["isDefault"]]
            check(
                "默认模型互斥",
                resp.status_code == 200 and len(defaults) == 1 and defaults[0]["id"] == model_id,
                str([m["name"] for m in defaults]),
            )

            # 7) 测试连接：mock 必通；未配 Key 的错误归类
            mock_id = next(m["id"] for m in resp2.json() if m["provider"] == "mock")
            resp = client.post(f"/api/v1/ai/models/{mock_id}/test", headers=headers)
            check("mock 连接测试", resp.status_code == 200 and resp.json()["ok"] is True, resp.text[:200])

            resp = client.post(
                "/api/v1/ai/models/test",
                headers=headers,
                json={"provider": "openai", "baseUrl": "https://api.openai.com/v1", "modelName": "gpt-4o-mini"},
            )
            check(
                "缺 Key 归因为 auth",
                resp.status_code == 200 and resp.json()["ok"] is False and resp.json()["category"] == "auth",
                resp.text[:200],
            )

            # 8) 复制 / 导出（不含密钥）
            resp = client.post(f"/api/v1/ai/models/{model_id}/duplicate", headers=headers)
            check("复制模型", resp.status_code == 200 and resp.json()["name"].endswith("（副本）"), resp.text[:200])
            resp = client.get("/api/v1/ai/models/export?format=csv", headers=headers)
            check(
                "导出 CSV 不含密钥",
                resp.status_code == 200 and "sk-smoke" not in resp.text and "hasKey" in resp.text,
                resp.text[:120],
            )

            # 9) 技能解析（含优先级加分）
            resp = client.post(
                "/api/v1/ai/skills/resolve",
                headers=headers,
                json={"query": "帮我做原理图审查，检查位号和封装", "topK": 3},
            )
            candidates = resp.json()
            check(
                "技能解析命中",
                resp.status_code == 200 and any(c["code"] == "schematic-review" for c in candidates),
                resp.text[:300],
            )
            check(
                "优先级参与打分",
                any(r.startswith("priority:") for c in candidates for r in c.get("reasons", [])),
                json.dumps(candidates, ensure_ascii=False)[:300],
            )

            # 10) 助手：新建 + 提示词预览 + 复制
            resp = client.get("/api/v1/ai/assistants", headers=headers)
            assistants = resp.json()
            check("种子助手存在", len(assistants) >= 4, str(len(assistants)))
            first = assistants[0]
            resp = client.post(f"/api/v1/ai/assistants/{first['id']}/prompt-preview", headers=headers)
            preview = resp.json().get("systemPrompt", "")
            check(
                "提示词预览包含基础规则",
                resp.status_code == 200 and "AIDriveAltium" in preview,
                preview[:120],
            )
            resp = client.post(
                "/api/v1/ai/assistants",
                headers=headers,
                json={"name": "冒烟助手", "systemPrompt": "你是测试助手", "temperature": 0.2, "maxTokens": 512},
            )
            check("新建助手（采样覆盖）", resp.status_code == 200 and resp.json()["temperature"] == 0.2, resp.text[:200])

            # 11) 流式对话（mock 模型）
            with client.stream(
                "POST",
                "/api/v1/ai/chat/stream",
                headers=headers,
                json={"content": "请总结当前设计上下文", "modelConfigId": mock_id},
            ) as stream:
                text = "".join(stream.iter_text())
            events = [line[6:] for line in text.splitlines() if line.startswith("data: ")]
            kinds = []
            for e in events:
                try:
                    kinds.append(json.loads(e).get("type"))
                except json.JSONDecodeError:
                    pass
            check(
                "SSE 事件序列",
                "meta" in kinds and "delta" in kinds and "done" in kinds,
                str(kinds[:12]),
            )
            meta = next(json.loads(e) for e in events if '"meta"' in e)
            check(
                "meta 携带模型信息",
                meta.get("provider") == "mock" and bool(meta.get("modelName")) and bool(meta.get("resolution")),
                json.dumps(meta, ensure_ascii=False)[:300],
            )

            # 12) 会话消息落库含用量
            conv_id = meta["conversationId"]
            resp = client.get(f"/api/v1/ai/conversations/{conv_id}/messages", headers=headers)
            messages = resp.json()
            check(
                "消息落库（含助手回复）",
                resp.status_code == 200 and len(messages) >= 2 and any(m["role"] == "assistant" and m["content"] for m in messages),
                str([(m["role"], len(m["content"])) for m in messages]),
            )

            # 退出前在应用自己的事件循环里释放连接池，否则 Windows 上 SQLite 文件被占用
            try:
                from app.database import engine as _engine

                client.portal.call(_engine.dispose)
            except Exception:  # noqa: BLE001 —— 清理阶段忽略
                pass
    finally:
        for path in (DB_PATH, DB_PATH.with_suffix(".db-wal"), DB_PATH.with_suffix(".db-shm")):
            try:
                path.unlink()
            except OSError:
                pass

    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} 项通过")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
