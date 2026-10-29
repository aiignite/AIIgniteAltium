from app.services.files.review import review_snapshot


def test_bom_and_net_rules():
    snapshot = {
        "components": [
            {"designator": "R1", "value": "10k", "footprint": "0603"},
            {"designator": "C1", "value": "100nF", "footprint": "0603"},
        ],
        "nets": [{"name": "VCC", "terminalCount": 2}, {"name": "N$7", "terminalCount": 2}],
        "bom": [
            {"designator": "R1", "value": "10k", "footprint": "0603"},
            {"designator": "R9", "value": "0", "footprint": "0603"},
        ],
        "pcbs": [],
        "warnings": [],
    }
    findings = {f["rule"]: f for f in review_snapshot(snapshot)}
    assert findings["bom_missing_row"]["refs"] == ["C1"]
    assert findings["bom_orphan_row"]["refs"] == ["R9"]
    assert findings["net_auto_named"]["refs"] == ["N$7"]
    assert findings["bom_missing_row"]["severity"] == "warning"
    assert findings["net_auto_named"]["severity"] == "info"


def test_board_off_origin():
    snapshot = {
        "components": [{"designator": "R1", "value": "10k", "footprint": "0603"}],
        "nets": [],
        "bom": [{"designator": "R1", "value": "10k", "footprint": "0603"}],
        "pcbs": [
            {"name": "B.PcbDoc", "board": {"outlineRectMils": [100, 200, 1100, 700]}},
            {"name": "C.PcbDoc", "board": {"outlineRectMils": [0, 0, 500, 300]}},
        ],
        "warnings": [],
    }
    findings = {f["rule"]: f for f in review_snapshot(snapshot)}
    assert findings["board_outline_off_origin"]["refs"] == ["B.PcbDoc"]
    assert findings["board_outline_off_origin"]["severity"] == "info"
    assert "100" in findings["board_outline_off_origin"]["detail"]
    assert "200" in findings["board_outline_off_origin"]["detail"]
