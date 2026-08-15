"""雷达图生成器：按 10 个维度绘制各模型能力画像（纯 SVG，零依赖）。

输入：各模型的评测结果 JSON（mc-*.json / trap-*.json / open-*.json）
维度得分 = 0.4×客观准确率 + 0.3×陷阱加权分 + 0.2×开放题分（缺项用该模型均值填充）
输出：results/radar/<model>.svg 与一张多模型叠加图 overview.svg
"""
import json
import math
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.dims import DIMENSIONS

SHORT = {d["name"]: d["name"][:4] for d in DIMENSIONS}
COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
          "#46f0f0", "#f032e6", "#bcf60c", "#008080", "#e6beff",
          "#9a6324", "#808000", "#800000", "#000075"]


def load_dim_scores(model):
    """把一个模型的所有维度得分（0-100）汇总。返回 {dim: score}。"""
    dims = {d["name"]: [] for d in DIMENSIONS}
    DIM_NAMES = {d["name"] for d in DIMENSIONS}
    def _dim_from_id(rid):
        # open 题的 id 形如 "说话之道-open-000"，取前缀维度名
        for dn in DIM_NAMES:
            if rid.startswith(dn):
                return dn
        return None

    def _add(src_key, path, scale=1.0, agg_field="per_question", qkey=None):
        if not Path(path).exists():
            return
        data = json.load(open(path, encoding="utf-8"))
        node = data if src_key == "mc" else data.get(src_key, {})
        perq = node.get(agg_field, node.get("per_question", []))
        for r in perq:
            dim = r.get("dimension") or (qkey or _dim_from_id)(r.get("id", ""))
            if dim and dim in dims:
                if src_key == "mc":
                    dims[dim].append(100 if r.get("correct") else 0)
                elif src_key == "trap":
                    dims[dim].append(r.get("score", 0))
                elif src_key == "open":
                    dims[dim].append(r.get("score", 0) * scale)
    _add("mc", f"results/mc-{model}.json")
    if not any(dims.values()):
        # 兼容旧文件名（如 deepseek-v4.json）
        _add("mc", f"results/deepseek-v4.json")
    _add("trap", f"results/trap-{model}.json")
    _add("open", f"results/open-{model}.json", scale=2.0)

    out = {}
    for dim in DIMENSIONS:
        vals = dims[dim["name"]]
        out[dim["name"]] = sum(vals) / len(vals) if vals else None
    # 用已有维度的均值填充缺失维度
    known = [v for v in out.values() if v is not None]
    fill = sum(known) / len(known) if known else 50.0
    return {k: (v if v is not None else fill) for k, v in out.items()}


def _svg_polygon(cx, cy, r, angles, vals, fill, opacity=0.25, stroke=None, dash=None):
    pts = []
    for i, v in enumerate(vals):
        a = angles[i]
        rr = r * v / 100.0
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return (f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" '
            f'fill="{fill}" opacity="{opacity}" stroke="{stroke or fill}" '
            f'stroke-width="2"{" stroke-dasharray=\"" + dash + "\"" if dash else ""} />')


def radar_svg(scores: dict, title="", w=640, h=640):
    cx, cy, R = w / 2, h / 2, 240
    n = len(scores)
    angles = [math.radians(90 - i * 360 / n) for i in range(n)]
    labels = [SHORT.get(d, d) for d in scores]
    vals = [scores[d] for d in scores]

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
             f'viewBox="0 0 {w} {h}">',
             f'<text x="{cx}" y="34" text-anchor="middle" font-size="20" '
             f'font-weight="bold" fill="#333">{title}</text>']
    # 网格（20/40/60/80/100）
    for g in (100, 80, 60, 40, 20):
        parts.append(_svg_polygon(cx, cy, R, angles, [g] * n, "#e0e0e0",
                                  opacity=0.5, stroke="#cccccc",
                                  dash="3,3" if g != 100 else None))
        parts.append(f'<text x="{cx + 6}" y="{cy - R * g / 100 + 4}" font-size="10" '
                     f'fill="#999">{g}</text>')
    # 轴线 + 标签
    for i, lbl in enumerate(labels):
        a = angles[i]
        x, y = cx + R * math.cos(a), cy - R * math.sin(a)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" '
                     f'stroke="#ddd" stroke-width="1" />')
        lx, ly = cx + (R + 26) * math.cos(a), cy - (R + 26) * math.sin(a)
        anchor = "middle" if abs(math.cos(a)) < 0.3 else ("start" if math.cos(a) > 0 else "end")
        dy = 4 if abs(math.sin(a)) < 0.3 else (1 if math.sin(a) < 0 else 12)
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                     f'font-size="13" fill="#444" dy="{dy}">{lbl}</text>')
    # 数据多边形
    parts.append(_svg_polygon(cx, cy, R, angles, vals, "#4363d8", opacity=0.30))
    pts = []
    for i, v in enumerate(vals):
        a = angles[i]
        rr = R * v / 100.0
        pts.append((cx + rr * math.cos(a), cy - rr * math.sin(a)))
        parts.append(f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.5" fill="#4363d8" />')
    parts.append("</svg>")
    return "".join(parts)


def multi_radar_svg(score_map: dict, title="多模型对比", w=720, h=720):
    """多模型叠加雷达图。score_map: {model: {dim: score}}"""
    cx, cy, R = w / 2, h / 2, 250
    dims = [d["name"] for d in DIMENSIONS]
    n = len(dims)
    angles = [math.radians(90 - i * 360 / n) for i in range(n)]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
             f'viewBox="0 0 {w} {h}">',
             f'<text x="{cx}" y="30" text-anchor="middle" font-size="20" '
             f'font-weight="bold" fill="#333">{title}</text>']
    for g in (100, 80, 60, 40, 20):
        parts.append(_svg_polygon(cx, cy, R, angles, [g] * n, "#eaeaea",
                                  opacity=0.5, stroke="#d5d5d5",
                                  dash="3,3" if g != 100 else None))
    for i, d in enumerate(dims):
        a = angles[i]
        x, y = cx + R * math.cos(a), cy - R * math.sin(a)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#ddd" />')
        lx, ly = cx + (R + 30) * math.cos(a), cy - (R + 30) * math.sin(a)
        anchor = "middle" if abs(math.cos(a)) < 0.3 else ("start" if math.cos(a) > 0 else "end")
        dy = 4 if abs(math.sin(a)) < 0.3 else (1 if math.sin(a) < 0 else 12)
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                     f'font-size="12" fill="#444" dy="{dy}">{SHORT[d]}</text>')
    for idx, (model, scores) in enumerate(score_map.items()):
        vals = [scores[d] for d in dims]
        color = COLORS[idx % len(COLORS)]
        parts.append(_svg_polygon(cx, cy, R, angles, vals, color, opacity=0.18))
        for i, v in enumerate(vals):
            a = angles[i]
            rr = R * v / 100.0
            parts.append(f'<circle cx="{cx + rr * math.cos(a):.1f}" '
                         f'cy="{cy - rr * math.sin(a):.1f}" r="2.6" fill="{color}" />')
    # 图例
    ly, lx = 30, w - 200
    for idx, (model, _) in enumerate(score_map.items()):
        color = COLORS[idx % len(COLORS)]
        parts.append(f'<rect x="{lx}" y="{ly}" width="12" height="12" fill="{color}" />')
        parts.append(f'<text x="{lx + 18}" y="{ly + 11}" font-size="12" fill="#333">{model}</text>')
        ly += 20
    parts.append("</svg>")
    return "".join(parts)


def build_all(out_dir="results/radar"):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    models = []
    for f in sorted(Path("results").glob("mc-*.json")):
        d = json.load(open(f, encoding="utf-8"))
        if d["model"] not in models:
            models.append(d["model"])
    for f in sorted(Path("results").glob("trap-*.json")):
        d = json.load(open(f, encoding="utf-8"))
        if d["model"] not in models:
            models.append(d["model"])
    print("参与雷达图的模型:", models)
    score_map = {}
    for m in models:
        scores = load_dim_scores(m)
        score_map[m] = scores
        Path(out_dir, f"{m}.svg").write_text(radar_svg(scores, title=m), encoding="utf-8")
        parts = " ".join(f"{SHORT[dd['name']]}={scores[dd['name']]:.0f}" for dd in DIMENSIONS)
        print(f"  → {m}.svg: " + parts)
    Path(out_dir, "overview.svg").write_text(multi_radar_svg(score_map), encoding="utf-8")
    print(f"\n多模型叠加图 → {out_dir}/overview.svg")
    return score_map


if __name__ == "__main__":
    build_all()