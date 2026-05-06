#!/usr/bin/env bash
# Run the LLM-jury on every config that doesn't already have results.
#
# Defaults to running configs in parallel (up to 4 at a time) to keep wall-clock
# reasonable while staying within Anthropic rate limits. Set MAX_PARALLEL to
# change.
#
# Logs go to llm_jury_eval/logs/<framework>_<domain>.log.
#
# Usage:
#   bash scripts/run_all_missing.sh
#   MAX_PARALLEL=2 bash scripts/run_all_missing.sh   # gentler on rate limits

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT" || exit 1

MAX_PARALLEL="${MAX_PARALLEL:-4}"
mkdir -p logs

# (framework, domain) pairs that still need a jury run.
JOBS=(
  "browseruse shopping_Amazon_email"
  "browseruse shopping_Amazon_generic"
  "browseruse shopping_ebay_email"
  "browseruse shopping_ebay_generic"
  "autogen    shopping_Amazon_chat"
  "autogen    shopping_Amazon_email"
  "autogen    shopping_Amazon_generic"
  "autogen    shopping_ebay_chat"
  "autogen    shopping_ebay_email"
  "autogen    shopping_ebay_generic"
)

run_one() {
  local fw="$1"
  local domain="$2"
  local script="scripts/llm_jury_${fw}.py"
  local log="logs/${fw}_${domain}.log"
  echo "[$(date +%H:%M:%S)] start: $fw $domain"
  python3 "$script" --domain "$domain" >"$log" 2>&1
  local rc=$?
  if [[ $rc -eq 0 ]]; then
    echo "[$(date +%H:%M:%S)] DONE : $fw $domain"
  else
    echo "[$(date +%H:%M:%S)] FAIL : $fw $domain (rc=$rc, see $log)"
  fi
}

# Skip jobs whose result already exists.
PENDING=()
for entry in "${JOBS[@]}"; do
  read -r fw domain <<<"$entry"
  if [[ "$fw" == "browseruse" ]]; then
    out="results/${domain}/jury_results_fixed.json"
  else
    out="results_autogen/${domain}/jury_results_fixed.json"
  fi
  if [[ -f "$out" ]]; then
    echo "skip (already done): $fw $domain"
  else
    PENDING+=("$fw $domain")
  fi
done

echo "Pending: ${#PENDING[@]} configs (max $MAX_PARALLEL in parallel)"
echo

# Run with simple parallelism via background jobs + wait.
running=0
for entry in "${PENDING[@]}"; do
  read -r fw domain <<<"$entry"
  run_one "$fw" "$domain" &
  ((running++))
  if (( running >= MAX_PARALLEL )); then
    wait -n
    ((running--))
  fi
done
wait

echo
echo "All jobs finished. Aggregating..."
python3 scripts/aggregate_to_tables.py
