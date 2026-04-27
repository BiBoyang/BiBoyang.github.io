---
layout: post
title: "GitHub Actions 每日自动测试：从 schedule 踩坑到跑通"
date: 2026-04-28 02:00:00 +0800
categories: [CI/CD, GitHub Actions, Swift, Rust]
---

我在维护两个项目，一个是 Swift 写的 macOS CLI 工具（ForgeLoop），另一个是 Rust 写的微信 Bot（AMClaw）。开发阶段每次 push 都跑全量测试太费时间，而且有些测试在本地 commit 之前已经跑过了，CI 再跑一次完全重复。

所以我开始研究怎么让 CI 更聪明一点——不是每次 push 都跑，而是每天凌晨检查一次：如果过去 24 小时有代码更新，就自动跑全量测试；没有就跳过。这样既能保证软件质量，又能把 CI 资源用在刀刃上。

GitHub Actions 的 `schedule` 事件配合 cron 表达式看起来能满足这个需求。但在选 runner 的时候踩了一个坑：self-hosted runner 要求机器在 schedule 触发时刻必须在线，如果关机任务就丢了。GitHub-hosted runner（`ubuntu-latest`、`macos-latest`）不存在这个问题。

决定用 GitHub-hosted runner。

## 需求背景

我的项目是 Swift Package Manager 管理的 macOS CLI 工具，依赖结构如下：

```
ForgeLoop/           ← 主仓库
├── Package.swift    ← swift-tools-version: 6.0
├── Sources/
└── Tests/

ForgeLoopTUI/        ← sibling 依赖
├── Package.swift
└── Sources/
```

`ForgeLoop/Package.swift` 里通过 `.package(path: "../ForgeLoopTUI")` 引用 sibling 目录的依赖。本地开发没问题，但放到 CI 上，两个仓库的相对位置需要自己处理。

测试量不算小，每次 push 都跑全量测试要几分钟。开发阶段我已经跑过单元测试了，没必要每个 commit 都再跑一次。

所以需求很明确：

- Push 到 main 分支时，跑一次快速验证（编译 + 测试）
- 每天凌晨检查过去 24 小时有没有新提交，有则跑全量测试，没有则跳过
- PR 时也要跑测试

## 方案设计

GitHub Actions 支持多种触发事件，我配了四个：

```yaml
on:
  schedule:
    - cron: '0 18 * * *'     # UTC 18:00 = 北京时间凌晨 2:00
  workflow_dispatch:         # 手动触发
  push:
    branches: [main]
  pull_request:
    branches: [main]
```

其中 `schedule` 需要配合一个前置 job 做"24 小时变更检测"：

```yaml
jobs:
  check-changes:
    runs-on: ubuntu-latest
    outputs:
      has_changes: ${{ steps.check.outputs.has_changes }}
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            const now = new Date();
            const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            const { data: commits } = await github.rest.repos.listCommits({
              owner: context.repo.owner,
              repo: context.repo.repo,
              since: yesterday.toISOString(),
              per_page: 1
            });
            core.setOutput('has_changes', commits.length > 0);
```

测试 job 的条件这样写：

```yaml
  test:
    needs: check-changes
    if: ${{ github.event_name != 'schedule' || needs.check-changes.outputs.has_changes == 'true' }}
```

意思是：schedule 事件要检测结果，其他事件直接跑。这条 `if` 就是核心逻辑，没有它的话 schedule 事件每天空跑浪费 Actions 分钟数。

## 踩坑记录

### 坑一：actions/checkout 的 path 不支持上级目录

我想用 `actions/checkout@v4` 来拉取 sibling 依赖：

```yaml
- uses: actions/checkout@v4
  with:
    repository: BiBoyang/ForgeLoopTUI
    path: ../ForgeLoopTUI        # ← 不行
```

报错：`Repository path '/Users/runner/work/ForgeLoop/ForgeLoopTUI' is not under '/Users/runner/work/ForgeLoop/ForgeLoop'`。

`actions/checkout` 的 `path` 参数强制限制在工作目录内部，不支持 `../` 这种上级路径。改用 raw `git clone` 解决：

```yaml
- run: |
    cd ..
    git clone https://github.com/BiBoyang/ForgeLoopTUI.git
```

### 坑二：macos-latest 的默认 Swift 版本

我的 `Package.swift` 指定了 `swift-tools-version: 6.0` 和 `swiftLanguageModes: .v6`。本地用的是 Xcode 16 + Swift 6.3.1，编译没问题。推到 GitHub 后 Build 直接失败。

原因：`macos-latest` runner 预装的 Xcode 版本随时间变化，默认可能还是 Xcode 15 + Swift 5.9，不支持 Swift 6 语法。

解决方式是显式选择 Xcode：

```yaml
- name: Select Xcode
  run: |
    for xcode in /Applications/Xcode_16.3.app /Applications/Xcode_16.2.app \
                 /Applications/Xcode_16.1.app /Applications/Xcode_16.0.app \
                 /Applications/Xcode_16.app; do
      if [ -d "$xcode" ]; then
        sudo xcode-select -s "$xcode"
        break
      fi
    done
```

GitHub 的 macOS runner 目前（2026年4月）有 Xcode 16，但默认选中的不一定是最新版。建议先 `ls /Applications/ | grep Xcode` 确认有哪些可用版本，再写选择逻辑。按版本号从高到低试，确保拿到最新的。

### 坑三：测试失败看不到日志

一开始我把 `swift test` 的输出直接打印，但 GitHub Actions 的 web UI 里日志太长会被截断，找错误信息很费劲。后来改成把输出同时 tee 到文件，再用 `tail` 打印末尾：

```yaml
- run: swift test 2>&1 | tee test.log

- if: always()
  run: tail -200 test.log
```

`2>&1` 把 stderr 也捕获到，`if: always()` 保证即使测试失败也会执行日志展示步骤。失败时还可以用 `actions/upload-artifact@v4` 把日志文件上传，方便下载查看。

## 最终工作流

```yaml
name: Nightly Tests

on:
  schedule:
    - cron: '0 18 * * *'     # 北京时间凌晨 2:00
  workflow_dispatch:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  check-changes:
    runs-on: ubuntu-latest
    outputs:
      has_changes: ${{ steps.check.outputs.has_changes }}
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            const now = new Date();
            const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            const { data: commits } = await github.rest.repos.listCommits({
              owner: context.repo.owner,
              repo: context.repo.repo,
              since: yesterday.toISOString(),
              per_page: 1
            });
            core.setOutput('has_changes', commits.length > 0);

  test:
    needs: check-changes
    if: ${{ github.event_name != 'schedule' || needs.check-changes.outputs.has_changes == 'true' }}
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4

      - run: |
          cd ..
          git clone https://github.com/BiBoyang/ForgeLoopTUI.git

      - run: |
          for xcode in /Applications/Xcode_16.3.app /Applications/Xcode_16.2.app \
                       /Applications/Xcode_16.1.app /Applications/Xcode_16.0.app \
                       /Applications/Xcode_16.app; do
            if [ -d "$xcode" ]; then
              sudo xcode-select -s "$xcode"
              break
            fi
          done

      - run: swift --version && xcodebuild -version

      - run: swift build

      - run: swift test 2>&1 | tee test.log

      - if: always()
        run: tail -200 test.log 2>/dev/null
```

## 另一个项目：Rust 几乎没踩坑

Swift 项目跑通之后，我又给另一个 Rust 项目配了同样的 CI。结构简单得多：

```
AMClaw/
├── Cargo.toml    ← edition: "2021"
├── src/
└── tests/
```

没有 sibling 依赖，没有平台限制，没有 Xcode 版本问题。`ubuntu-latest` 直接跑，用 `dtolnay/rust-toolchain@stable` 一步装好 Rust 工具链。

工作流的核心部分：

```yaml
  test:
    needs: check-changes
    if: ${{ github.event_name != 'schedule' || needs.check-changes.outputs.has_changes == 'true' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - run: cargo build
      - run: cargo test
```

`check-changes` 和 `schedule` 的逻辑完全复用，只是 `test` job 从 `macos-latest` 换成了 `ubuntu-latest`，步骤从 "clone sibling + 选 Xcode + swift build" 变成了 "checkout + 装 Rust + cargo test"。

Rust 的测试也跑通了，同样的 schedule 事件、同样的 24h 变更检测、同样的 push/PR 触发，但整个过程没有任何报错，一次通过。

这说明 CI 的复杂度差异主要来自语言和平台生态，而不是 schedule 机制本身。Swift 项目 sibling 依赖 + macOS + Xcode 版本三重叠加，Rust 项目 cargo + ubuntu 一路平坦。

但基础 CI 跑通之后，我又给 Rust 项目加了三个检查项，这次反而踩了不少坑。

## CI 不只是跑测试：fmt、clippy、audit

`cargo test` 只能保证代码逻辑正确，但代码风格、lint 警告、依赖安全这些也需要把关。我把三个步骤加进 CI：

```yaml
- run: cargo fmt -- --check
- run: cargo clippy --all-targets --all-features -- -D warnings
- run: cargo audit
```

执行顺序有讲究：fmt → clippy → audit → build → test。前面挂了后面不跑，避免浪费时间。

### cargo fmt：代码风格不一致

第一次跑 `cargo fmt --check` 就报了两处 diff：

```
Diff in src/chat_adapter/mod.rs:2006
-        Ok(Some(status)) => format!("任务当前状态为 {}，不允许人工归档: {task_id}", status.status),
+        Ok(Some(status)) => format!(
+            "任务当前状态为 {}，不允许人工归档: {task_id}",
+            status.status
+        ),
```

平时本地跑 `cargo build` 不会管格式，`cargo fmt --check` 是只读检查，不自动修改。本地执行 `cargo fmt` 修复后提交，问题解决。

### cargo clippy：sort_by 写法过时

`cargo clippy --all-targets --all-features -- -D warnings` 把 warning 提升为 error，结果 `trace_eval.rs` 里三处 `sort_by` 被 clippy 建议改成 `sort_by_key`：

```
error: consider using `sort_by_key`
   --> src/bin/trace_eval.rs:760:9
    |
760 |         pairs.sort_by(|left, right| right.1 .0.cmp(&left.1 .0));
    |         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    |
help: try
    |
760 -         pairs.sort_by(|left, right| right.1 .0.cmp(&left.1 .0));
760 +         pairs.sort_by_key(|right| std::cmp::Reverse(right.1 .0));
```

按 clippy 提示改就行。`-D warnings` 这个参数比较严格，本地开发时 `cargo clippy` 有 warning 不会报错，CI 里一开就发现一堆。好处是代码风格统一，代价是第一次配置 CI 时可能要修不少历史债务。

### cargo audit：依赖安全漏洞

`cargo audit` 不是 Rust 自带工具，需要先 `cargo install cargo-audit --locked`。它扫描 `Cargo.lock` 里的依赖，对比 RustSec 安全数据库。

第一次跑报了三个漏洞：

```
Crate:     rustls-webpki
Version:   0.103.10
Title:     Reachable panic in certificate revocation list parsing
Solution:  Upgrade to >=0.103.13

Crate:     rustls-webpki
Version:   0.103.10
Title:     Name constraints for URI names were incorrectly accepted
Solution:  Upgrade to >=0.103.12

Crate:     rand
Version:   0.9.2
Warning:   unsound
Title:     Rand is unsound with a custom logger using `rand::rng()`
```

这些都是间接依赖，通过 `reqwest` 引入的。解决方案是 `cargo update`，让 Cargo 自动解析并升级到兼容的最新版本：

```bash
cargo update
```

更新后 `Cargo.lock` 变了 98 处，`cargo audit` 再次跑就通过了。再跑一遍 `cargo test` 确认没有破坏功能，提交 `Cargo.lock` 即可。

## 几个值得注意的点

**schedule 的首次运行有延迟。** GitHub 的 cron 不是精确到秒触发，通常有几分钟到十几分钟的偏差，这属于正常行为，不必纠结。

**私有仓库要注意 Actions 分钟数。** `macos-latest` 的消耗是 `ubuntu-latest` 的 10 倍。我这里的 24h 变更检测用的是 ubuntu-latest（便宜），只有真正跑测试时才切换到 macos-latest，算是一个小的成本优化。如果是公开仓库，Actions 对公开仓库免费，不用考虑这个。

**self-hosted runner 不是不能用，但要确保在线。** 如果你确实需要特定硬件环境（比如 iOS 真机测试），self-hosted 是唯一选择，但要配好机器不睡眠，或者定时唤醒。`sudo pmset -c sleep 0` 可以让 Mac 在接通电源时不睡眠。

** sibling 依赖用 `git clone` 比 `actions/checkout` 更灵活。** 如果你的依赖关系更复杂（比如三个 sibling 仓库互相引用），actions/checkout 的 path 限制会成为问题，直接用 git 命令更可控。

## 验证方式

推送到 GitHub 后，去仓库的 Actions 标签页可以看到运行记录。`check-changes` job 会打印 `Last 24h commits: X, run tests: true/false`，可以直观确认检测逻辑是否正确。

手动触发 workflow_dispatch 可以验证整个测试流程本身是否跑通，不受 schedule 定时限制。
