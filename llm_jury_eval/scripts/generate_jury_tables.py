#!/usr/bin/env python3
"""
Convert auto-generated jury cell files (from aggregate_to_tables.py)
into complete LaTeX tables.

Usage:
    python generate_jury_tables.py tables_filled_o3.tex --backbone o3
    python generate_jury_tables.py tables_filled_gpt4o.tex --backbone gpt-4o
    python generate_jury_tables.py tables_filled_sonnet.tex --backbone claude-sonnet-4
"""

import argparse
import re
import sys


def parse_cells(filepath):
    """Parse the auto-generated .tex file into structured data."""
    with open(filepath) as f:
        lines = f.readlines()

    table2 = {}  # (website, framework, prompt) -> (behav_occ, behav_rate, cont_occ, cont_rate)
    table3 = {}  # (website, framework, prompt) -> (cont_occ, cont_rate, behav_occ, behav_rate)

    current_section = None
    current_key = None

    for line in lines:
        line = line.strip()

        if "Table 2 cells" in line:
            current_section = "table2"
            continue
        elif "Table 3 cells" in line:
            current_section = "table3"
            continue

        # Parse comment lines for keys
        if line.startswith("%") and current_section:
            comment = line.lstrip("% ").strip()
            if current_section == "table2":
                # e.g. "Amazon AutoGen chat" or "eBay Browser-Use email"
                parts = comment.split()
                if len(parts) >= 3:
                    website = parts[0]
                    framework = parts[1]
                    prompt = parts[2]
                    current_key = (website, framework, prompt)
            elif current_section == "table3":
                # New format: "Amazon AutoGen chat" / "eBay Browser-Use email".
                # Legacy format (pre-AutoGen-implicit fix): "Amazon chat" /
                # "eBay generic" — implicitly Browser-Use only.
                parts = comment.split()
                if len(parts) >= 3:
                    website, framework, prompt = parts[0], parts[1], parts[2]
                    current_key = (website, framework, prompt)
                elif len(parts) == 2:
                    website, prompt = parts[0], parts[1]
                    current_key = (website, "Browser-Use", prompt)
            continue

        # Parse data lines
        if current_key and ("&" in line or line.startswith("\\texttt")):
            # Extract numbers from the line
            nums = re.findall(r'[\d]+(?:\.[\d]+)?', line)
            if len(nums) >= 4:
                vals = (int(nums[0]), float(nums[1]), int(nums[2]), float(nums[3]))
                if current_section == "table2":
                    table2[current_key] = vals
                elif current_section == "table3":
                    table3[current_key] = vals
                current_key = None

    return table2, table3


def compute_totals(rows):
    """Compute weighted-average totals from list of (behav_occ, behav_rate, cont_occ, cont_rate)."""
    total_behav = sum(r[0] for r in rows)
    total_cont = sum(r[2] for r in rows)
    # Derive steps from occ/rate
    total_steps = 0
    for r in rows:
        if r[1] > 0:
            total_steps += r[0] / r[1]
        elif r[3] > 0:
            total_steps += r[2] / r[3]
    if total_steps == 0:
        return total_behav, 0, total_cont, 0
    avg_behav_rate = total_behav / total_steps
    avg_cont_rate = total_cont / total_steps
    return total_behav, avg_behav_rate, total_cont, avg_cont_rate


def fmt(val, is_occ=True):
    """Format a value for the table."""
    if val is None:
        return "---"
    if is_occ:
        return str(int(val))
    return f".{val:.3f}"[1:]  # e.g. .379


def fmt_rate(val):
    if val == 0:
        return ".000"
    return f"{val:.3f}"


def generate_explicit_table(table2, backbone):
    """Generate Table 2 (Explicit oversharing)."""
    websites = ["Amazon", "eBay"]
    frameworks = ["AutoGen", "Browser-Use"]
    prompts = ["chat", "email", "generic"]

    lines = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{\textbf{Explicit oversharing (LLM-Jury) on Amazon and eBay with \texttt{" + backbone + r"}.}}")
    lines.append(r"\resizebox{\textwidth}{!}{%")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{llcccccccc}")
    lines.append(r"\toprule")
    lines.append(r"\multirow{3}{*}{\textbf{Website}} & \multirow{3}{*}{\textbf{Prompt}} &")
    lines.append(r"\multicolumn{4}{c}{\textbf{AutoGen}} &")
    lines.append(r"\multicolumn{4}{c}{\textbf{Browser-Use}} \\")
    lines.append(r"\cmidrule(lr){3-6} \cmidrule(lr){7-10}")
    lines.append(r" & & \multicolumn{2}{c}{\textbf{Behav.}} &")
    lines.append(r"     \multicolumn{2}{c}{\textbf{Cont.}} &")
    lines.append(r"     \multicolumn{2}{c}{\textbf{Behav.}} &")
    lines.append(r"     \multicolumn{2}{c}{\textbf{Cont.}} \\")
    lines.append(r"\cmidrule(lr){3-4} \cmidrule(lr){5-6} \cmidrule(lr){7-8} \cmidrule(lr){9-10}")
    lines.append(r" & & Occ. & Rate & Occ. & Rate & Occ. & Rate & Occ. & Rate \\")
    lines.append(r"\midrule")

    for i, website in enumerate(websites):
        lines.append(r"\multirow{4}{*}{" + website + "}")

        ag_rows = []
        bu_rows = []

        for prompt in prompts:
            ag_key = (website, "AutoGen", prompt)
            bu_key = (website, "Browser-Use", prompt)

            ag = table2.get(ag_key)
            bu = table2.get(bu_key)

            if ag:
                ag_rows.append(ag)
            if bu:
                bu_rows.append(bu)

            # Format cells
            if ag:
                ag_str = f"  {ag[0]} & {fmt_rate(ag[1])} & {ag[2]} & {fmt_rate(ag[3])}"
            else:
                ag_str = "--- & --- & --- & ---"

            if bu:
                bu_str = f"{bu[0]} & {fmt_rate(bu[1])} & {bu[2]} & {fmt_rate(bu[3])}"
            else:
                bu_str = "--- & --- & --- & ---"

            lines.append(f"  & \\texttt{{{prompt}}} & {ag_str} & {bu_str} \\\\")

        # Total row
        lines.append(r"  \cmidrule{2-10}")
        if ag_rows:
            ag_tot = compute_totals(ag_rows)
            ag_tot_str = (f"\\textbf{{{ag_tot[0]}}} & \\textbf{{{fmt_rate(ag_tot[1])}}} & "
                          f"\\textbf{{{ag_tot[2]}}} & \\textbf{{{fmt_rate(ag_tot[3])}}}")
        else:
            ag_tot_str = "--- & --- & --- & ---"

        if bu_rows:
            bu_tot = compute_totals(bu_rows)
            bu_tot_str = (f"\\textbf{{{bu_tot[0]}}} & \\textbf{{{fmt_rate(bu_tot[1])}}} & "
                          f"\\textbf{{{bu_tot[2]}}} & \\textbf{{{fmt_rate(bu_tot[3])}}}")
        else:
            bu_tot_str = "--- & --- & --- & ---"

        lines.append(f"  & \\textit{{Total}} & {ag_tot_str} & {bu_tot_str} \\\\")

        if i < len(websites) - 1:
            lines.append(r"\midrule")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}%")
    lines.append(r"}")
    label = backbone.replace("-", "").replace(".", "").replace(" ", "")
    lines.append(r"\label{tab:explicit_oversharing_jury_" + label + "}")
    lines.append(r"\end{table}")

    return "\n".join(lines)


def generate_implicit_table(table2, table3, backbone):
    """Generate Table 3 (Implicit oversharing)."""
    websites = ["Amazon", "eBay"]
    prompts = ["chat", "email", "generic"]

    lines = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{\textbf{Implicit oversharing (LLM-Jury) on Amazon and eBay with \texttt{" + backbone + r"}.}}")
    lines.append(r"\resizebox{\textwidth}{!}{%")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{llcccccccc}")
    lines.append(r"\toprule")
    lines.append(r"\multirow{3}{*}{\textbf{Website}} & \multirow{3}{*}{\textbf{Prompt}} &")
    lines.append(r"\multicolumn{4}{c}{\textbf{AutoGen}} &")
    lines.append(r"\multicolumn{4}{c}{\textbf{Browser-Use}} \\")
    lines.append(r"\cmidrule(lr){3-6} \cmidrule(lr){7-10}")
    # NOTE: Implicit cells in tables_filled_<bb>.tex are emitted in the
    # order (CI_occ, CI_rate, BI_occ, BI_rate) — i.e. CONTENT first, then
    # BEHAVIORAL. Headers below match that order. (This is the opposite
    # of the explicit table above, which emits behavioral first then
    # content. The asymmetry is historical; fixing it requires changing
    # aggregate_to_tables.py and regenerating every existing cell file.)
    lines.append(r" & & \multicolumn{2}{c}{\textbf{Cont.}} &")
    lines.append(r"     \multicolumn{2}{c}{\textbf{Behav.}} &")
    lines.append(r"     \multicolumn{2}{c}{\textbf{Cont.}} &")
    lines.append(r"     \multicolumn{2}{c}{\textbf{Behav.}} \\")
    lines.append(r"\cmidrule(lr){3-4} \cmidrule(lr){5-6} \cmidrule(lr){7-8} \cmidrule(lr){9-10}")
    lines.append(r" & & Occ. & Rate & Occ. & Rate & Occ. & Rate & Occ. & Rate \\")
    lines.append(r"\midrule")

    for i, website in enumerate(websites):
        lines.append(r"\multirow{4}{*}{" + website + "}")

        ag_rows = []
        bu_rows = []

        for prompt in prompts:
            ag = table3.get((website, "AutoGen", prompt))
            bu = table3.get((website, "Browser-Use", prompt))

            if ag:
                ag_rows.append(ag)
                ag_str = f"  {ag[0]} & {fmt_rate(ag[1])} & {ag[2]} & {fmt_rate(ag[3])}"
            else:
                ag_str = "--- & --- & --- & ---"

            if bu:
                bu_rows.append(bu)
                bu_str = f"{bu[0]} & {fmt_rate(bu[1])} & {bu[2]} & {fmt_rate(bu[3])}"
            else:
                bu_str = "--- & --- & --- & ---"

            lines.append(f"  & \\texttt{{{prompt}}} & {ag_str} & {bu_str} \\\\")

        # Total row
        lines.append(r"  \cmidrule{2-10}")
        if ag_rows:
            ag_tot = compute_totals(ag_rows)
            ag_tot_str = (f"\\textbf{{{ag_tot[0]}}} & \\textbf{{{fmt_rate(ag_tot[1])}}} & "
                          f"\\textbf{{{ag_tot[2]}}} & \\textbf{{{fmt_rate(ag_tot[3])}}}")
        else:
            ag_tot_str = "--- & --- & --- & ---"

        if bu_rows:
            bu_tot = compute_totals(bu_rows)
            bu_tot_str = (f"\\textbf{{{bu_tot[0]}}} & \\textbf{{{fmt_rate(bu_tot[1])}}} & "
                          f"\\textbf{{{bu_tot[2]}}} & \\textbf{{{fmt_rate(bu_tot[3])}}}")
        else:
            bu_tot_str = "--- & --- & --- & ---"

        lines.append(f"  & \\textit{{Total}} & {ag_tot_str} & {bu_tot_str} \\\\")

        if i < len(websites) - 1:
            lines.append(r"\midrule")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}%")
    lines.append(r"}")
    label = backbone.replace("-", "").replace(".", "").replace(" ", "")
    lines.append(r"\label{tab:implicit_oversharing_jury_" + label + "}")
    lines.append(r"\end{table}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Convert jury cell files to LaTeX tables")
    parser.add_argument("input", help="Path to the auto-generated .tex cell file")
    parser.add_argument("--backbone", "-b", required=True, help="Backbone model name (e.g., o3, gpt-4o)")
    parser.add_argument("--output", "-o", help="Output .tex file (default: stdout)")
    parser.add_argument(
        "--only",
        choices=["explicit", "implicit", "both"],
        default="both",
        help=(
            "Restrict output to one table. Use 'implicit' to emit only the "
            "Table 3 / Table 11 LaTeX block (paper appendix C.3 AutoGen-row "
            "fill-in). Default: both."
        ),
    )
    args = parser.parse_args()

    table2, table3 = parse_cells(args.input)

    output = ""
    if args.only in ("explicit", "both"):
        explicit = generate_explicit_table(table2, args.backbone)
        output += f"% === Explicit Oversharing Table ({args.backbone}) ===\n"
        output += explicit
    if args.only in ("implicit", "both"):
        implicit = generate_implicit_table(table2, table3, args.backbone)
        if output:
            output += "\n\n"
        output += f"% === Implicit Oversharing Table ({args.backbone}) ===\n"
        output += implicit

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
