"""①c 陷阱题生成器：生成"无完美解"的人情世故困境题。

与普通选择题的区别：
- 场景存在客观条件限制，任何做法都会得罪人（如"四杯水分给五个领导"）
- 所有选项都带错误标记（见 dims.ERRORS 错误分类学），只有"损失最小解"没有"完美解"
- 评测按加权失误扣分，分数粒度细，不同模型自然拉开差距
"""
import json
import sys
import os
import random
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient
from src.dims import DIMENSIONS, ERRORS, penalty_of

# 四杯水五领导的原型思路：客观稀缺 → 分配必然不均
TRAP_PROTOTYPES = [
    "稀缺分配：资源（水/酒/菜/座/红包）少于人数，怎么分都会有人不满",
    "两头讨好：A和B同时找你索要，帮谁都会得罪另一个",
    "评功会：领导让你评价两个下属，他们都有功有过",
    "两难保密：当众被问到一个知道答案但说了会害人的问题",
    "站队表态：被逼当场表态支持/反对一个敏感决定",
    "寿宴红包：准备了不合适的礼金/礼物又无法临时更换",
    "领导口误：领导当众说错了重要信息，你指出会驳面子，不指出会误导团队",
    "代收礼物：有人托你把明显不妥的礼物转交给领导",
    "饭局座位：多了一个人少了一个座，主人暗示你让位",
    "背锅现场：责任三方在场，领导看向你等答案",
]

ERROR_TABLE = "\n".join(
    f"  {e['code']} {e['name']}（-{e['weight']}）：{e['desc']}" for e in ERRORS)


def build_prompt(dim, prototype):
    return f"""你是一位深谙中国"人情世故"的专家，同时是出题专家。请设计一道【陷阱题】。

所谓陷阱题：场景存在【客观条件的限制】，导致主角无论怎么做都会有人不满意、都会犯错，
不存在完美解法。出题目标是考"多害相权取其轻"——考生能否选择【损失最小】的选项。

【维度】{dim['name']}：{dim['desc']}
【困境原型】{prototype}
【硬性要求】
1. 场景必须源自真实的"两难/稀缺"客观限制（参考：宴会上只有四杯水却坐着五位领导）。
   不要捏造"其实有完美解法"的选项来破坏陷阱性。
2. 4 个选项 A/B/C/D 全部都有失误，失误程度必须有明显梯度：
   - 存在一个"损失最小"选项（但它也可能带 1 个小失误，不能是满分）；
   - 其他选项分别犯中/重/极重错误。
3. 每个选项必须标注 errors：1~3 个错误代码（从下方分类学选），并说明犯了什么失误。
4. best 填"损失最小"选项字母；best 必须是【无争议】的稳妥做法——绝大多数中国人第一直觉
   都会认可它最不伤人、最不惹事、最体面。如果连你自己都觉得 best 有争议，请重新设计选项。
5. no_perfect_reason 一段话说明为什么该场景没有完美解（60-120字）。

【错误分类学（权重即扣分）】
{ERROR_TABLE}

【JSON 格式】
{{
  "scenario": "完整情境描述（180字内，第三人称，结尾问'最稳妥的做法是？'）",
  "options": {{
    "A": {{"text": "做法描述", "errors": [{{"code": "E4", "reason": "…"}}]}},
    "B": {{"text": "…", "errors": [{{"code": "E1", "reason": "…"}}, {{"code": "E8", "reason": "…"}}]}},
    "C": {{"text": "…", "errors": [...]}},
    "D": {{"text": "…", "errors": [...]}}
  }},
  "best": "X",
  "best_note": "…",
  "no_perfect_reason": "…"
}}"""


def generate_trap_one(client, dim, prototype, retries=3):
    for _ in range(retries):
        try:
            data = client.chat_json(
                [{"role": "user", "content": build_prompt(dim, prototype)}], temperature=0.8)
            sc = str(data.get("scenario", "")).strip()
            opts = data.get("options", {})
            best = str(data.get("best", "")).strip().upper()
            if not (sc and opts and best in "ABCD" and len(opts) >= 4):
                continue
            parsed = {}
            for k in "ABCD":
                o = opts.get(k)
                if not isinstance(o, dict) or not str(o.get("text", "")).strip():
                    raise ValueError(f"选项 {k} 不完整")
                # 用权重表统一重算罚分，不信任生成器自报数字
                errors = [{"code": str(e.get("code", "")).strip()}
                          for e in o.get("errors", []) if e]
                errors = [e for e in errors if e["code"] in
                          {x["code"] for x in ERRORS}]
                if not errors:  # 至少一个错误，否则不是陷阱题
                    raise ValueError(f"选项 {k} 无错误标注")
                parsed[k] = {"text": str(o["text"]).strip(),
                             "errors": errors,
                             "penalty": penalty_of(errors)}
            # best 的罚分应显著小于其他选项
            bp = parsed[best]["penalty"]
            worst = max(v["penalty"] for v in parsed.values())
            if bp >= worst:  # best 的罚分必须严格低于最差项
                continue
            return {
                "dimension": dim["name"],
                "difficulty": "难",
                "scenario": sc,
                "options": parsed,
                "best": best,
                "best_note": str(data.get("best_note", "")).strip(),
                "no_perfect_reason": str(data.get("no_perfect_reason", "")).strip(),
            }
        except Exception as e:
            pass
    return None


def generate_trap_batch(client, count_per_dim=1, out_dir="data/out/trap_raw"):
    items = []
    for dim in DIMENSIONS:
        for i in range(count_per_dim):
            proto = random.choice(TRAP_PROTOTYPES)
            q = generate_trap_one(client, dim, proto)
            if q:
                q["id"] = f"trap-{dim['name']}-{len(items):03d}"
                items.append(q)
                penalties = {k: v["penalty"] for k, v in q["options"].items()}
                print(f"  ✓ {q['id']} | 罚分 {penalties} | best={q['best']}")
            else:
                print(f"  ✗ {dim['name']} 第{i}题 生成失败")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out = Path(out_dir) / "trap_all.json"
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
    generate_trap_batch(client, args.count)