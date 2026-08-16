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

W = {"mc": 0.33, "trap": 0.23, "open": 0.17, "sort": 0.10, "mt": 0.09, "stab": 0.08}


def load_one(model):
    out = {"model": model, "mc": None, "trap": None, "open": None,
           "sort": None, "mt": None, "stab": None,
           "mc_n": 0, "trap_n": 0, "open_n": 0, "sort_n": 0, "mt_n": 0}
    paths = {
        "mc": [f"results/mc-{model}.json", "results/deepseek-v4.json"],
        "trap": [f"results/trap-{model}.json"],
        "open": [f"results/open-{model}.json"],
        "sort": [f"results/sort-{model}.json"],
        "mt": [f"results/mt-{model}.json"],
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
                out["stab"] = node.get("stability")  # runs>1 时存在
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
            elif key == "sort":
                # 排序题得分：tau 归一 + 底线保护折半加分
                tau = node.get("avg_tau", None)
                guard = node.get("worst_guard_rate", None)
                if tau is not None and guard is not None:
                    out["sort"] = min(tau * 100 + guard * 10, 100)  # 满分100
                out["sort_n"] = node.get("total", 0)
            elif key == "mt":
                out["mt"] = node.get("avg_final")  # 0-100
                out["mt_n"] = node.get("total", 0)
            break
    return out


def _std(vals):
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))


def build_table():
    rows = [load_one(m) for m in MODELS]
    # 缺失维度（sort/mt 等）用全体有值模型的均值填充，避免权重偏差
    for key in ("mc", "trap", "open", "sort", "mt"):
        vals = [r[key] for r in rows if r[key] is not None]
        fill = sum(vals) / max(len(vals), 1) if vals else 0.0
        for r in rows:
            if r[key] is None:
                r[key] = fill
    for r in rows:
        mc = (r["mc"] or 0) * 100
        tr = r["trap"] or 0
        op = (r["open"] or 0) * 2
        so = r["sort"] or 0
        mt = r["mt"] or 0
        st = (r["stab"] or 0) * 100
        r["_mc100"], r["_trap100"], r["_open100"] = mc, tr, op
        r["_sort100"], r["_mt100"], r["_stab100"] = so, mt, st
        r["total"] = (mc * W["mc"] + tr * W["trap"] + op * W["open"]
                       + so * W["sort"] + mt * W["mt"] + st * W["stab"])
        r["_complete"] = True
    rows.sort(key=lambda x: -x["total"])
    return rows


def render_md(rows):
    lines = [
        "## 排行榜（综合）", "",
        "总分 = 33% 客观题准确率 + 23% 陷阱题加权得分 + 17% 开放题评分 + 10% 排序题 + 9% 多轮对话 + 8% 答题稳定性（满分 100）",
        "",
        "| 排名 | 模型 | 总分 | 客观题 | 陷阱题 | 开放题 | 排序题 | 多轮 | 稳定性 |",
        "|---|------|------|--------|--------|--------|--------|------|--------|",
    ]
    for i, r in enumerate(rows, 1):
        stab = f"{r['_stab100']:.0f}%" if r["stab"] is not None else "未测"
        lines.append(
            f"| {i} | {r['model']} | **{r['total']:.1f}** "
            f"| {r['_mc100']:.1f}% ({r['mc_n']}题) "
            f"| {r['_trap100']:.1f} ({r['trap_n']}题) "
            f"| {r['_open100']:.1f} ({r['open_n']}题) "
            f"| {r['_sort100']:.1f} ({r['sort_n']}题) "
            f"| {r['_mt100']:.1f} ({r['mt_n']}题) | {stab} |")
    # 区分度诊断
    lines += ["", "### 区分度诊断（指标标准差，越大越能区分模型）", ""]
    for key, label in [("_mc100", "客观题"), ("_trap100", "陷阱题"), ("_open100", "开放题"),
                       ("_sort100", "排序题"), ("_mt100", "多轮对话"), ("total", "总分")]:
        vals = [r[key] for r in rows]
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