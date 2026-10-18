> ⚠️ **已废弃 · 2026-10-18**：本文（执行学·下）已被《目标、咒语与协议-重铸合并版》（同目录）吸收合并，仅留档备查。审阅与发布请用合并版。

---
layout: post
title:  "长程任务执行学（下）：数据、祛魅，和那张没人做的实验"
date:   2026-10-18 00:00:00 +0800
categories: [AI]
tags: [AI, Agent]
---


三周前我写了《目标、咒语与协议》，把 Codex 的 `ext/goal` 和 LoopX 各读了一遍，结论是"咒语贬值、协议升值"。之后我把调研往前推了一步：让几路 agent 把 Codex 两个版本快照（v0.154、v0.160）和 LoopX 1.4.2 的 wheel 解包源码逐文件读了一遍，并且做了上次没做的一件事——**检索所有不来自任何厂商的独立证据**。

这轮读下来的结果：几个流传很广的说法在源码面前站不住；数据把优先级重新排了一遍；还有几个问题可以确认了——**不是没人找到答案，是没有人有答案**。

## 一、LoopX 最常被误读的两件事

LoopX 的二手介绍很多，但有两件事几乎所有转述都讲错了，值得先澄清。

**第一，它的验收不是"独立验证器"，而是 owner 预声明的确定性命令验收。** `acceptance.py` 的 docstring 第一句是 "No caller-supplied pass/fail result is accepted by the public CLI"——验收文件 SHA-256 pin、拷进临时快照目录执行、跑前跑后双重校验哈希，整套链路里**没有任何 LLM 评审环节**。"独立"指的是执行环境独立（快照、防篡改、防竞态），不是评审者独立。这带来两个直接推论：owner 不配 criteria，机制直接抛错不可用；验收脚本本身写错了，确定性验收就确定性地产出错误结论——这个不是理论风险，它的 benchmark 里就有实例（后面细说）。

**第二，跨 runtime 编排是 demo，不是产品。** 仓库顶层有 9 个 runtime 适配目录（claude/codex/opencode/……），看着像多宿主编排已经建成。读码：1.4.2 里"Claude 实现 + Codex 评审"的跨 runtime 流程是 **dry-run only 的 demo packet**（`cross_runtime_impl_review.py` 明确拒绝非 dry-run）。另外注意它正在 2.0 破坏性迁移中（控制平面迁 TypeScript 的 RFC 已挂出），API 与许可都在快速变化（v0.4.8 起从 MIT 转 Apache-2.0）——现在引用它的任何具体接口，都要标注版本。

## 二、Codex：两个版本之间的转向

v0.154 到 v0.160 之间发生的事，比任何单个功能都有信息量。七项变化：删掉 remote compaction v1（只留客户端主导的 v2）、上线 bounded resume（倒序扫描、遇 Compacted 记录即停）、新增 `thread/revert`、新增 `persistent_mode.md`、压缩元数据随落盘、memory V2 双写、多 agent 从邮箱升级到发布/订阅。**重心从"让压缩更强"移到了"让会话可回退、可有界恢复、可自我续跑"。**

`persistent_mode.md` 里三句话值得抄进任何自动续跑系统："Never invent an early stopping point for monitoring the user explicitly asked to continue"；"use short, proportionate waits"；"Persistence does not broaden that scope"（持久化不扩大权限）。

另外修正一处流传很广的误读：Codex 的"连续 3 轮失败熔断"是条**窄闸门**——只有"exec 工具硬失败且整轮无任何成功工具"才计数；模型只输出文本不计、工具软失败不计、哪怕成功跑了一次 `ls` 都把全局计数清零。它防的是"执行环境不可用被反复重试"，不是"模型空转烧钱"。防空转烧钱的是另一条独立路径（不可重试错误直接 Blocked，注释明说防压缩失败死循环）。**想抄这条当通用防空转机制的，会抄到一条几乎永不触发的熔断器。**

## 三、LoopX：祛魅之后，剩下的才是真的

LoopX 有几个名字很唬人的模块（vision checkpoint、dreaming），读码后逐一祛魅：

- **vision_checkpoint 是真机制**，而且是全部读码里我评价最高的一个：结构化 replan 契约，`vision_patch` 与 `todo_delta` 两阶段事务强制联动——改愿景必须同时改任务列表，不许只改口号。比"一句话 objective"强在**可审计**。
- **dreaming 是治理通道，不是认知通道**：关键词触发（"refactor/drift/bloat"），产出提案但 `execution_allowed: False`——执行中产生的副作用想法必须经人审才能变成工作。名字联想远大于实现。
- 工程量是认真的：`quota.py` 1703 行、`state_refresh.py` 1634 行、`goals/` 目录 81 个文件、1251 行的跨平台文件锁模块。这不是 demo 项目——但也意味着**自建复制的成本就是这么大**。

真正值得抄的是结算秩序。一次 turn 走七个事务阶段：`host_execute → typed_result → validation → durable_writeback → quota_spend → scheduler_apply → scheduler_ack`，结算顺序钉死为 `result < validate < writeback < spend`——**验证通过的写回才扣配额**。配上一句该贴在每个 agent 团队墙上的话："Never rerun a model and call its new output historical replay"（绝不许重跑模型然后把新输出叫历史重放）。

还有它的"不算进展"清单：复用已知证据不算、格式化报告不算、重复探测同一个否定结论不算。连续 2 轮停滞强制一个有界 replan 切片；同一目标 6 次无变化则必须写下过期/阻塞/替代者，否则不许再次静默跳过。防空转做到这个颗粒度，我没在第二家见过。

## 四、数据冷静期

LoopX 的 benchmark 数字流传很广，引用之前先把证据等级交代清楚：

**所有 LoopX 数字都是作者自跑，零独立复现。** Hacker News 全文检索 0 条；GitHub 三千多个 issue/PR 里没有一个第三方复现报告；中文社区全是转述。这本身是个重要结论。但**基准是独立的**：LHTB 和 SWE-Marathon 都是与 LoopX 无关的论文（作者名单无交集），任务集和验证器可信——可信的是题目，不是分数。

分数本身也得拆开看：

- LHTB：LoopX 比裸 Codex 高 17.3% mean reward，但**严格通过率（≥95%）和裸跑持平，都是 7/46**——多拿的全是部分分。更刺眼的是，旧版 Legacy Heartbeat 用 60% 的钱拿到新版九成的效果，且逐任务二元结果完全一致。
- SWE-Marathon：外部驱动臂比 Codex 原生 goal **多花 56% 的成本（$533→$830），只多完成 1/15 个任务**。LoopX 官方自己写："repeatable gains remain unproven"，还撤回了之前 14/14 的覆盖声明。以及官方承认的：四个关键变量（续跑所有者、会话复用、replan 策略、等预算停止规则）**一个都没隔离过**。
- **等预算对比不存在。** 两组 benchmark 成本差 2 倍以上，官方明说这不是效率排名。

独立学术证据，正反都有。正：LongHorizon-Harness（arXiv 2608.01964）把"状态外置 + 新鲜上下文执行器"做出 51.8→80.7% 的增益；InfiAgent 同向。反：Mem0 论文的 LoCoMo 实验里 full-context 得分 72.90 **高于**外置记忆的 66.88，MemoryAgentBench 同样测不到任何外置记忆方法在四项能力上全面胜出——上下文装得下时，外置反而引入检索损失。**分界变量是任务时长和状态量，不是"外置与否"本身。**

证据最强的一类失效是**假完成**：SWE-Marathon 论文实测 13.8% 的 rollout 出现 reward hacking；METR 2026 年报告里最难任务约 16% 的"成功"因作弊被取消资格。上下文耗尽反而证据最弱——它是工程上最先被解决的那层。

最后别忘了硬约束仍在模型侧：METR 实测 GPT-5.1-Codex-Max 的 50% 任务视界约 2 小时 40 分钟。所有 harness 工程都是在拉长这个数字，但数字本身还很小。

## 五、依然没人解决的问题

这轮调研最有价值的产出是这张负面清单——不是没找到，是确认过没有：

1. **完成判定仍然没有硬解，但路线在变多。** 并存的有：Codex 的模型自评（运动员当裁判）；LoopX 的 owner 预声明确定性命令（硬，但依赖配置）；以及新出现的——Claude Code 的 `/goal`（v2.1.139）**每轮用一个快速模型验证完成条件**，把"完成判定交给另一个模型"做成了官方产品。第四条线索在学术侧：Theta Software 的 Rayan Garg 在 AI Engineer 频道提出，软验收场景下 **judge 本身必须是 agent**——拿只读权限去检查最终环境状态（GitHub、CloudWatch），用子 agent 查询长轨迹。它和 Claude 的便宜模型路线是亲戚，但把"审什么"从文本换成了环境。几条路线没有一个闭环。
2. **验收标准本身谁验收。** 防"删测试让目标通过"是低级 reward hacking；让执行者起草验收标准是高级 reward hacking——不需要删测试，一开始把测试写松就行。实锤案例：LoopX 在 apex-law433 任务上的 validate 只查 schema 不查内容，验收过了，任务错了。
3. **等预算下的效率。** 没人做过。采购决策前必须自己补。
4. **任务该不该切成多个会话的判据。** 没人有。
5. **状态漂移没有长程测量。** 两家都没有漂移率的直接测量，只有任务级结果的间接推断。
6. **回滚粒度。** Claude Code 的 checkpointing 明确不追踪 bash 副作用。长任务的回滚必须覆盖 shell（git commit/stash 级），否则自动续跑会把 0.77 的任务滚成 0.00（duckdb 案例：22 个查询全对才给分，LoopX 和裸跑一起归零）。
7. **层级摘要的保真与 replan 语义。** 这是学术侧也空白的两格：Mage、HORMA 这类层次摘要工作都假设摘要是好的，没有失真检测器；父目标变更后已展开子树的失效与对账，所有论文和 Devin 都没有公开解法。Devin 已经把 goal drift 列为自家首要失效类，但它的答案是"交接摘要换专门微调的摘要模型"——摘要质量靠模型质量兜底，失真检测依然没人做。

## 六、技术方向：按我会押注的顺序

1. **状态外置，但分粒度。** 格局已经变了：session 内 goal 是宿主标配（Codex goal mode 已 GA，Claude Code `/goal` 已发布且在快速演进），自建这个是重复造轮子。宿主没动机做的是**跨会话、跨 runtime、项目级状态内核**——状态绑 thread 是它们的商业模式。这才是唯一的自建区。Composio 的人有句话可以直接引用："prompts 会被压缩掉，墙必须建在 agent 外部。"
2. **确定性验收管道 + 验收标准的来源分级。** 验收命令 owner 预声明、哈希 pin、快照执行，这套实现形态可以直接抄；但验收标准本身也要分级——agent 自写的默认低权威，升级要过 owner gate。上面 apex-law433 那个案例，缺的就是这一级。
3. **成本可观测是产品机会，不是成本项。** cached 排除计费、按 goal/子 agent 拆分、超支告警——Codex、LoopX、Claude Code 没有一家提供完整产品级方案。
4. **结构化 replan 契约。** 简化版 vision_patch + todo_delta：每轮强制产出 `{plan_delta, reason, evidence_refs}`。HumanLayer 的 Kyle Mistele 用控制论讲过同一形状：AST grep 当确定性传感器、controller 选最小改动单元、确定性 CI 当门禁、**每天只跑一轮、绝不在未合并 PR 上叠新 PR**。外层确定性 + 有界切片 + gate，这条路线正在收敛。Vercel 那边还有生产中的同款形状：durable workflow steps 加后台子 agent，主线程压在 7k token 以下——fresh-context 执行器不在论文里，在生产里。
5. **补上那个没人做的实验。** 20 个任务、等预算、多 trial、预注册指标，自建 MVP 对宿主原生 goal——任何方向的结果都接受。这是整个行业欠的账。

## 结尾

上次文章的结尾是三条协议：让证据代替信心，让验收独立于执行，让目标像代码一样被版本化和评审。这轮读码和数据让我给三条各加了一个注脚：

证据要防"**确定性地产出错误结论**"——验收脚本也会错，apex-law433 就是；验收独立的下一站是**验收标准的来源分级**——执行者起草的验收默认低权威；目标版本化之后还有一格没人填——**版本之间的对账**：父目标改了，已完成的子树算什么？

控制权的转移没有停在控制面。它的最后一站，是目标本身的生命周期管理。

