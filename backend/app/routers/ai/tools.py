"""AI 工具注册表查询（对齐 AIDriveNote ``GET /ai/tools/registry``）。

用途：助手/技能的「可用工具」选择器需要真实工具清单，而不是让用户手输工具名。
返回项刻意不含 handler / params_schema 的实现细节，只给展示与筛选所需字段。
"""

from fastapi import APIRouter, Depends

from app.ai_tools import registry, sync_gateway_tools
from app.schemas import CamelModel
from app.security import get_current_user

router = APIRouter(prefix="/ai/tools", tags=["ai-tools"])


class ToolOut(CamelModel):
    name: str
    description: str
    category: str
    requires_confirmation: bool


@router.get("/registry", response_model=list[ToolOut])
async def list_tool_registry(_user=Depends(get_current_user)) -> list[ToolOut]:
    # 有在线 gateway 时顺手同步动态工具（失败静默，不影响本地工具清单）
    try:
        await sync_gateway_tools()
    except Exception:  # noqa: BLE001 —— 同步失败不影响清单返回
        pass
    return [
        ToolOut(
            name=t["name"],
            description=t["description"],
            category=t["category"],
            requires_confirmation=bool(t["requires_confirmation"]),
        )
        for t in sorted(registry.list_all(), key=lambda x: (x["category"], x["name"]))
    ]
