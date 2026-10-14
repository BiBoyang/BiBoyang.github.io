# Codex 多层防护（defense-in-depth）模式盘点

> 调研快照：`codex-src`，commit `6b9826e3aa83b1a5947db50f4332cb9c65f1b340`
> （2026-09-09 14:43 -0700，v0.154.0-dev，带完整 git 历史 12172 commits）。
> 对照快照：`codex-src-v0.160.0`（**比主快照新**，version = "0.160.0"，CHANGELOG 引用 #44557）。
> 所有行号基于主快照。标注"注释"的内容为源码注释转述。

## 总表

| # | 不变量 | 层数 | 位置（主层） | 性质 | 测试钉死 |
|---|--------|------|--------------|------|----------|
| E1 | 响应流必须以 `response.completed` 收尾 | 3 拦截 + 1 观测 | sse/responses.rs:598；responses_websocket.rs:720/836；turn.rs:2381 | 设计（graft 前已有）+ 观测层后补 | stream_no_completed.rs::retries_on_early_close |
| E2 | deny-read 路径任何情况下不可读 | 2 否决 + 2 fail-closed | tools/sandboxing.rs:238/281；bwrap.rs:1149 | **事后补的疤**（#23943, 2026-05-28） | deny_read_blocks_explicit_escalation_and_policy_bypass |
| E3 | .git/.agents/.codex 元数据不可写 | 2（+1 备用 API） | permissions.rs:1017；seatbelt.rs:584 | **设计时分层**（#19846+#19847 同 stack） | seatbelt_tests.rs:571/2310/2358 |
| E4 | 受限会话网络必须被约束，失效即断 | 3 | seatbelt.rs:347/353；network-proxy/runtime.rs:581；exec-server-protocol:315 | 设计 | network-policy 测试群 |
| E5 | 进程不可被 dump/调试/注入 | 单模块多机制 | process-hardening/src/lib.rs:44-100 | 设计（注释自承 "defense in depth"） | 无直接测试 |
| E6 | rollout 迁移后磁盘永远可恢复 | 4（staging/verify/journal/barrier） | rollout_migration.rs:7-9；live_writer.rs:315/335 | 设计 | rollout_migration_tests.rs |
| E7 | history 中 call/output 必须配对 | 2 生产 + 1 测试基建 | history.rs:474/702；tests/common/responses.rs:1675 | 设计 | history_tests.rs + 全局 mock 校验 |
| E8 | 跨 turn 不残留 pending server requests | 3（同动作三处） | bespoke_event_handling.rs:167/197/1227 | 自觉冗余（注释 "be extra cautios"） | 间接 |
| E9 | managed requirements 对活跃设置成立 | 2（选择时+激活时） | step_settings.rs:149/318；step_activation.rs:384 | 设计（TOCTOU 复核） | step_activation_tests.rs |

---

## E1. 流终止检测：response.completed 缺失

**守的不变量**：模型响应流必须以 `response.completed`（或显式 error/failed）收尾；
传输层提前关闭必须转成显式错误并触发重试，绝不允许"安静地结束"。

**各层位置与校验方式**：

1. **SSE 传输层** `codex-api/src/sse/responses.rs:596-601`：eventsource 流返回
   `Ok(None)` 时注入 `Err(ApiError::Stream("stream closed before response.completed"))`；
   若之前已解析到 `response.failed` 事件则优先用具体错误（:597 `response_error.unwrap_or(...)`）。
   同层 :604-608 还有 idle timeout（"idle timeout waiting for SSE"）。
2. **WebSocket 传输层** `codex-api/src/endpoint/responses_websocket.rs:718-722`
   （`Ok(None)` → 同样错误）与 :835-838（收到 `Message::Close` 帧 →
   "websocket closed by server before response.completed"）；:707 idle timeout。
   注意 :718 和 :836 是同层内两个 sub-case，不是两层。
3. **turn 主循环** `core/src/session/turn.rs:2378-2382`：`stream.next()` 返回 `None`
   时 `break Err(CodexErr::Stream("stream closed before response.completed"))`。
   这是真正的兜底——即使传输层 channel 正常关闭却没注入错误（比如未来新增传输实现
   忘了这个约定），主循环照样兜住。
4. **观测层（非拦截）** `core/src/client.rs:2309-2313`：`map_response_events` 的转发
   循环耗尽后调 `inference_trace_attempt.record_failed("stream closed before response.completed")`。
   它**不向流里注入错误**，只记 trace。另有 `STREAM_DROPPED_REASON`
   （client.rs:2150，"response stream dropped before provider terminal event"）
   处理消费者提前 drop 的镜像场景。
5. **同族复制**：compaction 路径各自独立实现同一检查——`core/src/compact.rs:787`、
   `core/src/compact_remote_v2.rs:466`。

**防住的失败形态**：若全部失守，一次网络抖动导致的 TCP 半关闭会让 turn 表现为
"正常结束但输出不完整"——模型只说了半句话，UI 显示完成，用户拿到截断结果且
无任何错误提示。有了这些层，断流必然转成 `CodexErr::Stream`，经
`handle_retryable_response_stream_error` 重试（turn.rs:1515 附近的
`run_sampling_request` 循环），重试耗尽后显式报错。

**测试**：`core/tests/suite/stream_no_completed.rs::retries_on_early_close`
（端到端：第一次给不完整 SSE，断言重试后 TurnComplete 且 server 收到 2 个请求）；
单测 `codex-api/src/sse/responses.rs:953 error_when_missing_completed`、
`:1049 emits_completed_without_stream_end`。

**疤还是设计**：SSE/WS/turn-loop 三层在 graft 边界 commit 32d2df5c1（2026-03-19）
之前就已存在（blame 全部落在边界上）；client.rs 的 trace 记录是 89698ad1c3
（2026-04-28）后补的观测增强。**结论：核心三层是早期设计，观测层是后补**。

**对 prologue 的修正**：prologue 说的"事件映射层"如果指 `core/src/client.rs`
的 `map_response_events`，那它不是拦截层——它不做错误注入，只做 trace 记录。
真正的拦截层是 SSE、WS、turn 主循环三处；compaction 两条路径另有独立复制。

---

## E2. deny-read 路径的升级逃逸否决

**守的不变量**：只要策略里存在 deny-read 条目（如 `**/*.env`），就绝不能以
"无沙箱"方式运行任何命令——即使用户显式批准升级、即使 execpolicy 判 allow。

**各层位置与校验方式**：

1. `core/src/tools/sandboxing.rs:238-247` `sandbox_override_for_first_attempt`：
   首尝试沙箱 bypass 决策点，有 deny-read 时返回 `NoOverride`。注释（原文）：
   "Running without a filesystem sandbox would discard them, even if the command
   was otherwise approved by rules or explicit escalation."
2. `core/src/tools/sandboxing.rs:281-295` `sandbox_permissions_preserving_denied_reads`：
   权限解析阶段**再次**把 `RequireEscalated` 降级为 `UseDefault`。注释（原文）：
   "`RequireEscalated` normally asks the executor to bypass the sandbox. When denied
   reads are active, that would drop the only mechanism that enforces them, so fall
   back to the default sandboxed attempt instead."
3. `linux-sandbox/src/bwrap.rs:1149-1158`：bwrap 用 bind-mount mask 实现 deny-read，
   发现保护路径跨越可写符号链接时直接 `Err(Fatal)` fail closed。注释论证了
   TOCTOU 快照问题（解析 symlink 当前 target 只能保护旧 target）。
4. `protocol/src/permissions.rs:335`（注释）："Runtime read checks intentionally
   fail closed on malformed deny patterns"——deny glob 解析失败也按拒绝处理。

**防住的失败形态**：`cat`/`ls` 这类"已知安全"命令被 execpolicy allow 后传统上可
脱离沙箱运行；若此时策略里有 `**/*.env` 的 deny-read，脱沙箱等于静默放开
`.env` 读取——secrets 泄漏给模型上下文。两层否决保证"升级"这条路径上任何一个
决策点忘掉 deny-read，另一个仍然拦住。

**测试**：`core/src/tools/sandboxing_tests.rs:150`
`deny_read_blocks_explicit_escalation_and_policy_bypass`（显式升级 + 策略 bypass
两种逃逸都断言被拦）；`:208` `windows_sandbox_env_preserves_denied_reads_or_rejects_unsupported_backend`。

**疤还是设计**：**疤**。commit 6e10142199（2026-05-28，Michael Bolin）
"fix: preserve deny-read sandboxing for safe commands (#23943)"，commit body 明说：
"Several shell execution paths treated known-safe commands or execpolicy `allow` rules
as sufficient to run outside the filesystem sandbox. That is not valid for read-capable
commands."——先发现了"安全命令逃逸沙箱"的漏洞，修复时一次性在两个决策点各加否决，
形成双层。

---

## E3. 工作区元数据（.git/.agents/.codex）写保护

**守的不变量**：writable root 再宽，`.git`/`.agents`/`.codex` 这些元数据路径
默认不可写（除非用户显式规则放行）。

**各层位置与校验方式**：

1. **策略谓词层** `protocol/src/permissions.rs:32-37` 定义
   `PROTECTED_METADATA_PATH_NAMES`；`:1005-1015` `can_write_path` 内部调
   `:1017 metadata_write_denial`——审批/预检阶段拒绝。
2. **内核 profile 层** `sandboxing/src/seatbelt.rs:584-587`：把
   `protected_metadata_names` 编码进 seatbelt 规则的 `(require-not (regex ...))`，
   由 macOS 内核强制执行——即使 Codex 进程内的策略判断被绕过（bug 或被诱导），
   内核 profile 仍然拒绝写。
3. **预执行 API（备用）** `protocol/src/permissions.rs:47`
   `forbidden_agent_metadata_write`（注释："should be blocked before execution"）。
   注意：本快照树内**无调用方**——它是暴露给 executor 侧的协议 API。

**防住的失败形态**：agent 写 `.git/config`（注入恶意 hook、改 remote URL 偷代码）、
写 `.codex`（改自己的权限配置完成提权持久化）。两层失守才漏：策略层 bug 放过 +
seatbelt profile 生成漏编码。

**测试**：`sandboxing/src/seatbelt_tests.rs:571`
`nested_protected_paths_cannot_be_bypassed_by_renaming_ancestors`（防 rename 祖先目录绕过）、
`:2310 seatbelt_protects_resolved_target_of_symlinked_metadata_directory`（防 symlink 绕过）、
`:2358 create_seatbelt_args_block_first_time_dot_codex_creation_with_metadata_name_regex`；
策略层 `protocol/src/permissions.rs:2698`（assert `.git/config` 不可写）。

**疤还是设计**：**设计**。0156b1e61（#19846，2026-04-28，策略层）与 0670d8971
（#19847，同日，Seatbelt 层）是同一 stack 的连续 PR；#19846 描述明说第 4 点是
"Add the Linux fallback setup needed before Linux enforcement lands later in the
stack"——分层是规划好的落地顺序。
**演化信号**：v0.160.0（更新）里名单已扩到 4 个，新增 `.aws`——威胁名单在持续长。

---

## E4. 网络出口的双重门

**守的不变量**：受限会话的网络访问必须被约束；任何组件失效时宁可断网也不可
静默放宽。

**各层位置与校验方式**：

1. **seatbelt profile 生成** `sandboxing/src/seatbelt.rs:346-348`：proxy 配置存在
   但推不出有效 loopback endpoint 时返回**空策略**（注释原文："Fail closed to
   avoid silently widening network access in proxy-enforced sessions."）；
   :351-354 managed network 活跃但无 proxy endpoint 同样 fail closed。
2. **proxy 判定链** `network-proxy/src/runtime.rs:576-620`：deny list 永远优先 →
   本地/私网 IP 分类（注释自承 "defense-in-depth"，并论证不能只靠字符串匹配
   `localhost`/`127.0.0.1`，因为 DNS rebinding 可以把域名解析到私网 IP）→ allowlist。
3. **协议契约层** `exec-server-protocol/src/protocol.rs:313-316`（注释/契约）：
   "`enforce_managed_network` is true and these details are absent, the executor
   must continue to fail closed. This preserves compatibility with older clients."
   ——executor（server 侧）在客户端没给细节时独立兜底，不信任对端版本。

**防住的失败形态**：sandbox profile 生成 bug 导致网络放行；proxy 挂了导致直连；
DNS rebinding 绕过域名 allowlist 打内网。三层各自覆盖不同的失守方式。

**测试**：network-proxy 有 policy 测试（`network-proxy/src/policy.rs` 一带）；
本条目未逐一核测试名，详见"待验证"。

---

## E5. 进程自加固（单模块多机制）

**守的不变量**：Codex 主进程不可被同用户进程 dump、调试、或注入动态库。

**机制**（`process-hardening/src/lib.rs`）：
- Linux :44-61：`prctl(PR_SET_DUMPABLE, 0)` + `setrlimit(RLIMIT_CORE, 0)`
  （:55 注释原文：'For "defense in depth," set the core file size limit to 0.'）
  + 清除 `LD_*` 环境变量；注释还说明 MUSL 静态链接本来就忽略 LD_PRELOAD，
  "but just to be sure, clear them here"——冗余是自觉的。
- macOS :83-100：`ptrace(PT_DENY_ATTACH)` + RLIMIT_CORE=0 + 清 `DYLD_*`。

**说明**：这是单模块内的多机制叠加，按严格标准算**边界条目**。其中
PR_SET_DUMPABLE 与 RLIMIT_CORE=0 防的都是 core dump 泄露，是两个独立内核机制
固化同一路径——符合"删掉一层另一层仍兜住"。失败即静默（进程照跑），所以值得收。

---

## E6. rollout 迁移的崩溃可恢复性

**守的不变量**（模块头注释原文，rollout_migration.rs:7-9）："we always leave
behind either the original legacy rollout or a recoverable paginated rollout"——
迁移任意时刻崩溃，磁盘上永远存在可恢复的历史。

**各层**：
1. staged JSONL canonicalize（先写临时文件，不动原件）；
2. SQLite 投影完成后 **verify**，再 atomically publish；
3. `.pending` journal：rollout 路径替换后 journal 持久存在，下次迁移靠它完成
   SQLite 恢复（:483-496 `recover_published_migration`，:998-1044）；
4. 写入排序屏障 `thread-store/src/local/live_writer.rs:333-338`（注释原文）：
   "SQLite is a rebuildable view. The flush barrier must win before projection
   starts so it can lag JSONL after failure, but can never get ahead of canonical
   history."——SQLite 可以滞后，绝不超前；
5. 防御性 lookup（live_writer.rs:315 注释）：teardown 后晚到的写直接失败，
   "Keep the lookup defensive so late writes fail after teardown"。

**测试**：`thread-store/src/local/rollout_migration_tests.rs`（崩溃恢复场景）。

**性质**：设计型崩溃恢复协议，典型 WAL 思路的多层固化。

---

## E7. history 的 call/output 配对不变量

**守的不变量**：发给模型的 history 里每个 function/custom call 必须有对应 output，
每个 output 必须有对应 call（history.rs:702-706 注释逐条列出三条不变量）。

**各层**：
1. **变更点增量维护**：`core/src/context_manager/history.rs:474`
   `remove_first_item` 删条目时顺带删 counterpart（注释："to keep the invariants
   intact without running a full normalization pass"）；
2. **构建 prompt 前全量归一化**：`history.rs:707-720` `normalize_history`
   （`ensure_call_outputs_present` + `remove_orphan_outputs` + 模态剥离），
   由 `for_prompt_annotated`（:400-405）在每次发请求前调用；
3. **测试基建钢丝层**：`core/tests/common/responses.rs:1664-1675`
   `validate_request_body_invariants`——mock server 对抓到的**每个** /responses
   请求体验证配对对称性（:709 注释："Enforce invariant checks on every request
   body captured by the mock."）。任何一次回归在任何一个集成测试里都会立刻炸。

**防住的失败形态**：孤儿 output 导致 API 400，或更糟——模型把孤儿 output 当成
既成事实继续推理（静默的上下文污染）。增量维护保证热路径不产生孤儿；全量归一化
兜住所有漏网路径（rollback、compaction、外部注入）；mock 校验防止未来重构破坏。

**性质**：设计。第三层放在测试基建里是特别值得注意的文化信号——
他们不止在生产代码里固化不变量，还让**整个测试套件**成为不变量的常驻执法者。

---

## E8. 跨 turn 不残留 pending server requests（app-server）

**守的不变量**：turn 生命周期结束后，不得残留悬挂的 server→client 请求
（否则会错配到下一个 turn）。

**各层**：`app-server/src/bespoke_event_handling.rs`
- :197 `EventMsg::TurnComplete` 处理器：`abort_pending_server_requests()`
  （注释："All per-thread requests are bound to a turn, so abort them."）；
- :1227 `EventMsg::TurnAborted` 处理器：同样 abort；
- :167 `EventMsg::TurnStarted` 处理器：**再 abort 一次**，注释原文：
  "While not technically necessary as it was already done on TurnComplete, be extra
  cautios and abort any pending server requests."（拼写错误为原文）。

**说明**：同一清理动作在三个事件处理器里各做一遍，作者明确知道冗余
（"not technically necessary"）但故意保留——这是最直白的 defense-in-depth 注释。
严格说三处调的是同一个方法（同一机制多次触发），算**弱分层**，但符合
"删掉一层其他层仍兜住"的判定。

---

## E9. StepSettings 的 TOCTOU 复核

**守的不变量**：managed requirements（approval policy allow-list、auto-review
强制要求）必须对**实际生效的** step settings 成立，而不只是对"选择时刻"成立。

**各层**：
1. 选择/构造时 `validate`（`core/src/session/step_settings.rs:318-340`）；
2. 异步解析后激活时 `revalidate`（`step_settings.rs:149-166`），调用点
   `step_activation.rs:384`（注释原文："Rechecks ordinary managed authorization
   after asynchronous resolution."）。

**防住的失败形态**：异步解析期间 managed 约束被刷新（如管理员推送新策略），
旧校验结果过期——TOCTOU。激活复核兜住这个窗口。

**注意**：step_settings.rs:153-156 的 TODO 自承两层校验**不完全重合**
（validate 不查继承的 approval 值）——分层但边界有缝隙，作者自己标了 TODO。

---

## 模式总结：多层 vs 单层的分界

**倾向多层固化的不变量**（全部满足"失守时静默且后果严重"）：

1. **跨信任边界的不可逆动作**：命令执行、文件写、网络出口。审批层 → execpolicy
   → guardian → 内核沙箱 → proxy，每层独立能兜；且到处可见 fail-closed 设计
   （解析失败、配置缺失、对端版本旧，一律按拒绝处理）。
2. **异步流的生命周期终止**：`response.completed` 缺失检测在每种传输实现 +
   消费主循环各自复制；compaction 路径也各带一份。流式系统"安静结束"是最危险
   的故障形态。
3. **崩溃一致性/持久性**：staging + verify + journal + 写入排序屏障。
4. **协议配对不变量**（call/output）：变更点增量维护 + 构建前全量归一 +
   测试基建逐请求校验。

**只做单层的**：

1. **渲染不变量**（stable/tail 边界、重复发射防护）：TUI 用构造式不变量
   （`StreamCore` 的 `emitted_stable_len <= enqueued_stable_len` 等，controller.rs:30-35
   注释逐条列出）+ 大量快照/属性测试钉死，**不做运行时多层兜底**。原因直观：
   渲染错位立即可见、可恢复，不是静默恶化。
2. 普通参数校验、配置解析、遥测归一化（如 analytics_hook_status 的
   Running→Failed 防御性归一，analytics/events.rs:1487）。

**分界假设**（有注释语言佐证）：失守后是否**静默恶化**。
"silently widening network access"（seatbelt.rs:347）、"silently grant those reads"
（sandboxing.rs:275 注释）、"poison materialization"（thread_history.rs:442 注释）
——这些注释里的共同词是 silently/poison。凡是"失守时静默且后果不可逆"的不变量
→ 多层 + fail-closed；失守即自爆（立刻可见、可重试）→ 单层 + 测试。

---

## 待验证（未进正文的猜测）

1. **E4 网络层的引入史**：未做 blame，无法判定设计还是疤。
2. **`forbidden_agent_metadata_write`（permissions.rs:47）的调用方**：树内无调用，
   可能供树外 executor 二进制使用；若确认无调用，E3 应降级为"2 层 + 1 死 API"。
3. **ItemCompleted exactly-once 的生产侧强制点**：thread_history.rs:441-442 注释
   声明"local producers emit ItemCompleted exactly once per item"，消费侧用
   SQLite `ON CONFLICT` upsert 防御性容忍重复。生产侧的 exactly-once 是否有代码
   强制（而非仅靠约定）未找到——若有，E10 成立（生产约定 + 存储容错）。
4. **turn.rs 的 OutputTextDelta/ReasoningDelta "without active item"**
   （turn.rs:2719/2761/2779/2834，`error_or_panic`）：debug 构建 panic、release 记
   日志降级（util.rs:93-99）。这是"开发期爆炸、生产期幸存"的执法器模式，多点
   应用同一机制——文化信号强，但每个点本身是单层。
5. **idle timeout 家族**：SSE（responses.rs:604）与 WS（responses_websocket.rs:707）
   都有 idle timeout，配置同源（provider 的 stream_idle_timeout）——同配置双
    enforcement 点，可归入 E1 家族或单列。
6. **network-proxy 的 DNS 解析缓存 TTL 与二次解析**：runtime.rs:581 一带的
   DNS-rebinding 防御是否还有第二处独立实现（如 exec-server 侧），未核。

## 假分层识别（明确排除）

1. **prologue 的"事件映射层"**：`core/src/client.rs:2309` 只记录 inference trace，
   不做错误注入——是观测层，不是拦截层。E1 的真实拦截层是 SSE/WS/turn 主循环。
2. **`command_execution_started` HashSet**（app-server/src/thread_state.rs:90 +
   bespoke_event_handling.rs:1097-1105）：approval/guardian/core 三个**生产者**
   共用**一个**去重闸门（注释：:1097-1099 "Reuse the same set to suppress that
   duplicate"）。测试 `command_execution_started_helper_emits_once`（:2650）。
   这是"多生产者-单闸门"，单层。
3. **WS 层 :718 与 :836**：同一函数内对 `Ok(None)` 和 `Message::Close` 的两个
   match 分支，是同层的两个 sub-case。
4. **`exec_policy.rs:495-505`**：追加 amendment 前对当前策略的 already_allowed
   复查——防重复写规则的本地优化，单层。
