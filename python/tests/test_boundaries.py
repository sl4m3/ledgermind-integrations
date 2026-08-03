from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def test_integration_package_does_not_import_core_or_local() -> None:
    forbidden = ("ledgermind_core", "ledgermind_local")
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        assert not any(module == prefix or module.startswith(prefix + ".") for module in modules for prefix in forbidden), path


def test_packaging_declares_no_local_or_core_dependency() -> None:
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert "ledgermind-core" not in pyproject
    assert "ledgermind-local" not in pyproject
