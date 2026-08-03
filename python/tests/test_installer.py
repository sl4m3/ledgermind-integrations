from __future__ import annotations

from pathlib import Path

from ledgermind_integrations.installer import install_hermes


def test_installer_writes_plugin_manifest(tmp_path: Path) -> None:
    target = install_hermes(tmp_path)
    assert target == tmp_path / "ledgermind-hermes" / "plugin.yaml"
    assert "capture_schema_version: 1" in target.read_text(encoding="utf-8")
