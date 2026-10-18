---
layout: post
title:  "千轮之病：一个 agent 运行时的 goal 解剖，和它给自己开的药方"
date:   2026-10-18 00:00:00 +0800
categories: [AI]
tags: [AI, Agent]
---


开源项目里有个罕见的场面被我撞上了：维护者在自己的 issue 里公开承认自家功能治不了一类病，同时预告了重写方案。

10 月 17 日，metask-ai/metacodes 的维护者 wayfind 在 issue #277 里写："现在的 goal 在长任务场景里面存在问题，在连续运行的一周以上的长任务里，goal 的目标已经影响到迭代上千轮后的代码继续演进了。"然后他预告了根治方案：依托 TinyKG 图数据库把任务逐层分解，每次注入上下文的不只是当前任务，还包括"DAG 上目标节点到当前节点的摘要"，并且——"后面会专门启动一个 pr 来做，做完之后也严格评估"。

承认症状、预告方案、承诺严格评估，三件套同时出现，在我读过的开源 issue 里是第一次。上一个写长程任务文章时我读的是 Codex 和 LoopX，这次我把这个仓库的 goal 相关代码和 PR 记录完整核实了一遍。这篇文章是我读到的全部，加上我的判断。

## 一、这是什么项目，为什么值得读

metacodes 是一个 Zig 写的 agent runtime，特色是把运行时能力封装成 C ABI（AgentCore）卖给宿主应用：Session、Run、压缩、权限，以及 2026-10-17 刚合入的 goal（PR #286，+2923 行，ABI Revision 23）。

先看文化，因为后面会发现**文化才是它最大的资产**。这个仓库的每个 PR 都带三样东西：本地门禁证据（多少测试过、多少跳过）、**变异测试**清单（每改一条规则，点名哪个测试会失败——比如"activate 忽略已耗尽的预算 → 迁移表测试失败"）、以及对 Lean 形式化镜像的维护（`control-plane/lean/` 下二十多个 .lean 文件，给检查门、预算、学习回合各建了一份形式模型）。评估则是预注册制：`evals/experiments/` 里的实验文件长这样——Claim、Cohort、Arms、Stage A/B、Stopping rule、Claim boundary、Authorization，**没有 owner 签字和预算上限，实验不许跑**。

## 二、现行 goal 解剖

**状态机**：六个状态（active / paused / blocked / usage_limited / budget_limited / complete），Host 和用户能发的动作只有四个（pause / activate / complete / block），迁移表很短：

| 动作 | 源状态 | 到 | 拒绝 |
|---|---|---|---|
| pause | active, paused | paused | 其他 → GoalNotActive |
| activate | 任意 | active | 预算已尽 → BudgetExhausted |
| complete | 任意 | complete | 不拒绝 |
| block | 非 complete | blocked | complete → GoalComplete |

两个细节值得记：`usage_limited` 是个**预留的死状态**，全仓库没有任何代码路径设置它（ABI 文档自己写明 "never sets it"）；`update` 把改目标、改预算、发动作三件事原子化——"提高预算并恢复"是一次 update，要么全应用要么全不变。

**计费（Meter）**：规则一句话——只有"Run 开始时 goal 是 active"的 Run 才计费，计每个 provider 响应的 `(input − cached) + output`（缓存在 provider 侧已归一扣除）和 Run 的墙钟时间，**无论 Run 以什么方式结束**。这是 PR #286 修掉的存量 bug：旧实现只在 REPL 计费、且只计成功的 Run。什么不计也写得很清楚：子 agent 不计（SpawnOptions.goal_meter 默认 null），模型以工具调用形式 fork 的 Skill 不计（可能与其他工具并行，共享 Meter 会竞态），paused 起跑的 Run 不计。

**预算中途耗尽的时序**（这部分的精确度我喜欢）：响应到达→记账→翻转 budget_limited→发事件→**不切断当前轮**→下一个 turn 边界注入一次"收尾提醒"（持久 user 消息，只注一次）→Run 结束结算墙钟再发一次事件→此后新 Run 不再计费、续跑被拒（GOAL_CONFLICT）。是"软着陆"，不是"拉闸"。

**我读码时发现的最有意思的细节——两条注入路径的不对称**。同一段续跑提示词（`<objective>` 包裹的目标原文 + "Do not start unrelated work"），在 CLI 的 `/loop` 里只作为该 Run 第一个 turn 的 API 负载、**不落持久会话**；而在 AgentCore 的 `RUN_INPUT_GOAL_CONTINUATION` 里会作为**持久 user 消息**写进会话、跟着 checkpoint 走。同一套 goal 语义，两种历史污染级别。跑一周的托管任务走的是后一条——这一点和第四节的病直接相关。

**checkpoint 的定宽段设计**也很能代表这个仓库的手法：goal 段里除了 objective 全部定宽，所以**计费永远不改变 checkpoint 的字节尺寸**——持久化预算的准入检查因此只需要发生在 set/edit/clear 三个 idle 时刻。不变量不刻在流程里，刻在数据布局上。

**ABI 哲学**：goal 的 set/update/clear 全部仅 idle 可用；非法迁移不静默纠正，返回 `GOAL_CONFLICT`——这跟 Codex 是反的（Codex 会静默 coerce，比如 active 超预算时被悄悄压成 budget_limited 且不报错）。

## 三、它对 Codex 唱的三处反调，和我的评价

PR #286 自己声明对标 Codex 的 thread goals（六状态、计费公式、软着陆都一致），刻意差异有三处。逐一评：

**拒绝即报错 vs 静默 coerce**——我站 metacodes。静默 coerce 让 Host 以为操作成功了；在长任务里，"以为成功了"的错误会复利。

**没有模型侧 goal 工具**——Codex 还给模型留了 `create_goal` 和 `update_goal`（complete|blocked 两值），metacodes 连这个都不给：模型只能在回复里**说**目标完成了，标记权归用户或 Host。续跑提示词里那句 "marking the goal is the user's decision, not yours" 把这条写死了。这是彻底的"运动员不许当裁判"，比我上次文章里 Codex 的版本更激进。代价马上会看到：**无人值守的一周长跑里，目标事实上被冻结了**。

**子 agent 用量不 roll up**——Codex 把子线程用量沿 agent 树滚入 root 预算（防逃逸），metacodes 明确不滚。这是一处真实缺口：子代理成了预算的逃逸通道。

## 四、千轮之病：机制解剖

维护者说"上千轮后目标妨碍代码演进"。这句话可以从代码里拆出精确的机制，三个因素，权重不同：

**结构根因：目标不可分层。** Goal 就是一个扁平字符串加一个状态加一个账本。注入文本里唯一的"进度"信号是 "Tokens used toward it so far: X of Y"——**那是预算表，不是任务进度表**。系统无法表达"七步完成了三步"，于是每一轮续跑都得从（可能被压缩过的）会话里重新推导"做到哪了"，而冻结的原文提供不了这个信息。

**放大器：冻结原文的每轮重注入。** 每个续跑 Run 注入一次完整目标原文；AgentCore 路径还把它持久追加。compaction 对 user 消息只有 20K token 的逐字保留窗——旧副本被摘要掉，**最新副本永远在场。陈旧锚点被不断刷新，而不是老化退出。** 且提示词里写着 "Do not start unrelated work"，主动压制模型重新解释目标的余地。

**修正无法传播：目标无版本化。** 改目标只能由用户/Host 在 idle 时做；`editObjective` 原地改、无修订号、无历史。百轮尺度，这些全是防漂移的优点；千轮尺度，它们共同构成负债。

外部有个印证可以引用：Theta Software 的人在 AI Engineer 频道讲长程任务时说，真正的难点是**序列复杂度——早期一个坏查询会级联放大**，而不是"把短任务链起来"。冻结目标的每一轮重注入，就是把 day-0 的 framing 变成每一轮的"早期输入"。

其实他自己仓库里就有同源实证：learning turn 的设计文档（§10）引用了 stall gate 的实测数据——**文本 nudge 在长上下文里会被忽略**，所以经验注入走确定性通道而非提醒。也就是说，他早就知道提示层手段在长程失效；"冻结原文每轮重注入"正是同一类手段，DAG 投影是他选择的结构解。

## 五、仓库里藏着半个答案

读这个仓库最意外的发现：**DAG 的下半截它已经建好了，只是没接上去。**

TinyKG 任务协议是现成的：`TaskCreate / TaskList / TaskGet / TaskUpdate` 一套模型可见工具，open/claimed/completed/failed 生命周期，认领时下发 `task_packet`（父目标、依赖、证据链接），TaskList 的叶子行带 **path 面包屑**，依赖只在 completed 后解锁。甚至还有个孤儿：`plan_commit.zig` 能把批准的计划文本落成任务 DAG（contain/depends_on 边）——但 plan 模式被有意删除后（PR #260，维护者的立场是"plan 不持有状态，不配进 core"），它失去了唯一的调用方。

此外还有两件半成品：`check_gate`——宿主 pinned 的确定性验收命令，verdict 落图；以及 learning turn 的 **lesson supersede**——append-only 写新教训、命名被替代者、召回时过滤。

问题是血管没接通：**goal 不知道任务图存在，任务图不知道 goal 存在，验收结果不驱动 goal 状态迁移。** 所以那个预告中的 DAG PR，真实工作不是"发明 DAG"，而是把已有的两层接通，外加回答三个权责问题：分解由谁 authoring（它拒绝过模型侧 goal 工具，但任务协议的工具本来就是模型可见的——矛盾待解）；节点完成由谁裁决（check_gate 是现成答案，只差接线）；续跑要不要 LoopX 式的前置判据（现在 ABI 的口径是"续跑次数与时机完全由 Host 决定"，即没有任何确定性判据）。

验收这条还有个外部旁证：Theta 在同一集里说，软验收场景下 **judge 自己必须是 agent**——只读权限去检查最终环境状态（GitHub、CloudWatch），用子 agent 查询长轨迹。这和 check_gate 的 pinned 命令、以及仓库里那份还是 design-only 的 isolated verifier 设计（fresh context、只读快照、只能降级不能放行），是同一条收敛线。（顺带：他在 #277 里挂着的另一个决策——Swarm 的 teammate 线程归谁——已在 PR #294 以 host-scheduled 落地；Ona 的人在同一频道论证"runtime 和编排都已解决，缺的是 swarm 协调原语"，正好给那个决策提供了一个外部词汇表。）

## 六、这个药方在行业地图上的位置

先说好消息：**这个方向不孤独，甚至是 2026 下半年的行业收敛点**。状态外置 + 层次投影 + fresh-context 执行 + 独立验收——LongHorizon-Harness（manager 持有外置任务状态、fresh-context executor、只读 auditor，且只有被独立验证的事实才能跨轮）、InfiAgent、OneDayAgent（显式分解成有界可执行单元）几篇论文和 Devin、LoopX 的产品实践全都收敛在这个形状上。

最接近他预告方案的是 Mage（arXiv 2606.06090）：两层状态树，底层是逐步的 action-observation 原文，顶层在**子目标与决策边界**生成摘要——几乎就是"当前任务 + root 到当前节点的路径摘要"，连摘要的触发点都一样。TME 把状态树从 tree 推广到 DAG；ReAcTree 的 agent 树带控制流节点，形状接近"任务图 + Swarm"的合体。他要做的结构在文献里都有近似原型，不孤单。

再说坏消息，两个无人区恰好都是这个方案的核心风险：

1. **层级摘要的保真度没有评测方法。** Mage、HORMA 这类层次摘要工作全都假设摘要是好的，没有失真检测器。DAG 化的本质是把"每轮注入原文"换成"每轮注入路径摘要"——**摘要每层蒸馏丢了什么约束，没有人有任何检测手段**。这是方案的头号新失效模式。
2. **replan 语义是空白。** 父目标变更后，已展开的子树如何失效、如何对账，论文和 Devin 都没有公开解法。而这个仓库现行 goal 连 objective 的版本号都没有。

还有一个前车之鉴值得摆在桌上：Box 的 CTO 在同一个频道亲口收回了自己去年的图式 agent 架构——"agent 基建的半衰期以月计"。图方案的脆弱点在检索质量，TinyKG 押注图检索，这个风险是真实的。

## 七、它的胜算在评估文化

方案本身的风险上面说完了。我最后想说的是：**我比读码之前更相信这个项目能做成这件事**，理由不在代码，在它的评估基础设施。

这个仓库的实验是预注册的：先写 Claim 和 Decision rule，再写 Stopping rule（"stage A 若无观测到 X 则 stage B 不跑"），最后有一栏 Authorization 空着等 owner 签字和预算上限。它给 learning turn 做的实验设计里，"对照臂用 observe 模式记录治疗臂本会做什么"这种细节都想好了。wayfind 说"做完之后也严格评估"——**在别的仓库这是公关辞令，在这个仓库这是一句有文件格式和门禁兜底的话**。

如果那个 DAG PR 要配一个最小可行实验，骨架其实现成：chained runner（它正在 #297 里为 learning turn 建造）跑 K 次连续续跑、attempt 之间强制压缩模拟历史更替、链中点做一次目标编辑模拟 replan——断言落在末段相位的隐藏 validator 通过率、约束探针违规率、以及作废/孤儿节点计数上。ground truth 来自任务作者冻结的分相位验证器，不来自模型自评。这个实验同时检验方向（节点粒度新鲜度是否优于扁平重锚）和失效模式（摘要丢约束、父变更对账）。

## 结尾

上一篇我说，控制权的最后一站是目标本身的生命周期管理。这个项目正在给这句话做对照实验：一边是一个被冻结目标拖垮的千轮任务，一边是一张还没开出来的 DAG PR 和一份等着的预注册表。

长程任务的所有难题，到最后都是认识论问题：**你怎么知道你完成了？** 大部分项目的回答是提高模型的自信，这个项目的回答是管理自己的不确定——把每条规则的反面写成变异测试，把每个宣称写成预注册实验，把"我们不知道"写进文档的 Claim boundary。

目标会不会分层、摘要会不会丢约束，DAG PR 开出来才知道。但一个把"我不知道"管理得这么好的项目，值得等它的 PR。

