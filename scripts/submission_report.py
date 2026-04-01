#!/usr/bin/env python3
"""Generate a concise submission-readiness report."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPENENV_CLI = Path(sys.executable).with_name(
    "openenv.exe" if os.name == "nt" else "openenv"
)

CHECKS = [
    ("self_check", [sys.executable, "scripts/self_check.py"]),
    ("unit_tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
    ("openenv_validate", [str(OPENENV_CLI), "validate"]),
]


def run_check(name: str, command: list[str]) -> tuple[bool, str]:
    executable = command[0]
    if not Path(executable).exists() and shutil.which(executable) is None and executable != sys.executable:
        return False, f"{name}: skipped ({executable} not found on PATH)"

    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout.strip() or completed.stderr.strip() or "(no output)"
    if completed.returncode == 0:
        return True, f"{name}: passed\n{output}"
    return False, f"{name}: failed\n{output}"


def main() -> int:
    results: list[tuple[bool, str]] = []
    for name, command in CHECKS:
        results.append(run_check(name, command))

    print("support_ops_env submission report")
    print("=" * 36)
    for _, message in results:
        print(message)
        print("-" * 36)

    print("Suggested GitHub URL:")
    print("https://github.com/<your-username>/support-ops-env")
    print()
    print("Suggested Hugging Face Space URL:")
    print("https://huggingface.co/spaces/<your-username>/support-ops-env")

    return 0 if all(success for success, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
