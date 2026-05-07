#!/usr/bin/env bash
# Fill in the AutoGen rows of the Implicit Oversharing table (paper Table 11
# / appendix C.3) for one or more agent backbones.
#
# What it does, per backbone:
#   1. Runs llm_jury_autogen.py on the 6 shopping configs whose
#      results_autogen_<backbone>/<domain>/jury_results_fixed.json is missing.
#   2. Aggregates AutoGen + Browser-Use into tables_filled_<backbone>.tex.
#   3. Renders the paper-ready Table 2 + Table 3 LaTeX into
#      tables_filled_<backbone>_paper.tex (AutoGen implicit columns populated).
#
# Logs land in logs/autogen_<backbone>_<domain>.log so a failed run is
# easy to retry. Re-running this script is safe — completed configs are
# skipped on the second pass.
#
# Usage:
#   bash scripts/run_autogen_implicit.sh                  # both o3 and o4-mini
#   BACKBONES="o3"  bash scripts/run_autogen_implicit.sh  # just o3
#   MAX_PARALLEL=2  bash scripts/run_autogen_implicit.sh  # gentler on Anthropic rate limits
#   EMIT_BOTH=1     bash scripts/run_autogen_implicit.sh  # also re-emit Table 2 explicit
#
# Important methodology note:
#   The 3-judge jury scores all four oversharing categories (CE/CI/BE/BI) in
#   a SINGLE LLM call per (step, judge), and the implicit aggregation needs
#   the explicit votes to derive each judge's reliability weight. So even
#   though only the implicit AutoGen rows are missing from the paper, the
#   only way to fill them is to re-run the same jury — there is no cheaper
#   "implicit-only" code path. By default this script emits only the
#   Implicit table LaTeX (the rows you actually need to paste into Table 11).
#
# Prereq: scripts/.. (i.e. llm_jury_eval/) has a populated .env (see README §Setup)
# and the AutoGen trajectories under trajectories/autogen_<backbone>_processed/.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT" || exit 1

BACKBONES="${BACKBONES:-o3 o4-mini}"
MAX_PARALLEL="${MAX_PARALLEL:-3}"
mkdir -p logs

DOMAINS=(
  shopping_Amazon_chat
  shopping_Amazon_email
  shopping_Amazon_generic
  shopping_ebay_chat
  shopping_ebay_email
  shopping_ebay_generic
)

run_one() {
  local backbone="$1"
  local domain="$2"
  local log="logs/autogen_${backbone}_${domain}.log"
  echo "[$(date +%H:%M:%S)] start: autogen $domain ($backbone)"
  python3 scripts/llm_jury_autogen.py --domain "$domain" --backbone "$backbone" >"$log" 2>&1
  local rc=$?
  if [[ $rc -eq 0 ]]; then
    echo "[$(date +%H:%M:%S)] DONE : autogen $domain ($backbone)"
  else
    echo "[$(date +%H:%M:%S)] FAIL : autogen $domain ($backbone) (rc=$rc, see $log)"
  fi
}

for backbone in $BACKBONES; do
  echo "=========================================="
  echo "Backbone: $backbone"
  echo "=========================================="
  PENDING=()
  for d in "${DOMAINS[@]}"; do
    out="results_autogen_${backbone}/${d}/jury_results_fixed.json"
    if [[ -f "$out" ]]; then
      echo "skip (already done): autogen $d ($backbone)"
    else
      PENDING+=("$d")
    fi
  done
  echo "Pending for $backbone: ${#PENDING[@]} configs (max $MAX_PARALLEL in parallel)"
  echo

  running=0
  for d in "${PENDING[@]}"; do
    run_one "$backbone" "$d" &
    ((running++))
    if (( running >= MAX_PARALLEL )); then
      wait -n
      ((running--))
    fi
  done
  wait

  echo
  echo "Aggregating $backbone into tables_filled_${backbone}.tex..."
  python3 scripts/aggregate_to_tables.py --backbone "$backbone"

  echo "Rendering paper-ready LaTeX..."
  # Default: emit only the Implicit Oversharing table — that is the missing
  # AutoGen rows for paper Table 11. Set EMIT_BOTH=1 to also produce the
  # explicit table (Table 2 / Table 9), which the paper already contains for
  # AutoGen and which will simply be regenerated from these jury runs.
  if [[ "${EMIT_BOTH:-0}" == "1" ]]; then
    python3 scripts/generate_jury_tables.py "tables_filled_${backbone}.tex" \
        --backbone "$backbone" \
        --output "tables_filled_${backbone}_paper.tex"
    echo "  -> tables_filled_${backbone}_paper.tex (explicit + implicit)"
  else
    python3 scripts/generate_jury_tables.py "tables_filled_${backbone}.tex" \
        --backbone "$backbone" \
        --only implicit \
        --output "tables_filled_${backbone}_implicit.tex"
    echo "  -> tables_filled_${backbone}_implicit.tex (Table 11 AutoGen rows)"
  fi
done

echo
echo "All backbones complete. Paste-ready LaTeX files:"
for backbone in $BACKBONES; do
  if [[ "${EMIT_BOTH:-0}" == "1" ]]; then
    echo "  - tables_filled_${backbone}_paper.tex"
  else
    echo "  - tables_filled_${backbone}_implicit.tex"
  fi
done
