# 老中人情世故 Benchmark (ChineseSocialSurvivalBenchmark)

用 LLM 全自动构建的、评估大模型"人情世故"（中国式人际智慧：分寸感、潜台词、面子、人情往来）能力的 benchmark。

## 核心思想

人情世故 = **情境理解 × 分寸感 × 表达方式**。benchmark 不测知识，测模型在真实人际场景中能否选对、说对、做对。

## 全自动流水线（无人工标注）

```
① 生成 (src/generate.py)      LLM 按 10 大维度原创情境题（4选项+答案+解析）
        ↓
② 质检 (src/validate.py)      LLM judge 交叉审查：
        │    - 独立作答（不透露答案）→ 与标定答案比对，分歧即淘汰
        │    - 综合评审（答案唯一性/选项梯度/题干真实/文化适切/过犹不及）
        │      多轮采样，取保守结果；共识度低于 0.6 淘汰；语义去重
        ↓
③ 正式集 (data/benchmark/v1/)  通过质检的题目 + 标注信息
        ↓
④ 评测 (src/evaluate.py)      客观题自动判分 + 开放题 LLM-as-judge 打分
```

## 目录结构

```
config/settings.py      API 配置（可用环境变量覆盖）
src/client.py           轻量 OpenAI 兼容客户端（仅依赖 requests）
src/generate.py         ① 选择题/开放题生成器
src/validate.py         ② LLM judge 质检与过滤
src/evaluate.py         ④ 评测（客观题 + 开放题 judge）
data/out/               中间产物（原始生成、质检日志）
data/benchmark/v1/      正式 benchmark 集
results/                评测报告（json + markdown）
```

## 维度体系（10 类）

说话之道 · 饭局礼仪 · 面子文化 · 职场潜规则 · 人情往来 · 拒绝的艺术 · 分寸与边界 · 家庭关系 · 敏感话题 · 危机化解

## 使用方法

```bash
# 0. 设置 API（敏感信息只走环境变量，不入库）
export RENQING_BENCH_API_KEY="sk-xxx"
export RENQING_BENCH_API_BASE="https://your-api-endpoint/v1"   # 可选
export RENQING_BENCH_GEN_MODEL="grok-4.3-fast"                    # 可选
export RENQING_BENCH_JUDGE_MODEL="grok-4.3-fast"                  # 可选

# 1. 生成（按维度或全维度）
python3 -m src.generate --dimension "职场潜规则" --count 5
python3 -m src.generate --count 3          # 全部 10 个维度

# 2. 质检
python3 -m src.validate data/out/mc_raw/xxx.json --out data/benchmark/v1/mc/xxx.json
python3 -m src.validate --all              # 全量并行质检

# 3. 评测（被测模型 + 可选 judge 模型）
python3 -m src.evaluate --model deepseek-v4-flash-free --tag v1                 # 仅客观题
python3 -m src.evaluate --model deepseek-v4-flash-free --tag v1 --judge-model grok-4.3-fast  # 含开放题
python3 -m src.evaluate --model deepseek-v4-flash-free --tag v1 --runs 2         # 测答题稳定性
```

## 评测指标

- **客观题准确率**：模型作答与标准答案比对，按维度/难度分组统计
- **开放题分数**：judge 按 5 维 rubric（得体性/分寸感/可行性/长远性/理由）0~50 打分，多轮采样平均

## 已知设计与权衡

- **LLM 生成 + LLM 质检是"自产自销"**：judge 与被测若同模型会高估，故质检默认 2 个独立判官 + 与标定答案比对，只留"无争议"题。
- **judge 有噪声**：评审多轮采样取保守结果（所有轮次 pass 才收录）。
- **防污染**：生成 prompt 不含参考答案样例；素材用"情境关键词"而非现成段子，要求原创场景。
- **共识度**：每题标注主流中国人共识度（0~1），低于 0.6 不进正式集，避免收录"个别老顽固旧观念"。

## 后续路线

- [ ] 开放题 / 多轮对话题目生成与评测
- [ ] 不同 judge 模型做质检（用强模型质检弱模型的产物）
- [ ] 人类抽样验证 judge 分数的可靠性
- [ ] 难度分级统计、Leaderboard 化