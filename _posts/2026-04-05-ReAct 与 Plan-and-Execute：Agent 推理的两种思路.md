---
layout: post
title:  "Agent 推理模式复盘 | ReAct 与 Plan-and-Execute：Agent 推理的两种思路"
date:   2026-04-05 23:32:53 +0800
categories: [AI, Agent]
tags: [AI, Agent]
---


# 前言
这组文章一开始没想写这么大。

最早我只是想把自己踩过的 `ReAct` 坑记下来。结果一边写，一边翻日志，一边查资料，一边对源码，越写越发现问题根本不止一层。表面看是 `ReAct` 失控，往下挖会碰到 `Planning` 怎么失效，`ToolUse` 为什么逼着系统把执行权从模型手里拿回来，最后连 `Thought` 也不能再当成一个天然可信的东西。

所以后面干脆拆成了几篇。

里面有些是我真的踩过的坑，有些是我顺着坑往下推时冒出来的担心，也有些是我翻资料、看源码时慢慢确认下来的东西。它不是一套很工整的教材，更像一份边踩边记、边查边想的工程笔记。中间肯定有我自己的猜测，也有不少胡思乱想，但这些猜测和胡思乱想，基本都尽量往具体系统行为、资料或者源码上靠了。

如果这堆大杂烩能帮你少踩几个坑，或者至少在你踩坑的时候觉得“哦，原来别人也在这儿摔过”，那它就算没白写。



# 正文

假设你让一个 AI Agent 帮你查"特斯拉 2024 年第四季度的毛利率，和比亚迪比怎么样"。

这个任务拆开来看，需要好几步：查特斯拉的数据，查比亚迪的数据，然后做比较。问题是——Agent 怎么组织这些步骤？

两种完全不同的做法。

一种：边想边做。Agent 先想"我需要查特斯拉的数据"，去搜索，看到结果后想"还需要比亚迪的数据"，再去搜，最后做比较。每走一步，都看上一步的结果来决定下一步。

另一种：先把计划想清楚。Agent 先花时间规划："第一步查特斯拉财报，第二步查比亚迪财报，第三步对比"，然后按计划执行。

前者叫 ReAct，后者叫 Plan-and-Execute。这是构建 AI Agent 最基本的两种推理范式，也是做 Agent 架构设计时绕不开的一个选择。

下面我会分别拆开讲它们怎么工作，各自的强项和短板，最后聊聊实际中怎么选。

## ReAct：边推理，边行动

### 它在做什么

ReAct 这个名字来自 2022 年的一篇论文（Yao et al., 2022），是 Reasoning 和 Acting 的合写。想法直白：让大模型在"想"和"做"之间交替进行。

每次循环三个环节：

- Thought：模型分析当前状况，判断下一步怎么办
- Action：调用一个工具或执行一个操作
- Observation：拿到行动的结果

拿到结果后，回到 Thought，开始新一轮循环，直到任务完成。

### 完整走一遍

还是那个"特斯拉 vs 比亚迪毛利率"的问题，ReAct 的处理过程大概长这样：

```
Thought: 我需要查特斯拉 2024Q4 毛利率，先搜一下
Action: search("特斯拉 2024年第四季度 毛利率")
Observation: 特斯拉 2024Q4 毛利率为 16.6%，低于市场预期

Thought: 拿到特斯拉数据了，接下来查比亚迪
Action: search("比亚迪 2024年第四季度 毛利率")
Observation: 比亚迪 2024Q4 汽车业务毛利率约 20.3%

Thought: 两组数据齐了，可以对比
Action: finish("特斯拉 16.6%，比亚迪约 20.3%，比亚迪高出约 3.7 个百分点...")
```

注意看 Thought 那几行。模型在每一步都在"自言自语"——分析当前状态，决定下一步。这些思考过程用户平时看不到（除非开 debug 模式），但它们是 ReAct 的核心：正因为每步都在思考，模型才能根据实际看到的结果来调整策略。

如果第一次搜索"特斯拉毛利率"没拿到 Q4 的数据，模型会在 Thought 中发现这个问题，换个关键词再搜。这种"走一步看一步，不对就换方向"的能力，是 ReAct 最大的特点。

### 强在哪，弱在哪

**动态适应**是 ReAct 最突出的优势。每一步都基于最新观察做决策，天然能处理不确定的情况。搜索结果不理想？换个词。API 返回报错？换个方式。这种灵活性在和信息源交互的场景下特别有用。

**可解释性也不错**。Thought-Action-Observation 链条就是完整的推理记录，出了问题可以追溯每一步的决策逻辑，看哪一步走偏了。

但 ReAct 有几个让人头疼的地方：

Token 消耗大。每步都有一个 Thought，复杂任务可能十几轮循环，token 花得快。在按量计费的场景下，这笔开销不能忽视。

容易兜圈子。模型在某一步走了弯路之后，可能反复尝试相似的 Action，陷入死循环。实际使用中通常要设最大循环次数来兜底。

缺乏全局视野。整个过程中，模型是"走一步看一步"，没有对任务的宏观理解。对于需要协调多个步骤的复杂任务，这可能导致效率很低——它可能先查了 A，然后查 B，查完 B 才发现需要换个角度重新查 A。

### 运作机制

用伪代码来描述 ReAct，大概是这样：

```
while not done:
    thought = LLM.think(context + history)
    action  = LLM.choose_action(thought)
    result  = execute(action)
    history.append(thought, action, result)
```

一个循环，每轮都让模型基于当前上下文和历史来思考和行动。简单是简单，但效果出奇地好。

## Plan-and-Execute：先想好，再做

### 换一种思路

Plan-and-Execute 和 ReAct 截然相反。它不急着动手，而是先把计划想清楚，然后按计划走。

两个阶段：

- Plan：分析任务，生成一个有序的子任务列表
- Execute：按顺序执行每个子任务

执行过程中某个步骤失败了？触发 Replan——重新审视计划，做出调整。

### 同一个问题，Plan-and-Execute 怎么做

还是那个毛利率的问题：

```
─── Plan 阶段 ───

任务：对比特斯拉和比亚迪 2024Q4 毛利率

计划：
  Step 1: 搜索特斯拉 2024Q4 财报，提取毛利率
  Step 2: 搜索比亚迪 2024Q4 财报，提取毛利率
  Step 3: 对比两者毛利率，生成分析

─── Execute 阶段 ───

执行 Step 1: search("特斯拉 2024Q4 毛利率")
  → 16.6%

执行 Step 2: search("比亚迪 2024Q4 毛利率")
  → 约 20.3%

执行 Step 3: 对比分析
  → 比亚迪高出约 3.7 个百分点...
```

和 ReAct 对比一下，区别在哪？

Plan-and-Execute 在一开始就确定了三步走策略，然后按部就班地执行。它不需要每步都"想"，因为计划已经定好了。Execute 阶段甚至可以不调用 LLM，直接把参数传给工具就行。

但这也恰恰是它的弱点。如果 Step 1 的搜索结果里没有毛利率呢？Plan 阶段生成的计划基于模型对任务的初始理解，它还没看到 Step 1 的搜索结果。这时候要么硬着头皮按原计划走（可能后面的步骤都建在错误的基础上），要么停下来 Replan（额外的 LLM 调用，也有时间成本）。

### 几种变体

Plan-and-Execute 不是一种固定的模式，有几种常见的变体：

**单次规划**。一口气生成完整计划，执行到底不调整。简单粗暴，适合步骤明确、不确定性低的场景。

**多次重规划**。执行过程中遇到问题就停下来重新规划。灵活性强，但代价是额外的 LLM 调用。

**层级规划**。先定大方向，再逐层细化。比如大计划是"完成竞品分析"，子计划分别是"收集数据→分析对比→撰写报告"，每个子计划下面还有更细的步骤。复杂任务中，这种层级结构比一维的列表好管理。HuggingGPT 就是这个思路——先用 ChatGPT 做任务规划，然后把子任务分给 HuggingFace 上的专业模型。

### 运作机制

```
plan = LLM.generate_plan(task)

for step in plan:
    result = execute(step)
    if failed:
        plan = LLM.replan(task, plan, failed_step, error)
```

对比 ReAct 的 while 循环，Plan-and-Execute 是线性的、有序的。执行阶段不需要每步都调 LLM，这在 Token 成本上有优势。

## 逐项对比

聊完了各自的机制，现在做一个系统对比。

### 本质区别

一句话：**ReAct 是在线推理，Plan-and-Execute 是离线规划。**

"在线"不是说联网，是说决策是边执行边做的，每步都依赖最新信息。ReAct 的 LLM 调用贯穿整个执行过程。

"离线"是说计划在执行之前一次性生成，基于模型对任务的初始理解。Plan-and-Execute 的 LLM 调用集中在 Plan 阶段，Execute 阶段轻很多。

这个区别会渗透到方方面面。

### 多维度对比表

| 维度 | ReAct | Plan-and-Execute |
|------|-------|----------|
| 决策方式 | 增量式，逐步决策 | 一次性，全局规划 |
| 对新信息的适应 | 天然适应，每步都看新结果 | 需要显式 Replan 才能调整 |
| LLM 调用次数 | 多（每步都调） | 少（计划 + 可选 Replan） |
| 执行效率 | 低（每步都要"想"） | 高（按计划走） |
| 上下文窗口压力 | 大（要记住完整历史） | 小（计划本身就是压缩的历史） |
| 错误恢复 | 自然（下一步自动调整） | 需要机制支持（Replan） |
| 适合的任务类型 | 探索性、不确定性高 | 结构化、步骤明确 |

### 各自擅长的场景

**ReAct 更适合：**
- 信息检索。不确定搜索会返回什么，需要根据结果动态调整
- 多轮对话。用户每一轮回复都是新信息，需要实时响应
- 调试排错。需要不断观察输出，灵活调整策略

**Plan-and-Execute 更适合：**
- 工作流编排。步骤明确，比如 ETL 流程、数据处理 pipeline
- 多工具协作。需要把不同工具按特定顺序串起来
- 并行执行。计划中互相独立的步骤可以同时跑，Plan-and-Execute 天然支持这种并行性

### Benchmark 里的表现

在 Yao et al. 的原始论文中，ReAct 在 HotPotQA（多跳问答）和 ALFWorld（文字游戏）上优于纯推理（Chain-of-Thought）和纯行动（Act-only）。"边想边做"确实比"只想不做"或"只做不想"好。

但 Plan-and-Execute 类方法在某些结构化任务上表现更好。WebArena（网页操作基准测试）中，先规划再执行的方法完成率高于纯 ReAct——因为网页操作通常是确定性的步骤序列，全局规划的优势很明显。

一个有意思的发现：ReAct 在简单任务上容易"过度思考"，花很多 token 在 Thought 上却不如直接做；Plan-and-Execute 在简单任务上反而高效，因为计划阶段可以一步到位。

## Function Calling 和这两者是什么关系

这点容易混淆，值得单独讲。

### Function Calling ≠ ReAct

不少人的理解是"我用了 Function Calling，就是在用 ReAct"。

这个想法不对。

Function Calling 是大模型的一种能力——它知道什么时候该调用外部工具，能生成符合格式的调用参数。这是基础设施层面的东西。

ReAct 是推理范式——它规定的是"先思考再行动，看到结果后再思考"的循环模式。这是架构层面的东西。

打个比方：Function Calling 是"手"，ReAct 和 Plan-and-Execute 是"脑子指挥手的方式"。你可以用手去执行 ReAct 的 Action 步骤，也可以用手去执行 Plan-and-Execute 的 Execute 步骤。手本身不关心你用的是哪种指挥方式。

### 三层架构

把它们的层级关系画出来：

```
┌───────────────────────────────────┐
│           应用层（Agent）           │
│   对话助手 / 数据分析 / 编程助手     │
├───────────────────────────────────┤
│          范式层（推理策略）          │
│      ReAct  /  Plan-and-Execute  /  ...   │
├───────────────────────────────────┤
│          基础层（核心能力）          │
│   LLM 推理  +  Function Calling    │
└───────────────────────────────────┘
```

三层各管各的。基础层：LLM 提供推理能力，Function Calling 提供工具调用能力。范式层：决定推理和行动的时序——交替进行（ReAct）还是先规划再执行（Plan-and-Execute）。应用层：基于范式层构建具体的 Agent。

说"用了 Function Calling 就是 ReAct"，就好比说"有了手就是在做菜"——手是必要条件，不是充分条件。关键是怎么指挥这双手。

### 两个常见误区

**"Plan-and-Execute 不需要 Function Calling"**——不对。Plan-and-Execute 的 Execute 阶段同样要调工具。Plan 阶段说"Step 1：搜索特斯拉毛利率"，Execute 阶段就需要 Function Calling 来实际执行搜索。区别只在于调用的决策方式：ReAct 是实时决策，Plan-and-Execute 是按计划执行。

**"ReAct 是 Function Calling 的升级版"**——也不对。它们不在同一层。Function Calling 解决"怎么调用工具"，ReAct 解决"什么时候调、调完怎么处理"。两者互补，不互相替代。

## 融合：现实中的做法

纯 ReAct 和纯 Plan-and-Execute 都有短板，实际项目中很少只用一种。

### 为什么要混着来

纯 ReAct 的问题：缺乏全局规划。想象你在陌生城市找餐厅——走一步看一步，绕弯路是难免的。先看地图规划路线，遇到封路再灵活调整，效率会高得多。

纯 Plan-and-Execute 的问题：对变化反应迟钝。计划基于初始理解，但现实经常不按计划走。第一步搜索就返回了意外结果，原计划可能直接废了。

### 几种融合方式

**Plan-and-Execute + ReAct 混合**。Plan-and-Execute 定大方向，每个步骤的执行用 ReAct 模式处理。LangGraph 的 Plan-and-Execute Agent 就是典型实现——先规划，执行时保留灵活性。

**Reflexion**（Shinn et al., 2023）在 ReAct 上加了自我反思。Agent 完成任务后会复盘执行过程，总结经验，下一轮做得更好。相当于给 ReAct 加了一个跨回合的"元规划"能力。

**ReWOO**（Xu et al., 2023）走了另一条路。让模型在不看任何工具结果的情况下，先把所有需要的工具调用推理出来，然后批量执行。LLM 调用次数少了，上下文窗口压力也小了。代价是如果前置推理有误，后面可能全部白费。

### 一个趋势

2024 年以来的 Agent 框架越来越倾向于混合架构。Claude 的 tool use、OpenAI 的 Assistants API，底层都不是纯粹的 ReAct 或 Plan-and-Execute，而是根据任务特征动态选择策略。

这也符合直觉：简单问题不需要做计划，复杂问题不能只靠走一步看一步。好的 Agent 系统，应该能自己判断当前任务适合哪种方式。

## 怎么选

如果你在构建自己的 Agent：

**从 ReAct 开始。** 实现简单，一个 while 循环加几个工具定义就能跑，大部分场景够用。

**出现以下情况时引入 Plan-and-Execute：**

- 任务超过 5-6 步，ReAct 开始"迷路"
- 步骤之间有依赖关系，需要全局协调
- 需要并行执行多个子任务
- Token 成本成了瓶颈（Plan-and-Execute 的 Execute 阶段不需要每次都调 LLM）

**最终用混合方案。** 先规划大方向，执行细节用 ReAct 处理。遇到重大偏差时 Replan，然后继续。

一句话：**ReAct 是默认选项，Plan-and-Execute 是优化手段，融合是最终形态。**

---

**延伸阅读**

- ReAct 原始论文：Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models", 2022
- Reflexion：Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning", 2023
- ReWOO：Xu et al., "ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models", 2023
- Plan-and-Solve：Wang et al., "Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning by Large Language Models", 2023
