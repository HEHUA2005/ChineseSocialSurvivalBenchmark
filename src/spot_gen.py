"""⑥a 话外音识别题生成器：测"听弦外之音"能力。

题目结构完全兼容客观题（scenario/options/answer），生成后直接写入
data/benchmark/v1/mc/spot-*.json，被 evaluate.py 自动纳入评测。
"""
import json
import random
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient

# 话外音场景模板（写给模型的种子，保持防污染：不给现成句子）
SPOT_SEEDS = [
    "领导说客套话实际想让你加班/背锅/表态",
    "同事/朋友的客套话里有试探或暗示",
    "亲妈的唠叨话音外有需求（想让你回家/带人回家/存钱）",
    "对方说'这件事你决定就好'实际想要你按他的意思做",
    "饭局上的'随便点'实际有讲究",
    "说'不用送了'实际希望你送",
    "'改天一起吃饭'是客套还是真邀约",
    "一句夸奖里藏着的比较或压力",
]

PROMPT = """你是深谙中国人情世故的语言学专家。设计一道【话外音识别题】。

核心：中国人的表达常是"听话听音"，一句话表面意思 vs 真实意图经常不同。
请构造一个对话片段，其中说话人一句话的真实意图与字面意思【明显不同】，考考生能否听出弦外之音。

【种子】{seed}

【硬性要求】
1. scenario：写清关系背景（两人关系、场合、前情）+ 说话人那句【话】本身（90-140字）。
   「话」要自然、口语化、有弦外之音，来自真实生活。
2. options：4 个对"这句话真实意图"的解释：
   - 正确项：实际意图（委婉、暗藏真实诉求/试探/施压）
   - 干扰项：字面理解（表面意思）、不相关猜测、过度猜测
3. **答案字母必须是：{required_ans}**（把真实意图放在该选项，其余三项分配干扰项）。
4. rationale 解释为什么（60字内）。

【JSON】
{{
  "scenario": "...（含对话和背景）",
  "options": {{"A": "意图解释", "B": "意图解释", "C": "意图解释", "D": "意图解释"}},
  "answer": "{required_ans}",
  "rationale": "..."
}}"""

ANSWER_WHEEL = ["A", "B", "C", "D"]


def generate_spot_one(client, seed, required_ans, retries=3):
    for _ in range(retries):
        try:
            d = client.chat_json([{"role": "user", "content": PROMPT.format(seed=seed, required_ans=required_ans)}],
                                 temperature=0.8)
            opts = d.get("options", {})
            ans = str(d.get("answer", "")).strip().upper()
            if ans != required_ans or len(opts) != 4:
                continue
            if any(not str(v).strip() for v in opts.values()):
                continue
            return {
                "dimension": "说话之道",
                "subtype": "spot",
                "difficulty": "中等",
                "scenario": str(d.get("scenario", "")).strip() + "\n\n请问：这句话的真实意图最可能是？",
                "options": {k: str(opts[k]).strip() for k in "ABCD"},
                "answer": ans,
                "rationale": str(d.get("rationale", "")).strip(),
            }
        except Exception:
            pass
    return None


def generate_spot_batch(client, count=10, out_dir="data/out/spot_raw"):
    items = []
    round_robin = [ANSWER_WHEEL[i % 4] for i in range(count)]
    random.shuffle(round_robin)  # 进一步打散
    for i in range(count):
        seed = random.choice(SPOT_SEEDS)
        q = generate_spot_one(client, seed, round_robin[i])
        if q:
            q["id"] = f"spot-{len(items):03d}"
            items.append(q)
            print(f"  ✓ {q['id']} | answer={q['answer']} | {q['scenario'][:36]}...")
        else:
            print(f"  ✗ 第{i}题(需选{round_robin[i]}) 生成失败")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / "spot_all.json"
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"共 {len(items)} 题 → {out}")
    return items


def move_to_benchmark(items, dest="data/benchmark/v1/mc"):
    """写入 MC 目录，前缀 spot- 避免与普通题混淆。"""
    Path(dest).mkdir(parents=True, exist_ok=True)
    p = Path(dest) / "spot-all.json"
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {p} ({len(items)} 题)")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()
    client = LLMClient(model=args.model or None)
    items = generate_spot_batch(client, args.count)
    move_to_benchmark(items)