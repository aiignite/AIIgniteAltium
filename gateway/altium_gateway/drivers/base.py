"""Altium 驱动接口：所有操作经 `execute(ops)` 批量下发，返回逐 op 结果。"""

from abc import ABC, abstractmethod
from typing import Any


class AltiumDriver(ABC):
    """一次 execute = 一次桥事务（ADR-001 命令层与传输解耦）。"""

    @abstractmethod
    def execute(self, ops: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def is_alive(self) -> bool:
        """Altium 侧驻留脚本是否在线（最近是否有过响应/心跳）。"""
