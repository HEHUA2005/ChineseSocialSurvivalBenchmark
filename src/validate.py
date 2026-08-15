"""② 质检与过滤：用 LLM judge 对生成的题目做交叉审查。

核心思路（防 LLM 自欺）：
- 独立裁决：judge 不看到"标准答案"，独立作答。若 judge 选出的最佳选项
  与生成器标定的答案不一致 → 该题"有争议"，淘汰或降级。
- 双判官投票：默认跑 2 个独立 judge 流（不同 prompt 角色），都通过的才进正式集。
- 共识度标注：judge 预估"多数中国人会认同该答案"的比例，低于阈值则淘汰。
- 去重：与已有题目做语义相似度检查（LLM 判定），重复的淘汰。
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient

CONSENSUS_THRESHOLD = 0.60   # 低于该共识度的题不进正式集
MIN_JUDGE_SCORE = 4.0        # 满分5，judge 综合评分下限


def _fmt_q(q):
    opts = "\n".join(f"{k}. {q['options'][k]}" for k in "ABCD")
    return f"【题干】\n{q['scenario']}\n\n【选项】\n{opts}\n"


JUDGE_INDEPENDENT_PROMPT = """你是一位非常了解中国人情世故的资深评委。下面是一道"人情世故"情境题。
请你站在一个情商高、懂分寸的中国人视角，独立思考并选出最得体的做法。

{question}

请只输出 JSON：{{"choice": "A/B/C/D", "confidence": 0~1, "reason": "一句话理由"}}"""

JUDGE_REVIEW_PROMPT = """你是一位严格的出题质检员。下面是一道"人情世故"选择题，已给出参考答案。
请从以下维度严格评审（每个维度 1~5 分）：
1. 答案唯一性：最佳答案是否明显优于其它选项？是否有两个选项难以区分？
2. 选项质量：是否有选项过于离谱/明显是陪跑，导致题太简单或太假？
3. 题干质量：场景是否真实可信、信息是否充分？
4. 文化适切：答案是否符合当代中国主流社会共识（而非个别老顽固的旧观念）？
5. 过犹不及：最佳答案是否真的得体，而不是油滑/圆滑到令人反感？

【题目】
{question}

【参考答案】{answer}
【参考解析】{rationale}

请输出 JSON：
{{
  "scores": {{"uniqueness": x, "options": x, "scenario": x, "culture": x, "appropriateness": x}},
  "overall": 平均分,
  "consensus": 0~1（预估认同该答案的中国人比例，考虑代际差异取主流共识）,
  "issues": "该题存在的问题（若无则写'无'）",
  "pass": true/false（综合判断是否值得收录进 benchmark）
}}"""


def judge_independent(client, q):
    """judge 独立作答，返回 (choice, confidence, reason)。"""
    try:
        data = client.chat_json([
            {"role": "user", "content": JUDGE_INDEPENDENT_PROMPT.format(question=_fmt_q(q))}
        ], temperature=0.2)
        choice = str(data.get("choice", "")).strip().upper()
        conf = float(data.get("confidence", 0))
        return choice, conf, str(data.get("reason", ""))
    except Exception as e:
        print(f"    [独立裁决失败] {e}")
        return None, 0, ""


def judge_review(client, q):
    """judge 带参考答案做综合评审，返回 (result_dict, error)。"""
    try:
        data = client.chat_json([
            {"role": "user", "content": JUDGE_REVIEW_PROMPT.format(
                question=_fmt_q(q), answer=q["answer"], rationale=q["rationale"])}
        ], temperature=0.2)
        return data, None
    except Exception as e:
        return None, str(e)


def llm_similar(client, q, existing, threshold=0.85):
    """判断新题 q 与已有题是否语义重复。返回 (is_dup, score)。"""
    if not existing:
        return False, 0.0
    sample = existing[-8:]  # 只抽样最近8题，控制成本
    ex_text = "\n---\n".join(f"{e.get('scenario','')}" for e in sample)
    prompt = f"""判断下面【新题】的"情境/考点"是否与【已有题】中的任意一题高度重复（指的是核心冲突或考点的雷同，而非只是话题相近）。
【新题】{q['scenario']}
【已有题】
{ex_text}
请输出 JSON：{{"is_dup": true/false, "dup_of": "重复的题号或'无'", "score": 0~1（重复程度）}}"""
    try:
        data = client.chat_json([{"role": "user", "content": prompt}], temperature=0.0)
        return bool(data.get("is_dup")), float(data.get("score", 0))
    except Exception:
        return False, 0.0


def validate_question(client, q, existing, n_judges=2, review_rounds=2, check_dup=True):
    """对单题做完整质检。返回 (pass?, detail_dict)。
    review_rounds：评审采样次数，取平均值，降低 LLM judge 噪声。
    """
    detail = {"id": q.get("id"), "judges": [], "consensus": 0.0, "overall": 0.0}

    # 1. 去重
    if check_dup:
        is_dup, score = llm_similar(client, q, existing)
        if is_dup:
            detail["dup"] = True
            detail["dup_score"] = score
            return False, detail

    # 2. 多个独立 judge 投票（都须认同标定答案）
    agree = 0
    for i in range(n_judges):
        choice, conf, reason = judge_independent(client, q)
        detail["judges"].append({"choice": choice, "confidence": conf, "reason": reason})
        if choice == q["answer"]:
            agree += 1
    if agree < n_judges:  # 有 judge 不认同 → 有争议
        detail["contested"] = True
        return False, detail

    # 3. 综合评审（多轮采样取平均）
    overalls, consensuses, review_flags = [], [], []
    reviews = []
    for _ in range(max(1, review_rounds)):
        review, err = judge_review(client, q)
        if err or not review:
            detail["review_error"] = err
            continue
        scores = review.get("scores", {})
        overall = sum(float(scores.get(k, 0)) for k in
                      ["uniqueness", "options", "scenario", "culture", "appropriateness"]) / 5.0
        overalls.append(overall)
        consensuses.append(float(review.get("consensus", 0)))
        review_flags.append(bool(review.get("pass", False)))
        reviews.append(review)
    if not overalls:
        return False, detail
    overall = sum(overalls) / len(overalls)
    consensus = sum(consensuses) / len(consensuses)
    detail["overall"] = overall
    detail["consensus"] = consensus
    detail["issues"] = reviews[0].get("issues", "")
    detail["review_pass"] = all(review_flags)  # 保守：所有轮次都要 pass

    if overall < MIN_JUDGE_SCORE or consensus < CONSENSUS_THRESHOLD or not all(review_flags):
        detail["rejected_reason"] = f"overall={overall:.2f}<{MIN_JUDGE_SCORE} 或 consensus={consensus:.2f}<{CONSENSUS_THRESHOLD} 或 pass轮次不足"
        return False, detail
    return True, detail


def validate_file(client, in_path, out_path=None, n_judges=2, review_rounds=2):
    with open(in_path, encoding="utf-8") as f:
        items = json.load(f)
    passed, rejected = [], []
    existing = []
    for idx, q in enumerate(items):
        q = dict(q)
        q["id"] = f"{Path(in_path).stem}-{idx:03d}"
        ok, detail = validate_question(client, q, existing, n_judges=n_judges, review_rounds=review_rounds)
        q["validation"] = detail
        if ok:
            passed.append(q)
            existing.append(q)
            print(f"  ✓ {q['id']} 通过 | consensus={detail['consensus']:.2f} overall={detail['overall']:.2f}")
        else:
            rejected.append(q)
            reason = detail.get("rejected_reason") or detail.get("dup") and "重复" or \
                     detail.get("contested") and "judge分歧" or detail.get("review_error") or "未知"
            print(f"  ✗ {q['id']} 淘汰 | {reason}")

    print(f"\n统计: 通过 {len(passed)} / 总 {len(items)}，通过率 {len(passed)/max(len(items),1):.0%}")
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(passed, f, ensure_ascii=False, indent=2)
        print(f"  正式集已写入: {out_path}")
    return passed, rejected


def validate_all(client, in_dir="data/out/mc_raw", out_dir="data/benchmark/v1/mc",
                 n_judges=2, review_rounds=2, max_workers=4):
    """并发处理整个目录下所有维度文件。返回 (passed_total, rejected_total)。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    files = sorted(Path(in_dir).glob("*.json"))
    results = []
    def _work(f):
        out = Path(out_dir) / f.name
        return f.name, validate_file(client, str(f), str(out), n_judges=n_judges,
                                     review_rounds=review_rounds)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_work, f): f for f in files}
        for fut in as_completed(futures):
            name, (passed, rejected) = fut.result()
            results.append((name, len(passed), len(rejected)))
    tp, tr = sum(r[1] for r in results), sum(r[2] for r in results)
    print(f"\n===== 全量质检完成：通过 {tp} / 淘汰 {tr}，通过率 {tp/max(tp+tr,1):.0%} =====")
    for name, p, r in sorted(results):
        print(f"  {name}: 通过 {p} / 淘汰 {r}")
    return tp, tr


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("infile", type=str, nargs="?", default=None)
    ap.add_argument("--out", type=str, default=None)
    ap.add_argument("--all", action="store_true", help="处理 data/out/mc_raw 全部文件")
    ap.add_argument("--judges", type=int, default=2)
    ap.add_argument("--review-rounds", type=int, default=2)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()

    client = LLMClient(model=args.model or None)
    if args.all:
        validate_all(client, n_judges=args.judges, review_rounds=args.review_rounds,
                     max_workers=args.workers)
    else:
        validate_file(client, args.infile, args.out, n_judges=args.judges,
                      review_rounds=args.review_rounds)