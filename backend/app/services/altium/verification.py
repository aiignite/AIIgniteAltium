"""写后即查（Post-Action Verification，ADR-001 管线⑤ / llm-max-assist §2.3）。

每次确认写命令成功后，用确定性引擎读回受影响对象的当前状态，与"命令本应达成的结果"
比对，判断写入是否真的落地（而不是只信 gateway 返回的 ok）。结果内嵌进审计的
``result.verification``，并回喂到后续对话上下文，供模型自我修正——这是 L2→L3 的门槛。

不调用模型、不做几何推断：只做「意图 vs 实际」的一致性核验。
"""

from __future__ import annotations

from typing import Any

_CONTROL_KEYS = frozenset({"dry_run", "dryRun", "confirmed", "confirm", "requestId", "request_id"})


def _same_value(expected: Any, actual: Any) -> bool:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)) and not isinstance(expected, bool):
        return abs(float(expected) - float(actual)) < 1e-3
    return str(expected).strip().lower() == str(actual).strip().lower()


def _expected_from_params(command: str, params: dict[str, Any]) -> dict[str, Any]:
    """写命令成功后设计应呈现的状态（= 命令的目标参数）。"""
    if command == "altium_move_component":
        return {k: params[k] for k in ("x", "y") if params.get(k) is not None}
    if command == "altium_rotate_component":
        return {"rotation": params["rotation"]} if params.get("rotation") is not None else {}
    return {}


def _diff(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key, value in expected.items():
        if key not in actual:
            issues.append(f"{key}: 读回缺少该字段")
        elif not _same_value(value, actual[key]):
            issues.append(f"{key}: 期望 {value}，实际 {actual[key]}")
    return issues


def _not_checked(reason: str) -> dict[str, Any]:
    return {"checked": False, "ok": True, "issues": [], "note": reason}


async def _read_back(client, command: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """用 dry_run 预览读回对象当前状态；读不到（不支持/异常）返回 None，不误报失败。"""
    query = {k: v for k, v in params.items() if k not in _CONTROL_KEYS} | {"dry_run": True}
    try:
        preview = await client.command(command, query)
    except Exception:  # noqa: BLE001 —— 读回失败降级为「未核验」，不阻断写结果
        return None
    if not isinstance(preview, dict) or not preview.get("ok", True):
        return None
    current = preview.get("current")
    return dict(current) if isinstance(current, dict) else None


async def verify_write(client, command: str, params: dict[str, Any]) -> dict[str, Any]:
    """核验写命令是否真的落地。高亮等纯视觉操作无对象状态可回读，标记为未核验。"""
    expected = _expected_from_params(command, params)
    if not expected:
        if command == "altium_highlight_net":
            return _not_checked("高亮为视觉操作，无设计状态可回读核验")
        return _not_checked("该命令暂无可回读的目标状态，未做一致性核验")
    actual = await _read_back(client, command, params)
    if actual is None:
        return _not_checked("gateway 未提供该对象的状态读回，跳过核验")
    issues = _diff(expected, actual)
    result: dict[str, Any] = {
        "checked": True,
        "ok": not issues,
        "expected": expected,
        "actual": {k: actual.get(k) for k in expected},
        "issues": issues,
    }
    if issues:
        result["note"] = "写入返回成功但回读状态与目标不一致，可能未生效或被后续改动覆盖"
    return result


def verification_status(rows: list[Any]) -> list[dict[str, Any]]:
    """从审计记录里挑出「写后核验未通过」的条目，供下一轮对话回喂模型自我修正。"""
    flagged: list[dict[str, Any]] = []
    for audit in rows:
        verification = (audit.result or {}).get("verification") or {}
        if verification.get("checked") and not verification.get("ok"):
            flagged.append({
                "command": audit.command,
                "params": audit.params or {},
                "issues": verification.get("issues") or [],
                "auditId": str(audit.id),
            })
    return flagged


def verification_to_context(flagged: list[dict[str, Any]]) -> str:
    if not flagged:
        return ""
    lines = ["【写后即查·未通过】以下写操作回读状态与目标不一致，请核对后决定是否重新执行或撤销："]
    for item in flagged[:5]:
        refs = item["params"].get("designator") or item["params"].get("net") or ""
        issues = "；".join(item["issues"])
        lines.append(f"  - {item['command']} {refs}：{issues}")
    lines.append("  （可用 altium_get_pcb_components / altium_find_components 复查当前状态，必要时撤销该审计记录）")
    return "\n".join(lines)
