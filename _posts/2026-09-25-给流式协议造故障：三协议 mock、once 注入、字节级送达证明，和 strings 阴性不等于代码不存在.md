---
layout: post
title:  "给流式协议造故障：三协议 mock、once 注入、字节级送达证明，和 strings 阴性不等于代码不存在"
date:   2026-09-25 21:00:00 +0800
categories: [AI]
tags: [AI, Agent]
---

> **系列 · 我的评测工具链**（持续更新）
>
> 1. [从 trace 到 eval：trace 设计、agent eval 方法论、一个 eval harness 的实现，和它抓到的上游并发 bug](/posts/从-trace-到-eval-trace-设计-Agent-评测方法论-一个评测-harness-的实现-和它抓到的上游并发-bug/)
> 2. [给 skill 建门禁：一天里的三种沉默失败、一次红线写法实证，和它抓到的上游 bug（又一只）](/posts/给-skill-建门禁-一天里的三种沉默失败-一次红线写法实证-和它抓到的上游-bug-又一只/)
> 3. [我给 skill-up 报了一个不存在的 bug](/posts/我给-skill-up-报了一个不存在的-bug/)
> 4. [CI 红、本地绿：一次「平台差异」误诊，和 merge 干净不等于语义兼容](/posts/CI-红-本地绿-一次-平台差异-误诊-和-merge-干净不等于语义兼容/)
> 5. [回答被截断，你的 CLI 知道吗：四个工具、六种故障、108 格矩阵，和一个差点发布的错误结论](/posts/回答被截断-你的-CLI-知道吗-四个工具-六种故障-108-格矩阵-和一个差点发布的错误结论/)
> 6. **给流式协议造故障：三协议 mock、once 注入、字节级送达证明，和 strings 阴性不等于代码不存在**（本文）
> 7. [考官带伤阅卷：对 Agent Skill 做故障注入的完整性实验](/posts/考官带伤阅卷-对-Agent-Skill-做故障注入的完整性实验/)

> 上一篇是结论，这篇是厨房。一个给流式协议做确定性故障注入的 mock provider 怎么设计，三次口径修复各教会我什么，以及为什么 strings 搜不到不代表代码不存在。

# 1. 为什么不用中间人

测「截断检出」需要精确控制故障：第几个事件后断、终止事件发不发、finish_reason 填什么。方案里写了两条路：本地 mock provider 注入（首选），mitmproxy 中间人（兜底）。最后 mitmproxy 一次没启用——四个工具全部能接受本地 mock 的 base_url，中间人失去了存在意义。

mock 路线赢在一个字：**确定性**。真实代理里「发到一半断流」是个运气事件，mock 里是一行参数。测评要的是每格 3 次结果一致，只有确定性能把 flaky 压到零——最终 108 格全部 3/3 同级。

# 2. 把四个工具指向本地：最短配置路径

四个工具，四种指法，每种都有一个小坑。

**codex**：`-c` 命令行覆盖，不动 `~/.codex/config.toml`：

```console
MOCK_API_KEY=mock codex exec --skip-git-repo-check \
  -c model_provider=mock \
  -c 'model_providers.mock.base_url="http://127.0.0.1:8787/v1"' \
  -c 'model_providers.mock.wire_api="responses"' \
  -c 'model_providers.mock.env_key="MOCK_API_KEY"' \
  "<prompt>"
```

**claude code**：裸 `export ANTHROPIC_BASE_URL` 不够——`~/.claude/settings.json` 的 `env` 块会盖过它（我本机配了第三方网关）。最短路径是 `--bare --settings`，命令行 settings 优先级最高，bare 模式顺带跳过 hooks、插件、keychain 和 CLAUDE.md：

```console
claude --bare \
  --settings '{"env":{"ANTHROPIC_BASE_URL":"http://127.0.0.1:8787","ANTHROPIC_API_KEY":"mock",...},"model":"mock-model"}' \
  -p "<prompt>"
```

**kimi-cli**：已归档，PyPI 最新 1.52.0 的所有入口被 deprecation gate 短路——裸跑 `kimi` 只会拉一个 CDN 安装脚本去装它的继任者。好在原 Typer CLI 完整保留在包内，`kimi_cli.__main__.run_original_cli` 用 venv 内 python 直调即可绕过墓碑。遥测端点是硬编码的，用 `KIMI_DISABLE_TELEMETRY=1` 加 config 双保险关掉。装依赖用 uv 一次成功，没触发我给自己定的「环境折腾超过半小时就放弃」熔断。

**dsh**：`$DSH_HOME/settings.yaml` 里配 `llm-pi-ai.providers.<id>`（api / baseURL / apiKeyEnv / models），`DSH_HOME` 环境变量整体隔离配置目录，不碰 `~/.dsh`。

四条路都不碰真实 API——这是整个测评的硬约束，所有结论只连本地 mock。

# 3. mock 的三层设计

一个 Node 文件（`mock.mjs`，约 400 行，零依赖），三层结构。

**协议端点**。同一端口挂三个：`POST /v1/chat/completions`、`POST /v1/responses`、`POST /v1/messages`，外加健康检查、模型列表、Anthropic 的 count_tokens（Claude Code 会调）。每种协议的 SSE 事件序列按真实 API 的形态手写——这一步是全部地基，也是后文最大教训的案发地点。

**故障即参数**。六种故障 F0–F5 是请求参数，优先级：URL query > 请求头 > 控制面。运行时可切换：

```console
$ curl -X POST localhost:8787/__control -d '{"fault":"F2","once":true}'
```

**送达证明**。这是和普通 mock 拉开差距的一层：每个请求落一条结构化日志，记录实际 write 的字节数、完整事件序列、终止证人（`[DONE]` / `response.completed` / `message_stop`）送达没有、以什么方式关流：

```json
{"seq":24,"path":"/v1/responses","fault":"F4","user_agent":"deepseek-harness/0.1.7-rc.2",
 "bytes_sent":30755,"events_count":54,"events":["response.created","response.output_item.added",...]}
```

请求侧对称记录：字节数、prompt 标记、完整请求体落盘。有了这层，「工具没反应」和「故障没送达」才分得开——上一篇的翻案靠的就是逐事件核对这些字节。

顺带一提，把这三层从「模型回答」平移到「tool call」，就是 agent harness 可靠性测评的地基：故障开关对应工具失败注入，调用账本是断言「无双重副作用」的唯一依据，结果回放支撑「先回 200 再断流、对账时返回真实结果」这类两阶段剧本。那是另一个评测对象，留着以后打。

# 4. 三次口径修复

mock 从写完到可信，修了三次口径。每次的道理都比修复本身值钱。

**第一次：内容一致性。** F4 最初的实现把正文段落重复发了一遍，且 Responses 端点 `output_item.done` 里携带的完整文本和 delta 流的拼接不一致。协议上两者必须严格相等——done 事件是「汇总」，delta 流是「过程」，客户端有权利交叉校验。教训：**故障可以造，协议不变量不能破坏**——你要测的是「截断」，不是「数据自相矛盾」，后者触发的是另一条错误路径。

**第二次：注入语义。** 初版注入是「控制面切换故障 + 外部轮询复位」：打控制面设 F4，等工具请求消费掉，再轮询确认后切回 F0。实测直接翻车——工具的重试比轮询快，故障要么逃逸（重试赶到复位之后，打了两次），要么被并发请求抢走。改成 mock 内建 once：「仅下一个命中条件的请求」携带故障，命中即失效，不需要外部复位。后来交互模式测试又发现 TUI 会并发发辅助请求（codex 并发一个标题生成请求，42KB 体；claude 类似），once 又长出 `match`/`avoid` 子串条件来钉住主请求——附录第一个格子就踩中过辅助请求抢故障。教训：**注入点必须内建于故障源**，外部协调的窗口期永远比赛态条件宽。

**第三次：协议方言。** 这是上一篇翻案的工程侧。初版 mock 把 Responses 的 length 截断发成 `response.completed` 事件裹 `status:"incomplete"`——凭直觉拼的，「看起来信息都在」。真实 API 的方言是独立事件类型 `response.incomplete`，携带 `incomplete_details.reason`。codex 的 completed 分支不解析 status，信号等于没说出口；dsh 底层的 pi-ai 两种方言都认，安然无恙——同一个错误，一边假阴性，一边被兼容层默默消化。修正后重发真实事件，codex 立刻检出重试。教训最重，值得单独成句：**mock 的权威性和被测客户端的严格性成反比——客户端越宽容，你的方言错误藏得越深。** 每种故障形态都该配一个「必然触发现有检测」的阳性对照变体，而且对照要细到事件名的粒度。

# 5. 判读陷阱集锦

测评的另一半工程量在「判读」——看见什么算什么。四个陷阱，按踩坑顺序。

**strings 阴性 ≠ 代码不存在。** 翻案调查时我往 codex 二进制里搜 `response.incomplete` 整串，0 命中，差点写下「无此处理器」。实际 Rust 的 match 被 LLVM 内联成立即数比较，字符串不进 rodata；处理器证据串（`Incomplete response returned`）反而在。二进制取证要把「事件名」和「处理器证据」分开搜。

**判定防污染。** mock 的正文主题恰好就是「截断」——正文里全是「截断」「终止」「重试」这些判定关键词。直接扫输出，每个格子都「有信号」。解法：扫描前把 54 个 mock 段落精确剥除（去空白匹配，对抗 kimi 按终端列宽硬折行），transcript 打标只认结构性键值、不认文本内容。

**TUI 画面采集。** tmux `capture-pane` 判定弹窗只能扫当前可见屏，带 `-S -` 全量回滚会让「已 dismiss 的弹窗」永远匹配、循环卡死。而 codex 的 Reconnecting 是瞬态状态行，恢复后即被重绘抹除——终屏截图证明不了它存在过，得用 0.4 秒轮询专门捕获。

**弹窗与版本保卫。** 交互测试用隔离 home 预播种消解一次性弹窗（codex 的目录信任、claude 的 onboarding 与 API key 批准）。最险的一个：codex 的更新提示弹窗，Enter 会触发 npm install 把被测的 0.156.1 顶成最新版——只能按 Esc。测评矩阵外还真出过一次这类事故：全局 codex 曾被第三方装成 0.157.0 且装坏，恢复钉死版本后才开跑。**被测工具的新旧本身会被网络环境筛选**，所以版本号和测试日期要写进每张记录表。

**请求数不是重试证据。** kimi 的 print 模式偶发两次请求（辅助请求），dsh 主回答与辅助请求并发。判「有没有重试」只能看画面和事件流，数请求数会把辅助流量误判成自救。

# 6. 交互附录与复现

主矩阵全部跑非交互模式（exec / -p / --print / headless）。为回答「模式有没有影响」，补了 12 格交互附录：codex 和 claude 在 tmux 里起真 TUI 复测 F4/F5——结论是无模式差异。这里有个诚实标注值得说：dsh 没有终端 TUI（profile 只有 acp/web/headless/sdk，交互面是 web GUI），附录里它的位置标的是 N/A，而不是硬凑一行。缺席标 N/A，比编一个数字体面。

复现路径：起 mock（`node mock.mjs --fault F0`），按第 2 节配好任一工具，打控制面注入故障，收四路证据（stdout/stderr、exit code、transcript、mock 日志）对照判定。runner 脚本把这一串固化成了一格一条命令。

mock、runner 和 108 格逐格证据整理后会开源。这套东西对我是长期资产：以后每出一个新 CLI，配一次 base_url，几小时就能跑一轮同样的测评——横评做成连载，工具链才算真的建成。

---

*本文涉及的仓库：[deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)（被测对象之一）、[kimi-code](https://github.com/MoonshotAI/kimi-code)（相关上游，见 [issue #4012](https://github.com/MoonshotAI/kimi-code/issues/4012)）。mock 与矩阵 runner 开源后在此补链接。*
