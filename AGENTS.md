# AGENTS.md

Jekyll 博客（Minimal Mistakes remote theme），GitHub Pages 部署。

## 本地运行

系统自带 Ruby 2.6 太老，跑不起来。必须用 Homebrew ruby@3.3 + 用户目录的 bundler 2.6.5：

```bash
cd /Users/boyang/Documents/UGit/BiBoyang.github.io && PATH="/Users/boyang/.gem/ruby/3.3.0/bin:/opt/homebrew/opt/ruby@3.3/bin:$PATH" bundle exec jekyll serve
```

- 依赖装在仓库的 `vendor/bundle`（见 `.bundle/config`，勿提交 vendor 之外的 gem 缓存改动）。
- rubygems 走清华镜像（`.bundle/config`）。
- 预览地址：http://127.0.0.1:4000
