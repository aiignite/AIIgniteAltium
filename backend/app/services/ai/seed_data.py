"""技能与系统助手种子数据（对齐 AIIgnitePLM seed-sync 约定：幂等补种，不覆盖用户修改）。"""

import logging

from app.models.ai.ai_model import AIModelConfig
from app.models.ai.assistant import AIAssistant, AISkill
from app.services.ai.providers import PRESETS

logger = logging.getLogger(__name__)

# 首次安装时预置的模型模板（只建模板，不填 Key；云端模型未配 Key 会被路由自动跳过）
SEED_MODEL_PRESET_IDS = ("openai-gpt-4o-mini", "deepseek-chat", "ollama-qwen")

MOCK_MODEL_NAME = "演示引擎（无需 Key）"

SEED_SKILLS: list[dict] = [
    {
        "code": "schematic-review",
        "name": "原理图审查",
        "description": "原理图级审查：位号/封装/值完整性、可疑连接、电源结构",
        "category": "engineering",
        "icon": "clipboard",
        "keywords": ["原理图", "审查", "检查", "位号", "封装", "单端网络", "sch", "schematic"],
        "prompt_template": (
            "当前任务：原理图审查。请逐项检查并输出结构化清单（严重度：高/中/低）：\n"
            "1) 元件问题：缺封装、缺值/Comment、位号可疑（重复、空、跳号异常）；\n"
            "2) 网络问题：单端网络（只有一个连接点的网络）、命名可疑网络（如 N001 这类自动命名）；\n"
            "3) 电源结构：列出电源相关网络（VCC/GND/…）及其连接数量是否合理；\n"
            "4) 结论与建议。仅基于上下文数据，不要臆造。"
        ),
        "sort_order": 10,
        "priority": 80,
    },
    {
        "code": "pcb-review",
        "name": "PCB 审查",
        "description": "基于 PCB 统计与板框数据做初步审查与问题清单",
        "category": "engineering",
        "icon": "circuit",
        "keywords": ["pcb", "布局", "走线", "过孔", "板框", "叠层", "焊盘", "layout"],
        "prompt_template": (
            "当前任务：PCB 初步审查。基于上下文中的 PCB 统计（元件数、焊盘、走线、过孔、"
            "板框尺寸、叠层数）给出：\n"
            "1) 设计规模概述；\n"
            "2) 与原理图数据的对齐检查（PCB 元件数 vs 原理图元件数）；\n"
            "3) 需要在 Altium 中进一步确认的问题清单；\n"
            "4) 结论。"
        ),
        "sort_order": 20,
        "priority": 70,
    },
    {
        "code": "requirement-analysis",
        "name": "需求分析",
        "description": "把自然语言需求整理为结构化设计要点与选型方向",
        "category": "business",
        "icon": "bulb",
        "keywords": ["需求", "选型", "方案", "功能", "接口", "电源架构", "分析"],
        "prompt_template": (
            "当前任务：需求分析。把用户描述整理为：功能需求清单、关键器件候选方向"
            "（不得编造具体型号参数，仅给方向）、接口与电源需求、风险与待确认问题。"
        ),
        "sort_order": 30,
        "priority": 60,
    },
    {
        "code": "bom-analysis",
        "name": "BOM 分析",
        "description": "对 BOM 做归类统计、合并建议与风险物料识别",
        "category": "engineering",
        "icon": "chart",
        "keywords": ["bom", "物料", "元件清单", "用量", "替代料", "成本"],
        "prompt_template": (
            "当前任务：BOM 分析。基于上下文中的元件清单：\n"
            "1) 按类别（阻容感/电源/接口/逻辑/保护…）归类统计数量；\n"
            "2) 指出缺值、缺封装、疑似重复位号的物料；\n"
            "3) 给出可合并的物料项与替代料方向（不得编造具体型号）；\n"
            "4) 输出风险物料清单与建议。"
        ),
        "sort_order": 40,
        "priority": 55,
    },
]

SEED_ASSISTANTS: list[dict] = [
    {
        "code": None,
        "name": "通用硬件助手",
        "description": "平台问答与设计文件综合咨询，默认助手",
        "avatar": "bot",
        "category": "General",
        "system_prompt": (
            "你负责回答硬件设计相关问题：解释设计数据、定位元件/网络、协助排查问题。"
            "回答时优先引用「设计上下文」中的具体数据（位号/网络名/统计值）。"
        ),
        "skill_codes": [],
        "is_default": True,
        "sort_order": 0,
    },
    {
        "code": None,
        "name": "原理图审查助手",
        "description": "聚焦原理图审查：完整性、可疑连接与电源结构",
        "avatar": "clipboard",
        "category": "Engineering",
        "system_prompt": "你是原理图审查专家，输出务必结构化（严重度高/中/低），并给出可执行的修改建议。",
        "skill_codes": ["schematic-review"],
        "sort_order": 10,
    },
    {
        "code": None,
        "name": "PCB 审查助手",
        "description": "聚焦 PCB 初步审查：规模对齐与确认清单",
        "avatar": "circuit",
        "category": "Engineering",
        "system_prompt": "你是 PCB 审查专家，善于从统计与板框数据发现设计对齐问题，并输出需要在 Altium 中确认的清单。",
        "skill_codes": ["pcb-review"],
        "sort_order": 20,
    },
    {
        "code": None,
        "name": "需求分析助手",
        "description": "把自然语言需求整理为结构化设计要点与选型方向",
        "avatar": "bulb",
        "category": "Engineering",
        "system_prompt": "你是硬件需求分析专家，擅长把模糊需求拆解为功能清单、接口/电源需求与风险问题。",
        "skill_codes": ["requirement-analysis", "bom-analysis"],
        "sort_order": 30,
    },
]


async def seed_skills_and_assistants(db) -> None:
    """幂等补种：按 code/name 判断是否已存在，存在则跳过（不覆盖用户修改）。"""
    from sqlalchemy import select

    existing_skills = {
        code for (code,) in (await db.execute(select(AISkill.code))).all()
    }
    for spec in SEED_SKILLS:
        if spec["code"] in existing_skills:
            continue
        db.add(AISkill(is_system=True, enabled=True, **spec))

    existing_assistants = {
        name for (name,) in (await db.execute(select(AIAssistant.name))).all()
    }
    for spec in SEED_ASSISTANTS:
        if spec["name"] in existing_assistants:
            continue
        payload = {k: v for k, v in spec.items() if k != "code"}
        db.add(AIAssistant(is_system=True, enabled=True, **payload))
    await db.commit()


def _preset_to_model(preset: dict, sort_order: int) -> dict:
    return {
        "name": preset["name"],
        "provider": preset["provider"],
        "base_url": preset["baseUrl"],
        "model_name": preset["modelName"],
        "context_window": preset["contextWindow"],
        "supports_tools": preset["supportsTools"],
        "supports_image": False,
        "speed": preset["speed"],
        "cost": preset["cost"],
        "is_system": True,
        "enabled": True,
        "sort_order": sort_order,
        "remark": "预设模板：填入 API Key 并测试通过后即可使用",
    }


async def seed_models(db) -> None:
    """幂等补种模型：内置 mock 兜底 + 首批预设模板（不填 Key，未配 Key 由路由自动跳过）。"""
    from sqlalchemy import select

    rows = list((await db.execute(select(AIModelConfig))).scalars())
    existing_names = {r.name for r in rows}
    has_default = any(not r.is_deleted and r.is_default for r in rows)

    mock = next((r for r in rows if r.name == MOCK_MODEL_NAME), None)
    if mock is None:
        db.add(
            AIModelConfig(
                name=MOCK_MODEL_NAME,
                provider="mock",
                model_name="mock-1",
                is_default=not has_default,
                is_system=True,
                supports_tools=True,
                cost="local",
                remark="内置确定性演示模型，配置真实 API Key 后可切换",
                sort_order=0,
            )
        )
        existing_names.add(MOCK_MODEL_NAME)
    elif not mock.is_system:
        mock.is_system = True

    presets = {p["id"]: p for p in PRESETS}
    for idx, preset_id in enumerate(SEED_MODEL_PRESET_IDS):
        preset = presets.get(preset_id)
        if preset is None or preset["name"] in existing_names:
            continue
        db.add(AIModelConfig(**_preset_to_model(preset, 10 + idx * 10)))
        existing_names.add(preset["name"])
    await db.commit()


async def upgrade_legacy_api_keys(db) -> int:
    """把历史明文 api_key 加密写入 api_key_enc 并清空明文（幂等）。"""
    from sqlalchemy import select

    result = await db.execute(select(AIModelConfig).where(AIModelConfig.api_key != ""))
    count = 0
    for cfg in result.scalars():
        plain = cfg.api_key or ""
        if not plain:
            continue
        if not cfg.api_key_enc:
            cfg.bind_key(plain)
        else:
            cfg.api_key = ""
        count += 1
    if count:
        await db.commit()
        logger.info("已升级 %d 条模型密钥为加密存储", count)
    return count
