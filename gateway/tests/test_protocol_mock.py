"""gateway 测试：行式协议、mock 驱动、文件桥（FakeResponder 模拟 DelphiScript 侧）。"""

import threading
import time
from pathlib import Path

import pytest

from altium_gateway.commands import COMMANDS, build_live_summary, execute_command
from altium_gateway.drivers.file_bridge import FileBridgeDriver
from altium_gateway.drivers.mock import MockAltiumDriver
from altium_gateway.protocol import encode_request, parse_response


def test_protocol_roundtrip():
    ops = [("ping", {}), ("pcb_stats", {})]
    text = encode_request("abc123", ops)
    assert "OP|ping" in text and "END|abc123" in text

    response = "\n".join(
        [
            "RES|0|OK|reply=PONG",
            "RES|1|ITEM|designator=U1|value=AMS1117",
            "RES|1|ITEM|designator=U2|value=STM32",
            "RES|1|OK|count=2|document=x.PcbDoc",
            "END|abc123",
        ]
    )
    ok, results = parse_response(response, 2)
    assert ok
    assert results[0].to_payload() == {"ok": True, "reply": "PONG"}
    stats = results[1].to_payload()
    assert stats["count"] == 2
    assert [i["designator"] for i in stats["items"]] == ["U1", "U2"]


def test_protocol_missing_op_marked_failed():
    ok, results = parse_response("RES|0|OK|reply=PONG\nEND|x", 2)
    assert not ok
    assert results[1].ok is False and "no response" in results[1].error


def test_mock_driver_all_commands():
    driver = MockAltiumDriver()
    for name in COMMANDS:
        result = execute_command(driver, name)
        assert result.get("ok"), f"{name} failed: {result}"
    assert execute_command(driver, "nope")["ok"] is False


def test_live_summary_mock():
    summary = build_live_summary(MockAltiumDriver())
    assert summary["ok"]
    assert summary["project"] == "Mock JLink Demo"
    assert summary["pcbStats"]["tracks"] == 310
    assert summary["schematic"]["componentCount"] == 5


def test_file_bridge_with_fake_altium(tmp_path: Path):
    """模拟 DelphiScript 驻留脚本：发现请求文件后写行式响应。"""

    requests_dir = tmp_path / "requests"
    responses_dir = tmp_path / "responses"

    def fake_altium():
        resp_dir = responses_dir
        while True:
            for req in sorted(requests_dir.glob("req_*.txt")):
                req_id = req.stem.replace("req_", "")
                out_lines = []
                op_index = 0
                for line in req.read_text(encoding="ascii").splitlines():
                    if line.startswith("OP|"):
                        out_lines.append(f"RES|{op_index}|OK|reply=PONG|echo={line}")
                        op_index += 1
                out_lines.append(f"END|{req_id}")
                (resp_dir / f"resp_{req_id}.txt").write_text("\n".join(out_lines), encoding="ascii")
                req.unlink()
            time.sleep(0.05)

    threading.Thread(target=fake_altium, daemon=True).start()

    driver = FileBridgeDriver(bridge_dir=tmp_path, op_timeout=10)
    results = driver.execute([("ping", {}), ("get_project_info", {})])
    assert results[0]["ok"] and results[0]["reply"] == "PONG"
    assert results[1]["ok"]
    assert driver.is_alive()


def test_file_bridge_timeout(tmp_path: Path):
    driver = FileBridgeDriver(bridge_dir=tmp_path / "nonexistent", op_timeout=0.4)
    results = driver.execute([("ping", {})])
    assert not results[0]["ok"]
    assert "超时" in results[0]["error"]
