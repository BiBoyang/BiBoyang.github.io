# 附录 C · 2026-10 快照

> **待办（2026-10-14）· 待写**：把会过期的东西全部沉到这一篇，正文只写方法。原 #12 自己立过这条纪律——「结论会过期，方法不会」——册子里该推广到全册。

## 待收编内容

- **embedding 模型候选名单与定价**（原 #12 第二节，写作时口径 2026-05）：multilingual-e5-large-instruct、Qwen3-Embedding、bge-m3、Cohere Embed v4 / text-embedding-3-large / gemini-embedding-001、all-MiniLM-L6-v2
- **PDF 工具版本**：poppler-utils、pypdf 4.x、pdfplumber 0.11、MinerU（正文实测用 1.x，2026-09 时已到 4.x）
- **reranker 选型**（原 #10）：bge-reranker-v2-m3 等，延迟与语言支持
- **上下文窗口**：Claude 200K / Gemini 1M–2M / GPT 系列（原 #20、#21）
- **延迟与成本经验值**：rerank 200–500ms、cross-encoder 单对 10–100ms、多模态截图 $0.01–0.05/页

## 硬性要求

每一项必须标**测量口径与记录日期**，凡是从正文搬过来的经验值，一律保留原文里的「经验口径，不是实测」标注。附录的价值在可复核，不在全面。

## 两条待核实（成册前必须钉死）

- `bge-reranker-v2-m3` 这个命名是否真实存在（技术审查报告 2026-07-18 列为存疑）
- Qwen3-Embedding 的发布状态与 MTEB 榜单数字（原 #12、#20 均引用）
