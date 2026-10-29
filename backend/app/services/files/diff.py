"""快照版本差异：基于归一化快照的确定性对比，供版本面板与 AI 解读使用。"""

from typing import Any

MAX_ITEMS = 200

COMPONENT_FIELDS = ("value", "footprint", "description", "sheet")
BOM_FIELDS = ("value", "footprint", "libraryRef", "description", "dnp")
BOARD_FIELDS = ("widthMil", "heightMil", "layerStackupCount", "pads", "tracks", "vias")


def _rows(snapshot: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values = (snapshot or {}).get(key) or []
    return [v for v in values if isinstance(v, dict)]


def _by_key(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row.get(key) or "?")
        out.setdefault(name, row)
    return out


def _terminal_label(terminal: dict[str, Any]) -> str:
    return f"{terminal.get('designator') or '?'}-{terminal.get('pin') or '?'}"


def _terminals(net: dict[str, Any]) -> set[str]:
    return {_terminal_label(t) for t in net.get("terminals") or [] if isinstance(t, dict)}


def _terminal_count(net: dict[str, Any]) -> int:
    if isinstance(net.get("terminalCount"), int):
        return net["terminalCount"]
    return len(net.get("terminals") or [])


def _board_values(pcb: dict[str, Any]) -> dict[str, Any]:
    board = pcb.get("board") or {}
    rect = board.get("outlineRectMils")
    width = height = None
    if isinstance(rect, list) and len(rect) == 4 and all(isinstance(v, (int, float)) for v in rect):
        width, height = rect[2] - rect[0], rect[3] - rect[1]
    stats = pcb.get("stats") or {}
    return {
        "widthMil": width,
        "heightMil": height,
        "layerStackupCount": board.get("layerStackupCount"),
        "pads": stats.get("pads"),
        "tracks": stats.get("tracks"),
        "vias": stats.get("vias"),
    }


def _changed_fields(
    before: dict[str, Any], after: dict[str, Any], fields: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    changes: dict[str, dict[str, Any]] = {}
    for field in fields:
        old, new = before.get(field), after.get(field)
        if old != new:
            changes[field] = {"from": old, "to": new}
    return changes


def _diff_section(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    *,
    fields: tuple[str, ...],
    added_item,
    changed_item,
) -> dict[str, Any]:
    added = [added_item(key, after[key]) for key in sorted(after.keys() - before.keys())]
    removed = [added_item(key, before[key]) for key in sorted(before.keys() - after.keys())]
    changed = []
    for key in sorted(before.keys() & after.keys()):
        changes = _changed_fields(before[key], after[key], fields)
        if changes:
            changed.append(changed_item(key, changes))
    return {
        "added": added[:MAX_ITEMS],
        "removed": removed[:MAX_ITEMS],
        "changed": changed[:MAX_ITEMS],
    }


def _nets_section(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> dict[str, Any]:
    added = [
        {"name": key, "terminalCount": _terminal_count(after[key])}
        for key in sorted(after.keys() - before.keys())
    ]
    removed = [
        {"name": key, "terminalCount": _terminal_count(before[key])}
        for key in sorted(before.keys() - after.keys())
    ]
    changed = []
    for key in sorted(before.keys() & after.keys()):
        old, new = before[key], after[key]
        old_count, new_count = _terminal_count(old), _terminal_count(new)
        old_terminals, new_terminals = _terminals(old), _terminals(new)
        if old_count == new_count and old_terminals == new_terminals:
            continue
        changed.append(
            {
                "name": key,
                "terminalCount": {"from": old_count, "to": new_count},
                "terminalsAdded": sorted(new_terminals - old_terminals),
                "terminalsRemoved": sorted(old_terminals - new_terminals),
            }
        )
    return {"added": added[:MAX_ITEMS], "removed": removed[:MAX_ITEMS], "changed": changed[:MAX_ITEMS]}


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    components = _diff_section(
        _by_key(_rows(before, "components"), "designator"),
        _by_key(_rows(after, "components"), "designator"),
        fields=COMPONENT_FIELDS,
        added_item=lambda key, c: {
            "designator": key,
            "value": c.get("value") or "",
            "footprint": c.get("footprint") or "",
        },
        changed_item=lambda key, changes: {"designator": key, "fields": changes},
    )
    nets = _nets_section(_by_key(_rows(before, "nets"), "name"), _by_key(_rows(after, "nets"), "name"))
    bom = _diff_section(
        _by_key(_rows(before, "bom"), "designator"),
        _by_key(_rows(after, "bom"), "designator"),
        fields=BOM_FIELDS,
        added_item=lambda key, r: {
            "designator": key,
            "value": r.get("value") or "",
            "footprint": r.get("footprint") or "",
        },
        changed_item=lambda key, changes: {"designator": key, "fields": changes},
    )
    boards = _diff_section(
        _all_boards(before),
        _all_boards(after),
        fields=BOARD_FIELDS,
        added_item=lambda key, values: {"name": key, "values": values},
        changed_item=lambda key, changes: {"name": key, "fields": changes},
    )
    summary = {
        f"{name}{action.capitalize()}": len(section[action])
        for name, section in (("component", components), ("net", nets), ("bom", bom), ("board", boards))
        for action in ("added", "removed", "changed")
    }
    return {"components": components, "nets": nets, "bom": bom, "boards": boards, "summary": summary}


def _all_boards(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {key: _board_values(row) for key, row in _by_key(_rows(snapshot, "pcbs"), "name").items()}
