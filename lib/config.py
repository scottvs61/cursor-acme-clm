"""Load YAML config with ${ENV_VAR} substitution. CA-agnostic settings."""

import os
import re
from pathlib import Path
from typing import Any

import yaml

_CONFIG: dict[str, Any] | None = None
_CONFIG_PATH: Path | None = None

ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _subst(value: Any) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            key = m.group(1).strip()
            return os.environ.get(key, "")
        return ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _subst(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_subst(v) for v in value]
    return value


def _find_config() -> Path:
    for base in (Path.cwd(), Path(__file__).resolve().parent.parent):
        p = base / "config" / "config.yaml"
        if p.exists():
            return p
    return Path("config/config.yaml")


def load_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load config YAML and substitute ${VAR} with os.environ."""
    global _CONFIG, _CONFIG_PATH
    path = Path(config_path) if config_path else _find_config()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        _CONFIG = {"app": {}, "cas": {"default": ""}, "servicenow": {"enabled": False}}
        return _CONFIG
    _CONFIG_PATH = path
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    _CONFIG = _subst(data)
    return _CONFIG


def get_config() -> dict[str, Any]:
    if _CONFIG is None:
        load_config()
    return _CONFIG or {}


def get_app_config() -> dict[str, Any]:
    return get_config().get("app") or {}


def get_ca_config(ca_name: str | None = None) -> dict[str, Any]:
    cas = get_config().get("cas") or {}
    name = ca_name or cas.get("default") or ""
    return cas.get(name) or cas.get("default") or {}


def get_servicenow_config() -> dict[str, Any]:
    return get_config().get("servicenow") or {}


def get_scep_config() -> dict[str, Any]:
    return get_config().get("scep") or {}
