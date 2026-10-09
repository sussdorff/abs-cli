"""Behaviour of scripts/dev/preflight.sh, the tracked pre-push preflight.

The script runs the toolchain checker from the repository root and fails the
push when the checker fails. The real checker performs network lookups, so each
test copies the script into a throwaway git repository whose checker is a stub
that records its working directory and exits with a chosen status.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO_ROOT / "scripts" / "dev" / "preflight.sh"
CHECKER_REL = Path(".agents/standards/toolchains/scripts/check_toolchain_versions.py")

STUB_CHECKER = """\
import os
import sys
from pathlib import Path

Path(os.environ["PREFLIGHT_CWD_FILE"]).write_text(os.getcwd())
sys.exit(int(os.environ["PREFLIGHT_STUB_EXIT"]))
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scripts" / "dev").mkdir(parents=True)
    shutil.copy2(PREFLIGHT, root / "scripts" / "dev" / "preflight.sh")
    checker = root / CHECKER_REL
    checker.parent.mkdir(parents=True)
    checker.write_text(STUB_CHECKER)
    (root / "sub" / "dir").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def run_preflight(repo: Path, cwd: Path, stub_exit: int, tmp_path: Path):
    cwd_file = tmp_path / "checker-cwd"
    result = subprocess.run(
        ["bash", str(repo / "scripts" / "dev" / "preflight.sh"), "origin", "git@example:x.git"],
        cwd=cwd,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(tmp_path),
            "PREFLIGHT_CWD_FILE": str(cwd_file),
            "PREFLIGHT_STUB_EXIT": str(stub_exit),
        },
        capture_output=True,
        text=True,
    )
    return result, cwd_file


def test_preflight_is_tracked_executable():
    assert PREFLIGHT.is_file()
    assert PREFLIGHT.stat().st_mode & 0o111


def test_passing_checker_lets_push_through_and_runs_from_repo_root(repo, tmp_path):
    result, cwd_file = run_preflight(repo, repo / "sub" / "dir", 0, tmp_path)

    assert result.returncode == 0, result.stderr
    assert Path(cwd_file.read_text()).resolve() == repo.resolve()


@pytest.mark.parametrize("stub_exit", [1, 2])
def test_failing_checker_fails_the_push(repo, tmp_path, stub_exit):
    result, cwd_file = run_preflight(repo, repo / "sub" / "dir", stub_exit, tmp_path)

    assert cwd_file.exists(), "checker did not run"
    assert result.returncode != 0
