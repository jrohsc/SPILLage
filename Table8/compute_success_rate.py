#!/usr/bin/env python3
"""
Compute Browser-Use task success rates from parsed agent logs (Table 8).

Reads `{model}_parsed_json_format/{domain}/*.json` produced by
`parse_to_json.py` and marks a task as a success when the agent's
self-reported `header.completion_status` contains "✅" or "successfully"
(case-insensitive). Writes per-(model, domain) breakdown plus an OVERALL
row to `model_success_rates.csv`.

Usage:
    cd Table8
    python compute_success_rate.py \\
        --models gemini-2.5-flash claude-sonnet-4-0 deepseek-reasoner

Run after the upstream pipeline:
    1. run_agent.py        -> raw .log files
    2. parse_logs.py       -> {model}_parsed/
    3. parse_to_json.py    -> {model}_parsed_json_format/
"""

import argparse
import json
import os
import sys
from collections import defaultdict


DEFAULT_MODELS = [
    "gpt-4o",
    "o3",
    "o4-mini",
    "claude-sonnet-4-0",
    "gemini-2.5-flash",
    "deepseek-reasoner",
]


def is_success(completion_status: str) -> bool:
    if not completion_status:
        return False
    return "✅" in completion_status or "successfully" in completion_status.lower()


def calculate_success_rates(root: str, models: list[str], output_csv: str) -> None:
    results = defaultdict(lambda: defaultdict(lambda: {"success": 0, "total": 0}))
    all_categories: set[str] = set()

    for model in models:
        json_dir = os.path.join(root, f"{model}_parsed_json_format")
        if not os.path.isdir(json_dir):
            print(f"[skip] directory not found: {json_dir}")
            continue

        print(f"[scan] {model} <- {json_dir}")
        for category in os.listdir(json_dir):
            category_path = os.path.join(json_dir, category)
            if not os.path.isdir(category_path):
                continue
            all_categories.add(category)

            for filename in os.listdir(category_path):
                if not filename.endswith(".json"):
                    continue
                json_path = os.path.join(category_path, filename)
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    print(f"  [error] {json_path}: {e}")
                    continue

                header = data.get("header", {})
                status = header.get("completion_status")
                if status is None:
                    continue

                results[model][category]["total"] += 1
                if is_success(status):
                    results[model][category]["success"] += 1

    # Console summary
    print("\n" + "=" * 80)
    print("SUCCESS RATES BY MODEL AND CATEGORY")
    print("=" * 80)
    for model in models:
        print(f"\n{model}")
        print("-" * len(model))
        m_success, m_total = 0, 0
        for category in sorted(all_categories):
            cell = results[model][category]
            success, total = cell["success"], cell["total"]
            if total > 0:
                rate = success / total * 100
                print(f"  {category}: {rate:.2f}% ({success}/{total})")
                m_success += success
                m_total += total
            else:
                print(f"  {category}: N/A (0/0)")
        if m_total > 0:
            print(f"  OVERALL: {m_success / m_total * 100:.2f}% ({m_success}/{m_total})")
        else:
            print("  OVERALL: N/A (0/0)")

    # CSV output
    with open(output_csv, "w") as csv_file:
        csv_file.write("Category")
        for model in models:
            csv_file.write(f",{model} Success Rate,{model} Success Count,{model} Total Count")
        csv_file.write("\n")

        for category in sorted(all_categories):
            csv_file.write(f"{category}")
            for model in models:
                cell = results[model][category]
                success, total = cell["success"], cell["total"]
                if total > 0:
                    csv_file.write(f",{success / total * 100:.2f},{success},{total}")
                else:
                    csv_file.write(",0,0,0")
            csv_file.write("\n")

        csv_file.write("OVERALL")
        for model in models:
            m_success = sum(results[model][c]["success"] for c in all_categories)
            m_total = sum(results[model][c]["total"] for c in all_categories)
            if m_total > 0:
                csv_file.write(f",{m_success / m_total * 100:.2f},{m_success},{m_total}")
            else:
                csv_file.write(",0,0,0")
        csv_file.write("\n")

    print(f"\n[done] wrote {output_csv}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--root",
        default="results_output/less_sensitive",
        help="Directory containing {model}_parsed_json_format subfolders.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        help="Model slugs whose _parsed_json_format directories should be aggregated.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV path. Defaults to <root>/model_success_rates.csv.",
    )
    args = parser.parse_args()

    output_csv = args.output or os.path.join(args.root, "model_success_rates.csv")
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    calculate_success_rates(args.root, args.models, output_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
