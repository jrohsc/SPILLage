#!/usr/bin/env bash
# Single-entrypoint dispatcher for the Table 8 / oversharing pipelines.
#
# Usage:
#   ./run.sh <framework> [orchestrator args...]
#
# <framework> is one of:
#   browseruse | bu       Browser-Use library (header.completion_status -> success rate)
#   autogen    | ag       AutoGen MultimodalWebSurfer (LLM-judged success rate)
#   both                  Browser-Use first, then AutoGen, same args for both
#                         (deepseek-reasoner is refused for autogen — vision required)
#
# The remaining args are forwarded as-is to the underlying Python
# orchestrator. Anything those scripts accept also works here:
#   --models <m1> [m2 ...]
#   --domains <d1> [d2 ...]
#   --sub-folder less_sensitive
#   --start-persona N
#   --end-persona M
#   --skip-agent-run     (re-parse + re-score against existing logs)
#   --skip-jury          (only task success rate, no oversharing eval)
#
# Examples:
#   # Smoke test on 1 persona, Browser-Use only.
#   ./run.sh bu --models gemini-2.5-flash \
#               --domains shopping_Amazon_email_modified \
#               --start-persona 1 --end-persona 1
#
#   # Full Browser-Use sweep for the three rebuttal backbones × 5 missing domains.
#   ./run.sh browseruse \
#       --models gemini-2.5-flash claude-sonnet-4-0 deepseek-reasoner \
#       --domains shopping_Amazon_email_modified \
#                 shopping_Amazon_generic_modified \
#                 shopping_ebay_chat_modified \
#                 shopping_ebay_email_modified \
#                 shopping_ebay_generic_modified
#
#   # Full AutoGen sweep across the OpenAI + non-DeepSeek-R1 backbones.
#   ./run.sh autogen \
#       --models gpt-4o o3 o4-mini gemini-2.5-flash claude-sonnet-4-0 \
#       --domains shopping_Amazon_chat_modified shopping_Amazon_email_modified \
#                 shopping_Amazon_generic_modified \
#                 shopping_ebay_chat_modified shopping_ebay_email_modified \
#                 shopping_ebay_generic_modified
#
#   # Run both stacks back-to-back for the same backbones/domains.
#   ./run.sh both --models claude-sonnet-4-0 \
#                 --domains shopping_Amazon_chat_modified
#
# Outputs:
#   Browser-Use task success: Table8/results_output/<sub>/model_success_rates.csv
#   AutoGen task success:     Table8/results_utility_eval_autogen/model_success_rates_autogen.csv
#   Per-backbone tables:      llm_jury_eval/tables_filled_<model>.{md,tex}
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python}"

usage() {
  sed -n '2,55p' "$0"
}

if [ $# -lt 1 ]; then
  usage
  exit 1
fi

framework="$1"
shift

case "$framework" in
  -h|--help|help)
    usage
    exit 0
    ;;
  browseruse|bu)
    exec "$PYTHON" "$SCRIPT_DIR/run_full_pipeline_browseruse.py" "$@"
    ;;
  autogen|ag)
    exec "$PYTHON" "$SCRIPT_DIR/run_full_pipeline_autogen.py" "$@"
    ;;
  both)
    echo "==> [run.sh] Browser-Use stack first"
    "$PYTHON" "$SCRIPT_DIR/run_full_pipeline_browseruse.py" "$@"
    echo
    echo "==> [run.sh] AutoGen stack second"
    "$PYTHON" "$SCRIPT_DIR/run_full_pipeline_autogen.py" "$@"
    ;;
  *)
    echo "Unknown framework: $framework" >&2
    echo "Use one of: browseruse | bu | autogen | ag | both | help" >&2
    exit 1
    ;;
esac
