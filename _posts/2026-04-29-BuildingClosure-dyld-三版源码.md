---
layout: post
title:  "一年后重读得物 BuildingClosure 优化"
date:   2026-04-29 00:00:00 +0800
categories: [iOS]
tags: [iOS, dyld, 启动优化, BuildingClosure, 完美哈希, lookup8]
---

2025 年 4 月，得物技术团队发了一篇文章[得物 iOS 启动优化之 Building Closure](https://mp.weixin.qq.com/s/xr43Xx-A3NT8lPGIii8pPA)，讲他们排查到 iOS 启动耗时中 `BuildingClosure` 阶段的一次诡异暴增。根因不是动态库、不是编译选项、不是打包脚本，而是新增的几个 ObjC 方法名，跟已有符号在 dyld 的完美哈希构造算法里撞了。改名之后，耗时恢复正常。

当时这篇文章在 iOS 圈子里传得挺广。结论有意思是一方面，更难得的是排查链路完整：Instrument → 堆栈定位 → dyld 源码编译 → 注入日志 → 对照实验。这套方法本身就有参考价值。

一年后，dyld 的新版源码还在 GitHub 上持续放出，我把这篇文章翻出来重新读了一遍。

我本地存了三版完整源码——2021 年的 852.2、2026 年 1 月发布的 1335、以及四月份刚拉的 1376.6（发文时的最新版）。把时间线补齐的反而是从 GitHub 上补查的几个中间版本，尤其是 1231.3（2024 年 9 月，约对应 iOS 18.0）。对照下来发现：Apple 针对这件事很可能悄悄做了至少两次修补，第一次落地的时间点比得物发文还早半年。

---

## BuildingClosure 在干什么

先花一点篇幅把 Building Closure 到底是什么说清楚。这部分得物文章有涉及，但我这里补充一些源码视角的细节，后面对比版本差异时会用到。

iOS 启动过程中，dyld 作为动态链接器负责加载所有 Mach-O 镜像、做符号绑定（bind）和基址修正（rebase）。这是一笔每次启动都要付的账。从 dyld3（iOS 13）开始，Apple 引入了一个优化：把第一次启动时算好的结果缓存下来，存成闭包文件（在 `Library/Caches/com.apple.dyld/` 下），后面再启动直接用。生成这个缓存的过程就叫 Building Closure。

Building Closure 里有一个环节是给所有 ObjC 符号建索引——selector、class、protocol，各一张哈希表。dyld4（iOS 15）重写之后，这个环节在 iOS 16 的 dyld-1042 里被封装进了 `PrebuiltObjC`：

```
App 镜像 → PrebuiltObjC::make()
         → 遍历所有 loader，收集 selector/class/protocol 信息
         → generateHashTables()
         → serialize 到闭包文件
```

`generateHashTables` 是耗时大头。它遍历所有 image 中注册的 class 和 protocol，逐一插入到哈希表结构里。Class 可能有重名（多个 dylib 中定义了同名类），所以用 MultiMap 而不是普通的 Map，逻辑上更重一些。

这个函数本身也经历了一轮演变：852.2 里还没有它（那时根本没有 `PrebuiltObjC`）；iOS 16/17 时代（dyld-1042 ~ 1165）它的签名是 `generateHashTables(RuntimeState& state)`；从 1231.3 起才变成无参形式：

```cpp
// PrebuiltObjC.cpp，1231.3 及之后（含 1335、1376.6）
void PrebuiltObjC::generateHashTables()
{
    generateClassOrProtocolHashTable(ObjCStructKind::classes, ...);
    generateClassOrProtocolHashTable(ObjCStructKind::protocols, ...);
}
```

得物原文贴出的代码正是带 `RuntimeState&` 参数的那一代——这个细节后面会用到。签名之下，变的是构造哈希表的那条路径。

---

## 四版 dyld 源码，一条逐渐收敛的线索

### dyld-852.2（2021）：完美哈希直接在构造函数里

852.2 对应 iOS 15，是 dyld4 的第一代，但源码目录还是 dyld3 时代的布局：没有 `PrebuiltObjC`，闭包构建的逻辑在 `dyld3/ClosureBuilder.cpp` 里。这个文件里直接调了 `make_perfect`——一个构造最小完美哈希表的函数：

```cpp
// ClosureBuilder.cpp
objc_opt::make_perfect(classNames, phash);              // 2020 行附近
objc_opt::make_perfect(closureDuplicateSharedCacheClassNames, phash); // 2215 行附近
objc_opt::make_perfect(closureSelectorStrings, phash);   // 2227 行附近
```

`make_perfect` 内部调用 `findhash`，而这个 `findhash` 有一个有点"怪异"的循环：

```cpp
// 852.2 里内联在 include/objc-shared-cache.h
for (si = 1; ; ++si)       // ← 注意：没有终止条件
{
    *salt = si * 0x9e3779b97f4a7c13LL;  // Golden Ratio 的 64 位表示
    initnorm(keys, *alen, blen, smax, *salt);
    rslinit = inittab(tabb, keys);
    if (rslinit == 0) {
        // 有 key 的 (a,b) 对撞了，换 salt 重试
        if (++bad_initkey >= RETRY_INITKEY) {
            // 如果 alen 或 blen 还有空间，翻倍再试
            // 否则继续……
        }
        continue;
    }
    // 找到了无冲突的 (a,b) 分布，检查能否构造完美哈希
    if (!perfect(tabb, tabh, tabq, smax, scramble, keys.count())) {
        // 构造完美哈希失败了，继续重试
        // （连续失败到 RETRY_PERFECT 且表已扩到上限时，会放弃返回 false）
        continue;
    }
    break;  // 成功了才退出
}
```

每次循环换一个 salt（`si * golden_ratio`），用这个 salt 给所有 key 重新算哈希，把每个 key 映射到一对 (a,b) 值。如果任何两个 key 的 (a,b) 完全相同，这一轮就失败，`si++` 再试。如果 (a,b) 全部唯一，再尝试用这些 (a,b) 构建一个无冲突的完美哈希表。

> **补充说明：关于 salt 和 golden_ratio**
> 这里的 `salt` 并非密码学中防破解的加盐，而是哈希函数的**初始种子（Seed）**或**扰动变量**。面对固定的字符串集合，引入 `salt` 相当于动态全盘切换哈希映射规则。每次失败后 `si++`，再乘以 64 位下的黄金分割率常数（`0x9e3779b97f4a7c13LL`），目的是确保即使 `si` 只增加了 1，也会在乘积的二进制位上产生剧烈翻转，实现整个符号集合哈希碰撞拓扑的“大洗牌”，从而尽可能快地撞到一个无冲突分布。

得物文章里记录的 31 次 → 92 次的循环次数变化，就是这个 `si` 的计数。新增的方法名改变了字符串集合的哈希分布特征，`lookup8`（Bob Jenkins 1997 年发表的哈希函数）在某个 salt 范围内找不到能让所有 (a,b) 对无冲突的参数，导致 `si` 一路涨到 92 才命中。

关键问题是：**这段代码跑在 App 首次启动时**。`ClosureBuilder` 在用户设备上执行，而不是在 Apple 的构建机器上。对于一个靠重试收敛的算法，输入稍微变一点，耗时就可能从几十次跳到上百次——(a,b) 碰撞这条路径上没有实用的上界。

### dyld-1042 ~ 1165（iOS 16–17）：架构换了，算法没换

iOS 16 的 dyld-1042 引入了 `PrebuiltObjC`，把 ObjC 索引构建封装成独立组件。但封装归封装，算法没换——`generateHashTables` 内部依然在为类表和 selector 表调 `make_perfect`：

```cpp
// dyld-1165.3，PrebuiltObjC.cpp
if ( !closureSelectorStrings.empty() ) {
    objc::PerfectHash phash;
    objc::PerfectHash::make_perfect(closureSelectorStrings, phash);  // 还是它
    ...
}
```

得物踩中的正是这一代。两个证据能对上：他们 Instrument 抓到的堆栈是 `dyld4::PrebuiltObjC::generateHashTables(dyld4::RuntimeState&)`——带 `RuntimeState&` 参数的签名只存在于 1042 ~ 1165 这几版；他们原文贴出的 `generateHashTables` 代码片段，和 1165.3（2024 年 8 月，iOS 17 末代）的实现逐字吻合。

也就是说，2025 年 4 月得物发文时，他们用户手里跑着的 iOS 16/17 设备，走的还是 `findhash` 那条没有上界的路径。

### dyld-1231.3（2024-09，约 iOS 18.0）：转折点

1231.3 于 2024 年 9 月 24 日打上 tag，约对应 iOS 18.0。**设备端 Closure 构建不再走 `make_perfect`，是从这一版开始的**——不是更晚的版本。

`PrebuiltObjC::generateHashTables` 改调 `generateClassOrProtocolHashTable`，这个函数用 `ObjectMapTy::insert()` 来建表。`ObjectMapTy` 本质是 `MultiMap`（`common/Map.h`），一个用开放寻址 + 二次探测的常规哈希表，不是完美哈希。这条路径从 1231.3 一直延续到 1335，没再变过：

```cpp
// Map.h，MultiMap::insert（引用自 1335）
uint64_t hashIndex = GetHash::hash(v.first, state) & (hashBuffer.count() - 1);
uint64_t probeAmount = 1;
while (true) {
    uint64_t nodeBufferIndex = hashBuffer[hashIndex];
    if (nodeBufferIndex == SentinelHash) {
        // 找到空位，插入
        break;
    }
    if (IsEqual::equal(nodeBuffer[nodeBufferIndex].key, v.first, state)) {
        // 已存在（MultiMap 会追加）
        ...
    }
    hashIndex += probeAmount;      // 二次探测
    hashIndex &= (hashBuffer.count() - 1);
    ++probeAmount;
}
```

表满了就触发 rehash：分配两倍大小的新表，把所有节点重新散列进去（最坏情况 O(n²)）。

为什么这算 Apple 的第一次修补？它动的不是哈希碰撞本身——碰撞在常规哈希表里照样存在。它动的是「构造开销」的波动性：从不可控（`for(;;)` 重试）变成可控（二次探测步数跟负载因子挂钩）。碰撞还是会影响性能，但**最坏情况的边界是已知的**。

但 `make_perfect` 并没有死。以 1335 为准看，它还在 `common/PerfectHash.cpp` 里（806 行），只是不再被 `PrebuiltObjC` 调用——调用方只剩 Shared Cache Builder（代码都在 `BUILDING_CACHE_BUILDER` 宏守卫内）和单元测试。那个构建工具跑在 Apple 的构建机器上，不在用户设备上。

注意时间点：这一版比得物发文早了半年多。得物排查的时候，Apple 其实已经修完了；只是 iOS 17 及更早的设备上还跑着旧路径，所以他们观测到的症状依然真实。

### dyld-1376.6（2026-04）：彻底切割

1376.6 是四月份刚发的版本。这一版的改动不大，但意图很明确。

`common/PerfectHash.cpp` 从 806 行砍到了 179 行，只剩 `lookup8`。

`make_perfect`、`findhash`、`perfect`、`augment`——所有跟完美哈希构造相关的函数——全部搬进了 `cache_builder/PerfectHashWriter.cpp`。这是一个新增文件，放在 `cache_builder/` 目录下，而这个目录只在 Apple 构建 dyld 共享缓存时编译。也就是说，**在用户设备上运行的 dyld 二进制里，`findhash` 的那个重试循环已经不存在了**。

同时 `cache_builder/PerfectHashWriter.h` 里的 `PerfectHash` 结构体也变了：tab 的存储从 `dyld3::OverflowSafeArray<uint8_t>` 改成了 `std::vector<uint8_t>`——一个是 dyld 自己的内存管理，一个是标准库，进一步说明了它跟 dyld 运行时的切割关系。

拉一张表对比：

| | dyld-852.2 (2021-10) | dyld-1165.3 (2024-08) | dyld-1231.3 (2024-09) | dyld-1376.6 (2026-04) |
|---|---|---|---|---|
| 约对应系统版本 | iOS 15 / macOS 12 | iOS 17 末代 | iOS 18.0 | 发文时最新，随系统版本待定 |
| 设备端 Closure 构建用 | `make_perfect` + `findhash` | PrebuiltObjC 架构，仍是 `make_perfect` | Map/MultiMap | Map/MultiMap |
| `make_perfect` 所在位置 | `include/objc-shared-cache.h`（内联在头文件里） | `common/PerfectHash.cpp`（841 行） | `common/PerfectHash.cpp`（808 行，不再被 Closure 路径调用） | `cache_builder/PerfectHashWriter.cpp`（仅构建工具） |
| `findhash` 是否在设备端 | 是 | 是 | 是（但不再被 Closure 调用） | 否 |

Apple 分了两步：第一步换个不那么危险的算法，第二步把旧算法物理隔离到离线工具里。从代码路径变化看，这更像两次有意识的架构调整，而不只是一次 patch。得物踩中的正是第一步之前的最后一代——他们发文时修复已经随 iOS 18 落地，但旧系统设备上的症状还在，所以他们的排查和修法依然成立。

---

## lookup8 和改名为什么有效

有一个问题还没回答：为什么会撞？

dyld 的哈希函数是 `lookup8`，Bob Jenkins 在 1997 年发表的。函数签名是 `lookup8(k, length, level)`——三个参数分别是 key 的字节数组、key 长度、和一个初始哈希值。内部每 24 字节一批处理，每批喂进一个叫 `mix64` 的三值混合宏：

```cpp
// lookup8 的每轮处理：把 k[0..7], k[8..15], k[16..23] 分别加载到 a, b, c
a += (k[0] + (k[1]<<8) + ... + (k[7]<<56));
b += (k[8] + (k[9]<<8) + ... + (k[15]<<56));
c += (k[16] + (k[17]<<8) + ... + (k[23]<<56));
mix64(a, b, c);  // 12 轮移位和异或，让三个值的每个 bit 互相扰动
```

`mix64` 是 `lookup8` 内部的扩散步骤，不是独立哈希函数。`lookup8` 的设计目标是让每个输入 bit 都会影响每个输出 bit（雪崩效应），实践里通常能得到比较均匀的分布；但这并不等于对任意输入集合都有严格数学保证。**而完美哈希需要的不是「分布均匀」，而是所有 key 的 (a,b) 对两两不同**。这是两个完全不同的要求。

打个比方：`lookup8` 保证的是「把每把钥匙随机撒在地板上」，而完美哈希需要的是「每把钥匙恰好落在不同的方格」。钥匙越多、分布越不巧，找到合适的 salt 让它们全部分开的难度就非线性增长。

得物新增的几个 ObjC 方法名，改变了整个字符串集合的碰撞图景——两个之前被某个 salt 分得很开的字符串，在新 salt 下可能落在同一个 (a,b) 对。`findhash` 就得接着试，直到撞到一个能用的 salt。

得物记录的那 92 次重试意味着什么？意味着这个出了问题的字符串集合，在 salt 从 32 到 92 的范围里一直找不到无冲突的 (a,b) 分布——一个宽度约 60 个 salt 迭代的「死区」。改名之后，字符串集合的哈希分布特征完全变了，这个特定的死区不存在了，`findhash` 在第 31 次就能收敛。

改名之所以有效，是因为 `lookup8` 的输出对输入内容高度敏感。两个字符串哪怕只差一个字符，哈希值也完全不同。所以改一个方法名，等于把它在 (a,b) 空间的位置移动到了完全不同的坐标——整个字符串集合的碰撞拓扑被重新洗牌。

在 1231.3 及之后版本的 Map/MultiMap 路径下，这个原理同样成立：字符串集合的哈希分布影响二次探测的步数。只不过退化机制从「si 数到几十上百才停止」变成了「探测几步找到空位」，波动幅度小得多，但仍然可观测。

---

## 怎么判断 BuildingClosure 是不是你的瓶颈，以及能做什么

### 先看数据

Instruments → System Trace，启动后搜 BuildingClosure 阶段的耗时。对比两组数据：

- **首次启动**（或重启后首次、版本更新后首次）——这时 BuildingClosure 会完整执行
- **二次启动**——这时 dyld 直接读缓存的 .dyld 文件，BuildingClosure 基本不耗时

如果首次启动和二次启动的差值超过你启动总耗时的 20%，这个阶段值得关注。这里的 20% 是工程上的经验阈值，不是通用标准，按你们业务的启动预算调整即可。

### 三条路径，按性价比排

**1. 减少 ObjC 符号总量——治本，但需要长期投入**

BuildingClosure 的工作量直接跟符号数量挂钩。清理没用的方法、合并功能重复的 category、删除已废弃的代码路径。不需要一下子做完，但每次迭代清一点，启动时长会线性受益。

**2. CI 上做启动耗时回归检测——防住未来**

加一条 CI 流程：在指定设备上跑冷启动并把耗时写到基线文件。每次 MR 触发，超过基线 5% 就报警。这个 5% 同样是常见经验值，项目体量、设备噪声和发布节奏不同，阈值也要跟着调。得物的故事里，如果当时有这个机制，200ms 的增长不会靠人工偶然发现。

可以配合 `xcodebuild` 或 `xcrun simctl` 在模拟器上做自动化。关键是把环境变量固定好（同一台 CI 机器、同一个 OS 版本、关闭其他进程），否则数据波动会淹没真正的回归信号。

**3. 改名——精准打击，但成本高**

只有当 Instrument 已经明确指向某个新增的大规模类/方法集合引发了 BuildingClosure 退化时，改名才值得考虑。改名会带来维护成本，而且你没法提前知道改哪个名有效——这取决于 `lookup8` 在全体符号集合上的表现，不是单个名字的事。

得物团队之所以能做，是因为他们当时已经搭了一套 dyld 编译 + 日志注入的环境，可以精确打印出碰撞字符串和循环次数。没有这个环境的开发者，优先走前两条路径。

还有个前提：完美哈希这条路径只存在于 iOS 17 和更早的系统。用户大部分在 iOS 18+ 的话，算法风险 Apple 已经兜底了，上面第 3 条基本用不上。

### 如果想自己搭分析环境

dyld 的源码在 `apple-oss-distributions/dyld`，直接拉 tag 对应的 release tarball。跟 BuildingClosure 相关的几个文件：

- `common/PerfectHash.cpp`——`lookup8` 哈希函数和完美哈希构造（1042 ~ 1335；852.2 里这些代码内联在 `include/objc-shared-cache.h`；1376.6 起这个文件只剩 `lookup8`）
- `dyld/PrebuiltObjC.cpp`——设备端 Closure 构建路径；`make_perfect` 旧实现见 1165.3 及更早，MultiMap 新实现见 1231.3 及之后
- `common/Map.h`——Map/MultiMap 的二次探测插入和 rehash 逻辑
- `cache_builder/PerfectHashWriter.cpp`——1376.6 新增，完美哈希构造逻辑（仅 cache builder 目录）

得物的做法是在 `inittab` 里加打印、输出 si 值和冲突字符串，然后编译 dyld，在模拟环境里对比新老版本的输出。方法直接，但需要花时间搭模拟环境和注入日志，不是五分钟跑个脚本的事。

---

## 串起来看：Apple 到底改了什么

四个版本摊开，修补路径就很清楚了。

852.2 时代，设备端的 Closure 构建直接用 `findhash` 的重试循环构造完美哈希。这个算法的收敛速度绑在输入字符串集合的哈希分布上——分布顺，几十次就收敛；分布不顺，`si` 可以一直涨下去。iOS 16 引入 `PrebuiltObjC` 重新组织了代码，但算法原封不动地带了过来。得物遇到的就是这一代的极端情况：新增的几个方法名改变了字符串集合在 `lookup8` 下的碰撞图景，`si` 从 31 一路跑到 92，对应启动阶段多了 200ms。

1231.3（约 iOS 18.0）做了一个关键决定：设备端不再构造完美哈希。`PrebuiltObjC` 改用 `MultiMap`——标准开放寻址哈希表，冲突时二次探测，表满时 rehash。性能仍然受哈希分布影响，但最坏情况的边界是已知的（rehash 的代价可分析），不再是 `for(;;)` 重试。这一步解决的是**波动范围不可控**。`make_perfect` 此时还留在 `common/` 里，但调用方只剩 Shared Cache Builder——跑在 Apple 构建机器上的离线工具，不在用户设备上。

1376.6 把切割做彻底了。`make_perfect`、`findhash`、`perfect`、`augment` 全部从 `common/` 搬进 `cache_builder/`。这个目录只在构建 dyld 共享缓存时编译，用户设备上的 dyld 二进制不再包含 `findhash` 的重试循环。数据结构也从 dyld 自有的 `OverflowSafeArray` 换成了 `std::vector`——切割的不只是代码位置，还有运行时依赖。到这一步，残留风险也清掉了。

两步加起来，本质是把一段「输入稍有变化、耗时可能跳变数倍」的代码路径，从用户设备启动关键路径上拿掉了。不是修了一个 bug，也不是优化了一个热点——是把构造完美哈希这个决策从运行时移到了构建时。

第一步落地得无声无息。2024 年 9 月随 iOS 18 上线，没有任何 release note 会写这种事；半年多得物发文，讲的还是旧路径上的故事——他们和绝大多数用户当时踩的是 iOS 17。得物这篇文章，恰好成了那次静默修复的反面注脚：修复前的最后一代，有多疼。

回头看，这件事有两个层面的教训：

**对于 dyld 这种跑在数亿台设备上的基础设施，算法的「最坏情况可控」比「平均情况更优」重要得多。** `findhash` 的重试循环在大多数输入上收敛很快——但这不构成安全保证。一旦输入跨过某个阈值，退化就是跳变，不是渐变。`MultiMap` 平均性能可能不如完美哈希（查询多一次探测），但它的退化曲线是平滑的——输入再差，rehash 的代价也算得出来。做系统软件的人对这一点不会陌生，但得物的案例给了它一个精确到 `si` 计数的注脚。

**另一个是排查链路本身的价值。** 如果没有从 Instrument → 堆栈定位 → dyld 源码编译 → 注入日志 → 对照实验的完整链路，这个 200ms 大概率会作为「系统波动」被接受，一直留在线上。得物那篇文章最值得被记住的不是改了什么名字，而是怎么找出来的。方法论可以复用，具体结论会过时。

---

* 本文涉及的 dyld 源码版本：dyld-852.2（2021-10）、dyld-1042.1 / 1165.3（iOS 16–17 时代）、dyld-1231.3（2024-09）、dyld-1335（2026-01）、dyld-1376.6（2026-04）。其中 852.2 / 1335 / 1376.6 为本地完整源码，其余版本的关键文件来自 [apple-oss-distributions/dyld](https://github.com/apple-oss-distributions/dyld)。
* 得物技术原文：《得物 iOS 启动优化之 Building Closure》，2025-04 发表于微信公众号**得物技术**。
