"""VTune Profiler MCP Server — exposes Intel VTune CLI as tools for Claude Code."""

import os
import re
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ponytail: single-file server, no abstractions needed
mcp = FastMCP("vtune-profiler")

VTUNE_PATH = os.environ.get(
    "VTUNE_PATH",
    r"C:\Program Files (x86)\Intel\oneAPI\vtune\2026.1\bin64\vtune.exe",
)
MAX_OUTPUT = 50000  # ponytail: truncate to avoid MCP token ceiling


def _run_vtune(args: list[str], timeout: int = 120) -> str:
    """Run vtune CLI and return stdout or error message."""
    cmd = [VTUNE_PATH] + args
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


def _resolve_result_dir(result_dir: str) -> str:
    """Resolve result_dir — if it's just a name like 'r010hs', look in common locations."""
    if os.path.isdir(result_dir):
        return result_dir
    # Try as relative to CLAUDE_PROJECT_DIR
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
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
) -> str:
    """Generate a VTune profiling report from a result directory.

    Args:
        result_dir: Path to VTune result directory (e.g. C:/Users/.../r010hs)
        report_type: Report type — hotspots, summary, top-down, callstacks, hw-events
        format: Output format — csv or text
        group_by: Grouping — function, module, source-file, thread
    """
    result_dir = _resolve_result_dir(result_dir)
    args = [
        "-report", report_type,
        "-result-dir", result_dir,
        "-format", format,
    ]
    if report_type not in ("summary",):
        args += ["-group-by", group_by]
    return _run_vtune(args)


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
) -> str:
    """Compare two VTune result directories.

    Args:
        result_dir_1: First result directory (baseline)
        result_dir_2: Second result directory (comparison)
        report_type: Report type — hotspots, summary, top-down
        format: Output format — csv or text
    """
    result_dir_1 = _resolve_result_dir(result_dir_1)
    result_dir_2 = _resolve_result_dir(result_dir_2)
    args = [
        "-report", report_type,
        "-result-dir", result_dir_1,
        "-compare-with", result_dir_2,
        "-format", format,
    ]
    return _run_vtune(args)


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
) -> str:
    """Get top N hotspot functions from a VTune result (CSV format for easy AI analysis).

    Args:
        result_dir: Path to VTune result directory
        top_n: Number of top functions to return (default 30)
        group_by: Grouping — function, module, source-file, thread
    """
    result_dir = _resolve_result_dir(result_dir)
    output = _run_vtune([
        "-report", "hotspots",
        "-result-dir", result_dir,
        "-format", "csv",
        "-group-by", group_by,
    ])
    if output.startswith("["):  # error message
        return output
    # Keep header + top_n data lines
    lines = output.splitlines()
    header_lines = [l for l in lines if l.startswith(("Function", "Module", "Source", "Thread", '"'))]
    data_lines = [l for l in lines if l and l not in header_lines]
    # CSV from vtune: first line is header, rest are data
    if lines:
        result_lines = [lines[0]] + lines[1 : top_n + 1]
        return "\n".join(result_lines)
    return output


def main():
    """Entry point for package installation (uvx/pip)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
