---
layout: post
title:  "从 ENTRY 到 MSG_ENTRY：objc_msgSend 的热点入口优化解析"
date:   2025-10-28 23:32:53 +0800
categories: [iOS, Objective-C, Runtime]
tags: [iOS, Objective-C, runtime, objc_msgSend, performance]
---


这篇文章想聊一个 `iOS` 系统里非常有意思的**空间换时间优化**。

重新阅读 [objc4-950](https://github.com/apple-oss-distributions/objc4) 的源码时，我注意到 `objc_msgSend` 是纯汇编实现的。通过[汇编代码](https://github.com/BiBoyang/How_To_Hook_msg_send/blob/main/objc-msg-arm64.s#L532-L774)可以看到这样一段定义：


```
MSG_ENTRY _objc_msgSend
```

这里的 `MSG_ENTRY` 是什么意思呢？继续在文件里搜索 `MSG_ENTRY`，可以找到这样一个宏：
```
.macro MSG_ENTRY /*name*/
	.text
	.align 10
	.globl    $0
$0:
.endmacro
```
把它展开之后，就是：
```
.text
.align 10
.globl _objc_msgSend
_objc_msgSend:
```
这里本质上是给 `_objc_msgSend` 定义了一个全局可见的汇编入口符号。这样外部代码可以像调用普通函数符号一样去引用它，但它的实现本身仍然是一段纯汇编逻辑。



## MSG_ENTRY 的引入

如果看过老版本 `objc_msgSend` 源码，应该会注意到，新版本在这里用 `MSG_ENTRY` 替换掉了 `ENTRY`，而且这个变化几乎就是专门给 `objc_msgSend` 准备的，其他函数大多还是继续用 `ENTRY`。

老版本里，`objc_msgSend` 使用的就是普通的 `ENTRY` 宏。所以我第一反应就是：这大概率不是随手改的，而是一次专门针对 `objc_msgSend` 热点入口做的优化。

我们都知道 `objc_msgSend` 对整个 `iOS` 世界有多重要。它的调用频率高得可怕，哪怕只多浪费 1 个时钟周期，乘上巨大的调用次数之后，都会变成非常可观的损耗。

所以系统在这里显然做了一次非常典型的“空间换时间”优化。



## CPU 的读取机制

对于 `iPhone` 使用的 `ARM` 芯片来说，执行代码并不是“执行一条、读取一条”，而是按块取指。这个“块”通常就对应 `Cache Line`（缓存行）的大小。在现代 Apple 的 `ARM64` 平台上，`Cache Line` 通常是 `64` 字节，而指令长度固定是 `4` 字节。

也就是说，理想情况下，`CPU` 一次取指就能把 `16` 条指令（`64 ÷ 4 = 16`）装进来。

那么我们假设一种情况：`objc_msgSend` 的入口地址刚好落在一个 `Cache Line` 的末尾，比如最后 `4` 个字节。这样 `CPU` 第一次取指时，可能只拿到入口的第一条指令；如果后面的热点路径落到了下一条 `Cache Line`，那前端就还得继续去取下一块。这种布局虽然不一定每次都会带来明显损耗，但它会增加热点入口跨 `Cache Line` 的概率，也就增加了额外取指开销和 `i-cache` 冲突的可能性。

反过来看，如果把函数入口尽量安排在一个稳定的对齐边界上，那么 `objc_msgSend` 最前面那段最关键的快路径，就更容易完整地落在同一条 `Cache Line` 里。这样 `CPU` 一次取指就更有机会把最核心的那段逻辑整体装进来，取指行为也会更稳定。

## 1024 字节的对齐

`MSG_ENTRY` 的宏里使用的是 `.align 10`，它表达的其实是**入口地址的对齐约束**：按 `2^10 = 1024` 字节边界对齐。而普通函数（以及老版本的 `objc_msgSend`）使用的 `ENTRY` 宏是 `.align 5`，也就是按 `32` 字节对齐。

看到这里,可能会有一个疑问:**Cache Line 只有 64 字节,那系统搞一个 1024 字节（1KB）对齐,这也读不起啊?**


确实不可能“一次读 1024 字节”，但这里真正想优化的也不是“让 CPU 一次把 1KB 全读完”，而是**尽量保证前面最关键的那 64 字节稳定地落在同一条 `Cache Line` 里**。

转回 `CPU` 视角，`1024 = 0x400`，二进制是 `100 0000 0000`。这意味着 `objc_msgSend` 的入口地址**低 10 位全是 0**。

`CPU` 在访问 `i-cache` 时，会使用地址中的某些位去做索引和定位。这里低 `10` 位全部清零的意义，不是某一种特定处理器会“更方便匹配”，而是让 `objc_msgSend` 的入口落点更稳定、更可预测。即使不同代际的 `CPU` 在细节上会有差异，这种“大粒度对齐”依然能够降低入口地址低位的随机性，从而尽量减少热点前缀落在不理想边界上的概率。

## Fast Path

我们应该知道 `objc_msgSend` 是整个 `iOS` 底层的最常用的函数:它是一个**极度优化**的函数，它的**快速路径（Fast Path）**——也就是 `99%` 的情况下执行的那段代码—— **非常非常短** ！


我们看下 `objc_msgSend` 的核心代码

```
	cmp	p0, #0			// 1. 判空 (4字节)
	b.le	LNilOrTagged		// 2. 跳转 (4字节)
	ldr	p13, [x0]		// 3. 读 isa (4字节)
	and	p16, p13, #ISA_MASK	// 4. 处理 isa (4字节)
LGetIsaDone:
	CacheLookup NORMAL		// 5. 查缓存 (宏展开后约 10-20 条指令)
```

我们可以发现，`objc_msgSend` 整体当然不短，但**最核心的快速路径**其实非常短。光看入口附近那段，算上 `CacheLookup` 展开的核心部分，热点前缀大概也就是 `~64` 字节这个量级。

这就很有意思了：

1. Cache Line 大小 ：64 字节。
2. Fast Path 大小 ：约 64 字节。

`L1 Cache` 本身通常又是组相联（`Set Associative`）结构：地址的某些位决定它映射到哪个 `Set`，而每个 `Set` 里又有多个 `way`，每个 `way` 可以放一条 `cache line`。

打个比方的话，可以把 `L1 Cache` 想成：
- 一排很多“组”（set0, set1, set2...）
- 每组里有多层“停车位”（way0, way1, way2...）
- 每个停车位停一辆“车”（一条 cache line，常见 64B）

但这篇真正要抓住的重点不是“`Set` 到底怎么编号”，而是：**fast path 最好尽量落在单条 `Cache Line` 里**。因为一旦它横跨两条 line，CPU 前端就更依赖两条 line 同时保持热状态，也更容易受到 `i-cache` 冲突和布局波动的影响。

如果不强行对齐（随机地址）：

- 假设它从 0x...1030 开始。
- 前 16 字节落在一条 `Cache Line` 里。
- 后面的 48 字节落到下一条 `Cache Line` 里。
- 后果：一次 Fast Path 可能要依赖两条 line 都保持热状态。
- 风险：只要其中一条 line 因为别的热点代码被挤掉，取指稳定性就会变差。

如果强行对齐（起始地址低位全 0）：

- 它强制从 0x...1400 开始（1024 的倍数，当然也是 64 的倍数）。
- 前 64 字节更容易完整落在同一条 `Cache Line` 里。
- 后果：执行一次 Fast Path，CPU 前端只需要先保证这一条 line 就位。
- 收益：热点入口的取指行为更稳定，对额外 line 的依赖也更小。


`objc_msgSend` 的精髓其实就在这里：它最关键的那段代码，也就是 `Fast Path`，非常短。做 `1024` 对齐，并不是为了“让整个函数看起来更整齐”，而是为了尽可能保住这段最热点的入口前缀，让它更稳定地落在一个理想的取指范围里。

只要把前面这 `~64` 字节尽量保住，`99%` 的消息发送都能在更理想的前端条件下运行。至于后面的慢路径（`Slow Path`）跨不跨 line、在不在同一个 `Set`，重要性就明显低很多了——因为慢路径本来就慢，而且本来就不常走。


## 快慢路径的代码

快速路径最核心的代码可以概括成这样：

```
CacheLookup NORMAL, _objc_msgSend, __objc_msgSend_uncached
```

这个 `CacheLookup` 宏展开后，就是一堆高度优化的汇编指令（计算哈希、查桶、对比 SEL、跳转 IMP）。如果命中了缓存（Cache Hit），它就直接 `br x17` 跳到目标函数去执行了。这就是**最快**的那条路。

而慢速路径发生的场景也很明确：如果 `CacheLookup` 发现缓存里没有命中（`Cache Miss`），它就会跳到第三个参数指定的标签：`__objc_msgSend_uncached`

```
STATIC_ENTRY __objc_msgSend_uncached
UNWIND __objc_msgSend_uncached, FrameWithNoSaves

// THIS IS NOT A CALLABLE C FUNCTION
// Out-of-band p15 is the class to search

MethodTableLookup
TailCallFunctionPointer x17

END_ENTRY __objc_msgSend_uncached
```

这里最终会走到 `lookUpImpOrForward`（封装在 `MethodTableLookup` 宏里），去遍历类的方法列表、父类链、动态方法解析等等。这一步相对前面的快路径来说就慢很多了。

简单来说：
1. **Fast Path（前 \~64 字节）**：查找缓存 -> 命中 -> 跳转 `IMP`。这是 `99%` 的情况。
2. **Slow Path（后面的代码）**：查找缓存 -> 未命中 -> 跳转 `__objc_msgSend_uncached`。这是 `<1%` 的情况。

在绝大多数情况下，`CPU` 真正关心的也就是前面那条承载 `Fast Path` 的 `Cache Line`。后面的慢路径代码，就算布局没那么漂亮，影响也远没有入口前缀大。



## 为什么说是极端的空间换时间优化

先总结一下这个优化到底值在哪里：

从一个 `App` 启动开始，尤其是 `pre-main` 阶段和 `main` 之后的首屏渲染，会发生大量的 `objc_msgSend` 调用；而冷启动又恰恰是多线程并发、`i-Cache` 压力很大的场景。如果热点入口布局不稳定，就更容易在取指和 `i-cache` 上吃亏。

而如果跳出单个 `App` 的视角去看，`objc_msgSend` 几乎是整个 `Cocoa / Cocoa Touch` 世界的基石。这个优化不只会影响你的 `App`，也会影响 `SpringBoard`、系统服务等一大批进程。系统整体更轻，最终你的 `App` 也会受益。

对于单次 `objc_msgSend` 来说，这个优化可能只是非常细小的提升；但对于 `App` 启动这种高密度场景，它更像是在守住一条性能底线。它属于那种“单次看起来不大，累积起来非常可怕”的底层基础设施级优化。


## 那么代价呢

这种优化当然也不是没有代价。

为了让 `objc_msgSend` 满足这样的对齐要求，系统可能要在它前面插入 `0~1023` 字节（平均约 `512` 字节）的填充。这部分就是明确的空间成本。

对普通函数来说，`32/64` 字节对齐通常就已经够用了；但这里给 `objc_msgSend` 这种极端热点函数用到了 `1024` 字节对齐，对齐粒度明显更大。代价就是**二进制体积会增加**，而收益则是入口落点更稳定，快路径也更不容易受到 `i-cache` 冲突和取指波动的干扰。



# 总结 

系统使用 `MSG_ENTRY` 替代 `ENTRY`，是一次非常典型的底层工程优化。它通过**牺牲少量二进制空间**，换来了 `objc_msgSend` 热点入口更稳定的取指行为，以及更稳的快路径执行效率。对于 `App` 启动和高频消息发送场景来说，这种优化虽然细，但非常关键。
