"""AI 工具注册表查询（对齐 AIDriveNote ``GET /ai/tools/registry``）。

用途：助手/技能的「可用工具」选择器需要真实工具清单，而不是让用户手输工具名。
返回项刻意不含 handler / params_schema 的实现细节，只给展示与筛选所需字段。

网关工具按连接归属：传入 ``connectionId`` 时只列该连接（需可访问）的命令；
未传入时列出当前用户可见且在线的全部连接命令，供选择器展示。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.ai_tools import ToolContext, registry, reset_tool_context, set_tool_context, sync_gateway_tools
from app.schemas import CamelModel
from app.security import get_current_user

router = APIRouter(prefix="/ai/tools", tags=["ai-tools"])


class ToolOut(CamelModel):
    name: str
    description: str
    category: str
    requires_confirmation: bool


@router.get("/registry", response_model=list[ToolOut])
async def list_tool_registry(
    connection_id: UUID | None = Query(default=None, alias="connectionId"),
    user=Depends(get_current_user),
) -> list[ToolOut]:
    context = ToolContext(user_id=user.id, connection_id=connection_id)
    token = set_tool_context(context)
    try:
        # 有可访问的在线 gateway 时顺手同步动态工具（失败静默，不影响本地工具清单）
        try:
            await sync_gateway_tools(context)
        except Exception:  # noqa: BLE001 —— 同步失败不影响清单返回
            pass
        tools = registry.visible(context) if connection_id else registry.list_all()
    finally:
        reset_tool_context(token)
    return [
        ToolOut(
            name=t["name"],
            description=t["description"],
            category=t["category"],
            requires_confirmation=bool(t["requires_confirmation"]),
        )
        for t in sorted(tools, key=lambda x: (x["category"], x["name"]))
    ]
