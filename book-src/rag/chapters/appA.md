# 附录 A · metadata 字段全清单

> **待办（2026-10-14）· 待写**：可从正文直接收编，无需新经验——「数据上游」卷第 06 篇（原 #05）给了 T0/T1/T2 三档和字段表，「检索的错觉」卷第 03 篇（原 #07）补了 `accounting_standard` / `period_length` / `metric_scope` 三个口径字段，「从能跑到能扛」卷第 01 篇（原 #11）给了跨市场公共字段。三处散着，册子里该合成一张表。

## 待收编内容

- 文档级 / chunk 级分层表（原 #05 第二节的表，11 个字段）
- 三档优先级：T0 不做没法用、T1 做了明显提升、T2 有余力再做
- 口径三字段（原 #07）：`accounting_standard`、`period_length`、`metric_scope`
- 跨市场公共字段锚点（原 #11）：`stock_code` / `stock_name` / `fiscal_year` / `period_type` / `currency` / `accounting_standard`
- 市场专属字段：港股 `is_audited`、A 股 `disclosure_type`
- 准则枚举值按市场分（HKFRS / IFRS / CAS / US GAAP / Non-GAAP），原 #05 已交代 HKFRS 与 IFRS 法律上是两套

## 建议加的两列

正文各处的字段表没有这两列，册子附录里补上：

- **怎么标**：规则 / 正则 / LLM 兜底（原 #05 第四节给过分工）
- **在哪用**：硬过滤 / 软加权 / 仅展示——直接对应「标了不用等于白标」那节的自查
