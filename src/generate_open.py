"""①b 开放题生成器：LLM 生成"无标准答案"的人情世故情境题。

开放题不给选项，只给情境 + 追问，评测时由 judge 打分（见 evaluate.py）。
每题附一个"参考答案要点"（good_points），供 judge 参照但不作为唯一标准。
"""
import json
import sys
import os
import random
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient
from src.generate import DIMENSIONS, EPISODE_SEEDS

PROMPT = """你是一位深谙中国"人情世故"的资深人际交往专家，同时也是出题专家。
请原创一道"人情世故"开放情境题（没有选项，考察考生的临场应对与表达能力）。

【维度】{dim}：{desc}
【情境种子】{seed}
【要求】
1. 只输出 JSON，不要输出其它文字。
2. 场景要具体生动、贴近真实生活，包含人物关系、身份、处境、一段对话或事件。
3. 结尾问一个开放式问题，如"这时他/她应该怎么回应/怎么做？请给出具体做法并说明理由"。
4. 同时给出 good_points：2~3 个"高手级"应答要点（怎么做才得体），供评卷参考。注意要点要体现
   ①安全（不得罪人/不落人口实）②真实体面（不虚伪）③长远关系，且注意"过犹不及"。

【JSON 格式】
{{
  "dimension": "{dim}",
  "difficulty": "中等",
  "scenario": "情境描述 + 开放式提问（200字以内）",
  "good_points": ["要点1", "要点2", "要点3"]
}}"""


def generate_open_one(client, dim, seed):
    msg = PROMPT.format(dim=dim["name"], desc=dim["desc"], seed=seed)
    for _ in range(3):
        try:
            data = client.chat_json([{"role": "user", "content": msg}], temperature=0.8)
            sc = str(data.get("scenario", "")).strip()
            gps = data.get("good_points", [])
            if not sc or len(gps) < 2:
                continue
            return {
                "id": None,
                "dimension": dim["name"],
                "difficulty": data.get("difficulty", "中等"),
                "scenario": sc,
                "good_points": gps,
            }
        except Exception as e:
            print(f"  [失败] {e}")
    return None


def generate_open_batch(client, count_per_dim=2, out_dir="data/out/open_raw"):
    items = []
    for dim in DIMENSIONS:
        for i in range(count_per_dim):
            seed = random.choice(EPISODE_SEEDS)
            q = generate_open_one(client, dim, seed)
            if q:
                q["id"] = f"{dim['name']}-open-{i:03d}"
                items.append(q)
                print(f"  ✓ {q['id']}")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / "open_all.json"
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"共 {len(items)} 题，已写入 {out}")
    return items


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=2)
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()
    client = LLMClient(model=args.model or None)
    generate_open_batch(client, args.count)