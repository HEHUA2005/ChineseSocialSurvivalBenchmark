"""⑦ 错题本：聚合多模型错题，提炼高区分度题目 + 生成难度变体。

价值：34 题混在一起统计噪声大；错题本是"模型能力的分水岭"——
多个模型都答错的题才是区分强弱的筛子。

输出：
- results/hardest.md：高区分度题目清单（据多模型错题统计）
- data/out/hardest_variants/：基于易错题结构生成的变体题（供扩量）
"""
import json
import sys
import os
import random
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.dims import DIMENSIONS


def collect_mc_errors():
    """每个模型错题 {题id: 错比数}（只统计 4 家代表模型）。"""
    from src.leaderboard import MODELS
    err = Counter()
    details = {}
    for f in sorted(Path("results").glob("mc-*.json")):
        d = json.load(open(f, encoding="utf-8"))
        if d.get("model") not in MODELS:
            continue
        node = d.get("mc", {})
        for r in node.get("per_question", []):
            if not r.get("correct", False):
                err[r["id"]] += 1
                details.setdefault(r["id"], {"dimension": r.get("dimension"),
                                             "scenario": r.get("scenario", "")[:60],
                                             "model_choices": []})
    return err, details


def collect_trap_losses():
    """陷阱题：非最佳解（选错损失）统计（只统计 4 家代表模型）。"""
    from src.leaderboard import MODELS
    err = Counter()
    for f in sorted(Path("results").glob("trap-*.json")):
        d = json.load(open(f, encoding="utf-8"))
        if d.get("model") not in MODELS:
            continue
        node = d.get("trap", {})
        for r in node.get("per_question", []):
            if not r.get("is_best", False):
                err[r["id"]] += 1
    return err


def render_hardest(err_mc, trap_err, details, out="results/hardest.md"):
    from src.leaderboard import MODELS
    n_models = len(MODELS)
    lines = ["# 高区分度题型（错题本）", "",
             f"> 多模型都答错的题 = 真正的「人情世故分水岭」，数值 x/{n_models} 是答错模型数。", ""]
    lines.append("## 客观题（多模型答错）\n\n| 题 | 维度 | 答错模型数 | 题干摘要 |")
    lines.append("|---|---|---|---|")
    for qid, n in err_mc.most_common():
        det = details.get(qid, {})
        lines.append(f"| {qid} | {det.get('dimension','?')} | **{n}/{n_models}** | {det.get('scenario','')} |")
    lines.append("\n## 陷阱题（未选损失最小解）\n\n| 题 | 未选最佳解模型数 |")
    lines.append("|---|---|")
    for qid, n in trap_err.most_common():
        lines.append(f"| {qid} | **{n}/{n_models}** |")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text("\n".join(lines), encoding="utf-8")
    print(f"→ {out}")


def generate_variants(client, err_mc, details, k=6, out_dir="data/out/hardest_variants"):
    """取 k 道高区分度客观题做变体：只换人设/场合/细节，保留陷阱结构。"""
    top = [qid for qid, _ in err_mc.most_common(k) if details.get(qid)]
    items = []
    for qid in top:
        det = details[qid]
        # 用现有 benchmark 原题作为变体模板：按维度名匹配原题
        src_q = None
        for f in sorted(Path("data/benchmark/v1/mc").glob("*.json")):
            for x in json.load(open(f, encoding="utf-8")):
                if x.get("id") == qid:
                    src_q = x
                    break
            if src_q:
                break
        if not src_q:
            continue
        variant = make_variant(client, src_q)
        if variant:
            variant["id"] = f"var-{qid}-{len(items):03d}"
            items.append(variant)
            print(f"  ✓ {qid} → 变体 {variant['id']}")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    Path(out_dir, "variants.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"生成 {len(items)} 道变体题 → {out_dir}")
    return items


def make_variant(client, q):
    """提示词：换肤保结构。"""
    prompt = f"""你是一道人情世故选择题的改编者。下面是原题，请把它【换一个完全不同的场景/人名/场合】，"
保留原题的核心陷阱结构（人物关系张力、错误选项的诱饵类型、正确做法的精髓）。

原题：
维度：{q.get('dimension')}
题干：{q.get('scenario')}
选项：{" ".join(f"{k}.{v}" for k, v in q.get('options', {}).items())}
答案：{q.get('answer')}

要求：场景必须是新的（不能沿用原受害人/原单位/原事由），但陷阱结构等价。
输出 JSON：{{"scenario": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}}, "answer": "X", "rationale": "..."}}"""
    try:
        from src.client import LLMClient
        d = client.chat_json([{"role": "user", "content": prompt}], temperature=0.8)
        opts = d.get("options", {})
        ans = str(d.get("answer", "")).strip().upper()
        if ans in "ABCD" and len(opts) == 4 and all(str(v).strip() for v in opts.values()):
            return {"dimension": q.get("dimension"), "difficulty": "难",
                    "scenario": str(d.get("scenario", "")).strip(),
                    "options": {k: str(opts[k]).strip() for k in "ABCD"},
                    "answer": ans, "rationale": str(d.get("rationale", "")).strip(),
                    "is_variant_of": q.get("id")}
    except Exception as e:
        print(f"  [变体生成失败] {e}")
    return None


if __name__ == "__main__":
    import argparse
    from src.leaderboard import MODELS
    n_models = len(MODELS)
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", type=int, default=6, help="生成的变体数量(<=k)")
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()
    err_mc, details = collect_mc_errors()
    trap_err = collect_trap_losses()
    render_hardest(err_mc, trap_err, details)
    print("\n高区分度客观题 top：")
    for qid, n in err_mc.most_common(8):
        print(f"  {qid}  {n}/{n_models} 模型答错")
    if args.variants and args.variants > 0:
        print("\n开始生成变体题（保留陷阱结构，换肤）...")
        from src.client import LLMClient
        client = LLMClient(model=args.model or None)
        generate_variants(client, err_mc, details, k=args.variants)