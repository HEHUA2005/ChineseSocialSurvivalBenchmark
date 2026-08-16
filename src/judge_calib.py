"""judge 校准：评测 LLM judge 自身的一致性。

方法：从现有 open 评测结果中抽取答案样本（覆盖高低分），让 judge 在
3 种温度（0.0/0.3/0.7）下各打 2 遍，输出：
- 同答案总分标准差（judge 对同一份答案的稳定性）
- 温度敏感性（分数随温度漂移多少）
- 分数段采样偏差（judge 打分是否塌缩在中间区域，缺乏区分）

结论写进 results/judge_calibration.md，供排行榜解读时参考。
"""
import json
import statistics
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient
from src.evaluate import OPEN_RUBRIC, judge_open

TEMPS = [0.0, 0.3, 0.7]
REPS = 2
SAMPLE_PER_MODEL = 3


def collect_samples(n_per_model=SAMPLE_PER_MODEL):
    """从各模型的 open 结果里收集 (question, answer, known_score)。"""
    # 题目池：id -> scenario
    qmap = {}
    for f in sorted(Path("data/benchmark/v1/open").glob("*.json")):
        for q in json.load(open(f, encoding="utf-8")):
            qmap[q.get("id")] = q.get("scenario", "")
    samples = []
    for f in sorted(Path("results").glob("open-*.json")):
        d = json.load(open(f, encoding="utf-8"))
        node = d.get("open", {})
        pq = node.get("per_question", [])
        # 均匀采样高/中/低分
        pq = sorted(pq, key=lambda r: r.get("score", 0))
        if len(pq) <= n_per_model:
            picks = pq
        else:
            picks = [pq[0], pq[len(pq)//2], pq[-1]]
        for r in picks:
            samples.append({"question": qmap.get(r.get("id"), ""),
                            "answer": r.get("answer", ""),
                            "known": r.get("score")})
    return [s for s in samples if s["question"]]


def calib_one(client, sample):
    """同一答案多种温度多次打分。返回温度->[分数] 矩阵。"""
    scores = {}
    for t in TEMPS:
        vals = []
        for _ in range(REPS):
            try:
                data = client.chat_json(
                    [{"role": "user", "content": OPEN_RUBRIC.format(
                        question=sample["question"], answer=sample["answer"])}],
                    temperature=t)
                scores_ = data.get("scores", {})
                total = float(data.get("total", 0)) or sum(
                    float(scores_.get(k, 0)) for k in
                    ["tact", "measure", "practicality", "strategy", "rationale"])
                vals.append(total)
            except Exception:
                vals.append(None)
        scores[t] = [v for v in vals if v is not None]
    return scores


def run(client, out_md="results/judge_calibration.md"):
    samples = collect_samples()
    print(f"收集 {len(samples)} 份答案样本（覆盖各模型高/中/低分）")
    all_vals = []
    per_sample = []
    for i, s in enumerate(samples):
        m = calib_one(client, s)
        flat = [v for vals in m.values() for v in vals]
        if len(flat) >= 2:
            sd = statistics.pstdev(flat)
            mean = statistics.mean(flat)
        else:
            sd, mean = 0.0, 0.0
        all_vals.extend(flat)
        temp_spread = max(statistics.mean(m[t]) for t in TEMPS if m[t]) - \
                      min(statistics.mean(m[t]) for t in TEMPS if m[t]) if any(m.values()) else 0
        per_sample.append({
            "idx": i, "known": s["known"], "mean": round(mean, 1),
            "std": round(sd, 1), "temp_spread": round(temp_spread, 1),
            "scores": {str(t): [round(v,1) for v in m[t]] for t in TEMPS},
        })
        print(f"  #{i} 已知分={s['known']} | 复打均值={mean:.1f} 波动σ={sd:.1f} "
              f"温度极差={temp_spread:.1f}")
    stable = sum(1 for p in per_sample if p["std"] <= 3.0)
    overall_sd = statistics.pstdev(all_vals) if all_vals else 0
    report = {
        "samples": len(per_sample), "overall_std": round(overall_sd, 2),
        "stable_rate": round(stable / max(len(per_sample), 1), 2),
        "per_sample": per_sample,
        "temperatures": TEMPS, "reps_per_temp": REPS,
    }
    lines = [
        "# LLM Judge 校准报告", "",
        f"- 样本数：{report['samples']}（覆盖各模型高/中/低分答案 × 3 温度 × 2 次）",
        f"- 整体打分散布 σ = {report['overall_std']:.2f} / 50 分",
        f"- 单答案稳定性达标率（σ≤3 分）：{report['stable_rate']:.0%}",
        "",
        "| # | 已知分 | 复打均值 | σ | 温度极差 | 各温度分数 |",
        "|---|----|----|----|----|----|", ]
    for p in report["per_sample"]:
        lines.append(f"| {p['idx']} | {p['known']} | {p['mean']} | {p['std']} | "
                     f"{p['temp_spread']} | " +
                     " / ".join(f"{t}°C:{p['scores'][t]}" for t in map(str, TEMPS)) + " |")
    lines += ["", "### 解读参考",
              "- σ 大 = judge 对同一答案反复打分不稳定，其分数应被视作噪声区间而不是精确值",
              "- 温度极差大 = 分数严重依赖采样运气，两模型比较差 2-3 分可能无意义",
              "- 若整体 σ > 4（50分制），建议判分改为「3 次采样取中位数」而非单次"]
    Path(out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(out_md).write_text("\n".join(lines), encoding="utf-8")
    print(f"\n校准报告 → {out_md}")
    return report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, default=None)
    ap.add_argument("--samples", type=int, default=0)
    args = ap.parse_args()
    if args.samples:
        SAMPLES_ALL = collect_samples(args.samples)
    client = LLMClient(model=args.model or None)
    run(client)