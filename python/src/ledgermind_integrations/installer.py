"""Install the complete LedgerMind Hermes plugin directory."""

from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

_PLUGIN_INIT = 'from ledgermind_integrations.adapters.hermes.plugin_entry import register\n\n__all__ = ["register"]\n'


def _write_private(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            temporary.chmod(0o600)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _default_config() -> dict[str, object]:
    hermes_home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
    return {
        "endpoint": "http://127.0.0.1:8765",
        "token_file": "~/.ledgermind/local/server.token",
        "memory_space_id": "project-main",
        "processing_profile_id": "default",
        "source_instance_id": f"hermes-{uuid4().hex}",
        "profile_id": "default",
        "state_db_path": str(hermes_home / "state.db"),
        "spool_dir": "~/.ledgermind/integrations/hermes",
    }


def _plugin_root(destination: str | Path | None) -> Path:
    plugin_root = (
        Path(destination).expanduser()
        if destination is not None
        else Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "plugins"
    )
    return plugin_root / "ledgermind-hermes"


def install_hermes(destination: str | Path | None = None) -> Path:
    root = _plugin_root(destination)
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        source = files("ledgermind_integrations.adapters.hermes").joinpath("plugin.yaml")
        plugin_yaml = root / "plugin.yaml"
        with source.open("rb") as source_handle:
            _write_private(plugin_yaml, source_handle.read())
        _write_private(root / "__init__.py", _PLUGIN_INIT.encode("utf-8"))
        config = (
            json.dumps(_default_config(), ensure_ascii=False, indent=2, sort_keys=True).encode(
                "utf-8"
            )
            + b"\n"
        )
        _write_private(root / "config.json", config)
    except OSError as exc:
        raise RuntimeError("cannot install private Hermes plugin files") from exc
    return plugin_yaml


def uninstall_hermes(destination: str | Path | None = None) -> bool:
    root = _plugin_root(destination)
    if not root.exists():
        return False
    if not root.is_dir():
        raise RuntimeError(f"Hermes plugin path is not a directory: {root}")
    removed = False
    for name in ("plugin.yaml", "__init__.py", "config.json"):
        path = root / name
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RuntimeError("cannot uninstall private Hermes plugin files") from exc
        removed = True
    try:
        root.rmdir()
    except OSError:
        pass
    return removed


__all__ = ["install_hermes", "uninstall_hermes"]
