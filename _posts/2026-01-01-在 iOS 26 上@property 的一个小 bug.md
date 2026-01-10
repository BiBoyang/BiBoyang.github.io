---
layout: post
title:  "在 iOS 26 上@property 的一个小 bug"
date:   2026-01-01 23:32:53 +0800
categories: jekyll update
---


前段时间阅读了[iOS 26 你的 property 崩了吗？](https://juejin.cn/post/7565979063262117940?searchId=202601100203490EA4099612507A288C15) 这篇文章，当时没太注意，但是这一阵子我也遇到了类似的 bug 。刚好最近我重新阅读新出的 objc-950 的源码，正好阅读到了这一部分，也就顺便从源码的角度来分析一下这个 bug 以及如何解决这个问题。


