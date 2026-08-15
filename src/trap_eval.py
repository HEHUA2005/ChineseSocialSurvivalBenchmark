"""陷阱题评测：模型从"全错选项"中做选择，按加权失误扣分。

指标：
- choice_score：100 - 选中选项失误罚分归一化（满分 100）
- best_rate：选中"损失最小解"的比例（陷阱题中通常不高，区分度来源之一）
- 按维度聚合：各维度加权得分 → 供雷达图使用
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient
from src.dims import TRAP_MAX_PENALTY

PROMPT = """你是人情世故测试的答题者。下面是一个身处两难情境的题目。

{scenario}

无论怎么选都可能得罪人，请选择【损失最小、最稳妥】的做法：
A. {ta}
B. {tb}
C. {tc}
D. {td}

请只输出 JSON：{{"choice": "A/B/C/D", "reason": "30字内理由"}}"""


def ask_trap(client, q):
    opts = q["options"]
    try:
        data = client.chat_json([
            {"role": "user", "content": PROMPT.format(
                scenario=q["scenario"],
                ta=opts["A"]["text"], tb=opts["B"]["text"],
                tc=opts["C"]["text"], td=opts["D"]["text"])}
        ], temperature=0.2)
        choice = str(data.get("choice", "")).strip().upper()
        return choice, str(data.get("reason", ""))
    except Exception as e:
        return None, f"ERROR: {e}"


def evaluate_trap(client, questions, tag=""):
    per_q = []
    total_penalty = 0.0
    best_hits = 0
    for q in questions:
        choice, reason = ask_trap(client, q)
        if choice in q["options"]:
            penalty = q["options"][choice]["penalty"]
            score = max(0.0, 100 - penalty / TRAP_MAX_PENALTY * 100)
            is_best = choice == q["best"]
            best_hits += int(is_best)
        else:
            penalty, score, is_best = None, 0.0, False
        per_q.append({
            "id": q["id"], "dimension": q.get("dimension"),
            "choice": choice, "penalty": penalty,
            "score": round(score, 1), "is_best": is_best,
            "reason": reason,
            "best_label": q.get("best"),
        })
        mark = "✓" if is_best else ("·" if penalty is not None else "✗")
        display = f"{mark} {q['id']} 选{choice} 罚{penalty} 分{score:.0f}"
        if penalty is not None:
            display += f" ({'最佳' if is_best else '非最佳'})"
        print(display)

    n = len(questions)
    by_dim = {}
    for r in per_q:
        by_dim.setdefault(r["dimension"], []).append(r)
    dim_stats = {}
    for dim, rs in by_dim.items():
        sc = [r["score"] for r in rs]
        dim_stats[dim] = {"n": len(rs), "avg_score": sum(sc) / len(sc)}
    avg_score = sum(r["score"] for r in per_q) / max(n, 1)
    best_rate = best_hits / max(n, 1)
    print(f"  —— {tag} 陷阱题均分 {avg_score:.1f}/100，最佳解达成率 {best_rate:.0%}（{best_hits}/{n}）")
    result = {"per_question": per_q, "avg_score": round(avg_score, 1),
              "best_rate": round(best_rate, 3), "total": n,
              "by_dimension": dim_stats}
    return result


def load_trap(path="data/benchmark/v1/trap/trap_all.json"):
    if not Path(path).exists():
        return []
    return json.load(open(path, encoding="utf-8"))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, required=True)
    ap.add_argument("--tag", type=str, default="")
    ap.add_argument("--json", type=str, default=None, help="陷阱题库路径")
    args = ap.parse_args()

    qs = load_trap(args.json) if args.json else load_trap()
    print(f"加载陷阱题: {len(qs)} 道\n")
    client = LLMClient(model=args.model, temperature=0.2)
    result = evaluate_trap(client, qs, tag=args.tag or args.model)
    out = f"results/trap-{args.tag or args.model}.json"
    Path(out).write_text(json.dumps(
        {"model": args.model, "tag": args.tag, "trap": result},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {out}")