# 审查规则评测集（Deterministic Review Evals）

本目录说明 `backend/app/services/files/review.py` 确定性审查规则的金标准评测。评测**纯离线**运行，不连接数据库、不调用大模型，结果可复现，用于规则集演进时的回归基线。

## 为什么需要

审查规则是「辅助级别 L2→L3」信任链路的一环：AI 助手在设计上下文里引用审查结论前，规则本身必须先可信。`p2.0` 规则集有 13 条规则，随需求增长会持续增删；每改一条都可能悄悄改变已有工程的告警结果。评测集把「哪些输入应触发哪些规则」固化为可执行断言，避免规则回归。

## 组成

- **缺陷板** `backend/tests/fixtures/eval/defect_board.json`：人工构造，使 `expected_rules` 列出的 12 条规则各至少命中一次。用于测**查全率**（该报的有没有漏报）。
- **干净板** `backend/tests/fixtures/eval/clean_board.json`：满足全部阈值的一致性快照，期望零 findings。用于测**误报率**（不该报的有没有乱报）。
- **回归用例** `backend/tests/test_review_evals.py`：加载上述 fixture，断言查全率、误报率与分级计数。

> 单条规则的边界行为由 `backend/tests/test_review_rules.py` 覆盖；评测集聚焦「整套规则集在代表性输入上的整体行为」，两者互补。

## 指标口径

- **查全率（Recall）**：缺陷板实际命中规则集合 ⊇ `expected_rules`。任一预期规则未命中即失败。
- **零误报**：干净板 `review_snapshot() == []`。任一非预期告警即失败。
- **规则不误触发**：缺陷板命中集合不超出 `expected_rules`，防止新规则污染既有基线。
- **可消费性**：每条命中规则都带 `refs`（对象引用）与合法 `severity`，`summarize()` 分级计数与 findings 一致。

## 覆盖的规则（p2.0，缺陷板触发 12 条）

| 规则 | 级别 | 缺陷板触发对象 |
| --- | --- | --- |
| `duplicate_designator` | error | 位号 U1 重复 |
| `board_outline_invalid` | error | pcb `degenerate` 宽 0 |
| `missing_footprint` | warning | C1 封装为空 |
| `missing_value` | warning | R1 值为空 |
| `bom_missing_row` | warning | D5 无 BOM 行 |
| `bom_orphan_row` | warning | X9 孤儿 BOM 行 |
| `single_terminal_net` | warning | SPARE 单端网络 |
| `board_outline_missing` | warning | pcb `nobuf` 无板框 |
| `net_auto_named` | info | Net12 自动命名 |
| `dnp_bom_rows` | info | R1 为 DNP |
| `parse_warnings` | info | 解析降级告警 |
| `board_outline_off_origin` | info | pcb `offorigin` 起点非 0 |

`no_components`（快照无元件）在干净板/缺陷板均不触发，由 `test_review_rules.py` 单独覆盖。

## 运行

```bash
cd backend
pytest tests/test_review_evals.py -v
```

无需数据库，可与其它单元用例一同进入全量回归。

## 维护约定

- **新增规则**：在缺陷板补一段必然触发它的输入，并把规则名加入 `expected_rules`；确认干净板仍不触发它。
- **调整阈值**：优先改 fixture 数据来验证边界，不在评测里内联硬编码期望计数（保持评测对规则数量增长稳定）。
- 若某规则被移除或重命名，同步更新 `defect_board.json` 的 `expected_rules`，避免遗留失效断言。
