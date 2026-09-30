---
layout: post
title:  "从 5 个 issue 到 3 个 PR：我给 skill-up 交的 8 份作业"
date:   2026-09-30 10:00:00 +0800
categories: [AI]
tags: [AI, Agent]
---

> **系列 · 我的评测工具链**（持续更新）· 第 8 篇
>
> 全部篇目、阅读路径与系列沉淀的纪律见 [系列导读](/eval-series/)；
> 上一篇：[考官带伤阅卷：对 Agent Skill 做故障注入的完整性实验](/posts/考官带伤阅卷-对-Agent-Skill-做故障注入的完整性实验/)

Skill 没有编译器。它是一份 markdown、几个附件、一段 frontmatter，被宿主 agent 按 description 自主加载。这意味着它的「完整性」比代码更脆弱：

- 文件同步截断一个字，语义可能就漂了；
- 符号链接安装失败，可以 silent 地装上 0 个文件；
- 进程被 timeout 杀死，最后一帧证据可能永远写不出来。

我给阿里的 [skill-up](https://github.com/alibaba/skill-up) 交了 8 个 items：5 个 issue，3 个 PR。回头看，它们几乎全在说同一件事 —— **Agent Skill 的完整性防线该长在哪**。这条线可以分成三层：安装层、证据层、校验层。

# 一、安装层：skill 真的在场吗？

这条线的起点是 issue [#253](https://github.com/alibaba/skill-up/issues/253)。

当时我给自己的 9 个 skill 跑 skill-up 触发评测，报告红黄绿俱全。直到我翻被测 agent 的会话落盘，发现一个不对劲的事实：**所有 with_skill 会话里，被测 skill 的名字出现次数是零** —— 不是没被触发，是连 skill 列表里都没有它。

排查到底，是 skill-up 的 `ListSkillFiles` 用 `filepath.Walk` 遍历 skill 源目录，而我的 skill 全是符号链接。Go 的 `filepath.Walk` 不跟随符号链接根，遍历直接结束，选中文件数为零。安装逻辑把这个零当成正常，debug 日志还照常打印 `skill installed: xxx`。

也就是说，with_skill 和 without_skill 跑的是同一个裸模型。所有 PASS/FAIL 都是 noise 装扮成的 signal。

这件事的教训我在《[给 skill 建门禁](/posts/给-skill-建门禁-一天里的三种沉默失败-一次红线写法实证-和它抓到的上游-bug-又一只/)》里写过：**全量跑之前，先验证被测对象真的在场**。不是看退出码，是看直接证据。

PR [#257](https://github.com/alibaba/skill-up/pull/257) 修掉了这个问题：`EvalSymlinks` 解析 + 零文件安装直接报错，并附了三个回归测试。但 #257 只解决了「安装失败要出声」，没解决「装上之后内容完不完整」。

# 二、证据层：agent 死了之后，数据还在吗？

安装层修完后，我把注意力转向运行时的「临终证据」。

issue [#263](https://github.com/alibaba/skill-up/issues/263) 来自一次真实事故：一条用例超时，case timeout 把 custom engine 进程组 SIGKILL 掉，而引擎适配器还没来得及把 `session-result.json` 刷盘。那一整 case 的评测数据全丢了。

这个场景里，skill-up 的行为按自己的契约看是正确的：超时了，杀进程，报告 FAIL。但问题在于 **FAIL 之后没有留下任何可分析的证据**。下游无法知道 agent 死前到了哪一步、skill 有没有被触发、工具调用到哪一行。

我在 issue 里最初建议的修法是「超时时先 SIGTERM 给宽限再 SIGKILL」，但读源码后发现 skill-up 已经实现了进程组 + SIGTERM + 1 秒宽限的逐级升级。真正的缺口是：宽限期救不了「没有 SIGTERM handler 的引擎适配器」。Python 适配器收到 SIGTERM 后直接死掉，清理逻辑根本跑不到。

所以 PR [#265](https://github.com/alibaba/skill-up/pull/265) 没有改超时策略，而是改了一个更便宜、更可靠的地方：**当超时导致产物缺失时，由框架在 output 路径合成一份最小 session-result**（exit_code 124 + 合成标记）。下游至少有据可查。

同一个现场还诞生了 issue [#264](https://github.com/alibaba/skill-up/issues/264)：我以为 `--include-case-name` 单 case 重跑「报告 PASS 但不写产物」，后来用 `-v` 看到 `iteration-2` 才意识到 —— 不是没写，是写到了新的 iteration 目录，而我 stat 的是旧目录。

这个误报我在《[我给 skill-up 报了一个不存在的 bug](/posts/我给-skill-up-报了一个不存在的-bug/)》里完整复盘过。它带来的纪律是：**评测工具必须让「分母偏移」可见**。现在我们的报告会多一行 `EXCLUDED: N case(s) without session-result`，单 case 重跑一律用绝对路径 `--output-dir`。

# 三、校验层：装上之前，内容完整吗？

安装层和证据层都是「事后」。#257 保证坏安装会报错，#265 保证坏运行会留痕，但它们都没回答一个问题：**在 eval 开始之前，skill 的内容本身完不完整？**

issue [#280](https://github.com/alibaba/skill-up/issues/280) 来自《[考官带伤阅卷](/posts/考官带伤阅卷-对-Agent-Skill-做故障注入的完整性实验/)》里的故障注入实验。我们截断 SKILL.md、删除附件、清空 frontmatter，然后看宿主 agent 能不能发现。

结论是：**检出与否不取决于伤有多重，取决于伤是否挡在 agent 要走的路上**。挡路的伤（主文件截断、必读附件缺失）能被稳定发现；不挡路的伤（frontmatter 清空、可选附件截断）经常被忽略。而 skill-up 工具链本身对内容完整性没有任何防线 —— CLI 只检查 SKILL.md 是 regular file，`validate` 只检查 eval.yaml，skill-upper 只读目标 SKILL.md 生成用例。

也就是说，一个带伤的 skill 可以被正常安装、正常评测、正常产出报告，而报告本身已经被污染了。

#280 提了三个层次的解决方案：

1. 扩展 `skill-up validate`（或新增 `validate --skill`），静态检查 skill 源文件：frontmatter 是否闭合、`name`/`description` 是否非空、正文引用的 `references/` / `assets/` / `scripts/` 路径是否真实存在。
2. 在 skill-upper 的 Step 1 加一行指令，让它在生成用例前先跑这个检查。
3. 更远的未来：manifest/hash 模式，用于检测 stealth cuts（静默截断/篡改）。

PR [#281](https://github.com/alibaba/skill-up/pull/281) 实现了第 1 项。它新增 `skill-up validate --skill <dir>`，作为源文件级别的 content-integrity linter：

- 检查 YAML frontmatter 存在且闭合；
- 检查 `name` 和 `description` 非空；
- 用 goldmark 解析正文，检查每个真实引用的本地路径是否存在；
- 反过来报告「被引用的附件目录里有哪些文件正文从没提过」——这能抓到一个确定性签名：SKILL.md 尾部被截断后，它原本引用的附件会变成 orphan。

#281 自己也很清醒地界定了范围：它只是**源文件级**检查，看不到 `skills.include` / `skills.exclude` 过滤后的实际安装产物，也不会自动在 `run` 之前执行。那个缺口由 issue [#287](https://github.com/alibaba/skill-up/issues/287) 接着跟踪 —— **Preflight skill-integrity check: validate what a run actually installs**。

#287 目前还是 open questions：检查点该放在 installer post-install 还是 `run.go` case 执行前？范围是每 skill 一次还是每 case 一次？失败策略是 warn 还是 abort？内容级完整性（截断、篡改）要不要依赖 manifest/hash 基线？

这些问题没有定论，但它们把完整性防线推到了最后一层：**不是源文件写没写对，而是运行时要用的那套文件齐不齐、坏没坏**。

# 四、三个 PR 的三种诞生方式

把这 8 个 items 串起来看，3 个 PR 其实是三种不同的修复形态：

| PR | 类型 | 它解决什么问题 |
|---|---|---|
| #257 | **修 bug** | 一个确定性的安装错误：symlink 导致零文件安装 |
| #265 | **补证据** | 流程没错，但失败现场没有痕迹，下游无法分析 |
| #281 | **加门禁** | 从被动修复走到主动预防，在 validate 阶段拦截内容残缺 |

这个顺序不是随机的。#257 是「坏了要出声」，#265 是「坏了要留痕」，#281 是「别等坏了才出声」。防线一步步前移：安装 → 运行 → 验证。

# 五、沉淀：三条 eval 纪律

这 8 个 items 给我自己的工具链补了三条纪律：

1. **验证被测对象真的在场**。退出码、日志、报告都会说谎，直接证据（工作区落盘文件、会话记录里的 skill 加载行）不会。
2. **失败时要留下证据**。timeout、crash、OOM 不可怕，可怕的是事后没有任何可分析现场。
3. **校验要前移，不能依赖 agent 自觉**。agent 会不会发现 skill 残缺是概率问题；CI / loader / validate 阶段的确定性检查才是防线。

# 六、把防线对准自己

三条纪律总结完，自然的问题是：这套标准，你自己的工具链达标吗？本文发布前夜，我按同样的三层防线体检了 skill-quake 自己。结果是三层全中枪。

**安装层中枪。** matrix.sh 把证人的路径写死成 `$here/../../../bin/skill-guard`——在仓库布局里成立，一旦 skill 被装进 `~/.agents/skills/`，它解析到一个不存在的目录。这和 #253 同构：引用的东西不在场，流程照常走。更糟的是那行调用末尾的 `|| true`：guard 缺席时，整个矩阵带着空 guard.json 跑完，报告照出。这不是「失败没有痕迹」，是**证人根本没出庭，而法庭没有点名**。

修法是把沉默改成 loud-fail：guard 解析改成回退链（repo bin → PATH → 安装约定），找不到立刻退出；运行期区分 verdict 和崩溃——guard 对带伤副本报 FAIL 是数据不是错误，只有连 JSON verdict 都吐不出来才中止；再加一条 staging 断言：verdict 里出现 `SKILL.md missing` 一律停——mutate 永远复制 SKILL.md，missing 只可能是 staging 事故，永远不该被记成实验数据。

**证据层中枪。** loud-fail 一上，当场逼出两条在 `|| true` 下完全不可见的 bug。一条是平台差异：macOS 的 BSD `seq 1 0` 会输出 `1 0`（GNU 输出空），N=0 的 dry-run 会真的 dispatch 两发、烧掉配额。另一条更隐蔽：无冒号的 faultspec（如 `blank-frontmatter`）经过 `${spec#*:}` 原样保留，被当成幻影参数传给 mutate.sh，参数全体错位一格，副本写到了 `./blank-frontmatter`，guard 一直在检查一个不存在的目录。两条都沉默运行了相当久——吞错的 `|| true` 一拆，当场现形。#265 的纪律再次成立，只是这次被抓的是我自己。

**校验层中枪，也是最微妙的一枪。** 修完之后，`skill-guard --strict` 对 skill-quake 自己判 PASS：0 error，0 warning。但 SKILL.md 里躺着一个编辑事故——同一句话写了两遍。gate 抓不到它，因为伤不在 gate 要走的路上：文件层面一切完好，重复发生在语义层。《[考官带伤阅卷](/posts/考官带伤阅卷-对-Agent-Skill-做故障注入的完整性实验/)》的论点，在考官本人身上又复现了一次：检出与否不取决于伤有多重，取决于伤挡不挡路。

所以三条纪律各补一条注脚：「验证被测对象真的在场」——包括你的证人；「失败时要留下证据」——包括证人缺席这件事本身；「校验要前移」——但前移的每一道闸，自己也得被校验。

# 七、结尾

 skill 是提示词层的代码。代码有编译器、类型系统、 linter；skill 没有，所以它的完整性更依赖工具链主动设防。

我在 skill-up 上交的 8 份作业，本质上都是在补同一类工具：**让 skill 的损坏从「沉默」变成「有声」**。从 #253 的安装失败，到 #263 的运行时丢数据，再到 #280/#281/#287 的内容校验 —— 每一层都没有完美闭环，但每一层都比上一层更靠前。

下一层是什么？第六节给了第一个答案：你自己的工具链。再往下呢？等它漂了我就知道。

---

*本文涉及仓库：[skill-up](https://github.com/alibaba/skill-up)；相关 issue/PR：#253、#257、#263、#264、#265、#280、#281、#287。*
