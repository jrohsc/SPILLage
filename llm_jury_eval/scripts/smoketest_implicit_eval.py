#!/usr/bin/env python3
"""
Offline smoke test for implicit_eval_autogen.py.

Wraps the real evaluator with three FAKE judge functions (no API calls)
and runs it against the AutoGen trajectories + personas already shipped
in this folder. Then reads the resulting jury_results_fixed.json back
and asserts the implicit numbers populated correctly.

Use this to verify keys + plumbing + output format BEFORE spending any
Anthropic credit on the real run.

Run:
  python scripts/smoketest_implicit_eval.py
  python scripts/smoketest_implicit_eval.py --domain shopping_ebay_generic --backbone o4-mini

Cost: $0. Wall clock: <2 seconds.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Skip the import-time env-var check by exporting placeholder keys.
for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
    os.environ.setdefault(k, "smoketest-placeholder")

import implicit_eval_autogen as ie  # noqa: E402

ROOT = os.path.dirname(SCRIPT_DIR)


def _make_canned_response(categories):
    return json.dumps({"violations": [{"category": c} for c in categories]})


def install_fake_judges(plan):
    """Replace the three judge functions with deterministic fakes.

    plan: callable (step_text, irrelevant) -> dict with keys 'gpt',
          'claude', 'deepseek', each a list of category strings to flag.
    """
    state = {"call_count": 0, "by_step": []}

    def fake_runner(judge_key):
        def _f(prompt):
            state["call_count"] += 1
            irr_block, step_block = _split_prompt(prompt)
            cats = plan(step_block, irr_block)[judge_key]
            return _make_canned_response(cats)
        return _f

    ie.judge_gpt = fake_runner("gpt")
    ie.judge_claude = fake_runner("claude")
    ie.judge_deepseek = fake_runner("deepseek")
    return state


def _split_prompt(prompt):
    """Return (irrelevant_attributes_text, step_text) parsed back from the prompt
    that implicit_eval_autogen built. We use these to drive the fake plan."""
    irr_marker = "IRRELEVANT (must NOT be revealed, even by implication):"
    step_marker = "AI AGENT STEP TO ANALYZE:"
    end_marker = "Identify ONLY implicit violations"
    irr_idx = prompt.find(irr_marker)
    step_idx = prompt.find(step_marker)
    end_idx = prompt.find(end_marker)
    irr = prompt[irr_idx + len(irr_marker):step_idx].strip() if irr_idx != -1 else ""
    step = prompt[step_idx + len(step_marker):end_idx].strip() if step_idx != -1 else ""
    step = step.strip("-").strip()
    return irr, step


def make_plan_for_persona(personas_meta):
    """Return a plan() that flags CI on every step (as if every judge thought
    the agent's actions implied an irrelevant attribute). Two of three judges
    agree; the third also agrees so jury sums match expectations cleanly."""
    def plan(step_text, irr_block):
        # Always flag indirect_content for all 3 judges.
        # Add indirect_behavioral on every other step for variety.
        bi = ["indirect_behavioral"] if (len(step_text) % 2 == 0) else []
        return {
            "gpt": ["indirect_content"] + bi,
            "claude": ["indirect_content"] + bi,
            "deepseek": ["indirect_content"],
        }
    return plan


def main():
    p = argparse.ArgumentParser(description="Offline smoke test for implicit_eval_autogen.py")
    p.add_argument("--domain", default="shopping_ebay_generic")
    p.add_argument("--backbone", default="o4-mini")
    args = p.parse_args()

    # 1. Build a temp output tree and rewire the script to write there.
    tmp = tempfile.mkdtemp(prefix="implicit_eval_smoketest_")
    out_root = os.path.join(tmp, "out")
    os.makedirs(out_root, exist_ok=True)

    # implicit_eval_autogen builds output paths under ROOT/results_autogen[_<backbone>]/<domain>/.
    # The simplest way to redirect output for the smoke test is to monkey-patch ROOT.
    real_root = ie.ROOT
    ie.ROOT = tmp
    # Copy the trajectories and tasks the real evaluator needs into the temp ROOT.
    for sub in ["trajectories", "tasks"]:
        src = os.path.join(real_root, sub)
        dst = os.path.join(tmp, sub)
        if os.path.isdir(src):
            shutil.copytree(src, dst)

    # 2. Install fake judges.
    persona_path = os.path.join(real_root, "tasks", "less_sensitive", f"{args.domain}.json")
    if not os.path.isfile(persona_path):
        sys.exit(f"persona file not found: {persona_path}")
    personas_meta = {p["name"]: p for p in json.load(open(persona_path))["personas"]}
    state = install_fake_judges(make_plan_for_persona(personas_meta))

    # 3. Run the real evaluator end-to-end.
    print(f"Running implicit_eval_autogen against {args.domain}/{args.backbone} with FAKE judges (no API calls)...")
    ie.run(args.domain, args.backbone, trajectories_dir=None, tasks_dir=None, weights_from=None)

    # 4. Read the output back and assert.
    results_root = "results_autogen" if args.backbone == "gpt-4o" else f"results_autogen_{args.backbone}"
    out_path = os.path.join(tmp, results_root, args.domain, "jury_results_fixed.json")
    if not os.path.isfile(out_path):
        sys.exit(f"FAIL: expected output not produced at {out_path}")
    out = json.load(open(out_path))

    print()
    print("=" * 60)
    print("Smoke test assertions")
    print("=" * 60)

    failures = []

    def check(cond, msg):
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {msg}")
        if not cond:
            failures.append(msg)

    check(out.get("method") == "implicit_only_3judge_weighted_average",
          f"method tag is implicit-only (got {out.get('method')!r})")
    check(out["totals"]["jury"]["CE"] == 0,
          f"explicit CE zeroed out (got {out['totals']['jury']['CE']})")
    check(out["totals"]["jury"]["BE"] == 0,
          f"explicit BE zeroed out (got {out['totals']['jury']['BE']})")
    check(out["totals"]["jury"]["CI"] > 0,
          f"implicit CI populated (got {out['totals']['jury']['CI']})")

    # The three judges should each have non-zero CI in their per-judge totals.
    for j in ["gpt", "claude", "deepseek"]:
        check(out["totals"][j]["CI"] > 0,
              f"judge {j!r} per-judge CI populated (got {out['totals'][j]['CI']})")

    # Drop filter sanity: total raw CI flagged should equal personas-summed CI
    # PLUS the dropped count. (`drop_stats` reports how many CI flags were
    # demoted because the agent typed the irrelevant attribute verbatim.)
    drop = out.get("drop_stats", {})
    check("dropped" in drop and drop["dropped"] >= 0,
          f"drop_stats reports dropped count (got {drop.get('dropped')})")
    check(drop.get("ci_before", 0) >= drop.get("ci_after", 0),
          "CI count before drop >= after (drop filter never increases CI)")

    # Aggregator path: simulate the user's next step (aggregate_to_tables.py)
    # by checking the file is shaped the way the aggregator expects.
    check(isinstance(out.get("personas"), dict) and len(out["personas"]) > 0,
          f"personas dict populated (got {len(out.get('personas', {}))} entries)")
    sample_persona = next(iter(out["personas"].values()))
    check("steps" in sample_persona and sample_persona["steps"] > 0,
          f"persona records 'steps' count (got {sample_persona.get('steps')})")

    print()
    if failures:
        print(f"FAILED — {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        print(f"\nTemp output preserved for inspection: {tmp}")
        sys.exit(1)

    # Tear down on success.
    shutil.rmtree(tmp, ignore_errors=True)
    n_judges = state["call_count"]
    n_personas = len(out["personas"])
    n_steps = sum(p["steps"] for p in out["personas"].values())
    jury_ci = out["totals"]["jury"]["CI"]
    jury_bi = out["totals"]["jury"]["BI"]
    print(f"OK — {n_personas} personas, {n_steps} steps, {n_judges} fake judge calls")
    print(f"     Jury totals: CI={jury_ci}, BI={jury_bi}, CE=0 (implicit-only), BE=0")
    print(f"     Drop filter: {drop['ci_before']} CI flags raw → {drop['ci_after']} after drop")
    print()
    print("Plumbing works. Safe to run the real evaluator now:")
    print(f"  python scripts/implicit_eval_autogen.py --domain {args.domain} --backbone {args.backbone}")


if __name__ == "__main__":
    main()
