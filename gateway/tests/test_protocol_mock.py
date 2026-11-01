"""gateway 测试：行式协议、mock 驱动、文件桥（FakeResponder 模拟 DelphiScript 侧）。"""

import threading
import time
from pathlib import Path

import pytest

from altium_gateway.commands import COMMANDS, build_live_summary, execute_command, list_commands
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
        if COMMANDS[name].requires_confirmation:
            continue  # 写命令确认流程由专门的写命令用例覆盖
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
    """模拟 DelphiScript 驻留脚本：发现 request.txt 后写行式响应到 response.txt。"""

    requests_dir = tmp_path / "requests"
    responses_dir = tmp_path / "responses"
    requests_dir.mkdir(parents=True, exist_ok=True)
    responses_dir.mkdir(parents=True, exist_ok=True)

    def fake_altium():
        while True:
            req = requests_dir / "request.txt"
            if req.exists():
                try:
                    text = req.read_text(encoding="ascii")
                except OSError:
                    time.sleep(0.05)
                    continue
                if not text.strip():
                    time.sleep(0.05)
                    continue
                out_lines = []
                op_index = 0
                req_id = "x"
                for line in text.splitlines():
                    if line.startswith("OP|"):
                        out_lines.append(f"RES|{op_index}|OK|reply=PONG|echo={line}")
                        op_index += 1
                    elif line.startswith("END|"):
                        req_id = line.split("|")[1]
                out_lines.append(f"END|{req_id}")
                (responses_dir / "response.txt").write_text("\n".join(out_lines), encoding="ascii")
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


# ---------- M5 写命令：requires_confirmation + dry_run 预览 + confirmed 执行 ----------

WRITE_NAMES = ("altium_highlight_net", "altium_move_component", "altium_rotate_component")


def test_write_commands_metadata():
    writes = [c for c in COMMANDS.values() if c.category == "write"]
    assert len(writes) == 3
    for c in writes:
        assert c.requires_confirmation is True
        assert c.params_schema
        meta = next(m for m in list_commands() if m["name"] == c.name)
        assert meta["requiresConfirmation"] is True
        assert meta["paramsSchema"]


def test_write_unconfirmed_rejected():
    driver = MockAltiumDriver()
    for name in WRITE_NAMES:
        result = execute_command(driver, name, {"designator": "U1"})
        assert result.get("ok") is False
        assert result.get("requiresConfirmation") is True


def test_highlight_dry_run():
    driver = MockAltiumDriver()
    missing = execute_command(driver, "altium_highlight_net", {"dry_run": True})
    assert missing["ok"] is False and "net" in missing["error"]
    preview = execute_command(driver, "altium_highlight_net", {"net": "GND", "dry_run": True})
    assert preview["ok"] is True and preview["dryRun"] is True
    assert "GND" in preview["preview"]
    assert preview["params"] == {"net": "GND", "mode": 1}
    off = execute_command(driver, "altium_highlight_net", {"net": "VCC", "mode": 0, "dry_run": True})
    assert "取消高亮" in off["preview"] and off["params"]["mode"] == 0


def test_move_dry_run_uses_real_state():
    driver = MockAltiumDriver()
    missing = execute_command(driver, "altium_move_component", {"dry_run": True})
    assert missing["ok"] is False and "designator" in missing["error"]
    unknown = execute_command(driver, "altium_move_component", {"designator": "R99", "x": 1000, "y": 1000, "dry_run": True})
    assert unknown["ok"] is False and "未找到" in unknown["error"]
    preview = execute_command(driver, "altium_move_component", {"designator": "U1", "x": 5000, "y": 6000, "dry_run": True})
    assert preview["ok"] is True
    assert "(2000mils, 1500mils)" in preview["preview"]
    assert "移动到 (5000mils, 6000mils)" in preview["preview"]
    assert preview["current"]["designator"] == "U1"


def test_rotate_dry_run():
    driver = MockAltiumDriver()
    preview = execute_command(driver, "altium_rotate_component", {"designator": "U2", "rotation": 270, "dry_run": True})
    assert preview["ok"] is True
    assert "90°" in preview["preview"] and "270°" in preview["preview"]


def test_write_confirmed_executes_and_strips_control_keys():
    driver = MockAltiumDriver()
    move = execute_command(driver, "altium_move_component", {"designator": "U1", "x": 5000, "y": 6000, "confirmed": True})
    assert move["ok"] is True and move["designator"] == "U1" and move["x"] == 5000 and move["y"] == 6000
    rot = execute_command(driver, "altium_rotate_component", {"designator": "U1", "rotation": 180, "confirm": True})
    assert rot["ok"] is True and rot["rotation"] == 180
    hl = execute_command(driver, "altium_highlight_net", {"net": "GND", "confirmed": True})
    assert hl["ok"] is True and hl["net"] == "GND"


def test_mock_state_changes_after_writes():
    """撤销前置校验依赖「执行后状态真的变了」，mock 驱动必须保持同一份状态。"""

    driver = MockAltiumDriver()
    execute_command(driver, "altium_move_component", {"designator": "U1", "x": 5000, "y": 6000, "confirmed": True})
    execute_command(driver, "altium_rotate_component", {"designator": "U2", "rotation": 45, "confirmed": True})
    after = {c["designator"]: c for c in execute_command(driver, "altium_get_pcb_components")["items"]}
    assert (after["U1"]["x"], after["U1"]["y"]) == (5000, 6000)
    assert after["U2"]["rotation"] == 45

    unknown = execute_command(driver, "altium_move_component", {"designator": "R99", "x": 1, "y": 2, "confirmed": True})
    assert unknown["ok"] is False and "R99" in unknown["error"]


# ---------- 语义查询命令：复用只读桥 op，在网关侧过滤/分页 ----------


def test_find_components_filters_scope_and_limit():
    driver = MockAltiumDriver()
    by_designator = execute_command(driver, "altium_find_components", {"designator": "U"})
    assert by_designator["ok"] is True
    assert {i["designator"] for i in by_designator["items"]} == {"U1", "U2", "OUT1", "USB_Mini"}
    assert by_designator["matched"] == 4 and by_designator["returned"] == 4
    assert by_designator["truncated"] is False and by_designator["filters"]["designator"] == "U"

    by_footprint = execute_command(driver, "altium_find_components", {"value": "STM32"})
    assert [i["designator"] for i in by_footprint["items"]] == ["U2"]

    scoped = execute_command(driver, "altium_find_components", {"scope": "pcb", "footprint": "LQFP"})
    assert scoped["items"][0]["designator"] == "U2" and scoped["items"][0]["x"] == 2400

    paged = execute_command(driver, "altium_find_components", {"limit": 2})
    assert paged["returned"] == 2 and paged["truncated"] is True and paged["matched"] == 5
    assert "hint" in paged

    capped = execute_command(driver, "altium_find_components", {"limit": 5000})
    assert capped["returned"] == 5  # 上限保护，避免一次拉回整板数据


def test_find_nets_filters_by_name_and_terminal_count():
    driver = MockAltiumDriver()
    single = execute_command(driver, "altium_find_nets", {"max_terminals": 1})
    assert [i["name"] for i in single["items"]] == ["NetC4_1"]
    assert single["items"][0]["terminalCount"] == 1

    heavy = execute_command(driver, "altium_find_nets", {"min_terminals": 20})
    assert [i["name"] for i in heavy["items"]] == ["GND"]

    usb = execute_command(driver, "altium_find_nets", {"name": "usb"})
    assert {i["name"] for i in usb["items"]} == {"USB_DP", "USB_DM"}
    assert usb["filters"] == {"name": "usb", "minTerminals": None, "maxTerminals": None}

    query_commands = [c for c in COMMANDS.values() if c.post_filter is not None]
    assert {c.name for c in query_commands} == {"altium_find_components", "altium_find_nets"}
    for cmd in query_commands:
        assert cmd.category == "query" and cmd.requires_confirmation is False
