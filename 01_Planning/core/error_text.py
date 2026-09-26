"""PATCH_621: shared helper so a raw Python exception is never the *only*
thing a human reads in a messagebox.

Project convention is that ValueError is raised deliberately, with a
hand-written, already-human sentence (ja/en chosen at the raise site) -- so
it is returned unchanged here. Any other exception type (KeyError,
AttributeError, TypeError, OSError, json.JSONDecodeError, etc.) usually
means an unhandled internal condition, not a message written for a human
reader, so it is wrapped with a short generic framing sentence and the raw
type/message is kept only as a secondary "detail" line.
"""


def friendly_exception_text(exc, language="ja"):
    if isinstance(exc, ValueError):
        return str(exc)
    ja = (language == "ja")
    type_name = type(exc).__name__
    msg = str(exc) or "(no detail)"
    if ja:
        return (
            "予期しないエラーが発生しました。\n"
            f"詳細: {type_name}: {msg}\n"
            "繰り返し発生する場合は開発者にご連絡ください。"
        )
    return (
        "An unexpected error occurred.\n"
        f"Detail: {type_name}: {msg}\n"
        "If this keeps happening, please contact the developer."
    )
