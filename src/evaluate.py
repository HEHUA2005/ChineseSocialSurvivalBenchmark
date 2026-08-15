"""③ 评测：客观题自动判分 + 开放题 LLM-as-judge 打分。

评测对象：被测模型（test model）。
评测方式：
- 选择题（mc/）：被测模型直接作答 → 与标准答案比对 → 准确率 + 按维度/难度分组统计。
- 开放题（open/）：被测模型给出完整应对 + 理由 → judge 按 rubric 打分。
- 输出 JSON 报告 + Markdown 汇总表。
"""
import json
import sys
import os
import re
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient

# ---------- 客观题 ----------

ANSWER_EXTRACT_PROMPT = """你是人情世故测试的答题者。请阅读下面的情境题，选出最得体的做法。

{question}

请直接输出 JSON：{{"choice": "A/B/C/D", "reason": "一句话理由"}}"""


def ask_mcq(client, q):
    """让被测模型做一道选择题，返回 (choice, reason, raw)。"""
    opts = "\n".join(f"{k}. {q['options'][k]}" for k in "ABCD")
    question = f"{q['scenario']}\n\n{opts}"
    try:
        data = client.chat_json([
            {"role": "user", "content": ANSWER_EXTRACT_PROMPT.format(question=question)}
        ], temperature=0.2)
        choice = str(data.get("choice", "")).strip().upper()
        return choice, str(data.get("reason", "")), json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return None, "", f"ERROR: {e}"


def evaluate_mc(client, questions, tag="", runs=1):
    """返回逐题结果 + 汇总统计。runs>1 时额外统计答题稳定性。"""
    per_q, correct = [], 0
    for q in questions:
        # runs 次采样：runs=1 取第一次，runs>1 记录全部采样用于稳定性分析
        samples = []
        for _ in range(max(1, runs)):
            choice, reason, raw = ask_mcq(client, q)
            samples.append({"choice": choice, "reason": reason})
        choice = samples[0]["choice"]
        is_correct = choice == q["answer"]
        correct += int(is_correct)
        rec = {
            "id": q["id"], "dimension": q.get("dimension"),
            "difficulty": q.get("difficulty"), "answer": q["answer"],
            "model_choice": choice, "correct": is_correct,
            "reason": samples[0]["reason"],
        }
        if runs > 1:
            # 稳定性：多次采样是否一致
            choices = {s["choice"] for s in samples if s["choice"]}
            rec["stable"] = len(choices) == 1
            rec["samples"] = samples
        per_q.append(rec)
        mark = "✓" if is_correct else "✗"
        print(f"  {mark} {q['id']} | 模型选 {choice} vs 答案 {q['answer']} | {rec['reason'][:40]}")
    acc = correct / max(len(questions), 1)
    # 按维度分组
    by_dim = {}
    for r in per_q:
        by_dim.setdefault(r["dimension"], []).append(r)
    dim_stats = {
        dim: {"n": len(rs), "acc": sum(r["correct"] for r in rs) / len(rs)}
        for dim, rs in by_dim.items()
    }
    print(f"  —— {tag} 客观题准确率: {acc:.1%} ({correct}/{len(questions)})")
    result = {"per_question": per_q, "accuracy": acc, "correct": correct,
              "total": len(questions), "by_dimension": dim_stats}
    if runs > 1:
        stable = sum(r.get("stable", False) for r in per_q) / len(per_q)
        result["stability"] = stable
        print(f"  —— 答题稳定性: {stable:.0%}（{runs} 次采样一致率）")
    return result


# ---------- 开放题 ----------

OPEN_RUBRIC = """你是一位资深"人情世故"评卷老师。请给下面这道开放题的【考生回答】打分。

【题目】
{question}

【评分维度】（每项 0~10 分）
1. 得体性(tact)：做法是否得体、照顾对方感受、符合场合。
2. 分寸感(measure)：是否过犹不及？有没有油滑/虚伪/过度讨好/过度生硬？
3. 可行性(practicality)：做法是否真实可行，还是空喊口号/理想化？
4. 长远性(strategy)：是否有利于长期关系维护？
5. 理由充分性(rationale)：解释理由是否自洽、深刻？

请输出 JSON：
{{
  "scores": {{"tact": x, "measure": x, "practicality": x, "strategy": x, "rationale": x}},
  "total": 加权总分(0~50),
  "comment": "60~120字评语"
}}"""


def judge_open(client, question, answer, rounds=2):
    """开放题 judge 打分，多轮采样取平均。返回 (avg_total, details)。"""
    totals = []
    details = []
    for _ in range(max(1, rounds)):
        try:
            data = client.chat_json([
                {"role": "user", "content": OPEN_RUBRIC.format(
                    question=question,
                    answer=answer)}
            ], temperature=0.3)
            scores = data.get("scores", {})
            total = float(data.get("total", 0)) or sum(float(scores.get(k, 0)) for k in
                        ["tact", "measure", "practicality", "strategy", "rationale"])
            totals.append(total)
            details.append({"scores": scores, "total": total, "comment": data.get("comment", "")})
        except Exception as e:
            print(f"    [judge失败] {e}")
    avg = sum(totals) / max(len(totals), 1)
    return avg, details


def evaluate_open(client, questions, judge_client=None, judge_rounds=2):
    """让被测模型回答开放题，再由 judge 打分。"""
    jc = judge_client or client
    results = []
    for q in questions:
        q_text = q["scenario"]
        try:
            answer = client.chat([{"role": "user", "content":
                f"下面是一道人情世故情境题。请给出你的应对做法和理由（150字以内）：\n\n{q_text}"}],
                temperature=0.4)
            print(f"  → {q['id']} 回答: {answer[:50]}...")
            score, details = judge_open(jc, q_text, answer, rounds=judge_rounds)
            results.append({"id": q["id"], "answer": answer,
                            "score": score, "judge_details": details})
            print(f"  ✓ {q['id']} judge总分 {score:.1f}/50")
        except Exception as e:
            print(f"  ✗ {q['id']} 评测失败: {e}")
    avg = sum(r["score"] for r in results) / max(len(results), 1)
    print(f"  —— 开放题平均分: {avg:.1f}/50")
    return {"per_question": results, "average_score": avg, "total": len(results)}


# ---------- 汇总 ----------

def load_benchmark(mc_dir="data/benchmark/v1/mc", open_dir="data/benchmark/v1/open"):
    mc, op = [], []
    for f in sorted(Path(mc_dir).glob("*.json")):
        mc.extend(json.load(open(f, encoding="utf-8")))
    for f in sorted(Path(open_dir).glob("*.json")):
        op.extend(json.load(open(f, encoding="utf-8")))
    return mc, op


def write_report(results, out_path="results/report.json"):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n报告已写入: {out_path}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, required=True, help="被测模型 id")
    ap.add_argument("--tag", type=str, default="", help="报告标签")
    ap.add_argument("--judge-model", type=str, default=None, help="judge 模型（默认同被测模型）")
    ap.add_argument("--no-open", action="store_true", help="跳过开放题")
    ap.add_argument("--runs", type=int, default=1, help="客观题多次采样测稳定性（>1 生效）")
    ap.add_argument("--judge-rounds", type=int, default=1, help="开放题 judge 采样次数")
    args = ap.parse_args()

    mc_qs, open_qs = load_benchmark()
    print(f"加载 benchmark: {len(mc_qs)} 道选择题, {len(open_qs)} 道开放题\n")

    test_client = LLMClient(model=args.model, temperature=0.2)
    report = {"model": args.model, "tag": args.tag, "timestamp": __import__("datetime").datetime.now().isoformat()}

    print("===== 选择题评测 =====")
    mc_result = evaluate_mc(test_client, mc_qs, tag=args.tag, runs=args.runs)
    report["mc"] = mc_result

    if not args.no_open and open_qs:
        print("\n===== 开放题评测 =====")
        jc = LLMClient(model=args.judge_model, temperature=0.2) if args.judge_model else None
        open_result = evaluate_open(test_client, open_qs, judge_client=jc, judge_rounds=args.judge_rounds)
        report["open"] = open_result

    write_report(report, f"results/{args.tag or 'report'}.json")

    # Markdown 汇总
    lines = [f"# 评测报告: {args.model} {args.tag}",
             f"\n- 选择题准确率: **{mc_result['accuracy']:.1%}** ({mc_result['correct']}/{mc_result['total']})"]
    if "open" in report:
        lines.append(f"- 开放题平均分: **{report['open']['average_score']:.1f}/50**")
    lines.append("\n## 选择题按维度\n\n| 维度 | 题数 | 准确率 |")
    lines.append("|---|---|---|")
    for dim, st in mc_result["by_dimension"].items():
        lines.append(f"| {dim} | {st['n']} | {st['acc']:.0%} |")
    md_path = f"results/{args.tag or 'report'}.md"
    Path(md_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Markdown 汇总已写入: {md_path}")