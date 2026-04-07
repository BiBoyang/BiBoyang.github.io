---
layout: post
title:  "从虚拟内存到 iOS Memory Footprint"
date:   2018-11-03 23:32:53 +0800
categories: [iOS, Memory, System]
---


# DEAD in iOS Memory 

# 虚拟内存的来由
一个系统中的进程是与其他进程共享 CPU 和主存资源的。最开始我们直接访问物理内存地址，但是后来发现，这会带来各种各样的问题：
 1. **地址空间不隔离**   
 所有的进程都可以直接访问物理地址，那表明各个进程的内存空间不是互相隔离的。有些恶意的进程或者被注入恶意代码的进程非常容易去改写其他进程的内存数据，以达到破坏的目的。
 2. **内存使用效率低**    
 由于没有有效的内存管理机制，需要一个程序执行时，会将整个程序装入内存中然后开始执行。如果我们这个时候突然想要运行另外一个程序，那么很可能遇到内存空间不足。这时候有一种处理方法是将其他程序的数据暂时写到磁盘里面，等到用的时候再读回来。由于程序所需要的空间是连续的，那么在这个方法里，如果我们将程序A换出到磁盘所释放的内存空间是不够的，所以接着会将程序B换出到磁盘，然后将程序C读入到内存开始运行。我们可以看出来，整个过程中有大量的数据在换入换出，导致效率十分低下。
 3. **程序运行的地址不确定**  
    因为程序每次需要装入运行时，我们需要给它从内存中分配一块足够大的空闲区域，这个空闲区域的位置是不确定的。这给程序员的编写造成了一定的麻烦，因为程序在编写时，它访问数据和指令跳转的目标地址很多都是固定的，需要重定向。
     
这时候，就产生了一种解决方案：一种对主存的抽象概念，叫做 **虚拟内存**（Virtual Memory，下面为了简便可能会直接写成 `VM`）。

# 虚拟内存的作用

虚拟内存是硬件异常、硬件地址翻译、主存、磁盘文件和内核软件的完美交互，它为每个进程提供了一个大的、一致的和私有的地址空间。
虚拟内存提供了三个重要功能：

1. 它将主存看成是一个存储在磁盘上的地址空间的高速缓存，在主存中只保存活动区域，并根据需要在磁盘和主存之间来回传送数据；
2. 它为每个进程提供了一致的地址空间，从而简化了内存管理；
3. 它保护了每个进程的地址空间不被其他进程破坏。

VM是沉默的工作，不需要开发人员的任何干涉。但是，我们依然要注意它，原因有三：
> 1. **虚拟内存是核心的**       
        VM遍及计算机系统的所有层面，在硬件异常、汇编器、链接器、加载器、共享对象、文件和进程的设计中扮演着重要的角色。理解VM将帮助开发者更好的理解系统通常是如何工作的。（尤其是在iOS开发中！）
> 2. **虚拟内存是强大的**
        VM给予了应用程序强大的能力，可以创建和销毁内存片、将内存片映射到磁盘文件中的某个部分（mmap），以及与其他进程共享内存。理解VM将帮助你利用它的强大功能在应用程序中添加动力。 
> 3. **虚拟内存是危险的**
        每次应用程序引用一个变量、间接引用一个指针，或者调用一个诸如malloc这样的动态分配程序时，它就会和VM发生交互。如果VM使用不当，应用将遇到复杂危险的与内存有关的错误。理解VM可以帮助开发者规避这种错误。
   
# 寻址方式
计算机系统的主存可以被看作一个由 M 个连续字节组成的数组。每个字节都有一个唯一的物理地址（Physical Address）。第一个字节的地址为 0，下一个为 1，再往下是 2，以此类推。直接通过物理地址访问内存的方法，就是 **物理寻址**。
 
而现在，除了嵌入式设备和某些超级计算机以外，我们更多使用 **虚拟寻址** 来取代物理寻址。
 
使用虚拟寻址时，CPU 先生成一个虚拟地址（Virtual Address）来访问主存，这个虚拟地址在送到内存之前，会先被转换成真正的物理地址。这个过程就叫做地址翻译。

 
# 地址空间
地址空间是一个线性的非负整数地址的有序集合：
> 如果像是{0,1,2,……}一样，我们可以称之为线性地址空间。
> 分为虚拟地址空间和物理地址空间，分别对应虚拟内存和物理内存。
    地址空间帮助我们区分了数据对象（字节）和它们的属性（地址）。主存中的每字节都有一个选自虚拟空间的虚拟地址和一个选自物理空间的物理地址。
 
# 页
（注意，这里只讲了页式虚拟内存，还有另外一种段式虚拟内存，也可以把页式当成一种特殊的段式）

现代操作系统将内存划分为页，来简化内存管理，一个页其实就是一段连续的内存地址的集合，通常有 4k 和 16k（iOS 64 位是 16K）的，成为 Virtual Page 虚拟页。与之对应的物理内存被称为 Physical Page 物理页。

注意 虚拟页的个数可能和物理页个数不一样 比如说一个 64 位操作系统中使用 48 位地址空间的 虚拟页大小为 16K，那么其虚拟页可数可达到（2^48 / 2^14 = 16M 个）假设物理内存只有 4G 那么物理页可能只有 (2^32 / 2^14 = 256k 个)。

任何时刻，虚拟页面的集合都分为三个不相交的子集：
> 1. **未分配的**
        VM系统还未分配的（或者创建）的页。未分配的块没有任何数据和它们相关联，因此也就不占用任何磁盘空间。
> 2. **缓存的**
        当前已缓存在物理内存中的已分配页。
> 3. **未缓存的**
        未缓存在物理内存中的已分配页。

#### DRAM中的结构

我们用SRAM（静态RAM）来表示L1、L2和L3高速缓存，用DRAM（动态RAM）表示虚拟内存中的缓存（它在主页中缓存虚拟页）。   

在缓存层级里，DRAM 未命中比 SRAM 要昂贵得多，因为 SRAM 未命中还可以让 DRAM 兜底，而 DRAM 未命中就只能让磁盘来兜底（磁盘比 DRAM 慢很多很多，而且随机读取第一个字节的成本尤其高）。也正因为如此，虚拟页通常会设置得比较大，常见有 `4KB ~ 2MB` 这种量级。从抽象上看，虚拟页到物理页的映射并不像 CPU cache 那样被固定到某一个位置，而是由页表来决定。

#### 页表
操作系统使用页表（PageTable），将虚拟页映射到物理页。每次地址翻译硬件将一个虚拟地址转换为物理地址时，都会读取页表。

页表实际上是一个页表条目（Page Table Entry，PTE）的数组。虚拟地址空间中的每个页在页表中一个固定偏移处都有一个PTE。


# 缺页
假如DRAM缓存未命中，被称之为缺页（page fault）。当缺页发生时，会启动内核中的缺页异常程序，选择一个牺牲页，进行磁盘和内存中数据的交换。

在 iOS 系统里，开发者平时更直接感受到的，往往不是经典桌面系统里那种“磁盘交换”的体验，而是 `memory warning`、`compressed memory` 和最终的 `jetsam / OOM` 压力。不过从原理上讲，缺页和映射这些底层机制并没有消失，尤其在 `mmap` 这类场景里依然值得理解。

# 虚拟内存的内存管理
VM 为每个进程都提供了一个独立的页表，也就意味着每个进程都有一套独立的虚拟地址空间。使用 VM 会带来很多优点：
> 1. **简化链接**   
        每个独立的地址空间允许每个进程的内存映像使用相同的基本格式，而不管代码和数据实际存放在物理内存的何处。
> 2. **简化加载** 
        VM使得容易向内存中加载可执行文件和共享对象文件。
> 3. **简化共享**
        独立的地址空间为操作系统提供了一个管理用户进程和操作系统自身之间共享的一致机制。
> 4. **简化内存分配**
        假如遇到需要共享内存数据的时候，VM机制可以帮助我们有选择的访问共享页面。

# 内存保护
我们应该明白，不应该允许一个用户进程任意修改它的只读代码段；不允许修改内核的代码和数据结构；不允许读写其他进程的私有内存。
为了提供这种保护，地址翻译机制会在读取PTE的时候，添加一些额外的许可位来控制虚拟页面。

# 地址翻译
`n` 位的虚拟地址包含两个部分：`p` 位的虚拟页面偏移（VPO）和一个 `(n-p)` 位的虚拟页号（VPN）。MMU 使用 VPN 来选择适当的 PTE。
 **这里详细细节查看《深入理解计算机系统》（第三版）p568-p570**
 
## TLB

每次 CPU 产生一个地址，MMU 就必须查阅一个 PTE，以便把虚拟地址翻译成物理地址。这会带来额外开销。如何解决呢？答案很简单：继续用缓存。这里我们使用一个叫做 **翻译后备缓冲器**（Translation Lookaside Buffer，TLB）的东西来加速地址翻译。当 TLB 未命中时，MMU 再去更低层获取对应的 PTE，然后把它放回 TLB。

## 多级页表
一般来说，系统的地址空间也是有限的，我们不能每次都要一起访问整个页表。这里我们可以使用 **多级页表**技术。

一级页表对应二级页表，二级页表对应虚拟内存页面。我们只要把一级页表一直放到主存中就好了，需要的时候再去访问二级页表。

## 现代系统中的虚拟地址空间
操作系统一般都会为每个进程维护一个单独的虚拟地址空间，大体可以分成两部分：
> * **内核虚拟内存**
        包含内核中的代码和数据结构，还有一些被映射到所有进程共享的内存页面。还有一些页表，内核在进程上下文中执行代码使用的栈。
> * **进程虚拟内存**
        OS 将内存组织成一些区域（Segment）的集合，代码段、数据段、共享库、线程栈都是不同的区域。分段的原因是便于管理内存权限；如果了解过 Mach-O 或 ELF，会发现相同 Segment 内的内存权限通常是一致的，而每个 Segment 之下还会继续细分成不同的 section。


# 内存映射 （mmap）

> 在Linux中，通过将一个虚拟内存区域与一个磁盘上的对象关联起来，以初始化这个虚拟内存区域的内容。

大致过程如下：进程先在虚拟地址空间中创建虚拟映射区域，然后内核开始调用mmap函数，实现物理地址和虚拟地址的映射。

实现细节可以查看 **《深入理解计算机系统》（第三版）p582-p586**

我们需要记住：`mmap` 为共享库、创建新进程以及加载程序都提供了一个高效机制。应用也可以使用 `mmap` 来手工地创建和删除虚拟地址空间中的某些区域。
而mmap在iOS的用处：

> 1. mmap让读写一个文件像操作一个内存地址一样简单方便，
> 2. mmap效率极高，不用将一个内容从磁盘读入内核态再拷贝至用户态
> 3. `mmap` 映射的文件由操作系统接管，在某些场景下即使进程崩溃，数据一致性也比手工读写更容易管理。

通过以上的特点，我们可以在图片加载（例如[FastImageCache](https://github.com/path/FastImageCache)），数据存储以及关键的crash收集上报中使用。

# 动态内存分配

在运行时需要额外的虚拟内存时，使用动态内存分配器会更方便，也更有可移植性。
动态内存分配器维护着一个进程的虚拟内存区域，称之为 **堆**。堆可以被视为一组大小不同的块（block）的集合。这些块要不然就是分配的，要不然就是空闲的。
分配器有两种基本风格，两种风格都要求显式的分配块：
> * 显式分配器 （手动管理内存，严格来讲 ARC 也算这一路的变种）
> * 隐式分配器 （垃圾收集，Java等语言采用这种）

显式分配器的实现细节可以查看 **《深入理解计算机系统》（第三版）p587-p605**。十分推荐 iOS 开发也去读一读，很多时候跳出来看一下原理，会让自己有新的认知。
隐式分配器或者说垃圾收集实现细节可以查看 **《深入理解计算机系统》（第三版）p605-p609**。
因为我对使用 GC 的语言没什么系统研究，两者的区别优劣我不敢下特别重的结论，不过可以看一下这篇文章 [Garbage Collection vs Automatic Reference Counting](https://medium.com/computed-comparisons/garbage-collection-vs-automatic-reference-counting-a420bd4c7c81)。
[倾寒](https://www.valiantcat.cn/)推荐这个代码[C + + 实现一个简易的内存池分配器](https://blog.csdn.net/oyoung_2012/article/details/78874869)，也可以看一下。

# iOS Memory

上面提到的“页”这个概念，在 iOS 里同样成立。也就是说，前面这些看起来很像操作系统课内容的东西，和 iOS 并不是割裂的。

我们可以使用以下代码来查看数据
```C++
#import <UIKit/UIKit.h>
#import "AppDelegate.h"
#import "mach/mach.h"

int main(int argc, char * argv[]) {
    @autoreleasepool {
        printf("page-size:%ld \nmask:%ld\nshift:%d \n", vm_kernel_page_size, vm_kernel_page_mask, vm_kernel_page_shift);
        printf("%ld\n", sysconf(_SC_PAGE_SIZE));
        printf("%d\n", getpagesize());
        printf("%lu\n", PAGE_SIZE);
        return UIApplicationMain(argc, argv, nil, NSStringFromClass([AppDelegate class]));
    }
}
```
得到的数据为（iPhone 8 plus和iPhone SE）：
```C++
page-size:16384 
mask:16383
shift:14 
16384
16384
16384 = 16kb
```
我们用以上数据可以得知：页大小为 `16KB`，也就是页偏移量对应 `14` 位。这里依然会用到上文提过的 TLB 来加速地址翻译。
在我们未写入数据，但是刚刚被操作系统分配或者磁盘映射的时候，内存都是出于 **Clean**的状态，但是一旦被写入了，操作系统会将它标记为 **Dirty**。
> * **Clean**
        指的是能够被系统清理出内存并且在有需要的时候重新加载的数据，包括：Memory mapped files；Frameworks中的__DATA_CONST部分；应用的二进制可执行文件。
> * **Dirty**
        指的是不能被系统回收的内存占用，包括：堆上的对象；图片解码数据；Frameworks中的__DATA和__DATA_DIRTY部分。

标记的一个好处在于：因为Dirty页面已经被写入数据，是要比Clean重要的多的。当操作系统发现内存十分紧张的时候，会尝试驱逐一部分内存页面。Clean的页面会因为优先级的原因被首先驱逐，并开始和磁盘（中的backing store部分）交换分区，等到需要使用的时候再去读取。
但是这里要注意一点：在 iOS 上，开发者更常直接感受到的不是传统桌面系统里那种“明显的 swap 体验”，而是 **Compressed Memory** 和系统的内存回收 / 杀进程策略。也就是说，当内存紧张时，系统会优先尝试压缩一部分不活跃内存，而不是让开发者像在桌面环境里那样直接感知到磁盘交换。

> * When your system’s memory begins to fill up, Compressed Memory automatically compresses the least recently used items in memory, compacting them to about half their original size. When these items are needed again, they can be instantly uncompressed.

这个举措，特点可以归纳为:
> * 减少了不活跃内存占用      
> * 改善了电源效率，通过压缩减少磁盘IO带来的损耗     
> * 压缩/解压十分迅速，能够尽可能减少 CPU 的时间开销     
> * 支持多核操作      

从 footprint 统计的视角看，**Compressed Memory** 依然属于我们需要认真对待的内存压力来源。

**memory footprint = dirty size + compressed size ，这也就是我们需要并且能够尝试去减少的内存占用**

当我们的 App 的 memory footprint 达到一定程度时，就可能收到内存警告（Memory Warnings）。

如果我们收到了内存警告，系统本身会尝试释放一部分可回收内容（例如 `NSCache` 一类机制），同时也会向当前运行的程序发送低内存警告，我们自己也要对此作出响应。

UIKit中有几种接受低内存警告的方法：
> 1. applicationDidReceiveMemoryWarning:方法；     
> 2. 在UIViewController中重写didReceiveMemoryWarning；       
> 3. 注册接受UIApplicationDidReceiveMemoryWarningNotification通知     
如果我们对此置之不理，程序有可能直接被干掉，那时候我们就会陷入OOM的困境之中。

# 监测内存的工具
## Xcode
命令行工具暂且不提，那套更加适合MacOS。
在Xcode中，我们可以使用三种工具来测量内存：
> 1. Xcode memory gauge     
> 2. Instruments(主要是Leaks、Allocation、Counters以及System Trace中的Virtual Memory Trace)      
> 3. Xcode Memory Debugger      

![Xcode memory gauge](https://ws4.sinaimg.cn/large/006tNbRwly1fwpuwrudttj31kw0yj7wh.jpg)

![Instruments](https://ws4.sinaimg.cn/large/006tNbRwly1fwpuxiyldxj31kw0yjjxf.jpg)

![Xcode Memory Debugger](https://ws2.sinaimg.cn/large/006tNbRwly1fwpuxr31mwj31kw0yje81.jpg)

在 Xcode 10 之后，当内存占用过大时，也可能触发 debugger，自动捕获 `EXC_RESOURCE RESOURCE_TYPE_MEMORY` 异常，并断在对应的位置。
![](https://ws1.sinaimg.cn/large/006tNbRwly1fwpviiqyrhj31kw0w07fh.jpg)

在 `Product -> Scheme -> Edit Scheme -> Diagnostics` 中开启 `Malloc Stack` 功能，建议配合 **Live Allocations Only** 选项使用。这样会在 lldb 中记录调试过程中对象创建的堆栈，配合 `malloc_history` 工具，可以更方便地定位高内存对象的创建位置。

## 代码方法
获取应用使用真实物理内存值的代码：
```C++
- (NSUInteger)getResidentMemory
{
    struct mach_task_basic_info info;
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
	
	int r = task_info(mach_task_self(), MACH_TASK_BASIC_INFO, (task_info_t)& info, & count);
	if (r == KERN_SUCCESS)
	{
		return info.resident_size;
	}
	else
	{
		return -1;
	}
}
```
## 线上内存检测工具
1. [MLeaksFinder](https://github.com/Tencent/MLeaksFinder)       
2. [FBRetainCycleDetector](https://github.com/facebook/FBRetainCycleDetector)        
3. [OOMDetector](https://github.com/Tencent/OOMDetector)     

当然，我们也可以自己在理解内存检测的原理之后，自己去实现一些轮子，以更加贴合自己的使用场景。


# 如何注意内存优化

1. 多用懒加载     
2. `weak` 替代 `unsafe_unretained`，并且谨慎使用 `assign`；       
3. 安全的使用weak；        
4. 可以尝试多用autoreleasepool（但是不要滥用，这个不是毫无代价的）；        
5. 对 UI、动画机制深入了解，尤其是动画以及Cell复用机制；     
6. imageName：        
7. performSelect谨慎使用；        
8. 倒计时使用注意，设计一定要严谨；      
9. 多使用Cache而非dictionary；     
10. 监测性能组件使用mmap存放读取数据；       
11. 注意 `NSDateFormatter` 的使用；      
12. 谨慎小心的使用指针，小心野指针；     
13. WKWebView 是跨进程通信的，不会占用我们的 APP 使用的物理内存量，**但是依然要小心谨慎的测量**；     
14. 在保证安全的前提下，选用一些更小的数据结构；       
15. 特别大的贴图要谨慎使用；     
16. 谨慎小心地使用指针；       
17. `NSDateFormatter` 这种高开销对象尽量复用。       

# 后续记录计划
这篇其实还远远没有讲完，后面我还想继续记录：

- `SLC / MLC / TLC` 的差异，以及为什么移动设备会大量使用 `TLC`
- `OOM` 到底是什么，和 `memory warning`、`jetsam` 的关系是什么
- 如何设计一个真正线上可用的内存监测组件
- `如何注意内存优化` 这一节里每一条建议的展开说明

# 参考和鸣谢
《程序员的自我修养-链接、装载和库》第一版（第十章）           
《深入理解计算机系统》第三版（第九章）             
《iOS 和 macOS 性能优化：Cocoa、Cocoa Touch、Objective-C 和 Swift》第一版（第五章）                
《高性能iOS应用开发》 第一版-第二章        
《Effective Objective-C 2.0 编写高质量iOS与OS X代码的52个有效方法》第五十条     
[WWDC 2018-Session 416： iOS Memory Deep Dive](https://developer.apple.com/videos/play/wwdc2018/416/)        
[iOS Memory Deep Dive](https://www.valiantcat.cn/index.php/2018/10/06/64.html#menu_index_40)        
[OS X Mavericks Core Technology Overview](https://images.apple.com/media/us/osx/2013/docs/OSX_Mavericks_Core_Technology_Overview.pdf)       
[Memory Usage Performance Guidelines](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/ManagingMemory/ManagingMemory.html)      
[Instruments Help](https://help.apple.com/instruments/mac/current/#//apple_ref/doc/uid/TP40004652)      
[iOS-Monitor-Platform](https://aozhimin.github.io/iOS-Monitor-Platform/)        
感谢[倾寒](https://github.com/ValiantCat)、[冬瓜](https://github.com/Desgard)在创作中给予的帮助。
