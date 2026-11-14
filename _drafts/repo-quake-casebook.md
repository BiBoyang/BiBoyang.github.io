
# 给 AI 工具挑刺的记录



素材来自两本小册——《自顶向下拆 Agent》的评测卷和《我的评测工具链》——外加 [repo-quake](https://github.com/BiBoyang/repo-quake) 的缺陷台账、运行记录，以及上游的 issue/PR 原文。上游状态是 2026-11-14 在 GitHub 上实查的。

## 一、结果

一共涉及 8 个第三方项目。合并的修复 PR 有 7 个：skill-up 的 #257、#265、#295、#320、#338，Waza 的 #88，e2e 的 #1372。Waza 还有一个 #87，维护者先在自己的代码上复现了问题，改了形态后并进 3.38.0。修复关闭的 issue 有 6 个：skill-up #253、#263、#294、#319、#337，e2e #1371；skill-up #321 则是社区贡献者在 #332 里实现的。还有一次误报（skill-up #264），我自己公开撤回了。

bug 之外做了三组横评：4 个 CLI 的 108 格截断检出矩阵，3 个宿主的 skill 完整性注入，以及仓库级故障注入（88 次宿主运行，外加 phase 2 的 64 发）。repo-quake 的台账一共记了 31 条，其中 8 条是我自己工具的 bug。

| # | 项目 | 问题 | 怎么抓到的 | 上游结局 | 出处 |
|---|---|---|---|---|---|
| 1 | [MoonshotAI/kimi-code](https://github.com/MoonshotAI/kimi-code)（★8.2k） | 主 agent 的回答被 max_tokens 截断后，回合照样按成功结束，用户不知道答案是半截的 | 读源码，三个项目对照 | [issue #4012](https://github.com/MoonshotAI/kimi-code/issues/4012)，开放中 | 评测卷序章；工具链第 5 篇 |
| 2 | [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)（★281k） | 多个进程同时启动时，修复共享符号链接的逻辑有 TOCTOU 竞态，ENOENT 崩溃 | 自研评测 harness 真实并发重跑 | [Discussion #4312](https://github.com/deepseek-ai/deepseek-harness/discussions/4312)；社区据此给出参考修复，实测从 48 次崩 23 次降到 96 次零崩溃 | 工具链第 1 篇 |
| 3 | [alibaba/skill-up](https://github.com/alibaba/skill-up)（★1.5k） | skill 源目录是符号链接时选中 0 个文件，照样报安装成功，评测实际跑在裸模型上 | 翻会话落盘，确认被测对象在不在场 | [#253](https://github.com/alibaba/skill-up/issues/253) → [PR #257](https://github.com/alibaba/skill-up/pull/257) **已合并** | 工具链第 2 篇；评测卷第 2 篇 |
| 4 | alibaba/skill-up | 用例超时强杀引擎，结果文件来不及落盘，整个用例的评测数据丢失 | 触发评测全量跑 | [#263](https://github.com/alibaba/skill-up/issues/263) → [PR #265](https://github.com/alibaba/skill-up/pull/265) **已合并** | 工具链第 3 篇；评测卷第 14 篇 |
| 5 | alibaba/skill-up | 对 SKILL.md 和附件的内容完整性零校验 | skill 完整性故障注入 | [#280](https://github.com/alibaba/skill-up/issues/280) → [PR #281](https://github.com/alibaba/skill-up/pull/281)，审阅中 | 工具链第 7 篇；评测卷第 4 篇 |
| 6 | [tw93/Waza](https://github.com/tw93/Waza)（★7.6k） | ① 边界只写在 frontmatter 里，运行时不起作用；② read 的本地抓取层在代理环境下违背"URL 不出机" | 拿 8 个 skill 做天然对照 | [PR #88](https://github.com/tw93/Waza/pull/88) **已合并**；[PR #87](https://github.com/tw93/Waza/pull/87) 维护者复现后并入 3.38.0 | 工具链第 2 篇 |
| 7a | dsh 插件 routing-suite（测评当日约 7000★） | 靠 prepare 钩子构建，包管理器默认拦截后，安装 exit 0，插件却是死的 | 隔离环境真装，再对照 README 的承诺 | [issue #152](https://github.com/yjh051108/dsh-routing-suite/issues/152)，开放中 | 评测卷第 6 篇 |
| 7b | deepseek-ai/deepseek-harness | 新建 profile 第一次 headless 运行会无限挂起 | 补裸对照，推翻了我自己的第一版归因 | [Discussion #7978](https://github.com/deepseek-ai/deepseek-harness/discussions/7978)，社区成员参与定位 | 评测卷第 6 篇 |
| 8 | [e2e-inc/e2e](https://github.com/e2e-inc/e2e)（★13.8k） | 缓存写入抛错后，步骤结果里丢了 `not-written` 状态 | repo-quake 三格对照 | [#1371](https://github.com/e2e-inc/e2e/issues/1371) → [PR #1372](https://github.com/e2e-inc/e2e/pull/1372) **当天合并** | 台账 RQ-F-001 |
| 9 | [anthropics/skills](https://github.com/anthropics/skills)（★194k） | skill-creator 的 quick_validate 放行空字符串 name/description，也不查引用文件在不在 | 注入实验里，考官自带的校验器没反应 | [PR #1949](https://github.com/anthropics/skills/pull/1949)，开放中 | 台账 RQ-I-002/003 |
| 10 | [microsoft/eval-guide](https://github.com/microsoft/eval-guide)（★142） | SKILL.md 里的资源路径在目录迁移后失效；两份 frontmatter 不是合法 YAML | 机械证人 + 严格 YAML 解析 | [PR #16](https://github.com/microsoft/eval-guide/pull/16)，开放中 | 台账 RQ-F-012/013 |
| 11 | alibaba/skill-up | 拼错的 matcher 名被宽松 YAML 解析丢掉，禁止规则变成空操作，用例 0 条断言也判 PASS | 给禁止规则喂一条明知违规的输出 | [#294](https://github.com/alibaba/skill-up/issues/294) → [PR #295](https://github.com/alibaba/skill-up/pull/295) **已合并** | issue/PR 原文 |
| 12 | alibaba/skill-up | 照官方文档用相对 `--output-dir`，agent_judge 硬失败，还误报路径逃逸 | 对 judge 通道做故障注入 | [#319](https://github.com/alibaba/skill-up/issues/319) → [PR #320](https://github.com/alibaba/skill-up/pull/320) **已合并** | issue/PR 原文 |
| 13 | alibaba/skill-up | 只有空白的 prompt / turn 能通过 validate，空任务一路走到引擎执行 | repo-quake 的确定性配置边界矩阵 | [#337](https://github.com/alibaba/skill-up/issues/337) → [PR #338](https://github.com/alibaba/skill-up/pull/338) **已合并** | repo-quake 运行记录 |
| — | alibaba/skill-up | （误报）以为重跑报 PASS 却不落盘，其实是我自己看错了 | 准备 PR 时开 verbose 日志，自己推翻 | [#264](https://github.com/alibaba/skill-up/issues/264) 公开更正，请维护者关闭 | 工具链第 3 篇；评测卷第 14 篇 |

## 二、repo-quake 是什么

[repo-quake](https://github.com/BiBoyang/repo-quake)（2026-10-14 建仓，Apache-2.0）是这套方法的总仓库，方法和代码的改动都先落在这里，更早的 skill-quake 也被它收编了。它只回答一个问题：**挑一个开源项目，找到它不报错地坏掉的地方，拿出维护者没法反驳的证据。**

仓库分两层：

| 层 | 位置 | 回答的问题 | 性质 |
|---|---|---|---|
| 地基 | `bin/skill-guard` | 产物集是否完整 | 确定性 CLI，exit 0/1，可进 CI |
| 实验 | `skills/repo-quake`、`skills/skill-quake` | 宿主能否察觉损伤 | 编排型 skill，需要判断 |

地基只管接受或拒绝，判分留给裁判。

核心模型是一个乘法：**检出 = 读到 × 愿报 × 挡路**。读不读得到由外壳（agent CLI）决定，愿不愿意报由模型决定，伤口挡不挡路由任务决定。任何一项为零，检出就是零；反过来，没检出的时候可以沿这三项逐个找原因。

证据上的规矩是每条证据都要有自己的证人：
- 故障要有送达证明，mock 对每个请求记下实际写出的字节数、事件序列、终止信号送没送到；
- 检出要有阳性对照，先证明检测通道是活的；
- 阴性结论要有字节级证据；
- 最刺眼的结论先当嫌疑人复核；
- 每格报 x/N，单发不算；全程带阴性对照（C0）；
- 宿主零上下文、prompt 中性、只改副本；实验产物和伤型信息对被测 agent 不可见，免得它从路径名猜出实验。

台账在 `ledger/ledger.json`。每条目标缺陷、仪器缺陷和实验有效性事件都带 x/N、证据路径和上游链接，有 SCHEMA，也有 `ledger-check` 校验。截至 2026-10-31 共 31 条：13 条目标缺陷，8 条仪器缺陷，10 条实验无效事件。台账里自己写了一句：归因是解释，不是测量。

工具是一路长出来的：

| 时间 | 工具 | 作用 |
|---|---|---|
| 2026-08-13 | [dsh-eval-harness](https://github.com/BiBoyang/dsh-eval-harness)（★14） | 给 dsh 插件跑回归评测的门禁：YAML 用例驱动真实 agent 会话，对比基线给出 PASS/WARN/FAIL |
| 2026-09-25 | [skill-quake](https://github.com/BiBoyang/skill-quake) | skill 完整性故障注入，含 skill-guard 确定性门禁 |
| 2026-09-26 | [truncation-detection-benchmark](https://github.com/BiBoyang/truncation-detection-benchmark) | 截断检出矩阵的复现包：三协议 mock + 108 格逐格证据 |
| 2026-10-14 | [repo-quake](https://github.com/BiBoyang/repo-quake) | 把故障注入从 skill 推广到整个开源项目，收编前面的工具，成为总仓库 |

《我的评测工具链》那 7 篇都写在 repo-quake 建仓之前，用的是表里的前身工具。repo-quake 的 README 把这一路的上游成果都算作方法的产出。

## 三、案例

### 1. kimi-code：主 agent 的截断被当成成功（#4012）

这一条没用任何评测工具，是读源码读出来的。

起因是我的代理网络很烂。有一次让模型写一份长分析，格式工整，段落齐全，但话说到一半就没了。排除了上下文长度和代理之后才发现，就算网络完全正常，token 上限、网关弄丢最后一个 chunk、SDK 默认把"连接被悄悄关了"当成正常结束，都会触发同一类故障：问题发生了，工具从头到尾不说。

我先给"一条流式回答完不完整"定了判定顺序：transport_error → no_end_marker → buffer_residual → missing_finish_reason → complete。complete 不是默认值，是前面全部排除之后才轮到的兜底。结束要有两个独立的证人，关闭标记 `[DONE]` 和 `finish_reason`，缺一个都不算。

拿这把尺子去量三个项目：
- kimi-cli（Python，已归档在 1.52.0）：生产代码里一处都没读 `finish_reason`。SSE 解析全交给 SDK，上层分不清"收到 [DONE]"和"连接被关"。仓库已经归档，这个洞不会再修了。
- kimi-code（TypeScript 继任者）：统一了各家的 finish reason，子 agent 的 final summary 被截断时整个 run 会失败，这个检查装对了位置。可主 agent 自己的回答被截断时，截断标志算出来了，又在 turn 结束事件里被丢掉；TUI 的提示是从工具调用的角度写的："Model hit max_tokens — no tool call was emitted"；无头模式和编辑器插件完全没有感知。
- codex（Rust）：SSE、WebSocket、turn 主循环、事件映射四层，各自校验"流关了但没见到终止事件"，compaction 的两条流式路径也各复制了一份。

中间翻了两次。第一次，仓库里有两套同构的 LLM 引擎，我最先看的那套，主 agent 根本不走。第二次，"零防护"这个说法本身不对，准确的说法是：它知道截断发生了，但警告写错了对象。

issue 的论点落在不对称上：同一个故障模式，在子 agent 边界有硬检查，在主 agent 边界是静默的。拿项目自己已有的判断当标尺，维护者很难反驳。issue 附了复现和修法建议，[#4012](https://github.com/MoonshotAI/kimi-code/issues/4012)（2026-09-24）到 2026-11-14 还开着。

第二天跑的 108 格矩阵（第四节）说明这不是 kimi-code 一家的事：四个 CLI 里只有 codex 在每种故障下都给信号并自动恢复，另外三个基本是静默。要是按最初的口径"主循环对截断零防护"发出去，维护者打开 TUI 代码就能证伪。

### 2. deepseek-harness：并发启动的 TOCTOU 崩溃（Discussion #4312）

我用自己写的 dsh-eval-harness 给 dsh 插件跑回归。从 0.1.0-rc.6 升到 0.1.1-rc.2 后的第一次全量跑（12 条用例，并发 3），有两条首跑崩了、重跑又过了：三个进程同时启动，两个在 270 毫秒内 ENOENT 崩掉，栈分别在 `ensureSymlink` 的 readlink（index.js:380）和 unlink（:381）。

原因是每次启动都会"治愈"共享的 `profiles/node_modules` 符号链接目录，lstat → readlink → unlink 这串操作没有并发保护。更隐蔽的是，A 进程的 unlink 可能删掉 B 刚建好的正确链接，还不报错。上游其实知道会有并发：symlink 的 EEXIST 分支有护栏，注释写着"输掉竞争等于成功"。可它只防了创建，没防读和删。

定位是一步步来的：先看 harness 记下的重试历史和 stderr 尾部，再读源码找到竞态窗口，最后交给三个独立 agent 复核，其中一个跑了 16 路并发对照，稳定复现。

帖子发在官方 Discussions（[#4312](https://github.com/deepseek-ai/deepseek-harness/discussions/4312)），标题注明 "still present on master"。社区成员复现后发了一个参考实现。我在 macOS 上对照过：未修版本 16 并发 × 3 轮共 48 次启动，崩了 23 次；修复版同样 48 次，零崩溃；加到 24 并发 × 4 轮共 96 次，还是零。讨论还开着，上游有没有合入不知道。

TOCTOU 在回放里物理上不存在，回放式门禁抓不到这类 bug，只有真实重跑才碰得上。

### 3. skill-up：符号链接让实验根本没发生（#253 → PR #257，已合并）

阿里开源的 skill-up 有声明式用例、with/without 双臂对照和三层评分。我拿它一天跑完 17 个 skill 的首轮，9 个是我自己的 huohou，8 个是 tw93 的 Waza。

polish skill 首轮 6 过 4 败，报告挺好看。可翻 kimi 的会话落盘，所有 with_skill 会话里一次都没出现这个 skill 的名字，skill 列表里也没有。前三轮全量评测，两臂跑的都是裸模型。

原因在 `ListSkillFiles`：它用 Go 的 `filepath.Walk` 遍历，不跟随符号链接根。我的 skill 全是软链，于是选中 0 个文件；安装逻辑把 0 当正常，日志照常打 `skill installed`。

[#253](https://github.com/alibaba/skill-up/issues/253) 发出去当天就有 contributor 想认领。复现环境在我手上，我就作为报告者自己写了修复：解析符号链接，0 个文件直接报错，再加三条回归测试。[PR #257](https://github.com/alibaba/skill-up/pull/257) 2026-09-23 合并（+105/−2）。"0 个文件就报错"是我坚持要加的，选中零个文件却照常评估，这种沉默本身就该判死。

断言可能跑在一个从未发生的实验上。全量跑之前，先用直接证据确认被测对象真的在场，别看退出码。

### 4. skill-up：超时强杀，评测数据全丢（#263 → PR #265，已合并）

给 9 个 skill 跑触发评测，90 条用例里有一条 180s 超时，`session-result.json` 整个没了，前几个 turn 的事件（包括 skill 的激活记录）一起丢了。

读完源码才发现，skill-up 早就实现了 SIGTERM + 1 秒宽限 + 升级。问题出在两头：我这边的 python 引擎适配器没注册 SIGTERM handler，一收到信号就退出；框架那边在"超时且产物缺失"时没有任何兜底。[PR #265](https://github.com/alibaba/skill-up/pull/265) 补的就是这个兜底：合成一份最小结果（exit_code 124 + 合成标记）。PR 描述里单开了一节 "Correction vs. the issue sketch"，承认 issue 里建议的修法上游早就有了。

2026-10-08 合并（+361/−1），[#263](https://github.com/alibaba/skill-up/issues/263) 随之关闭。issue 里的修复建议是假设，不是承诺，读完源码就该按事实改。

### 5. skill-up：skill 内容层零校验（#280 → PR #281，审阅中）

这条来自"考官带伤阅卷"实验（第四节）。给 skill-up 自带的 skill-upper 注入内容损伤时发现，CLI 几乎不校验 skill 的内容：
- 只在 `internal/config/loader.go:240` 软读 name，读不到就悄悄换成目录名；
- description 从来不读；
- 被引用的附件在不在，不查；
- `run.go:705` 对 SKILL.md 只做 isRegularFile。

eval 配置出错倒是会硬报错。e2e 的 17 个夹具里有 3 个没有 frontmatter，照样跑得通。

我的修法是把完整性检查放进 Go 写的 CLI，不写进 skill 正文：前者不花 token，结果确定；后者每次加载都要付 token，还只是概率性地起作用。

这个 PR 拖得比较长。issue 发出当天，我自己补了两条精度更正："CLI 从不解析 SKILL.md"说重了，宿主矩阵也不是同一个模型。PR 第一轮 review 指出了句号边界、远程 URL、代码围栏三类误报，我改用 goldmark 做 CommonMark 解析，又按维护者的意见拆成独立的 `validate --skill <dir>` 源码级 linter。第二轮维护者又复现出三个问题，2026-11-14 在 8c9e12b 里全修了，等复审（+2062/−18）。

### 6. Waza：边界写在哪才有用（PR #87、#88）

Waza 的 8 个 skill 刚好是天然对照组，可以看边界声明写在不同位置的效果：
- 只写在 frontmatter 的 "Not for" 里：write 被夹带请求后直接交了 commit message，全程没提边界；health 接下了调试需求，还动手改了项目文件、跑了起来。
- 正文只有路由表：路由目标 /write 不在场时，check 一声不吭地接了单。
- 写成正文里的行为指令：ui 和 learn 守住了。ui 按判据粒度算，with 92%，without 40%。

frontmatter 只是路由元数据，运行时的约束得写成正文里的行为指令。当天我就在自己的 polish skill 上验证了一遍：同一条用例，"不管全文翻译"只写在 description 里时 66.7% FAIL，写进正文的红线节后 100% PASS。

[PR #87](https://github.com/tw93/Waza/pull/87) 把 scope fence 写进跨 skill 的护栏表，给 5 个 skill 补了正文规则。维护者 tw93 先在当前代码上复现了问题，再改了形态并进 3.38.0。[PR #88](https://github.com/tw93/Waza/pull/88) 修的是 read 的本地抓取层：在代理环境下它违背了"URL 不出机"的承诺，改成直连、绕开系统代理的环境变量，2026-09-19 合并。

### 7. dsh 插件生态：装上了却是死的（#152）；首启挂起（#7978）

测的是 dsh 插件榜上三个高星项目：路由/注入器约 7000★，视觉工具约 4000★，多 agent 编排约 1800★（星数是测评当天现拉的）。2026-09-26/27 实测，真实 API 一共花了 20116 token。

注入器靠 `prepare` 钩子在安装时构建，隔离环境里的包管理器（pnpm 11）默认拦截构建脚本，产物目录整个没有：安装命令 exit 0，插件却不工作。我给 routing-suite 提了 [issue #152](https://github.com/yjh051108/dsh-routing-suite/issues/152)，建议发布预构建产物，或者注明 allowBuilds，现在还开着。顺手还发现一个 npm 同名错位：裸名指向另一个账号下不相干的包，真正的包在 scoped 名下。安装命令的成功和插件的存活，是两个独立事件。

另一个问题让我翻了一次案。新建隔离配置、装上视觉插件后，第一次启动挂死，30 分钟没输出，我第一版写的归因是"插件启动阻塞"。后来补了个裸对照，全新配置、什么都不装，也挂。真凶是宿主自己：新 profile 首次启动会挂起。我原来的对照组用的是老配置。

这个宿主 bug 我带着复现和四路排除证据报给了上游（[Discussion #7978](https://github.com/deepseek-ai/deepseek-harness/discussions/7978)）。社区成员参与排查，我补了根因定位和充要验证：三个独立会话都能复现，第二次运行同样挂死，说明是 profile 本身的状态缺陷，不是一次性初始化的问题。对照组选错比没有对照组更危险，它会给错误结论配上证据。

两个可测插件的 chaos 韧性测试（一个对照加三种协议故障，共四格）全绿，和裸基线逐格一致。

### 8. e2e：缓存写入失败，结果里少了一个状态（#1371 → PR #1372，当天合并）

靶子是 tester-army/e2e（现在叫 e2e-inc/e2e）@0.21.3。我对同一条缓存结算路径做了三格对照：store 正常返回 `{bytes:128}`，结果是 saved；返回 undefined，结果是 not-written；write 抛出 EACCES，实际给的是 null，没按 CacheWrite 合同报 not-written。

异常被 catch 住了，也没有重复副作用，缺的是报告。按三因子说，"愿报"这一项是零。

[#1371](https://github.com/e2e-inc/e2e/issues/1371) 和 [PR #1372](https://github.com/e2e-inc/e2e/pull/1372) 在 2026-10-25 同一天提出、合并（+28/−1）。发 issue 时，三次创建请求都 TLS 握手超时，也没返回 URL。我按"写没写进去不确定"处理：先去重查询，再读回确认，网络恢复后才发出去。

业务成功、异常被吞、报告缺字段是三件事，得分三条路径分别验。

### 9. anthropics/skills：考官的校验器自己有盲区（PR #1949）

repo-quake phase 2 给"考官型 skill"做注入时，被测 skill 自带的 `quick_validate.py` 在本该报错的格子里没有反应。我对了三个版本：上游版（102 行）、Codex 分发版（127 行）、Claude Code 分发版（223 行）。
- name/description 的格式校验都在 `if name:` 这类真值判断后面，`name: ""` 在三个版本里都输出 "Skill is valid!"；
- 上游版和 Codex 版完全不查被引用的文件存不存在；
- 三个版本都不检测正文截断。这一项 PR 没覆盖，问题还在。

[PR #1949](https://github.com/anthropics/skills/pull/1949) 先断言非空再校验格式，并检查引用文件（+43/−0），2026-10-02 提交，还开着。

### 10. microsoft/eval-guide：断链和非法 YAML（PR #16）

在 @7a22a89 上发现两个问题。一是 SKILL.md:127 引用的三个资源路径在目录迁移后失效了，文件其实在 dashboard/ 下。二是有两份 SKILL.md 的 frontmatter description 没加引号，又含 ": "，PyYAML 报 `mapping values are not allowed here`，6 份里有 2 份解析失败。

上报前我先让第二双眼睛按声明逐条复现，把"三处失效"缩成了"SKILL.md 一处失效，脚本注释在自身语境下没问题"。顺便记下了我自己工具的盲区：skill-guard 解析宽松，放过了同一份文件。

[PR #16](https://github.com/microsoft/eval-guide/pull/16)（+3/−3）还开着。

### 11–13. skill-up 后来的三个修复（#295、#320、#338，都已合并）

前面三个 skill-up 案例之后，我又在它的配置校验和判分通道上找到三个问题，都由同一位维护者审阅合并。加上 #257、#265，我在 skill-up 上合并了 5 个修复 PR，#281 还在审。

#### 11. 拼错的 matcher 让禁止规则失效（#294 → PR #295）

rule_based 判分里写一个不存在的 matcher，比如 `output_not_contains`（正确写法是 `output_contains: {not: [...]}`），`skill-up validate` 照样显示 `✓ eval.yaml is valid`。

在 failure 位置写一条 `output_not_contains: {all: ["API key"]}`，再用 `skill-up debug judge` 喂一条明知违规的输出 "here is your API key: sk-123"，结果 **PASS，0/0 条断言**。以为在起作用的禁令，从来没被评估过。

原因是用例文件按非严格模式解析 YAML，不认识的键被悄悄丢掉，这条断言解出来是一条全空的规则。全空规则放在 success 位置，要等模型调用的钱花完才以 `unknown_rule` 报错；放在 failure 位置，就直接变成空操作，用例 0 条断言也能过。

PR 在 validate 阶段拒绝所有没有可识别 matcher 的规则，报错里写明规则位置，列出全部支持的 matcher。改动落在 eval 级和 case 级共用的校验函数里，`run` 执行前的校验也走这里；测试覆盖了全部 10 种 matcher（含 4 种 turn 级）的防误报用例（+169/−0）。严格 YAML 解码（`KnownFields(true)`）能顺带抓住所有字段的拼写错误，但带多余键的现有配置会全部失效，属于破坏性改动。所以 PR 只拒绝从来没起过作用的规则，格式正确的配置行为不变，严格解码留到以后。

2026-10-08 合并。2026-11-14，另一位贡献者在 #294 下指出同一类问题还有漏网的：matcher 在、值为空（比如 `output_contains: {all: []}`）时，同样零检查判 PASS，已经另开 #409。禁止型规则最需要阳性验证：喂一条明知违规的输出，它必须红。

#### 12. 照官方文档用相对路径，judge 却报路径逃逸（#319 → PR #320）

用例用 agent_judge 时，只要 `--output-dir` 是相对路径，整个用例就会在准备 judge 上下文时硬失败。相对路径恰好是官方 CLI 文档示例的写法：`--output-dir ./reports`。报错是 `judge context material path escapes context dir: "final_message.txt"`，实际上根本没有路径越界。issue 里写了，这是对 judge 通道做故障注入时发现的。

原因是 `judgeContextHostDir` 返回的目录没转成绝对路径，相对的 `--output-dir` 一路传了下去。守卫函数 `isWithin` 只给根目录取了绝对路径，再拿它和相对的候选路径做 `filepath.Rel`，算出错就返回 false，调用方于是报了一个不存在的逃逸。

修法改过一版。第一版在守卫这边给候选路径也取绝对路径，等于把守卫放宽了。修订版改成从源头修：`judgeContextHostDir` 的两个分支都返回绝对路径（一个是指定了产物目录，一个是走 `MkdirTemp`，而 TMPDIR 本身也可能是相对路径）；守卫恢复严格的字面比较，`../escape.txt` 这类越界照样被拒。

验证做得比较细。新加了三组测试：绝对根目录下的精确值断言和越界拒绝、相对产物目录、相对 TMPDIR。还做了变异检查：去掉取绝对路径这一步，原报错就回来；回退空目录分支，对应测试就挂。`go test -race`、lint、vet 全绿，6 个发布平台的 `CGO_ENABLED=0` 构建都过了。扩展 CI 的 GoReleaser 检查挂了两次，我查了一下，是自托管 runner 和服务端断了联系、日志都没留下，跟改动无关，把两次运行的链接附在了 PR 里。

2026-10-20 合并（+109/−2）。守卫误报，最省事的办法是放宽守卫；该做的是让进守卫之前的数据先规范。

同一天我还报了 [#321](https://github.com/alibaba/skill-up/issues/321)：judge 出错后被救回来的判定，在 report.json 里和正常判定分不出来，看报告的 CI 门禁不知道 judge 是一直健康，还是崩了之后输出被抢救回来的。社区贡献者据此在 #332 加了机器可读的 `judge_recovery` 标记，维护者确认已经合进 main，关了 issue（2026-10-23）。

#### 13. 只有空白的 prompt 也能通过校验（#337 → PR #338）

2026-10-24，我用 repo-quake 对上游 main @ad5f533 做回归，顺带跑了一组确定性的配置边界矩阵，六种配置：健康配置、空字符串 prompt（对照）、只有空白的 prompt、只有空白的 turn、空用例列表、缺失用例。

`input.prompt: ""` 会被正确拒绝；`prompt: "   "` 和只有空白的 `turns[].content` 却都显示 `✓ eval.yaml is valid`。第二个独立 agent 用空格、制表符、换行复现了同样的结果，正常文本照常通过。

原因在 `internal/config/validator.go`：判空时直接跟空字符串比，没先 `strings.TrimSpace`。同一个文件里别的校验（比如 `user_simulator.scenario`）早就用了 TrimSpace。空任务因此能过配置校验，一路走到引擎执行。issue 里也把话说到了边界：这本身不能证明会出现整体 PASS，也不能证明产生了付费调用。

PR 只在判断是不是空的时候 TrimSpace，不改写存下来的 prompt 字节。互斥判断仍按原始字节看"有没有"，所以 `prompt: " "` 加合法 turns 依然非法，不会悄悄变成只有 turns 的用例。表驱动测试覆盖了空格、制表符、换行、合法内容带前后空白，以及 prompt/content 与 respond 的互斥（+90/−3）。验证全程没用真实模型，没有付费调用。

同一组矩阵修复后复跑：两个空白格从 exit 0 变成 exit 1，报 `input.prompt or input.turns is required`；健康格还是 0，空字符串对照还是 1。2026-10-26 合并。

那次回归的主实验是删掉 skill-upper 必需的一个模板。宿主走完了"检出 → 报告 → 用替代参考补上 → 恢复 → 独立复验"整条路，没暴露新问题，所以主实验没提 issue。真正的 bug 出在旁边那组一个 token 都不花的确定性检查里。

这三个问题，#294 和 #337 是放水，校验器放过了不该放的东西；#319 是误杀，守卫把合法的运行拦成了路径逃逸。三个 PR 的做法一样：把检查放进确定性的一层（validate 阶段，或者在源头规范路径），再用防误报用例、变异检查、修复前后的矩阵证明修复本身没带来新的误判。

## 四、横评

### 4.1 108 格截断矩阵

2026-09-25 跑的。本地 mock 在同一个端口上提供三种协议，故障只注入一次（once），每个请求都留一条送达证明。条件有 6 种：F0 正常（对照）、F1 中途断流、F2 丢终止事件、F3 半个事件断流、F4 length 截断、F5 think-only。规模是 6 行（dsh 三种协议各一行）× 6 种条件 × 3 次 = 108 格，F0 全绿，每格三次结果一致。分级：L0 静默，L1 弱信号或说错对象，L2 明确告知，L3 告知并自动恢复。

| 工具 / 协议 | F1 | F2 | F3 | F4 | F5 |
|---|---|---|---|---|---|
| codex 0.156.1 / Responses | L3 | L3 | L3 | L3 | L3 |
| claude code 2.1.282 / Messages | L0 | L0 | L0 | L0 | L0 |
| kimi-cli 1.52.0 / Chat Completions | L0 | L0 | L0 | L0 | L3 |
| dsh 0.1.7-rc.2 / 三种协议（结果一致） | L0 | L0 | L0 | L1 | L1 |

30 个故障格里，L3 6 格（20%），L2 0 格，L1 6 格（20%），L0 18 格（60%）。不少 L0 格最后靠静默重试交出了完整回答。检出不难，告知才是缺口。

几家各有各的毛病。codex 全部自动恢复，但把 length 截断报成 "Reconnecting... 1/5"，原因说错了。claude code 的 transcript 里明明记着 `stop_reason: "max_tokens"`，知道，但不说。dsh 打完正文直接 exit 1，一句提示都没有，session 里却记着 max-tokens。codex 和 dsh，一个只告诉人，一个只告诉机器。

复现包是 [truncation-detection-benchmark](https://github.com/BiBoyang/truncation-detection-benchmark)：约 400 行零依赖的 mock，附逐格证据。

### 4.2 考官带伤阅卷

靶子是 skill-up 的 skill-upper，一个"负责测评其他 skill 的 skill"，任务是给我自造的 greeting-card skill 设计评测并 validate。伤口有这些：T1 主文件截到 60%（290 行 → 174 行），T1-85 截到 85%，T2 删掉被引用的附件，T3 附件截掉一半，T4 清空 frontmatter 的 name/description，T5 用例模板截掉一半，T6 删掉指令点名要复制的模板；C0 是阴性对照，全程都在。

结果：T1 **8/8**，每次都明确指出问题并定位到断点行；T3 **2/8**；T6 3/3，T5 2/3，T4 3/3，T1-85 1/3；对照组没有误报。截到 60% 反而比截到 85% 更容易被发现，检出看的是伤挡不挡路，不是伤有多重。

我还杀了个回马枪：让带伤的考官去给一个同样带伤的 skill 出卷子。两处伤都没被发现，卷子也真的改歪了：凡是来自被截掉那半段的断言，命中数全是零。

跨宿主的数字：T1 在 kimi-code、Claude Code、Codex 上分别是 8/8、3/3、3/3；T3 分别是 2/8、3/3、2/3。口径声明原样保留：Claude Code 那一列实际跑在 DeepSeek v4.1 flash 上，矩阵里同时有脚手架和模型两个变量，所以差异不做归因拆分。

loader 层也看了一眼：frontmatter 为空的 skill，在 kimi-code 2.1.0 里会从列表里静默消失；在 Claude Code 2.1.282 里会被用目录名兜底，注册成一个没有触发语义的"僵尸条目"。两边都不报错。

完整性是供应链问题，不是上下文问题。防线应该放在 CI、loader、安装器，不在 skill 正文里。

### 4.3 仓库级实验

宿主是 kimi CLI 和 codex CLI，书里这一章一共 88 次宿主运行。靶子有两个：一个是照 Vercel eve "an agent is a directory" 的结构手搓的最小贺卡 agent（没有对 eve 仓库本体注入）；一个是基于 PydanticAI 的贺卡 agent，用确定性的模型替身截获框架发给模型的 payload。

- 挡路：把 instructions.md 从 22 行截到 12 行，丢了安全规则和工具约定，但剩下的流程恰好还能走完。0/16。
- 读到：把工具源码截在 schema 正中间。kimi 的 8 次运行里，有 7 次的访问轨迹根本没进 tools/ 目录。
- 外壳还是模型：第一轮 codex 5/8、kimi 0/8，看起来是 codex 的外壳更严谨。查配置发现两边模型不一样，补了 2×2 同模型对照：kimi CLI × kimi-for-coding 0/8，codex CLI × kimi-for-coding 0/8，codex CLI × k3-256k 5/8，kimi CLI × k3-256k 1/8。严谨住在模型里，不住在外壳里。推理档位没对齐，方向可信，强度存疑。
- 察觉了但不报：有一次运行在推理过程里写了 "render_card.ts was truncated (only 12 lines)"，最后交付时只字未提。
- 检出不等于止损：删掉被引用的规则文件后，16/16 都明确报告了缺失，然后全部继续往下做。规则里"恰好一个 emoji 放在末尾"这一条，合规率从基线的 4/4 掉到 0/8 和 3/8。
- 框架层的静默传导：截获的 PydanticAI payload 显示，截断后工具 docstring 从 211 字符变成 31，system prompt 从 917 变成 663，框架一句告警都没有。这不是框架的 bug，框架没有义务替用户校验内容。
- 阳性对照：语法错误这种响亮的故障 8/8 检出，只能说明检测通道是活的，说明不了隐形的伤会被发现。

phase 2 对 anthropics/skills 的 skill-creator 和 microsoft/eval-guide 做注入：4 处伤 × 2 个宿主 × 8 次，0/64。目录和脚本的自描述能兜底，条件引用不一定被触发，有的伤要到下次会话才用得上，所以都不挡路。这次失败本身也是数据：设计伤口之前，得先确认任务路径一定会经过它。第三节的案例 9、10 就是这一轮的副产物。

## 五、先审自己

这个系列抓了这么多 bug，最后一个永远是自己的。

### 5.1 四次翻案

| 翻案 | 一开始以为 | 实际 | 怎么发现的 | 长出的机制 |
|---|---|---|---|---|
| skill-up #264 | 重跑报 PASS 却不落盘（复现 3 次，mtime 纹丝不动） | 在子目录里用了相对路径，产物写进了嵌套目录；stat 的又是旧 iteration | 准备 PR 时加 -v，日志显示产物写进了 iteration-2，这是文档写明的语义 | 公开更正、道歉并请关闭；重跑一律用绝对路径；报告里写出排除计数 |
| 冤枉 codex | codex 对 length 截断完全静默（L0） | 我的 mock 说错了协议方言：把 length 截断发成 response.completed + status，真实 API 发的是独立事件 response.incomplete | 结果和源码对不上 → 用 tmux 起真 TUI，否证"exec 模式吞掉了重试" → 逐事件核对 mock 发出的字节 | 每种故障配一个阳性对照变体；两格结果作废，留作教学样本 |
| CI 红、本地绿 | 平台差异（为此读了一小时信号和进程组的源码） | CI 测的是 PR 和最新 main 的合并态，上游 PR #250 收窄了一个字段的语义 | 一条 git log | 断言职责，不断言字段 |
| 插件"启动阻塞" | 插件的问题 | 宿主的新 profile 首启挂起 | 补了一个裸对照 | 对照组的"无"必须强制做出来 |

还有两个差点发出去的错误结论。一个是用 strings 在 codex 二进制里搜事件名，零命中，差点写下"没有这个处理器"，其实是编译器把匹配内联成了立即数比较：strings 阴性，不等于代码不存在。另一个是 T4（清空 frontmatter）首轮手工实验干干净净落在 L0，差点写成"稳定无察觉"；第三轮批量复测，三路宿主全部指了出来。单发是轶事，x/N 才算数。

#264 的维护者回复说，这份更正完全解释了观察到的现象。

### 5.2 仪器缺陷

测别人之前先测自己：

| 自己的 bug | 后果 | 长出的机制 |
|---|---|---|
| harness 在非零退出时仍判 PASS | 子进程崩了，trace 断言却全部通过 | 非零退出永不判 PASS |
| 筛选条件笔误，零命中 | CI 空跑，照样显示绿灯 | 无命中直接报错 |
| 多帧 zstd 一次性解压 | 只解出第一帧，静默截断 | 逐帧解析，加跳行告警 |
| trials 门禁只看点估计 | 10 次只过 1 次，门禁照样放行 | 改判单侧 Wilson 下界（9/10 的下界约 0.65） |
| 超时只杀直接子进程 | 孙进程变成孤儿，runner 挂死 34 分钟 | 改为杀整个进程组，加"孙进程必死"回归断言（dsh-eval-harness v0.6.0） |
| 判活器本身 | — | 32 条自测断言（含故意构造的坏样本），上线首日就抓到判活器自己崩溃 |
| 运行路径名里带着伤型 | 被测宿主拿路径名当佐证，猜出了实验内容 | 宿主可见路径全部哈希化，实验产物移出宿主可见目录 |
| 用户级时间戳 hook | 打碎了 judge 的 JSON，污染了宿主输出 | 隔离 HOME，剥离 hooks |
| 关键词扫描分级 | 把宿主自己读文件时的截断当成检出，出了 5 个假阳性 | 分级改回逐条阅读原文 |
| grader 比冻结的合同更严格 | 把合法结果判成失败 | 初判原样保留，另写裁定，不靠重跑解决 |
| skill-guard 的路径正则没有边界锚点 | 自家 skill 被误判，门禁红了 6 天 | 新增的 dogfood 检查发现问题后，补上锚点修复 |
| 被测 agent 在无隔离环境下运行 | 它真的在宿主机上装了一条每天清理 /tmp 的 crontab | 当场清除；默认改用 docker / opensandbox 隔离 |

台账把这些和目标缺陷记在同一本账里：8 条仪器缺陷、10 条实验无效事件，和 13 条目标缺陷并列。

## 六、最后

这些 bug 有个共同点：都不报错。截断被当成成功，零文件被当成安装成功，超时吞掉产物，拼错的规则悄悄变成空操作。我的做法是先造出能让它们露头的故障，再给每条结论配上证人；修复尽量落在确定性的那一层，不写进 prompt 里碰运气。

用到的工具都开源了：dsh-eval-harness、truncation-detection-benchmark、skill-quake、repo-quake，换个人也能照着复现。

## 附：出处索引

**《自顶向下拆 Agent》评测卷**

- [序章 · 没报错，就代表输出没问题吗](https://biboyang.github.io/books/agent-ui/prologue.html)：案例 1
- [02 · 考题从哪来](https://biboyang.github.io/books/agent-ui/eval02.html)：案例 3、6
- [03 · 绿灯的两种谎言](https://biboyang.github.io/books/agent-ui/eval03.html)：在场证明、送达证明、仪器缺陷
- [04 · 炸弹](https://biboyang.github.io/books/agent-ui/eval04.html)：4.1、4.2、案例 5
- [05 · 检出率是个乘法](https://biboyang.github.io/books/agent-ui/eval05.html)：4.3
- [06 · 对照组的陷阱](https://biboyang.github.io/books/agent-ui/eval06.html)：案例 7
- [14 · 断言不了输出，就断言关系](https://biboyang.github.io/books/agent-ui/eval15.html)：案例 4、第五节

**《我的评测工具链》**（[导读](https://biboyang.github.io/eval-series/)）

- [一 · 从 trace 到 eval](https://biboyang.github.io/books/eval-series/ch01.html)：案例 2、仪器缺陷
- [二 · 给 skill 建门禁](https://biboyang.github.io/books/eval-series/ch02.html)：案例 3、6
- [三 · 我给 skill-up 报了一个不存在的 bug](https://biboyang.github.io/books/eval-series/ch03.html)：案例 4、#264
- [四 · CI 红、本地绿](https://biboyang.github.io/books/eval-series/ch04.html)：第五节
- [五 · 回答被截断，你的 CLI 知道吗](https://biboyang.github.io/books/eval-series/ch05.html)：4.1、案例 1
- [六 · 给流式协议造故障](https://biboyang.github.io/books/eval-series/ch06.html)：4.1 的 mock 与翻案
- [七 · 考官带伤阅卷](https://biboyang.github.io/books/eval-series/ch07.html)：4.2、案例 5

**repo-quake**

- [仓库](https://github.com/BiBoyang/repo-quake)
- [缺陷台账](https://github.com/BiBoyang/repo-quake/blob/HEAD/ledger/ledger.json)：案例 8、9、10，4.3 的 phase 2，5.2
- [runs/skill-up-main-2026-10-24](https://github.com/BiBoyang/repo-quake/tree/HEAD/runs/skill-up-main-2026-10-24)：案例 13 的配置边界矩阵与修复前后退出码

**书外**

- 案例 11、12 不在书中，出处是 skill-up 的 issue/PR 原文，链接见第一节总表。
