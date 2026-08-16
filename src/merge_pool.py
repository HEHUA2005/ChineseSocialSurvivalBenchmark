"""扩量题目合并工具：把多批 MC 题目按场景去重合并回 mc_raw，供全量质检。

用法：python3 -m src.merge_pool --mc --trap
"""
import argparse
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def merge_mc():
    seen, merged = set(), {}
    for d in sorted(Path("data/out").glob("mc_raw_b*")) + [Path("data/out/mc_raw")]:
        for f in sorted(d.glob("*.json")):
            for q in json.load(open(f, encoding="utf-8")):
                key = q.get("scenario", "")[:40]
                if key in seen:
                    continue
                seen.add(key)
                merged.setdefault(q.get("dimension", "其他"), []).append(q)
    out = Path("data/out/mc_raw")
    for dim, items in merged.items():
        (out / f"{dim}.json").write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    n = sum(len(v) for v in merged.values())
    print(f"MC 合并去重后: {n} 题（{len(merged)} 维度）→ {out}")


def merge_trap():
    seen, merged = set(), []
    for d in sorted(Path("data/out").glob("trap_raw_b*")) + [Path("data/out/trap_raw")]:
        p = d / "trap_all.json"
        if not p.exists():
            continue
        for q in json.load(open(p, encoding="utf-8")):
            key = q.get("scenario", "")[:40]
            if key in seen:
                continue
            seen.add(key)
            merged.append(q)
    p = Path("data/out/trap_raw/trap_all.json")
    p.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"TRAP 合并去重后: {len(merged)} 题 → {p}")


def merge_open():
    seen, merged = set(), []
    for d in sorted(Path("data/out").glob("open_raw_b*")) + [Path("data/out/open_raw")]:
        p = d / "open_all.json"
        if not p.exists():
            continue
        for q in json.load(open(p, encoding="utf-8")):
            key = q.get("scenario", "")[:40]
            if key in seen:
                continue
            seen.add(key)
            merged.append(q)
    p = Path("data/out/open_raw/open_all.json")
    p.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OPEN 合并去重后: {len(merged)} 题 → {p}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc", action="store_true")
    ap.add_argument("--trap", action="store_true")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    if args.mc:
        merge_mc()
    if args.trap:
        merge_trap()
    if args.open:
        merge_open()