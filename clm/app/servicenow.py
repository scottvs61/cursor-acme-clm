"""Optional ServiceNow CMDB sync. Config-driven; no-op if disabled or missing config."""

from __future__ import annotations

import json
from typing import Any

import httpx

# Load config from repo root
import sys
from pathlib import Path
_repo = Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from lib.config import get_servicenow_config, load_config

load_config(_repo / "config" / "config.yaml")


def push_certificate_to_cmdb(record: dict[str, Any]) -> None:
    """
    Push a certificate record to ServiceNow CMDB if enabled in config.
    record: dict with id, common_name, product_id, sha256_fingerprint, not_before, not_after, etc.
    """
    cfg = get_servicenow_config()
    if not cfg.get("enabled"):
        return
    instance = (cfg.get("instance") or "").rstrip("/")
    username = cfg.get("username")
    password = cfg.get("password")
    table = cfg.get("table") or "u_certificate_ci"
    mapping = cfg.get("field_mapping") or {}
    if not instance or not username or not password:
        return
    # Map our fields to ServiceNow columns
    payload: dict[str, Any] = {}
    for our_key, sn_key in mapping.items():
        val = record.get(our_key)
        if val is not None:
            payload[sn_key] = str(val) if not hasattr(val, "isoformat") else val.isoformat()
    if not payload:
        payload = {k: record.get(k) for k in ("id", "common_name", "product_id", "sha256_fingerprint", "not_before", "not_after") if record.get(k) is not None}
    url = f"{instance}/api/now/table/{table}"
    auth = (username, password)
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(url, json=payload, auth=auth)
            r.raise_for_status()
    except Exception as e:
        # Log only; do not fail CLM request
        print(f"[ServiceNow] push failed: {e}")
