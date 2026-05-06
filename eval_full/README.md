# `eval_full/` — Run any backbone × any framework

Two CLI runners for driving persona-based shopping tasks through both web-agent frameworks. No editing scripts, no opinions about which cells of which table to fill — just `--model X --task Y` and go.

This folder is a runner toolkit only. Downstream parsing / oversharing-judging / success-rate aggregation lives in the existing `Browser-Use/` and `AutoGen/` folders at the repo root; the runners write log files in formats those existing scripts already understand.

## What's here

| Script | Framework | Backbones it accepts |
|---|---|---|
| `browser_use_run.py` | `browser-use` library | `gpt-4o`, `o3`, `o4-mini`, `claude-sonnet-4-0`, `gemini-2.5-flash`, `deepseek-chat`, `deepseek-reasoner` |
| `autogen_run.py` | `autogen-ext` `MultimodalWebSurfer` | `gpt-4o`, `o3`, `o4-mini`, `claude-sonnet-4-0`, `gemini-2.5-flash`, `deepseek-chat` |

Why no `deepseek-reasoner` (DeepSeek-R1) for AutoGen: `MultimodalWebSurfer` feeds the model browser screenshots, but R1 is text-only. The runner refuses with an explanatory error if you try.

## Setup

Python 3.11+ (tested on 3.12) in a fresh venv.

```bash
cd eval_full
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

The pinned versions in `requirements.txt` have been smoke-tested end-to-end
on a fresh install against:
- Browser-Use × Claude-Sonnet-4 (full Amazon trajectory)
- Browser-Use × Gemini-2.5-Flash (12+ steps, real Amazon navigation)
- AutoGen × Claude-Sonnet-4 (3 turns, search + sort)
- AutoGen × Gemini-2.5-Flash (3 turns, full plan + price-sorted summary)

`.env` at the repo root with whichever keys you need:

```
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
DEEPSEEK_API_KEY=...
```

## Usage

Both runners share the same flag shape:

```
--model         backbone slug (required)
--task          task file basename without .json, required
                e.g. shopping_Amazon_chat_modified
--sub-folder    tasks/<sub_folder>/ (default: less_sensitive)
--tasks-dir     path to the repo's tasks/ dir (default: ../tasks)
--start-persona first persona id to run (default: 1)
--end-persona   last persona id to run (default: 30)
```

Examples:

```bash
cd eval_full

# Browser-Use × Gemini × Amazon-chat (single persona smoke test)
python browser_use_run.py --model gemini-2.5-flash \
                          --task shopping_Amazon_chat_modified \
                          --start-persona 1 --end-persona 1

# AutoGen × Sonnet × ebay-email (full 30 personas)
python autogen_run.py --model claude-sonnet-4-0 \
                      --task shopping_ebay_email_modified

# Browser-Use × DeepSeek-R1 × Amazon-generic (R1 only works in Browser-Use)
python browser_use_run.py --model deepseek-reasoner \
                          --task shopping_Amazon_generic_modified
```

Already-logged personas are skipped, so re-running after a transient failure only retries the missing ones.

## Output paths

```
eval_full/results_output/<sub_folder>/<model>/<task>/persona_*.log         # browser_use_run.py
eval_full/results_output_autogen/<sub_folder>/<model>/<task>/persona_*.log # autogen_run.py
```

Two separate trees because the log formats differ — Browser-Use logs use STEP / 🦾 ACTION markers, AutoGen logs use TextMessage / MultiModalMessage sections. Don't mix them.

## Sweeping the full matrix

The full `models × frameworks × domains × personas` cross-product is large. Use bash loops to fan out:

```bash
cd eval_full

DOMAINS=(
  shopping_Amazon_chat_modified
  shopping_Amazon_email_modified
  shopping_Amazon_generic_modified
  shopping_ebay_chat_modified
  shopping_ebay_email_modified
  shopping_ebay_generic_modified
)

# Browser-Use full sweep (all 6 backbones × 6 domains × 30 personas = 1080 runs)
for m in gpt-4o o3 o4-mini gemini-2.5-flash claude-sonnet-4-0 deepseek-reasoner; do
  for d in "${DOMAINS[@]}"; do
    python browser_use_run.py --model "$m" --task "$d"
  done
done

# AutoGen sweep (5 backbones × 6 domains × 30 personas = 900 runs; skips R1)
for m in gpt-4o o3 o4-mini gemini-2.5-flash claude-sonnet-4-0; do
  for d in "${DOMAINS[@]}"; do
    python autogen_run.py --model "$m" --task "$d"
  done
done
```

Realistic wall-clock with the three Browser-Use models running in parallel terminals: ~6–10 hours per framework. AutoGen is similar. Total spend ≈ $200–400 if you do everything, mostly Sonnet.

## Downstream processing

Once the logs are written, reuse the existing pipelines:

**Browser-Use logs** (`eval_full/results_output/...`):
1. Copy or symlink into `Browser-Use/results_output/<sub_folder>/<model>/...` (or run the parsers from inside `eval_full/`).
2. `python Browser-Use/1_log_parser.py` (edit the model list at the bottom of the file).
3. `Browser-Use/2_log_parser_to_json_format.ipynb` to produce `_parsed_json_format/`.
4. For task success rate, use the aggregator at `Table8/compute_success_rate.py` against the `_parsed_json_format/` tree.
5. For oversharing, use `Browser-Use/3_LLM_judge_batch.py` (LLM-judged).

**AutoGen logs** (`eval_full/results_output_autogen/...`):
1. Copy or symlink into `AutoGen/results_output/<sub_folder>/<model>/...`.
2. `python AutoGen/1_TextMessage_parse.py` -> `results_output_TextMessage/`.
3. For task success rate, edit + run `AutoGen/2_utility_judge.py` (LLM judge that reads the TextMessage output).
4. For oversharing, `AutoGen/2_LLM_judge.py`.

## Caveats

- **AutoGen × non-OpenAI backbones is less well-trodden than the OpenAI path.** The Gemini and DeepSeek branches use AutoGen's `OpenAIChatCompletionClient` against the providers' OpenAI-compatible REST endpoints. If the framework version on your machine doesn't accept the `model_info=...` kwarg shape, upgrade `autogen-ext` to a recent release.
- **AutoGen × DeepSeek-R1**: refused at startup. Use Browser-Use for R1.
- **Sequencing**: a single `*_run.py` invocation runs personas one at a time. Spread the matrix across multiple terminals (or background processes) for concurrency. Output paths are namespaced by `(framework, model, task)` so parallel invocations on disjoint cells will not collide.
