#!/usr/bin/env python3
"""check-xrefs.py — 小册「第 N 篇」互指审计（只读，不修改任何文件）。

用法:
    cd /Users/boyang/Documents/UGit/BiBoyang.github.io
    python3 book-src/check-xrefs.py agent-ui

核对三件事:
    A. 正文里的「第 N 篇」互指（含「界面部分第 N 篇」「基建第 N 篇」等带部分名形式，
       以及「第 13、14 篇」「第 3、7–12 篇」等并列/区间形式）能否按 chapters.txt
       的编号解析到正确章节；裸编号按惯例解析到「界面」部分。
       章首「系列第X篇」自标签不进本区（见 B）。
    B. 每章开头「系列第X篇」自标签与 chapters.txt 分配的编号是否一致。
    C. 疑似 slug 式编号引用（如「00b 的截断检测」「05 事件流模型」「基 02 的主线」），
       这类不走「第 N 篇」格式，编号重排后最容易腐烂；能解析的给出目标，不能解析的
       标记为疑似失效引用。

判定:
    OK              解析成功，部分名（若有）与目标所在部分一致
    ?? 越界         任何部分都没有这个编号
    !! 部分错配     带部分名，但该部分没有此编号（提示编号实际所在部分）
    ?? 歧义         裸编号在「界面」部分不存在，但在其它部分存在
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CN_DIGIT = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9}
PART_ALIAS = {
    "界面部分": "界面", "界面": "界面", "基建": "基建", "基": "基建",
    "评测卷": "评测", "评测": "评测", "胶水层": "胶水层", "胶水": "胶水层",
}

# 「第 N 篇」：N 支持阿拉伯/中文数字，、–-~, 分隔的并列与区间
REF_RE = re.compile(
    r"(界面部分|界面|基建|基|评测卷|评测|胶水层|胶水)?\s*第\s*"
    r"([0-9一二三四五六七八九十百、\-–~,\s]{1,24}?)\s*篇")
# 自标签：「系列第十八篇」「基建系列第二篇之上」「本文是系列第一篇」
SELF_RE = re.compile(
    r"系列第\s*([0-9一二三四五六七八九十百]{1,4})\s*篇\s*(?:之上|之下)?\s*(?=[。，]|$)")
# slug 式编号：「00b 的截断检测」「05 事件流模型」「基 02 的主线」「基01 拆过的」
# 排除日期（2026-10-04）、小数（0.75）、版本号（v1.2.1）等误报
SLUG_RE = re.compile(
    r"(?<![0-9A-Za-z第篇.\-:/_基])(\d{2}[ab]?)\s*"
    r"(?:的\s*[一-龥]|(?:事件流|模型|框架|机制|检测|结论|那张|提过|写过|拆过|讲过|税单|记分牌|地图|矩阵|清单|暗线|实录|状态机|问句|主线))"
    r"|(?:基建|基)\s*(\d{2}[ab上下]?)\s*(?:的|拆过|提过|写过|讲过|问过)")


def cn_to_int(s: str) -> int | None:
    """解析 1-99 的中文数字（十、二十一、二十四）。"""
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if "百" in s:
        return None
    total, seen_ten = 0, False
    for ch in s:
        if ch in CN_DIGIT:
            if seen_ten:
                total += CN_DIGIT[ch]
                seen_ten = False
            else:
                total = total * 10 + CN_DIGIT[ch] if total else CN_DIGIT[ch]
        elif ch == "十":
            total = (total or 1) * 10
            seen_ten = True
        else:
            return None
    return total or None


def parse_manifest(book_dir: Path):
    """返回 (parts, entries)：parts=[部分名...]（按出现顺序）；
    entries=[(kind, slug, number, suffix, title, part)]，按阅读顺序。"""
    parts: list[str] = []
    entries = []
    current_part = None
    for raw in (book_dir / "chapters.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("!"):
            continue
        if line.startswith("# "):
            current_part = line[2:].strip()
            parts.append(current_part)
            continue
        if line.startswith("@ ") or line.startswith("- "):
            slug, title = [p.strip() for p in line[2:].split(" | ")][:2]
            m = re.match(r"^(\d+)([上下ab]?)\s*·\s*(.+)$", title)
            if m:
                entries.append(("numbered", slug, int(m.group(1)), m.group(2),
                                m.group(3), current_part))
            else:
                entries.append(("prefix", slug, None, "", title, current_part))
    return parts, entries


def split_numbers(expr: str) -> list[int]:
    """把「13、14」「3、7–12」「2-4」解析成编号列表；无法解析时返回 []。"""
    expr = expr.strip()
    if not expr:
        return []
    if re.fullmatch(r"[0-9]{1,3}", expr):
        return [int(expr)]
    if re.fullmatch(r"[一二三四五六七八九十]{1,3}", expr):
        n = cn_to_int(expr)
        return [n] if n else []
    nums: list[int] = []
    for token in re.split(r"[、,，\s]+", expr):
        if not token:
            continue
        rng = re.split(r"[-–~]", token)
        if len(rng) == 2:
            a, b = cn_to_int(rng[0].strip()), cn_to_int(rng[1].strip())
            if a and b and a <= b and b - a <= 30:
                nums.extend(range(a, b + 1))
                continue
            return []
        n = cn_to_int(token)
        if not n:
            return []
        nums.append(n)
    return nums


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    book = sys.argv[1]
    book_dir = REPO / "book-src" / book
    parts, entries = parse_manifest(book_dir)

    # 编号索引：部分 -> {编号: (slug, suffix, title)}
    index: dict[str, dict[int, tuple[str, str, str]]] = {p: {} for p in parts}
    own_number: dict[str, tuple[int, str]] = {}  # slug -> (编号, 部分)
    for kind, slug, num, suffix, title, part in entries:
        if kind == "numbered":
            index[part][num] = (slug, suffix, title)
            own_number[slug] = (num, part)

    ui = "界面" if "界面" in parts else parts[0]
    n_prefix = sum(1 for e in entries if e[0] == "prefix")
    a_lines: list[str] = []
    b_lines: list[str] = []
    c_lines: list[str] = []
    n_ok = n_bad = 0

    for kind, slug, num, suffix, title, part in entries:
        path = book_dir / "chapters" / f"{slug}.md"
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # C. slug 式编号引用
            for m in SLUG_RE.finditer(line):
                frag = m.group(0).strip()
                if m.group(2):  # 「基NN 的」形式：在基建部分内解析
                    n = int(m.group(2)[:2])
                    hit = index.get("基建", {}).get(n)
                    if hit:
                        note = f"→ 基建 {n:02d} · {hit[2]}（可解析，建议统一为「基建第 {n} 篇」）"
                    else:
                        note = "→ 基建部分无此编号，疑似失效引用"
                    c_lines.append(f"  {slug}.md:{lineno}  「{frag}」  {note}")
                else:  # 裸「NN 的XX」：列出各部分的候选，人工判定
                    n = int(m.group(1)[:2])
                    cands = [f"{p} {n:02d} · {index[p][n][2]}"
                             for p in parts if n in index[p]]
                    if cands:
                        note = f"→ 候选：{'；'.join(cands)}（裸编号，请人工确认想指哪个）"
                    else:
                        note = "→ 任何部分都无此编号，疑似失效引用"
                    c_lines.append(f"  {slug}.md:{lineno}  「{frag}」  {note}")
            # B. 自标签
            for m in SELF_RE.finditer(line):
                n = cn_to_int(m.group(1))
                if slug in own_number and n is not None and n != own_number[slug][0]:
                    b_lines.append(
                        f"  {slug}.md:{lineno}  自标签「系列第{m.group(1)}篇」"
                        f"但 chapters.txt 分配为第 {own_number[slug][0]:02d} 篇"
                        f"（{own_number[slug][1]}）")
            # A. 第 N 篇互指（自标签句不进本区）
            for m in REF_RE.finditer(line):
                if re.match(r"\s*(?:之上|之下)?\s*[。，]", line[m.end():]):
                    continue  # 自标签，归 B 区
                prefix, expr = m.group(1), m.group(2)
                if prefix and prefix not in PART_ALIAS:
                    continue
                want_part = PART_ALIAS.get(prefix) if prefix else None
                for n in split_numbers(expr):
                    if want_part:
                        hit = index.get(want_part, {}).get(n)
                        if hit:
                            status, tag = f"OK → {want_part} {n:02d} · {hit[2]}", "ok"
                        else:
                            other = [p for p in parts if n in index[p]]
                            hint = f"（该编号在：{'、'.join(other)}）" if other else ""
                            status, tag = f"!! 部分错配：「{prefix}第{n}篇」在{want_part}不存在{hint}", "bad"
                    else:
                        hit = index.get(ui, {}).get(n)
                        if hit:
                            status, tag = f"OK → {ui} {n:02d} · {hit[2]}", "ok"
                        else:
                            other = [p for p in parts if p != ui and n in index[p]]
                            if other:
                                status, tag = f"?? 歧义：裸「第{n}篇」在{ui}不存在，但在 {'、'.join(other)} 存在", "bad"
                            else:
                                status, tag = f"?? 越界：任何部分都没有第 {n} 篇", "bad"
                    if tag == "ok":
                        n_ok += 1
                    else:
                        n_bad += 1
                    a_lines.append(f"  {slug}.md:{lineno}  「{m.group(0).strip()}」  {status}")

    print(f"== {book} 互指审计 ==  目录条目 {len(entries)}"
          f"（编号章 {len(entries) - n_prefix} + 前置 {n_prefix}），部分：{' / '.join(parts)}")
    print(f"\n[A] 「第 N 篇」互指：{n_ok} 条可解析，{n_bad} 条可疑")
    print("\n".join(a_lines) if a_lines else "  （无）")
    print(f"\n[B] 「系列第X篇」自标签不一致：{len(b_lines)} 处")
    print("\n".join(b_lines) if b_lines else "  （无）")
    print(f"\n[C] 疑似 slug 式编号引用（人工确认）：{len(c_lines)} 处")
    print("\n".join(c_lines) if c_lines else "  （无）")


if __name__ == "__main__":
    main()
