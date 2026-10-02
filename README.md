# BiBoyang's Blog

欢迎访问我的个人博客！

## 小册子（/books/）

系列文章的网页成书版：mdBook 构建，产物提交进 `books/<册名>/`，由 Jekyll 原样透传（GitHub Pages 跑不了 mdBook，产物必须随仓库走）。

- `book-src/<册名>/chapters.txt`：目录清单，**章节顺序与侧栏标题的唯一权威**——新增篇目、调顺序、微调标题都只改这里
- `book-src/agent-ui/chapters/`：《Agent 时代的开发者界面》书内容正典，**微调正文直接改这里**（已与 Desktop 写作目录解耦，此处的修订不会回流原稿，互不干扰）
- `book-src/eval-series/`：《我的评测工具链》无独立副本，内容源即 `_posts/` 单篇（博客与书同源，改 post 即改书）
- `book-src/build-books.py`：取源 → 转换（post 模式剥 front matter 与系列导航块、注入 H1、H1 降级）→ `mdbook build`
- `book-src/<册名>/src/`：生成物，勿手改

重建小册：

```bash
cd /Users/boyang/Documents/UGit/BiBoyang.github.io && python3 book-src/build-books.py all
```

本地预览整站见 AGENTS.md。
