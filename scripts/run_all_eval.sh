#!/usr/bin/env bash
# 全题型总控评测：6 模型 × (MC runs2 + trap + open + sort + mt)
# 用法: bash scripts/run_all_eval.sh [阶段序号]
#   1 = MC (runs=2)   2 = trap   3 = open   4 = sort   5 = mt
set -u
cd "$(dirname "$0")/.."
# 敏感 API 配置从 .env 读取（绝不硬编码进仓库）
if [ -f .env ]; then
  set -a; source .env; set +a
fi
: "${RENQING_BENCH_API_KEY:?请先在 .env 配置 RENQING_BENCH_API_KEY}"

MODELS=(
  "grok-4.5"
  "deepseek-v4-flash-free"
  "hy3-free"
  "nemotron-3.5-lightning-free"
)
STAGE="${1:-all}"
PY=python3

run_stage_mc() {
  for m in "${MODELS[@]}"; do
    echo ">>> MC  $m  (runs=2)"
    $PY -u -m src.evaluate --model "$m" --tag "mc-$m" --runs 2 || echo "[失败] mc $m"
  done
}

run_stage_trap() {
  for m in "${MODELS[@]}"; do
    echo ">>> TRAP  $m"
    $PY -u -m src.trap_eval --model "$m" --tag "$m" || echo "[失败] trap $m"
  done
}

run_stage_open() {
  for m in "${MODELS[@]}"; do
    echo ">>> OPEN  $m"
    $PY -u -m src.evaluate --model "$m" --tag "open-$m" --judge-model grok-4.3-fast --judge-rounds 2 || echo "[失败] open $m"
  done
}

run_stage_sort() {
  for m in "${MODELS[@]}"; do
    echo ">>> SORT  $m"
    $PY -u -m src.sort_eval --model "$m" --tag "$m" || echo "[失败] sort $m"
  done
}

run_stage_mt() {
  for m in "${MODELS[@]}"; do
    echo ">>> MT  $m"
    $PY -u -m src.multi_turn_eval --model "$m" --tag "mt-$m" || echo "[失败] mt $m"
  done
}

case "$STAGE" in
  1|mc) run_stage_mc ;;
  2|trap) run_stage_trap ;;
  3|open) run_stage_open ;;
  4|sort) run_stage_sort ;;
  5|mt) run_stage_mt ;;
  all)
    run_stage_mc; run_stage_trap; run_stage_open; run_stage_sort; run_stage_mt ;;
esac
echo "ALL_EVAL_DONE stage=$STAGE"