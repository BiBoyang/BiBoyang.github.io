---
layout: post
title: "如何 hook objc_msgSend"
date: 2025-10-20 23:32:53 +0800
categories: objc runtime hook
tags: [iOS, Objective-C, runtime, hook, objc_msgSend]
excerpt: "objc_msgSend 可以作为符号被重绑定，但真正困难的不是找到它，而是在不破坏 ABI、寄存器现场和返回路径的前提下完成 hook。"
---

# 如何 hook objc_msgSend

最近我在做一个实验：`objc_msgSend` 这种几乎等于 Objective-C 心脏的函数，到底能不能像普通 C 符号一样被 hook？

答案是：

- **可以做实验性质的 hook**
- **但它绝对不是一个“普通 C 函数”**
- **真正难的地方不在“找到符号”，而在“保住调用现场”**

这篇文章对应的 demo 就是我写的这个项目：

- 项目地址：`https://github.com/BiBoyang/How_To_Hook_msg_send`
- 核心文件：`objc-msg-arm64.s`
- hook 实现：`HookMsg/HookMsg/objc_msgSend_hook.m`

下面我把整个过程顺着讲清楚。

## 先确认一件事：`objc_msgSend` 确实是一个可链接的符号

通过查看 Runtime 源码，我们可以发现 `objc_msgSend` 是由**纯汇编**实现的。在 `objc-msg-arm64.s` 里，能看到这样的定义：

```asm
MSG_ENTRY _objc_msgSend
```

继续搜索 `MSG_ENTRY`，会看到它的宏定义：

```asm
.macro MSG_ENTRY /*name*/
	.text
	.align 10
	.globl    $0
$0:
.endmacro
```

把它展开以后，其实就是：

```asm
.text
.align 10
.globl _objc_msgSend
_objc_msgSend:
```

这几行非常关键，因为它说明了一件事：

从**链接器**的角度看，`_objc_msgSend` 就是一个对外导出的全局符号。

也就是说，虽然它是用汇编实现的，但它依然可以像普通外部函数一样，被别的目标文件引用、被动态链接器解析、被 `fishhook` 这种基于符号重绑定的方案捕获。

不过这里要立刻补一句：

> `objc_msgSend` **可以被当成函数符号来链接**，不等于它**可以被当成普通 C 函数来随便替换**。

这两个结论看起来很像，实际上差得很远。后面你会看到，真正麻烦的地方正在这里。

## `MSG_ENTRY` 到底特别在哪

如果你看过早些年的 objc runtime 汇编，可能会发现很多函数入口使用的是 `ENTRY`：

```asm
.macro ENTRY /* name */
	.text
	.align 5
	.globl    $0
$0:
.endmacro
```

而 `objc_msgSend` 用的是 `MSG_ENTRY`：

```asm
.macro MSG_ENTRY /*name*/
	.text
	.align 10
	.globl    $0
$0:
.endmacro
```

两者最明显的差别是对齐方式：

- `ENTRY` 是 `.align 5`
- `MSG_ENTRY` 是 `.align 10`

在 ARM64 下，指令长度固定为 4 字节。更高的对齐意味着 `objc_msgSend` 的入口会被放到一个更“整齐”的边界上。

我个人的理解是：这是 Apple 针对 `objc_msgSend` 这种超高频热点路径做的**激进对齐优化**。  
原因并不是源码里直接写死说明的，所以这里我更愿意把它称作**基于源码现象的推断**：

- `objc_msgSend` 是所有消息分发的核心入口
- 它的前几十条指令是整个分发快速路径里最热的一段
- 更大的对齐通常更有利于指令抓取、I-Cache 命中和分支预测布局

换句话说，Apple 连函数入口对齐都愿意为它单独开宏，已经足够说明这条路径到底有多重要。

## 为什么 `objc_msgSend` 很难 hook

很多人第一次想到的方案都很自然：

1. 用 `fishhook` 把 `objc_msgSend` 换成自己的函数
2. 在自己的函数里打印一下 `self` 和 `_cmd`
3. 再调用原始 `objc_msgSend`

看起来非常顺，但真正动手以后会发现：**这事不能直接用普通 C 函数写。**

原因主要有四个。

### 1. `objc_msgSend` 是汇编实现，不是普通 ABI 下的业务函数

它虽然有符号，但它的调用方式非常特殊。

`objc_msgSend` 本质上是一个“**动态分发跳板**”：

- 输入是 `self`、`_cmd` 和后续参数
- 内部先做 isa 获取、缓存查找、miss 跳转
- 最终 tail call 到真正的 `IMP`

它自己不是业务逻辑的终点，而是调用链中间的关键跳板。

### 2. 参数类型和返回值类型都不固定

Objective-C 消息发送的签名是动态的。

同一个 `objc_msgSend`，有可能承载下面这些调用：

```objc
[obj foo];
[obj foo:1];
[obj foo:1 bar:2];
CGRect rect = [obj frame];
double value = [obj progress];
id result = [obj nextObject];
```

也就是说：

- 返回值可能在 `x0`
- 也可能走浮点寄存器
- 参数可能放在 `x0 ~ x7`
- 浮点参数可能放在 `q0 ~ q7`
- 更多参数还可能继续走栈

你如果写一个普通的 C 包装函数，编译器会按**你声明的那个函数签名**来生成保存和恢复逻辑。  
但 `objc_msgSend` 面对的是“所有可能的 Objective-C 方法签名”，这就天然冲突了。

### 3. 你稍微处理不当，就会破坏调用现场

比如你只是简单写：

```objc
static id my_objc_msgSend(id self, SEL _cmd, ...) {
    printf("hook\n");
    return orig_objc_msgSend(self, _cmd);
}
```

这个写法看起来像样，实际上问题很多：

- 可变参数没有被正确透传
- 浮点寄存器现场可能丢失
- 返回值语义可能被破坏
- 编译器插入的函数序言/尾声也会改变现场

所以，想 hook 它，核心并不是“换符号”，而是“**在不破坏寄存器和返回路径的情况下插入逻辑**”。

### 4. hook 代码本身还会触发新的 Objective-C 消息发送

比如你在 hook 里调用：

- `NSLog`
- `[self class]`
- `NSStringFromSelector`

这些调用本身又会继续触发 `objc_msgSend`，递归立刻就来了。

所以 demo 里我尽量使用：

- `object_getClassName`
- `sel_getName`
- `printf`

并配合线程局部变量做递归保护。

## `fishhook` 在这里到底帮了什么忙

`fishhook` 解决的问题，其实只是第一步：

> **把当前镜像里对某个外部符号的引用，改指向我们自己的实现。**

它并不会直接改写 `libobjc.A.dylib` 里的 `objc_msgSend` 机器码，而是去扫描 Mach-O 里的符号表和间接符号表，然后把对应的函数指针改掉。

在 `fishhook.c` 里，能看到一个很核心的思路：

```c
void **indirect_symbol_bindings = (void **)((uintptr_t)slide + section->addr);
...
if (strcmp(&symbol_name[1], cur->rebindings[j].name) == 0) {
    *(cur->rebindings[j].replaced) = indirect_symbol_bindings[i];
    indirect_symbol_bindings[i] = cur->rebindings[j].replacement;
}
```

它本质上做的是：

1. 找到当前 image 的 `__DATA` / `__DATA_CONST`
2. 找到 lazy/non-lazy symbol pointer section
3. 找到目标符号对应的间接绑定项
4. 把这个绑定项从原函数地址改成你的 replacement

所以 `fishhook` 能解决的是：

- **“我的程序里，谁在引用 `objc_msgSend` 这个符号？”**

但它解决不了的是：

- **“我替换进去的新函数，能不能正确模拟 `objc_msgSend` 的调用语义？”**

后者才是真正的难点。

## 现代编译器下，`objc_msgSend` 甚至不一定是唯一入口

这是一个特别容易踩坑的点。

在较新的 clang/LLVM 产物里，很多 Objective-C 调用已经不会简单地生成一个统一的：

```asm
bl _objc_msgSend
```

而是可能出现更具体的调用入口，比如：

```asm
bl _objc_msgSend$bar
bl _objc_alloc
```

也就是说：

- `[obj bar]` 可能走 `objc_msgSend$bar`
- `[Foo alloc]` 可能直接走 `objc_alloc`
- `super` 调用还可能走 `objc_msgSendSuper2`
- 某些优化路径还可能落到 `objc_opt_*`

这意味着一件非常现实的事情：

> **只 rebinding `objc_msgSend`，并不保证你能看到所有 Objective-C 调用。**

这也是为什么我在 demo 里顺手把 `objc_alloc` 也一并 hook 了：

```objc
struct rebinding bind_msgSend = {
    "objc_msgSend",
    (void *)hook_Objc_msgSend,
    (void **)&orig_objc_msgSend
};

struct rebinding bind_alloc = {
    "objc_alloc",
    (void *)hook_objc_alloc,
    (void **)&orig_objc_alloc
};
```

它的意义不是“`objc_alloc` 和 `objc_msgSend` 等价”，而是告诉我们：

现代 Objective-C 调度路径比以前想象得要分散，不能假设所有调用最终都会乖乖走到同一个符号上。

## 我的 demo 是怎么做的

整个 demo 的思路其实很直接：

1. 用 `fishhook` 重绑定 `objc_msgSend`
2. 不用普通 C 函数接管，而是写一个 `naked` 的汇编桥
3. 在桥里手动保存/恢复寄存器
4. 调用前置逻辑
5. 调回原始 `objc_msgSend`
6. 再执行后置逻辑
7. 恢复 `LR`，回到原始调用点

核心实现就在 `objc_msgSend_hook.m`。

### 1. 先保存现场

我写了两个宏：`save()` 和 `load()`。

```objc
#define save() \
__asm__ volatile ( \
"stp q6, q7, [sp, #-32]! \n" \
"stp q4, q5, [sp, #-32]! \n" \
"stp q2, q3, [sp, #-32]! \n" \
"stp q0, q1, [sp, #-32]! \n" \
"stp x8, x9, [sp, #-16]! \n" \
"stp x6, x7, [sp, #-16]! \n" \
"stp x4, x5, [sp, #-16]! \n" \
"stp x2, x3, [sp, #-16]! \n" \
"stp x0, x1, [sp, #-16]! \n");
```

为什么要这样做？

因为对 `objc_msgSend` 来说，`x0 ~ x7`、`q0 ~ q7` 很可能正装着调用参数，返回值也可能落在这些寄存器里。  
如果在调用前置/后置逻辑之前不先把它们保住，现场就被我们自己踩坏了。

### 2. 用 `naked` 函数自己接管入口

真正被 `fishhook` 替换进去的不是一个普通 Objective-C 函数，而是这个：

```objc
__attribute__((naked))
static void hook_Objc_msgSend(void) {
    save()
    __asm__ volatile ("mov x2, lr \n");
    call(&pre_objc_msgSend)
    load()
    call(orig_objc_msgSend)
    save()
    call(&post_objc_msgSend)
    __asm__ volatile ("mov lr, x0 \n");
    load()
    __asm__ volatile ("ret \n");
}
```

这里 `naked` 的意义非常大：

- 不让编译器自动插入标准函数序言/尾声
- 我们自己控制 `sp`、寄存器保存和返回路径
- 尽量把这个桥接入口做成“像 `objc_msgSend` 一样轻”

### 3. 前置逻辑里只做最少的事情

前置函数长这样：

```objc
static void pre_objc_msgSend(id self, SEL _cmd, uintptr_t lr) {
    if (is_hooking) return;
    is_hooking = true;

    if (lr_top < (int)(sizeof(lr_stack) / sizeof(lr_stack[0]))) {
        lr_stack[lr_top++] = lr;
    }

    const char *cls = object_getClassName(self);
    const char *sel = sel_getName(_cmd);
    printf("pre action... [%s %s]\n", cls ? cls : "(nil)", sel ? sel : "(null)");

    is_hooking = false;
}
```

这里有几个点很关键：

- 用 `__thread` 保存 `lr_stack`
- 用 `__thread` 保存 `is_hooking`
- 不用 `NSLog`
- 不主动发 Objective-C 消息

否则这个 hook 很容易自己把自己绕死。

### 4. 为什么要自己维护一个 `LR` 栈

`LR` 是返回地址寄存器。

对于 `objc_msgSend` 这种高频、可嵌套的调用来说，一次消息发送内部很可能又触发下一次消息发送。  
如果你只用一个全局变量保存 `LR`，嵌套一发生，返回地址就乱了。

所以我这里用了：

```objc
static __thread uintptr_t lr_stack[1024];
static __thread int lr_top = 0;
```

两个关键词：

- `__thread`：线程隔离，避免多线程互相污染
- `stack`：支持嵌套调用，先进后出

前置逻辑压栈，后置逻辑出栈，最后把值再写回 `lr`。

### 5. 后置逻辑负责把返回路径接回去

后置函数：

```objc
static uintptr_t post_objc_msgSend(void) {
    if (is_hooking) {
        if (lr_top > 0) return lr_stack[lr_top-1];
        return 0;
    }
    is_hooking = true;

    printf("post action...\n");
    uintptr_t lr = 0;
    if (lr_top > 0) {
        lr_top--;
        lr = lr_stack[lr_top];
    }

    is_hooking = false;
    return lr;
}
```

在汇编桥里，`post_objc_msgSend()` 返回的 `lr` 会被重新写回：

```asm
mov lr, x0
ret
```

这样 hook 逻辑执行完后，程序依然能回到原本的调用点。

## 整个调用时序可以概括成这样

当一条 Objective-C 消息真的命中了我们 rebinding 过的入口后，大致流程如下：

1. 进入 `hook_Objc_msgSend`
2. 保存参数寄存器和浮点寄存器
3. 取出当前 `LR`，传给 `pre_objc_msgSend`
4. 执行前置打印/记录逻辑
5. 恢复寄存器现场
6. 调用原始 `objc_msgSend`
7. 再次保存现场
8. 执行 `post_objc_msgSend`
9. 取回之前保存的 `LR`
10. 恢复寄存器并 `ret`

这套流程的本质就是一句话：

> **把 hook 逻辑塞进 `objc_msgSend` 前后，同时尽量让真实调用者感觉一切都没变。**

## 为什么不能直接“用 C 再包一层”

讲到这里，其实就能看出核心结论了：

`objc_msgSend` 难 hook，不是因为它没有符号，也不是因为 `fishhook` 不够强，而是因为：

> **它的 ABI 太特别，普通 C 包装层根本兜不住。**

普通 C 函数的问题在于：

- 它有固定函数签名
- 编译器会主动改寄存器和栈
- 它不理解 Objective-C 消息分发的动态返回值模型
- 它也不会替你维护原始返回地址链路

所以这类 hook 的关键套路基本都是：

- **用符号重绑定拿到入口**
- **用裸函数或纯汇编桥保护现场**
- **把真正的业务记录逻辑压到最轻**

## 这个方案的局限性

这个 demo 能跑通思路，但它依然只是一个实验性方案，不是生产级方案。

至少有下面几个限制。

### 1. 覆盖率不完整

前面已经提到，现代编译器和 runtime 可能会走：

- `objc_msgSend$selector`
- `objc_alloc`
- `objc_msgSendSuper2`
- `objc_opt_*`

所以你看到的调用，只是“你成功拦截到的那一部分”。

### 2. 性能开销非常夸张

`objc_msgSend` 原本就是 runtime 里最敏感的热点路径之一。  
你在这里加任何保存寄存器、打印日志、线程局部变量访问，都会把开销放大到可怕的程度。

换句话说：

> **能 hook，不代表值得长期 hook。**

它更适合做原理验证、调试实验、研究 runtime，而不是线上常驻埋点。

### 3. 对架构和系统细节很敏感

当前这份代码显式限制在：

```objc
#if defined(__arm64__)
```

这很合理，因为：

- ARM64 和 x86_64 的调用约定不同
- arm64e 还会涉及 BTI / Pointer Authentication
- 系统版本变化也可能让行为出现差异

所以这个 demo 的正确打开方式是：

**把它当成“原理实验”，不要把它当成“稳定方案”。**

### 4. hook 逻辑本身非常容易递归

哪怕只是一个不小心的 `NSLog`，都可能重新触发 Objective-C 消息发送。  
这也是为什么这里看起来有点“原始”地使用了 `printf` 和 C runtime API。

不是为了好看，而是为了活下来。

## 总结

现在再回到文章开头那个问题：

**`objc_msgSend` 能不能 hook？**

可以，但要分两层理解：

### 第一层：符号层面

它是一个真实存在、可以被链接器解析的全局符号。  
所以 `fishhook` 这样的符号重绑定方案，理论上确实可以把引用它的调用点改到我们自己的入口。

### 第二层：调用语义层面

它又不是一个普通 C 函数。

它承担的是 Objective-C 消息分发的核心跳板职责，参数、返回值、寄存器现场、返回地址、递归风险，全都比普通函数复杂得多。  
因此真正可行的 hook 方案，重点不在“换掉符号”，而在“**自己接住 ABI**”。

这也是我这个 demo 最想说明的一点：

> `fishhook` 负责把门撬开，真正走进去处理现场的，还是汇编。

如果你只是想知道“能不能 hook”，答案是能。  
如果你想知道“为什么网上很多人试一下就崩”，答案也很简单：

因为 `objc_msgSend` 从来都不是那种可以随手包一层的函数。
