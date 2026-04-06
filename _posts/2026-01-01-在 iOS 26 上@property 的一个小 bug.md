---
layout: post
title:  "在 iOS 26 上@property 的一个小 bug"
date:   2026-01-01 23:32:53 +0800
categories: [iOS, Objective-C, Runtime]
tags: [iOS, Objective-C, property, bug]
---

前段时间我阅读了 [iOS 26 你的 property 崩了吗？](https://juejin.cn/post/7565979063262117940?searchId=202601100203490EA4099612507A288C15) 这篇文章，当时没有太在意。结果这一阵子我自己也遇到了类似的 `bug`。刚好最近我又重新读了一遍新出的 [objc4-950](https://github.com/apple-oss-distributions/objc4) 源码，正好读到这一段，也就顺手从源码的角度来分析一下这个问题，以及到底该怎么处理。

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


简单对比一下，变化还是很明显的。

在老版本里，步骤简单清楚：
1. `objc_retain(obj)`  ---- 引用计数 + 1
2. `*location = obj`   ---- 指针赋值
3. `objc_release(prev)`---- 释放旧值

而在新版本中，多了一步：先写入一个哨兵值 `BAD_OBJECT ((id)0x400000000000bad0)`。如果这时候有别的线程读到这个值，并继续向它发消息或者访问它，程序就会立刻崩溃，而且崩溃地址也非常有辨识度。

那么问题来了，为什么新版本里要专门插入这样一个“故意让你崩”的值？这就要回头看看老逻辑本身到底有什么问题。


## objc_retain 和 objc_release 的线程安全

先看一下这两个函数的实现。

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

在这里，`runtime` 使用 `LoadExclusive` 和 `StoreExclusive` 构成原子操作循环，来保证内部更新的线程安全。你可以把它理解为一种类似 `CAS` 的无锁原子更新机制。

* `CAS`，即 `Compare-And-Swap`，是多线程里非常经典的一类原子操作思路，常用于实现无锁同步。


可以看到，`objc_retain` 和 `objc_release` 本身的内部实现是线程安全的，但这个“线程安全”只限于它们自己那一步的引用计数更新。

而在老版本的 `objc_storeStrong` 实现中，这潜伏着危险！

假设我们有这样一份代码：

```
@property (nonatomic, strong) NSObject *obj;
```

这里特意用 `nonatomic`，因为它不会帮我们处理多线程同步。多个线程如果同时读写同一个强引用属性，底层就可能撞上 `objc_storeStrong` 赋值过程中的非原子窗口。

我们从最坏的角度，推演一下可能发生的问题：

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


两个线程都读到了同一个旧值 `A`，然后都认为自己有责任去释放它。结果就是：`A` 被释放了两次。第二次释放时，就可能访问已经被回收的内存，从而导致 `Crash`。

还有另外一种情况：线程 A 正在赋值，线程 B 同时去读，这时候线程 B 也可能读到一个不该读到的中间状态。不过这篇主要先讨论最典型、也最好理解的这一类问题。


## 是否可以在 `objc_storeStrong` 里面加锁？

这当然是一种思路，但很可惜，`runtime` 不能直接这么干。

道理也很简单，`objc_storeStrong` 是一个**极其高频调用的函数**。如果在这里统一加锁，代价会非常高。并且大多数场景下，其实也不需要它承担“全局线程安全”这个责任，比如一个局部变量的单次赋值，或者主线程上的 `UI` 刷新。所以 `runtime` 最终还是把“并发访问时如何保证安全”这个责任交给了开发者。

但现实情况是，对于大多数开发者（包括我自己），平时很少会把这个点想到这么细。而且这类崩溃原本发生概率并不高，就算真发生了，也很难第一时间从崩溃栈里想到这里。

所以在新版本里，官方其实并不是从根上把这个并发问题“修好了”，而是通过插入哨兵值，把原本潜伏得比较深的问题更快地暴露出来。


## 该如何解决

对于这个问题，我觉得有以下几种处理方式：

#### 修改原代码

既然问题根源是“多线程读写同一个非线程安全属性”，那真正的解决方案还是得回到线程安全本身：
   
1. 加锁（强烈推荐）：
   在读写该属性时，使用 `os_unfair_lock`、`pthread_mutex` 或 `NSLock` 保护。
   
   ```
   os_unfair_lock_lock(&_lock);
   self.obj = newItem;
   os_unfair_lock_unlock(&_lock);
   ```
   
2. 使用 `atomic` 属性：
   
   ```
   @property (atomic, strong) NSObject *obj;
   ```
   虽然 `atomic` 性能略低，但它保证的是 `getter/setter` 这一层的原子性。也就是说，在正常通过属性访问器读写时，它会比 `nonatomic` 更稳一些，也不容易把这种窗口直接暴露出来。  
   但这里一定要注意：**它只保证单次取值/设值的原子性，并不等同于“整体线程安全”**。一旦牵扯进复合操作，照样可能出问题。
   
3. 串行队列：
   将对该属性的所有读写操作都放入同一个串行队列（如主队列或自定义队列）中执行。


#### Hook objc_storeStrong

既然问题的直接诱因是“新版 `objc_storeStrong` 写入了哨兵值，从而把问题立刻暴露出来”，那么一个兜底思路就是：把 `objc_storeStrong` 暂时改回旧版本那种实现。

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

这个方案可以作为一个“急救包”，让你在排障期或者重构前先把问题压住，不至于因为一次系统升级就让 App 直接大面积崩掉。  
但一定要明白，**这个方案并没有修复线程安全问题，它只是把“更容易暴露的崩溃”重新变回了“更隐蔽的崩溃”**。

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

旧版本里的 `objc_storeStrong` 本质问题在于：`读取旧值`、`更新指针`、`释放旧值` 这三个步骤并不是一个原子事务。  
而新版本（`objc4-950`）的改动，并不是把这个非原子问题彻底解决了，而是通过插入哨兵值，把这种并发访问错误更快、更明显地暴露出来。
