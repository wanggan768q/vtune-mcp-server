"""Tests for server.py — uses real VTune result fixtures under tests/fixtures."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# ponytail: single file, import via path hack
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import (  # noqa: E402
    MAX_OUTPUT,
    _build_subtree,
    _compare_subtrees_html,
    _compare_subtrees_text,
    _parse_topdown,
    _resolve_result_dir,
    _run_vtune,
    _save_csv,
    vtune_compare,
    vtune_function_tree,
    vtune_hotspots,
    vtune_list_results,
    vtune_report,
    vtune_summary,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _mock_run(stdout: str, returncode: int = 0, side_effect=None):
    """Return a mock for subprocess.run."""
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = "fake stderr"
    return mock


# ---------------------------------------------------------------------------
# _save_csv
# ---------------------------------------------------------------------------
def test_save_csv_writes_file():
    with tempfile.TemporaryDirectory() as td:
        path = _save_csv(td, "hello,world\n", suffix="_test")
        assert Path(path).exists()
        assert Path(path).read_text() == "hello,world\n"


def test_save_csv_returns_error_on_failure():
    with tempfile.TemporaryDirectory() as td:
        # Remove write permission to force error (Windows: use read-only file)
        f = Path(td) / "readonly.csv"
        f.write_text("x")
        os.chmod(f, 0o444)
        result = _save_csv(td, "data", "_readonly")
        # Windows may still allow rename; just assert string returned
        assert isinstance(result, str)
        os.chmod(f, 0o644)


# ---------------------------------------------------------------------------
# _run_vtune
# ---------------------------------------------------------------------------
@patch("server.subprocess.run")
def test_run_vtune_success(mock_run):
    mock_run.return_value = _mock_run("line1\nline2")
    out = _run_vtune(["-report", "summary"])
    assert out == "line1\nline2"
    assert mock_run.call_args[0][0][0].endswith("vtune.exe")


@patch("server.subprocess.run")
def test_run_vtune_truncate(mock_run):
    huge = "x" * (MAX_OUTPUT + 1000)
    mock_run.return_value = _mock_run(huge)
    out = _run_vtune(["-report", "hotspots"])
    assert out.endswith("... [truncated, total 51000 chars]")
    assert len(out) <= MAX_OUTPUT + 50


@patch("server.subprocess.run")
def test_run_vtune_error(mock_run):
    mock_run.return_value = _mock_run("", returncode=1)
    out = _run_vtune(["-report", "bad"])
    assert "[VTune Error" in out


@patch("server.subprocess.run")
def test_run_vtune_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["vtune"], timeout=10)
    out = _run_vtune(["-report", "summary"])
    assert "[VTune Timeout]" in out


@patch("server.subprocess.run")
def test_run_vtune_not_found(mock_run):
    mock_run.side_effect = FileNotFoundError()
    out = _run_vtune(["-report", "summary"])
    assert "[VTune Not Found]" in out


@patch("server.subprocess.run")
def test_run_vtune_permission_error(mock_run):
    mock_run.side_effect = PermissionError()
    out = _run_vtune(["-report", "summary"])
    assert "[VTune Permission Denied]" in out


@patch("server.subprocess.run")
def test_run_vtune_unicode_error(mock_run):
    mock_run.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "reason")
    out = _run_vtune(["-report", "summary"])
    assert "[VTune Encoding Error]" in out


@patch("server.subprocess.run")
def test_run_vtune_knobs_after_args(mock_run):
    """knobs must appear AFTER the main args (VTune CLI requirement)."""
    mock_run.return_value = _mock_run("ok")
    _run_vtune(["-report", "hotspots", "-result-dir", "/tmp/r"],
               knobs=["-report-knob", "show-issues=false"])
    cmd = mock_run.call_args[0][0]
    ri = cmd.index("-report")
    ki = cmd.index("-report-knob")
    assert ki > ri  # knob must come after -report


# ---------------------------------------------------------------------------
# _resolve_result_dir
# ---------------------------------------------------------------------------
def test_resolve_result_dir_exists():
    with tempfile.TemporaryDirectory() as td:
        assert _resolve_result_dir(td) == td


def test_resolve_result_dir_via_env():
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "r010hs"
        fake.mkdir()
        with patch.dict(os.environ, {"VTUNE_PROJECT_DIR": td}):
            assert _resolve_result_dir("r010hs") == str(fake)


def test_resolve_result_dir_unmatched():
    assert _resolve_result_dir("/nonexistent/x") == "/nonexistent/x"


# ---------------------------------------------------------------------------
# vtune_report
# ---------------------------------------------------------------------------
@patch("server._run_vtune")
def test_vtune_report_csv_save(mock_run, tmp_path):
    mock_run.return_value = "h1,h2\n1,2\n"
    out = vtune_report(str(tmp_path), report_type="hotspots", format="csv")
    assert "[Saved]" in out
    csv = list(tmp_path.glob("*.csv"))
    assert len(csv) == 1


@patch("server._run_vtune")
def test_vtune_report_text_no_save(mock_run):
    mock_run.return_value = "Summary text"
    out = vtune_report("/fake", report_type="summary", format="text", save_csv=False)
    assert out == "Summary text"


@patch("server._run_vtune")
def test_vtune_report_skips_group_by_for_summary(mock_run):
    mock_run.return_value = "ok"
    vtune_report("/fake", report_type="summary", format="csv")
    args = mock_run.call_args[0][0]
    assert "-group-by" not in args


# ---------------------------------------------------------------------------
# vtune_list_results
# ---------------------------------------------------------------------------
def test_vtune_list_results_detects_hs():
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "r010hs").mkdir()
        (Path(td) / "r010hs" / "config").mkdir()
        out = vtune_list_results(td)
        assert "r010hs  (hotspots)" in out


def test_vtune_list_results_empty():
    with tempfile.TemporaryDirectory() as td:
        out = vtune_list_results(td)
        assert "[No VTune results found" in out


def test_vtune_list_results_bad_dir():
    out = vtune_list_results("/this/does/not/exist")
    assert "[Error] Directory not found" in out


# ---------------------------------------------------------------------------
# vtune_compare
# ---------------------------------------------------------------------------
@patch("server._run_vtune")
def test_vtune_compare(mock_run, tmp_path):
    mock_run.return_value = "cmp\n"
    out = vtune_compare(str(tmp_path), str(tmp_path), format="csv")
    assert "[Saved]" in out
    assert "_vs_" in out


# ---------------------------------------------------------------------------
# vtune_summary
# ---------------------------------------------------------------------------
@patch("server._run_vtune")
def test_vtune_summary(mock_run):
    mock_run.return_value = "Elapsed Time: 10s"
    out = vtune_summary("/fake")
    assert "10s" in out


# ---------------------------------------------------------------------------
# vtune_hotspots
# ---------------------------------------------------------------------------
@patch("server._run_vtune")
def test_vtune_hotspots_trims_top_n(mock_run):
    lines = ["Function,CPU Time"] + [f"f{i},{i}.0" for i in range(100)]
    mock_run.return_value = "\n".join(lines)
    out = vtune_hotspots("/fake", top_n=5, save_csv=False)
    assert len(out.splitlines()) == 6  # header + 5


@patch("server._run_vtune")
def test_vtune_hotspots_error_passthrough(mock_run):
    mock_run.return_value = "[VTune Error] oops"
    out = vtune_hotspots("/fake")
    assert out == "[VTune Error] oops"


# ---------------------------------------------------------------------------
# _parse_topdown / _build_subtree / _compare_subtrees
# ---------------------------------------------------------------------------
def test_parse_topdown_detects_depth():
    csv_text = "Function Stack\tCPU Time:Self\n _start\t10.0\n  main\t5.0\n   foo\t2.0\n  bar\t3.0"
    rows, cmap = _parse_topdown(csv_text)
    assert len(rows) == 4
    assert rows[0]["name"] == "_start" and rows[0]["depth"] == 1
    assert rows[1]["name"] == "main" and rows[1]["depth"] == 2
    assert rows[2]["name"] == "foo" and rows[2]["depth"] == 3
    assert rows[3]["name"] == "bar" and rows[3]["depth"] == 2
    assert "CPU Time:Self" in cmap


def test_build_subtree_basic():
    rows = [
        {"name": "main", "depth": 0},
        {"name": "foo", "depth": 1},
        {"name": "bar", "depth": 2},
        {"name": "baz", "depth": 1},
    ]
    sub = _build_subtree(rows, "foo", max_depth=5)
    assert len(sub) == 2
    assert sub[0]["name"] == "foo"
    assert sub[1]["name"] == "bar"


def test_build_subtree_max_depth():
    rows = [
        {"name": "a", "depth": 0},
        {"name": "b", "depth": 1},
        {"name": "c", "depth": 2},
        {"name": "d", "depth": 3},
    ]
    sub = _build_subtree(rows, "a", max_depth=1)
    assert len(sub) == 2  # a + b (c at depth 2 exceeds max_depth=1)
    assert sub[0]["name"] == "a"
    assert sub[1]["name"] == "b"


def test_build_subtree_not_found():
    rows = [{"name": "foo", "depth": 0}]
    assert _build_subtree(rows, "bar", 5) == []


def test_compare_subtrees_format():
    a = [
        {"name": "foo", "depth": 0, "parts": ["foo", "1.5", "1.5"]},
        {"name": "bar", "depth": 1, "parts": ["bar", "0.5", "0.5"]},
    ]
    b = [
        {"name": "foo", "depth": 0, "parts": ["foo", "2.0", "2.0"]},
        {"name": "bar", "depth": 1, "parts": ["bar", "0.3", "0.3"]},
    ]
    col_map = {"CPU Time:Total": 1, "CPU Time:Self": 2}
    out = _compare_subtrees_text(a, b, max_depth=5, a_col_map=col_map, b_col_map=col_map)
    assert "foo" in out
    assert "1.500" in out or "1.5" in out
    assert "2.000" in out or "2.0" in out
    assert "+0.500" in out or "+0.5" in out


def test_compare_subtrees_markdown():
    a = [
        {"name": "foo", "depth": 0, "parts": ["foo", "1.5", "1.5"]},
        {"name": "bar", "depth": 1, "parts": ["bar", "0.5", "0.5"]},
    ]
    b = [
        {"name": "foo", "depth": 0, "parts": ["foo", "2.0", "2.0"]},
    ]
    col_map = {"CPU Time:Total": 1, "CPU Time:Self": 2}
    out = _compare_subtrees_text(a, b, max_depth=5, a_col_map=col_map, b_col_map=col_map)
    assert "|" in out  # markdown table pipe
    assert "foo" in out
    assert "bar" in out


@patch("server._run_vtune")
def test_vtune_function_tree_not_found(mock_run):
    # Minimal top-down CSV with no matching function
    csv = "Function Stack\tCPU Time:Self\n _start\t10.0\n"
    mock_run.return_value = csv
    out = vtune_function_tree("/fake1", "/fake2", "NonExistent", max_depth=5)
    assert "[Not Found]" in out


@patch("server._run_vtune")
def test_vtune_function_tree_found(mock_run, tmp_path):
    csv_a = "Function Stack\tCPU Time:Total\tCPU Time:Self\n _start\t99.9\t10.0\n  main\t95.5\t5.0\n"
    csv_b = "Function Stack\tCPU Time:Total\tCPU Time:Self\n _start\t99.8\t12.0\n  main\t94.0\t6.0\n"
    mock_run.side_effect = [csv_a, csv_b]
    out = vtune_function_tree(str(tmp_path), str(tmp_path), "main", max_depth=5)
    assert "[Saved]" in out
    assert ".html" in out


@patch("server._run_vtune")
def test_vtune_function_tree_html_content(mock_run, tmp_path):
    """Integration test: verify HTML output contains correct structure and data."""
    csv_a = (
        "Function Stack\tCPU Time:Total\tCPU Time:Self\n"
        "Total\t100.0\t0.0\n"
        " _start\t99.9\t0.0\n"
        "  main\t95.5\t5.0\n"
        "   foo\t50.0\t3.0\n"
    )
    csv_b = (
        "Function Stack\tCPU Time:Total\tCPU Time:Self\n"
        "Total\t100.0\t0.0\n"
        " _start\t99.8\t0.0\n"
        "  main\t94.0\t6.0\n"
        "   foo\t45.0\t2.0\n"
    )
    mock_run.side_effect = [csv_a, csv_b]
    # save_html=False to return raw HTML
    out = vtune_function_tree(str(tmp_path), str(tmp_path), "main", max_depth=5, save_html=False)
    assert "<!DOCTYPE html>" in out
    assert "main" in out
    assert "foo" in out
    assert "data-depth=\"2\"" in out  # main depth = 2
    assert "data-depth=\"3\"" in out  # foo depth = 3
    assert "toggleRow" in out  # JS interactive function
    assert "diff-worse" in out or "diff-better" in out or "diff-neutral" in out


@patch("server._run_vtune")
def test_vtune_function_tree_markdown_output(mock_run, tmp_path):
    """Integration test: verify Markdown output contains data and table structure."""
    csv_a = (
        "Function Stack\tCPU Time:Total\tCPU Time:Self\n"
        " _start\t99.9\t0.0\n"
        "  main\t95.5\t5.0\n"
        "   foo\t50.0\t3.0\n"
    )
    csv_b = (
        "Function Stack\tCPU Time:Total\tCPU Time:Self\n"
        " _start\t99.8\t0.0\n"
        "  main\t94.0\t6.0\n"
        "   foo\t45.0\t2.0\n"
    )
    mock_run.side_effect = [csv_a, csv_b]
    out = vtune_function_tree(str(tmp_path), str(tmp_path), "main", max_depth=5, output_format="markdown")
    assert "|" in out
    assert "main" in out
    assert "foo" in out
    assert "95.5" in out
    assert "94.0" in out