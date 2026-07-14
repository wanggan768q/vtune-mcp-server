"""对比两个 VTune hotspots CSV fixture 文件。

用法:
    python tests/compare_fixtures.py
    python tests/compare_fixtures.py --top 20
    python tests/compare_fixtures.py --search OnPhysScenePreStep
"""

import csv
import sys
from pathlib import Path
from typing import Dict

FIXTURES = Path(__file__).resolve().parent / "fixtures"
A = FIXTURES / "r354hs_hotspots_full.csv"
B = FIXTURES / "r361hs_hotspots_full.csv"


def load(path: Path) -> Dict[str, float]:
    """解析 VTune CSV (tab 分隔), 返回 Function -> CPU Time."""
    data: Dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            name = row.get("Function", "").strip()
            try:
                cpu = float(row.get("CPU Time", "0").strip() or 0)
            except ValueError:
                continue
            if name and name != "Function":
                data[name] = data.get(name, 0.0) + cpu
    return data


def search_compare(a: Dict[str, float], b: Dict[str, float], query: str):
    """搜索并对比两个版本的同一函数."""
    query = query.lower()
    matches_a = {k: v for k, v in a.items() if query in k.lower()}
    matches_b = {k: v for k, v in b.items() if query in k.lower()}
    all_keys = sorted(set(matches_a) | set(matches_b), key=lambda x: -(matches_b.get(x, 0) or matches_a.get(x, 0)))

    if not all_keys:
        print(f"not found: '{query}'")
        return

    print(f"{'Function':<80} {'r354hs(s)':>10} {'r361hs(s)':>10} {'Diff(s)':>10} {'Change%':>8}")
    print("-" * 120)
    for key in all_keys:
        va = matches_a.get(key, 0.0)
        vb = matches_b.get(key, 0.0)
        diff = vb - va
        pct = ((vb - va) / va * 100) if va else (float("inf") if vb else 0.0)
        sign = "+" if diff > 0 else ""
        pct_str = f"{sign}{pct:.1f}%" if pct != float("inf") else "new"
        absent = " (缺失)" if va == 0 or vb == 0 else ""
        print(f"{key:<80} {va:>10.3f} {vb:>10.3f} {diff:>+10.3f} {pct_str:>8}{absent}")


def compare(a: Dict[str, float], b: Dict[str, float], top: int = 30):
    all_keys = set(a) | set(b)
    rows = []
    for key in all_keys:
        va = a.get(key, 0.0)
        vb = b.get(key, 0.0)
        diff = vb - va
        pct = ((vb - va) / va * 100) if va else (float("inf") if vb else 0.0)
        rows.append((key, va, vb, diff, pct))

    rows.sort(key=lambda x: -x[2])

    header = f"{'Function':<60} {'r354hs(s)':>10} {'r361hs(s)':>10} {'Diff(s)':>10} {'Change%':>8}"
    print(header)
    print("-" * len(header))

    for key, va, vb, diff, pct in rows[:top]:
        sign = "+" if diff > 0 else ""
        pct_str = f"{sign}{pct:.1f}%" if pct != float("inf") else "new"
        print(f"{key:<60} {va:>10.3f} {vb:>10.3f} {diff:>+10.3f} {pct_str:>8}")

    print("\n--- 汇总 ---")
    print(f"r354hs 总函数数: {len(a)}, 总 CPU Time: {sum(a.values()):.3f}s")
    print(f"r361hs 总函数数: {len(b)}, 总 CPU Time: {sum(b.values()):.3f}s")

    only_a = set(a) - set(b)
    only_b = set(b) - set(a)
    if only_a:
        print(f"\n仅在 r354hs 出现 ({len(only_a)} 个):")
        for name in sorted(only_a, key=lambda x: -a[x])[:10]:
            print(f"  - {name}: {a[name]:.3f}s")
    if only_b:
        print(f"\n仅在 r361hs 出现 ({len(only_b)} 个):")
        for name in sorted(only_b, key=lambda x: -b[x])[:10]:
            print(f"  + {name}: {b[name]:.3f}s")


if __name__ == "__main__":
    top = 30
    search_query = None
    if "--top" in sys.argv:
        idx = sys.argv.index("--top")
        top = int(sys.argv[idx + 1])
    if "--search" in sys.argv:
        idx = sys.argv.index("--search")
        search_query = sys.argv[idx + 1]

    a_data = load(A)
    b_data = load(B)

    if search_query:
        search_compare(a_data, b_data, search_query)
    else:
        compare(a_data, b_data, top=top)
