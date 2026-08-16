"""⑤c 排序题质检：判官独立验证每个选项的"得罪分"端点。

不要求判官排出 5 个完整顺序（5! 排列成本高且主观），只验证：
- 判官认为"最不得罪"（最小罚分）的选项 = 标注极小值项
- 判官认为"最得罪"（最大罚分）的选项 = 标注极大值项
两端点都对 → 排序骨架可信。
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient

CHECK_PROMPT = """下面是一个人情世故场景的 5 个回应。这些回应全部都会得罪人，但程度不同。

【场景】{scenario}

A. {a}
B. {b}
C. {c}
D. {d}
E. {e}

请你独立判断：
1. least：哪个回应【得罪人最轻】（几乎不得罪，最稳）？
2. most：哪个回应【得罪人最重】（最危险，最伤关系）？

输出 JSON：{{"least": "X", "most": "Y", "note": "10字内"}}"""


def validate_sorts(client, in_path="data/out/sort_raw/sort_all.json",
                   out_path="data/benchmark/v1/sort/sort_all.json") -> dict:
    items = json.load(open(in_path, encoding="utf-8"))
    passed = []
    for q in items:
        r = q["responses"]
        try:
            d = client.chat_json([
                {"role": "user", "content": CHECK_PROMPT.format(
                    scenario=q["scenario"], a=r["A"], b=r["B"], c=r["C"],
                    d=r["D"], e=r["E"])}], temperature=0.2)
            judge_least = str(d.get("least", "")).strip().upper()
            judge_most = str(d.get("most", "")).strip().upper()
        except Exception:
            judge_least = judge_most = ""
        order = q["correct_order"]
        true_least, true_most = order[0], order[-1]
        ok = judge_least == true_least and judge_most == true_most
        q["validation"] = {"judge_least": judge_least, "judge_most": judge_most,
                           "ok": ok}
        if ok:
            passed.append(q)
            print(f"  ✓ {q['id']} 端点一致 (最轻{true_least} 最重{true_most})")
        else:
            print(f"  ✗ {q['id']} 判官(轻{judge_least},重{judge_most}) vs 标注(轻{true_least},重{true_most})")
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps(passed, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    print(f"\n入册 {len(passed)}/{len(items)} → {out_path}")
    return {"passed": len(passed), "total": len(items)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()
    validate_sorts(LLMClient(model=args.model or None))