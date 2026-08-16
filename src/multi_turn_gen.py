"""④a 多轮对话题生成器：动态社交博弈剧本（3 轮连环局面）。

与人情世故选择题的单轮差异：
- 真实社交是动态的：你圆场 → 对方话里有刺 → 你接着圆
- 剧本包含"雷点"设计：每轮都有让局面恶化的钩子，好应对稳住局面，差应对引爆
- 评测不是比对标准答案，而是 judge 扮演对手推进局面 + 逐轮给"局面分"
"""
import json
import random
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient
from src.dims import DIMENSIONS

MT_PLOT_SEEDS = [
    "饭局两难：桌上有人当众给你挖坑（价格/难堪问题），你还得同时照顾主角面子",
    "职场连环：领导在汇报会上连问两个刁钻问题，中间还有同事补刀",
    "亲戚矛盾：家族聚会上被催婚/被比较，长辈步步紧逼",
    "朋友借钱：对方拐弯抹角要开口，你既不想借又不想伤感情",
    "抢功现场：你做的方案被同事当众说成他的，领导偏向",
    "家庭关系：婆婆/丈母娘与另一半的当面冲突，你被夹在中间",
    "保密压力：当众被问到一个你知情但说了会害人的消息",
    "酒后失言：领导酒后说了不该说的，被你在场听见，他要你表态",
    "拒绝艺术：领导让你周末加班/朋友让你帮忙办事，对方持续施压两轮",
    "面子里子：下属当众顶嘴/熟人当众讽刺，两轮升级到围观",
]

PROMPT = """你是深谙中国人情世故的编剧。请设计一个【三轮连环社交剧本】，模拟真实社交博弈。

【维度】{dim}：{desc}
【情节种子】{seed}

【剧本要求】
1. scene：场景定场（人物、关系、场合、氛围，120字内）。
2. 三轮递进：round1 是常温局面；主角化解后 round2 出现升级（对方试探/加码/围观者参与）；
   round3 是最棘手的关键点（可能直接戳中主角软肋）。
3. 每轮 question 是主角【当场要面对的话/局面】，写成对主角的直接压力（80-130字）。
4. trap：整个剧本埋的最大的雷（30字内说明：什么情况下会彻底得罪人）。
5. 剧本要"多解"：好应对能化解，差应对会引爆——不要有唯一标准操作。

【JSON】
{{
  "scene": "...",
  "turns": [
    {{"round": 1, "question": "..."}},
    {{"round": 2, "question": "..."}},
    {{"round": 3, "question": "..."}}
  ],
  "trap": "...",
  "difficulty": "难"
}}"""


def generate_mt_one(client, dim, seed, retries=3):
    for _ in range(retries):
        try:
            data = client.chat_json([
                {"role": "user", "content": PROMPT.format(
                    dim=dim["name"], desc=dim["desc"], seed=seed)}],
                temperature=0.8)
            scene = str(data.get("scene", "")).strip()
            turns = data.get("turns", [])
            if not scene or len(turns) != 3:
                continue
            parsed = []
            for t in turns:
                q = str(t.get("question", "")).strip() if isinstance(t, dict) else ""
                if not q:
                    raise ValueError("轮次问题为空")
                parsed.append({"round": len(parsed) + 1, "question": q})
            return {
                "dimension": dim["name"],
                "scene": scene,
                "turns": parsed,
                "trap": str(data.get("trap", "")).strip(),
                "difficulty": str(data.get("difficulty", "难")),
            }
        except Exception:
            pass
    return None


def generate_mt_batch(client, count_per_dim=1, out_dir="data/out/mt_raw"):
    items = []
    for dim in DIMENSIONS:
        for i in range(count_per_dim):
            seed = random.choice(MT_PLOT_SEEDS)
            q = generate_mt_one(client, dim, seed)
            if q:
                q["id"] = f"mt-{dim['name']}-{len(items):03d}"
                items.append(q)
                print(f"  ✓ {q['id']} | {q['scene'][:36]}...")
            else:
                print(f"  ✗ {dim['name']} 第{i}个 生成失败")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / "mt_all.json"
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"共 {len(items)} 个剧本 → {out}")
    return items


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()
    client = LLMClient(model=args.model or None)
    generate_mt_batch(client, args.count)