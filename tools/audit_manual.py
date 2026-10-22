"""手册体检：只做三件机械的事，不下判断。

1. 判据覆盖——哪些小节只有步骤、没有"做完看到什么"
2. 强断言清单——列出所有"不会/一定/无法/绝不"等绝对化句子，供人核边界
3. 数字清单——把手册里所有带单位的数字列出来，供人和代码对账

不判断对错。事实判断留在人手里，脚本只负责不漏。
用法：py tools/audit_manual.py [--verbose]
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "USER_GUIDE.md"
VERBOSE = "--verbose" in sys.argv

# 一个"操作小节"应该至少带一个这类标签，否则读者不知道做完对不对
MARKERS = ("判据：", "注意：", "失败排除", "状态收尾", "依次排除")
# 不套"判据"标准的小节：0-x 是边界与纪律，5-x 本身整节就是失败清单，3-1 是页面说明
SKIP_SECTIONS = re.compile(r"^(0-\d|5-\d|3-1)")
# 绝对化措辞：不是错，是"必须能说出依据"的地方
STRONG = ("不会", "绝不", "一定", "必然", "保证", "无法", "不可能", "永远")
# 带单位的数字：秒 / 毫秒 / 像素 / 百分比 / 度 / 米 / 档
NUM = re.compile(r"(\d+(?:\.\d+)?)\s*(秒|毫秒|像素|%|度|米|档|ms|px)")

def main() -> int:
    if not MANUAL.exists():
        print(f"找不到 {MANUAL}")
        return 2
    lines = MANUAL.read_text(encoding="utf-8").splitlines()

    # ── 1. 判据覆盖：按 ## 切块，看每块有没有标签 ──
    sections, cur = [], None
    for i, ln in enumerate(lines, 1):
        if ln.startswith("## "):
            cur = {"title": ln[3:].strip(), "line": i, "body": []}
            sections.append(cur)
        elif cur is not None:
            cur["body"].append(ln)
    # 只检查"操作型"小节（1-x / 2-x / 3-x / 4-x / 5-x），章节导语不算
    op = [s for s in sections
          if re.match(r"^\d+-\d+", s["title"]) and not SKIP_SECTIONS.match(s["title"])]
    lacking = [s for s in op
               if not any(m in "\n".join(s["body"]) for m in MARKERS)]

    print(f"一、判据覆盖")
    print(f"    操作小节 {len(op)} 个，全部带判据类标签 {len(op) - len(lacking)} 个")
    for s in lacking:
        print(f"    ✗ 第 {s['line']} 行「{s['title']}」没有任何判据/注意/失败排除")
    if not lacking:
        print("    ✓ 每个操作小节都有可核对的收尾")

    # ── 2. 强断言清单 ──
    hits = [(i, ln.strip()) for i, ln in enumerate(lines, 1)
            if any(w in ln for w in STRONG)]
    print(f"\n二、强断言 {len(hits)} 处（需人工确认每句都有代码依据）")
    for i, ln in hits:
        print(f"    {i:4d}  {ln[:88]}")
    if not VERBOSE:
        print("    （用 --verbose 看全部）")

    # ── 3. 数字清单 ──
    nums = {}
    for i, ln in enumerate(lines, 1):
        for m in NUM.finditer(ln):
            nums.setdefault(f"{m.group(1)} {m.group(2)}", []).append(i)
    print(f"\n三、带单位的数字 {len(nums)} 种（逐个和代码/出厂配置对账）")
    for k, v in sorted(nums.items(), key=lambda x: -len(x[1])):
        where = f"第 {v[0]} 行" + (f" 等 {len(v)} 处" if len(v) > 1 else "")
        print(f"    {k:14s} {where}")

    print(f"\n合计：{len(lacking)} 处缺判据 / {len(hits)} 处强断言 / {len(nums)} 种数字")
    return 0 if not lacking else 1


if __name__ == "__main__":
    sys.exit(main())
