"""④c 多轮剧本质检：判官验证剧本张力与三轮递进性。

剧本必须满足：
- 三轮是连环升级的（round2/3 比上一轮更难缠，不是重复）
- 存在"雷点"（差应对会引爆的关键点）
- 有多解性：好应对能救回局面，不是只有一种标准答案
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient

CHECK_PROMPT = """你是评估剧本质量的评委。下面是一个三轮社交博弈剧本。

【场景】{scene}
【三轮局面】
{rounds}
【埋的雷】{trap}

请判断剧本质量，输出 JSON：
{{
  "escalating": true/false（三轮是否逐渐升级、越来越难缠）,
  "has_trap": true/false（是否存在差应对会引爆的雷点）,
  "open_ended": true/false（是否存在多种可行应对，而非唯一答案）,
  "realistic": true/false（场景是否贴近真实中国式人情世故场景）,
  "score": 0~10,
  "note": "30字内点评"
}}"""


def validate_one(client, q):
    try:
        rounds = "\n".join(f"第{t['round']}轮：{t['question']}" for t in q["turns"])
        d = client.chat_json([
            {"role": "user", "content": CHECK_PROMPT.format(
                scene=q["scene"], rounds=rounds, trap=q.get("trap", ""))}],
            temperature=0.2)
        ok = all(d.get(k) for k in ("escalating", "has_trap", "open_ended", "realistic"))
        score = int(d.get("score", 0))
        return ok and score >= 7, d
    except Exception as e:
        return False, {"note": f"校验失败: {e}"}


def validate_batch(client, in_path="data/out/mt_raw/mt_all.json",
                   out_path="data/benchmark/v1/mt/mt_all.json"):
    items = json.load(open(in_path, encoding="utf-8"))
    passed = []
    for q in items:
        ok, detail = validate_one(client, q)
        q["validation"] = {
            **{k: detail.get(k) for k in ("escalating", "has_trap", "open_ended", "realistic", "score")},
            "note": detail.get("note", "")}
        if ok:
            passed.append(q)
            print(f"  ✓ {q['id']} 通过 | score={detail.get('score')}")
        else:
            print(f"  ✗ {q['id']} 淘汰 | score={detail.get('score')} {detail.get('note','')}")
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps(passed, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    print(f"\n通过 {len(passed)}/{len(items)}")
    return passed


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()
    validate_batch(LLMClient(model=args.model or None))