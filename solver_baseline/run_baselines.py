from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time
from typing import Any, List, Type

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(CURRENT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from env import DeliveryEnv, load_config
from solver_baseline import BASELINE_SOLVERS


def stable_config_seed(config_name: str, base_seed: int) -> int:
    digest = hashlib.md5(f"{base_seed}:{config_name}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def run_solver(solver_cls: Type[Any], cfg: dict, seed: int) -> dict:
    env = DeliveryEnv(copy.deepcopy(cfg), seed=seed)
    solver = solver_cls(env)
    return solver.run()


def error_result(method: str, cfg: dict, error: str) -> dict:
    total_orders = int(cfg.get("G", 0))
    return {
        "method": method,
        "config_name": cfg.get("name", "unknown"),
        "total_orders": total_orders,
        "orders_generated": 0,
        "delivered": 0,
        "on_time": 0,
        "late": 0,
        "missed": total_orders,
        "delivery_rate": 0.0,
        "on_time_rate": 0.0,
        "total_reward": 0.0,
        "total_movecost": 0.0,
        "net_reward": 0.0,
        "elapsed_sec": 0.0,
        "shipper_rewards": [],
        "status": "ERROR",
        "error": error,
    }


def select_solvers(method: str) -> List[Type[Any]]:
    if method == "all":
        return list(BASELINE_SOLVERS)
    selected = [cls for cls in BASELINE_SOLVERS if cls.__name__ == method or cls.method_name == method]
    if not selected:
        names = ", ".join(cls.__name__ for cls in BASELINE_SOLVERS)
        raise SystemExit(f"[ERROR] Unknown baseline '{method}'. Available classes: {names}")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Run basic baseline solvers.")
    parser.add_argument("--config", required=True, help="Path to test_config.txt or val_config.txt")
    parser.add_argument("--out", default="results_solver_baseline", help="Output directory")
    parser.add_argument("--method", default="all", help="all, class name, or method_name")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    configs = load_config(args.config)
    solvers = select_solvers(args.method)

    all_results = []
    results_by_config = []
    total_start = time.time()

    print("Baseline solvers:", ", ".join(cls.method_name for cls in solvers))
    print(f"Configs: {len(configs)} from {args.config}\n")

    for cfg in configs:
        name = cfg.get("name", "unknown")
        seed = stable_config_seed(str(name), int(cfg.get("base_seed", 42)))
        cfg_results = []
        print(f"[{name}] N={cfg['N']} C={cfg['C']} G={cfg['G']} T={cfg['T']}")

        for solver_cls in solvers:
            started = time.time()
            try:
                result = run_solver(solver_cls, cfg, seed)
            except Exception as exc:
                result = error_result(solver_cls.method_name, cfg, str(exc))
            result["wall_sec"] = round(time.time() - started, 2)
            cfg_results.append(result)
            all_results.append(result)
            print(
                f"  {result['method']:<28} net={result['net_reward']:>8.2f} "
                f"delivered={result['delivered']}/{result['total_orders']} "
                f"on_time={result['on_time']} t={result['wall_sec']:.2f}s"
            )

        payload = {
            "config_name": name,
            "orders_total_fixed": cfg["G"],
            "online_generation": True,
            "results": cfg_results,
        }
        results_by_config.append(payload)
        with open(os.path.join(args.out, f"result_{name}.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print("")

    total_score_by_method = {
        method: round(sum(r["net_reward"] for r in all_results if r["method"] == method), 4)
        for method in sorted({r["method"] for r in all_results})
    }
    summary = {
        "config_file": args.config,
        "online_generation": True,
        "total_elapsed": round(time.time() - total_start, 2),
        "total_score_by_method": total_score_by_method,
        "results_by_config": results_by_config,
        "all_results": all_results,
    }

    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "all_results.json"), "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print("Total score by method:")
    for method, score in total_score_by_method.items():
        print(f"- {method}: {score:.2f}")
    print(f"\nSaved results to {args.out}")


if __name__ == "__main__":
    main()

