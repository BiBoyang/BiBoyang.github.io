# 「我的评测工具链」系列导读

写给同样在给 agent 建质量基建的人。这个系列记录我给 agent 生态里的东西建门禁的实战：自己的插件、自己的 skill、手里的 CLI、流式协议、SKILL.md 文件。每篇都是真实事故报告，结构固定：踩过的坑 → 规则 → 规则背后的权衡 → 你能单独拿走的东西。

全系列只有一条主线：**门禁不是判官，是反馈回路**。而回路里的每一环——trace、考题、对照组、观测者、judge——自己也会坏，所以**裁判本身也要被校准**。写到现在的每一篇，最后抓到的「bug」都不在被测对象里，在测量系统自己身上。

单篇可以独立读，交叉引用都带链接。

## 从哪篇读起

- **想要方法论地基**：先读第 1 篇。最重也最全，trace 设计、假通过/假失败、judge 校准、统计口径都在这一篇里立起来。
- **想看翻案故事**：3 → 4 → 5 连读。误报 issue、平台差异误诊、mock 方言假阴性——三次「证据很硬、结论是错的」。
- **关心 CLI 的截断行为**：5 → 6。一篇结论、一篇厨房。
- **写 skill 或管 skill 质量**：2 → 7。红线写法实证 + 完整性故障注入。

## 逐篇索引

| # | 篇目 | 一句话 | 可带走的 |
|---|---|---|---|
| 1 | [从 trace 到 eval](/posts/从-trace-到-eval-trace-设计-Agent-评测方法论-一个评测-harness-的实现-和它抓到的上游并发-bug/) | 方法论地基：trace 设计、假通过/假失败的归因学、judge 校准、harness 关键决策，抓到 dsh 并发 bug | 「trace 第一天就做；假通过和假失败都要防；校准集有保质期」 |
| 2 | [给 skill 建门禁](/posts/给-skill-建门禁-一天里的三种沉默失败-一次红线写法实证-和它抓到的上游-bug-又一只/) | 用 skill-up 测 17 个 skill：三种沉默失败 + 红线写法实证 | 「断言可能跑在一个从未发生的实验上；红线写在正文才有约束力」 |
| 3 | [我给 skill-up 报了一个不存在的 bug](/posts/我给-skill-up-报了一个不存在的-bug/) | 一次完整误报的诞生、长大与推翻，包括具体错在哪条命令上 | 「证据质量不保证结论正确，它保证纠错的速度」 |
| 4 | [CI 红、本地绿](/posts/CI-红-本地绿-一次-平台差异-误诊-和-merge-干净不等于语义兼容/) | 「平台差异」误诊一小时，真相是 CI 和本地测的不是同一份代码 | 「merge 干净不等于语义兼容；断言职责，不断言字段」 |
| 5 | [回答被截断，你的 CLI 知道吗](/posts/回答被截断-你的-CLI-知道吗-四个工具-六种故障-108-格矩阵-和一个差点发布的错误结论/) | 四工具 × 六故障 × 三次 = 108 格截断检出矩阵，60% 静默 | 「检出不难，告知才是缺口；阴性结论要配阳性证据」 |
| 6 | [给流式协议造故障](/posts/给流式协议造故障-三协议-mock-once-注入-字节级送达证明-和-strings-阴性不等于代码不存在/) | 第 5 篇的厨房：三协议 mock、once 注入、字节级送达证明 | 「故障可以造，协议不变量不能破；mock 的权威性和客户端的严格性成反比」 |
| 7 | [考官带伤阅卷](/posts/考官带伤阅卷-对-Agent-Skill-做故障注入的完整性实验/) | 对 SKILL.md 做故障注入，测宿主 agent 的检出率 | 「检出取决于伤挡不挡路，不取决于伤多重；完整性是供应链问题，不是上下文问题」 |

## 系列沉淀的纪律

**对实验**

- 对照组的「无」必须是强制出来的，宿主的默认值全是污染；对照组选错比没有对照组更危险
- 全量跑之前，先验证被测对象真的在场——用直接证据，不用退出码
- 版本、日期、样本量、口径进每份报告；单发是轶事，x/N 才算数

**对判定**

- 假通过和假失败两个方向都要防，判之前先问一句「这次失败真的是 agent 的失败吗」
- 判置信区间的界，不判点估计
- judge 上岗先校准，TPR/TNR 分开看；校准集有保质期，换模型要重校
- 写不出可判定断言就标「不可判定」——橡皮图章比没有断言更坏

**对自己**

- 最刺眼的那个结论，发布前当嫌疑人审一遍：它往往是你自己的
- 错误结论原样保留，推翻过程比结论值钱
- 测到什么就报什么

## 战果与工具

这个系列的规矩是结论必须闭环——抓到的上游问题（部分）：

- deepseek-harness 并发启动崩溃（TOCTOU）——[Discussion #4312](https://github.com/deepseek-ai/deepseek-harness/discussions/4312)
- skill-up 零文件安装不报错——[issue #253](https://github.com/alibaba/skill-up/issues/253) / [PR #257](https://github.com/alibaba/skill-up/pull/257)
- skill-up 超时丢产物——[issue #263](https://github.com/alibaba/skill-up/issues/263) / [PR #265](https://github.com/alibaba/skill-up/pull/265)
- skill-up 对 skill 内容层零校验——[issue #280](https://github.com/alibaba/skill-up/issues/280) / [PR #281](https://github.com/alibaba/skill-up/pull/281)
- kimi-code 主 agent 截断静默——[issue #4012](https://github.com/MoonshotAI/kimi-code/issues/4012)
- Waza skill 边界写法与 URL 承诺——[PR #87](https://github.com/tw93/Waza/pull/87) / [PR #88](https://github.com/tw93/Waza/pull/88)

沉淀出的开源工具：

- [dsh-eval-harness](https://github.com/BiBoyang/dsh-eval-harness)——给 dsh 插件跑回归测试的门禁
- [truncation-detection-benchmark](https://github.com/BiBoyang/truncation-detection-benchmark)——截断检出矩阵复现包（mock + 逐格证据）
- [skill-quake](https://github.com/BiBoyang/skill-quake)——skill 完整性故障注入（含 skill-guard 确定性门禁）

## 相邻阅读

- [自顶向下拆 Agent · 开篇：没报错，就代表输出没问题吗？](/posts/Agent-时代的开发者界面-开篇-没报错-就代表输出没问题吗/)——另一个系列的开篇，同一次截断调查的知识建构版：完整性判定为什么在内容层做不出来、必须下沉到协议层。

系列持续更新。
