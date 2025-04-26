---
layout: post
title:  "不安全的 UserDefaults：隐藏在便捷背后的技术风险"
date:   2025-04-08 23:32:53 +0800
categories: jekyll update
---


众所周知，UserDefaults 是 iOS 系统中一个轻量级的本地存储方案，很多人会在这里存储一些小的数据。

简单的用法如下：

```swift
// 写入
UserDefaults.standard.set("value", forKey: "key")  
// 读取
let value = UserDefaults.standard.string(forKey: "key")  
// 跨应用共享（需配置 App Group）
let suiteDefaults = UserDefaults(suiteName: "group.com.example")  
```

它的特点是：

1. 线程安全（底层用 os_unfair_lock 锁保证）；
2. 支持 KVO 和 NSUserDefaultsDidChangeNotification 监听变更；
3. 支持明文存储（文件路径：Library/Preferences/<BundleID>.plist）；
4. 自动缓存数据，减少磁盘 I/O。


## 底层机制简析

Swift 的 UserDefaults 是 NSUserDefaults 的桥接，底层是完全一样的。

但因为Swift存在泛型，编译器会做额外优化，Swift 自动处理 NSNumber 到 Int/Double 的桥接，避免手动转换。

通过阅读官方文档和进行代码实现，我们知道 UserDefaults 使用的是懒加载模式，当代码首次调用 UserDefaults.standard（或 [NSUserDefaults standardUserDefaults]）时，系统才会加载 plist 文件到内存。

举个例子：
在 *AppDelegate* 中访问：如果开发者在  *application(_:didFinishLaunchingWithOptions:)* 中读取或写入 UserDefaults，此时会触发 plist 文件的加载。而如果在后续代码中访问，加载会进一步延迟到首次调用时。

此外，UserDefaults 的每次写操作，会出发 XPC 通信，与系统进程 cfprefsd 同步数据；而读操作则不会。

因为这点，如果短时间大量进行写入，有可能会可能阻塞线程。而且我们一定要知道 UserDefaults 的写入并不是第一时间写入，即使是使用 synchronize 方法，也不会第一时间写入，官方文档写的非常清楚
*Waits for any pending asynchronous updates to the defaults database and returns; this method is unnecessary and shouldn’t be used.*这个方法已经事实上废弃了。


## 新版本系统的致命挑战

随着 iOS 15 的到来，苹果提供了一个 App 预热功能，可以让常用应用更快的启动。虽然理论上讲：应用预热应该在停止在 UIApplicationMain() 之前。但是这几年来，在社群上一直有人反馈，预热功能在有的时候*完全启动*了应用！

甚至还有更进一步的场景：在你重启了手机还没有解锁的时候，App 有可能已经被“预热”了！

这导致一些尴尬的问题，虽然 UserDefaults 默认使用NSFileProtectionCompleteUntilFirstUserAuthentication（使其在首次设备解锁后即可访问），但它可能会在首次解锁前的预热期间返回 nil 或默认值。这种情况会悄无声息地发生，不会引发任何错误。

假如你在 UserDefaults 中存储了一些关于启动是直接读取甚至于写入的数据，那么数据的安全性，以及 App 基于 UserDefaults 的一些设置（比如说暗黑模式）就会变得严重不可控。

与之类似的还有  Live Activit，就是在动态岛和锁屏页面常常出现的那个东西。也一样会触发这种问题。当多个 Extension 同时访问共享域时，XPC 延迟导致数据不一致。



### 使用须知

* 如果要使用 UserDefaults，那么至少要保证只是少量数据存储和偶尔修改的情况下使用。
* 即使要使用，也不要完全相信；
* 写入操作最好也要异步化（防止 XPC 堵塞）。

```swift
let defaultsQueue = DispatchQueue(label: "com.example.defaults")
defaultsQueue.async {
    UserDefaults.standard.set(value, forKey: "key")
}
```
* 并且最好防御性编程（关键数据需校验设备解锁状态）

```swift
if UIApplication.shared.isProtectedDataAvailable {
    // 安全访问逻辑
}
```

### 替代方案

如果是敏感数据，使用Keychain；

如果是需要高频写入读取的数据，直接使用 MMKV 算了，写入速度比 UserDefaults 快 100 倍，通过 mmap 还可以实现崩溃安全。

# 总结

UserDefaults 的「便捷性」本质是苹果对开发者的一种妥协。在 iOS 15+ 的复杂运行环境下，其底层机制已无法满足现代应用对数据可靠性、安全性的要求。建议开发者：

* ​​严格限制使用场景​​：仅作非关键配置存储
* 推进架构改造​​：逐步迁移至专业化存储方案
* 建立监控体系​​：如果一时无法迁移，建议通过埋点统计异常返回值



