
from __future__ import annotations
import json
from pathlib import Path

LANGUAGE_ORDER = ("en", "ja")
LANGUAGE_LABELS = {"en": "English", "ja": "日本語"}
LANGUAGE_OPTIONS = tuple(LANGUAGE_LABELS[code] for code in LANGUAGE_ORDER)

class I18N:
    def __init__(self, root: Path, language: str = "en"):
        self.root = Path(root)
        self.language = language if language in LANGUAGE_ORDER else "en"
        self.data = {}
        self.load()

    def load(self) -> None:
        path = self.root / "lang" / f"{self.language}.json"
        self.data = json.loads(path.read_text(encoding="utf-8"))

    def set_language(self, language: str) -> None:
        if language not in LANGUAGE_ORDER:
            raise ValueError("Only " + " and ".join(LANGUAGE_ORDER) + " are supported.")
        self.language = language
        self.load()

    def t(self, key: str) -> str:
        return self.data.get(key, key)
