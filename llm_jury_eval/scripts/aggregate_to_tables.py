#!/usr/bin/env python3
"""
Aggregate per-domain jury_results_fixed.json files into Table 2 / Table 3
ready-to-paste numbers.

Looks in three locations:
  - llm_jury_eval/results/<domain>/jury_results_fixed.json          (BU runs)
  - llm_jury_eval/results_autogen/<domain>/jury_results_fixed.json  (AutoGen runs)
  - llm_jury_eval/existing_results/<framework>_<domain>/jury_results_fixed.json
                                                                    (pre-shipped)

Outputs:
  - tables_filled.md  : human-readable Markdown of Tables 2 & 3
  - tables_filled.tex : LaTeX cells you can drop into the paper

Cells without data print as '---'.
"""
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)

CONFIGS_T2 = [
    ("Amazon", "AutoGen", "chat",    "autogen",     "shopping_Amazon_chat"),
    ("Amazon", "AutoGen", "email",   "autogen",     "shopping_Amazon_email"),
    ("Amazon", "AutoGen", "generic", "autogen",     "shopping_Amazon_generic"),
    ("Amazon", "Browser-Use", "chat",    "browseruse", "shopping_Amazon_chat"),
    ("Amazon", "Browser-Use", "email",   "browseruse", "shopping_Amazon_email"),
    ("Amazon", "Browser-Use", "generic", "browseruse", "shopping_Amazon_generic"),
    ("eBay",   "AutoGen", "chat",    "autogen",     "shopping_ebay_chat"),
    ("eBay",   "AutoGen", "email",   "autogen",     "shopping_ebay_email"),
    ("eBay",   "AutoGen", "generic", "autogen",     "shopping_ebay_generic"),
    ("eBay",   "Browser-Use", "chat",    "browseruse", "shopping_ebay_chat"),
    ("eBay",   "Browser-Use", "email",   "browseruse", "shopping_ebay_email"),
    ("eBay",   "Browser-Use", "generic", "browseruse", "shopping_ebay_generic"),
]

CONFIGS_T3 = [
    ("Amazon", "AutoGen",     "chat",    "autogen",    "shopping_Amazon_chat"),
    ("Amazon", "AutoGen",     "email",   "autogen",    "shopping_Amazon_email"),
    ("Amazon", "AutoGen",     "generic", "autogen",    "shopping_Amazon_generic"),
    ("Amazon", "Browser-Use", "chat",    "browseruse", "shopping_Amazon_chat"),
    ("Amazon", "Browser-Use", "email",   "browseruse", "shopping_Amazon_email"),
    ("Amazon", "Browser-Use", "generic", "browseruse", "shopping_Amazon_generic"),
    ("eBay",   "AutoGen",     "chat",    "autogen",    "shopping_ebay_chat"),
    ("eBay",   "AutoGen",     "email",   "autogen",    "shopping_ebay_email"),
    ("eBay",   "AutoGen",     "generic", "autogen",    "shopping_ebay_generic"),
    ("eBay",   "Browser-Use", "chat",    "browseruse", "shopping_ebay_chat"),
    ("eBay",   "Browser-Use", "email",   "browseruse", "shopping_ebay_email"),
    ("eBay",   "Browser-Use", "generic", "browseruse", "shopping_ebay_generic"),
]


def find_results(framework, domain, backbone="gpt-4o"):
    """Return (jury_totals, total_steps) or (None, None) if no data.

    For implicit-only runs (method == "implicit_only_..."), the returned
    jury dict has CE/BE set to ``None`` so the explicit-table renderer
    prints ``---`` for those cells instead of the dummy zeros stored on
    disk. CI/BI are always returned as integers.
    """
    domain_variants = [domain, f"{domain}_modified"]

    candidate_paths = []
    for d in domain_variants:
        if framework == "browseruse":
            if backbone == "gpt-4o":
                candidate_paths.append(os.path.join(ROOT, "results", d, "jury_results_fixed.json"))
                candidate_paths.append(os.path.join(ROOT, "existing_results", f"browseruse_{d}", "jury_results_fixed.json"))
            else:
                candidate_paths.append(os.path.join(ROOT, f"results_{backbone}", d, "jury_results_fixed.json"))
        else:  # autogen
            if backbone == "gpt-4o":
                candidate_paths.append(os.path.join(ROOT, "results_autogen", d, "jury_results_fixed.json"))
                candidate_paths.append(os.path.join(ROOT, "existing_results", f"autogen_{d}", "jury_results_fixed.json"))
            else:
                candidate_paths.append(os.path.join(ROOT, f"results_autogen_{backbone}", d, "jury_results_fixed.json"))
    for p in candidate_paths:
        if os.path.isfile(p):
            data = json.load(open(p))
            jury = dict(data["totals"]["jury"])
            steps = sum(persona["steps"] for persona in data["personas"].values())
            method = data.get("method", "")
            if method.startswith("implicit_only"):
                jury["CE"] = None
                jury["BE"] = None
            return jury, steps
    return None, None


def fmt_occ(v):
    return str(v) if v is not None else "---"


def fmt_rate(occ, steps):
    return f"{occ / steps:.4f}" if (occ is not None and steps and steps > 0) else "---"


def render_table2(backbone="gpt-4o"):
    rows = []
    for site, fw, prompt, fw_key, domain in CONFIGS_T2:
        jury, steps = find_results(fw_key, domain, backbone)
        if jury is None:
            row = (site, fw, prompt, "---", "---", "---", "---")
        else:
            # jury["BE"]/["CE"] may be None for implicit-only runs.
            row = (site, fw, prompt,
                   fmt_occ(jury.get("BE")), fmt_rate(jury.get("BE"), steps),
                   fmt_occ(jury.get("CE")), fmt_rate(jury.get("CE"), steps))
        rows.append(row)
    return rows


def render_table3(backbone="gpt-4o"):
    rows = []
    for site, fw, prompt, fw_key, domain in CONFIGS_T3:
        jury, steps = find_results(fw_key, domain, backbone)
        if jury is None:
            row = (site, fw, prompt, "---", "---", "---", "---")
        else:
            row = (site, fw, prompt,
                   fmt_occ(jury.get("CI")), fmt_rate(jury.get("CI"), steps),
                   fmt_occ(jury.get("BI")), fmt_rate(jury.get("BI"), steps))
        rows.append(row)
    return rows


def write_md(t2, t3, path):
    lines = []
    lines.append("# Tables 2 & 3 — LLM-Jury values\n")
    lines.append("Auto-generated by `scripts/aggregate_to_tables.py`. `---` = no jury data yet.\n")
    lines.append("## Table 2 — Explicit oversharing (gpt-4o backbone)\n")
    lines.append("| Site | Framework | Prompt | Explicit Behavior Occ. | Rate | Explicit Content Occ. | Rate |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in t2:
        lines.append("| " + " | ".join(r) + " |")
    lines.append("")
    lines.append("## Table 3 — Implicit oversharing (gpt-4o)\n")
    lines.append("| Site | Framework | Prompt | Implicit Content Occ. | Rate | Implicit Behavioral Occ. | Rate |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in t3:
        lines.append("| " + " | ".join(r) + " |")
    lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines))


def write_tex(t2, t3, path):
    lines = []
    lines.append("% Auto-generated by scripts/aggregate_to_tables.py")
    lines.append("% --- Table 2 cells (12 rows, in order: Amazon AG/BU x chat/email/generic, eBay AG/BU x chat/email/generic) ---")
    for r in t2:
        site, fw, prompt, be_occ, be_rate, ce_occ, ce_rate = r
        lines.append(f"% {site} {fw} {prompt}")
        lines.append(f"  & \\texttt{{{prompt}}} & {be_occ} & {be_rate} & {ce_occ} & {ce_rate} \\\\")
    lines.append("")
    lines.append("% --- Table 3 cells (12 rows, in order: Amazon AG/BU x chat/email/generic, eBay AG/BU x chat/email/generic) ---")
    for r in t3:
        site, fw, prompt, ci_occ, ci_rate, bi_occ, bi_rate = r
        lines.append(f"% {site} {fw} {prompt}")
        lines.append(f"  & \\texttt{{{prompt}}} & {ci_occ} & {ci_rate} & {bi_occ} & {bi_rate} \\\\")
    with open(path, "w") as f:
        f.write("\n".join(lines))


def main():
    import argparse
    p = argparse.ArgumentParser(
        description=(
            "Build Tables 2 & 3 (gpt-4o, default) or the appendix C.2/C.3 "
            "tables (--backbone o3 / o4-mini) from per-domain jury outputs."
        )
    )
    p.add_argument(
        "--backbone",
        default="gpt-4o",
        help=(
            "Agent backbone whose jury results to aggregate. Default gpt-4o "
            "reads from results/ and results_autogen/. Other backbones read "
            "from results_<backbone>/ and results_autogen_<backbone>/."
        ),
    )
    args = p.parse_args()

    t2 = render_table2(args.backbone)
    t3 = render_table3(args.backbone)

    suffix = "" if args.backbone == "gpt-4o" else f"_{args.backbone}"
    md_path = os.path.join(ROOT, f"tables_filled{suffix}.md")
    tex_path = os.path.join(ROOT, f"tables_filled{suffix}.tex")
    write_md(t2, t3, md_path)
    write_tex(t2, t3, tex_path)

    label = "Tables 2 & 3" if args.backbone == "gpt-4o" else f"Appendix tables (backbone: {args.backbone})"
    print("=" * 70)
    print(f"{label} — Explicit oversharing")
    print("=" * 70)
    print(f"{'Site':<8} {'Framework':<12} {'Prompt':<8} {'BE Occ':<8} {'Rate':<8} {'CE Occ':<8} {'Rate':<8}")
    for r in t2:
        print(f"{r[0]:<8} {r[1]:<12} {r[2]:<8} {r[3]:<8} {r[4]:<8} {r[5]:<8} {r[6]:<8}")
    print()
    print("=" * 70)
    print(f"{label} — Implicit oversharing")
    print("=" * 70)
    print(f"{'Site':<8} {'Framework':<12} {'Prompt':<8} {'CI Occ':<8} {'Rate':<8} {'BI Occ':<8} {'Rate':<8}")
    for r in t3:
        print(f"{r[0]:<8} {r[1]:<12} {r[2]:<8} {r[3]:<8} {r[4]:<8} {r[5]:<8} {r[6]:<8}")
    print()
    print(f"Wrote: {md_path}")
    print(f"Wrote: {tex_path}")


if __name__ == "__main__":
    main()
