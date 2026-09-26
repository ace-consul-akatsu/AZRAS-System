from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_PRODUCT_NAME = "AZRAS Evaluation"
# Fallback only when VERSION.json cannot be read; dev_checks/version_consistency_self_check.py
# keeps it equal to VERSION.json "version".
DEFAULT_VERSION = "2.2.0"
DEFAULT_SCHEMA_VERSION = "3.0"


def _application_root() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            return Path(bundle_root).resolve()
    return Path(__file__).resolve().parent.parent


def _load_version_data() -> dict[str, Any]:
    path = _application_root() / "VERSION.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {}


_VERSION_DATA = _load_version_data()
PRODUCT_NAME = str(_VERSION_DATA.get("product_name") or DEFAULT_PRODUCT_NAME)
VERSION = str(_VERSION_DATA.get("version") or DEFAULT_VERSION)
SCHEMA_VERSION = str(_VERSION_DATA.get("schema_version") or DEFAULT_SCHEMA_VERSION)
DISPLAY_NAME = f"{PRODUCT_NAME} Version {VERSION}"
DISPLAY_NAME_SHORT = f"{PRODUCT_NAME} v{VERSION}"
EXECUTABLE_NAME = str(_VERSION_DATA.get("executable_name") or "AZRAS_Evaluation")
RELEASE_CHANNEL = str(_VERSION_DATA.get("release_channel") or "development")


def version_metadata() -> dict[str, str]:
    return {
        "product_name": PRODUCT_NAME,
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "display_name": DISPLAY_NAME,
        "executable_name": EXECUTABLE_NAME,
        "release_channel": RELEASE_CHANNEL,
    }
