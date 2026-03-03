---
layout: post
title:  "如何 hook objc_msgSend"
date:   2025-10-20 23:32:53 +0800
categories: jekyll update
---



# 如何 Hook objc_msgSend：从 fishhook 到可运行实现

这篇我不讲抽象概念，直接从可运行工程出发，把两件事讲清楚：  
第一，fishhook 到底改了哪里，为什么能生效；  
第二，为什么 `objc_msgSend` 比普通符号难 hook，以及我在项目里是怎么落地的。

## 1. 先把入口钉住：hook 是在应用启动时挂上的

我在 `application:didFinishLaunchingWithOptions:` 里直接调用 `hookStart()`，也就是应用启动后第一时间注册替换逻辑。这样做的目的很简单：尽量覆盖后续消息发送路径，避免“部分调用已经发生但还没挂钩”的窗口期。

这一步在工程里非常明确，启动点是固定的，不依赖额外注入流程。

## 2. fishhook 的本质不是改函数体，而是改符号指针

我一开始也容易把 fishhook 想成“改代码段指令”，但它真正做的是 rebinding：把符号指针槽里的地址换掉。  
在实现里可以看到，fishhook 会：

- 找到 `__LINKEDIT` 相关信息，拿到符号表、字符串表、间接符号表
- 只遍历 `__DATA` / `__DATA_CONST` 下符号指针类型的 section
- 根据 `reserved1` 定位间接符号索引，再映射到符号名
- 名字匹配时把对应槽位替换成我提供的新函数地址

这也解释了它为什么轻量：它不改可执行代码页，而是改运行时可重定向的符号引用关系。

## 3. 我的工程里 fishhook 做了两件替换

在 `hookStart()` 里我绑定了两个符号：

- `objc_msgSend` -> `hook_Objc_msgSend`
- `objc_alloc` -> `hook_objc_alloc`

绑定方式是标准 `rebind_symbols`，并且保留原始函数指针（`orig_objc_msgSend` / `orig_objc_alloc`），这样替换后仍然可以安全回调原实现。  
这个“保留原函数地址”的动作是关键，没有它就不是 hook，而是硬切断调用链。

## 4. 为什么 objc_msgSend 不能按普通 C 函数写法去 hook

`objc_msgSend` 是 ABI 敏感点。  
它参数分布、返回值路径、寄存器约定都非常严格，直接写一个普通 C 函数去替代，通常会因为上下文污染导致崩溃或随机行为。

所以我这里采用的是“裸函数 + 汇编跳板”的方案：  
先完整保存现场，执行 pre 逻辑，再恢复现场调用原始 `objc_msgSend`，返回后再执行 post 逻辑，最后把控制权还给原调用方。

一句话：我不是“重写 objc_msgSend”，而是“在不破坏调用约定前提下包一层透明代理”。

## 5. 跳板函数怎么保证透明

我的 `hook_Objc_msgSend` 是 `__attribute__((naked))`，并配了 `save/load/call` 三组宏。

流程是：

1. 保存寄存器和向量寄存器上下文  
2. 把 `lr` 作为第三参数传给 `pre_objc_msgSend`  
3. 恢复现场，调用原始 `objc_msgSend`  
4. 再次保存现场，调用 `post_objc_msgSend`  
5. 用 post 返回值恢复 `lr`，恢复返回值寄存器，`ret` 回到原调用点

这里我还做了两件稳定性处理：

- 用线程局部 `lr_stack` 保存返回地址，避免多线程互相覆盖
- 用线程局部 `is_hooking` 做递归保护，防止 hook 逻辑自身再次触发 hook 导致重入爆炸

在 arm64e 上我加了 `bti c`，避免某些间接跳转保护场景下的非法分支问题。

## 6. fishhook 与 msgSend hook 的边界要说清楚

这套方案能工作，不代表“任何调用都能改”。

- fishhook 主要作用于动态符号引用链路
- 模块内部早已静态定址且不经过目标符号指针槽的路径，不会被它影响
- `objc_msgSend` 族函数本身有多个变体，文章里要明确你 hook 的是哪个入口，不要泛化成“全消息都已覆盖”

这部分边界写清楚，文章可信度会高很多，也能减少读者误用。

## 7. 我这套实现的核心结论

我最终验证下来的结论是：  
fishhook 负责“把入口改到我这里”，汇编跳板负责“改完入口后还保持 ABI 透明”。  
两者缺一不可。只讲 fishhook 会变成概念文；只讲汇编会变成孤立技巧。把它们连起来，才是一套可复用的 `objc_msgSend` hook 方法。

---

如果要继续扩展，我下一步会做三件事：  
1) 给 pre/post 增加 selector 白名单，降低日志噪音；  
2) 补充性能开销对比（开启/关闭 hook）；  
3) 增加 crash-safe 降级开关，便于线上回滚。