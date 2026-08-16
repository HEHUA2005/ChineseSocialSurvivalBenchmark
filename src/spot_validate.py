"""⑥b 话外音题质检：判官独立判断真实意图，与标注答案比对。

话外音题的答案存在主观性（不同人对同一句话意图解读不同），
只有判官 = 标注答案才收录。
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient

CHECK_PROMPT = """下面是一段中国式对话情境，说话人一句话的真实意图可能与字面意思不同。
请凭你对中国人情世故的理解，独立判断这句话的真实意图。

【情境】{scenario}

A. {a}
B. {b}
C. {c}
D. {d}

输出 JSON：{{"answer": "A/B/C/D", "confidence": 0~1, "note": "10字内"}}"""


def validate_spots(client, in_path="data/out/spot_raw/spot_all.json",
                   out_path="data/benchmark/v1/mc/spot-all.json",
                   min_confidence=0.55, rounds=2):
    items = json.load(open(in_path, encoding="utf-8"))
    passed = []
    for q in items:
        opts = q["options"]
        agree = 0
        confs = []
        for _ in range(rounds):
            try:
                d = client.chat_json([
                    {"role": "user", "content": CHECK_PROMPT.format(
                        scenario=q["scenario"], a=opts["A"], b=opts["B"],
                        c=opts["C"], d=opts["D"])}], temperature=0.3)
                guess = str(d.get("answer", "")).strip().upper()
                conf = float(d.get("confidence", 0) or 0)
                confs.append(conf)
                if guess == q["answer"]:
                    agree += 1
            except Exception:
                pass
        avg_conf = sum(confs) / max(len(confs), 1)
        q["validation"] = {"judge_agree": f"{agree}/{rounds}",
                           "avg_confidence": round(avg_conf, 2)}
        # 判官多数同意 + 置信度不低 → 通过
        if agree >= max(1, rounds - 1) and avg_conf >= min_confidence:
            passed.append(q)
            print(f"  ✓ {q['id']} 判官 {agree}/{rounds} 置信 {avg_conf:.2f}")
        else:
            print(f"  ✗ {q['id']} 判官 {agree}/{rounds} 置信 {avg_conf:.2f}（答案有争议）")
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps(passed, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    print(f"\n入册 {len(passed)}/{len(items)} → {out_path}")
    return passed


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()
    validate_spots(LLMClient(model=args.model or None))