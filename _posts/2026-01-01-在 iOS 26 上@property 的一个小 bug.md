---
layout: post
title:  "在 iOS 26 上@property 的一个小 bug"
date:   2026-01-01 23:32:53 +0800
categories: jekyll update
---


前段时间阅读了[iOS 26 你的 property 崩了吗？](https://juejin.cn/post/7565979063262117940?searchId=202601100203490EA4099612507A288C15) 这篇文章，当时没太注意，但是这一阵子我也遇到了类似的 bug 。刚好最近我重新阅读新出的 objc-950 的源码，正好阅读到了这一部分，也就顺便从源码的角度来分析一下这个 bug 以及如何解决这个问题。

## objc_storeStrong 的修改

对比源码，很容易发现 `objc_storeStrong` 函数发生了修改。

老版本
```
void
objc_storeStrong(id *location, id obj)
{
    id prev = *location;
    if (obj == prev) {
        return;
    }
    objc_retain(obj);
    *location = obj;
    objc_release(prev);
}
```

新版本

```
void
objc_storeStrong(id *location, id obj)
{
    id prev = *location;
    if (obj == prev) {
        return;
    }

#if __INTPTR_WIDTH__ == 32
#define BAD_OBJECT ((id)0xbad0)
#else
#define BAD_OBJECT ((id)0x400000000000bad0)
#endif
    *(volatile id *)location = BAD_OBJECT;

    objc_retain(obj);
    *location = obj;
    objc_release(prev);
}
```


简单对比一下，非常明显。

在老版本里，步骤简单清楚：
1. `objc_retain(obj)`  ---- 引用计数 + 1
2. `*location = obj`   ---- 指针赋值
3. `objc_release(prev)`---- 释放旧值

而在新版本中，写入了一个哨兵值 `BAD_OBJECT ((id)0x400000000000bad0)`，当读取到它，向它发送消息或者访问时，程序会立即崩溃，且崩溃地址直接非常明显。

那么问题来了，为什么在新版本中加入了这一个**必现且地址非常明显**的崩溃呢？我们就要审视一下原本的逻辑有什么问题。


## objc_retain 和 objc_release 的线程安全

先看一下 这两个函数的实现

```
__attribute__((always_inline))
static id _Nullable _objc_retain(id _Nullable obj) {
    if (_objc_isTaggedPointerOrNil(obj)) return obj;
    return obj->retain();
}
__attribute__((always_inline))
static void _objc_release(id _Nullable obj) {
    if (_objc_isTaggedPointerOrNil(obj)) return;
    return obj->release();
}
----------------------------------------------
简化代码
ALWAYS_INLINE id
objc_object::rootRetain(bool tryRetain, objc_object::RRVariant variant) {
    isa_t oldisa;
    isa_t newisa;

    oldisa = LoadExclusive(&isa().bits);
    
    newisa = oldisa;
    newisa.extra_rc++; 
    
    
    slowpath(!StoreExclusive(&isa().bits, &oldisa.bits, newisa.bits)));

    return (id)this;
}
----------------------------------------------
ALWAYS_INLINE bool 
objc_object::rootRelease(bool performDealloc, objc_object::RRVariant variant)
{
    isa_t newisa, oldisa;

    oldisa = LoadExclusive(&isa().bits);

    newisa = oldisa;
    uintptr_t carry;
    newisa.bits = subc(newisa.bits, RC_ONE, 0, &carry); 
        
    slowpath(!StoreExclusive(&isa().bits, &oldisa.bits, newisa.bits)));

}



```

在这里，`runtime` 使用 `LoadExclusive` 和 `StoreExclusive` 构成原子操作循环，保证线程安全，这是 `CAS` 操作。

* `CAS`，即 `Compare-And-Swap`，这是 `CPU` 级别的原子指令，用于实现无锁同步，现代多线程编程中实现高性能无锁数据结构的基石。


可以看到，`objc_retain` 和 `objc_release` 本身就是线程安全的，但是仅限于**内部实现**！

而在老版本的 `objc_storeStrong` 实现中，这潜伏着危险！

假设我们有这样一份代码：

```
@property (atomic, strong) NSObject *obj;
```

从最坏的角度，我们推演一下可能发生的问题：

**self.obj 一开始指向 A**


| 时间线 | 线程 A                        | 线程 B                        | 状态                   |
|--------|:------------------------------|:------------------------------|------------------------|
| 1      | id prev = *location; (读到 A) |                               |                        |
| 2      |                               | id prev = *location; (读到 A) |                        |
| 3      | objc_retain(B);               |                               |                        |
| 4      | *location = B;                |                               |                        |
| 5      |                               | objc_retain(C);               |                        |
| 6      |                               | *location = C;                |                        |
| 7      | objc_release(A);              |                               | A 的 RC 变 0， A 被销毁 |
| 8      |                               | objc_release(A);              | CRASH！Boom！            |


两个线程都读到了同一个旧值 A，然后都认为自己有责任去释放它。A 被释放了两次。第二次释放时，访问了已经回收的内存，导致 `Crash` 。

还有另外一种情况，如果线程 A 正在赋值，线程 B 读取，线程 B 可能会读到旧对象。不过这个概率要比第一种情况要低，就不过多讨论。


## 是否可以在 `objc_storeStrong` 里面加锁？

这是一种解决的思路，但是很可惜不能这么实现。

道理很简单，`objc_storeStrong` 是一个**极其高频调用的函数**。如果在这里加锁，性能会下降数个数量级。并且对于大多数情况下，其实并不怎么需要保证线程安全，比如说一个局部变量单次赋值，或者主线程 `UI` 刷新；所以 `runtime` 将这个处理并发安全的责任交给了开发者来处理。

但是很可惜的是，对于大多数开发者（包括我在内），一般情况下考虑不到这里；并且这种崩溃的发生概率实际上是非常低的，即使发生了，也很难通过崩溃记录想到这里。

所以在最新版本里，官方事实上没有从系统的角度解决这个问题，而是通过插入哨兵值，让这种非原子的并发访问行为必然导致 `Crash` ，从而暴露问题。


## 该如何解决

对于这个问题，有以下几种方法来解决：

####  修改原代码

既然问题根源是“多线程读写非线程安全的属性”，那么解决方案就是保证线程安全：
   
1. 加锁（强烈推荐） ：
   在读写该属性时，使用 `os_unfair_lock` 、 `pthread_mutex` 或 `NSLock` 保护。
   
   ```
   os_unfair_lock_lock(&_lock);
   self.obj = newItem;
   os_unfair_lock_unlock(&_lock);
   ```
   
2. 使用 `atomic` 属性 ：
   
   ```
   @property (atomic, strong) NSObject *obj;
   ```
   虽然 `atomic` 性能略低，但它保证了 `getter/setter` 的原子性，绝对不会读到 `BAD_OBJECT` 。但是**仅限于读写这一瞬间的并发安全**，它远远不等同于“线程安全”。如果牵扯进复杂操作，依然无法保证线程安全。
   
3. 串行队列 ：
   将对该属性的所有读写操作都放入同一个串行队列（如主队列或自定义队列）中执行。


#### Hook objc_storeStrong

既然问题的核心是 “新版 `objc_storeStrong` 写入了哨兵值导致崩溃” ，那么兜底方案就是 “把 `objc_storeStrong` 还原回旧版本的实现” 。

这里我们就要引入 `fishhook` 了。

创建一个新文件，代码如下：
```
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import "fishhook.h" 

OBJC_EXPORT id objc_retain(id);
OBJC_EXPORT void objc_release(id);

// 保存原始函数的指针
static void (*orig_objc_storeStrong)(id *location, id obj);

void safe_storeStrong(id *location, id obj) {
    id prev = *location;
    if (obj == prev) {
        return;
    }
    objc_retain(obj);   
    *location = obj;    
    objc_release(prev); 
}


// 启动时自动 Hook

__attribute__((constructor))
static void installSafeStoreStrongHook() {
    // 使用 fishhook 重绑定符号
    struct rebinding storeStrongRebinding;
    storeStrongRebinding.name = "objc_storeStrong";
    storeStrongRebinding.replacement = (void *)safe_storeStrong;
    storeStrongRebinding.replaced = (void **)&orig_objc_storeStrong;
    
    struct rebinding rebinds[] = { storeStrongRebinding };
    
    // 执行重绑定
    rebind_symbols(rebinds, 1);
    
    NSLog(@"[SafeStoreStrong] 已成功 Hook objc_storeStrong，降级为旧版无哨兵模式。");
}
```

这个方案可以作为你的“急救包”，让你有时间慢慢去重构代码，而不是因为一个系统更新就让 App 瘫痪。但是我们依然要明白，**这个方案 没有修复线程安全问题 。它只是把“必现的崩溃”变回了“偶现的崩溃”**。

我们可以写一个测试用例：

```
@interface ViewController ()

// 必须是 nonatomic 且 strong 才能触发 objc_storeStrong
@property (nonatomic, strong) NSString *targetString;
@property (nonatomic, assign) BOOL stopTest;

@end
@implementation ViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    
    self.stopTest = NO;
    self.targetString = @"objc_storeStrong_test";
    
    NSLog(@"开始并发读写测试...");
    NSLog(@"如果 Hook 生效，App 应该能坚持运行一段时间，然后崩溃");

    // 线程 1: 疯狂写
    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_HIGH, 0), ^{
        int i = 0;
        while (!self.stopTest) {
            // 构造新字符串，确保是堆对象
            self.targetString = [NSString stringWithFormat:@"Value-%d", i++];
        }
    });
    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_HIGH, 0), ^{
        while (!self.stopTest) {
            NSString *str = self.targetString;
            if (str.length > 0) {
                // 模拟使用对象
                // NSLog(@"Read: %@", str); // 打印太快会卡死控制台，这里仅访问属性
            }
        }
    });
}

```


# 总结

`objc_storeStrong` 在旧版本是线程不安全的，本质在于： “读取旧值、更新指针、释放旧值”这三个步骤不是一个原子事务 。新版本（`objc-950`）的改动并没有解决这个非原子问题，而是通过插入哨兵值，让这种非原子的并发访问行为 必然导致 `Crash` ，从而暴露问题。
