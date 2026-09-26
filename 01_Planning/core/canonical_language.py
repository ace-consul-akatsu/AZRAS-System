from __future__ import annotations

CANONICAL_LANGUAGE = "en"
SUPPORTED_UI_LANGUAGES = ("en", "ja")
LANGUAGE_LABELS = {
    "en": "English",
    "ja": "日本語",
}
# Display order is a product-wide invariant: English first; append future languages below.
LANGUAGE_OPTIONS = tuple(LANGUAGE_LABELS[code] for code in SUPPORTED_UI_LANGUAGES)

def normalize_ui_language(language: str | None) -> str:
    """Return a supported UI language; English is the canonical fallback."""
    value = str(language or "").strip().lower()
    if value in {"ja", "jp", "japanese", "日本語"} or value.startswith("ja-") or value.startswith("ja_"):
        return "ja"
    return CANONICAL_LANGUAGE

def language_label(language: str | None) -> str:
    return LANGUAGE_LABELS[normalize_ui_language(language)]
