#!/usr/bin/env bash
# Fill in the AutoGen rows of the Implicit Oversharing table (paper Table 11
# / appendix C.3) for one or more agent backbones.
#
# Usage:
#   bash scripts/run_autogen_implicit.sh                  # both o3 and o4-mini
#   bash scripts/run_autogen_implicit.sh o3               # just o3
#   bash scripts/run_autogen_implicit.sh o3 o4-mini gpt-4o   # any list
#
# Knobs (env vars):
#   MAX_PARALLEL=2     gentler on Anthropic rate limits (default 3)
#   EMIT_BOTH=1        also re-emit Table 2 explicit (only useful with USE_FULL_JURY=1)
#   USE_FULL_JURY=1    use 4-category llm_jury_autogen.py instead (Table-2-comparable)
#
# What it does, per backbone:
#   1. For each of the 6 shopping configs, runs the implicit-only evaluator
#      (or the 4-category jury if USE_FULL_JURY=1) on the AutoGen
#      trajectories. Skips configs whose output already exists.
#      If a 4-category jury_results_fixed.json from a previous run is
#      already present, it is automatically backed up to
#      jury_results_fixed_4cat.json AND its judge_weights are passed to
#      the implicit evaluator via --weights-from, so the implicit numbers
#      use the same reliability weights as the explicit run.
#   2. Aggregates AutoGen + Browser-Use into tables_filled_<backbone>.tex.
#   3. Renders the implicit table only into tables_filled_<backbone>_implicit.tex
#      (the rows you paste into Table 11). Set EMIT_BOTH=1 to also render the
#      explicit table.
#
# Logs land in logs/autogen_<backbone>_<domain>.log so a failed run is easy
# to retry. Re-running this script is safe — completed configs are skipped.
#
# Prereq: llm_jury_eval/.env populated (see README §Setup) and AutoGen
# trajectories under trajectories/autogen_<backbone>_processed/.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
cd "$ROOT" || exit 1

# Backbones come from positional args, falling back to the BACKBONES env
# var, falling back to "o3 o4-mini" — so all of these work:
#   bash scripts/run_autogen_implicit.sh o3
#   BACKBONES="o3" bash scripts/run_autogen_implicit.sh
#   bash scripts/run_autogen_implicit.sh
if [[ $# -gt 0 ]]; then
  BACKBONES="$*"
else
  BACKBONES="${BACKBONES:-o3 o4-mini}"
fi

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

if [[ "${USE_FULL_JURY:-0}" == "1" ]]; then
  EVAL_SCRIPT="scripts/llm_jury_autogen.py"
  EVAL_LABEL="4-category jury (CE/CI/BE/BI)"
else
  EVAL_SCRIPT="scripts/implicit_eval_autogen.py"
  EVAL_LABEL="implicit-only (CI/BI), with auto-borrow of weights from existing 4-cat run"
fi
echo "Backbones: $BACKBONES"
echo "Evaluator: $EVAL_SCRIPT  ($EVAL_LABEL)"
echo

# Helper: classify an existing jury_results_fixed.json. Echoes one of
#   missing       — file does not exist
#   implicit_only — already an implicit-only run (skip it)
#   4cat          — a previous 4-category run we should preserve + reuse weights from
#   unknown       — file exists but its method tag isn't recognized
classify_existing() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "missing"
    return
  fi
  python3 - "$path" <<'PY'
import json, sys
try:
    m = json.load(open(sys.argv[1])).get("method", "")
except Exception:
    print("unknown")
    sys.exit(0)
if m.startswith("implicit_only"):
    print("implicit_only")
elif m.startswith("category_specific"):
    print("4cat")
else:
    print("unknown")
PY
}

run_one() {
  local backbone="$1"
  local domain="$2"
  local extra_args="$3"   # e.g. "--weights-from <path>"
  local log="logs/autogen_${backbone}_${domain}.log"
  echo "[$(date +%H:%M:%S)] start: autogen $domain ($backbone) $extra_args"
  # shellcheck disable=SC2086
  python3 "$EVAL_SCRIPT" --domain "$domain" --backbone "$backbone" $extra_args >"$log" 2>&1
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
  PENDING=()                # "<domain>|<extra_args>"
  for d in "${DOMAINS[@]}"; do
    out_dir="results_autogen_${backbone}/${d}"
    out="${out_dir}/jury_results_fixed.json"
    state="$(classify_existing "$out")"
    case "$state" in
      missing)
        PENDING+=("$d|")
        ;;
      implicit_only)
        echo "skip (implicit-only run already exists): autogen $d ($backbone)"
        ;;
      4cat)
        # Preserve the 4-category result + borrow its judge_weights for the
        # implicit eval (only matters for the implicit-only evaluator —
        # llm_jury_autogen.py would just ignore --weights-from).
        backup="${out_dir}/jury_results_fixed_4cat.json"
        if [[ ! -f "$backup" ]]; then
          cp "$out" "$backup"
          echo "preserved existing 4-cat result: $backup"
        fi
        if [[ "$EVAL_SCRIPT" == "scripts/implicit_eval_autogen.py" ]]; then
          PENDING+=("$d|--weights-from $backup")
        else
          # Already a 4-cat result; nothing to do for USE_FULL_JURY=1.
          echo "skip (4-category run already exists, USE_FULL_JURY=1): autogen $d ($backbone)"
        fi
        ;;
      unknown)
        echo "warn: $out exists but has unrecognized method tag — leaving alone (delete it to re-run)"
        ;;
    esac
  done
  echo "Pending for $backbone: ${#PENDING[@]} configs (max $MAX_PARALLEL in parallel)"
  echo

  # Bounded parallelism that works on macOS's bash 3.2 (no `wait -n`).
  # Spawn up to MAX_PARALLEL background jobs, then `wait` for all of them
  # before spawning the next batch. Slightly less efficient than per-job
  # waits but portable.
  running=0
  for entry in "${PENDING[@]}"; do
    domain="${entry%%|*}"
    extra="${entry#*|}"
    run_one "$backbone" "$domain" "$extra" &
    running=$((running + 1))
    if (( running >= MAX_PARALLEL )); then
      wait
      running=0
    fi
  done
  wait

  echo
  echo "Aggregating $backbone into tables_filled_${backbone}.tex..."
  python3 scripts/aggregate_to_tables.py --backbone "$backbone"

  echo "Rendering paper-ready LaTeX..."
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
