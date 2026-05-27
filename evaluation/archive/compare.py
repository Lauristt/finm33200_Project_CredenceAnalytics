"""Compare no-AI vs AI, before vs after the verification fix.

This is the centerpiece for the course question: *does the AI component add value
over a non-AI version of the same workflow?* It reads the four result files
produced by run_eval.py and prints one side-by-side table.

Usage:
    python3 evaluation/compare.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# (stage, judge, results file produced by run_eval.py)
RUNS_V1 = [
    ("before fix", "no-AI", "results_heuristic.json"),
    ("before fix", "AI",    "results_ai.json"),
    ("after fix",  "no-AI", "results_heuristic_fixed.json"),
    ("after fix",  "AI",    "results_ai_fixed.json"),
]
# v2 = reasoning-heavy claims (direction + paraphrase), where AI may add value.
RUNS_V2 = [
    ("v2 reasoning", "no-AI", "results_v2_heuristic.json"),
    ("v2 reasoning", "AI",    "results_v2_ai.json"),
]


def auc(true_scores: list[float], false_scores: list[float]) -> float:
    if not true_scores or not false_scores:
        return float("nan")
    wins = sum(1.0 if a > b else 0.5 if a == b else 0.0
               for a in true_scores for b in false_scores)
    return wins / (len(true_scores) * len(false_scores))


def metrics(rows: list[dict]) -> dict:
    trues = [r for r in rows if r["label"] == "true"]
    falses = [r for r in rows if r["label"] == "false"]
    expected = lambda r: "credible" if r["label"] == "true" else "not_credible"
    return {
        "auc": auc([r["final_confidence"] for r in trues],
                   [r["final_confidence"] for r in falses]),
        "contra": sum(1 for r in falses if r["numeric_verdict"] == "contradicted"),
        "n_false": len(falses),
        "acc": sum(1 for r in rows if r["tool_binary"] == expected(r)) / len(rows),
        "base": sum(1 for r in rows if r["baseline_binary"] == expected(r)) / len(rows),
    }


def print_table(title: str, runs: list[tuple[str, str, str]]) -> None:
    print(f"\n{title}")
    print(f"{'stage':<14}{'judge':<8}{'AUC':>7}{'accuracy':>11}{'baseline':>10}")
    print("-" * 50)
    for stage, judge, fname in runs:
        path = HERE / fname
        if not path.exists():
            print(f"{stage:<14}{judge:<8}  (not run yet: {fname})")
            continue
        m = metrics(json.loads(path.read_text(encoding="utf-8")))
        print(f"{stage:<14}{judge:<8}{m['auc']:>7.2f}{m['acc']:>10.0%}{m['base']:>10.0%}")


def main() -> None:
    print_table("V1 - exact numeric facts (deterministic regime)", RUNS_V1)
    print_table("V2 - reasoning claims (direction + paraphrase)", RUNS_V2)
    print("\nHow to read it:")
    print("  - V1: once the verification logic is fixed, AI adds nothing -> rules win.")
    print("  - V2: compare 'no-AI' vs 'AI' on reasoning claims -> here AI can add value.")
    print("  - 'baseline' = trivial number-in-evidence rule.")


if __name__ == "__main__":
    main()
