"""审查规则金标准评测：以固定缺陷板/干净板回归查全率与误报率，纯离线、不调用模型或数据库。"""

import json
from pathlib import Path

from app.services.files.review import RULESET_VERSION, review_snapshot, summarize

FIXTURES = Path(__file__).parent / "fixtures" / "eval"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _rules(findings: list[dict]) -> set[str]:
    return {f["rule"] for f in findings}


def test_defect_board_full_recall():
    """缺陷板：expected_rules 中每条规则必须至少命中一次（查全率 100%）。"""
    board = _load("defect_board.json")
    findings = review_snapshot(board)
    hit = _rules(findings)
    expected = set(board["expected_rules"])
    missing = expected - hit
    assert not missing, f"规则集 {RULESET_VERSION} 未能命中预期规则：{sorted(missing)}"


def test_defect_board_no_unexpected_rules():
    """缺陷板：除预期规则外不应触发其它规则（避免规则误触发污染基线）。"""
    board = _load("defect_board.json")
    hit = _rules(review_snapshot(board))
    expected = set(board["expected_rules"])
    extra = hit - expected
    assert not extra, f"缺陷板触发了未登记的规则：{sorted(extra)}"


def test_clean_board_zero_findings():
    """干净板：满足全部阈值，期望零 findings（误报率 0）。"""
    board = _load("clean_board.json")
    findings = review_snapshot(board)
    assert findings == [], f"干净板不应有任何告警，实际：{_rules(findings)}"


def test_each_expected_rule_has_refs_and_severity():
    """缺陷板每条命中规则都应带对象引用与合法级别，供报告与前端消费。"""
    board = _load("defect_board.json")
    by_rule = {f["rule"]: f for f in review_snapshot(board)}
    for rule in board["expected_rules"]:
        finding = by_rule[rule]
        assert finding["refs"], f"{rule} 缺少对象引用"
        assert finding["severity"] in {"error", "warning", "info"}


def test_summarize_counts_match_findings():
    """summarize 的分级计数应与缺陷板 findings 一致。"""
    findings = review_snapshot(_load("defect_board.json"))
    counts = summarize(findings)
    assert sum(counts.values()) == len(findings)
    for level in counts:
        assert counts[level] == sum(1 for f in findings if f["severity"] == level)
