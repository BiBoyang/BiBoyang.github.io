# LoopX 的基准测试与长程任务 eval 调研

> 调研对象：[loopx-project/loopx](https://github.com/loopx-project/loopx)（main 分支，2026-10-18 抓取；约 6.3k stars，Python，2026-05-31 创建）。
> 证据来源：仓库内的研究 RFC、benchmark workspace、LHTB runner、共享运行时、DeepSWE/SWE-Marathon 实践文档、benchmark toolkit，以及官方 LHTB 研究简报页。
> 证据边界：读了 RFC 全文（1,387 行）、benchmark README（1,184 行）、LHTB runner/配置/preflight、五臂研究文档、RUNTIME.md、DeepSWE 与 SWE-Marathon 文档、toolkit README 的关键章节；没有逐行审计全部测试与私有运行数据。凡是文档写「proposed / not qualified」的，本文不当作已实现。

---

## 0. 一句话结论

LoopX 不是一个「跑 benchmark 的产品」，而是一个**给长程 agent 提供持久控制面的 harness**；它的评测也不是「刷榜」，而是一套**以 benchmark 原生结果为准、以 claim ladder 限制结论、以 treatment integrity 和 authority parity 防止自欺**的实验程序。

它最值得看的地方不是 46 个任务上的 +17.3%，而是三件事：

1. **把「你能声称什么」写成了分级制度**（C0–C4），工程就绪度（E0–E4）和声明等级正交；
2. **把 treatment（LoopX 到底有没有生效）做成了可审计的 receipt**，缺投递算 non-compliance，不算 treatment failure；
3. **把作弊/污染当成独立资格轴**（eligible / quarantined / invalid），不是评分后的备注。

它最明显的短板也同样清楚：**公开证据仍然停在「每格一次 trial 的探索性系统对比」**，RFC 里那套很漂亮的长程过程指标（stall、重复、replan 延迟、证据采用率、恢复损失）还没有进入已发布的结果表。

---

## 1. 先理解被测对象：LoopX 评的不是模型，是 harness

LoopX 的自我定位是「a control plane with a durable state kernel for long-horizon agents and teams」：把 objective、gates、todos、evidence、quota、handoff 这些控制状态从会话里抽出来，持久化到跨会话、跨宿主的一层；执行器（Codex / Claude Code / DSH / Cursor）只负责跑一个有界的 turn。

这决定了它的 eval 问题与普通 benchmark 不同：

> 在什么 task / model / host / budget 条件下，一个外置的持久控制面能把**可验证的长程工作**提升到足以抵消它的协议、延迟和复杂度成本？

注意这句话里的三个关键词：

- **可验证**：只认 benchmark 原生 verifier 的结果，不认 LoopX 自己的协调分；
- **长程**：任务要跨上下文窗口、跨多次模型停手、跨无人值守窗口；
- **成本**：协议税（protocol tax）必须被拆开计量，不能用「更多 Todo、更多 control call」冒充能力。

所以它的 benchmark 设计首先要解决的不是「题难不难」，而是「**treatment 有没有真的发生、两臂是否真的只差一个变量、结论能说到哪一级**」。

---

## 2. 评测纲领：两条车道、六个基准、五级声明

### 2.1 两条严格分离的车道

RFC 第一节把程序拆成两条不能混的车道：

| 车道 | 问的问题 | 允许的产出 |
|---|---|---|
| **Capability evidence** | 一个 pinned LoopX harness 是否在公平、可复现的比较下改善了 benchmark 原生结果、效率或恢复 | 有 claim level 的能力声明 |
| **Mechanism research** | 把 benchmark 当实验环境，检验 stride、evidence delivery、replan、research exploration、human attention、memory utility 等**有类型的假设** | 可以是负结果，可以永远不上榜 |

这条分离很重要：很多团队把「机制实验」和「能力证明」混在一起，最后既说不清因果，也不敢发负结果。LoopX 明确允许机制研究「non-leaderboard indefinitely」。

### 2.2 六个基准，不是一个大杂烩

初始三件套是 **ALE / LHTB / DeepSWE**，后来又加了 **StartupBench / LoopsBench / WideSearch**。它们不是按「名气」选的，而是按**证据维度互补**选的：

| 基准 | 它提供的独特维度 | 在 LoopX 研究里的角色 |
|---|---|---|
| **ALE**（Agents' Last Exam） | 跨 CLI/GUI 的专业工作流、真实交付物、1,500+ 任务、13 个行业簇 | 外部效度：控制面能不能迁移到软件之外 |
| **LHTB**（Long-Horizon Terminal Benchmark） | 46 个容器化任务、9 类、数百个依赖动作、连续 reward `[0,1]`、隐藏/回放 verifier、检查点 | 长程动力学主实验室：停滞、重复、replan、恢复 |
| **DeepSWE** | 113 个原创长程软件任务、91 个活跃仓库、5 种语言、手写 verifier 按功能而非参考 patch 判分 | 软件交付的因果证据；benchmark 能力的孵化环境 |
| **StartupBench** | 97 个市场验证过的创业工作流、多格式交付物（DOCX/XLSX/PPTX/PDF）、artifact-first + 加权 rubric（平均 25.3 条/任务） | 交付物质量、格式合规、自验证幻觉 |
| **LoopsBench** | 多单元终端软件、模块依赖图、incomplete/partial/complete 三档 verifier | 部分完成 vs 完整完成、依赖图排序 |
| **WideSearch** | 200 个双语广域检索任务、18 个行业、Item F1（精确/数字近似/URL/日期/LLM judge） | 规模与完整性、检索窗口、证据门控 |

RFC 明确禁止把 ALE 分数、LHTB reward、DeepSWE pass rate 平均成一个「LoopX 数」。每个 benchmark 必须在自己的原生度量空间里报告。这是我在同类项目里见过的最清醒的一条纪律。

### 2.3 C0–C4：先说你只能声称到哪一级

| 级别 | 含义 | 关键约束 |
|---|---|---|
| **C0** | 复现与 adapter 保真 | 能跑通原生 runner、不改任务语义；**不声称任何 LoopX 收益** |
| **C1** | 控制面可观测 | 只读记录状态、进度、成本、恢复、失败归因；**不改变 worker 决策** |
| **C2** | 单 benchmark 内的因果证据 | 匹配、重复的比较，隔离一个机制或一个完整 profile；声明被限定在 benchmark/model/harness/任务层/预算 |
| **C3** | 跨 benchmark 泛化 | 同一机制方向在至少两个实质不同的 benchmark 家族复现；第三个家族的 null 也要报告 |
| **C4** | 产品晋升证据 | C2/C3 + 模型行为/状态机资格 + 开销与权限预算 + 非 benchmark 的产品 canary；**benchmark 证据本身不能改生产默认** |

这套阶梯的用处在于：它把「我们跑了个 benchmark」和「我们证明了产品价值」之间的巨大鸿沟，变成了几个必须逐级填的坑。绝大多数团队缺的不是 C2，而是**愿意承认自己还在 C0/C1**。

---

## 3. 实验契约：比较单元、四种臂、公平性

### 3.1 比较的最小身份

RFC 规定的最小实验身份是一个十元组：

```text
(benchmark_id, benchmark_revision, task_id, task_stratum,
 environment_digest, verifier_revision, model_id, model_revision,
 harness_id, harness_revision, policy_profile, seed, budget)
```

未知值必须显式保留；显示名、散文 prompt、「同一模型家族」都不算身份。

这条看起来像废话，但它直接堵住了最常见的三类自欺：拿不同 revision 的任务比、拿不同 scaffold 的结果比、拿「都是 GPT-5」当同一模型。

### 3.2 四种臂，而不是「baseline vs ours」

| 臂 | 定义 | 它能回答什么 |
|---|---|---|
| **Native baseline** | benchmark 支持的参考 scaffold，或无 LoopX 的声明 CLI harness | 原生上限/基线 |
| **Passive LoopX** | worker 决策与 benchmark 契约完全不变，只做只读观测与 compact settlement | **harness tax**：光挂控制面要付多少成本 |
| **Governed LoopX** | 一个声明的 profile 可以影响 continuation、checkpoint、replan、recovery | treatment 的整体效果 |
| **Mechanism ablation** | 从 governed 父 profile 里只改一个命名机制，其余全部固定 | 单机制因果 |

辅助的人类/模拟器干预是**单独的研究家族**，永远不能当作自主 leaderboard 臂。这个区分比很多论文都严谨。

### 3.3 公平性与 treatment integrity

匹配单元里必须钉死：task input、environment、verifier、model revision、reasoning effort、budget、network/tool envelope、starting state。runner 和 harness 的差异必须**声明**，不能藏在模型名后面。

更关键的是这一组：

- 每个 treatment 必须发出 **compact typed receipt**，证明哪些机制被 delivered / triggered / accepted / rejected / unused；
- **缺投递是 non-compliance，不是 treatment failure**；
- crash、setup failure、verifier failure 保留独立的 attempt 与 failure class；
- task selection 与 primary metric 必须在看结果之前注册；
- 重复比较用 paired tasks 和 seeds；`N >= 5` 是默认下限，不是统计功效的保证；
- 昂贵的 ALE 单元可以用预先声明的序贯设计，但**停止规则不能取决于当前效果是否好看**。

最后一条是整份 RFC 里最像「有实战经验的人写的」的地方。绝大多数「我们跑了几次就停了」的评测，坏在停止规则上。

### 3.4 结果分层：内部指标永远不能翻案

每份实验报告必须把这几层分开：

- benchmark-native outcome；
- LoopX control-plane observations；
- cost 与 latency；
- assisted intervention（如果有）；
- treatment-integrity status；
- benchmark-integrity / arm-authority-parity status；
- publication / leaderboard eligibility。

RFC 的原话是：内部的控制分可以用来诊断行为，**不能加到原生任务分上，也不能把失败的任务变成成功**。

---

## 4. 度量模型：原生结果只是第一层

RFC 第 6 节把度量分成五块。前三块是常规，后两块是 LoopX 的特色。

### 4.1 Native outcomes

benchmark 原生 score / reward / pass；task 与 stratum 成功率（带不确定性）；官方子分；最终 artifact/verifier 结果；submit 与 leaderboard eligibility。

### 4.2 Efficiency

wall time、model tokens、provider cost、tool calls、agent steps；**score per unit cost/time 与原始分并列报告**；有 checkpoint 时报告 reward area under the time/step curve；到第一个 material delta 和到分数阈值的时间与成本；诚实成功/耗尽/阻塞/无后续之后**未使用的预算**。

### 4.3 Long-horizon control quality（核心）

这是整套东西里最有价值、也最没被公开证据兑现的一节。它列了：

- materially equivalent work-slice repetitions（实质等价的重复工作切片）；
- idle / maintenance loops accepted after a replan obligation（replan 义务之后仍被接受的空转/维护循环）；
- trigger-to-context、trigger-to-new-direction、trigger-to-material-delta **三种延迟**；
- evidence delivered / used / contradicted / ignored 四态；
- 中断后的 duplicated work 与 recovery loss；
- stale-state、premature-terminal、repeated-blocker、harness-conflict 四类比率；
- durable settlement lag 与 resume quality；
- **protocol tax 拆成 model tokens / control calls / wall time / attention 四项**，而不是一个「control call 占比」的百分比。

并且明确：这些测量必须来自 typed observations、receipts、runner events 或 verifier checkpoints；**散文相似度和关键词匹配不能当语义真值**。

### 4.4 Human attention（仅 assisted 研究）

人类/模拟器的 attention minutes 与响应延迟；改变 authority 的 gate vs 仅状态通知；accepted/declined/expired/unused 的 wishlist 项；干预后避免的浪费工作；false escalation 与 unnecessary gate rate；固定干预预算下的 value of information。

### 4.5 Benchmark integrity / anti-cheating

一段值得全文抄下来的立场：

> A correct outcome is not eligible evidence when one arm had access to hidden answers, reference artifacts, verifier implementation details, post-run grading material, or a broader undeclared permission envelope. Integrity is an independent qualification axis, not a note attached after scoring.

审计必须消费**结构化 runner facts**：mount 与文件可见性、environment/capability manifests、network policy、artifact staging phases、tool-access events、verifier invocation ownership、cross-arm envelope diffs。**不能**从模型散文、命令子串、或「答案像参考解」推断作弊。

三种处置：`eligible` / `quarantined` / `invalid`。公开 receipt 只含稳定 run identity、pinned policy 与 environment digests、parity status、disposition、reason codes、脱敏证据引用；公开 receipt 不能把未知的私有审计升级成 eligible。

---

## 5. 工程实现：一次 LHTB trial 到底怎么跑

### 5.1 分层

```
benchmark-native runner (Harbor)
  └─ shared runtime: benchmark.runtime.harbor:BenchmarkCodex
       └─ 执行模式：plain / native-goal / heartbeat / turn / loopx-goal
            └─ LoopX external_scheduler_worker.py
                 └─ 每次 wake：一次新的 codex exec（不是 exec resume）
```

任务、环境、verifier、分数留在 Harbor；LoopX 只提供控制面与 compact 观测。这个边界是 RFC 反复强调的「benchmark truth 不被 LoopX 替换」。

### 5.2 LHTB runner 的具体配置

`benchmark/LHTB/configs/heartbeat-generic-cli.yaml`：

- 46 个任务，`n_attempts: 1`（这是关键限制），`n_concurrent_trials: 4`；
- `environment.type: docker`，清空代理变量；
- agent 是 `benchmark.runtime.harbor:BenchmarkCodex`，模型 `openai/gpt-5.6-sol`，`reasoning_effort: max`；
- `execution_mode: heartbeat`，`iteration_context: fresh`，`goals: "false"`（禁用 Codex 原生 Goal，确保 continuation 的归属是 LoopX），`web_search: disabled`；
- Harbor 外层超时 5,400s；scheduler 5,080s；单次 wake 4,800s；
- 46 个任务里 22 个 offline、24 个允许互联网；offline 任务只接内部 `lhtb-modelonly` 网络（能到模型网关，没有公网路由）；
- verifier 策略：44 个共享、2 个独立（`langchain-version-migration`、`nbody-accel-iterative`）；
- verifier feedback 是 binary（`HB_VERIFIER_FEEDBACK_MODE=binary`）。

执行流（README 原样）：

```text
stage native Codex + current LoopX source/profile
  -> expose staged Node 22 through BASH_ENV
  -> create trial-local registry/runtime/task document
  -> bootstrap one trial-local Goal
  -> register benchmark-agent
  -> configure replan_after_effective_turns=3 and read it back
  -> plan phase Todos from the task
  -> start LoopX external_scheduler_worker.py
       -> quota should-run --runtime-profile generic_cli
       -> when allowed, invoke benchmark.runtime.worker
            -> create a unique TURN_ID
            -> heartbeat-prompt --thin --runtime-profile generic_cli
            -> require ok=true and non-empty current task_body
            -> use the isolated trial CODEX_HOME
            -> codex exec --json, with task_body on stdin
            -> save JSONL/receipt and emitted session files
       -> obey LoopX local_scheduler wait/stop hints
  -> Harbor runs interim/final verifier and owns trial termination
```

产物结构（每次 trial）：

```text
agent/
  loopx-install.json
  loopx-worker-phase-*.log
  trajectory.json              # 聚合后的 ATIF
  wakes/<TURN_ID>/
    heartbeat.json
    task-body.md
    invocation.json
    codex-events.jsonl
    codex-stderr.log
    receipt.json
    sessions/.../*.jsonl
```

`trajectory.json` 把每次 fresh wake 的 JSONL 聚合成一条 ATIF；原始 per-wake 文件保留，用于审计 LoopX 决策、实际 task body、模型调用、token 用量、settlement。这正好是「trace 是一等公民」在 benchmark 场景的落地：**每个 wake 都有独立身份、独立 receipt、独立字节级事件流**。

### 5.3 preflight：fail-closed 的入场检查

`benchmark/LHTB/scripts/preflight.py` 是一个很好的工程范本。它在**不调用模型**的前提下检查：

- LHTB 任务数恰为 46；
- offline/online 分布恰为 22/24；
- verifier 的 separate 集合恰为那两个任务；
- 选中任务数等于期望值，且都在任务目录里；
- Harbor adapter import path、模型、reasoning、native Goal 设置、web search disabled；
- LoopX 源码 commit 等于期望 commit；
- `external_scheduler_worker.py` 存在且能解析两种 stop action；
- shared offline Codex adapter 存在；
- 当前 CLI 的 `configure-goal` 真的支持解析出来的 replan cadence（读 `--help` 的 choices，不是假设）；
- Harbor / Codex binary / code-mode sidecar / portable Python / Node 版本；
- Harbor 的 model-only Docker patch 真的打上了；
- Docker daemon 活着，内部 model 网络 `Internal=true`；
- 模型网关 `/health` 可达。

最后输出一个 JSON receipt：`ok`、config、task_count、loopx_commit、runtime_profile、execution_mode、iteration_context、home_scope、model、reasoning_effort、replan 设置、verifier_policy、failures。

这是「在场证明」的工业化版本：不是跑完看退出码，而是**开跑前用直接证据证明实验要件齐全**。

### 5.4 五种执行模式与两个独立消融轴

| 模式 | 执行/续跑 | LoopX 技能与状态 |
|---|---|---|
| `plain` | 一次 Codex exec，native Goal 关闭 | 无 |
| `native-goal` | 用 Codex 原生 Goal transport，objective 固定 `Finish the task.` | 无 |
| `heartbeat` | 产品 thin heartbeat + 外部 scheduler，fresh 或同 session resume | 有 |
| `turn` | 公开 Turn CLI，typed result，独立 validation，settlement | 有 |
| `loopx-goal` | 产品 Goal body + 原生 Goal transport | 有 |

两个独立消融轴：

- `iteration_context`：`fresh`（每次新会话）vs `resume`（复用同一 native session ID）；
- `task_entry`：`seeded-todo`（种一个通用执行 Todo）vs `loopx-planned`（先跑产品 `todo plan` checkpoint，再执行）。

`turn` 模式还要求一个独立保护的 `validation_command`（argv 数组），候选结果从 stdin 进去；缺 validation 会在执行前失败。runner 不提供「HEAD 动了/工作区干净/退出码为 0」的替代品，也**绝不调用隐藏 benchmark verification 来提供中间反馈**。

### 5.5 checkpoint 与长程连续性

checkpoint 被明确标成「inert capture」——研究续跑的前置条件，不是已资格化的研究 continuation：

- 请求是一个 host 上的 JSON 文件，声明 destination、components、point_metadata；
- destination 必须是 trial log owner 的 `checkpoints` 目录的新直接子目录；
- capture 在一次成功 execute wake 的 settlement 之后、下一次 wake 之前；用剩余 phase budget，上限 30s；
- 保留 SQLite 已提交 WAL；拒绝源文件变化/符号链接；从不覆盖 destination；
- capture 失败单独记录，不重放工作、不改已结算结果；
- 读回用 `runtime.checkpoint_artifacts` 的 `verify` / `materialize`；两者都不 adopt state、不启动执行；
- `research_point_qualified`、`execution_authority_granted`、`privacy_certified` 保持 false；
- 支持 `trigger: fresh_replan` 的**决策前**捕获，而且第一次尝试即使失败也保留，重试不能用更晚的状态替代它。

这套东西的复杂度说明一件事：**长程 eval 的难点不是「跑得久」，是「在正确的时间点留下可验证的状态，并且不把捕获本身变成干预」**。

---

## 6. 已发布的证据：三份材料，三种诚实度

### 6.1 LHTB 五臂研究（主证据）

设置：46 个匹配任务，模型 `GPT-5.6 Sol`，`reasoning_effort=max`，Codex Web Search 关闭；五个臂：

> 先分清两个东西：LHTB 官方模型对比用的是 Terminus-2 + 90 分钟预算；下面这份是 LoopX 自己的独立五臂研究，runtime、预算、replacement 都不同，**不能和官方榜直接比**。

1. Plain Codex app-server
2. Native Codex Goal
3. LoopX SSH-Goal（历史）
4. Legacy LoopX 0.5.3 Heartbeat over app-server（历史）
5. LoopX 1.0.3 Heartbeat，`generic_cli` + 每次 wake 一次 fresh `codex exec`

结果：

| 臂 | Mean reward | Success ≥95% | Success >80% |
|---|---:|---:|---:|
| Plain | 0.4218 | 7/46（15.2%） | 12/46（26.1%） |
| Native Goal | 0.4475 | 4/46（8.7%） | 14/46（30.4%） |
| LoopX SSH-Goal | 0.4678 | 6/46（13.0%） | 12/46（26.1%） |
| Legacy Heartbeat | 0.4794 | 7/46（15.2%） | 15/46（32.6%） |
| **LoopX 1.0.3 Heartbeat** | **0.4948** | **7/46（15.2%）** | **15/46（32.6%）** |

对 Plain：+0.0731（+17.3%），17 胜 / 13 平 / 16 负，strict solve 7 vs 7。
对 Native Goal：+0.0473（+10.6%），23 胜 / 13 平 / 10 负，strict solve 7 vs 4。

成本（描述性，口径不同）：Plain $212.97、Native Goal $344.25、LoopX $551.73；token：251.72M / 293.81M / 505.10M in + 3.64M out。

**最值得注意的不是均值，是分布**：全 46 个任务的 median paired delta 对 Plain 是 **0**，对 Goal 是 **0.00026**。均值增益集中在少数任务上：

- Research & modeling：+0.2802 vs Plain（4/0/0）；
- Logic & puzzles：+0.2739 vs Plain；
- Systems, performance & security：+0.1732 vs Plain，但**去掉 PoC 一个任务后变成 −0.0065**；
- Multimodal：六个任务的绝对 delta 全部 <0.05；
- DuckDB：LoopX 0.0000，Native Goal 0.7697——一个「正确性否决」的典型；
- Snake：LoopX 0.6164，Plain 0.8415——保留进度不是充分条件。

这些反例在官方简报里是主动放出来的，不是被藏起来的。这一点比数字本身更值得学。

### 6.2 SWE-Marathon：15 任务 × 3 模式，45 trial

模型 `GPT-5.6 Sol`，`reasoning_effort=high`，预算压到任务时限的 ~30%（`agent_timeout_multiplier=0.3`）。

| 模式 | reward | partial | 花费 | 自收工 | 续跑 | 解锁 | 构建失败 |
|---|---:|---:|---:|---:|---:|---:|---:|
| plain | 0.267 | 0.710 | $368 | 0/15 | 0 | 0 | 0/15 |
| goal | 0.267 | 0.767 | $533 | 12/15 | 7 | 0 | 0/15 |
| heartbeat | 0.333 | 0.778 | $830 | 13/15 | 42 | 8 | 0/15 |

关键不是 +0.011 的 partial，而是三个行为差异：**自收工从 0/15 到 12/15**（原生 Goal 带来的「主动收尾」），以及 heartbeat 的 42 次续跑 / 8 次解锁。这些是长程控制面的直接行为证据。

这份文档还带了一个**更正**：SSH Goal 与 Codex CLI 两组的数据和结论已撤回，原始记录不删除，撤回不按分数选样本。这是我在 benchmark 文档里少见的「负结果/撤回结果保留为一级公民」的实践。

### 6.3 DeepSWE pilot：方法最完整，公开分数最少

DeepSWE 有 113 个原创长程软件任务、91 个活跃仓库、5 种语言；官方用 mini-swe-agent 做 scaffold 一致性，Pier 可以驱动 Codex / Claude Code。LoopX 的 pilot 明确是「harness 价值，不是模型榜」：

- **frozen selection**：先冻结候选顺序，再按顺序筛 baseline；基础设施/启动/关闭/verifier 失败不算任务失败，用冻结队列里的下一个替换；**verifier 结果已经告知 controller 之后不许重跑**；不许浏览原始任务/解 artifact 来挑替换。
- **native Goal proof**：baseline 必须走 Codex app-server Goal API，不能是 `codex exec`、不能是首 token 为 `/goal` 的 prompt、不能是外层轮询冒充 Goal。事务是 `initialize → thread/start → thread/goal/set → thread/goal/get → turn/start → 观察关联 turn 终态 → 继续观察自动续跑 turn → Goal 离开 active 或超时 → 独立 verifier`。
- **三条 product-path proofs**：Goal body 是按 `codex_app_ssh_goal` profile 生成的；LoopX skills 装进了 app-server 实际使用的 `CODEX_HOME`；Goal body 指向的 LoopX release-snapshot CLI 确实存在。而且要用 `skills/list` 在 thread 创建前证明 Codex 真的发现了技能集——**文件系统检查不算 treatment fidelity 证据**。
- **authority/anti-cheating**：两臂拿到相同的 task-visible filesystem、network、sandbox、approval policy、model credential envelope、tool surface；都不能读 evaluator answers、hidden references、verifier source、expected patches、别的 trial 的 workspace/state/trajectory、controller-private manifests。私有结构化审计比对实际 tool access 与 runner-owned isolation attestations；公开 receipt 只含稳定标签、计数、digest、reason code。
- **preflight**：pinned runner/task-set revision、case/arm identity、model/effort/time/token/concurrency/retry envelope、answer/verifier denial、cross-trial isolation、no-upload/no-submission、LoopX CLI 与 skill readback、app-server 真的发现技能、worker-before-verifier ordering、exact-job container binding、compact result/closeout destination。

这份 pilot 的方法论完整度高于它公开的分数——目前只公开了 behavior-discovery 的探索性发现，不是完整结果表。

---

## 7. 它到底怎么评「长程」：八个可观测面

把 RFC 的度量模型翻译成可执行的问题，LoopX 的长程 eval 实际在八个面上取证：

1. **完成度**：原生 reward / pass / strict solve，以及最终 artifact/verifier 结果。
2. **进度形状**：有 checkpoint 时，reward 随时间的曲线、到阈值的时间、AUC；不是只看终分。
3. **停滞与重复**：实质等价的工作切片重复、replan 义务之后的空转/维护循环。
4. **replan 质量**：从触发到新方向、到 material delta 的延迟；方向变化有没有带来 reward 进展。
5. **证据流**：evidence delivered / used / contradicted / ignored；read receipt 只证明投递，不证明采用。
6. **恢复**：中断后的重复工作、恢复损失、durable settlement lag、resume 后的质量。
7. **失败形态**：stale-state、premature-terminal、repeated-blocker、harness-conflict 的比率。
8. **协议税**：把开销拆成 model tokens、control calls、wall time、attention 四项；不是算一个「control call 占比」。

### 7.1 三种 stride：长程控制到底在哪个尺度上发生

RFC 把长程控制拆成三种嵌套的 stride（[Hierarchical Agent Stride Control v0](https://github.com/loopx-project/loopx/blob/main/docs/architecture/rfcs/hierarchical-agent-stride-control-v0.md)），这是它和普通「多轮 eval」最不一样的地方：

- **Effect stride**：下一次「决策相关的环境观察」返回模型之前，可以执行多少有因果关系的工作。目标单元是 coherence slice 内的一个 effect program。
- **Delivery stride**：下一次轻量控制干预与 durable settlement 之前，可以执行多少承载结果的工作。目标单元是一个 Todo 拥有的、有证据的 bounded delivery slice。
- **Authority stride**：下一次可能改变 scope / acceptance / permission / direction 的重干预之前，可以自主跑多久。目标单元是一个可自主终止的 segment。

三者不是三个 timeout，也不是三个固定计数。内层由 host / effect interpreter 拥有，中层由 Turn/Todo/settlement 生命周期拥有，外层由 goal / vision / gate / human authority 拥有。内层结果可以迫使提前 delivery settlement，delivery 结果可以迫使提前 authority escalation；但**一个 scheduler tick 不能凭空制造任何一种语义转换**。

对应的失败也很具体：effect 太短 → 模型往返、上下文重入、工具开销；effect 太长 → 决策相关观察被晚消费，错误和副作用复利。delivery 太短 → Todo 碎片化、重复调度、local-completion bias；delivery 太长 → 证据过期、writeback 延迟、一个 Todo 掩盖方向变化。authority 太短 → 人的注意力被无新授权的干预消耗；authority 太长 → scope drift、late steering、权限错误、不诚实的非终止。

实验分工：DeepSWE 测 effect / delivery stride（仓库调查、实现、验证）；LHTB 测 delivery stride、checkpoint cadence、矛盾 verifier 反馈后的纠正；ALE 测 authority stride 和异构工具下的跨面交付。RFC 反对一个全局的 tool-call / Todo-count 阈值，主张按 model × work-class 估响应曲线——目标是「在保持决策连贯、可逆、证据新鲜、权限正确的前提下，最大的 stride」，不是「越大越好」。

这也解释了为什么 LHTB 要用「数百个依赖动作 + 中间 checkpoint + continue-until-timeout」：只有这种任务，才能把「第几步投递、第几步纠偏、第几步该停」变成可观测的自变量。普通单轮 benchmark 测不到这一层。

再往上一层，是 **episode-based evaluation**（目前是 proposed refinement）：以「一个 scoped question / 竞争解释、一个区分实验、实际 artifacts 与观察、由此产生的决策」为分析单元，报告一个向量而不是一个未校准的总分：

- Native outcome；
- Information（独立复核过的 episode 中，有效实验改变了某个决策相关不确定性的比例）；
- Discrimination（完成的实验里，真正区分了其声明的竞争解释的比例）；
- Adoption（有后续机会、且有 artifact/behavior 追溯后果的证据采用）；
- Repetition（同问题/干预/输入、没有新信息的可评估 episode）；
- Cost & coverage（episode/资源计数、墙钟区间、控制/等待/恢复/缓存 token）。

并且要求：两个独立人类编码者、报告 episode 边界与维度一致性、冻结 rubric 后再测 judge、先隐藏臂标签和最终分数、分别报告 model-judge 的 precision 与 recall（含 abstention）。这套东西比大多数「LLM-as-judge 一致性 90%」的说法严谨得多。

**但请注意**：这一节在 RFC 里明确写着「proposed refinement / does not close packaged-product or independent scientific qualification」。也就是说，长程过程指标目前更多是**测量纲领**，不是已发布的 LHTB 结果表。

---

## 8. 值得抄的十条

1. **Claim ladder 先行**。先写「这个实验最多能声称到 C 几」，再决定跑多少、跑多久。工程就绪度（E0–E4）与声明等级正交：E2 跑得再顺，也不会自动变成 C2。
2. **Passive arm**。在 governed arm 之前先跑只读观测臂，把 harness tax 单独量出来。否则你分不清「控制面有用」和「控制面很贵但恰好没拖垮」。
3. **Treatment receipt**。delivered / triggered / accepted / rejected / unused 五态；缺投递 = non-compliance，不是 treatment failure。这一条能救掉大量「我们以为加了，其实没生效」的假通过。
4. **Integrity 是独立资格轴**。eligible / quarantined / invalid；只从结构化 runner facts 推断，不从散文推断；公开 receipt 不能把未知审计升级成 eligible。
5. **Authority parity**。两臂的 filesystem、network、sandbox、approval、credential、tool surface 必须相同；差异要声明，不能藏在模型名后面。
6. **Preflight fail-closed + receipt**。开跑前用直接证据证明任务数、网络策略、verifier 策略、commit、版本、网关、patch 都在位；不是跑完看退出码。
7. **结果分层**。native outcome、control observation、cost、integrity、eligibility 分开；内部控制分永远不能把失败翻成成功。
8. **原生度量空间**。六个 benchmark 各报各的，禁止平均成一个数；跨家族只做方向复现，不做分数平均。
9. **负结果与撤回是一级公民**。SWE-Marathon 撤回两组、LHTB 主动放 DuckDB/Snake 反例、median delta = 0 照写。这比任何「SOTA」都更能建立可信度。
10. **Protocol tax 分解**。token / control call / wall time / attention 四项分开；「更多 Todo、更多 control call」不是能力。

---

## 9. 这套方法的弱点与未解问题

### 9.1 统计功效：每格一次 trial，却讲了 46 个任务的故事

LHTB 研究是 `n_attempts: 1`，每格一个有效 trial；官方文档自己说「one effective trial per task-arm cell, not a repeated-seed estimate」。这意味着：

- +17.3% 没有置信区间；
- 17 胜 / 13 平 / 16 负不是显著性检验；
- median paired delta = 0 说明增益高度集中，均值不是「典型任务」的故事；
- 「>80% 阈值」是 post-hoc，虽然他们明确标注了。

更可惜的是：**46 个任务的配对 delta 其实可以做 paired bootstrap 或置换检验**（在「任务可视为来自某个任务分布」的假设下），即使每格只有一次 trial。他们没有做。这是从「探索性」走向「C2」最便宜的一步。

### 9.2 预算与传输不是严格匹配

五个臂里，Plain/Native Goal 走 app-server，LoopX 走 `generic_cli` + 每次 fresh `codex exec`；effective aggregates 还包含 designated replacement trials，其中一些 replacement 用了更长的预算。文档反复承认「not an equal-budget efficiency or isolated causal result」。

这不是撒谎，是**在文档里把 confound 摆出来**——但这也意味着 +17.3% 不能读成「LoopX 的控制面单独带来的」。它至少混了：传输方式、session 生命周期、替换策略、预算。

### 9.3 严格解与 Plain 打平

7/46 vs 7/46。均值提升主要来自 partial credit 的改善，不是「多解出了多少任务」。对「长程 agent 能不能把事做完」这个问题，strict solve 可能比 mean reward 更接近用户关心的事。文档没有回避，但标题级的 +17.3% 容易让人误读。

### 9.4 成本没有进入主结论

LoopX $551.73 vs Plain $212.97（+159%），vs Native Goal $344.25（+60%）。均值 +0.073。文档说「higher mean does not establish better efficiency」，但没有给出 score per dollar 的主表。RFC 要求「score per unit cost and time 与原始分并列」——公开简报里这一条执行得不够。

### 9.5 长程过程指标没有进入已发布结果

RFC 6.3 列了停滞、重复、replan 延迟、证据采用、恢复损失、stale-state、premature-terminal、protocol tax 分解；公开的 LHTB 研究只有 reward、strict solve、>80%、cost、token、task-level/group-level delta。**测量模型领先于证据**。这不是致命问题，但它是「长程 eval」这个题目下最应该补的一块。

### 9.6 treatment 的「使用率」没有公开

SWE-Marathon 报了「harness 层 15/15、agent 自调 `loopx` CLI 4/15」——这是很好的 treatment-fidelity 证据。LHTB 研究没有对应数字：我们不知道模型有多少次真的用了 LoopX 的 Todo/replan/evidence，还是只是「LoopX 在旁边挂着」。RFC 要求 receipt 证明 delivered/used；公开聚合里没有这个维度。

### 9.7 反馈时序是一个未闭合的 confound

LHTB 的 modified Harbor 支持中间 verifier 反馈、continue-until-timeout；runner 又把 verifier feedback 设成 binary。RFC 的「Declared feedback and evaluation timing」要求把「solver 能否请求/接收原生反馈」「evaluator 是只在解完后跑还是中途采样」作为两个独立协议选择，并做 feedback ablation。但当前 `benchmark_integrity_policy_v0` **无条件要求** `official_feedback_blinded` 和 `verifier_started_after_agent`，作者自己标注这是「open toolkit/runner contract gap」。

如果 treatment 臂和 baseline 臂在「能否消费中间验证反馈」上不一致，分数差就不能全归给控制面。目前公开材料没有把这一点讲透。

### 9.8 隐藏测试隔离没有强于上游

LHTB README 写得很直白：「This runner does not claim stronger hidden-test isolation than the underlying Harbor/LHTB checkout provides.」integrity audit 能证明「没有访问 forbidden source」，但不能证明 verifier 本身正确、不能证明任务没有被污染、不能证明模型训练时没见过这些公开任务。

### 9.9 只有一个 benchmark 家族，C3 未达成

主证据是 LHTB；SWE-Marathon 只有 15 个任务且撤回过两组；DeepSWE 是 pilot；ALE/StartupBench/LoopsBench 还在 integration plan，WideSearch 已有 Pier adapter 与本地 runner，但不在本文的主证据范围。RFC 自己说仓库最强在 E0–E2，E3 是下一个目标，E4 是未来。所以现在最多是 **C2 的候选**，不是 C3/C4。

### 9.10 自指问题

LoopX 用 benchmark 证明 LoopX 的价值，而 benchmark harness 的一部分（continuation、scheduler、receipts）又是 LoopX 自己实现的。claim ladder、native truth、integrity 三件事在制度上缓解了自指，但没有消除：**谁来判断「LoopX 的 receipt 是可信的」？** 目前是 LoopX 自己的 toolkit 和私有审计。独立第三方复现（尤其是用原生 Codex/Claude 做对照）仍然是缺口。

### 9.11 文档漂移

LHTB README 写 `replan_after_effective_turns=3`，shared runtime 文档写 Harbor LoopX 模式默认 6（旧 benchmark 默认 3）。这类漂移在快速演进的仓库里很常见，但它恰好说明：**跨版本比较必须看 preflight receipt，不能看 README**。他们自己也这么说，但文档量（1,184 行 benchmark README + 1,476 行 toolkit README + 1,387 行 RFC）本身就是维护负担。

### 9.12 复现的边界

公开的是 `data.json` 聚合、pinned task links、runner 代码；原始 trajectory、隐藏 verifier、凭证、私有审计都在本地。这是 benchmark integrity 的正确做法，但也意味着外部只能**重算聚合**，不能独立复核「某一次 trial 到底发生了什么」。要真正复现，需要自己拿 LHTB + Codex + 模型网关跑一遍——成本不低。

---

## 10. 和「我那套方法论」的对照

如果把 LoopX 的做法和你写的 eval 方法论放在一起，会发现两者是同一条主线的两个 specialization。

### 同构

| 你的纪律 | LoopX 的对应物 |
|---|---|
| trace 一等公民 | 每 wake 的 `TURN_ID` + receipt + `codex-events.jsonl` + ATIF |
| 在场证明 | preflight 直接证据 + `skills/list` 发现验证 |
| 对照组纯度 | 四臂 + authority parity + 固定 task/environment/verifier |
| 假通过 | treatment receipt（缺投递 = non-compliance）+ integrity dispositions |
| 假失败 | setup/solver/verifier/infrastructure failure 分类 |
| 判界不判点 | RFC 要求 uncertainty、paired tasks、N>=5；但 LHTB 公开结果还没做到 |
| 裁判也要被校准 | integrity audit 用结构化 facts；episode 评估要求双人编码、judge precision/recall |
| 负结果保留 | SWE-Marathon 撤回、LHTB 反例、median delta = 0 |
| 版本化报告 | 十元组 identity + pinned revision + digest |

### LoopX 有、你没有的

- **claim ladder**：把「能声称什么」变成制度；你的方法论里是隐含的，没有分级。
- **treatment fidelity receipt**：你有「实验有没有发生」，LoopX 进一步问「treatment 有没有被投递、触发、接受」。
- **integrity 作为独立资格轴**：你有「非零退出不许 PASS」，LoopX 有 eligible/quarantined/invalid 和 authority parity。
- **protocol tax 分解**：你有 token 成本观察，LoopX 要求拆成 token / call / wall / attention 四项。
- **episode vector**：你有 trace 断言，LoopX 试图把「研究性工作」本身做成可评估单元。

### 你有、LoopX 不够的

- **故障注入**：mock provider、截断矩阵、skill 完整性、阳性对照、送达证明。LoopX 的 benchmark 里没有等价的 chaos 层；它的 integrity 是「有没有越权」，不是「系统在故障下会不会静默」。
- **judge 校准的硬数字**：TPR/TNR、Wilson 界、pass^k。LoopX 的 episode 评估写了要求，但没有公开的校准数字；LHTB 是确定性 verifier，暂时不需要，但 StartupBench/WideSearch 会需要。
- **供应链完整性**：skill/文件层的截断、缺附件、loader 静默。LoopX 的 benchmark 供应链是 pin revision + digest，但没有对 skill 内容层做完整性门禁。
- **「检出率由伤的位置决定」这类可证伪的测量学结论**：LoopX 有工程纪律，但还没有这种「测量系统自身的定律」。

一句话：**LoopX 强在「因果声明与实验治理」，你强在「测量有效性与故障注入」**。两者拼起来，才是一套完整的 agent eval 基建。

---

## 11. 如果要复刻：最小可行路径

按 LoopX 的工程阶梯，从零做一个「长程 harness eval」可以这样排：

1. **E0**：写清楚十个 identity 字段、四种臂、三种 integrity disposition、public/private 边界；先写负向测试。
2. **E1**：选一个 pinned benchmark（最好是有原生 verifier 的），跑通 oracle smoke + 一个 synthetic conformance slice；证明 setup / solver / verifier / scoring failure 四类可区分；preflight 输出 receipt。
3. **E2**：把 trial 生命周期、并发准入、exact-job 观测、terminal closeout、reconciliation 做出来；invalid run 能隔离，不污染分数。
4. **E3**：冻结 manifest，预注册 primary metric 和 stopping rule；跑 paired tasks，`N>=5`；每臂发 treatment receipt；做 authority parity + integrity audit；报告原生指标 + 不确定性 + 成本 + W/T/L + 负结果。
5. **E4**：在第二个 benchmark 家族复现同一机制方向；再做非 benchmark 的产品 canary；最后才谈改默认。

如果只能做一件事：**先做 preflight + receipt + passive arm**。它们最便宜，也最能防止「实验根本没发生」和「harness tax 把收益吃光」这两种最常见的失败。

---

## 12. 证据索引

**LoopX 仓库**

- 研究 RFC：[long-horizon-harness-benchmark-research-program-v0.md](https://github.com/loopx-project/loopx/blob/main/docs/architecture/rfcs/long-horizon-harness-benchmark-research-program-v0.md)
- benchmark workspace：[benchmark/README.md](https://github.com/loopx-project/loopx/blob/main/benchmark/README.md)
- LHTB runner：[benchmark/LHTB/README.md](https://github.com/loopx-project/loopx/blob/main/benchmark/LHTB/README.md)
- LHTB 五臂研究：[studies/five-arm-gpt56sol-max/README.md](https://github.com/loopx-project/loopx/blob/main/benchmark/LHTB/studies/five-arm-gpt56sol-max/README.md)
- 共享运行时：[benchmark/runtime/RUNTIME.md](https://github.com/loopx-project/loopx/blob/main/benchmark/runtime/RUNTIME.md)
- DeepSWE 实践：[benchmark/deepswe/README.md](https://github.com/loopx-project/loopx/blob/main/benchmark/deepswe/README.md)
- SWE-Marathon：[benchmark/swe-marathon/README.md](https://github.com/loopx-project/loopx/blob/main/benchmark/swe-marathon/README.md)
- benchmark toolkit：[loopx/capabilities/benchmark_toolkit/README.md](https://github.com/loopx-project/loopx/blob/main/loopx/capabilities/benchmark_toolkit/README.md)
- LHTB preflight：[benchmark/LHTB/scripts/preflight.py](https://github.com/loopx-project/loopx/blob/main/benchmark/LHTB/scripts/preflight.py)
- 公开研究简报：<https://loopx-project.github.io/loopx/benchmarks/lhtb/>

**被评测的 benchmark**

- LHTB：[repo](https://github.com/zli12321/LHTB) / [site](https://zli12321.github.io/LHTB/index.html) / [paper arXiv:2607.08964](https://arxiv.org/abs/2607.08964)
- ALE：<https://agents-last-exam.org/> / [paper](https://arxiv.org/abs/2606.05405)
- DeepSWE：<https://deepswe.datacurve.ai/> / [paper](https://arxiv.org/abs/2607.07946)
- StartupBench：<https://startupbench.github.io/>
- LoopsBench：<https://loopsbench.ai/> / [paper](https://arxiv.org/abs/2608.00267)
- WideSearch：<https://widesearch-seed.github.io/> / [paper](https://arxiv.org/abs/2508.07999)

---

*本文所有数字均来自上述公开文档与页面；未使用 LoopX 的私有运行数据。文中「未实现/仅提议」的判断，依据是文档里的 proposed / not qualified / open gap 标注，以及公开结果表中缺失的字段。*
