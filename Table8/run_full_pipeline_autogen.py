#!/usr/bin/env python3
"""
End-to-end AutoGen pipeline: agent runs -> parsed logs -> task success
rate -> LLM-jury -> per-backbone Tables 2/3/8 cells.

Counterpart to run_full_pipeline_browseruse.py for the AutoGen
MultimodalWebSurfer stack. Same six-stage shape, different parsers and
a different success-rate methodology (LLM-judged via gpt-4.1-mini,
not parsed from completion_status).

Usage:
    cd Table8

    # Smoke test: 1 (model, domain, persona) before the full sweep.
    python run_full_pipeline_autogen.py \\
        --models gemini-2.5-flash \\
        --domains shopping_Amazon_email_modified \\
        --start-persona 1 --end-persona 1

    # Full sweep — all 5 backbones × 6 shopping domains × 30 personas.
    python run_full_pipeline_autogen.py \\
        --models gpt-4o o3 o4-mini gemini-2.5-flash claude-sonnet-4-0 \\
        --domains shopping_Amazon_chat_modified shopping_Amazon_email_modified \\
                  shopping_Amazon_generic_modified \\
                  shopping_ebay_chat_modified shopping_ebay_email_modified \\
                  shopping_ebay_generic_modified

    # Re-parse + re-judge without re-running agents.
    python run_full_pipeline_autogen.py --models gpt-4o \\
        --domains shopping_Amazon_chat_modified --skip-agent-run

NOTE: AutoGen × deepseek-reasoner is NOT supported — MultimodalWebSurfer
requires a vision-capable model and DeepSeek-R1 is text-only. Use
run_full_pipeline_browseruse.py for R1 instead.

Per (model × domain) the orchestrator runs:
  1. run_agent_autogen.py      → results_output_autogen/<sub>/<model>/<task>/persona_*.log
  2. parse_autogen_logs.py     → results_output_autogen_TextMessage/<sub>/<model>/<task>/*_eval.json
  3. judge_autogen_utility.py  → results_utility_eval_autogen/<task>/<model>/persona_*_evaluation.json
                                 + model_success_rates_autogen.csv
  4. llm_jury_autogen.py       → llm_jury_eval/results_autogen_<model>/<task>/jury_results_fixed.json
  5. aggregate_to_tables.py    → llm_jury_eval/tables_filled_<model>.{md,tex}
                                 (combined with browseruse runs if both have run)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
JURY_SCRIPTS = REPO_ROOT / "llm_jury_eval" / "scripts"


def sh(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    if cwd:
        print(f"  (cwd: {cwd})")
    return subprocess.run(cmd, cwd=cwd).returncode


def step_run_agents(models: list[str], domains: list[str], sub_folder: str,
                    start_persona: int, end_persona: int) -> None:
    print("\n" + "=" * 72)
    print("STEP 1 — AutoGen agent runs")
    print("=" * 72)
    for model in models:
        if model == "deepseek-reasoner":
            print(f"\n[skip] {model}: AutoGen MultimodalWebSurfer requires vision; "
                  f"R1 is text-only. Use run_full_pipeline_browseruse.py instead.")
            continue
        for domain in domains:
            rc = sh(
                [
                    sys.executable, "run_agent_autogen.py",
                    "--model", model,
                    "--task", domain,
                    "--sub-folder", sub_folder,
                    "--start-persona", str(start_persona),
                    "--end-persona", str(end_persona),
                ],
                cwd=THIS_DIR,
            )
            if rc != 0:
                print(f"[warn] run_agent_autogen.py exited {rc} for {model} × {domain}; continuing")


def step_parse(models: list[str], sub_folder: str) -> None:
    print("\n" + "=" * 72)
    print("STEP 2 — Parse AutoGen logs to TextMessage JSON")
    print("=" * 72)
    sh(
        [sys.executable, "parse_autogen_logs.py", "--models", *models, "--sub-folder", sub_folder],
        cwd=THIS_DIR,
    )


def step_success_rate(models: list[str], domains: list[str], sub_folder: str,
                      num_personas: int) -> None:
    print("\n" + "=" * 72)
    print("STEP 3 — Task success rate (LLM-judged)")
    print("=" * 72)
    sh(
        [
            sys.executable, "judge_autogen_utility.py",
            "--models", *models,
            "--domains", *domains,
            "--sub-folder", sub_folder,
            "--num-personas", str(num_personas),
        ],
        cwd=THIS_DIR,
    )


def step_jury(models: list[str], domains: list[str], sub_folder: str) -> None:
    print("\n" + "=" * 72)
    print("STEP 4 — LLM-Jury (AutoGen)")
    print("=" * 72)
    if not JURY_SCRIPTS.exists():
        print(f"[skip] {JURY_SCRIPTS} not found; jury step requires the llm_jury_eval/ folder.")
        return

    for model in models:
        traj_dir = THIS_DIR / "results_output_autogen_TextMessage" / sub_folder / model
        if not traj_dir.exists():
            print(f"[skip] {model}: no parsed-TextMessage dir at {traj_dir}; run parse_autogen_logs first.")
            continue
        for domain in domains:
            domain_dir = traj_dir / domain
            if not any(domain_dir.glob("*_eval.json")):
                print(f"[skip] {model} × {domain}: no _eval.json at {domain_dir}")
                continue
            rc = sh(
                [
                    sys.executable, "llm_jury_autogen.py",
                    "--domain", domain,
                    "--backbone", model,
                    "--trajectories-dir", str(traj_dir),
                    "--tasks-dir", str(REPO_ROOT / "tasks" / sub_folder),
                ],
                cwd=JURY_SCRIPTS,
            )
            if rc != 0:
                print(f"[warn] jury exited {rc} for {model} × {domain}; continuing")


def step_aggregate(models: list[str]) -> None:
    print("\n" + "=" * 72)
    print("STEP 5 — Aggregate jury results")
    print("=" * 72)
    if not JURY_SCRIPTS.exists():
        return
    for model in models:
        sh(
            [sys.executable, "aggregate_to_tables.py", "--backbone", model],
            cwd=JURY_SCRIPTS,
        )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", required=True)
    p.add_argument("--domains", nargs="+", required=True)
    p.add_argument("--sub-folder", default="less_sensitive")
    p.add_argument("--start-persona", type=int, default=1)
    p.add_argument("--end-persona", type=int, default=30)
    p.add_argument("--skip-agent-run", action="store_true",
                   help="Skip step 1 (use existing logs).")
    p.add_argument("--skip-jury", action="store_true",
                   help="Skip steps 4-5 (only task success rate).")
    args = p.parse_args()

    if not args.skip_agent_run:
        step_run_agents(args.models, args.domains, args.sub_folder,
                        args.start_persona, args.end_persona)

    step_parse(args.models, args.sub_folder)
    step_success_rate(args.models, args.domains, args.sub_folder,
                      args.end_persona - args.start_persona + 1)

    if not args.skip_jury:
        step_jury(args.models, args.domains, args.sub_folder)
        step_aggregate(args.models)

    print("\n" + "=" * 72)
    print("Done.")
    print("=" * 72)
    print("Task success rate:    Table8/results_utility_eval_autogen/model_success_rates_autogen.csv")
    if not args.skip_jury:
        print("Per-backbone tables:  llm_jury_eval/tables_filled_<model>.{md,tex}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
