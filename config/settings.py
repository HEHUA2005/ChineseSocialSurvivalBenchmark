"""全局配置。所有敏感信息只从环境变量读取，不硬编码。

使用前设置：
    export RENQING_BENCH_API_KEY="sk-xxx"
可选覆盖：
    export RENQING_BENCH_API_BASE="https://your-api-endpoint/v1"
    export RENQING_BENCH_GEN_MODEL="grok-4.3-fast"
    export RENQING_BENCH_JUDGE_MODEL="grok-4.3-fast"
"""
import os

# ---- LLM API 配置（全部来自环境变量）----
API_BASE = os.environ.get("RENQING_BENCH_API_BASE", "https://your-api-endpoint/v1")
API_KEY = os.environ.get("RENQING_BENCH_API_KEY", "")

# 生成用的模型
GENERATION_MODEL = os.environ.get("RENQING_BENCH_GEN_MODEL", "grok-4.3-fast")

# Judge 用的模型（可用更强的模型做质检）
JUDGE_MODEL = os.environ.get("RENQING_BENCH_JUDGE_MODEL", "grok-4.3-fast")

# 常见参数
TEMPERATURE = 0.7
MAX_TOKENS = 4096
TIMEOUT = 120
MAX_RETRIES = 4


def require_api_key():
    if not API_KEY:
        raise RuntimeError("未设置 RENQING_BENCH_API_KEY 环境变量。请先 export。")
    return API_KEY