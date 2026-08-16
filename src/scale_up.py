"""批量扩量脚本：多轮生成 MCQ / 陷阱题 / 开放题，每轮备份输出目录。

用法：python3 -m src.scale_up --mc-batches 5 --trap-batches 4 --open-batches 2
每批：MC 10维×3题=30、Trap 10维×3题=30、Open 10维×2题=20
"""
import argparse
import json
import shutil
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.client import LLMClient
from src.generate import generate_batch, DIMENSIONS as MC_DIMS
from src.trap_gen import generate_trap_batch
from src.generate_open import generate_open_batch


def backup(dir_path, tag):
    src = Path(dir_path)
    dst = Path(dir_path).parent / f"{Path(dir_path).name}_{tag}"
    if src.exists() and any(src.iterdir()):
        if not dst.exists():
            shutil.copytree(src, dst)
            return dst
    return None


def run_mc(client, batches):
    # 难度轮换：每批 3 题里 易/中/难 各 1，保证难度梯度
    diff_wheel = ["容易", "中等", "难"]
    for b in range(batches):
        tag = f"b{b+1}"
        backup("data/out/mc_raw", tag)
        print(f"\n########## MC 批次 {b+1}/{batches} ##########", flush=True)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda dim: generate_batch(
                client, dim, 3, diff_wheel[b % 3], out_dir="data/out/mc_raw"), MC_DIMS))
        time.sleep(3)


def run_trap(client, batches):
    for b in range(batches):
        tag = f"b{b+1}"
        backup("data/out/trap_raw", tag)
        print(f"\n########## TRAP 批次 {b+1}/{batches} ##########", flush=True)
        generate_trap_batch(client, count_per_dim=3, out_dir="data/out/trap_raw")
        time.sleep(3)


def run_open(client, batches):
    for b in range(batches):
        tag = f"b{b+1}"
        backup("data/out/open_raw", tag)
        print(f"\n########## OPEN 批次 {b+1}/{batches} ##########", flush=True)
        generate_open_batch(client, count_per_dim=2, out_dir="data/out/open_raw")
        time.sleep(3)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mc-batches", type=int, default=0)
    ap.add_argument("--trap-batches", type=int, default=0)
    ap.add_argument("--open-batches", type=int, default=0)
    ap.add_argument("--model", type=str, default=None)
    args = ap.parse_args()
    client = LLMClient(model=args.model or None)
    print("扩量开始:", vars(args), flush=True)
    if args.mc_batches:
        run_mc(client, args.mc_batches)
    if args.trap_batches:
        run_trap(client, args.trap_batches)
    if args.open_batches:
        run_open(client, args.open_batches)
    print("SCALE_UP_DONE", flush=True)