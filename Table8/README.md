# Table 8 — Task Success Rate Reproduction

Self-contained pipeline for filling in the **Browser-Use rows of Table 8** in the SPILLage paper for three backbones that the original sweep didn't cover end-to-end. Everything you need (runner, log parsers, success-rate aggregator) lives in this folder; you do not need any pre-existing trajectories from the paper.

## What you need to run

You're running **all six shopping domains** for each of three backbones, 30 personas each:

| Backbone | Slug used here | API key |
|---|---|---|
| Gemini 2.5-Flash | `gemini-2.5-flash` | `GOOGLE_API_KEY` |
| Claude Sonnet 4 | `claude-sonnet-4-0` | `ANTHROPIC_API_KEY` |
| DeepSeek-R1 | `deepseek-reasoner` | `DEEPSEEK_API_KEY` |

```
shopping_Amazon_chat_modified
shopping_Amazon_email_modified
shopping_Amazon_generic_modified
shopping_ebay_chat_modified
shopping_ebay_email_modified
shopping_ebay_generic_modified
```

Total: **3 backbones × 6 domains × 30 personas = 540 agent runs.** No pre-parsed data is shipped — the pipeline produces everything from the task JSON files in `tasks/less_sensitive/`.

## Setup

```bash
# from the repo root
pip install "browser-use[all]" python-dotenv
playwright install chromium
```

Create a `.env` at the **repo root** (one level up from this folder) containing whichever keys you need:

```
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
DEEPSEEK_API_KEY=...
```

Smoke test (one persona, default backbone):

```bash
cd Table8
python run_agent.py --model gemini-2.5-flash \
                    --domain shopping_Amazon_chat_modified \
                    --start-persona 1 --end-persona 1
```

You should get one log file at `Table8/results_output/less_sensitive/gemini-2.5-flash/shopping_Amazon_chat_modified/persona_1_*.log`. If that works, the full run will too.

## Pipeline

### 1. Run agents — `run_agent.py`

Once per (model, domain) combination — 18 invocations total:

```bash
cd Table8

DOMAINS=(
  shopping_Amazon_chat_modified
  shopping_Amazon_email_modified
  shopping_Amazon_generic_modified
  shopping_ebay_chat_modified
  shopping_ebay_email_modified
  shopping_ebay_generic_modified
)

for m in gemini-2.5-flash claude-sonnet-4-0 deepseek-reasoner; do
  for d in "${DOMAINS[@]}"; do
    python run_agent.py --model "$m" --domain "$d"
  done
done
```

Each invocation iterates 30 personas sequentially, writing one `.log` per persona to `Table8/results_output/less_sensitive/<model>/<domain>/`. Already-logged personas are skipped, so re-running the same command after a transient API failure only retries the missing personas.

If you have multiple terminals, **run the three models in parallel** (one model per terminal) — they don't conflict because output paths are namespaced by model. Domains within a single model run sequentially, since they all write Chromium output through the same browser-use stack.

`run_agent.py` flags:
- `--model` (required): one of `gpt-4o`, `o3`, `o4-mini`, `claude-sonnet-4-0`, `gemini-2.5-flash`, `deepseek-chat`, `deepseek-reasoner`.
- `--domain` (required): task file basename without `.json`.
- `--sub-folder`: defaults to `less_sensitive`.
- `--tasks-dir`: defaults to `../tasks` (the `tasks/` folder at the repo root).
- `--start-persona`, `--end-persona`: persona id range (defaults to `1..30`).

### 2. Parse raw logs — `parse_logs.py`

Converts `.log` → structured `*_parsed.log`:

```bash
python parse_logs.py --models gemini-2.5-flash claude-sonnet-4-0 deepseek-reasoner
```

Output: `Table8/results_output/less_sensitive/<model>_parsed/<domain>/*_parsed.log`.

### 3. Convert to per-task JSON — `parse_to_json.py`

```bash
python parse_to_json.py --models gemini-2.5-flash claude-sonnet-4-0 deepseek-reasoner
```

Output: `Table8/results_output/less_sensitive/<model>_parsed_json_format/<domain>/persona_*.json`. Each JSON has a `header.completion_status` field — that's what the success metric reads.

### 4. Compute success rate — `compute_success_rate.py`

```bash
python compute_success_rate.py --models gemini-2.5-flash claude-sonnet-4-0 deepseek-reasoner
```

The script:
1. Walks `<model>_parsed_json_format/<domain>/*.json`.
2. Marks a task as success when `header.completion_status` contains `✅` or `successfully` (case-insensitive).
3. Prints a per-(model, domain) breakdown to stdout.
4. Writes `Table8/results_output/less_sensitive/model_success_rates.csv`.

Note on denominators: `parse_logs.py` drops `.log` files that don't contain any parseable STEP markers (typically runs that crashed before the agent took its first action). Those are excluded from both numerator and denominator — the published Table 8 numbers were computed the same way (e.g. gpt-4o Amazon-chat is `21/27`, not `21/30`). If you want to penalize crashes, copy `parse_logs.py`'s skip logic and have it emit a stub success-status of `❌` instead of dropping.

The shopping rows of that CSV are exactly the cells of Table 8. Extract them:

```bash
grep -E "^(shopping_Amazon|shopping_ebay)" \
  results_output/less_sensitive/model_success_rates.csv
```

The CSV reports percentages (e.g. `83.33`); the paper uses proportions (`0.833`), so divide by 100 before pasting into `oversharing-neurips/tables/browser-use-utility.tex`.

## Cost / time estimate

Rough orders of magnitude per (model × domain × 30 personas) on a single machine:

| Backbone | Wall clock | API cost |
|---|---|---|
| Gemini 2.5-Flash | ~30–45 min | low (~$1–3) |
| Claude Sonnet 4 | ~45–90 min | mid ($10–20) |
| DeepSeek-R1 | ~60–120 min | low (~$1–5) but more 502s |

Total for the full 18-cell sweep (3 models × 6 domains × 30 personas = 540 runs): roughly a day of wall-clock if you run sequentially, or **~5–10 hours if you run the three models in parallel terminals**. Total API spend ≈ $60–140, mostly Sonnet.

Personas within a single (model, domain) are not parallelized in `run_agent.py` — one Chromium at a time keeps the failure modes simple. The three model runs are independent though; running them concurrently is the recommended way to reduce wall-clock.

## Troubleshooting

- **`ChatDeepSeek` import fails** — upgrade browser-use: `pip install -U "browser-use[all]"`. The DeepSeek client landed mid-2025.
- **Rate limits / 429** — re-run the same `python run_agent.py --model … --domain …`; only the missing personas will be retried.
- **DeepSeek 502s** — same fix; R1's API is occasionally flaky.
- **A persona has no `completion_status`** — that run probably crashed mid-flight. Delete the corresponding `.log` and re-run.
- **`tasks/` not found** — pass `--tasks-dir /absolute/path/to/tasks` if you're not running from inside `Table8/`.

## Why AutoGen rows aren't here

`MultimodalWebSurfer` (the AutoGen agent class) requires a vision-capable model for screenshot reasoning. **DeepSeek-R1 is text-only** so it cannot complete tasks via AutoGen end-to-end. For the camera-ready, the practical options are:

- Cite Browser-Use numbers as the per-backbone evidence (this folder), and
- Either leave the AutoGen × {Gemini, Sonnet, R1} cells blank with a footnote, or run only AutoGen × {Gemini, Sonnet} via the existing `AutoGen/0_autogen_run_batch.py` and report N/A for AutoGen × R1.
