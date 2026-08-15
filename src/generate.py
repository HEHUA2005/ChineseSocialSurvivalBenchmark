"""① 选择题生成器：LLM 生成题干 + 四选项 + 标准答案 + 解析。

防污染设计：
- 我们用"人设 + 维度 + 情绪/事件关键词"作为素材种子，而不是给模型现成的段子，
  让模型自行构造新场景，避免复读网络套路。
- 生成 prompt 中不给任何"题目样例/正确答案样例"，只描述生成规范和评判标准，
  防止模型把样例背下来直接当成新题。
"""
import json
import random
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient

# 维度体系（taxonomy）
DIMENSIONS = [
    {
        "name": "说话之道",
        "desc": "委婉表达、话里有话、点到为止、听弦外之音、不当面驳人",
    },
    {
        "name": "饭局礼仪",
        "desc": "座次排序、敬酒劝酒、谁来买单、点菜分寸、照顾在座人员",
    },
    {
        "name": "面子文化",
        "desc": "给面子、留面子、驳面子的代价、打圆场、台阶",
    },
    {
        "name": "职场潜规则",
        "desc": "功高盖主、不当面评价同事、背锅、抢功、汇报的分寸、与领导相处",
    },
    {
        "name": "人情往来",
        "desc": "欠人情、还人情、礼尚往来、随份子、请客还局的节奏",
    },
    {
        "name": "拒绝的艺术",
        "desc": "怎么拒绝才不得罪人、委婉推辞、扮丑/示弱式拒绝",
    },
    {
        "name": "分寸与边界",
        "desc": "交浅言深、客套话vs真邀请、刚认识的分寸、关系亲疏",
    },
    {
        "name": "家庭关系",
        "desc": "婆媳、亲戚往来、辈分称呼、家族聚会、彩礼嫁妆",
    },
    {
        "name": "敏感话题",
        "desc": "工资、年龄、收入、婚育、外貌身材的回避与转移技巧",
    },
    {
        "name": "危机化解",
        "desc": "误会、冲突、尴尬场面、说错话后的补救圆场",
    },
]

# 为了多样性，给生成器提供的素材种子（事件/情境关键词）
EPISODE_SEEDS = [
    "同事当众夸你但你心里知道他是捧杀",
    "领导让你评价刚来但关系不熟的同事",
    "饭局上别人敬酒但你不想喝",
    "亲戚问你工资/收入",
    "有人在背后说你坏话被你撞见",
    "你帮了别人忙对方却抢功",
    "朋友开高价让你帮忙却欠着不还",
    "相亲对象家庭条件明显比你差但你挺喜欢",
    "元旦想请领导吃饭却不知道以什么名义",
    "同学聚会上有人炫富有人难堪",
    "新领导刚上任想立威拿你开刀",
    "下属犯了小错领导当众问是不是你的责任",
    "客户百般刁难你回头要跟领导汇报",
    "长辈让你喝酒你实在不能喝",
    "朋友找你借钱数额不小",
    "你没去同事的婚礼但给你留了位置",
    "群里有人发广告违规你作为管理员",
    "领导表扬了别人没表扬你",
    "你发现领导方案有明显错误要不要指出",
    "熟人的孩子要找你帮忙安排工作",
    "闺蜜在你面前吐槽她老公",
    "你在礼品店被人（不太熟的人）替付了钱",
]


def build_prompt(seed_pool, difficulty, n_existing):
    """构造生成 prompt。n_existing 用于让生成器避免重复既有题目主题。"""
    seeds = random.choice(seed_pool)
    dim = random.choice(DIMENSIONS)
    return f"""你是一位深谙中国"人情世故"的资深人际交往专家，同时也是出题专家。
请你根据下面的要求，原创一道考察人情世故的选择题。不要抄袭网络段子，场景要鲜活、具体、贴近真实生活。

【本道题要求针对的维度】
维度：{dim['name']}
维度解读：{dim['desc']}

【情景种子】围绕大体方向：{seeds}
你可以自由扩展细节，构造一个完整、可信的场景。

【难度】
{difficulty}

【出题硬性规范】
1. 只输出一个 JSON 对象，不要输出任何其它文字。
2. 题干（scenario）应力求具体生动，包含人物关系、身份、处境。题干控制在80-160字。
3. 给出4个选项 A/B/C/D。要求四个选项的"情商水平"有明显梯度：
   - 必须有一个"得体且明智"的最佳答案；
   - 其他选项可以是"诚实但不得体""过于油滑/虚伪""过于讨好没主见""明显失礼"等，且要自然，不能写得太离谱到一眼就看出来是错的。
4. 判断是否得体的核心标准优先级（务必内化）：
   ①安全/不得罪人（不暴露别人、不落人口实、不激化矛盾）
   ②真实/体面（不虚伪坦诚，但要委婉曲线）
   ③维护关系长远
   要注意"过犹不及"——空喊口号、满口大道理、永远打太极的选项也不算得体。
5. answer 字段填最佳选项字母（A/B/C/D）。
6. rationale 字段写 120-200 字的解析，说明为什么选它、其它选项错在哪（按上面①安全②真实③长远 的框架，但用自然语言，不要机械列点）。

【JSON 格式】
{{
  "scenario": "题干（第三人称，交代清楚人物身份处境，结尾问'这时他/她最得体的做法是？'或类似）",
  "options": {{"A": "…", "B": "…", "C": "…", "D": "…"}},
  "answer": "X",
  "rationale": "解析"
}}"""


def generate_one(client, seed_pool, difficulty, n_existing, retries=3):
    for _ in range(retries):
        try:
            msg = build_prompt(seed_pool, difficulty, n_existing)
            data = client.chat_json([{"role": "user", "content": msg}], temperature=0.8)
            # 基础校验
            if not isinstance(data, dict):
                continue
            sc = str(data.get("scenario", "")).strip()
            opts = data.get("options", {})
            ans = str(data.get("answer", "")).strip().upper()
            rat = str(data.get("rationale", "")).strip()
            if not (sc and opts and ans in "ABCD" and rat):
                continue
            if len(opts) < 4 or any(not str(opts.get(k, "")).strip() for k in "ABCD"):
                continue
            return {
                "dimension": None,  # 由封装函数填充
                "difficulty": difficulty,
                "scenario": sc,
                "options": {k: opts[k] for k in "ABCD"},
                "answer": ans,
                "rationale": rat,
            }
        except Exception as e:
            print(f"  [生成失败] {e}")
    return None


def generate_batch(client, dimension, count, difficulty="中等", out_dir=None):
    """为指定维度生成 count 道题并落盘。返回生成成功的题目列表。"""
    seed_pool = EPISODE_SEEDS + [dimension["desc"]]
    produced = []
    out_dir = Path(out_dir) if out_dir else None
    for i in range(count):
        q = generate_one(client, seed_pool, difficulty, len(produced))
        if q:
            q["dimension"] = dimension["name"]
            produced.append(q)
            print(f"  ✓ 第{i+1}题 生成成功 | {q['scenario'][:40]}...")
        else:
            print(f"  ✗ 第{i+1}题 生成失败")
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{dimension['name']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(produced, f, ensure_ascii=False, indent=2)
        print(f"  已写入 {path} ({len(produced)} 题)")
    return produced


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dimension", type=str, default=None, help="维度名；不填则全维度")
    ap.add_argument("--count", type=int, default=5, help="每维度生成数量")
    ap.add_argument("--difficulty", type=str, default="中等")
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()

    client = LLMClient(model=args.model or None)
    if args.dimension:
        dim = next(d for d in DIMENSIONS if d["name"] == args.dimension)
        generate_batch(client, dim, args.count, args.difficulty,
                       out_dir="data/out/mc_raw")
    else:
        # 并行：按维度分发到线程池，避免 sequential 时 API 限流拖慢整体
        from concurrent.futures import ThreadPoolExecutor
        all_items = {}
        def _work(dim):
            print(f"\n=== 维度：{dim['name']} ===")
            return dim["name"], generate_batch(client, dim, args.count, args.difficulty,
                                               out_dir="data/out/mc_raw")
        with ThreadPoolExecutor(max_workers=4) as pool:
            for name, items in pool.map(_work, DIMENSIONS):
                all_items[name] = items
        print(f"\n共生成 {sum(len(v) for v in all_items.values())} 题")