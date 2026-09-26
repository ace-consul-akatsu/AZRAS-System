# -*- coding: utf-8 -*-
"""Read the paragraphs of a .docx with the standard library only (used by check_disclaimer.py)."""
import re, zipfile
from xml.etree import ElementTree as ET
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
def paragraphs(path):
    """[(style, text)] for every non-empty paragraph; <w:br/> becomes '\\n'."""
    root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    out = []
    for p in root.iter(W + "p"):
        st = p.find(f"{W}pPr/{W}pStyle")
        style = st.get(W + "val") if st is not None else ""
        bold = p.find(f".//{W}rPr/{W}b") is not None
        parts = []
        for el in p.iter():
            if el.tag == W + "t": parts.append(el.text or "")
            elif el.tag == W + "br": parts.append("\n")
        text = "".join(parts).strip()
        if text: out.append((style or ("Bold" if bold else ""), text))
    return out
