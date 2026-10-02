# BiBoyang's Blog

欢迎访问我的个人博客！

## 小册子（/books/）

系列文章的网页成书版：mdBook 构建，产物提交进 `books/<册名>/`，由 Jekyll 原样透传（GitHub Pages 跑不了 mdBook，产物必须随仓库走）。

- `book-src/<册名>/chapters.txt`：目录清单，**章节顺序与侧栏标题的唯一权威**——新增篇目、调顺序、微调标题都只改这里
- `book-src/build-books.py`：取源 → 转换（博客 post 剥 front matter 与系列导航块、注入 H1、H1 降级）→ `mdbook build`
- `book-src/<册名>/src/`：生成物，勿手改

重建小册：

```bash
cd /Users/boyang/Documents/UGit/BiBoyang.github.io && python3 book-src/build-books.py all
```

本地预览整站见 AGENTS.md。
