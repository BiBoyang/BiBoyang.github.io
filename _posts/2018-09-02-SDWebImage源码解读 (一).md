---
layout: post
title:  "SDWebImage源码解读 (一)"
date:   2018-09-02 23:32:53 +0800
categories: [iOS, SourceCode, Image]
---

# SDWebImage源码解读 (一)

###### SDWebImage (v4.4.1)

这一组文章分析的版本是 **SDWebImage 4.4.1**。主要目的不是为了照着这个版本写业务代码，而是借它来理解一套成熟图片框架的整体设计思路。

特点:

> * Categories for UIImageView, UIButton, MKAnnotationView adding web image and cache management
> * An asynchronous image downloader - 异步下载
> * An asynchronous memory + disk image caching with automatic cache expiration handling - 缓存自动到期，memory和disk缓存
> * A background image decompression - 后台解压
> * A guarantee that the same URL won't be downloaded several times - URL不会被多次下载
> * A guarantee that bogus URLs won't be retried again and again - 虚假的URL不会被持续重试
> * A guarantee that main thread will never be blocked Performances! - 主线程安全
> * Use GCD and ARC

# 目录

* **主要方法**
  
  * **SDWebImageOperation**
  * **SDWebImageCompat**
* **Decoder**
  
  * **SDWebImageCodersManager**
  * **SDWebImageCoder**
  * **SDWebImageFrame**
  * **SDWebImageGIFCoder**
  * **SDWebImageWebPCoder**
  * **SDWebImageImageIOCoder**
  * **SDAnimatedImageRep**
  * **SDWebImageCoderHelper**
* **Utils**
  
  * **SDWebImageManager**
  * **SDWebImagePrefetcher**
  * **SDWebImageTransition**
* **Downloader**
  
  * **SDWebImageDownloader**
  * **SDWebImageDownloaderOperation**
* **Cache**
  
  * **SDImageCache**
  * **SDImageCacheConfig**
* **WebCacheCategories**
  
  * **NSImage+WebCache**
  * **NSButton+WebCache**
  * **MKAnnotationView+WebCache**
  * **UIView+WebCache**
  * **UIButton+WebCache**
  * **UIImageView+WebCache**
  * **UIImageView+HighlightedWebCache**
* **Categories**
  
  * **NSData+ImageContentType**
  * **UIImage+WebP**
  * **UIView+WebCacheOperation**
  * **UIImage+ForceDecode**
  * **UIImage+GIF**
  * **UIImage+MultiFormat**
* **FLAnimatedImage**
  
  * **FLAnimatedImageView+WebCache**
  
  # 主要类名及其作用

| 类名 | 功能 |
| --- | --- |
| SDWebImageOperation | 宏定义、常量、常用方法 |
| SDWebImageCompat | 统一cancel方法 |
| SDWebImageCodersManager | 总体入口 |
| SDWebImageCoder| 需要实现的接口 |
| SDWebImageImageIOCoder| PNG/JPEG的Coder操作  |
| SDWebImageGIFCoder | GIF的Coder操作  |
| SDWebImageWebPCoder | WebP的Coder操作  |
| SDWebImageManager | 管理cache和download入口  |
| SDWebImagePrefetcher | 预处理获取Image |
| SDWebImageTransition | 过渡动画 |
| SDWebImageDownloader | 提供下载管理入口  |
| SDWebImageDownloaderOperation | 下载的Operation操作  |
| SDImageCache | 处理缓存逻辑 |
| SDImageCacheConfig | 配置缓存参数 |
| NSData+ImageContentType |  提供类型判断和ImageIO类型转换  |
| UIImage+GIF | Data转UIImage(GIF)扩展  |
| UIImage+ForceDecode | 解压操作  |
| UIView+WebCacheOperation | 提供顶层关于取消和下载记录的扩展  |




# 主要方法

## SDWebImageOperation

这里代码不多，只实现了一个 `SDWebImageOperation` 协议。

```
@protocol SDWebImageOperation <NSObject>
- (void)cancel;
```

这里的作用其实很直接：把“可以取消”这件事抽象成统一协议。调用这个 **cancel** 方法，最终会把对应链路上的操作一起取消掉。

## SDWebImageCompat

这里一开始先通过 **__OBJC_GC__** 宏表明，**SDWebImage** 不支持垃圾回收机制。
接着作者还顺手吐槽了一下 Apple 的平台判断宏。

```C++
Apple's defines from TargetConditionals.h are a bit weird.
 Apple的从TargetConditionals.h引用的宏有点诡异。
 Seems like TARGET_OS_MAC is always defined (on all platforms).
 好像TARGET_OS_MAC 是在所有的平台上被默认（都是1）
 To determine if we are running on OSX, we can only rely on TARGET_OS_IPHONE=0 and all the other platforms
为了确定我们是否正在运行OSX，我们只能靠target_os_iphone = 0 和 其他所有的平台
```

这里我把这个宏的槽点标一下：

```C++
+------------------------------------------------+
 |                TARGET_OS_MAC                   |
 | +---+  +-------------------------------------+ |
 | |   |  |          TARGET_OS_IPHONE           | |
 | |OSX|  | +-----+ +----+ +-------+ +--------+ | |
 | |   |  | | IOS | | TV | | WATCH | | BRIDGE | | |
 | |   |  | +-----+ +----+ +-------+ +--------+ | |
 | +---+  +-------------------------------------+ |
 +------------------------------------------------+
```

接着就是一段冗长但又必要的平台判断。

#### 枚举宏的细节

这里有一个很有意思的点是，作者把NS_ENUM和NS_OPTIONS的宏重写了一遍，改成了一样的位运算的样子。

```C++
#ifndef NS_ENUM
#define NS_ENUM(_type, _name) enum _name : _type _name; enum _name : _type
#endif

#ifndef NS_OPTIONS
#define NS_OPTIONS(_type, _name) enum _name : _type _name; enum _name : _type
#endif
```

之所以这么写，是因为普通的 `NS_ENUM` 在 Objective-C++ 语境下可能会有兼容性问题，所以这里做了一层兜底处理。

#### 主线程判断

**dispatch_main_sync_safe** 宏是一个保证 block 在主线程执行的方法。
在之前的版本中，主线程判断使用的是 `NSThread`。

```C++
#define dispatch_main_sync_safe(block)\
    if ([NSThread isMainThread]) {\
        block();\
    } else {\
        dispatch_sync(dispatch_get_main_queue(), block);\
    }
```

但是这个方法有个问题：**它只能判断线程是不是主线程，却无法判断当前是不是目标队列**。
所以后面又更新成了一个新的版本。

```C++
#ifndef dispatch_queue_async_safe
#define dispatch_queue_async_safe(queue, block)\
    if (strcmp(dispatch_queue_get_label(DISPATCH_CURRENT_QUEUE_LABEL), dispatch_queue_get_label(queue)) == 0) {\
        block();\
    } else {\
        dispatch_async(queue, block);\
    }
#endif

#ifndef dispatch_main_async_safe
#define dispatch_main_async_safe(block) dispatch_queue_async_safe(dispatch_get_main_queue(), block)
#endif
```

**strcmp()** 是 C 语言里的字符串比较函数。`strcmp(s1, s2)` 用来判断两个字符串是否相同，相同则返回 `0`。这里通过比较队列 label，尽量避免把本来就在目标队列上的任务再次异步派发。

这么做的原因可以参考[这个 issue](https://github.com/lionheart/openradar-mirror/issues/7053) 和[这篇文章](http://blog.benjamin-encz.de/post/main-queue-vs-main-thread/)。

#### 修改图片尺寸

有时候，后台传给我们的图片会有多种 scale，需要去适配屏幕大小。

这里的核心，就是根据图片命名里的 scale 标记去调整显示比例。

```C++
inline UIImage *SDScaledImageForKey(NSString * _Nullable key, UIImage * _Nullable image) {
    if (!image)
    {
        return nil;
    }
    
#if SD_MAC
    return image;
#elif SD_UIKIT || SD_WATCH
    //如果是动态图片，比如GIF图片，则迭代处理
    if ((image.images).count > 0)
    {
        NSMutableArray<UIImage *> *scaledImages = [NSMutableArray array];

        for (UIImage *tempImage in image.images) {
            [scaledImages addObject:SDScaledImageForKey(key, tempImage)];
        }
        
        UIImage *animatedImage = [UIImage animatedImageWithImages:scaledImages duration:image.duration];
        if (animatedImage) {
            animatedImage.sd_imageLoopCount = image.sd_imageLoopCount;
        }
        //把处理结束的图片再合成一张动态图片
        return animatedImage;
    }
    else
    {
#if SD_WATCH
        //判断screenScale方法是否存在
        if ([[WKInterfaceDevice currentDevice] respondsToSelector:@selector(screenScale)]) {
#elif SD_UIKIT
        //判断scale方法是否存在
        if ([[UIScreen mainScreen] respondsToSelector:@selector(scale)])
        {
#endif
            CGFloat scale = 1;
            // “@2x.png”的长度为7，所以此处添加了这个判断，很巧妙
            if (key.length >= 8)
            {
                NSRange range = [key rangeOfString:@"@2x."];
                if (range.location != NSNotFound) {
                    scale = 2.0;
                }
                //这里需要判断图片的大小
                range = [key rangeOfString:@"@3x."];
                if (range.location != NSNotFound) {
                    scale = 3.0;
                }
            }
            // 使用initWithCGImage来根据Core Graphics的图片构建UIImage。
            UIImage *scaledImage = [[UIImage alloc] initWithCGImage:image.CGImage scale:scale orientation:image.imageOrientation];
            image = scaledImage;
        }
        return image;
    }
#endif
}
```

## 图片加载的顺序

### 从磁盘里获取图片

1.磁盘区拷贝数据到内核缓冲区；

2.内核缓冲区复制数据到用户控件；

3.生成UIImageView并赋值；

4.如果图像是未解码的PNG/JPEG，就解码为位图数据；

5.CATransation捕获到UIImageView layer树变化；

6.主线程提交CATranstion开始渲染；

7.若没有字节对齐，先进行字节对齐；

8.GPU处理位图数据，开始渲染。
