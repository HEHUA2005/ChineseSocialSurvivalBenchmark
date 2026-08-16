"""⑤b 杀伤力排序题评测：模型排序 vs 标准排序。

指标：
- kendall_tau：排序相关性（-1~1）
- 头名错误率：模型认为"最不得罪人"的回应是否真的最少得罪
- worst_guard：模型是否把最得罪人的回应放在最后（保护底线）
- penalty_mae：逐项罚分差异
"""
import json
import sys
import os
from itertools import permutations
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient

PROMPT = """你是人情世故测试的答题者。下面是一个社交场合，有 5 个可能的回应。

【情境】{scenario}

A. {a}
B. {b}
C. {c}
D. {d}
E. {e}

注意：这些回应全部都会带来麻烦，但程度不同。
请按【得罪人程度从最轻到最严重】排序。

输出 JSON：{{"order": ["A","B","C","D","E"], "reason": "30字内理由"}}"""


def kendall_tau(a, b):
    """a,b 为元素列表（同元素全排列），返回 -1~1 的一致性。"""
    if len(a) != len(b) or set(a) != set(b):
        return 0.0
    pairs = 0
    concordant = 0
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            pairs += 1
            da = a.index(a[i]) < a.index(a[j])
            db = b.index(a[i]) < b.index(a[j])
            concordant += 1 if da == db else 0
    return 2 * concordant / pairs - 1 if pairs else 0.0


def ask_sort(client, q):
    r = q["responses"]
    try:
        d = client.chat_json([
            {"role": "user", "content": PROMPT.format(
                scenario=q["scenario"], a=r["A"], b=r["B"], c=r["C"],
                d=r["D"], e=r["E"])}], temperature=0.2)
        order = [str(x).strip().upper() for x in d.get("order", [])]
        # 宽容：归一化为 A-E 的排列
        good = [x for x in order if x in "ABCDE"]
        seen, norm = set(), []
        for x in good:
            if x not in seen:
                seen.add(x)
                norm.append(x)
        for x in "ABCDE":
            if x not in seen:
                norm.append(x)
        return norm, str(d.get("reason", ""))
    except Exception as e:
        return None, str(e)


def evaluate_sort(client, questions, tag=""):
    per_q = []
    for q in questions:
        order, reason = ask_sort(client, q)
        if order is None:
            tau, top_ok, worst_ok, pmae = 0.0, False, False, 99.0
            order = list("ABCDE")
        else:
            correct = q["correct_order"]
            tau = kendall_tau(order, correct)
            top_ok = order[0] == correct[0] if order else False
            worst_ok = order[-1] == correct[-1] if order else False
            pmap = q["penalties"]
            pmae = sum(abs(pmap[order[i]] - pmap[correct[i]]) for i in range(5)) / 5
        per_q.append({
            "id": q["id"], "dimension": q.get("dimension"),
            "model_order": order, "correct_order": q["correct_order"],
            "tau": round(tau, 3), "top_ok": top_ok, "worst_ok": worst_ok,
            "penalty_mae": round(pmae, 1), "reason": reason,
        })
        print(f"  ✓ {q['id']} | tau={tau:.2f} 头名{'✓' if top_ok else '✗'} "
              f"底线{'✓' if worst_ok else '✗'} | 模型排序 {''.join(order)}")
    n = max(len(questions), 1)
    res = {
        "per_question": per_q,
        "avg_tau": round(sum(r["tau"] for r in per_q) / n, 3),
        "top_accuracy": round(sum(1 for r in per_q if r["top_ok"]) / n, 3),
        "worst_guard_rate": round(sum(1 for r in per_q if r["worst_ok"]) / n, 3),
        "avg_penalty_mae": round(sum(r["penalty_mae"] for r in per_q) / n, 2),
        "total": len(questions),
    }
    print(f"  —— {tag} 排序题 | tau={res['avg_tau']} 头名={res['top_accuracy']:.0%} "
          f"底线保护={res['worst_guard_rate']:.0%} 罚分MAE={res['avg_penalty_mae']}")
    return res


def load_sort(path="data/benchmark/v1/sort/sort_all.json"):
    return json.load(open(path, encoding="utf-8")) if Path(path).exists() else []


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, required=True)
    ap.add_argument("--tag", type=str, default="")
    ap.add_argument("--json", type=str, default=None)
    args = ap.parse_args()
    qs = load_sort(args.json) if args.json else load_sort()
    print(f"加载排序题: {len(qs)} 道\n")
    client = LLMClient(model=args.model)
    res = evaluate_sort(client, qs, tag=args.tag or args.model)
    out = f"results/sort-{args.tag or args.model}.json"
    Path(out).write_text(json.dumps({"model": args.model, "tag": args.tag, "sort": res},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {out}")