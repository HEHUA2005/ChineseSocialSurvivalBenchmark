<div align="center">

# 🏮 ChineseSocialSurvivalBenchmark

### 老中人情世故 Benchmark

> 一个**全自动构建**的、评估大模型「人情世故」能力的开源基准
> 不考知识，考的是**看清潜台词、拿捏分寸、体面做人**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()
[![Benchmark v0.1](https://img.shields.io/badge/Benchmark-v0.1-8A2BE2.svg)]()
[![中文](https://img.shields.io/badge/语言-中文-orange.svg)]()

---

[特性](#-特性) · [流水线](#-全自动流水线) · [排行榜](#-排行榜) · [示例题](#-示例题) · [快速开始](#-快速开始) · [Roadmap](#-roadmap)

</div>

---

## 📢 一句话介绍

现有的中文基准（CMMLU、C-Eval 等）测的是**知识储备**，而大模型在中文社交场景中最大的失误往往不是「不知道」，而是「不会做人」——过于坦诚、把客套话当真、公开场合驳人面子。

**ChineseSocialSurvivalBenchmark** 用 10 大维度、21+ 道高共识情境题，专门量化模型的**社会判断力**：情境理解 × 分寸感 × 表达方式。

## ✨ 特性

- 🤖 **全自动流水线**：LLM 生成题目 → LLM judge 三层对抗质检 → 自动评测，**零人工标注**
- 🛡️ **防自欺设计**：独立判官（不看到答案）与生成器交叉验证，63% 的低质题被过滤
- 🎭 **三种题型**：客观题 / 开放题 5 维 rubric judge 打分 / **陷阱题（加权失误评分）**
- ⚖️ **错误分类学**：10 类人情世故失误分级加权（驳面子−10 → 小失误−2），陷阱题按「多害相权取其轻」给分
- 📏 **共识度标注**：每题标注「主流中国人认同度」，剔除只有老顽固认可的旧观念
- 📊 **能力雷达图**：10 维度画像（说话之道/饭局/面子/职场/人情/拒绝/分寸/家庭/敏感/危机）纯 SVG 生成
- 🔍 **可解释报告**：按维度/难度分组统计 + 答题稳定性指标 + 逐题解析

## 🔧 全自动流水线

```mermaid
flowchart LR
    A[题源生成<br/>grok-4.3-fast] --> B{LLM judge 质检}
    B -->|独立判官×2 交叉验证| C{综合评审×2采样<br/>5维打分 + 共识度}
    C -->|通过| D[(正式集<br/>data/benchmark/v1)]
    C -->|淘汰 63%| E[丢弃]

    T[陷阱题生成<br/>无完美解困境 + 错误权重] --> V{判官严重度校验<br/>3判官投票 best}
    V -->|通过 43%| D
    V -->|争议题| E

    D --> F[评测被测模型<br/>deepseek 等]
    F --> G[客观题准确率<br/>✓ 自动判分]
    F --> H[开放题 judge 分<br/>✓ rubric 0-50]
    F --> J[陷阱题加权得分<br/>✓ 失误罚分制]
    G & H & J --> R[能力雷达图<br/>✓ 10维 SVG]
    R --> I[(评测报告 + 排行榜)]
```

**防污染关键设计**：生成 prompt 中不出现任何「答案样例」，只用维度 + 情境种子，强制模型原创场景，避免复读网络段子。

## 🏆 排行榜

> v1.0（2025-08，11 道客观题 + 13 道陷阱题 + 10 道开放题，6 个模型）

**综合总分** = 45% 客观题准确率 + 30% 陷阱题加权得分 + 25% 开放题评分（满分 100）

| 排名 | 模型 | 总分 | 客观题 | 陷阱题 | 开放题(×2) |
|---|------|------|--------|--------|-----------|
| 1 | hy3-free | **83.9** | 90.9% | 77.2 | **79.2** |
| 2 | nemotron-3.5-lightning-free | **80.1** | 90.9% | 70.0 | 72.7 |
| 3 | deepseek-v4-flash-free | **79.6** | 81.8%※ | 78.7 | 76.5 |
| 4 | grok-4.5 | **79.1** | 81.8%※ | **79.7** | 73.3 |
| 5 | grok-4.3-fast | **77.6** | 81.8% | 69.7 | 79.3 |
| 6 | grok-4.20-0309-reasoning | **71.6** | 72.7% | 71.5 | 69.8 |

> ⚠️ **※ 稳定性提示**：同一模型多次答题采样有波动——deepseek 客观题两次测量为 **90.9% / 81.8%**，
> grok-4.5 两次为 **81.8% / 100%**。排名仅供参考，关注维度画像（雷达图）比总分更有意义。
> 另外 deepseek / grok-4.20 在『面子文化』维度反复选错，见下方示例。

### 📊 能力雷达图（10 维度）

[多模型叠加图](results/radar/overview.svg)｜单模型：
[deepseek](results/radar/deepseek-v4-flash-free.svg) · [grok-4.5](results/radar/grok-4.5.svg) · [grok-4.3-fast](results/radar/grok-4.3-fast.svg) · [grok-4.20](results/radar/grok-4.20-0309-reasoning.svg) · [hy3](results/radar/hy3-free.svg) · [nemotron](results/radar/nemotron-3.5-lightning-free.svg)

> 辨别度观察：
> - **面子文化**：deepseek 93 分 vs grok-4.3-fast 36 分——grok-4.3-fast 倾向公开处理、直球表达
> - **危机化解**：nemotron 39 分 vs 其他模型 68-78 分——补救能力明显掉队
> - **说话之道**：deepseek 93 分 vs grok-4.20 60 分

> 想上榜？在 [Issues](https://github.com/HEHUA2005/ChineseSocialSurvivalBenchmark/issues) 提交你的模型评测结果，或直接跑 `src/evaluate.py` + `src/trap_eval.py`。

## 🧪 示例题

> **维度：面子文化**　共识度 0.9
>
> 作为小红书群管理员，你正在群里管理不少朋友和熟人。突然有老同学小张发了一条广告，硬说『限时特价，拒绝收钱』，实际想推销产品，群里有人直呼违规。你正在斟酌怎么办。小张平时很活跃，但最近欠你一个大忙，你知道如果因为这事闹僵，他可能就再不联系你了。这时你最得体的做法是？
>
> - A. 直接删掉小张的帖子和账号，告诉大家这是违规广告，让大家别点。
> - B. 私聊小张问他是不是违规广告，让他解释清楚，但没删帖。✅ **（答案）**
> - C. 对小张说『最近工作忙，有点敏感啊，要是真违规我可不好办，你自己看着办吧』，然后不管不问。
> - D. 公开发帖先调侃一下小张『老同学发广告我可帮不了你，群规得守，哈哈』。

> 💡 **有意思的是**：deepseek 在这题上选了 D（公开调侃）。它的「用幽默化解、避免直接冲突」思路偏年轻化/西方沟通文化，与主流中国式「私下解决、公开留面子」存在可复现的偏差——这正是该基准想测出来的东西。

---

> **陷阱题示例（维度：说话之道）** —— 这题**没有完美解**，所有选项都会犯错，区别只在错误轻重
>
> 公司评功会上，领导让你评价两个同事 A 和 B，他们都有功有过。A 帮忙筹办了盛大活动、受到高层肯定，但因未上报额外成本，审批被驳回。B 受邀参与活动并在领导讲话时发挥出色，但会后未及时整理会议纪要，导致资料丢失。领导说「评价时不伤脸就好」。其他同事在场。最稳妥的做法是？
>
> - A.（罚 11）先夸 A 功劳大、再提「不过成本没报，审批有风险」…
> - B.（罚 14）当众指出 A 的失职、点评 B 纪要管理不足
> - C.（罚 8）说 A 和 B 都是功过参半，推给领导拍板
> - D.（罚 2，损失最小）只夸双方功劳，只字不提过失
>
> 💡 陷阱题的真相：**「各打五十大板」看似公平，实则是当众评价他人 + 推卸责任**（罚 8）；
> 真正损失最小的做法是只褒不贬——不给他人难堪、不落人口实。模型选 A 是「负责任但伤脸」，选 B 是「直球但失礼」，分数自然拉开。

## 🚀 快速开始

```bash
git clone https://github.com/HEHUA2005/ChineseSocialSurvivalBenchmark.git
cd ChineseSocialSurvivalBenchmark
pip install requests   # 唯一依赖

# 0. 配置 API：复制 .env.example 为 .env 并填写你的密钥（.env 已被 gitignore，不会泄露）
cp .env.example .env
# 然后编辑 .env：
#   RENQING_BENCH_API_KEY=sk-xxx
#   RENQING_BENCH_API_BASE=https://your-api-endpoint/v1   # 可选，默认值是占位符
#   RENQING_BENCH_GEN_MODEL=grok-4.3-fast                # 可选
#   RENQING_BENCH_JUDGE_MODEL=grok-4.3-fast              # 可选

# 1. 生成题目（按维度或全维度）
python3 -m src.generate --dimension "职场潜规则" --count 5
python3 -m src.generate --count 3          # 全部 10 个维度并行

# 2. 质检（LLM judge 三层过滤）
python3 -m src.validate data/out/mc_raw/xxx.json --out data/benchmark/v1/mc/xxx.json
python3 -m src.validate --all              # 全量并行质检

# 3. 评测被测模型
python3 -m src.evaluate --model deepseek-v4-flash-free --tag v1                 # 仅客观题
python3 -m src.evaluate --model deepseek-v4-flash-free --tag v1 \
  --judge-model grok-4.3-fast              # 含开放题 judge 打分
python3 -m src.evaluate --model deepseek-v4-flash-free --tag v1 --runs 2         # 测答题稳定性

# 4. 陷阱题（无完美解困境，加权失误评分）
python3 -m src.trap_gen --count 3 --model grok-4.3-fast   # 生成
python3 -m src.trap_validate --model grok-4.3-fast        # 判官严重度校验
python3 -m src.trap_eval --model deepseek-v4-flash-free   # 加权评测

# 5. 汇总可视化
python3 -m src.radar            # 10 维能力雷达图（SVG）
python3 -m src.leaderboard      # 综合排行榜（markdown）
```

## 📁 项目结构

```
ChineseSocialSurvivalBenchmark/
├── src/
│   ├── generate.py      # ① 选择题生成器
│   ├── generate_open.py # ① 开放题生成器
│   ├── trap_gen.py      # ① 陷阱题生成器（无完美解困境 + 错误权重）
│   ├── validate.py      # ② LLM judge 质检与过滤
│   ├── trap_validate.py # ② 陷阱题判官严重度校验（3 判官投票）
│   ├── evaluate.py      # ④ 评测（客观题 + 开放题 judge）
│   ├── trap_eval.py     # ④ 陷阱题加权评测（失误罚分制）
│   ├── dims.py          # 维度体系 + 错误分类学（10 类失误权重）
│   ├── radar.py         # ⑤ 10 维能力雷达图（纯 SVG）
│   ├── leaderboard.py   # ⑤ 综合排行榜聚合
│   └── client.py        # 轻量 OpenAI 兼容客户端
├── data/
│   └── benchmark/v1/    # 正式 benchmark 集（11 客观题 + 13 陷阱题 + 10 开放题）
├── results/             # 评测报告（json + markdown + 雷达图 svg）
├── docs/design.md       # 设计文档与首测分析
└── config/settings.py   # 环境变量配置
```

## 🗂️ 维度体系（Taxonomy）

| 维度 | 考察点 |
|---|---|
| 🗣️ 说话之道 | 委婉表达、弦外之音、点到为止 |
| 🍽️ 饭局礼仪 | 座次、敬酒、点菜、买单的分寸 |
| 🀄 面子文化 | 给面子、留台阶、打圆场 |
| 💼 职场潜规则 | 功高盖主、不当面评价同事、汇报分寸 |
| 🎁 人情往来 | 欠人情、还人情、礼尚往来的节奏 |
| 🚫 拒绝的艺术 | 怎么拒绝才不得罪人 |
| 📏 分寸与边界 | 交浅言深、客套话 vs 真邀请 |
| 🏠 家庭关系 | 婆媳、亲戚、辈分 |
| 🤫 敏感话题 | 工资、年龄、婚育的回避技巧 |
| 🆘 危机化解 | 误会、尴尬、说错话的补救 |

## 🧭 设计理念

人情世故的判断优先级：**① 安全（不得罪人）> ② 真实（不虚伪）> ③ 长远（维护关系）**，同时警惕「过犹不及」——满口大道理、永远打太极的答案同样不及格。

质量保障三道防线（详见 [docs/design.md](docs/design.md)）：
1. **独立判官**：judge 不看答案独立作答，与标定答案分歧即淘汰
2. **多轮采样保守评审**：所有轮次通过才收录，缓解 LLM judge 噪声
3. **共识度门槛**：主流共识 < 0.6 的题不进正式集

## 🗺️ Roadmap

- [x] v0.1：流水线跑通，21 题正式集，deepseek 首测
- [ ] v0.2：扩量至 100+ 题（已验证题目作 few-shot 种子迭代）
- [ ] v0.3：多轮对话题目（测「说到做到」与临场应变）
- [ ] v0.4：交叉质检（不同模型族互相质检，消除同族偏差）
- [ ] v0.5：人类抽样验证，对齐 judge 分数与人类评分
- [ ] 官方排行榜 + Leaderboard 页

## 🤝 参与贡献

欢迎任何形式的贡献：加入更多模型评测结果、扩充题目、改进 judge 逻辑、报告坏题。请通过 [Issues](https://github.com/HEHUA2005/ChineseSocialSurvivalBenchmark/issues) 或 PR 参与。

## 📄 License

[MIT](LICENSE) © HEHUA2005