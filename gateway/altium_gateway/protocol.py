"""桥协议（v1）：行式文本协议，专为 DelphiScript 侧无 JSON 解析器设计。

请求文件  requests/req_<id>.txt：
    OP|<op_name>|<k>=<v>|k=v...
    OP|...
    END|<id>

响应文件  responses/resp_<id>.txt：
    RES|<op_index>|OK|<k>=<v>|...
    RES|<op_index>|ITEM|<k>=<v>|...   （同一 op 可多行，聚合为 items）
    RES|<op_index>|ERR|<message>
    END|<id>

标量值解析：int/float 优先，否则字符串。所有 k,v 均不含换行与竖线。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def encode_op(op: str, **params: Any) -> str:
    parts = ["OP", op] + [f"{k}={v}" for k, v in params.items() if v is not None]
    return "|".join(str(p) for p in parts)


def encode_request(request_id: str, ops: list[tuple[str, dict[str, Any]]]) -> str:
    lines = [encode_op(op, **params) for op, params in ops]
    lines.append(f"END|{request_id}")
    return "\n".join(lines) + "\n"


def _parse_value(raw: str) -> Any:
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_kv(pairs: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for pair in pairs:
        if "=" in pair:
            k, _, v = pair.partition("=")
            data[k] = _parse_value(v)
    return data


@dataclass
class OpResult:
    index: int
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def to_payload(self) -> dict[str, Any]:
        if not self.ok:
            return {"ok": False, "error": self.error or "op failed"}
        payload = {"ok": True, **self.data}
        if self.items:
            payload["items"] = self.items
        return payload


def parse_response(text: str, expected_ops: int) -> tuple[bool, list[OpResult]]:
    """解析响应文本。返回 (整体是否成功, 每个 op 的结果)。"""
    results: dict[int, OpResult] = {}
    end_id: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        kind = parts[0].upper()
        if kind == "END":
            end_id = parts[1] if len(parts) > 1 else ""
        elif kind == "RES" and len(parts) >= 3:
            try:
                index = int(parts[1])
            except ValueError:
                continue
            status = parts[2].upper()
            result = results.setdefault(index, OpResult(index=index, ok=True))
            if status == "ITEM":
                result.items.append(_parse_kv(parts[3:]))
            elif status == "OK":
                result.data.update(_parse_kv(parts[3:]))
            elif status == "ERR":
                result.ok = False
                result.error = "|".join(parts[3:]) or "unknown error"
    ordered: list[OpResult] = []
    for i in range(expected_ops):
        ordered.append(results.get(i) or OpResult(index=i, ok=False, error="no response for op"))
    overall_ok = end_id is not None and all(r.ok for r in ordered)
    return overall_ok, ordered


def execute_ops_via_protocol(ops: list[tuple[str, dict[str, Any]]], raw_response: str) -> list[dict[str, Any]]:
    _, ordered = parse_response(raw_response, len(ops))
    return [r.to_payload() for r in ordered]
