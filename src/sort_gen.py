"""⑤a 杀伤力排序题生成器：同一情境给多个回应，按"得罪人程度"排序。

排序题的价值：比单选更细粒度——两个模型可能选同一个"最优回应"，
但一个把最得罪人的回应排对了，另一个把铁板钉钉的禁忌话排到第二位，能力差异就显形。
"""
import json
import random
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient
from src.dims import DIMENSIONS, ERRORS, ERROR_WEIGHT

SORT_SEEDS = [
    "领导当众问你意见，你其实有不同看法，4种回应方式力度不同",
    "同事抢功后你还得在场配合",
    "亲戚当众让你『掏钱』赞助喜事",
    "朋友迟到两小时，你被晾在餐厅",
    "领导把锅甩给你，当着全组的面",
    "有人当众开玩笑揭你短",
    "被要求转发明显不妥的内容",
    "饭局上被灌酒，4种推辞方式",
]

PROMPT = """你是深谙中国人情世故的专家。请设计一道【杀伤力排序题】。

情境是一个需要立即回应的社交场合，你给出 5 个可能的回应（A~E），这些回应【全部都会得罪人】，但得罪程度从【几乎不得罪】（小失误）到【彻底搞崩关系】（极端失礼）有明显梯度。

【维度】{dim}：{desc}
【种子】{seed}

【要求】
1. scenario：一组完整的对话情境（120字内），铺垫好关系背景和在场第三方的反应。
2. responses：5 个回应（每个 40-90 字），覆盖从轻到重的等级：
   - 轻：不得罪或只算小失误（比如转移话题）
   - 中：轻微得罪（比如生硬拒绝）
   - 重：明显伤害（比如当众拆穿）
   - 极重：搞崩关系（比如当众骂人或公开打脸）
3. correct_order：从【最不得罪】到【最得罪】的字母排列（5 个字母的全排列）。
4. penalties：给每个回应一个 1~10 的"得罪分"（与排列一致：最小的在前，最大在后，要有明显梯度）。

【⚠️ 重要】不得照抄示例的排序或分数！你必须根据自己刚写的 5 个回应逐一评估轻重，
每次生成的正确排序和罚分都应该是不同的。

【JSON】
{{
  "scenario": "...",
  "responses": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
  "correct_order": [5个字母，自定义全排列],
  "penalties": {{"A": 1~10, "B": 1~10, "C": 1~10, "D": 1~10, "E": 1~10}},
  "rationale": "为什么这个排序是对的（60字内）"
}}"""


def generate_sort_one(client, dim, seed, retries=3):
    for _ in range(retries):
        try:
            data = client.chat_json([
                {"role": "user", "content": PROMPT.format(
                    dim=dim["name"], desc=dim["desc"], seed=seed)}],
                temperature=0.8)
            responses = data.get("responses", {})
            order = data.get("correct_order", [])
            penalties = data.get("penalties", {})
            if not set(order) == {"A", "B", "C", "D", "E"}:
                continue
            if len(responses) != 5 or any(not str(v).strip() for v in responses.values()):
                continue
            # 验证排列与罚分单调一致（从小到大对应）
            vals = [penalties.get(x, 0) for x in order]
            if vals != sorted(vals):
                continue
            # 罚分还得有明显的梯度范围
            if max(vals) - min(vals) < 5:
                continue
            return {
                "dimension": dim["name"],
                "scenario": str(data.get("scenario", "")).strip(),
                "responses": {k: str(v).strip() for k, v in responses.items()},
                "correct_order": order,
                "penalties": {k: int(penalties.get(k, 0)) for k in "ABCDE"},
                "rationale": str(data.get("rationale", "")).strip(),
            }
        except Exception:
            pass
    return None


def shuffle_letters(q):
    """随机重排选项字母：保持语义不变，但字母分布随机，防位置猜答案。"""
    import random
    perm = list("ABCDE")
    random.shuffle(perm)
    old_resp, old_pen = q["responses"], q["penalties"]
    q["responses"] = {perm[i]: old_resp[old] for i, old in enumerate("ABCDE")}
    q["penalties"] = {perm[i]: old_pen[old] for i, old in enumerate("ABCDE")}
    q["correct_order"] = [perm["ABCDE".index(old)] for old in q["correct_order"]]
    return q


def generate_sort_batch(client, count_per_dim=1, out_dir="data/out/sort_raw"):
    items = []
    for dim in DIMENSIONS:
        for i in range(count_per_dim):
            seed = random.choice(SORT_SEEDS)
            q = generate_sort_one(client, dim, seed)
            if q:
                q = shuffle_letters(q)
                q["id"] = f"sort-{dim['name']}-{len(items):03d}"
                items.append(q)
                print(f"  ✓ {q['id']} | 排序 {q['correct_order']} 罚分 {q['penalties']}")
            else:
                print(f"  ✗ {dim['name']} 第{i}个 生成失败")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / "sort_all.json"
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"共 {len(items)} 题 → {out}")
    return items


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()
    client = LLMClient(model=args.model or None)
    generate_sort_batch(client, args.count)