---
layout: post
title:  "我给 skill-up 报了一个不存在的 bug"
date:   2026-09-20 20:00:00 +0800
categories: [AI]
tags: [AI, Agent]
---

> **系列 · 我的评测工具链**（持续更新）
>
> 1. [从 trace 到 eval：trace 设计、agent eval 方法论、一个 eval harness 的实现，和它抓到的上游并发 bug](/posts/从-trace-到-eval-trace-设计-Agent-评测方法论-一个评测-harness-的实现-和它抓到的上游并发-bug/)
> 2. [给 skill 建门禁：一天里的三种沉默失败、一次红线写法实证，和它抓到的上游 bug（又一只）](/posts/给-skill-建门禁-一天里的三种沉默失败-一次红线写法实证-和它抓到的上游-bug-又一只/)
> 3. **我给 skill-up 报了一个不存在的 bug**（本文）
> 4. [CI 红、本地绿：一次「平台差异」误诊，和 merge 干净不等于语义兼容](/posts/CI-红-本地绿-一次-平台差异-误诊-和-merge-干净不等于语义兼容/)

> 一个超时、两次观测错误、一条 verbose 日志，和一场从"确信"到"自我推翻"的完整经历。全程写实，包括我具体错在哪条命令上。

# 1. 开场

前两天我给阿里的 [skill-up](https://github.com/alibaba/skill-up)（Agent Skill 评测工具）提了两个 issue。第一个是真问题，我给它提了 [PR #265](https://github.com/alibaba/skill-up/pull/265)；第二个，第二天我自己回到 issue 下面发了一条评论：**"这是一个误报，skill-up 的行为完全正确，请关闭。"**

这篇文字记录的是第二个 issue 的完整一生：它怎么在真实的故障现场里诞生，怎么带着"严谨的证据"长大，怎么被一条日志推翻，以及推翻之后我学到了什么。写给所有相信"我亲眼看到的观测结果"的工程师——包括两天前的我。

# 2. 现场：一个真的故障

背景是我给自己的 9 个 Agent Skill 跑触发评测（测"该不该触发"而不是"触发后跑得对不对"），用 skill-up 驱动自写的 custom engine 适配器。某天全量跑到 90 条用例，其中一条超时了：

```console
[ERROR] case trigger-pos-digest-repo: agent execution failed: custom engine run failed:
context deadline exceeded (case timeout 180s via cases.defaults.timeout_seconds)
```

超时本身不奇怪，奇怪的是产物。引擎适配器的契约是把运行结果写到 `session-result.json`，被杀后目录里长这样：

```console
$ ls <workspace>/iteration-1/trigger-pos-digest-repo/with_skill/outputs/agent/run/
messages.json      # 框架写的输入文件
                    # session-result.json —— 没有了
```

agent 运行前几个 turn 里已经发生的事件（包括 skill 激活记录）全部随进程蒸发。这是真问题，后来成了 issue [#263](https://github.com/alibaba/skill-up/issues/263) 和 PR #265。这个场景，是后面所有误会的起源。

# 3. 误报的诞生：三次"失败"的重跑

为了补回这条丢失的数据，我用 `--include-case-name` 单独重跑这个 case。跑了三次，每次控制台都报 `1 passed`，但去产物目录看，`session-result.json` 依然不存在。另外两个 skill 的单 case 重跑也是同样症状。

"PASS 但不落盘"——这听起来就像一个增量重跑的 bug 了。但发 issue 前，我决定先做个严谨的复现：记录文件 mtime，重跑，再记录。

```console
$ stat -f "%m %N" .../iteration-1/trigger-pos-terse/.../session-result.json
1789808917 ...

$ skill-up run evals/eval-triggers.yaml --include-case-name "trigger-pos-terse" \
    --output-dir /Users/boyang/Desktop/源码学习/huohou/huohou-code-review-triggers-workspace
📋 Results: 1 passed, 0 failed, 0 errors

$ stat -f "%m %N" .../iteration-1/trigger-pos-terse/.../session-result.json
1789808917 ...     # ← mtime 纹丝不动
```

数字完全一致。"重跑报 PASS 但产物零更新"，铁证如山。我把它连同命令和输出一起写进 issue [#264](https://github.com/alibaba/skill-up/issues/264)，标题起得很有把握：*"Rerunning a single case with --include-case-name into a non-empty output workspace reports PASS but writes no fresh artifacts"*。

发出去的时候我没有任何不踏实的感觉。这才是最值得写下来的部分。

# 4. 推翻：一条 verbose 日志

两天后准备给这个问题提 PR，第一步是加 `-v` 复现一遍，看内部日志。输出里有这么一行：

```console
level=DEBUG msg="Runner: iteration workspace: /tmp/spike264/iteration-2"
```

**iteration-2**。skill-up 把重跑 append 成了新的 iteration——这正是它文档里写的 auto-append 语义，行为完全正确。产物呢？

```console
$ ls /tmp/spike264/iteration-2/trigger-pos-terse/with_skill/outputs/agent/run/
messages.json  session-result.json    # ← 都在，全新
```

所以"重跑不落盘"根本不成立。那我的三次"失败重跑"和 mtime 铁证是怎么回事？顺着这条线拉回去，两个观测错误原形毕露。

# 5. 解剖：我具体错在哪

**错误一：相对路径的 `--output-dir`。** 三次补跑的命令是在 skill 子目录里敲的：

```bash
cd huohou-digest && skill-up run ... --output-dir huohou-digest-triggers-workspace
#                                                  ↑ 相对路径，相对的是 cwd
```

产物老老实实写进了 `huohou-digest/huohou-digest-triggers-workspace/`——一个嵌套目录。而我检查的是仓库根下的同名 workspace。找到这个目录时，三次"消失"的重跑产物整整齐齐躺在里面，每份 `session-result.json` 都在。

**错误二：对照组选错了 iteration。** 那个"严谨"的 mtime 复现，stat 的是 `iteration-1` 里的文件；而重跑写的是 `iteration-2`。**mtime 是真的，数字是一致的，结论是错的**——我验证了一个没人怀疑的命题（旧文件不会被重跑改写），却以为自己验证了那个有问题的命题（新文件没有被写出）。

两层错误叠加出的现象高度自洽：控制台说 PASS（它确实跑完了）、我盯着的目录没有新文件（新文件在别处）、mtime 不变（我盯的是旧文件）。每一格观测都"对"，拼起来的图景却是虚构的。事后看还有第三个帮凶：第 2 节那个真实的超时丢产物问题给了我"产物会丢"的先入之见，让我对"又一次产物丢失"毫无防备。

# 6. 纠错，以及真 PR 怎么从误报调查里长出来

发现真相的当天，我在 #264 下面发了更正评论：说明 skill-up 行为正确、给出 verbose 日志证据、逐条拆解自己的两个观测错误、指出唯一真实的问题是 #263、道歉并请维护者关闭。写这段评论花的时间比写原 issue 还长——这是应该的。公开误报的成本是一次尴尬，收益是维护者的时间和一个可信的轨迹记录：下次你再报问题时，你的历史记录在替你说话。

更有意思的是另一条线。为了给"真问题" #263 提 PR，我读了 skill-up 的源码，发现 issue 里我建议的修法（"超时时先 SIGTERM 给宽限再 SIGKILL"）**上游早就实现了**——`none_exec_unix.go` 里进程组、SIGTERM、1 秒宽限、逐级升级一应俱全，注释写得清清楚楚。真正的缺口在别处：skill-up 优雅终止的是引擎适配器进程，而一个没注册 SIGTERM handler 的 python 适配器收到 SIGTERM 后直接死掉，宽限期救不了"没有清理逻辑的进程"。于是 PR #265 做的是 issue 里我自己标的"备选方案"：超时且产物缺失时，由框架在 output 路径合成一份最小 session-result（exit_code 124 + 合成标记），让下游至少有据可查。

这带来一个上游协作的实操经验：**issue 里的修复建议是假设，不是承诺**。调查阶段发现"提纲是错的"很正常，正确做法是在 PR 描述里显式修正它——#265 的描述里专门有一节 "Correction vs. the issue sketch"，说明哪个建议已被上游实现、真实缺口是什么。维护者看到的不是一个推翻自己 issue 的别扭 PR，而是一份诚实的调查记录。

顺带一提 issue 本身的质量：#263/#264 都带了最小复现、环境信息、期望 vs 实际、内联证据（不依赖仓库访问的命令输出）。回头看，这些纪律在 #264（误报）上没能阻止我犯错——但它让我的错误**可被快速验证和推翻**，verbose 日志一跑就水落石出。证据质量不保证结论正确，它保证的是纠错的速度。

# 7. 沉淀：误报的反向产物

这场误报直接催生了几个机制，都进了我们自己的工具链：

- **排除计数**。评测报告原来对"分母里少了谁"是静默的；现在每份报告都有一行 `EXCLUDED: N case(s) without session-result`。我犯的错本质是"观测对象静默偏移"——分母、iteration、目录，任何一处悄悄变了都不该无声无息。
- **评测器的自测**。判活脚本自身有一套 32 条断言的回归测试（含一个故意的坏 skill 样本），上线以来抓到过判活器崩溃、配置漂移两个真 bug；这次又把误报涉及的产物聚合逻辑补了进去，固化"同 case 多 iteration 取最新"的语义。
- **重跑纪律**。单 case 重跑一律绝对路径 `--output-dir`，判产物看最新 iteration——两条都写进了仓库的纪律文档。

给 Agent Skill 做评测这段时间，我越来越同意《[LLM-as-a-Judge：如何判断你的 LLM 应用是否「健康」](https://mp.weixin.qq.com/s/x2zo6TcFu-y-niKUfNFBOQ)》里的观点：**裁判本身也需要被校准**。这篇文字记录的是同一命题的另一个切面——不只是 judge 模型会偏，评测工具、观测脚本，以及拿着它们的人，整套链路都会以自洽的方式出错。工具链的价值不在于永不出错，而在于错了之后，一条 verbose 日志、一行排除计数、一个可复现的 issue 就能把它抓住。

那天要不是想给 PR 加日志，这个"bug"大概还活着。verbose 一响，黄金万两。

---

*本文涉及的仓库与工具：[huohou](https://github.com/BiBoyang/huohou)（9 个 Agent Skill + 触发评测工具链）、[skill-up](https://github.com/alibaba/skill-up)。相关上游记录：issue [#263](https://github.com/alibaba/skill-up/issues/263)、误报更正 [#264](https://github.com/alibaba/skill-up/issues/264#issuecomment-5743592368)、PR [#265](https://github.com/alibaba/skill-up/pull/265)。*
