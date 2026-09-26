
from __future__ import annotations
import json
from pathlib import Path
from core.canonical_language import SUPPORTED_UI_LANGUAGES, CANONICAL_LANGUAGE

class I18N:
    def __init__(self, root: Path, language: str = CANONICAL_LANGUAGE):
        self.root = Path(root)
        self.language = language if language in SUPPORTED_UI_LANGUAGES else CANONICAL_LANGUAGE
        self.data = {}
        self.load()

    def load(self) -> None:
        path = self.root / "lang" / f"{self.language}.json"
        self.data = json.loads(path.read_text(encoding="utf-8"))

    def set_language(self, language: str) -> None:
        if language not in SUPPORTED_UI_LANGUAGES:
            raise ValueError("Only " + " and ".join(SUPPORTED_UI_LANGUAGES) + " are supported.")
        self.language = language
        self.load()

    def t(self, key: str) -> str:
        return self.data.get(key, key)
