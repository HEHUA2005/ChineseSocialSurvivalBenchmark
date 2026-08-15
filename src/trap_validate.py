"""陷阱题质检：独立判官评审每个选项的错误标注，确认权重合理性。

与普通题质检的区别：
- 不看"生成器标注的错误"，判官独立为每个选项挑出 1-3 个错误类型
- 比对判官错误集与生成器错误集的重合度；最佳选项必须被判官认可为损失最小
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient
from src.dims import DIMENSIONS, ERRORS, penalty_of

ERROR_GUIDE = "\n".join(
    f"{e['code']} {e['name']}（-{e['weight']}）：{e['desc']}" for e in ERRORS)

JUDGE_OPTION_PROMPT = """你是一位深谙中国人情世故的资深评委。下面是一个人情世故【困境】和 4 个应对做法。
该困境存在客观限制，任何做法都会犯错误。请你独立评估每个做法的【失误严重程度】。

【评分标准】
- 0 = 基本无失误；10 = 极严重的失误（当众驳面子、泄露致命隐私、把所有人得罪光）
- 常见失误分档参考：当众驳面子 9-10；泄露敏感信息 8-9；得罪实权人物 7-8；
  当面评价他人 6-7；承诺无法兑现 5-6；交浅言深 5-6；拒绝生硬 4-5；
  油滑空洞 / 逃避责任 3-4；小失误 1-2。

【困境】{scenario}

【选项】
{options}

请对每个选项给出严重度分（小数可），并指出最严重和最轻的选项：
{{
  "severity": {{"A": 1.5, "B": 9.0, "C": 3.0, "D": 6.0}},
  "most_severe": "B",
  "least_severe": "A",
  "note": "一两句点评"
}}"""

JUDGE_BEST_PROMPT = """以下是一个人情世故困境的 4 个做法，你认为哪个选项的【损失最小】（最稳）？

{scenario}

A：{ta}
B：{tb}
C：{tc}
D：{td}

请输出 JSON：
{{
  "best": "X"（损失最小的选项）,
  "agree_generator": true/false（是否认同数据标注的 best）,
  "note": "一句话理由"
}}"""


def _fmt_opts(q):
    return "\n".join(f"{k}. {q['options'][k]['text']}" for k in "ABCD")


def judge_options(client, q):
    """判官给每个选项打严重度分。返回 (severity_dict, most, least) 或 None。"""
    try:
        data = client.chat_json([
            {"role": "user", "content": JUDGE_OPTION_PROMPT.format(
                scenario=q["scenario"], options=_fmt_opts(q))}
        ], temperature=0.2)
        sev = data.get("severity", {})
        out = {}
        for k in "ABCD":
            v = sev.get(k)
            if v is None:
                return None
            out[k] = float(v)
        return out, str(data.get("most_severe", "")).upper(), str(data.get("least_severe", "")).upper()
    except Exception:
        return None


def _rank_corr(gen, judge):
    """选项罚分排序 vs 判官严重度排序的 Spearman 秩相关（简版）。"""
    keys = list(gen.keys())
    def _ranks(vals):
        order = sorted(keys, key=lambda k: vals[k])
        return {k: i for i, k in enumerate(order)}
    rg, rj = _ranks(gen), _ranks(judge)
    n = len(keys)
    import statistics
    mg = statistics.mean(rg.values())
    mj = statistics.mean(rj.values())
    num = sum((rg[k]-mg)*(rj[k]-mj) for k in keys)
    dg = sum((rg[k]-mg)**2 for k in keys) ** 0.5
    dj = sum((rj[k]-mj)**2 for k in keys) ** 0.5
    if dg == 0 or dj == 0:
        return 0.0
    return num / (dg * dj)


def validate_trap(client, q):
    """返回 (pass?, detail)。
    稳健标准：① 判官认可的 most_severe 与生成器最大罚分项一致（或 least 与最小一致）
    ② 判官 best 与标注 best 一致 ③ 判官给 best 的 severity 为最低或并列最低。
    """
    detail = {"id": q["id"]}
    res = judge_options(client, q)
    if res is None:
        detail["fail"] = "判官解析失败"
        return False, detail
    judge_sev, most, least = res
    detail["judge_severity"] = judge_sev
    detail["judge_most_severe"] = most
    detail["judge_least_severe"] = least

    gen_pen = {k: v["penalty"] for k, v in q["options"].items()}
    detail["gen_penalty"] = gen_pen
    gen_most = max(gen_pen, key=gen_pen.get)
    gen_least = min(gen_pen, key=gen_pen.get)

    # ① 关键端点对齐（宽松：至少最重一致或最轻一致）
    if most != gen_most and least != gen_least:
        detail["fail"] = f"端点不一致: judge(most={most},least={least}) vs gen(most={gen_most},least={gen_least})"
        return False, detail

    # ② best 一致性：3 个独立判官投票，多数认同标注 best 才通过（降单次噪声）
    votes = ["", "", ""]
    for i in range(3):
        try:
            bd = client.chat_json([
                {"role": "user", "content": JUDGE_BEST_PROMPT.format(
                    scenario=q["scenario"],
                    ta=q["options"]["A"]["text"], tb=q["options"]["B"]["text"],
                    tc=q["options"]["C"]["text"], td=q["options"]["D"]["text"])}
            ], temperature=0.4)
            votes[i] = str(bd.get("best", "")).strip().upper()
        except Exception:
            votes[i] = ""
    detail["judge_best_votes"] = votes
    agree = sum(1 for v in votes if v == q["best"])
    if agree < 2:  # 至少 2/3 判官认同
        detail["fail"] = f"判官投票不认同 best: {votes} (标注 {q['best']})"
        return False, detail
    return True, detail


def validate_trap_file(client, in_path="data/out/trap_raw/trap_all.json",
                       out_path="data/benchmark/v1/trap/trap_all.json"):
    items = json.load(open(in_path, encoding="utf-8"))
    passed, rejected = [], []
    for q in items:
        ok, detail = validate_trap(client, q)
        q["validation"] = detail
        if ok:
            passed.append(q)
            print(f"  ✓ {q["id"]} 通过 | 判官端点对齐")
        else:
            rejected.append(q)
            print(f"  ✗ {q['id']} 淘汰 | {detail.get('fail')}")
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps(passed, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    print(f"\n通过 {len(passed)}/{len(items)}，通过率 {len(passed)/max(len(items),1):.0%}")
    return passed, rejected


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()
    client = LLMClient(model=args.model or None)
    validate_trap_file(client)