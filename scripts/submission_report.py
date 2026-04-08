#!/usr/bin/env python3
"""Generate a concise submission-readiness report."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def resolve_openenv_cli() -> str:
    executable_name = "openenv.exe" if os.name == "nt" else "openenv"

    resolved = shutil.which("openenv")
    if resolved:
        return resolved

    python_path = Path(sys.executable).resolve()
    candidates = [
        python_path.parent / executable_name,
        python_path.parent / "Scripts" / executable_name,
        python_path.parent.parent / "Scripts" / executable_name,
        python_path.parent / "bin" / executable_name,
        python_path.parent.parent / "bin" / executable_name,
    ]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return executable_name


OPENENV_CLI = resolve_openenv_cli()

CHECKS = [
    ("self_check", [sys.executable, "scripts/self_check.py"]),
    ("unit_tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
    ("openenv_validate", [OPENENV_CLI, "validate"]),
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
    print("https://github.com/Kenxpx/support-ops-env")
    print()
    print("Suggested Hugging Face Space URL:")
    print("https://huggingface.co/spaces/Kenxpx/support-ops-env")

    return 0 if all(success for success, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
