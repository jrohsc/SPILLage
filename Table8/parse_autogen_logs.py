#!/usr/bin/env python3
"""
Parse AutoGen MultimodalWebSurfer logs into the per-task JSON format
that downstream task-success and LLM-jury scripts consume.

Reads:  results_output_autogen/<sub>/<model>/<task>/persona_*.log
Writes: results_output_autogen_TextMessage/<sub>/<model>/<task>/persona_*_eval.json

Each output JSON contains every TextMessage section keyed by step number,
e.g. {"step_1": "...", "step_2": "...", ...}. This is the format
AutoGen/2_utility_judge.py historically expected and matches what the
LLM-jury (llm_jury_autogen.py) uses.

Usage:
    cd Table8
    python parse_autogen_logs.py --models claude-sonnet-4-0 gemini-2.5-flash
"""

import argparse
import glob
import json
import os
import re
import sys
from typing import Any, Dict, List


class WebAgentActionParser:
    def __init__(self):
        # Pattern to identify TextMessage sections
        self.textmessage_pattern = re.compile(
            r'--- TextMessage ---\s*(.*?)(?=(?:--- TextMessage ---|--- MultiModalMessage ---|$))',
            re.DOTALL,
        )

    def parse_log_content(self, content: str) -> List[Dict[str, Any]]:
        sections = self.textmessage_pattern.findall(content)
        actions: List[Dict[str, Any]] = []
        for section in sections:
            text = section.strip()
            if text:
                actions.append({"action": text})
        return actions

    def parse_log_file(self, file_path: str) -> List[Dict[str, Any]]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1") as f:
                content = f.read()
        return self.parse_log_content(content)

    def save_actions(self, actions: List[Dict[str, Any]], output_file_path: str) -> str:
        os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
        steps = {f"step_{i}": a["action"] for i, a in enumerate(actions, start=1)}
        with open(output_file_path, "w", encoding="utf-8") as f:
            json.dump(steps, f, indent=2, ensure_ascii=False)
        return output_file_path


def process_one_model(model: str, sub_folder: str, in_root: str, out_root: str) -> None:
    parser = WebAgentActionParser()
    input_dir = os.path.join(in_root, sub_folder, model)
    output_dir = os.path.join(out_root, sub_folder, model)

    log_files = glob.glob(os.path.join(input_dir, "**", "*.log"), recursive=True)
    print(f"\n[{model}] {len(log_files)} log files under {input_dir}")
    if not log_files:
        return

    os.makedirs(output_dir, exist_ok=True)
    for log_path in log_files:
        try:
            out_path = log_path.replace(".log", "_eval.json").replace(input_dir, output_dir)
            actions = parser.parse_log_file(log_path)
            if actions:
                parser.save_actions(actions, out_path)
                print(f"  ✅ {os.path.relpath(log_path, input_dir)} -> {len(actions)} actions")
            else:
                print(f"  [warn] no TextMessage sections in {log_path}")
        except Exception as e:
            print(f"  ❌ {log_path}: {e}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", required=True, help="Backbone slugs to parse.")
    p.add_argument("--sub-folder", default="less_sensitive")
    p.add_argument("--in-root", default="results_output_autogen", help="Where the .log files live.")
    p.add_argument(
        "--out-root",
        default="results_output_autogen_TextMessage",
        help="Where to write *_eval.json.",
    )
    args = p.parse_args()
    for model in args.models:
        process_one_model(model, args.sub_folder, args.in_root, args.out_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
