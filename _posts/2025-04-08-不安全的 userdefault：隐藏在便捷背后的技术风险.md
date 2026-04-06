---
layout: post
title:  "不安全的 UserDefaults：隐藏在便捷背后的技术风险"
date:   2025-04-08 23:32:53 +0800
categories: [iOS, Storage, Reliability]
---


`UserDefaults` 是 iOS 里最常用的轻量级本地存储方案之一。因为它太方便了，很多人会很自然地把一些“小数据”直接塞进去。

简单的用法如下：

```swift
// 写入
UserDefaults.standard.set("value", forKey: "key")  
// 读取
let value = UserDefaults.standard.string(forKey: "key")  
// 跨应用共享（需配置 App Group）
let suiteDefaults = UserDefaults(suiteName: "group.com.example")  
```

它的特点大概有这些：

1. 线程安全（底层用 os_unfair_lock 锁保证）；
2. 支持 `KVO` 和 `NSUserDefaultsDidChangeNotification` 监听变更；
3. 支持明文存储（文件路径：Library/Preferences/<BundleID>.plist）；
4. 自动缓存数据，减少磁盘 I/O。


## 底层机制简析

Swift 里的 `UserDefaults` 本质上就是 `NSUserDefaults` 的桥接，底层还是同一套机制。

只不过在 Swift 里，编译器会顺手帮你处理一些桥接细节，比如 `NSNumber` 到 `Int/Double` 的转换，看起来会更自然一些。

通过阅读文档和实际验证，大致可以知道 `UserDefaults` 用的是懒加载模式：当代码第一次调用 `UserDefaults.standard`（或者 `[NSUserDefaults standardUserDefaults]`）时，系统才会把对应的 `plist` 文件加载进内存。

举个例子：

如果开发者在 `application(_:didFinishLaunchingWithOptions:)` 里第一次读取或写入 `UserDefaults`，那这个时刻通常就会触发底层数据的加载；如果前面一直没有碰它，那这个动作就会继续延迟到真正第一次访问时。

另外，`UserDefaults` 的写操作通常不只是改一下进程内内存，还会触发和系统进程 `cfprefsd` 的同步过程；而读操作更多时候会直接命中缓存。

因为这一点，如果短时间内大量写入，线程就有可能被拖慢。而且有一个容易被误解的点是：`UserDefaults` 的写入并不是“你一 set 就立刻稳定落盘”。即使调用 `synchronize`，也不应该把它当成一个可靠的“强制立即持久化”手段。官方文档对此写得很直接：

*Waits for any pending asynchronous updates to the defaults database and returns; this method is unnecessary and shouldn’t be used.*

也就是说，这个方法现在基本已经不建议再依赖了。


## iOS 15+ 下更容易暴露的问题

随着 iOS 15 的到来，苹果给系统加入了更积极的 App 预热能力，用来让常用应用启动得更快。按常规理解，这种预热不应该走完整的业务启动路径；但这几年来，社区里一直有人反馈：在某些场景下，预热确实会把应用带到比预想更靠后的执行阶段。

甚至还有更进一步的场景：在手机刚重启、用户还没有完成首次解锁时，App 也可能已经被“预热”了。

这就带来一个很尴尬的问题。虽然 `UserDefaults` 默认使用的是 `NSFileProtectionCompleteUntilFirstUserAuthentication`，也就是首次设备解锁之后即可访问；但在“首次解锁前 + App 被预热”这样的时段里，相关读取结果就可能和开发者预期不一致，表现为 `nil`、默认值，或者共享域状态异常，而且这个过程往往不会抛出显式错误。

如果你刚好把一些“启动时立刻要读、甚至还会顺手写回去”的数据放在 `UserDefaults` 里，那事情就会变得很麻烦。轻则设置错乱，比如暗黑模式、实验开关、启动态配置异常；重则把错误状态进一步写回，导致问题扩大。

与之类似的还有 `Live Activities`，也就是动态岛和锁屏上经常出现的那类实时内容。再加上各种 `Extension` 共享同一个 `App Group` 域时，多方同时访问 `UserDefaults`，也会让时序问题和一致性问题变得更明显。



### 使用须知

* 如果要使用 `UserDefaults`，那至少要保证只是少量数据存储、偶尔修改的场景。
* 即使要使用，也不要完全相信；
* 写入操作最好也异步化（尽量避免同步链路被拖慢）。

```swift
// 建议使用自定义串行队列并指定QoS
let defaultsQueue = DispatchQueue(label: "com.example.defaults",
                                  qos: .userInitiated,
                                  attributes: .concurrent)
defaultsQueue.async {
    UserDefaults.standard.set(value, forKey: "key")
}
```
* 并且最好做防御性编程（关键数据先校验设备解锁状态）

```swift
if UIApplication.shared.isProtectedDataAvailable {
    // 安全访问逻辑
}
```

### 替代方案

如果是敏感数据，就用 `Keychain`；

如果是需要高频读写的数据，那就别硬塞给 `UserDefaults` 了，直接考虑 `MMKV` 这类更适合高频访问的方案。

# 总结

`UserDefaults` 的“便捷”，本质上是苹果给开发者的一种低门槛方案。但在 iOS 15+ 这种运行环境更复杂、预热更积极、Extension 更多的背景下，它已经不适合承载那些对可靠性和时序要求很高的数据。

所以我的建议是：

* ​​严格限制使用场景​​：仅作非关键配置存储
* 推进架构改造​​：逐步迁移至专业化存储方案
* 建立监控体系​​：如果一时无法迁移，建议通过埋点统计异常返回值


