#!/usr/bin/env python3
"""build-books.py — 从 chapters.txt manifest 构建 mdBook 小册。

用法:
    cd /Users/boyang/Documents/UGit/BiBoyang.github.io
    python3 book-src/build-books.py all            # 构建全部
    python3 book-src/build-books.py agent-ui       # 构建单册

每册一个目录 book-src/<name>/:
    book.toml      mdBook 配置（产物输出到博客 books/<name>/，Jekyll 原样透传）
    chapters.txt   目录清单（唯一顺序权威；调顺序/微调标题只改这里）
    src/           生成物，勿手改

chapters.txt 行格式（以「 | 」分隔）:
    !mode raw|post   取源模式。raw=源 md 原样拷贝；
                     post=博客 post：剥 front matter 与文首「系列导航」引用块、
                     注入 H1 标题、正文 H1 降一级（跳过代码围栏）
    # 文字           分卷标题（写入 SUMMARY.md）
    @ slug | 标题 [| 源文件绝对路径]    前置章节（不编号）
    - slug | 标题 [| 源文件绝对路径]    正文章节
    源文件路径可省略，默认取本册 chapters/<slug>.md（书内容正典，可直接手改）。
    空行与其余 ! 开头的行为注释。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BOOKS = ["agent-ui", "eval-series"]


def parse_manifest(path: Path, book_dir: Path):
    mode = "raw"
    entries = []  # (kind, slug, title, source)  kind: part | prefix | chapter
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("!mode"):
            mode = line.split(None, 1)[1].strip()
            if mode not in ("raw", "post"):
                raise SystemExit(f"{path}:{lineno} 未知 mode: {mode}")
            continue
        if line.startswith("!"):
            continue
        if line.startswith("# "):
            entries.append(("part", None, line[2:].strip(), None))
            continue
        if line.startswith("@ ") or line.startswith("- "):
            kind = "prefix" if line[0] == "@" else "chapter"
            parts = [p.strip() for p in line[2:].split(" | ")]
            if len(parts) == 2:
                parts.append(str(book_dir / "chapters" / f"{parts[0]}.md"))
            if len(parts) != 3:
                raise SystemExit(f"{path}:{lineno} 格式错误（应为 slug | 标题 [| 源文件]）: {line}")
            entries.append((kind, parts[0], parts[1], Path(parts[2]).expanduser()))
            continue
        raise SystemExit(f"{path}:{lineno} 无法识别的行: {line}")
    return mode, entries


def strip_front_matter(text: str):
    """剥 YAML front matter，返回 (title 或 None, body)。"""
    title, body = None, text
    if text.startswith("---"):
        lines = text.splitlines()
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                for h in lines[1:i]:
                    m = re.match(r'title:\s*"(.*)"\s*$', h.strip())
                    if m:
                        title = m.group(1)
                body = "\n".join(lines[i + 1:])
                break
    return title, body


def strip_series_block(body: str) -> str:
    """剥正文开头紧跟的博客专用引用块：「系列导航」块（> **系列 开头）和
    「成册横幅」块（> 本系列已集结成 开头，书里是自指链接）。"""
    lines = body.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines) and (
        lines[i].startswith("> **系列") or lines[i].startswith("> 本系列已集结成")
    ):
        while i < len(lines) and lines[i].startswith(">"):
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    return "\n".join(lines[i:])


def demote_h1(body: str) -> str:
    """正文里列 0 的 H1 降一级（跳过代码围栏）。"""
    out, in_fence = [], False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
        if not in_fence and line.startswith("# "):
            line = "#" + line
        out.append(line)
    return "\n".join(out)


def transform(source: Path, mode: str, fallback_title: str) -> str:
    text = source.read_text(encoding="utf-8").lstrip("﻿")
    if mode == "raw":
        return text if text.endswith("\n") else text + "\n"
    title, body = strip_front_matter(text)
    body = demote_h1(strip_series_block(body))
    return f"# {title or fallback_title}\n\n{body.strip()}\n"


def build(book: str) -> None:
    book_dir = REPO / "book-src" / book
    src_dir = book_dir / "src"
    mode, entries = parse_manifest(book_dir / "chapters.txt", book_dir)

    if src_dir.exists():
        shutil.rmtree(src_dir)
    src_dir.mkdir(parents=True)

    summary = ["# Summary", ""]
    n = 0
    for kind, slug, title, source in entries:
        if kind == "part":
            summary += ["", f"# {title}", ""]
            continue
        if not source.is_file():
            raise SystemExit(f"源文件不存在: {source}")
        (src_dir / f"{slug}.md").write_text(transform(source, mode, title), encoding="utf-8")
        n += 1
        summary.append(f"[{title}]({slug}.md)" if kind == "prefix" else f"- [{title}]({slug}.md)")
        if kind == "prefix":
            summary.append("")
    (src_dir / "SUMMARY.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    subprocess.run(["mdbook", "build"], cwd=book_dir, check=True)
    print(f"[ok] {book}: {n} 章 → books/{book}/")


def main() -> None:
    targets = sys.argv[1:] or ["all"]
    if targets == ["all"]:
        targets = BOOKS
    for book in targets:
        if book not in BOOKS:
            raise SystemExit(f"未知小册: {book}（可选: {', '.join(BOOKS)} 或 all）")
        build(book)


if __name__ == "__main__":
    main()
