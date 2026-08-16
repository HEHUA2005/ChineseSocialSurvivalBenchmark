"""难度打标器：对正式集客观题批量打 容易/中等/难 标签（grok 判题）。

扩量生成的题库 difficulty 统一为"中等"，本脚本用 judge 按判别标准
把每道题归入三档，写回 data/benchmark/v1/mc/*.json 的 difficulty 字段。
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient

JUDGE_PROMPT = """你是一个中文人情世故考题难度评估专家。下面是一道多选题（含正确选项与解析），
请把它归入三档之一并给一句话理由。

难度定义：
- 容易：常识性礼仪，基本无冲突，多数成年人都会做（如敬酒、让座、客气话）
- 中等：有人际张力，需要权衡人情与规则
- 难：多边利益冲突、面子+规则+关系叠加、含隐晦潜规则，主流人容易答错或纠结

只输出 JSON：{{"difficulty": "容易|中等|难", "reason": "一句话理由"}}

题目：{scenario}
选项：{options}
正确选项：{answer}
解析：{rationale}"""


def _parse_label(raw):
    """宽容解析：去掉 ```json 围栏/前后文本，取最后一个 {..}。"""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json"):
            s = s[4:]
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        return json.loads(s[i:j + 1])
    return {}


def label_one(client, q, retries=2):
    opts = "\n".join(f"{k}. {v}" for k, v in q.get("options", {}).items())
    for _ in range(retries):
        try:
            r = client.chat([{"role": "user", "content": JUDGE_PROMPT.format(
                scenario=q["scenario"], options=opts,
                answer=q["answer"], rationale=q.get("rationale", ""))}])
            j = _parse_label(r)
            lv = j.get("difficulty", "")
            if lv in ("容易", "中等", "难"):
                return lv, j.get("reason", "")
        except Exception:
            pass
    return "中等", "打标失败默认"


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, default="grok-4.3-fast")
    args = ap.parse_args()
    client = LLMClient(model=args.model, temperature=0.2)
    from collections import Counter
    total, stat = 0, Counter()
    for f in sorted(Path("data/benchmark/v1/mc").glob("*.json")):
        qs = json.load(open(f, encoding="utf-8"))
        changed = False
        for q in qs:
            total += 1
            lv, reason = label_one(client, q)
            if q.get("difficulty") != lv or q.get("difficulty_reason") != reason:
                q["difficulty"] = lv
                q["difficulty_reason"] = reason
                changed = True
            stat[lv] += 1
            print(f"  {q.get('id', f.stem)} → {lv}")
        if changed:
            json.dump(qs, open(f, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
    print(f"\n共打标 {total} 题：{dict(stat)}")
    print("DONE")


if __name__ == "__main__":
    main()
