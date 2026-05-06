#!/usr/bin/env python3
"""
Browser-Use agent runner for Table 8 task-success-rate reproduction.

Drives a browser-use Agent on every persona of a task file, capturing the
full agent log (stdout+stderr) to disk so the downstream parser can
extract step-by-step behavior and the agent's self-reported
completion_status.

Output: <Table8>/results_output/<sub_folder>/<model>/<domain>/persona_*.log

Usage:
    cd Table8
    python run_agent.py --model gemini-2.5-flash \
                        --domain shopping_Amazon_email_modified
    python run_agent.py --model claude-sonnet-4-0 \
                        --domain shopping_ebay_chat_modified
    python run_agent.py --model deepseek-reasoner \
                        --domain shopping_Amazon_generic_modified

Run once per (model, domain) cell of Table 8 you want to fill. Already-logged
personas are skipped, so re-running is idempotent.

Models supported (with the env var the LLM client expects):
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

        # Import the LLM class lazily so optional deps for one backbone
        # (e.g. google-genai for ChatGoogle) don't block runs of others.
        llm = None
        if "{model}" in ["gpt-4o", "o3", "o4-mini"]:
            from browser_use.llm import ChatOpenAI
            llm = ChatOpenAI(model="{model}", temperature=1.0)
        elif "{model}" in ["claude-sonnet-4-0", "claude-sonnet-3-7"]:
            from browser_use.llm import ChatAnthropic
            llm = ChatAnthropic(model="{model}", temperature=1.0)
        elif "{model}" in ["gemini-2.5-flash"]:
            from browser_use.llm import ChatGoogle
            llm = ChatGoogle(model="{model}", temperature=1.0)
        elif "{model}" in ["deepseek-chat", "deepseek-reasoner"]:
            from browser_use.llm import ChatDeepSeek
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
    """Run a single persona and tee all output into log_file."""
    script_file = create_agent_script(task, test_id, domain, model)
    try:
        print(f"📋 Logging to: {log_file}")
        print(f"📊 Tail in real-time: tail -f {log_file}")
        print("-" * 80)

        # set -o pipefail so the agent script's exit code propagates
        # past tee (which always exits 0).
        cmd = ["bash", "-c", f"set -o pipefail; python {script_file} 2>&1 | tee {log_file}"]
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
    parser.add_argument("--model", required=True, choices=SUPPORTED_MODELS, help="Backbone LLM slug.")
    parser.add_argument(
        "--domain",
        required=True,
        help="Task file basename without .json (e.g. shopping_Amazon_chat_modified).",
    )
    parser.add_argument(
        "--sub-folder",
        default="less_sensitive",
        help="tasks/<sub_folder>/ to load from. Defaults to less_sensitive.",
    )
    parser.add_argument(
        "--tasks-dir",
        default="../tasks",
        help="Path to the tasks/ directory. Defaults to ../tasks (one level up).",
    )
    parser.add_argument(
        "--start-persona",
        type=int,
        default=1,
        help="First persona id to run (inclusive). Default 1.",
    )
    parser.add_argument(
        "--end-persona",
        type=int,
        default=30,
        help="Last persona id to run (inclusive). Default 30.",
    )
    args = parser.parse_args()

    task_path = Path(args.tasks_dir) / args.sub_folder / f"{args.domain}.json"
    if not task_path.exists():
        print(f"[fatal] task file not found: {task_path}", file=sys.stderr)
        return 1

    output_root = Path("results_output") / args.sub_folder / args.model / args.domain
    output_root.mkdir(parents=True, exist_ok=True)

    with open(task_path, "r", encoding="utf-8") as f:
        task_data = json.load(f)

    print(f"\n🤖 Model: {args.model}")
    print(f"📁 Task file: {task_path}")
    print(f"💾 Output: {output_root}")

    for persona in task_data.get("personas", []):
        pid = persona["id"]
        if pid < args.start_persona or pid > args.end_persona:
            continue

        pname = persona["name"]
        task = persona["prompt"]
        domain_url = persona.get("website", args.domain)
        test_id = f"persona_{pid}_{pname.replace(' ', '_')}"
        log_file = output_root / f"{test_id}.log"

        print(f"\n📝 Persona {pid}: {pname}")
        if log_file.exists():
            print("   ⏭️  log exists, skipping")
            continue

        run_with_complete_logging(task, test_id, domain_url, log_file, args.model)
        print(f"   🎉 done -> {log_file}")
        print("-" * 80)

    print(f"\n✅ Finished {args.model} × {args.domain}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
