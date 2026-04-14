---
layout: post
title:  "Swift Actor ：隔离的不是线程，而是状态"
date:   2025-12-08 07:40:00 +0800
categories: [iOS, Swift,Concurrency]
tags: [iOS, Swift,Concurrency]
---



在 Swift Concurrency 里，`actor` 很容易和 `@MainActor` 被混成一件事。表面上看，它们都在处理“并发访问”问题；但如果把两者等同起来，后面几乎一定会写出边界模糊的代码。

我现在更愿意把它们拆成两句话来记：

- `actor` 解决的是可变状态的隔离问题
- `@MainActor` 解决的是某段代码必须受主执行器串行保护的问题

这两个概念有关，但不是一回事。把这层关系理顺之后，很多 Swift 并发代码会顺很多：什么时候该用 `actor`，什么时候该用 `@MainActor`，什么时候两者都不用，判断会清楚很多。

## 先别急着谈主线程，先看 `actor` 到底解决了什么

`actor` 被引入，不是为了替代 `DispatchQueue.main.async`，也不是为了让异步代码“自动更安全”。它更核心的目标，其实是避免共享可变状态在并发环境下被同时读写。

最典型的问题是这种代码：

```swift
final class Counter {
    var value = 0

    func increment() {
        value += 1
    }
}
```

如果多个任务同时调用 `increment()`，`value += 1` 这类读-改-写操作就可能发生数据竞争。问题不在于这段代码写得短，而在于它默认允许多个执行上下文同时碰同一份可变状态。

把它改成 `actor` 之后，语义就变了：

```swift
actor Counter {
    private var value = 0

    func increment() {
        value += 1
    }

    func currentValue() -> Int {
        value
    }
}
```

这时 `value` 不再是“谁都可以直接摸”的共享状态，而是 actor 隔离的内部状态。外部要访问它，必须通过 actor 的隔离边界。也正因为这个边界存在，跨 actor 调用通常需要 `await`：

```swift
let counter = Counter()

await counter.increment()
let value = await counter.currentValue()
```

这里的重点不是“加了 `await`”，而是 Swift 把“访问这份状态”这件事变成了一次受控制的跨隔离域调用。你不能再像访问普通对象一样，随手在任意线程、任意任务里直接读写它的内部可变数据。

这其实就是 `actor` 最重要的价值：不是帮你切线程，而是帮你把“谁有权修改状态”这件事变成编译器可检查的规则。

## `actor` 保证没有数据竞争，但不保证没有业务层面的竞争

理解 `actor` 时，另一个很容易踩的坑是：它确实能避免数据竞争，但它不等于“从此一切并发问题都消失”。

原因在于 actor 是可重入的。也就是说，一个 actor 方法在执行过程中如果遇到 `await` 挂起，actor 可以去处理别的消息，之后再回来继续执行原来的逻辑。

这意味着下面这种代码虽然没有底层数据竞争，但仍然可能出现业务上的时序问题：

```swift
actor ImageCache {
    private var storage: [URL: Data] = [:]

    func data(for url: URL) async throws -> Data {
        if let cached = storage[url] {
            return cached
        }

        let downloaded = try await download(from: url)
        storage[url] = downloaded
        return downloaded
    }
}
```

看起来没问题，但如果两个任务几乎同时请求同一个 `url`，它们都可能在第一次检查缓存时发现“还没有”，然后分别发起下载。这里不会产生内存层面的竞争，因为 `storage` 仍然被 actor 隔离；但逻辑上会重复下载。

所以 `actor` 带来的不是“自动正确”，而是一个更强的基础前提：共享状态的访问顺序是受控的，剩下的业务一致性还得你自己设计。比如要不要去重请求、要不要在 actor 内维护 in-flight task、要不要做状态机，这些都还是建模问题，不是关键字能替你决定的。

这一点特别重要。很多人第一次用 `actor`，会下意识把它理解成“线程安全类”。这只说对了一半。更准确的说法是：`actor` 提供的是隔离模型，不是万用并发药。

## `@MainActor` 说的是隔离域，不只是“主线程”

接着再看 `@MainActor`。

很多文章会把它简单解释成“保证代码在主线程执行”。这个说法不算完全错，但不够精确。更准确一点，`@MainActor` 是一个全局 actor，它表示某段代码属于主 actor 隔离域，访问它需要经过主 actor。

看一个常见例子：

```swift
@MainActor
final class ProfileViewModel: ObservableObject {
    @Published private(set) var username: String = ""

    func updateName(_ newName: String) {
        username = newName
    }
}
```

这段代码的含义不是“这个类里每一行代码都神秘地绑定到了某条固定线程”，而是：这个类型及其隔离成员都受 `MainActor` 保护。谁想访问这些成员，就得满足主 actor 的隔离规则。

在 Swift Concurrency 的异步上下文里，这通常会表现为一次 hop 到主 actor 执行，因此很多时候看起来就像“自动切回主线程”：

```swift
func loadProfile() async {
    let name = await service.fetchName()
    await viewModel.updateName(name)
}
```

这里的 `await viewModel.updateName(name)`，本质上不是普通意义上的 GCD dispatch，而是跨隔离域调用主 actor 隔离的方法。

这个区别看起来像术语问题，实际上很关键，因为它直接关系到一个常见误解：

`@MainActor` 并不等于“无论你从哪里调用，都一定立刻帮你切到主线程”。

如果调用点本身不在 Swift 并发模型正确感知的上下文里，比如某些旧式同步回调、遗留 API、手工线程切换场景，你不能把 `@MainActor` 当成一个无条件的运行时跳板。它首先是隔离规则，其次才在合适的异步上下文里表现为调度行为。

这也是为什么有些代码明明标了 `@MainActor`，但你仍然会遇到编译器警告，或者需要显式写出：

```swift
await MainActor.run {
    viewModel.updateName(name)
}
```

`MainActor.run` 的意义是：我现在明确要求这段闭包在主 actor 上执行。它和“给某个声明加 `@MainActor`”解决的问题并不完全一样。前者更像是一次显式 hop，后者是给 API 建立隔离契约。

## 什么时候用 `actor`，什么时候用 `@MainActor`

如果只讲定义，这两个概念不难；真正容易混乱的是工程里怎么落。

我现在更倾向于这样分：

如果一个类型的核心职责是持有并保护共享可变状态，比如缓存、令牌存储、下载去重器、会话状态、内存索引，这类对象更适合建模成 `actor`。

如果一个类型的核心职责是驱动界面、维护 UI 可观察状态、响应用户交互，那它通常更适合标成 `@MainActor`。比如 `ViewModel`、部分 `ObservableObject`、只能在 UI 主隔离域里更新的状态容器。

一个很自然的组合是：

- 底层状态和并发访问控制，交给 `actor`
- 上层界面状态和渲染相关更新，交给 `@MainActor`

例如：

```swift
actor UserService {
    func fetchUser(id: String) async throws -> User {
        // 网络请求、缓存协调、并发去重
    }
}

@MainActor
final class UserViewModel: ObservableObject {
    @Published private(set) var user: User?
    private let service: UserService

    init(service: UserService) {
        self.service = service
    }

    func reload(id: String) async {
        do {
            user = try await service.fetchUser(id: id)
        } catch {
            user = nil
        }
    }
}
```

这个分层里，`UserService` 关心的是并发访问时的数据一致性，`UserViewModel` 关心的是界面状态更新必须落在主 actor。两者职责很清楚，也不需要把所有东西都粗暴地塞进 `@MainActor`。

## 还有一个经常被忽略的点：不是所有成员都必须被隔离

Swift 在 actor 模型里还给了一个很实用的出口：`nonisolated`。

当某个成员并不依赖 actor 的可变状态，或者某个协议要求同步访问，但实现本身不需要碰隔离数据时，可以把它标成 `nonisolated`，避免无意义的 `await` 和隔离限制。

这类设计的重点不是“少写几个关键字”，而是把 API 的并发语义写准确：哪些成员真正依赖隔离状态，哪些成员只是普通计算或常量暴露。隔离越精确，后续维护成本越低。

当然，前提也很明确：一旦用了 `nonisolated`，就不能再偷偷访问 actor 隔离的可变状态。这个边界如果写乱了，等于主动绕开模型给你的保护。

## 真正值得记住的结论

如果把整件事压缩成一句话，那就是：

`actor` 隔离的是状态，`@MainActor` 隔离的是执行上下文；它们都和并发有关，但解决的是不同层面的约束。

所以在 Swift 并发代码里，最好不要一上来就问“这里要不要切主线程”，而是先问两个更本质的问题：

- 这段代码有没有共享可变状态需要隔离？
- 这段状态变化是不是必须发生在主 actor？

第一个问题更接近 `actor`，第二个问题更接近 `@MainActor`。

当你先按这个方式建模，再去写 `await`、写 `MainActor.run`、写 ViewModel 和 Service 的边界，代码会自然很多。反过来，如果一开始就把 `actor` 理解成“高级锁”，把 `@MainActor` 理解成“新版 `DispatchQueue.main.async`”，那后面大概率只是把旧问题换了一套新语法。

## 参考

- SwiftLee: `MainActor usage in Swift explained to dispatch to the main thread`
- SwiftLee: `Actors in Swift: how to use and prevent data races`
- Swift Evolution: `SE-0306 Actors`
- Swift Evolution: `SE-0316 Global Actors`
