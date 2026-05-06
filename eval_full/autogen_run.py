#!/usr/bin/env python3
"""
AutoGen MultimodalWebSurfer agent runner — any backbone × any task file.

Drives a MagenticOneGroupChat over a single MultimodalWebSurfer agent
for every persona in a task JSON. Logs are streamed to disk in the same
TextMessage / MultiModalMessage format that `AutoGen/1_TextMessage_parse.py`
and `AutoGen/2_utility_judge.py` consume.

Output: <eval_full>/results_output_autogen/<sub_folder>/<model>/<task>/persona_*.log

Usage:
    cd eval_full
    python autogen_run.py --model gpt-4o \\
                          --task shopping_Amazon_chat_modified

    python autogen_run.py --model claude-sonnet-4-0 \\
                          --task shopping_ebay_email_modified \\
                          --start-persona 1 --end-persona 5

Supported backbones (env var the LLM client expects):
    gpt-4o, o3, o4-mini       -> OPENAI_API_KEY
    claude-sonnet-4-0         -> ANTHROPIC_API_KEY
    gemini-2.5-flash          -> GOOGLE_API_KEY (OpenAI-compatible endpoint)
    deepseek-chat             -> DEEPSEEK_API_KEY (V3, vision via DeepSeek API)

NOT supported:
    deepseek-reasoner / DeepSeek-R1 — text-only model, but
    MultimodalWebSurfer feeds the agent screenshots, so it deadlocks.
    Use browser_use_run.py instead for R1.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


SUPPORTED_MODELS = [
    "gpt-4o", "o3", "o4-mini",
    "claude-sonnet-4-0",
    "gemini-2.5-flash",
    "deepseek-chat",
]

UNSUPPORTED_MODELS = {
    "deepseek-reasoner": (
        "DeepSeek-R1 is text-only; MultimodalWebSurfer requires a vision-capable model. "
        "Run R1 via Browser-Use (eval_full/browser_use_run.py) instead."
    ),
}


def get_model_client(model: str):
    """Return an AutoGen ChatCompletionClient for the given backbone slug."""
    m = model.lower()
    if m.startswith("gpt") or m.startswith("o3") or m.startswith("o4"):
        from autogen_ext.models.openai import OpenAIChatCompletionClient
        return OpenAIChatCompletionClient(model=model)

    if "claude" in m:
        from autogen_ext.models.anthropic import AnthropicChatCompletionClient
        return AnthropicChatCompletionClient(model=model)

    if "gemini" in m:
        # Gemini exposes an OpenAI-compatible REST endpoint.
        from autogen_ext.models.openai import OpenAIChatCompletionClient
        return OpenAIChatCompletionClient(
            model=model,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.getenv("GOOGLE_API_KEY"),
            model_info={
                "vision": True,
                "function_calling": True,
                "json_output": True,
                "family": "gemini",
                "structured_output": True,
            },
        )

    if "deepseek" in m:
        from autogen_ext.models.openai import OpenAIChatCompletionClient
        return OpenAIChatCompletionClient(
            model=model,
            base_url="https://api.deepseek.com/v1",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            model_info={
                "vision": True,
                "function_calling": True,
                "json_output": True,
                "family": "deepseek",
                "structured_output": False,
            },
        )

    raise ValueError(f"Unsupported model: {model}")


async def run_surfer_agent(task: str, test_id: str, domain: str, log_file: Path, model: str) -> None:
    from autogen_ext.agents.web_surfer import MultimodalWebSurfer
    from autogen_agentchat.teams import MagenticOneGroupChat

    model_client = get_model_client(model)

    start_url = domain
    if not start_url.startswith("http"):
        start_url = f"https://{start_url}"

    surfer = MultimodalWebSurfer(
        "MultimodalWebSurfer",
        model_client=model_client,
        headless=True,
        to_resize_viewport=True,
        description=(
            "A web surfing assistant that can browse and interact with web pages. "
            "Make sure to only use the website url provided. DO NOT use other websites."
        ),
        start_page=start_url,
        animate_actions=True,
    )

    team = MagenticOneGroupChat([surfer], model_client=model_client, max_turns=3)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=== MultimodalWebSurfer Search Results ===\n")
        f.write(f"Task: {task}\n")
        f.write(f"Test ID: {test_id}\n")
        f.write(f"Start time: {datetime.now().isoformat()}\n")
        f.write(f"Domain: {domain}\n")
        f.write(f"Model: {model}\n")
        f.write("-" * 80 + "\n\n")

        try:
            async for message in team.run_stream(task=task):
                message_type = type(message).__name__
                try:
                    content = getattr(message, "content", None) or getattr(message, "message", None) or str(message)
                except Exception as e:
                    content = f"[Error extracting content: {e}]"
                sender = getattr(message, "sender", message_type)

                line = f"--- {sender} ---\n{content}\n\n"
                print(line)
                f.write(line)
                f.flush()

            f.write("-" * 80 + "\n")
            f.write(f"Task completed at: {datetime.now().isoformat()}\n")
        except Exception as e:
            import traceback
            print(f"❌ Error: {e}")
            traceback.print_exc()
            f.write(f"\n❌ Error: {e}\n")
            f.write(traceback.format_exc())
        finally:
            await surfer.close()


async def run_all(args) -> int:
    task_path = Path(args.tasks_dir) / args.sub_folder / f"{args.task}.json"
    if not task_path.exists():
        print(f"[fatal] task file not found: {task_path}", file=sys.stderr)
        return 1

    output_root = Path("results_output_autogen") / args.sub_folder / args.model / args.task
    output_root.mkdir(parents=True, exist_ok=True)

    with open(task_path, "r", encoding="utf-8") as f:
        task_data = json.load(f)

    print(f"\n🤖 Framework: AutoGen MultimodalWebSurfer")
    print(f"🤖 Model: {args.model}")
    print(f"📁 Task: {task_path}")
    print(f"💾 Output: {output_root}")

    for persona in task_data.get("personas", []):
        pid = persona["id"]
        if pid < args.start_persona or pid > args.end_persona:
            continue

        pname = persona["name"]
        task = persona["prompt"]

        website = persona.get("website", args.task)
        if website.startswith("http://"):
            website = website[7:]
        elif website.startswith("https://"):
            website = website[8:]

        test_id = f"persona_{pid}_{pname.replace(' ', '_')}"
        log_file = output_root / f"{test_id}.log"

        print(f"\n📝 Persona {pid}: {pname}")
        if log_file.exists():
            print("   ⏭️  log exists, skipping")
            continue

        await run_surfer_agent(task, test_id, website, log_file, args.model)
        print(f"   🎉 done -> {log_file}")
        print("-" * 80)

    print(f"\n✅ Finished {args.model} × {args.task}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--task",
        required=True,
        help="Task file basename without .json (e.g. shopping_Amazon_chat_modified).",
    )
    parser.add_argument("--sub-folder", default="less_sensitive")
    parser.add_argument("--tasks-dir", default="../tasks")
    parser.add_argument("--start-persona", type=int, default=1)
    parser.add_argument("--end-persona", type=int, default=30)
    args = parser.parse_args()

    if args.model in UNSUPPORTED_MODELS:
        print(f"[fatal] {args.model}: {UNSUPPORTED_MODELS[args.model]}", file=sys.stderr)
        return 2

    if args.model not in SUPPORTED_MODELS:
        print(
            f"[fatal] unknown model {args.model}. Supported: {SUPPORTED_MODELS}",
            file=sys.stderr,
        )
        return 2

    return asyncio.run(run_all(args))


if __name__ == "__main__":
    sys.exit(main())
