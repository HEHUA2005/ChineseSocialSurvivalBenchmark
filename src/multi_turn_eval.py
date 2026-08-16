"""④b 多轮对话评测：judge 扮演对手推进局面 + 逐轮局面分。

流程（每轮）：
1. 被测模型针对当前局面作答（开放文本）
2. judge 双重任务：a) 以对手角色模拟自然反应（推进局面）b) 该轮局面分
   （-5 彻底崩坏 ~ +5 完美化解，本轮结束后的关系紧张度）
3. 终局：judge 总结被测者整体表现，给出终局分 0-100

指标：
- 逐轮局面分 ×3（可看"救场曲线"：落差越大说明前轮埋雷）
- 终局分（0-100）
- 触发雷点检测（trap 命中）
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient

ROLE_PROMPT = """你是社交局中的对手角色【{role}】，正在一场真实的中国式人情世故场合。
场合背景：{scene}
你此刻的身份和心情：{stance}

当前局面：{question}

被测者（主角）刚说了：{answer}

请以你【角色的真实反应】回应：可能给面子也可能带刺、可能点头也可能冷笑，要自然。
同时评估主角这句应对让局面变好还是变坏。

输出 JSON：
{{
  "reaction": "你的自然反应（80字内，含语气/脸色/潜台词）",
  "situation_score": 整数，-5~+5（+5=主角完美化解局面升温；-5=主角把关系搞崩；0=什么都没改变）,
  "reason": "你为什么这样反应（30字内）"
}}"""

FINAL_PROMPT = """你是一位人情世故评委。以下是主角在一场{rounds}轮社交博弈中的全程表现。

【场景】{scene}
【逐轮记录】
{log}

请综合评估主角的整体表现。重点看：
1. 是否踩了剧本里的雷点（{trap}）
2. 局面是否逐轮好转/恶化（救场能力）
3. 终局关系状态（得罪了谁/保住了谁）

输出 JSON：{{
  "final_score": 0~100 的整数,
  "trap_triggered": true/false（是否最终踩雷）,
  "verdict": "一段 80 字内的评价（定位主角情商）"
}}"""


def _fmt_log(turns):
    lines = []
    for t in turns:
        lines.append(f"--- 第{t['round']}轮 ---\n局面：{t['question']}\n"
                     f"主角回应：{t['answer']}\n对方反应：{t['reaction']}\n"
                     f"局面分：{t['situation_score']}（{t['reason']}）\n")
    return "\n".join(lines)


def _judge_round(client, game, t, answer, role, stance):
    try:
        d = client.chat_json([
            {"role": "user", "content": ROLE_PROMPT.format(
                role=role, scene=game["scene"], stance=stance,
                question=t["question"], answer=answer)}], temperature=0.5)
        return {
            "reaction": str(d.get("reaction", "")).strip(),
            "situation_score": int(d.get("situation_score", 0)),
            "reason": str(d.get("reason", "")).strip(),
        }, None
    except Exception as e:
        return None, str(e)


def _judge_final(client, game, turns):
    try:
        d = client.chat_json([
            {"role": "user", "content": FINAL_PROMPT.format(
                rounds=len(turns), scene=game["scene"], log=_fmt_log(turns),
                trap=game.get("trap", "") or "无")}], temperature=0.2)
        return {
            "final_score": int(d.get("final_score", 50)),
            "trap_triggered": bool(d.get("trap_triggered", False)),
            "verdict": str(d.get("verdict", "")).strip(),
        }
    except Exception as e:
        return {"final_score": 0, "trap_triggered": False,
                "verdict": f"终局判定失败: {e}"}


def evaluate_multi_turn(client, games, opponent_names=None, tag=""):
    """games: [{scene, turns:[{round,question}], trap,...}]"""
    results = []
    for gi, game in enumerate(games):
        turns_out = []
        prev_reaction = "（开场）"
        for t in game["turns"]:
            # 给被测模型的当前局面：场景 + 对方上一轮反应 + 本轮问题
            question = f"{game['scene']}\n\n上一轮对方的反应：{prev_reaction}\n\n本轮你要应对：{t['question']}"
            try:
                ans_data = client.chat_json([
                    {"role": "user", "content":
                        f"你是主角。请用沉稳的中国人情世故应对，只输出 JSON："
                        f"{{\"answer\": \"你的当场回应（60-120字，直接说出口的话）\"}}\n\n{question}"}],
                    temperature=0.3)
                answer = str(ans_data.get("answer", "")).strip()
            except Exception as e:
                answer = f"（作答失败:{e}）"
            # judge 扮演对手
            role = opponent_names[gi] if opponent_names and gi < len(opponent_names) else "对方"
            stance = "对你的应对不满意或想试探你；但也有合理的一面"
            judged, err = _judge_round(client, game, t, answer, role, stance)
            if judged is None:
                judged = {"reaction": f"（判定失败:{err}）", "situation_score": 0, "reason": "判定失败"}
            turns_out.append({
                "round": t["round"], "question": t["question"],
                "answer": answer, **judged,
            })
            prev_reaction = judged["reaction"]
        final = _judge_final(client, game, turns_out)
        results.append({
            "id": game.get("id", f"mt-{gi:03d}"), "dimension": game.get("dimension"),
            "scene": game["scene"], "turns": turns_out, **final,
        })
        scores = [t["situation_score"] for t in turns_out]
        print(f"  ✓ {results[-1]['id']} | 局面分 {scores} → 终局 {final['final_score']} "
              f"| 踩雷 {final['trap_triggered']}")
    avg = sum(r["final_score"] for r in results) / max(len(results), 1)
    trap_rate = sum(1 for r in results if r["trap_triggered"]) / max(len(results), 1)
    res = {"per_game": results, "avg_final": round(avg, 1),
           "trap_rate": round(trap_rate, 2), "total": len(results)}
    return res


def load_mt(path="data/benchmark/v1/mt/mt_all.json"):
    if not Path(path).exists():
        return []
    return json.load(open(path, encoding="utf-8"))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=str, required=True)
    ap.add_argument("--tag", type=str, default="")
    ap.add_argument("--json", type=str, default=None)
    args = ap.parse_args()
    games = load_mt(args.json) if args.json else load_mt()
    print(f"加载剧本: {len(games)} 个\n")
    client = LLMClient(model=args.model)
    res = evaluate_multi_turn(client, games, tag=args.tag or args.model)
    out = f"results/mt-{args.tag or args.model}.json"
    Path(out).write_text(json.dumps({"model": args.model, "tag": args.tag, "mt": res},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {out}")