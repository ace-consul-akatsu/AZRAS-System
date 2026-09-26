from __future__ import annotations
import json
from pathlib import Path
from threading import RLock

_LOCK = RLock()

class UISettings:
    def __init__(self, app_name: str = "AZRAS_Platform"):
        self.path = Path.home() / "Documents" / app_name / "ui_settings.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        with _LOCK:
            self.data[key] = value
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
