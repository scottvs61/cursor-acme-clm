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


def get_subject_defaults() -> dict[str, str]:
    """Return pre-defined TLS Subject DN fields (C, ST, L, O) for generated CSRs. CN and OU come from enrollment."""
    return get_config().get("subject_defaults") or {}


def get_clm_ingest_secret() -> str:
    """
    Shared secret for ACME/SCEP to POST issued certs to CLM without a user JWT.
    Same value must be in config for CLM and services that call /api/events/issued.
    Read from app.clm_ingest_secret, top-level clm_ingest_secret, or env CLM_INGEST_SECRET.
    """
    cfg = get_config()
    v = (
        get_app_config().get("clm_ingest_secret")
        or cfg.get("clm_ingest_secret")
        or os.environ.get("CLM_INGEST_SECRET")
        or ""
    )
    return str(v).strip()


def get_auth_config() -> dict[str, Any]:
    """Return auth section: api_keys (list of {key, role}), acme_required_api_key, scep_required_api_key."""
    return get_config().get("auth") or {}


def get_api_keys() -> list[dict[str, str]]:
    """List of {key: str, role: "admin"|"user"}. If non-empty, CLM API requires X-API-Key and enforces roles."""
    raw = get_auth_config().get("api_keys") or []
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and item.get("key") and item.get("role") in ("admin", "user"):
            out.append({"key": str(item["key"]).strip(), "role": item["role"]})
    return out


def get_acme_required_api_key() -> str | None:
    """If set, ACME new-account/new-order/finalize require X-API-Key to match this value."""
    v = get_auth_config().get("acme_required_api_key")
    return str(v).strip() or None if v else None


def get_scep_required_api_key() -> str | None:
    """If set, SCEP PKIOperation requires X-API-Key to match this value."""
    v = get_auth_config().get("scep_required_api_key")
    return str(v).strip() or None if v else None
