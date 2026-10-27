"""Load the integration plugin for the configured APP_MODE.

A plugin is a module exposing `register(app, settings)`. It is imported by dotted path from
`INTEGRATION_PLUGINS`, so `shelf` never imports `integrations` statically (import-linter checks).
"""

from __future__ import annotations

import importlib
from typing import Protocol, cast

from fastapi import FastAPI

from shelf.config import INTEGRATION_PLUGINS, Settings


class IntegrationPlugin(Protocol):
    def register(self, app: FastAPI, settings: Settings) -> None: ...


class PluginUnavailableError(RuntimeError):
    pass


def load_integration(
    app: FastAPI, settings: Settings, registry: dict[str, str] | None = None
) -> str | None:
    if settings.app_mode == "standalone":
        return None
    registry = INTEGRATION_PLUGINS if registry is None else registry
    module_path = registry.get(settings.app_mode)
    if module_path is None:
        raise PluginUnavailableError(f"no integration registered for APP_MODE={settings.app_mode}")
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        raise PluginUnavailableError(
            f"APP_MODE={settings.app_mode} needs {module_path}, which is not in this build"
        ) from exc
    cast(IntegrationPlugin, module).register(app, settings)
    return module_path
