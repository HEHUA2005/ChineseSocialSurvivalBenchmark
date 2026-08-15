"""综合排行榜：汇总各模型的 MC / 陷阱题 / 开放题成绩，输出 markdown 排行表。

总分 = 0.45×MC准确率 + 0.30×陷阱题均分 + 0.25×开放题均分（均 0-100）
区分度诊断：打印各指标的标准差，指标失效（分差过小）时给出警告。
"""
import json
import math
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MODELS = [
    "grok-4.5", "grok-4.3-fast", "grok-4.20-0309-reasoning",
    "hy3-free", "nemotron-3.5-lightning-free", "deepseek-v4-flash-free",
]

W = {"mc": 0.45, "trap": 0.30, "open": 0.25}


def load_one(model):
    out = {"model": model, "mc": None, "trap": None, "open": None,
           "mc_n": 0, "trap_n": 0, "open_n": 0}
    paths = {
        "mc": [f"results/mc-{model}.json", "results/deepseek-v4.json"],
        "trap": [f"results/trap-{model}.json"],
        "open": [f"results/open-{model}.json"],
    }
    for key, cands in paths.items():
        for p in cands:
            if not Path(p).exists():
                continue
            d = json.load(open(p, encoding="utf-8"))
            node = d.get(key, d)
            if key == "mc":
                out["mc"] = node.get("accuracy") or (
                    node.get("correct", 0) / max(node.get("total", 1), 1))
                if out["mc"] is None:
                    pq = node.get("per_question", [])
                    if pq:
                        out["mc"] = sum(1 for r in pq if r.get("correct")) / len(pq)
                out["mc_n"] = node.get("total", 0)
            elif key == "open":
                v = node.get("average_score")
                if v is None:
                    pq = node.get("per_question", [])
                    if pq:
                        v = sum(r.get("score", 0) for r in pq) / len(pq)
                out["open"] = v  # 0-50
                out["open_n"] = node.get("total", 0)
            elif key == "trap":
                out["trap"] = node.get("avg_score")
                out["trap_n"] = node.get("total", 0)
            break
    return out


def _std(vals):
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))


def build_table():
    rows = [load_one(m) for m in MODELS]
    for r in rows:
        mc = (r["mc"] or 0) * 100
        tr = r["trap"] or 0
        op = (r["open"] or 0) * 2
        r["_mc100"], r["_trap100"], r["_open100"] = mc, tr, op
        r["total"] = mc * W["mc"] + tr * W["trap"] + op * W["open"]
        r["_complete"] = all(v is not None for v in (r["mc"], r["trap"], r["open"]))
    rows.sort(key=lambda x: -x["total"])
    return rows


def render_md(rows):
    lines = [
        "## 排行榜（综合）", "",
        "总分 = 45% 客观题准确率 + 30% 陷阱题加权得分 + 25% 开放题评分（满分 100）",
        "",
        "| 排名 | 模型 | 总分 | 客观题 | 陷阱题 | 开放题 | 数据完整度 |",
        "|---|------|------|--------|--------|--------|-----------|",
    ]
    for i, r in enumerate(rows, 1):
        complete = "完整" if r["_complete"] else "⚠️ 部分"
        lines.append(
            f"| {i} | {r['model']} | **{r['total']:.1f}** "
            f"| {r['_mc100']:.1f}% ({r['mc_n']}题) "
            f"| {r['_trap100']:.1f} ({r['trap_n']}题) "
            f"| {r['_open100']:.1f} ({r['open_n']}题) | {complete} |")
    # 区分度诊断
    lines += ["", "### 区分度诊断（指标标准差，越大越能区分模型）", ""]
    for key, label in [("_mc100", "客观题"), ("_trap100", "陷阱题"), ("_open100", "开放题"), ("total", "总分")]:
        vals = [r[key] for r in rows if r.get("_complete")]
        if len(vals) >= 2:
            sd = _std(vals)
            sp = sd / max(sum(vals) / len(vals), 1e-6)
            flag = "⚠️ 区分度弱" if sp < 0.06 else "✓ 可区分"
            lines.append(f"- {label}：σ = {sd:.2f}（变异系数 {sp*100:.1f}%）{flag}")
    return "\n".join(lines)


if __name__ == "__main__":
    rows = build_table()
    md = render_md(rows)
    print(md)
    Path("results/leaderboard.md").write_text(md, encoding="utf-8")
    for r in rows:
        print(f"{r['model']:30s} total={r['total']:.1f} mc={r['_mc100']:.1f} "
              f"trap={r['_trap100']:.1f} open={r['_open100']:.1f} "
              f"complete={r['_complete']}")