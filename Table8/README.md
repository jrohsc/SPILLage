# Table 8 — Task Success Rate Reproduction

Self-contained pipeline for filling in the empty Browser-Use cells of **Table 8** in the SPILLage paper. Everything you need (runner, log parsers, success-rate aggregator) lives in this folder.

## What's missing in Table 8

The paper's Browser-Use rows have only the `shopping_Amazon_chat` cell filled for these three backbones:

| Backbone | Slug used here | API key |
|---|---|---|
| Gemini 2.5-Flash | `gemini-2.5-flash` | `GOOGLE_API_KEY` |
| Claude Sonnet 4 | `claude-sonnet-4-0` | `ANTHROPIC_API_KEY` |
| DeepSeek-R1 | `deepseek-reasoner` | `DEEPSEEK_API_KEY` |

We need success rates for the **5 remaining shopping domains**, 30 personas each:

```
shopping_Amazon_email_modified
shopping_Amazon_generic_modified
shopping_ebay_chat_modified
shopping_ebay_email_modified
shopping_ebay_generic_modified
```

Total: **3 backbones × 5 domains × 30 personas = 450 agent runs.**

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

Once per (model, domain) combination:

```bash
cd Table8

# Gemini 2.5-Flash × 5 domains
for d in shopping_Amazon_email_modified shopping_Amazon_generic_modified \
         shopping_ebay_chat_modified shopping_ebay_email_modified \
         shopping_ebay_generic_modified; do
  python run_agent.py --model gemini-2.5-flash --domain "$d"
done

# Claude Sonnet 4 × 5 domains
for d in shopping_Amazon_email_modified shopping_Amazon_generic_modified \
         shopping_ebay_chat_modified shopping_ebay_email_modified \
         shopping_ebay_generic_modified; do
  python run_agent.py --model claude-sonnet-4-0 --domain "$d"
done

# DeepSeek-R1 × 5 domains
for d in shopping_Amazon_email_modified shopping_Amazon_generic_modified \
         shopping_ebay_chat_modified shopping_ebay_email_modified \
         shopping_ebay_generic_modified; do
  python run_agent.py --model deepseek-reasoner --domain "$d"
done
```

Each invocation iterates 30 personas sequentially, writing one `.log` per persona to `Table8/results_output/less_sensitive/<model>/<domain>/`. Already-logged personas are skipped, so re-running the same command after a transient API failure only retries the missing personas.

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

Total for the full 15-cell sweep: roughly half a day of wall-clock if you run them sequentially. Personas are not parallelized in `run_agent.py` (one Chromium at a time keeps the failure modes simple); if you want concurrency, run multiple `run_agent.py` invocations in separate terminals — they target disjoint (model, domain) output directories so they won't collide.

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
