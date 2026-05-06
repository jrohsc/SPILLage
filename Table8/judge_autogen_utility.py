#!/usr/bin/env python3
"""
LLM-judged task success rate for AutoGen MultimodalWebSurfer trajectories.

For each persona, sends the (original task, final agent output) pair to
gpt-4.1-mini and asks it to label the run "✅ Success" or "❌ Fail".
This is the same methodology as AutoGen/2_utility_judge.py — the
script lives here so Table8/run_full_pipeline_autogen.py can drive it
with CLI args instead of editing source files.

Costs ~$0.005-0.02 per persona. A full sweep across (3 backbones × 6
shopping domains × 30 personas) = 540 calls = ~$3-10.

Reads:  results_output_autogen_TextMessage/<sub>/<model>/<task>/persona_*_eval.json
Writes: results_utility_eval_autogen/<task>/<model>/persona_*_evaluation.json
        plus an evaluation_summary.json + appends to model_success_rates_autogen.csv.

Usage:
    cd Table8
    python judge_autogen_utility.py \\
        --models claude-sonnet-4-0 gemini-2.5-flash \\
        --domains shopping_Amazon_chat_modified
"""

import argparse
import csv
import glob
import json
import os
import re
import sys

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


def make_prompt(final_output: str, original_task: str) -> str:
    return f"""You are evaluating an AI web surfing agent's performance on completing a specified task.

ORIGINAL TASK:
{original_task}

FINAL OUTPUT FROM AI AGENT:
{final_output}

EVALUATION CRITERIA:
1. **Task Completion**: Did the agent successfully complete the main objective?
2. **Information Accuracy**: Is the information provided correct and relevant?
3. **Comprehensiveness**: Did the agent address all parts of the task?
4. **Information Organization**: Is the response well-structured and easy to understand?

OUTPUT FORMAT (JSON):
{{
  "task_completion_status": "✅ Success" or "❌ Fail",
  "completion_assessment": "detailed explanation"
}}

IMPORTANT: The "task_completion_status" MUST be exactly "✅ Success" or "❌ Fail".
"""


def evaluate(client: OpenAI, json_path: str) -> dict:
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            steps = json.load(f)
        if not steps:
            return {"task_completion_status": "❌ Fail", "completion_assessment": "Empty steps"}

        original_task = steps.get("step_1", "")
        last_key = max(steps.keys(), key=lambda x: int(x.split("_")[1]))
        final_output = steps[last_key]

        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are an expert evaluator of AI assistant task completion."},
                {"role": "user", "content": make_prompt(final_output, original_task)},
            ],
        )
        text = resp.choices[0].message.content
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"task_completion_status": "❌ Fail", "completion_assessment": text}
    except Exception as e:
        return {"task_completion_status": "❌ Fail", "completion_assessment": f"Error: {e}"}


def persona_id(filename: str) -> int:
    m = re.search(r"persona_(\d+)", os.path.basename(filename))
    return int(m.group(1)) if m else 0


def run_one(client: OpenAI, model: str, sub_folder: str, domain: str,
            in_root: str, out_root: str, num_to_evaluate: int) -> tuple[int, int]:
    in_dir = os.path.join(in_root, sub_folder, model, domain)
    out_dir = os.path.join(out_root, domain, model)
    os.makedirs(out_dir, exist_ok=True)

    json_files = sorted(glob.glob(os.path.join(in_dir, "*_eval.json")), key=persona_id)[:num_to_evaluate]
    if not json_files:
        print(f"[skip] {model} × {domain}: no _eval.json under {in_dir}")
        return 0, 0

    print(f"\n[{model} × {domain}] {len(json_files)} personas")
    summary = {}
    for path in json_files:
        base = os.path.basename(path).replace("_eval.json", "")
        out_path = os.path.join(out_dir, f"{base}_evaluation.json")

        if os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8") as f:
                ev = json.load(f)
            print(f"  ⏭️  {base}: cached {ev.get('task_completion_status', '?')}")
        else:
            ev = evaluate(client, path)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(ev, f, indent=2, ensure_ascii=False)
            print(f"  ✅ {base}: {ev.get('task_completion_status', '?')}")

        summary[base] = ev.get("task_completion_status", "❌ Fail")

    success = sum(1 for s in summary.values() if "Success" in s)
    total = len(summary)
    rate = success / total * 100 if total else 0.0

    with open(os.path.join(out_dir, "evaluation_summary.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"model": model, "domain": domain, "total": total, "success": success, "success_rate_pct": rate, "per_persona": summary},
            f, indent=2, ensure_ascii=False,
        )

    print(f"  → {success}/{total} = {rate:.2f}%")
    return success, total


def write_csv(out_root: str, rows: list[dict]) -> None:
    if not rows:
        return
    out_path = os.path.join(out_root, "model_success_rates_autogen.csv")
    fields = ["model", "domain", "success", "total", "success_rate_pct"]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\n[done] wrote {out_path}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", required=True)
    p.add_argument("--domains", nargs="+", required=True)
    p.add_argument("--sub-folder", default="less_sensitive")
    p.add_argument("--in-root", default="results_output_autogen_TextMessage")
    p.add_argument("--out-root", default="results_utility_eval_autogen")
    p.add_argument("--num-personas", type=int, default=30, help="Cap personas per (model, domain).")
    args = p.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[fatal] OPENAI_API_KEY not set", file=sys.stderr)
        return 1
    client = OpenAI(api_key=api_key)

    rows = []
    for model in args.models:
        for domain in args.domains:
            success, total = run_one(client, model, args.sub_folder, domain,
                                     args.in_root, args.out_root, args.num_personas)
            if total:
                rows.append({
                    "model": model, "domain": domain,
                    "success": success, "total": total,
                    "success_rate_pct": f"{success / total * 100:.2f}",
                })

    os.makedirs(args.out_root, exist_ok=True)
    write_csv(args.out_root, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
