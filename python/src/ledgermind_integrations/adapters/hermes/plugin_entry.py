"""Hermes plugin entry point."""

from __future__ import annotations

from .hook_contracts import HermesPluginContext
from .runtime import HermesPluginRuntime

_runtime: HermesPluginRuntime | None = None


def register(ctx: HermesPluginContext) -> None:
    global _runtime
    if _runtime is not None:
        _runtime.shutdown()
    _runtime = HermesPluginRuntime.from_context(ctx)
    _runtime.register_hooks(ctx)
    _runtime.start()


__all__ = ["register"]
