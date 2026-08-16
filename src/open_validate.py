"""开放题题面质检：判官评估开放性题目的质量（可作答/情境真实/无泄漏）。

开放题没有唯一答案，无法做答案校验，只能保题面质量：
- 情境真实（贴合中国人情世故）
- 可作答（考生能给出应对策略，不空洞）
- 无泄漏提示（不该把标准做法写在题干里）
score ≥ 7/10 入册。
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient

CHECK_PROMPT = """你是人情世故评测专家组。请评估下面这道【开放题】的题面质量。

【题目】{scenario}

按以下标准打分（各 0-5）：
1. 情境真实：是否贴合真实中国职场/人情场景，能引起共鸣
2. 可作答：考生能否据此给出具体应对策略（不空洞、不无解题）
3. 无泄漏：题干是否已经暗示了"标准做法"（泄漏则扣分，0=完整泄漏, 5=无泄漏）

输出 JSON：{{"reality": x, "answerability": x, "no_leak": x, "score": 加权总分0-15, "note": "15字内"}}"""


def validate_opens(client, in_path="data/out/open_raw/open_all.json",
                   out_path="data/benchmark/v1/open/open_all.json",
                   min_score=10.0, rounds=2):
    items = json.load(open(in_path, encoding="utf-8"))
    passed = []
    for q in items:
        scores = []
        for _ in range(rounds):
            try:
                d = client.chat_json([
                    {"role": "user", "content": CHECK_PROMPT.format(
                        scenario=q["scenario"])}], temperature=0.3)
                tot = float(d.get("score", 0)) or (
                    float(d.get("reality", 0)) + float(d.get("answerability", 0))
                    + float(d.get("no_leak", 0)))
                scores.append(tot)
            except Exception:
                pass
        avg = sum(scores) / max(len(scores), 1)
        q["validation"] = {"avg_score": round(avg, 1)}
        if avg >= min_score:
            passed.append(q)
            print(f"  ✓ {q['id']} 题面 {avg:.1f}/15")
        else:
            print(f"  ✗ {q['id']} 题面 {avg:.1f}/15（<{min_score} 淘汰）")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(passed, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"\n入册 {len(passed)}/{len(items)} → {out_path}")
    return passed


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, default=None)
    ap.add_argument("--min-score", type=float, default=10.0)
    args = ap.parse_args()
    validate_opens(LLMClient(model=args.model or None), min_score=args.min_score)