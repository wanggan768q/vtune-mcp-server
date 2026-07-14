"""VTune Profiler MCP Server — exposes Intel VTune CLI as tools for Claude Code."""

import html as _html_module
import os
import re
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def _esc(s: str) -> str:
    """Escape HTML special characters."""
    return _html_module.escape(s)

def _get_col(parts: list[str], col_map: dict[str, int], key: str) -> str:
    """Return cell value by column name, or empty string if absent."""
    idx = col_map.get(key)
    if idx is None or idx >= len(parts):
        return ""
    return parts[idx].strip()


# ponytail: single-file server, no abstractions needed
mcp = FastMCP("vtune-profiler")

VTUNE_PATH = os.environ.get(
    "VTUNE_PATH",
    r"C:\Program Files (x86)\Intel\oneAPI\vtune\2026.1\bin64\vtune.exe",
)
MAX_OUTPUT = 50000  # ponytail: truncate to avoid MCP token ceiling


def _save_csv(result_dir: str, output: str, suffix: str = "") -> str:
    """Save CSV output into the result directory. Returns file path."""
    name = Path(result_dir).name
    filename = f"{name}{suffix}.csv"
    out_path = Path(result_dir) / filename
    try:
        out_path.write_text(output, encoding="utf-8")
        return str(out_path)
    except Exception as e:
        return f"[Save Error] {e}"


def _run_vtune(args: list[str], timeout: int = 120, knobs: list[str] | None = None) -> str:
    """Run vtune CLI and return stdout or error message.

    Args:
        args: VTune CLI arguments (without the vtune binary path).
        timeout: Max seconds to wait for the command.
        knobs: Extra report-knob flags (e.g. ["-report-knob", "show-issues=false"]).
    """
    cmd = [VTUNE_PATH] + args + (knobs or [])
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return f"[VTune Error (exit {result.returncode})]\n{result.stderr.strip()}"
        output = result.stdout
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + f"\n\n... [truncated, total {len(result.stdout)} chars]"
        return output
    except subprocess.TimeoutExpired:
        return f"[VTune Timeout] Command exceeded {timeout}s"
    except FileNotFoundError:
        return f"[VTune Not Found] {VTUNE_PATH} does not exist. Set VTUNE_PATH env var."
    except PermissionError:
        return f"[VTune Permission Denied] {VTUNE_PATH} is not an executable file. Check VTUNE_PATH."
    except UnicodeDecodeError as exc:
        return f"[VTune Encoding Error] Failed to decode VTune output: {exc}"


def _resolve_result_dir(result_dir: str) -> str:
    """Resolve result_dir — if it's just a name like 'r010hs', look in common locations."""
    if os.path.isdir(result_dir):
        return result_dir
    # Try as relative to VTUNE_PROJECT_DIR
    project_dir = os.environ.get("VTUNE_PROJECT_DIR", "")
    if project_dir:
        candidate = os.path.join(project_dir, result_dir)
        if os.path.isdir(candidate):
            return candidate
    return result_dir  # let vtune report the error


@mcp.tool()
def vtune_report(
    result_dir: str,
    report_type: str = "hotspots",
    format: str = "csv",
    group_by: str = "function",
    save_csv: bool = True,
    fast: bool = True,
) -> str:
    """Generate a VTune profiling report from a result directory.

    Args:
        result_dir: Path to VTune result directory (e.g. C:/Users/.../r010hs)
        report_type: Report type — hotspots, summary, top-down, callstacks, hw-events
        format: Output format — csv or text
        group_by: Grouping — function, module, source-file, thread
        save_csv: Save CSV output to result_dir/<name>.csv (only when format=csv)
        fast: Skip performance-issue descriptions to speed up CSV generation (default True)
    """
    result_dir = _resolve_result_dir(result_dir)
    knobs = ["-report-knob", "show-issues=false"] if fast else []
    args = [
        "-report", report_type,
        "-result-dir", result_dir,
        "-format", format,
    ]
    if report_type not in ("summary",):
        args += ["-group-by", group_by]
    output = _run_vtune(args, knobs=knobs)
    if save_csv and format == "csv" and not output.startswith(("[VTune", "[Error", "[Save Error", "[VTune Timeout", "[VTune Not Found")):
        saved = _save_csv(result_dir, output)
        return f"{output}\n\n[Saved] {saved}"
    return output


@mcp.tool()
def vtune_list_results(project_dir: str) -> str:
    """List all VTune result directories in a project folder.

    Args:
        project_dir: Path to VTune project folder containing result directories
    """
    project = Path(project_dir)
    if not project.is_dir():
        return f"[Error] Directory not found: {project_dir}"

    results = []
    for d in sorted(project.iterdir()):
        if not d.is_dir():
            continue
        # VTune result dirs have a .vtune metadata file or config/ subfolder
        vtune_files = list(d.glob("*.vtune"))
        config_dir = d / "config"
        if vtune_files or config_dir.is_dir():
            # Try to detect analysis type from dir name suffix
            alias = "unknown"
            match = re.search(r"\d+(hs|ue|ps|mc|ma|tr|th)", d.name)
            if match:
                type_map = {
                    "hs": "hotspots", "ue": "microarchitecture",
                    "ps": "platform-profiler", "mc": "memory-consumption",
                    "ma": "memory-access", "tr": "threading", "th": "threading",
                }
                alias = type_map.get(match.group(1), match.group(1))
            results.append(f"{d.name}  ({alias})")

    if not results:
        return f"[No VTune results found in {project_dir}]"
    return "\n".join(results)


@mcp.tool()
def vtune_compare(
    result_dir_1: str,
    result_dir_2: str,
    report_type: str = "hotspots",
    format: str = "csv",
    save_csv: bool = True,
    fast: bool = True,
) -> str:
    """Compare two VTune result directories.

    Args:
        result_dir_1: First result directory (baseline)
        result_dir_2: Second result directory (comparison)
        report_type: Report type — hotspots, summary, top-down
        format: Output format — csv or text
        save_csv: Save CSV output to baseline result_dir/<name1>_vs_<name2>.csv (only when format=csv)
        fast: Skip performance-issue descriptions to speed up CSV generation (default True)
    """
    result_dir_1 = _resolve_result_dir(result_dir_1)
    result_dir_2 = _resolve_result_dir(result_dir_2)
    knobs = ["-report-knob", "show-issues=false"] if fast else []
    args = [
        "-report", report_type,
        "-result-dir", result_dir_1,
        "-compare-with", result_dir_2,
        "-format", format,
    ]
    output = _run_vtune(args, knobs=knobs)
    if save_csv and format == "csv" and not output.startswith(("[VTune", "[Error", "[Save Error", "[VTune Timeout", "[VTune Not Found")):
        name1 = Path(result_dir_1).name
        name2 = Path(result_dir_2).name
        saved = _save_csv(result_dir_1, output, suffix=f"_vs_{name2}")
        return f"{output}\n\n[Saved] {saved}"
    return output


@mcp.tool()
def vtune_summary(result_dir: str) -> str:
    """Get a quick summary of a VTune result (elapsed time, top metrics).

    Args:
        result_dir: Path to VTune result directory
    """
    result_dir = _resolve_result_dir(result_dir)
    return _run_vtune(["-report", "summary", "-result-dir", result_dir, "-format", "text"])


@mcp.tool()
def vtune_hotspots(
    result_dir: str,
    top_n: int = 30,
    group_by: str = "function",
    save_csv: bool = True,
    fast: bool = True,
) -> str:
    """Get top N hotspot functions from a VTune result (CSV format for easy AI analysis).

    Args:
        result_dir: Path to VTune result directory
        top_n: Number of top functions to return (default 30)
        group_by: Grouping — function, module, source-file, thread
        save_csv: Save CSV output to result_dir/<name>_hotspots.csv
        fast: Skip performance-issue descriptions to speed up CSV generation (default True)
    """
    result_dir = _resolve_result_dir(result_dir)
    knobs = ["-report-knob", "show-issues=false"] if fast else []
    output = _run_vtune([
        "-report", "hotspots",
        "-result-dir", result_dir,
        "-format", "csv",
        "-group-by", group_by,
    ], knobs=knobs)
    if output.startswith(("[VTune", "[Error", "[Save Error", "[VTune Timeout", "[VTune Not Found")):
        return output
    # Keep header + top_n data lines
    lines = output.splitlines()
    if lines:
        result_lines = [lines[0]] + lines[1 : top_n + 1]
        output = "\n".join(result_lines)
    if save_csv:
        saved = _save_csv(result_dir, output, suffix="_hotspots")
        return f"{output}\n\n[Saved] {saved}"
    return output


def _parse_topdown(csv_text: str) -> tuple[list[dict], dict[str, int]]:
    """Parse VTune top-down CSV into rows with depth and column map.

    Returns a tuple of (rows, col_map) where col_map maps column names
    to 0-based indices from the CSV header.
    """
    rows = []
    col_map: dict[str, int] = {}
    for line in csv_text.splitlines():
        if not line.strip() or line.startswith("vtune:") or line.startswith("Elapsed Time"):
            continue
        if '\t' not in line:
            continue
        parts = line.split('\t')
        if not parts:
            continue
        func_field = parts[0].strip()
        # First tab-separated line with "Function Stack" is the header
        if not col_map and func_field == "Function Stack":
            for idx, col in enumerate(parts):
                col_map[col.strip()] = idx
            continue
        depth = 0
        while depth < len(parts[0]) and parts[0][depth] == ' ':
            depth += 1
        name = parts[0].strip()
        if not name:
            continue
        rows.append({
            "name": name,
            "depth": depth,
            "raw": line,
            "parts": parts,
        })
    return rows, col_map


def _build_subtree(rows: list[dict], target: str, max_depth: int = 50) -> list[dict]:
    """Extract subtree rooted at target function up to max_depth additional levels.

    Priority: exact (case-insensitive) match if present; falls back to substring
    otherwise. This prevents partial names like 'Step' from matching multiple
    unrelated functions.
    """
    target_lc = target.lower()
    has_exact = any(r["name"].lower() == target_lc for r in rows)

    subtree = []
    in_scope = False
    base_depth = 0
    for row in rows:
        if not in_scope:
            name_lc = row["name"].lower()
            matched = (name_lc == target_lc) if has_exact else (target_lc in name_lc)
            if matched:
                in_scope = True
                base_depth = row["depth"]
                subtree.append(row)
            continue
        # We are past the target; stop when we encounter a row at same or shallower depth
        if row["depth"] <= base_depth:
            break
        if row["depth"] <= base_depth + max_depth:
            subtree.append(row)
    return subtree


def _compare_subtrees_html(
    a_rows: list[dict],
    b_rows: list[dict],
    max_depth: int,
    a_col_map: dict[str, int],
    b_col_map: dict[str, int],
    baseline_name: str = "Baseline",
    compare_name: str = "Compare",
) -> str:
    """Build an interactive HTML table comparing two subtrees from template.

    Rows are emitted in original CSV order so the call tree stays readable.
    """
    a_by = {(r["name"], r["depth"]): r for r in a_rows}
    b_by = {(r["name"], r["depth"]): r for r in b_rows}

    # Merge keys preserving original order from both sides
    seen: set[tuple[str, int]] = set()
    all_keys: list[tuple[str, int]] = []
    for r in a_rows:
        key = (r["name"], r["depth"])
        if key not in seen:
            seen.add(key)
            all_keys.append(key)
    for r in b_rows:
        key = (r["name"], r["depth"])
        if key not in seen:
            seen.add(key)
            all_keys.append(key)

    rows_html = []
    for idx, (name, depth) in enumerate(all_keys):
        a_row = a_by.get((name, depth))
        b_row = b_by.get((name, depth))

        a_total = _get_col(a_row["parts"], a_col_map, "CPU Time:Total") if a_row else ""
        b_total = _get_col(b_row["parts"], b_col_map, "CPU Time:Total") if b_row else ""
        a_self  = _get_col(a_row["parts"], a_col_map, "CPU Time:Self") if a_row else ""
        b_self  = _get_col(b_row["parts"], b_col_map, "CPU Time:Self") if b_row else ""

        def _fmt_num(val_str: str) -> tuple[float, str]:
            try:
                v = float(val_str)
                return v, f"{v:.3f}"
            except (ValueError, TypeError):
                return 0.0, val_str or "—"

        at_f, at_s = _fmt_num(a_total)
        bt_f, bt_s = _fmt_num(b_total)
        as_f, as_s = _fmt_num(a_self)
        bs_f, bs_s = _fmt_num(b_self)

        dt_f = bt_f - at_f
        ds_f = bs_f - as_f

        def _diff_cls(val: float) -> str:
            if val > 0.001:
                return "diff-worse"
            if val < -0.001:
                return "diff-better"
            return "diff-neutral"

        has_children = (idx + 1 < len(all_keys) and all_keys[idx + 1][1] > depth)
        toggle = '<span class="toggle" onclick="toggleRow(this)">▼</span>' if has_children else '<span class="toggle-placeholder"></span>'

        rows_html.append(
            f'<tr data-depth="{depth}" class="d{depth}">'
            f'  <td style="padding-left:{depth * 20 + 8}px">{toggle}<span class="fname">{_esc(name)}</span></td>'
            f'  <td class="num">{at_s}</td>'
            f'  <td class="num">{bt_s}</td>'
            f'  <td class="num">{as_s}</td>'
            f'  <td class="num">{bs_s}</td>'
            f'  <td class="num {_diff_cls(dt_f)}">{dt_f:+.3f}</td>'
            f'  <td class="num {_diff_cls(ds_f)}">{ds_f:+.3f}</td>'
            f'</tr>'
        )

    tpl_path = Path(__file__).resolve().parent / "templates" / "function_tree.html"
    try:
        template = tpl_path.read_text(encoding="utf-8")
    except Exception:
        # Fallback: inline minimal HTML if template missing
        return "[Template Error] function_tree.html not found"

    return template.replace(
        "{title}", "VTune Function Tree Comparison"
    ).replace(
        "{baseline_name}", baseline_name
    ).replace(
        "{compare_name}", compare_name
    ).replace(
        "{max_depth}", str(max_depth)
    ).replace(
        "{rows}", "\n".join(rows_html)
    )


def _build_markdown(
    a_rows: list[dict],
    b_rows: list[dict],
    max_depth: int,
    a_col_map: dict[str, int],
    b_col_map: dict[str, int],
    baseline_name: str = "Baseline",
    compare_name: str = "Compare",
) -> str:
    """Build a side-by-side Markdown table comparing two subtrees."""
    a_by = {(r["name"], r["depth"]): r for r in a_rows}
    b_by = {(r["name"], r["depth"]): r for r in b_rows}

    # Merge keys preserving original order from both sides
    seen: set[tuple[str, int]] = set()
    all_keys: list[tuple[str, int]] = []
    for r in a_rows:
        key = (r["name"], r["depth"])
        if key not in seen:
            seen.add(key)
            all_keys.append(key)
    for r in b_rows:
        key = (r["name"], r["depth"])
        if key not in seen:
            seen.add(key)
            all_keys.append(key)

    def _fmt(a_str: str, b_str: str) -> tuple[str, str, str]:
        try:
            av = float(a_str) if a_str else 0.0
            bv = float(b_str) if b_str else 0.0
            diff = f"{bv - av:+.3f}"
            return f"{av:.3f}", f"{bv:.3f}", diff
        except (ValueError, TypeError):
            return a_str or "—", b_str or "—", "—"

    header = (
        f"|{'Function':<70} | {baseline_name+'(Total%)':>12} | "
        f"{compare_name+'(Total%)':>12} | {baseline_name+'(Self%)':>12} | "
        f"{compare_name+'(Self%)':>12} | {'Diff(Total)':>10} | {'Diff(Self)':>10} |"
    )
    sep = (
        f"|{'-'*70}-|{'-'*13}-|{'-'*13}-|"
        f"{'-'*13}-|{'-'*13}-|{'-'*11}-|{'-'*11}-|"
    )
    lines = [header, sep]

    for name, depth in all_keys:
        a_row = a_by.get((name, depth))
        b_row = b_by.get((name, depth))
        indent = "  " * depth
        display = f"{indent}{name}"

        a_total = _get_col(a_row["parts"], a_col_map, "CPU Time:Total") if a_row else ""
        b_total = _get_col(b_row["parts"], b_col_map, "CPU Time:Total") if b_row else ""
        a_self  = _get_col(a_row["parts"], a_col_map, "CPU Time:Self") if a_row else ""
        b_self  = _get_col(b_row["parts"], b_col_map, "CPU Time:Self") if b_row else ""

        at, bt, dt = _fmt(a_total, b_total)
        as_, bs_, ds = _fmt(a_self, b_self)
        lines.append(
            f"|{display:<70} | {at:>12} | {bt:>12} | {as_:>12} | {bs_:>12} | {dt:>10} | {ds:>10} |"
        )

    return "\n".join(lines)


def _save_html(result_dir: str, output: str, suffix: str = "") -> str:
    """Save HTML output into the result directory. Returns file path."""
    name = Path(result_dir).name
    filename = f"{name}{suffix}.html"
    out_path = Path(result_dir) / filename
    try:
        out_path.write_text(output, encoding="utf-8")
        return str(out_path)
    except Exception as e:
        return f"[Save Error] {e}"


def _compare_subtrees_text(
    a_rows: list[dict],
    b_rows: list[dict],
    max_depth: int,
    a_col_map: dict[str, int],
    b_col_map: dict[str, int],
    baseline_name: str = "Baseline",
    compare_name: str = "Compare",
) -> str:
    """Build a plain-text side-by-side comparison string for two subtrees.

    Rows are emitted in original CSV order so the call tree stays readable.
    """
    md = _build_markdown(a_rows, b_rows, max_depth, a_col_map, b_col_map, baseline_name, compare_name)
    return md


@mcp.tool()
def vtune_function_tree(
    result_dir_baseline: str,
    result_dir_compare: str,
    function_name: str,
    max_depth: int = 50,
    group_by: str = "function",
    output_format: str = "html",
    save_html: bool = True,
) -> str:
    """Locate a function in VTune top-down call tree and compare its subtree between two results.

    Args:
        result_dir_baseline: Baseline result directory
        result_dir_compare: Comparison result directory
        function_name: Function name (or substring) to search for in the call tree
        max_depth: Max depth of callees to display below the matched function (default 50)
        group_by: Grouping — function, module, source-file, thread
        output_format: Output format — html (interactive), markdown (AI-friendly table), or text (terminal)
        save_html: Save HTML output to baseline result_dir/<baseline>_vs_<compare>_tree.html (when output_format=html)
    """
    dir1 = _resolve_result_dir(result_dir_baseline)
    dir2 = _resolve_result_dir(result_dir_compare)

    out1 = _run_vtune([
        "-report", "top-down",
        "-result-dir", dir1,
        "-format", "csv",
        "-group-by", group_by,
    ], knobs=["-report-knob", "show-issues=false", "-report-knob", "hide-recursive-entries=true"])
    out2 = _run_vtune([
        "-report", "top-down",
        "-result-dir", dir2,
        "-format", "csv",
        "-group-by", group_by,
    ], knobs=["-report-knob", "show-issues=false", "-report-knob", "hide-recursive-entries=true"])

    if out1.startswith(("[VTune", "[Error", "[Save Error", "[VTune Timeout", "[VTune Not Found")) or \
       out2.startswith(("[VTune", "[Error", "[Save Error", "[VTune Timeout", "[VTune Not Found")):
        return f"[Error generating top-down report]\nBaseline: {out1[:500]}\nCompare: {out2[:500]}"

    rows1, a_col_map = _parse_topdown(out1)
    rows2, b_col_map = _parse_topdown(out2)

    sub1 = _build_subtree(rows1, function_name, max_depth)
    sub2 = _build_subtree(rows2, function_name, max_depth)

    if not sub1 and not sub2:
        return f"[Not Found] Function '{function_name}' not found in either top-down tree."

    name1 = Path(dir1).name
    name2 = Path(dir2).name

    if output_format.lower() == "html":
        result = _compare_subtrees_html(sub1, sub2, max_depth, a_col_map, b_col_map, baseline_name=name1, compare_name=name2)
        if save_html:
            saved = _save_html(dir1, result, suffix=f"_vs_{name2}_tree")
            return f"[Saved] {saved}"
        return result

    # markdown or text — both return Markdown table (readable in terminal and AI-friendly)
    result = _compare_subtrees_text(sub1, sub2, max_depth, a_col_map, b_col_map, baseline_name=name1, compare_name=name2)
    return result


def main():
    """Entry point — run via `python server.py` or uvx."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()