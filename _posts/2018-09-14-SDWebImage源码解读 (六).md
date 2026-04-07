---
layout: post
title:  "SDWebImage源码解读 (六)"
date:   2018-09-14 23:32:53 +0800
categories: [iOS, SourceCode, Image]
---



这个系列到这里先告一段落。这一篇不再顺着主流程继续读源码，而是把前面没完全展开、但又很值得单独说一下的几个问题补在这里。

## （一） 加载大图的内存暴涨的原因
这个问题本来应该写到上一节“图片解码”里一起讲，但是那边当时没写完，所以就单独放在这里。
```
[[SDImageCache sharedImageCache] setShouldDecompressImages:NO];
[[SDWebImageDownloader sharedDownloader] setShouldDecompressImages:NO];
```
这两个配置的意义，就是关闭图片的提前解压缩。

原因其实很直接：

- 图片文件通常是压缩格式；
- 真正显示时会被解码成位图；
- 一旦图片太大，或者同时解码的图片太多，内存就会涨得很快。

所以这本质上还是“空间换时间”：

- 提前解压缩，展示更顺；
- 但内存也会涨得更快。

所以如果面对的是大图、长图或者高清图，很多时候就不能继续沿用普通列表图的策略了，可能要：

- 点击后再看高清；
- 减少缓存；
- 或者在某些场景下关闭提前解压缩。

有关解码，可以继续看这篇文章：

- [谈谈 iOS 中图片的解压缩](http://blog.leichunfeng.com/blog/2017/02/20/talking-about-the-decompression-of-the-image-in-ios/)

## （二） setNeedsLayout方法的作用
直接点说，`setNeedsLayout` 的作用，不是“马上开始刷新布局”，而是**给当前 UIView 打一个标记，告诉系统：这个 view 需要在后面的布局周期里重新 layout 一次。**

我们先看一下官方解释：
```
Invalidates the current layout of the receiver and triggers a layout update during the next update cycle.
Call this method on your application’s main thread when you want to adjust the layout of a view’s subviews. This method makes a note of the request and returns immediately. Because this method does not force an immediate update, but instead waits for the next update cycle, you can use it to invalidate the layout of multiple views before any of those views are updated. This behavior allows you to consolidate all of your layout updates to one update cycle, which is usually better for performance.
使接收器的当前布局无效，并在下一更新周期触发布局更新。
当您想调整视图的子视图布局时，请在应用程序的主线程上调用此方法。该方法记录请求并立即返回。因为此方法不强制立即更新，而是等待下一个更新周期，所以您可以使用它来在更新任何视图之前使多个视图的布局无效。这种行为允许您将所有布局更新合并到一个更新周期，这通常对性能更好。
```
![](https://ws4.sinaimg.cn/large/006tNbRwly1fw9l4lop5ej30yu0icqeu.jpg)
这里借用这张图，简单说一下（只讲最右边方框里的方法）：
> 在Touches传递到了视图上的时候，会调整视图的UI属性，比如frame，透明度神马的；会被表示为setNeedsLayout；会被标识为setNeedsDisplay。
> 接着会被传到layoutSubviews，如果确定要被重新布局，就会开始调用layoutsubviews方法；
> 如果需要重新绘制，会调用drawRect方法。

这里要了解一个概念：[The View Drawing Cycle](https://developer.apple.com/library/archive/documentation/WindowsViews/Conceptual/ViewPG_iPhoneOS/WindowsandViews/WindowsandViews.html#//apple_ref/doc/uid/TP40009503-CH2-SW9)

>The UIView class uses an on-demand drawing model for presenting content. When a view first appears on the screen, the system asks it to draw its content. The system captures a snapshot of this content and uses that snapshot as the view’s visual representation. If you never change the view’s content, the view’s drawing code may never be called again. The snapshot image is reused for most operations involving the view. If you do change the content, you notify the system that the view has changed. The view then repeats the process of drawing the view and capturing a snapshot of the new results.
When the contents of your view change, you do not redraw those changes directly. Instead, you invalidate the view using either the setNeedsDisplay or setNeedsDisplayInRect: method. These methods tell the system that the contents of the view changed and need to be redrawn at the next opportunity. The system waits until the end of the current run loop before initiating any drawing operations. This delay gives you a chance to invalidate multiple views, add or remove views from your hierarchy, hide views, resize views, and reposition views all at once. All of the changes you make are then reflected at the same time.

这里其实很好理解：系统会把多次 UI 更新请求尽量聚合到同一个 run loop 周期中处理，从而避免重复地、零碎地去刷新 UI。

这里顺便补一下 `layoutIfNeeded` 的要点：

- `setNeedsLayout` 是“先标记一下，等会再布局”；
- `layoutIfNeeded` 是“如果已经有标记了，那我现在就把这次布局做掉”。

所以如果我们想立即刷新布局，通常会这么写：

 ```
[self setNeedsLayout];
[self layoutIfNeeded];
 ```
 
## （三） 为什么替换@synchronize
简单来说，`@synchronize` 的通用性很强，但额外开销也不小；而像 `dispatch_semaphore`、`os_unfair_lock` 这类更明确的同步手段，在知道自己要保护什么的时候，往往会更轻量一些。

这里不一定适合把话说成“谁一定性能最高”，更稳妥的理解是：

- 通用锁更省脑子；
- 定向锁更省开销；
- 框架里替换掉 `@synchronize`，通常是为了降低热点路径上的同步成本。

## （四）block和delegate的区别
这里只限于 `SDWebImage` 这个上下文里说。

类似于“单次图片下载完成”这种一次性的结果回调，用 `block` 会很自然；

如果涉及的方法很多，或者需要让某个对象长期承担一整类回调职责，那么 `delegate` 会更合适。

也就是说，这里并不是谁绝对更好，而是：

- **一次性结果** → 更适合 `block`
- **长期协作关系** → 更适合 `delegate`

## （五）NSMapTable的使用
`NSMapTable` 本身就是可变类型，可以看作 `NSMutableDictionary` 的一种更灵活替代。

和 `NSDictionary / NSMutableDictionary` 相比，它更大的价值在于：

- key / value 的内存语义可以自定义；
- 可以选择弱引用 key、弱引用 value，或者其他组合；
- 这对于框架内部管理对象映射关系时会非常方便。

简单说，`NSMapTable` 更适合那些“普通字典不够灵活”的场景。

## （六）啥是内联函数
内联函数是 `C++` 里的一个概念。

我们写代码的时候会定义很多函数来方便复用。但函数调用本身是有成本的，所以对于那些功能很简单、规模很小、调用又很频繁的函数，编译器有时会把函数体直接展开到调用处，这就是内联函数的思路。

它和宏的区别很明显：

1. 内联函数在运行时仍然更像“函数”，可读性和调试性都更好；
2. 编译器会对内联函数的参数类型做检查，而宏不会；
3. 内联函数仍然遵守语言规则，宏只是简单文本替换。

当然还有一点要注意：`inline` 关键字更多是一种“建议”，编译器不一定真的会把它展开成内联函数。


 
