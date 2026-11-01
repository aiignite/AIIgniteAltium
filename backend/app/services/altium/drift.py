"""实时 Altium 设计与离线快照的漂移对比（不依赖具体 Altium 版本，纯数据比较）。"""

from __future__ import annotations

from typing import Any

MAX_ITEMS = 100
COMPONENT_FIELDS = ("value", "footprint")


def _by_designator(rows: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if isinstance(row, dict) and row.get("designator"):
            out[str(row["designator"])] = row
    return out


def _by_name(rows: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        if isinstance(row, dict) and row.get("name"):
            out[str(row["name"])] = row
    return out


def _changed(
    live: dict[str, dict[str, Any]], snapshot: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    changes = []
    for designator in sorted(live.keys() & snapshot.keys()):
        fields = {
            field: {"live": live[designator].get(field), "snapshot": snapshot[designator].get(field)}
            for field in COMPONENT_FIELDS
            if live[designator].get(field) != snapshot[designator].get(field)
        }
        if fields:
            changes.append({"designator": designator, "fields": fields})
    return changes[:MAX_ITEMS]


def compare_drift(
    live_components: list[Any], live_nets: list[Any], snapshot: dict[str, Any]
) -> dict[str, Any]:
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    live = _by_designator(live_components)
    snap = _by_designator(snapshot.get("components") or [])
    live_net = _by_name(live_nets)
    snap_net = _by_name(snapshot.get("nets") or [])
    only_live = sorted(live.keys() - snap.keys())
    only_snap = sorted(snap.keys() - live.keys())
    nets_only_live = sorted(live_net.keys() - snap_net.keys())
    nets_only_snap = sorted(snap_net.keys() - live_net.keys())
    changed = _changed(live, snap)
    return {
        "drifted": bool(only_live or only_snap or nets_only_live or nets_only_snap or changed),
        "components": {
            "onlyInLive": only_live[:MAX_ITEMS],
            "onlyInSnapshot": only_snap[:MAX_ITEMS],
            "changed": changed,
            "countLive": len(live),
            "countSnapshot": len(snap),
        },
        "nets": {
            "onlyInLive": nets_only_live[:MAX_ITEMS],
            "onlyInSnapshot": nets_only_snap[:MAX_ITEMS],
            "countLive": len(live_net),
            "countSnapshot": len(snap_net),
        },
    }
