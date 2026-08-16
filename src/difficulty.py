"""难度梯度分析：按 容易/中等/难 分层看每个模型的能力衰减。

回答关键问题："模型是人情世故的什么水平"——
- 简单题都会做吗？（基础礼仪/常识）
- 难题是否拉开？（潜规则、危机、面子文化）
- 谁在难题上崩盘？（难度曲线陡峭 = 只会皮毛）

输出 results/difficulty.md
"""
import json
import statistics
from pathlib import Path
from src.leaderboard import MODELS

DIFF_ORDER = ["容易", "中等", "难"]


def collect(mode="mc"):
    # 从题库读 id→难度 映射（label_difficulty.py 打标结果）
    diff_map = {}
    for f in sorted(Path("data/benchmark/v1/mc").glob("*.json")):
        for q in json.load(open(f, encoding="utf-8")):
            diff_map[q["id"]] = q.get("difficulty", "中等")
    rows = {"models": []}
    for m in MODELS:
        f = f"results/mc-{m}.json"
        d = json.load(open(f, encoding="utf-8"))
        pq = d["mc"]["per_question"]
        dim_stats = {}
        for r in pq:
            lv = diff_map.get(r["id"], "中等")
            if lv not in ("容易", "中等", "难"):
                lv = "中等"
            dim_stats.setdefault(lv, {"n": 0, "ok": 0})
            dim_stats[lv]["n"] += 1
            dim_stats[lv]["ok"] += 1 if r.get("correct") else 0
        rows["models"].append({"model": m, "by_difficulty": dim_stats})
    # 陷阱难度同样分层
    rows["trap"] = []
    for m in MODELS:
        f = f"results/trap-{m}.json"
        d = json.load(open(f, encoding="utf-8"))
        pq = d["trap"]["per_question"]
        # 陷阱题结果里暂无 difficulty，按全场分 × 分层口径做整体汇总
        scores = [r.get("score", 0) for r in pq]
        rows["trap"].append({"model": m, "all": {"n": len(pq),
                                                   "avg": statistics.mean(scores) if scores else 0}})
    return rows


def render(rows, out="results/difficulty.md"):
    lines = ["# 难度梯度分析", "",
             "> 客观题按难度分层准确率；陷阱题按难度分层的加权得分（100-罚分制）。",
             "> 曲线越陡 = 只会简单常识、难题崩盘；平缓 = 真本事。", "",
             "## 客观题（准确率）\n\n| 模型 | 容易 | 中等 | 难 | 衰减(易→难) |",
             "|---|---|---|---|---|"]
    for r in rows["models"]:
        b = r["by_difficulty"]
        for lv in DIFF_ORDER:
            b.setdefault(lv, {"n": 0, "ok": 0})
        acc = {lv: (b[lv]["ok"] / max(b[lv]["n"], 1)) for lv in DIFF_ORDER}
        decay = (acc["容易"] - acc["难"]) * 100 if b["容易"]["n"] and b["难"]["n"] else None
        dec_str = f"{-decay:.0f}pts" if decay is not None else "—"
        if decay is not None and decay > 30:
            dec_str += " ⚠️崩盘"
        cells = " | ".join(
            f"{acc[lv]*100:.0f}%<br/>({b[lv]['n']}题)" for lv in DIFF_ORDER)
        lines.append(f"| {r['model']} | {cells} | {dec_str} |")
    lines += ["", "## 陷阱题（加权得分 /100）\n\n| 模型 | 全场均分 | 题数 | 最佳解达成率 |", "|---|---|---|---|"]
    for r in rows["trap"]:
        d = json.load(open(f"results/trap-{r['model']}.json", encoding="utf-8"))
        node = d["trap"]
        lines.append(f"| {r['model']} | {node['avg_score']:.1f} | {node['total']}题 | {node['best_rate']:.0%} |")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text("\n".join(lines), encoding="utf-8")
    print(f"→ {out}")
    return lines


if __name__ == "__main__":
    render(collect())