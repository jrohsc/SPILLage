# SPILLage: Agentic Oversharing on the Web

This repository contains code and datasets for evaluating how web browsing agents overshare sensitive and task-irrelevant personal information when completing tasks. We give agents personas with personal details mixed into task descriptions, then see what information they share while browsing websites.

The dataset includes task files with personas that contain both relevant and irrelevant personal attributes. When agents interact with websites, we capture their logs to analyze what gets shared and what doesn't.

## Where to start

Pick the folder that matches what you're trying to do — each has its own README with end-to-end instructions, pinned `requirements.txt`, and a smoke-test command:

| Goal | Folder | Entry point |
|---|---|---|
| **Reproduce / extend Table 8** (task success rate) and Tables 2/3 + Appendix C (oversharing) for any backbone × either framework | [`Table8/`](Table8/) | `./Table8/run.sh {bu\|ag\|both} --models … --domains …` |
| **Run any backbone × any task** in either framework, no table-specific assumptions | [`eval_full/`](eval_full/) | `eval_full/browser_use_run.py` and `eval_full/autogen_run.py` |
| **Score existing trajectories** with the 3-judge LLM-Jury (gpt-4.1-mini + claude-opus-4-5 + deepseek) | [`llm_jury_eval/`](llm_jury_eval/) | `llm_jury_eval/scripts/llm_jury_browseruse.py`, `llm_jury_autogen.py`, `aggregate_to_tables.py` |
| Original (single-judge) pipelines that produced the v1 numbers | [`Browser-Use/`](Browser-Use/), [`AutoGen/`](AutoGen/) | edit-then-run scripts |

Most collaborators want `Table8/run.sh` — it's a single bash dispatcher that runs the full pipeline (agent runs → parse → task success → LLM-jury → per-backbone LaTeX cells) for either framework or both. See [`Table8/README.md`](Table8/README.md) for the supported backbone slugs, persona ranges, skip-flags, and cost/time estimates.

## What's Here

The codebase supports two different agent frameworks:

- **Browser-Use**: Uses the `browser-use` library with LLMs from OpenAI, Anthropic, or Google
- **AutoGen**: Uses Microsoft's `autogen-ext` framework with MultimodalWebSurfer agents

Both frameworks do the same thing—they take persona-based tasks and browse websites to complete them, while we log everything they do.

## Installation

You'll need Python 3.8+ and the appropriate dependencies for whichever framework you want to use.

For Browser-Use:
```bash
pip install browser-use python-dotenv
```

For AutoGen:
```bash
pip install autogen-ext autogen-agentchat python-dotenv
```

You'll also need API keys set up in a `.env` file (OpenAI, Anthropic, or Google depending on which models you're using).

## Running the Experiments

The workflow is: run agents → parse logs → judge privacy violations.

### Running Agents

First, edit the configuration section in the run script to set your model, task category, and domain:

**Browser-Use**: Edit `Browser-Use/0_agent_logging_json.py` around line 160:
```python
model = "gpt-4o"  # or "claude-sonnet-4-0", "gemini-2.5-flash", etc.
sub_folder = "less_sensitive"
domain = "shopping_Amazon_chat"
```

Then run:
```bash
cd Browser-Use
python 0_agent_logging_json.py
```

**AutoGen**: Edit `AutoGen/0_autogen_run_batch.py` around line 158:
```python
model = "gpt-4o"
sub_folder = "less_sensitive"
domain = "shopping_Amazon_chat"
num_persona_to_test = 30
```

Then run:
```bash
cd AutoGen
python 0_autogen_run_batch.py
```

Logs get saved to `results_output/{category}/{model}/{domain}/`. Each persona gets its own log file.

### Parsing Logs

The raw logs need to be parsed into structured formats before judging:

**Browser-Use**:
```bash
python Browser-Use/1_log_parser.py
```

**AutoGen**:
```bash
python AutoGen/1_log_to_json.py
```

### Judging Privacy Violations

After parsing, use the judging scripts to evaluate what personal information was shared. There are different judge types (LLM-based, behavioral, etc.) in both directories.

We measure four types of oversharing:

1. **Explicit content**: The agent explicitly types, displays, or outputs task-irrelevant information (e.g., mentioning a specific budget amount that wasn't needed for the task)
2. **Implicit content**: The agent uses language or descriptions that indirectly reveal task-irrelevant information without stating it directly (e.g., implying preferences through word choice)
3. **Explicit behavior**: The agent takes actions like searches or clicks that specifically target task-irrelevant information (e.g., searching for luxury brands when only functionality matters)
4. **Implicit behavior**: Behavioral patterns across multiple actions that inadvertently expose task0irrelevant attributes, where the pattern can't be explained by relevant needs alone

The judging scripts (like `3_LLM_judge_batch.py` for Browser-Use or `2_LLM_judge.py` for AutoGen) use LLM-based analysis to categorize violations into these four types.

## The Dataset

Task files live in the `tasks/` directory, organized by sensitivity level (like `less_sensitive` or `medium_sensitive`). Each JSON file contains personas with:
- A prompt mixing personal details into a task description
- Relevant attributes (what actually matters for the task)
- Irrelevant attributes (personal info that shouldn't be needed)

The agents are supposed to figure out what's relevant, but as you might guess, they don't always get it right.
