#!/usr/bin/env python3
"""Static submission sanity checks for support_ops_env.

This script intentionally uses only the Python standard library so it can run
before the full OpenEnv runtime is installed.
"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "README.md",
    "BENCHMARK_SPEC.md",
    "LICENSE",
    "openenv.yaml",
    "pyproject.toml",
    "models.py",
    "client.py",
    "inference.py",
    "tests/test_support_ops_env.py",
    "scripts/submission_report.py",
    "server/app.py",
    "server/tasks.py",
    "server/support_ops_env_environment.py",
]


def load_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def check_required_files() -> list[str]:
    errors: list[str] = []
    for relative_path in REQUIRED_FILES:
        if not (ROOT / relative_path).exists():
            errors.append(f"Missing required file: {relative_path}")
    return errors


def check_openenv_manifest() -> list[str]:
    manifest = load_text("openenv.yaml")
    errors: list[str] = []
    required_snippets = [
        "spec_version: 1",
        "name: support_ops_env",
        "runtime: fastapi",
        "app: server.app:app",
    ]
    for snippet in required_snippets:
        if snippet not in manifest:
            errors.append(f"openenv.yaml missing expected entry: {snippet}")
    return errors


def check_inference_contract() -> list[str]:
    content = load_text("inference.py")
    errors: list[str] = []
    required_terms = [
        "API_BASE_URL",
        "MODEL_NAME",
        "HF_TOKEN",
        "OpenAI",
        "TASK_IDS",
    ]
    for term in required_terms:
        if term not in content:
            errors.append(f"inference.py missing required term: {term}")
    return errors


def extract_task_specs() -> list[tuple[str, list[float]]]:
    tree = ast.parse(load_text("server/tasks.py"))
    specs: list[tuple[str, list[float]]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "TaskSpec":
            continue

        task_id: str | None = None
        milestone_weights: list[float] = []

        for keyword in node.keywords:
            if keyword.arg == "task_id":
                if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    task_id = keyword.value.value
            if keyword.arg == "milestones" and isinstance(keyword.value, ast.Tuple):
                for milestone_node in keyword.value.elts:
                    if (
                        isinstance(milestone_node, ast.Call)
                        and isinstance(milestone_node.func, ast.Name)
                        and milestone_node.func.id == "MilestoneSpec"
                        and len(milestone_node.args) >= 3
                    ):
                        weight_node = milestone_node.args[2]
                        if isinstance(weight_node, ast.Constant) and isinstance(
                            weight_node.value, (int, float)
                        ):
                            milestone_weights.append(float(weight_node.value))

        if task_id is not None:
            specs.append((task_id, milestone_weights))

    return specs


def check_tasks_file() -> list[str]:
    errors: list[str] = []
    task_specs = extract_task_specs()
    task_ids = [task_id for task_id, _ in task_specs]
    if len(task_ids) < 3:
        errors.append("Expected at least 3 tasks in server/tasks.py")

    if len(set(task_ids)) != len(task_ids):
        errors.append("Task ids should be unique")

    if not task_specs:
        errors.append("No milestone weights found in server/tasks.py")
        return errors

    for task_id, weights in task_specs:
        if not weights:
            errors.append(f"Task '{task_id}' has no milestone weights")
            continue
        total = round(sum(weights), 6)
        if abs(total - 1.0) > 0.001:
            errors.append(
                f"Milestone weights for task '{task_id}' sum to {total}, expected 1.0"
            )
    return errors


def main() -> int:
    checks = [
        check_required_files(),
        check_openenv_manifest(),
        check_inference_contract(),
        check_tasks_file(),
    ]
    errors = [error for group in checks for error in group]

    if errors:
        print("support_ops_env self-check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("support_ops_env self-check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
