#!/usr/bin/env python3
"""
Browser-Use agent runner — any backbone × any task file.

Drives a browser-use Agent over every persona of a task JSON, capturing
the full agent log (stdout+stderr) to disk. The downstream parsing
scripts in `Browser-Use/` (1_log_parser.py and
2_log_parser_to_json_format.ipynb) consume these `.log` files.

Output: <eval_full>/results_output/<sub_folder>/<model>/<task>/persona_*.log

Usage:
    cd eval_full
    python browser_use_run.py --model gemini-2.5-flash \\
                              --task shopping_Amazon_chat_modified

    python browser_use_run.py --model deepseek-reasoner \\
                              --task shopping_ebay_email_modified \\
                              --start-persona 1 --end-persona 5

Supported backbones (env var the LLM client expects):
    gpt-4o, o3, o4-mini       -> OPENAI_API_KEY
    claude-sonnet-4-0         -> ANTHROPIC_API_KEY
    gemini-2.5-flash          -> GOOGLE_API_KEY
    deepseek-chat,
    deepseek-reasoner (R1)    -> DEEPSEEK_API_KEY
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SUPPORTED_MODELS = [
    "gpt-4o", "o3", "o4-mini",
    "claude-sonnet-4-0",
    "gemini-2.5-flash",
    "deepseek-chat", "deepseek-reasoner",
]


def create_agent_script(task: str, test_id: str, domain: str, model: str) -> Path:
    """Write a temporary single-persona agent script to disk and return its path."""
    task_escaped = json.dumps(task)
    test_id_escaped = json.dumps(test_id)

    script_content = f'''
import asyncio
import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from browser_use import Agent, BrowserSession, BrowserProfile
from browser_use.llm import ChatOpenAI, ChatAnthropic, ChatGoogle, ChatDeepSeek

async def main():
    task = {task_escaped}
    test_id = {test_id_escaped}

    print("🚀 Starting browser-use agent...")
    print(f"📝 Task: {{task}}")
    print(f"🏷️  Test ID: {{test_id}}")
    print(f"⏰ Start time: {{datetime.now().isoformat()}}")
    print("-" * 80)

    try:
        browser_profile = BrowserProfile(headless=True)
        session = BrowserSession(browser_profile=browser_profile)

        llm = None
        if "{model}" in ["gpt-4o", "o3", "o4-mini"]:
            llm = ChatOpenAI(model="{model}", temperature=1.0)
        elif "{model}" in ["claude-sonnet-4-0", "claude-sonnet-3-7"]:
            llm = ChatAnthropic(model="{model}", temperature=1.0)
        elif "{model}" in ["gemini-2.5-flash"]:
            llm = ChatGoogle(model="{model}", temperature=1.0)
        elif "{model}" in ["deepseek-chat", "deepseek-reasoner"]:
            llm = ChatDeepSeek(
                model="{model}",
                temperature=1.0,
                api_key=os.getenv("DEEPSEEK_API_KEY"),
            )
        else:
            raise ValueError(f"Unsupported model: {model}")

        agent = Agent(
            task=task,
            llm=llm,
            browser_session=session,
            allowed_domains=["{domain}"],
        )

        result = await agent.run()

        print("-" * 80)
        print("✅ Task completed successfully!")
        print(f"📊 Result: {{result}}")
        print(f"⏰ End time: {{datetime.now().isoformat()}}")

    except Exception as e:
        print(f"❌ Error: {{e}}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
'''

    script_file = Path(f"_temp_agent_{test_id}.py")
    script_file.write_text(script_content, encoding="utf-8")
    return script_file


def run_with_complete_logging(task: str, test_id: str, domain: str, log_file: Path, model: str) -> Path:
    script_file = create_agent_script(task, test_id, domain, model)
    try:
        print(f"📋 Logging to: {log_file}")
        cmd = ["bash", "-c", f"python {script_file} 2>&1 | tee {log_file}"]
        process = subprocess.run(
            cmd,
            cwd=os.getcwd(),
            env=dict(os.environ, PYTHONUNBUFFERED="1"),
            text=True,
        )
        print("-" * 80)
        if process.returncode == 0:
            print("✅ Agent run successful")
        else:
            print(f"⚠️  Agent exited with code {process.returncode}")
        print(f"📏 Log size: {log_file.stat().st_size:,} bytes")
        return log_file
    finally:
        if script_file.exists():
            script_file.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, choices=SUPPORTED_MODELS)
    parser.add_argument(
        "--task",
        required=True,
        help="Task file basename without .json (e.g. shopping_Amazon_chat_modified).",
    )
    parser.add_argument("--sub-folder", default="less_sensitive")
    parser.add_argument(
        "--tasks-dir",
        default="../tasks",
        help="Path to the tasks/ directory (default: ../tasks).",
    )
    parser.add_argument("--start-persona", type=int, default=1)
    parser.add_argument("--end-persona", type=int, default=30)
    args = parser.parse_args()

    task_path = Path(args.tasks_dir) / args.sub_folder / f"{args.task}.json"
    if not task_path.exists():
        print(f"[fatal] task file not found: {task_path}", file=sys.stderr)
        return 1

    output_root = Path("results_output") / args.sub_folder / args.model / args.task
    output_root.mkdir(parents=True, exist_ok=True)

    with open(task_path, "r", encoding="utf-8") as f:
        task_data = json.load(f)

    print(f"\n🤖 Model: {args.model}")
    print(f"📁 Task: {task_path}")
    print(f"💾 Output: {output_root}")

    for persona in task_data.get("personas", []):
        pid = persona["id"]
        if pid < args.start_persona or pid > args.end_persona:
            continue

        pname = persona["name"]
        task = persona["prompt"]
        domain_url = persona.get("website", args.task)
        test_id = f"persona_{pid}_{pname.replace(' ', '_')}"
        log_file = output_root / f"{test_id}.log"

        print(f"\n📝 Persona {pid}: {pname}")
        if log_file.exists():
            print("   ⏭️  log exists, skipping")
            continue

        run_with_complete_logging(task, test_id, domain_url, log_file, args.model)
        print(f"   🎉 done -> {log_file}")
        print("-" * 80)

    print(f"\n✅ Finished {args.model} × {args.task}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
