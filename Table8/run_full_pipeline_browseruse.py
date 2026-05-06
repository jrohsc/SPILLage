#!/usr/bin/env python3
"""
End-to-end pipeline: agent runs -> parsed logs -> task success rate ->
LLM-jury -> per-backbone Tables 2/3/8 cells.

Single command that does everything for one or more (model, domain)
combinations against the Browser-Use stack. Idempotent: re-running
skips agent runs whose log already exists, parses skip already-parsed
files, jury skips domains whose jury_results_fixed.json already exists.

Usage:
    cd Table8

    # Smoke test on a single (model, domain) — recommended first run
    python run_full_pipeline.py \\
        --models gemini-2.5-flash \\
        --domains shopping_Amazon_email_modified \\
        --start-persona 1 --end-persona 1

    # Full sweep for the three rebuttal backbones across the 5 missing
    # shopping domains (450 agent runs).
    python run_full_pipeline.py \\
        --models gemini-2.5-flash claude-sonnet-4-0 deepseek-reasoner \\
        --domains shopping_Amazon_email_modified \\
                  shopping_Amazon_generic_modified \\
                  shopping_ebay_chat_modified \\
                  shopping_ebay_email_modified \\
                  shopping_ebay_generic_modified

    # Skip the agent-run step (e.g. you already have logs and just want
    # to re-parse and re-judge):
    python run_full_pipeline.py --models o3 --domains shopping_Amazon_email_modified \\
        --skip-agent-run

What it does, per (model × domain):
  1. run_agent.py            → Table8/results_output/<sub>/<model>/<domain>/persona_*.log
  2. parse_logs.py           → ..._parsed/<domain>/*.log
  3. parse_to_json.py        → ..._parsed_json_format/<domain>/*_parsed.json
  4. compute_success_rate.py → Table8/results_output/<sub>/model_success_rates.csv
  5. llm_jury_browseruse.py  → llm_jury_eval/results_<model>/<domain>/jury_results_fixed.json
                              (reads parsed JSON via --trajectories-dir, no copy)
  6. aggregate_to_tables.py  → llm_jury_eval/tables_filled_<model>.{md,tex}
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
JURY_DIR = REPO_ROOT / "llm_jury_eval"
JURY_SCRIPTS = JURY_DIR / "scripts"


def sh(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> int:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    if cwd:
        print(f"  (cwd: {cwd})")
    return subprocess.run(cmd, cwd=cwd, env=env or os.environ.copy()).returncode


def step_run_agents(models: list[str], domains: list[str], sub_folder: str,
                    start_persona: int, end_persona: int) -> None:
    print("\n" + "=" * 72)
    print("STEP 1 — Agent runs")
    print("=" * 72)
    for model in models:
        for domain in domains:
            rc = sh(
                [
                    sys.executable, "run_agent.py",
                    "--model", model,
                    "--domain", domain,
                    "--sub-folder", sub_folder,
                    "--start-persona", str(start_persona),
                    "--end-persona", str(end_persona),
                ],
                cwd=THIS_DIR,
            )
            if rc != 0:
                print(f"[warn] run_agent.py exited {rc} for {model} × {domain}; continuing")


def step_parse(models: list[str], sub_folder: str) -> None:
    print("\n" + "=" * 72)
    print("STEP 2 — Parse raw logs to structured logs")
    print("=" * 72)
    sh(
        [sys.executable, "parse_logs.py", "--models", *models, "--categories", sub_folder],
        cwd=THIS_DIR,
    )

    print("\n" + "=" * 72)
    print("STEP 3 — Parse structured logs to per-task JSON")
    print("=" * 72)
    sh(
        [sys.executable, "parse_to_json.py", "--models", *models, "--categories", sub_folder],
        cwd=THIS_DIR,
    )


def step_success_rate(models: list[str], sub_folder: str) -> None:
    print("\n" + "=" * 72)
    print("STEP 4 — Task success rate (Table 8)")
    print("=" * 72)
    sh(
        [
            sys.executable, "compute_success_rate.py",
            "--root", f"results_output/{sub_folder}",
            "--models", *models,
        ],
        cwd=THIS_DIR,
    )


def step_jury(models: list[str], domains: list[str], sub_folder: str) -> None:
    print("\n" + "=" * 72)
    print("STEP 5 — LLM-Jury (Browser-Use)")
    print("=" * 72)
    if not JURY_SCRIPTS.exists():
        print(f"[skip] {JURY_SCRIPTS} not found; jury step requires the llm_jury_eval/ folder.")
        return

    env = os.environ.copy()
    if (JURY_DIR / ".env").exists():
        # The jury scripts load .env from JURY_DIR via dotenv at import-time;
        # nothing to do here. Just heads-up.
        pass

    for model in models:
        # Path the jury reads parsed JSONs from. parse_to_json.py emits
        # ..._parsed_json_format/<domain>/persona_*_parsed.json which is the
        # exact shape the jury expects.
        traj_dir = THIS_DIR / "results_output" / sub_folder / f"{model}_parsed_json_format"
        if not traj_dir.exists():
            print(f"[skip] {model}: no parsed_json_format dir at {traj_dir}; run parse_to_json first.")
            continue

        for domain in domains:
            domain_dir = traj_dir / domain
            if not any(domain_dir.glob("*.json")):
                print(f"[skip] {model} × {domain}: no parsed JSONs at {domain_dir}")
                continue
            rc = sh(
                [
                    sys.executable, "llm_jury_browseruse.py",
                    "--domain", domain,
                    "--backbone", model,
                    "--trajectories-dir", str(traj_dir),
                    "--tasks-dir", str(REPO_ROOT / "tasks" / sub_folder),
                ],
                cwd=JURY_SCRIPTS,
                env=env,
            )
            if rc != 0:
                print(f"[warn] jury exited {rc} for {model} × {domain}; continuing")


def step_aggregate(models: list[str]) -> None:
    print("\n" + "=" * 72)
    print("STEP 6 — Aggregate jury results into LaTeX cells")
    print("=" * 72)
    if not JURY_SCRIPTS.exists():
        return
    for model in models:
        sh(
            [sys.executable, "aggregate_to_tables.py", "--backbone", model],
            cwd=JURY_SCRIPTS,
        )


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--models", nargs="+", required=True, help="Backbone slugs.")
    p.add_argument("--domains", nargs="+", required=True, help="Task file basenames without .json.")
    p.add_argument("--sub-folder", default="less_sensitive")
    p.add_argument("--start-persona", type=int, default=1)
    p.add_argument("--end-persona", type=int, default=30)
    p.add_argument("--skip-agent-run", action="store_true",
                   help="Skip step 1 (use existing logs).")
    p.add_argument("--skip-jury", action="store_true",
                   help="Skip steps 5-6 (only Table 8 success rate).")
    args = p.parse_args()

    if not args.skip_agent_run:
        step_run_agents(args.models, args.domains, args.sub_folder,
                        args.start_persona, args.end_persona)

    step_parse(args.models, args.sub_folder)
    step_success_rate(args.models, args.sub_folder)

    if not args.skip_jury:
        step_jury(args.models, args.domains, args.sub_folder)
        step_aggregate(args.models)

    print("\n" + "=" * 72)
    print("Done.")
    print("=" * 72)
    print("Table 8 cells:        Table8/results_output/<sub>/model_success_rates.csv")
    if not args.skip_jury:
        print("Per-backbone tables:  llm_jury_eval/tables_filled_<model>.{md,tex}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
