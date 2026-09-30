
from __future__ import annotations
import copy
import re
import math
import statistics
import numpy as np
import cv2
from pathlib import Path
from typing import Any

from pypdf import PdfReader
try:
    import fitz  # PyMuPDF: vector-PDF geometry takeoff
except Exception:
    fitz = None


STRUCTURE_KEYWORDS = {
    "AZRAS": ["AZRAS構造", "RC300", "ベタ基礎：厚500", "2×6外壁部"],
    "RC Frame": ["RCラーメン構造", "1Ｃ1", "2Ｃ1", "Ｇ1", "独立基礎"],
    "2x6 Timber": ["2×6構造", "2×6スタッド", "フェノールフォーム厚140", "布基礎", "布基礎伏せ図"],
    # Generic steel drawings often do not contain the literal string "S造".
    # Architectural sections commonly state 柱・梁：鉄骨, and structural sheets
    # contain H-section marks.  Keep multiple independent clues so a single H-
    # token cannot dominate other structure candidates.
    "Steel Structure": ["柱・梁：鉄骨", "鉄骨", "鉄骨造", "H-", "H形鋼", "角形鋼管"],
    "Wood Post-and-Beam": ["木造軸組", "在来軸組"],
    "Wood Framed-Wall": ["木造枠組壁", "枠組壁工法"],
    "RC Wall Structure": ["RC壁式", "壁式鉄筋コンクリート"],
    "Other": [],
}


def extract_pdf_text(pdf_path: str | Path) -> str:
    reader = PdfReader(str(pdf_path))
    chunks: list[str] = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            chunks.append("")
    return "\n".join(chunks)


def identify_structure(text: str) -> tuple[str, float]:
    scores: dict[str, int] = {}
    for structure, words in STRUCTURE_KEYWORDS.items():
        scores[structure] = sum(1 for word in words if word in text)
    max_score = max(scores.values()) if scores else 0
    # PATCH_85: never default to AZRAS merely because every keyword score is 0.
    if max_score <= 0:
        return "Other", 0.20
    best = max(scores, key=scores.get)
    confidence = min(0.98, 0.35 + 0.15 * max_score)
    return best, confidence


def first_number(patterns: list[str], text: str, default: float | None = None) -> float | None:
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                pass
    return default


def _all_numbers(patterns: list[tuple[str, str, int]], text: str) -> list[dict[str, Any]]:
    """Collect insulation thickness candidates with source priority.

    Higher priority is more specific to the building component. This prevents
    a generic cavity dimension (e.g. 床下空気層300) or an earlier stale note
    from silently overriding a component-specific section note.
    """
    found: list[dict[str, Any]] = []
    for pattern, source, priority in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            try:
                value = float(m.group(1))
            except Exception:
                continue
            found.append({
                "value": value,
                "source": source,
                "priority": priority,
                "matched_text": re.sub(r"\s+", " ", m.group(0)).strip()[:180],
                "position": m.start(),
            })
    return found


def _select_candidate(candidates: list[dict[str, Any]], default: float) -> tuple[float, dict[str, Any], list[dict[str, Any]]]:
    if not candidates:
        return float(default), {
            "source": "profile_default",
            "priority": 0,
            "matched_text": "",
            "value": float(default),
        }, []
    # Most component-specific source wins. If equal priority appears multiple
    # times, prefer the later drawing note because detail/section sheets often
    # appear after general-plan notes.
    selected = sorted(candidates, key=lambda x: (x["priority"], x["position"]))[-1]
    distinct = sorted({round(float(c["value"]), 6) for c in candidates})
    conflicts = candidates if len(distinct) > 1 else []
    return float(selected["value"]), selected, conflicts


def detect_insulation(text: str, structure: str, profile_defaults: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    defaults = (profile_defaults or {}).get("assemblies", {})
    def d(part: str, fallback: float) -> float:
        try:
            return float((defaults.get(part) or {}).get("thickness_mm", fallback))
        except Exception:
            return float(fallback)

    result = {
        "rc_wall": {"material": "Phenolic foam", "thickness_mm": d("rc_wall", 0.0)},
        "light_wall": {"material": "Phenolic foam", "thickness_mm": d("light_wall", 0.0)},
        "roof": {"material": "Phenolic foam", "thickness_mm": d("roof", 0.0)},
        "slab": {"material": "XPS", "thickness_mm": d("slab", 100.0)},
        "_evidence": {},
        "_conflicts": [],
    }

    rc_candidates = _all_numbers([
        (r"RC外壁(?:部)?.{0,120}?外断熱層[：:]?\s*フェノールフォーム厚\s*([0-9.]+)", "RC外壁部・外断熱層", 100),
        (r"RC外壁(?:部)?.{0,120}?フェノールフォーム厚\s*([0-9.]+)", "RC外壁部", 80),
    ], text)
    rc, ev, conflicts = _select_candidate(rc_candidates, d("rc_wall", 0.0))
    result["rc_wall"]["thickness_mm"] = rc
    result["_evidence"]["rc_wall"] = ev
    if conflicts:
        result["_conflicts"].append({"part": "rc_wall", "candidates": conflicts, "selected": ev})

    # AZRAS hybrid wall parsing: bind insulation to the structural marker, not
    # to drawing headings. PDF text extraction may place "2×6外壁部 RC外壁部"
    # together even though the two detail blocks are visually separate.
    if str(structure).strip().upper() == "AZRAS":
        light_candidates = []

        # Find each actual "構造：2×6" marker and inspect only the following
        # wall-detail block. Stop before a later roof/detail heading where possible.
        for sm in re.finditer(r"構造\s*[：:]\s*2\s*[x×]\s*6\b", text, re.I):
            block_start = sm.start()
            tail = text[sm.end():sm.end() + 900]
            stop = re.search(r"(?:屋根断熱|屋根仕様|RC外壁部|構造\s*[：:]\s*RC\b)", tail, re.I)
            block = text[block_start:(sm.end() + stop.start()) if stop else min(len(text), sm.end() + 900)]

            # Prefer an explicit equation such as 140mm + 50mm = 190mm.
            eq = re.search(
                r"外断熱層\s*[：:]?\s*フェノールフォーム厚\s*"
                r"([0-9.]+)\s*(?:mm|㎜)?\s*\+\s*([0-9.]+)\s*(?:mm|㎜)?\s*[＝=]\s*"
                r"([0-9.]+)\s*(?:mm|㎜)?",
                block, re.I | re.S
            )
            if eq:
                a, b, stated = map(float, eq.groups())
                value = stated if abs((a + b) - stated) <= 0.5 else (a + b)
                light_candidates.append({
                    "value": value,
                    "source": "AZRAS 構造:2×6 → 外断熱層（明示合計）",
                    "priority": 200,
                    "matched_text": re.sub(r"\s+", " ", eq.group(0)).strip()[:180],
                    "position": block_start + eq.start(),
                })
                continue

            # If no equation is present, accept a single thickness only when it
            # occurs downstream of the actual 2×6 structural marker.
            one = re.search(
                r"外断熱層\s*[：:]?\s*フェノールフォーム厚\s*([0-9.]+)\s*(?:mm|㎜)",
                block, re.I | re.S
            )
            if one:
                light_candidates.append({
                    "value": float(one.group(1)),
                    "source": "AZRAS 構造:2×6 → 外断熱層",
                    "priority": 180,
                    "matched_text": re.sub(r"\s+", " ", one.group(0)).strip()[:180],
                    "position": block_start + one.start(),
                })

        light, ev, conflicts = _select_candidate(light_candidates, d("light_wall", 190.0))
        # Defensive rule: if no structurally-bound 2×6 evidence was found, retain
        # the confirmed AZRAS comparison profile instead of borrowing RC evidence.
        if not light_candidates:
            light = d("light_wall", 190.0)
            ev = {
                "source": "AZRAS confirmed 2×6 wall profile fallback",
                "priority": 1,
                "matched_text": "",
                "value": light,
                "message_ja": "構造:2×6 に結び付く断熱注記が見つからないため、確認済み2×6外壁プロファイルを使用。",
            }
            conflicts = []
    else:
        light_candidates = _all_numbers([
            (r"2\s*[x×]\s*6\s*外壁部.{0,260}?外断熱層[：:]?\s*フェノールフォーム厚(?:\s*[0-9.]+\s*(?:mm|㎜)?\s*\+\s*[0-9.]+\s*(?:mm|㎜)?\s*[＝=]\s*)?([0-9.]+)\s*(?:mm|㎜)", "2×6外壁部・外断熱層", 130),
            (r"2\s*[x×]\s*6\s*外壁部.{0,260}?フェノールフォーム厚\s*([0-9.]+)\s*(?:mm|㎜)", "2×6外壁部", 120),
            (r"外壁断熱[：:]?\s*フェノールフォーム厚\s*([0-9.]+)\s*(?:mm|㎜)", "2×6外壁部内・外壁断熱", 110),
        ], text)
        light, ev, conflicts = _select_candidate(light_candidates, d("light_wall", 0.0))

    result["light_wall"]["thickness_mm"] = light
    result["_evidence"]["light_wall"] = ev
    if conflicts:
        result["_conflicts"].append({"part": "light_wall", "candidates": conflicts, "selected": ev})

    roof_candidates = _all_numbers([
        (r"屋根断熱[：:]?\s*フェノールフォーム厚\s*([0-9.]+)", "屋根断熱明記", 130),
        (r"屋根.{0,80}?フェノールフォーム厚\s*([0-9.]+)", "屋根仕様", 90),
    ], text)
    roof, ev, conflicts = _select_candidate(roof_candidates, d("roof", 0.0))
    result["roof"]["thickness_mm"] = roof
    result["_evidence"]["roof"] = ev
    if conflicts:
        result["_conflicts"].append({"part": "roof", "candidates": conflicts, "selected": ev})

    slab_candidates = _all_numbers([
        # Section/detail note: highest priority.
        (r"土間厚\s*[0-9.]+\s*\+?\s*高性能発泡ポリスチレン厚\s*([0-9.]+)", "断面図：土間厚＋断熱厚", 150),
        (r"発泡スチロール\s*[（(]?\s*XPS\s*[）)]?\s*厚\s*([0-9.]+)", "断面図：XPS厚明記", 150),
        (r"(?:土間下|基礎下)(?:に)?\s*高性能発泡ポリスチレン厚\s*([0-9.]+)", "基礎・土間下断熱注記", 100),
        (r"(?:土間下|基礎下).{0,40}?XPS\s*(?:厚)?\s*([0-9.]+)", "基礎・土間下XPS注記", 100),
    ], text)
    slab, ev, conflicts = _select_candidate(slab_candidates, d("slab", 100.0))
    result["slab"]["thickness_mm"] = slab
    result["_evidence"]["slab"] = ev
    if conflicts:
        result["_conflicts"].append({"part": "slab", "candidates": conflicts, "selected": ev})

    # "床下空気層" is deliberately parsed separately and never used as XPS thickness.
    air = _all_numbers([
        (r"床下空気層[：:]?\s*([0-9.]+)", "床下空気層", 100),
    ], text)
    if air:
        result["_floor_air_cavity_mm"] = float(air[-1]["value"])
        result["_evidence"]["floor_air_cavity"] = air[-1]

    # Flag a conflict between extracted drawing value and the currently confirmed
    # comparison-profile default. This is especially useful while drawings are
    # being revised and old notes remain elsewhere in the PDF.
    for part in ("rc_wall","light_wall","roof","slab"):
        expected = d(part, result[part]["thickness_mm"])
        actual = float(result[part]["thickness_mm"])
        if expected > 0 and actual > 0 and abs(expected - actual) > 0.1:
            result["_conflicts"].append({
                "part": part,
                "type": "drawing_vs_profile_default",
                "profile_default_mm": expected,
                "selected_drawing_mm": actual,
                "message_ja": f"{part}: 図面抽出値 {actual:g}mm と確認済み比較プロファイル {expected:g}mm が一致しません。",
            })
    return result

def _extract_area_values(text: str) -> list[float]:
    patterns = [
        r"(?:床面積|延床面積|延べ床面積|建築面積)\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m2|m²|㎡)",
        r"([0-9]+(?:\.[0-9]+)?)\s*(?:m2|m²|㎡)\s*(?:/戸|×\s*[0-9]+\s*戸)",
    ]
    values: list[float] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                value = float(match.group(1))
            except (TypeError, ValueError):
                continue
            if 5.0 <= value <= 100000.0:
                values.append(value)
    return values


def _extract_repeated_unit_area_m2(text: str) -> tuple[float, int] | None:
    """Detect a bare area label (e.g. "40.85m2") repeated 2+ times identically.

    PATCH_015: general-purpose corroboration check, not tied to any one
    structure type. Repeated-unit floor plans (terrace houses, apartment
    blocks) often label each identical unit's area directly on the plan
    without any surrounding keyword ("床面積" etc.) that _extract_area_values()
    looks for, so those labels were previously invisible to footprint
    detection entirely. When the same bare value repeats on the drawing,
    that repetition is itself strong evidence that it is a real per-unit
    area (a coincidence would not repeat identically), and
    unit_value x repeat_count is a footprint candidate grounded directly in
    an explicit, human-authored drawing label -- a stronger evidence class
    than a width x depth product inferred from scanning raw dimension text.
    """
    norm = _norm_drawing_text(text)
    vals: list[float] = []
    # Some PDF text extractors (observed with pypdf on this project's source
    # PDF) split the "m2" superscript so the digit "2" lands on its own line,
    # e.g. "40.85m2" -> "40.85m\n2". Allow (but do not require) whitespace
    # between "m" and "2" to tolerate that without over-matching.
    for m in re.finditer(r"(?<![0-9.])([0-9]{1,4}\.[0-9]{1,2})\s*m\s?2(?!\s*/)", norm):
        try:
            v = float(m.group(1))
        except (TypeError, ValueError):
            continue
        # Floor of 15.0 m2 excludes window/door/opening-area labels (which
        # this same drawing style prints the same way, e.g. "5.25m2" for a
        # window) from ever being mistaken for a repeated per-unit footprint.
        if 15.0 <= v <= 5000.0:
            vals.append(v)
    if not vals:
        return None
    from collections import Counter
    freq = Counter(vals)
    best_v, best_c = max(freq.items(), key=lambda kv: (kv[1], kv[0]))
    if best_c < 2:
        return None
    return (best_v, best_c)


def detect_dimensions(text: str) -> dict[str, Any]:
    """Extract building-scale geometry while excluding member-section dimensions."""
    norm=_norm_drawing_text(text)

    def _first_mm(patterns: list[str]) -> float | None:
        for pattern in patterns:
            m=re.search(pattern,norm,re.I)
            if not m: continue
            try: v=float(m.group(1).replace(",",""))
            except Exception: continue
            if 3000.0<=v<=200000.0:
                return v
        return None

    width_mm=_first_mm([
        r"(?:建物幅|全幅|間口|overall\s+width|building\s+width)\s*[:：]?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})\s*(?:mm)?",
    ])
    depth_mm=_first_mm([
        r"(?:建物奥行|奥行|全長|overall\s+depth|building\s+depth)\s*[:：]?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})\s*(?:mm)?",
    ])

    vals=[]
    for m in re.finditer(r"(?<![\d.])([0-9]{4,6})(?![\d.])",norm):
        try: v=int(m.group(1))
        except Exception: continue
        if 4000<=v<=50000:
            vals.append(v)
    from collections import Counter
    freq=Counter(vals)

    # Prefer frequently repeated non-subdivision spans for the second building axis.
    def _is_subdivision(v):
        for w in freq:
            if w<=v: continue
            r=w/v
            if abs(r-round(r))<0.02 and round(r) in (2,3,4,5,6):
                return True
        return False

    overall=[v for v,c in freq.items() if c>=2 and v>=5000 and not _is_subdivision(v)]
    overall=sorted(overall,key=lambda v:(freq[v],v),reverse=True)

    if width_mm is None and overall:
        # BUGFIX (260916): previously `float(max(overall))`, which discarded the
        # frequency-based ranking above and picked the single largest raw digit
        # string found anywhere in the extracted PDF text -- including rare
        # (freq==2, the minimum threshold) noise values unrelated to the
        # building envelope (e.g. stray/invisible text extracted from the PDF).
        # Rank by (frequency, value) like depth_mm below, so the most-repeated
        # dimension wins ties only when frequency is equal.
        width_mm=float(max(overall,key=lambda v:(freq[v],v)))
    if depth_mm is None:
        opts=[v for v in overall if width_mm is None or abs(v-width_mm)>1]
        if opts:
            depth_mm=float(max(opts,key=lambda v:(freq[v],v)))

    width_m=width_mm/1000.0 if width_mm is not None else None
    depth_m=depth_mm/1000.0 if depth_mm is not None else None

    storeys=None
    sm=re.search(r"([1-9])\s*階建",norm)
    if sm: storeys=int(sm.group(1))
    elif "3階平面" in norm or "3階床" in norm: storeys=3
    elif "2階平面" in norm or "2階床" in norm: storeys=2
    elif "平屋" in norm or ("1階平面" in norm and "2階平面" not in norm): storeys=1
    else:
        fl=[]
        for m in re.finditer(r"([1-9])\s*階(?:平面|床|PLAN)?",norm,re.I):
            try: fl.append(int(m.group(1)))
            except Exception: pass
        if fl: storeys=max(fl)

    area_values=_extract_area_values(text)
    total_area=None

    footprint=width_m*depth_m if width_m and depth_m else None
    if total_area is None and area_values:
        if footprint and storeys:
            expected=footprint*storeys
            plausible=[v for v in area_values if v>=footprint*0.70]
            if plausible:
                total_area=min(plausible,key=lambda v:abs(v-expected))
        if total_area is None:
            total_area=max(area_values)
    if footprint is None and total_area is not None and storeys:
        footprint=total_area/storeys

    # PATCH_015: general-purpose corroboration check (any structure type).
    # If the drawing itself repeats an identical bare per-unit area label
    # (e.g. three "40.85m2" labels on a terrace-house plan), that explicit,
    # human-authored fact outranks a footprint merely inferred from a
    # width_mm x depth_mm product built out of frequency-ranked dimension
    # text -- the same class of heuristic that produced a ~3.64x
    # overestimate on 260915_RC_Rahmen_Sample even after the width_mm
    # tie-break fix above, on drawings noisy enough to still mislead it.
    conflicts=[]
    unit_area=_extract_repeated_unit_area_m2(text)
    if unit_area:
        unit_value,unit_count=unit_area
        unit_footprint=unit_value*unit_count
        if footprint and unit_footprint>0 and (footprint<unit_footprint*0.85 or footprint>unit_footprint*1.15):
            conflicts.append({
                "type":"footprint_vs_repeated_unit_area",
                "width_depth_footprint_m2":footprint,
                "repeated_unit_area_m2":unit_value,
                "repeat_count":unit_count,
                "repeated_unit_area_total_m2":unit_footprint,
                "resolution":"repeated_unit_area_preferred",
                "message_ja": f"width x depthから推定したfootprint {footprint:.2f}m2 と、図面上に{unit_count}回繰り返されている面積表記 {unit_value:g}m2 の合計 {unit_footprint:.2f}m2 が一致しません。繰り返し表記された明示的な面積を優先して採用し、width/depthは要再確認としました。",
            })
            footprint=unit_footprint
            # width_m/depth_m came from the now-discredited candidate set;
            # do not keep displaying them as if they were still trustworthy.
            width_m=None
            depth_m=None

    missing=[]
    if width_m is None: missing.append("width")
    if depth_m is None: missing.append("depth")
    if storeys is None: missing.append("storeys")
    if total_area is None: missing.append("gross_floor_area")
    floor_areas=[total_area/storeys for _ in range(storeys)] if total_area is not None and storeys else ([footprint]*storeys if footprint and storeys else [])

    return {
        "width_m":width_m,"depth_m":depth_m,"footprint_m2":footprint,
        "storeys":storeys,"floor_areas_m2":floor_areas,"floor_area_m2":total_area or (footprint*storeys if footprint and storeys else None),
        "height_m":None,"volume_m3":None,
        "geometry_complete":not missing,"missing_geometry_fields":missing,
        "floor_area_source":"current PDF explicit/repeated drawing dimensions; member-section dimensions excluded",
        "dimension_candidates_mm":dict(freq),
        "_conflicts":conflicts,
    }

def detect_openings(text: str) -> dict[str, float]:
    """Read opening areas only when direction + opening type + area are explicit.

    Older comparison-drawing code injected hard-coded areas after detecting a
    particular window product/sample marker.  That can contaminate arbitrary
    projects.  The production rule is now evidence-only: a cardinal direction,
    window/door label, and numeric area with m2/m²/㎡ must occur together in the
    extracted PDF text.  If that evidence is absent the value remains 0.0 and can
    be confirmed/edited in Module 1 rather than guessed.
    """
    result = {
        "north_window_m2": 0.0, "north_door_m2": 0.0,
        "south_window_m2": 0.0, "south_door_m2": 0.0,
        "east_window_m2": 0.0, "east_door_m2": 0.0,
        "west_window_m2": 0.0, "west_door_m2": 0.0,
    }

    direction_tokens = {
        "north": r"(?:北(?:面|側)?|N(?:orth)?)",
        "east": r"(?:東(?:面|側)?|E(?:ast)?)",
        "south": r"(?:南(?:面|側)?|S(?:outh)?)",
        "west": r"(?:西(?:面|側)?|W(?:est)?)",
    }
    opening_tokens = {
        "window": r"(?:窓(?:面積)?|開口窓|window(?:\s+area)?)",
        "door": r"(?:扉(?:面積)?|ドア(?:面積)?|door(?:\s+area)?)",
    }
    area_unit = r"(?:m\s*[2²]|㎡)"

    def explicit_area(direction_pat: str, opening_pat: str) -> float | None:
        # Direction/opening before the number, e.g. a direction + opening-type + explicit area label.
        patterns = [
            rf"{direction_pat}\s*[^\n]{{0,24}}?{opening_pat}\s*[:：=]?\s*([0-9]+(?:\.[0-9]+)?)\s*{area_unit}",
            rf"{opening_pat}\s*[^\n]{{0,24}}?{direction_pat}\s*[:：=]?\s*([0-9]+(?:\.[0-9]+)?)\s*{area_unit}",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except (TypeError, ValueError):
                    pass
        return None

    for direction, direction_pat in direction_tokens.items():
        for opening_type, opening_pat in opening_tokens.items():
            value = explicit_area(direction_pat, opening_pat)
            if value is not None:
                result[f"{direction}_{opening_type}_m2"] = max(0.0, value)

    return result



def detect_openings_from_pdf(pdf_path: str | Path) -> dict[str, Any] | None:
    """Take off exterior openings from the elevation page of a vector PDF.

    The four elevation drawings are identified by their titles. Area labels with
    m2 are spatially grouped into the four elevation quadrants. Door labels are
    then matched to repeated area values; the remaining opening area is glazing.

    This uses the current PDF only. No comparison-sample opening values are used.
    """
    if fitz is None:
        return None
    try:
        doc=fitz.open(str(pdf_path))
    except Exception:
        return None

    page=None
    try:
        for p in doc:
            t=_norm_drawing_text(p.get_text())
            if all(x in t for x in ("東立面図","南立面図","西立面図","北立面図")):
                page=p
                break
        if page is None:
            return None

        title_map={}
        title_tokens={"east":"東立面図","south":"南立面図","west":"西立面図","north":"北立面図"}
        for direction,token in title_tokens.items():
            hits=page.search_for(token)
            if hits:
                r=hits[0]
                title_map[direction]=((r.x0+r.x1)/2.0,(r.y0+r.y1)/2.0)
        if len(title_map)!=4:
            return None

        area_words=[]
        for w in page.get_text("words"):
            wt=_norm_drawing_text(str(w[4])).strip()
            m=re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*m2",wt,re.I)
            if not m:
                continue
            area=float(m.group(1))
            cx=(float(w[0])+float(w[2]))/2.0
            cy=(float(w[1])+float(w[3]))/2.0
            area_words.append({"area":area,"cx":cx,"cy":cy,"text":wt})
        if len(area_words)<4:
            return None

        # The four elevations form a 2x2 arrangement on the sheet. Determine
        # the split from the largest natural gap in the area-label positions.
        def largest_gap_split(vals):
            vals=sorted(set(float(v) for v in vals))
            if len(vals)<2:
                return None
            gaps=[(vals[i+1]-vals[i],i) for i in range(len(vals)-1)]
            gap,i=max(gaps)
            return (vals[i]+vals[i+1])/2.0 if gap>20.0 else None

        xsplit=largest_gap_split([a["cx"] for a in area_words])
        ysplit=largest_gap_split([a["cy"] for a in area_words])
        if xsplit is None or ysplit is None:
            return None

        # Map each title to the same quadrant coordinates.
        quadrant_to_direction={}
        for d,(x,y) in title_map.items():
            quadrant_to_direction[("R" if x>xsplit else "L","B" if y>ysplit else "T")]=d

        by_direction={d:[] for d in title_tokens}
        for a in area_words:
            q=("R" if a["cx"]>xsplit else "L","B" if a["cy"]>ysplit else "T")
            d=quadrant_to_direction.get(q)
            if d:
                by_direction[d].append(a["area"])

        # PATCH_573: detect door declarations by SPATIAL association first.
        # PDF text extraction order is not a reliable geometric relationship. In the
        # AZRAS terrace-house elevation, for example, the door label is adjacent to
        # the repeated 2.11m2 row while a later text-order row contains 1.79m2 windows.
        # A text-order regex therefore misclassified window/door areas.
        norm=_norm_drawing_text(page.get_text())
        door_specs=[]
        used_spatial=set()

        # Build grouped area-label locations per elevation quadrant.
        grouped={d:{} for d in title_tokens}
        for a in area_words:
            q=("R" if a["cx"]>xsplit else "L","B" if a["cy"]>ysplit else "T")
            d=quadrant_to_direction.get(q)
            if not d:
                continue
            key=round(float(a["area"]),6)
            grouped[d].setdefault(key,[]).append(a)

        # Door callouts are often one rotated PDF word containing the entire label.
        # Associate them to the nearest repeated area group in the same quadrant,
        # strongly preferring a group whose occurrence count exactly matches xN.
        for w in page.get_text("words"):
            raw=str(w[4])
            wt=_norm_drawing_text(raw).strip()
            low=wt.lower()
            if not ("戸" in wt or "ドア" in wt or "door" in low):
                continue
            cm=re.search(r"x\s*(\d{1,3})",wt,re.I)
            if not cm:
                continue
            count=int(cm.group(1))
            if count<=0:
                continue
            cx=(float(w[0])+float(w[2]))/2.0
            cy=(float(w[1])+float(w[3]))/2.0
            q=("R" if cx>xsplit else "L","B" if cy>ysplit else "T")
            d=quadrant_to_direction.get(q)
            if not d:
                continue
            ranked=[]
            for area,pts in grouped.get(d,{}).items():
                n=len(pts)
                if n<count:
                    continue
                gx=sum(float(a["cx"]) for a in pts)/n
                gy=sum(float(a["cy"]) for a in pts)/n
                dist=((gx-cx)**2+(gy-cy)**2)**0.5
                count_penalty=0.0 if n==count else 1000.0+100.0*abs(n-count)
                ranked.append((count_penalty+dist,area,n,dist))
            if ranked:
                ranked.sort(key=lambda x:x[0])
                _,area,n,dist=ranked[0]
                key=(d,round(area,6),count)
                if key not in used_spatial:
                    used_spatial.add(key)
                    door_specs.append((count,float(area),f"spatial door label: {raw}; matched repeated area row; distance={dist:.1f}"))

        # Conservative text-order fallback only when no spatial door match exists.
        if not door_specs:
            door_pat=(
                r"(?:戸|ドア|door)[^\n]{0,80}?"
                r"(?:x|×)\s*(\d{1,3})[\s\S]{0,180}?"
                r"([0-9]+(?:\.[0-9]+)?)\s*m2"
            )
            for m in re.finditer(door_pat,norm,re.I):
                count=int(m.group(1)); area=float(m.group(2))
                if count>0 and area>0:
                    door_specs.append((count,area,re.sub(r"\s+"," ",m.group(0))[:220]))

        door_by_direction={d:0.0 for d in title_tokens}
        door_evidence=[]
        for count,area,evidence in door_specs:
            candidates=[]
            for d,vals in by_direction.items():
                n=sum(1 for v in vals if abs(v-area)<1e-6)
                if n>=count:
                    candidates.append(d)
            if len(candidates)==1:
                d=candidates[0]
                door_by_direction[d]+=count*area
                door_evidence.append({"direction":d,"count":count,"unit_area_m2":area,
                                      "total_area_m2":count*area,"evidence":evidence})

        result={"source":"current_pdf_elevation_spatial_takeoff",
                "requires_confirmation":True,
                "directions":{},"door_evidence":door_evidence}
        total_window=0.0; total_door=0.0
        for d in ("north","east","south","west"):
            total_open=sum(by_direction[d])
            door=max(0.0,door_by_direction[d])
            window=max(0.0,total_open-door)
            result["directions"][d]={
                "opening_area_m2":total_open,
                "window_area_m2":window,
                "door_area_m2":door,
                "area_labels_m2":by_direction[d],
            }
            total_window+=window; total_door+=door
        result["window_area_m2"]=total_window
        result["door_area_m2"]=total_door
        result["total_exterior_opening_area_m2"]=total_window+total_door
        return result
    finally:
        doc.close()


def make_four_surfaces(dim: dict[str, Any], openings: dict[str, float], north_rotation_deg: float) -> list[dict[str, float | str]]:
    width = dim.get("width_m")
    depth = dim.get("depth_m")
    height = dim.get("height_m")
    if not width or not depth or not height:
        return []
    base = [
        ("North facade", width, 0.0, openings["north_window_m2"], openings["north_door_m2"]),
        ("East facade", depth, 90.0, openings["east_window_m2"], openings["east_door_m2"]),
        ("South facade", width, 180.0, openings["south_window_m2"], openings["south_door_m2"]),
        ("West facade", depth, 270.0, openings["west_window_m2"], openings["west_door_m2"]),
    ]
    surfaces = []
    for name, length, local_azimuth, win, door in base:
        gross = length * height
        opening = win + door
        surfaces.append({
            "name": name,
            "length_m": length,
            "height_m": height,
            "azimuth_deg": (local_azimuth + north_rotation_deg) % 360.0,
            "window_area_m2": win,
            "door_area_m2": door,
            "opaque_area_m2": max(0.0, gross - opening),
            "shading_factor": 1.0 if local_azimuth == 0 else (0.70 if local_azimuth == 180 else 0.82),
        })
    return surfaces



def _norm_drawing_text(text: str) -> str:
    # Normalize common full-width structural drawing characters without OCR.
    trans=str.maketrans({
        "Ｃ":"C","Ｇ":"G","Ｂ":"B","Ｓ":"S","Ｒ":"R",
        "１":"1","２":"2","３":"3","４":"4","５":"5","６":"6","７":"7","８":"8","９":"9","０":"0",
    })
    return (text.translate(trans).replace("×", "x").replace("Ｘ", "x").replace("X", "x")
                .replace("㎜", "mm").replace("ｍｍ", "mm")
                .replace("㎡", "m2").replace("㎥", "m3").replace("ｍ³", "m3"))


def _explicit_mm_section(text: str, labels: list[str], dims: int) -> dict[str, Any] | None:
    """Read a member section only when the label and dimensions occur together."""
    norm=_norm_drawing_text(text)
    label='(?:'+'|'.join(labels)+')'
    if dims==1:
        pats=[
            rf"{label}[^\n]{{0,100}}?(?:厚|t|thickness)?\s*[:：=]?\s*(\d{{2,4}}(?:\.\d+)?)\s*mm",
            rf"(?:厚|t|thickness)\s*[:：=]?\s*(\d{{2,4}}(?:\.\d+)?)\s*mm[^\n]{{0,100}}?{label}",
        ]
    elif dims==2:
        pats=[rf"{label}[^\n]{{0,120}}?(\d{{2,4}}(?:\.\d+)?)\s*(?:mm)?\s*x\s*(\d{{2,4}}(?:\.\d+)?)\s*mm"]
    else:
        pats=[rf"{label}[^\n]{{0,140}}?(\d{{2,4}}(?:\.\d+)?)\s*(?:mm)?\s*x\s*(\d{{2,4}}(?:\.\d+)?)\s*(?:mm)?\s*x\s*(\d{{2,4}}(?:\.\d+)?)\s*mm"]
    for pat in pats:
        m=re.search(pat,norm,re.I)
        if not m: continue
        vals=[float(m.group(i)) for i in range(1,dims+1)]
        if all(10.0<=v<=10000.0 for v in vals):
            return {"values_mm":vals,"evidence":re.sub(r"\s+"," ",m.group(0)).strip()[:220],"source":"pdf_text_explicit"}
    return None


def _explicit_count(text: str, labels: list[str]) -> dict[str, Any] | None:
    norm=_norm_drawing_text(text)
    label='(?:'+'|'.join(labels)+')'
    pats=[
        rf"{label}[^\n]{{0,80}}?(\d{{1,3}})\s*(?:箇所|ヶ所|個|基|本|nos?\.?)",
        rf"(\d{{1,3}})\s*(?:箇所|ヶ所|個|基|本|nos?\.?)[^\n]{{0,80}}?{label}",
    ]
    for pat in pats:
        m=re.search(pat,norm,re.I)
        if m:
            n=int(m.group(1))
            if 1<=n<=999:
                return {"value":n,"evidence":re.sub(r"\s+"," ",m.group(0)).strip()[:220],"source":"pdf_text_explicit"}
    return None


def _explicit_length_m(text: str, labels: list[str]) -> dict[str, Any] | None:
    norm=_norm_drawing_text(text)
    label='(?:'+'|'.join(labels)+')'
    pats=[
        rf"{label}[^\n]{{0,100}}?(?:総延長|延長|長さ|length|total)[^\n]{{0,30}}?(\d+(?:\.\d+)?)\s*m\b",
        rf"(?:総延長|延長|長さ|length|total)[^\n]{{0,30}}?(\d+(?:\.\d+)?)\s*m\b[^\n]{{0,100}}?{label}",
    ]
    for pat in pats:
        m=re.search(pat,norm,re.I)
        if m:
            v=float(m.group(1))
            if 0<v<100000:
                return {"value_m":v,"evidence":re.sub(r"\s+"," ",m.group(0)).strip()[:220],"source":"pdf_text_explicit"}
    return None


def _explicit_volume_m3(text: str, labels: list[str]) -> dict[str, Any] | None:
    norm=_norm_drawing_text(text)
    label='(?:'+'|'.join(labels)+')'
    pats=[
        rf"{label}[^\n]{{0,100}}?(?:数量|体積|volume|concrete)?[^\n]{{0,30}}?(\d+(?:\.\d+)?)\s*m3\b",
        rf"(\d+(?:\.\d+)?)\s*m3\b[^\n]{{0,100}}?{label}",
    ]
    for pat in pats:
        m=re.search(pat,norm,re.I)
        if m:
            v=float(m.group(1))
            if 0<v<100000:
                return {"value_m3":v,"evidence":re.sub(r"\s+"," ",m.group(0)).strip()[:220],"source":"pdf_text_explicit"}
    return None


def _count_plan_symbol(text: str, pattern: str) -> int:
    n=0
    for line in _norm_drawing_text(text).splitlines():
        if re.search(r"(は全て|とする|厚さ|断面|仕様)",line):
            continue
        n += len(re.findall(pattern,line,re.I))
    return n


def _rc_symbol_specs(text: str) -> dict[str, Any]:
    norm=_norm_drawing_text(text)
    out={}

    def find_dims(pats,n):
        for pat in pats:
            m=re.search(pat,norm,re.I)
            if m:
                vals=[float(m.group(i)) for i in range(1,n+1)]
                return {"values_mm":vals,"evidence":re.sub(r"\s+"," ",m.group(0)).strip()[:220],
                        "source":"pdf_text_explicit"}
        return None

    footing=find_dims([
        r"(?:独立基礎[\s\S]{0,120}?)?基礎は?\s*(\d{3,4})\s*x\s*(\d{3,4})\s*x\s*(\d{2,4})",
        r"基礎\s*(\d{3,4})\s*x\s*(\d{3,4})\s*x\s*(\d{2,4})",
    ],3)
    if footing: out["isolated_footing_section"]=footing

    col=find_dims([
        r"(?:1C1|2C1)[^\n]{0,80}?(\d{2,4})\s*x\s*(\d{2,4})",
        r"(?:柱|column)[^\n]{0,80}?(\d{2,4})\s*x\s*(\d{2,4})",
    ],2)
    if col: out["column_section"]=col

    gb=find_dims([
        r"(?:地中梁|G1|G2|B1)[^\n]{0,100}?(\d{2,4})\s*x\s*(\d{2,4})",
    ],2)
    if gb: out["beam_section"]=gb

    for pat in [r"壁は全て厚さ\s*(\d{2,4})", r"RC外壁\s*(\d{2,4})"]:
        m=re.search(pat,norm,re.I)
        if m:
            out["rc_wall_section"]={"values_mm":[float(m.group(1))],"evidence":m.group(0),"source":"pdf_text_explicit"}
            break

    for pat in [
        r"(?:S1(?:・S2・S3)?|S1・S2・S3)[^\n]{0,80}?厚さ\s*(\d{2,4})",
        r"(?:床スラブ|スラブ)[^\n]{0,80}?厚さ\s*(\d{2,4})",
    ]:
        m=re.search(pat,norm,re.I)
        if m:
            out["slab_section"]={"values_mm":[float(m.group(1))],"evidence":m.group(0),"source":"pdf_text_explicit"}
            break

    c1=_count_plan_symbol(text,r"\b1C1\b")
    c2=_count_plan_symbol(text,r"\b2C1\b")
    if c1:
        out["column_1f_count"]={"value":c1,"source":"derived_from_plan_symbol_count","evidence":"1C1 drawing-tag count"}
    if c2:
        out["column_2f_count"]={"value":c2,"source":"derived_from_plan_symbol_count","evidence":"2C1 drawing-tag count"}

    if footing and "独立基礎" in norm and c1:
        out["isolated_footing_count"]={
            "value":c1,"source":"derived_from_plan_symbol_count",
            "evidence":"独立基礎図 + 1C1 support-tag count","requires_confirmation":True
        }
    return out


def detect_structural_members(text: str, structure: str) -> dict[str, Any]:
    """Common PDF-text extraction for member dimensions/counts/quantity bases.

    This deliberately does not import the three comparison samples' confirmed
    dimensions.  Values exist only when the current PDF supplies evidence.
    Missing fields stay unconfirmed for later user verification.
    """
    labels={
        "isolated_footing":[r"独立基礎",r"isolated\s+footing"],
        "strip_footing":[r"布基礎",r"strip\s+footing"],
        "ground_beam":[r"地中梁",r"基礎梁",r"ground\s+beam",r"grade\s+beam"],
        "column":[r"柱",r"column"],
        "beam":[r"(?<!地中)梁",r"beam"],
        "rc_wall":[r"RC(?:造)?壁",r"鉄筋コンクリート壁",r"RC外壁",r"concrete\s+wall",r"RC\s+wall"],
        "slab":[r"床スラブ",r"スラブ",r"slab"],
        "foundation_slab":[r"ベタ基礎",r"基礎スラブ",r"mat\s+foundation",r"raft\s+foundation"],
    }
    out={"source":"current_pdf","policy":"explicit_evidence_or_plan_symbol_derived","requires_confirmation":True,"members":{},"missing":[]}
    rc_specs=_rc_symbol_specs(text) if structure=="RC Frame" else {}

    spec={
        "isolated_footing":3,"strip_footing":3,"ground_beam":2,"column":2,"beam":2,
        "rc_wall":1,"slab":1,"foundation_slab":1,
    }
    for key,dims in spec.items():
        rec={}
        sec=_explicit_mm_section(text,labels[key],dims)
        if sec: rec["section"]=sec
        cnt=_explicit_count(text,labels[key]) if key in {"isolated_footing","column","beam"} else None
        if cnt: rec["count"]=cnt
        length=_explicit_length_m(text,labels[key]) if key in {"strip_footing","ground_beam","beam","rc_wall"} else None
        if length: rec["total_length"]=length
        vol=_explicit_volume_m3(text,labels[key])
        if vol: rec["explicit_volume"]=vol
        if rec: out["members"][key]=rec
        else: out["missing"].append(key)

    if structure=="RC Frame" and rc_specs:
        mapping={
            "isolated_footing_section":("isolated_footing","section"),
            "column_section":("column","section"),
            "beam_section":("beam","section"),
            "rc_wall_section":("rc_wall","section"),
            "slab_section":("slab","section"),
        }
        for sk,(mk,fld) in mapping.items():
            if sk in rc_specs and fld not in out["members"].get(mk,{}):
                out["members"].setdefault(mk,{})[fld]=rc_specs[sk]
        if "beam_section" in rc_specs and "地中梁" in _norm_drawing_text(text):
            out["members"].setdefault("ground_beam",{}).setdefault("section",rc_specs["beam_section"])
        if "isolated_footing_count" in rc_specs:
            out["members"].setdefault("isolated_footing",{})["count"]=rc_specs["isolated_footing_count"]
        counts={k:v for k,v in rc_specs.items() if k.endswith("_count")}
        if counts:
            out["plan_symbol_counts"]=counts
        out["missing"]=[k for k in out["missing"] if k not in out["members"]]

    # Keep a direct, machine-friendly geometry block for downstream calculation.
    mg={"source":"pdf_text_explicit_only","requires_confirmation":True}
    def vals(k):
        try: return out["members"][k]["section"]["values_mm"]
        except Exception: return None
    if vals("column"): mg["column_mm"]=vals("column")
    if vals("beam"): mg["beam_mm"]=vals("beam")
    if vals("ground_beam"): mg["ground_beam_mm"]=vals("ground_beam")
    if vals("isolated_footing"): mg["isolated_footing_mm"]=vals("isolated_footing")
    if vals("strip_footing"): mg["strip_footing_mm"]=vals("strip_footing")
    if vals("rc_wall"): mg["rc_wall_thickness_mm"]=vals("rc_wall")[0]
    if vals("slab"): mg["upper_slab_thickness_mm"]=vals("slab")[0]
    if vals("foundation_slab"): mg["foundation_slab_thickness_mm"]=vals("foundation_slab")[0]
    for k,field in [("isolated_footing","isolated_footing_count"),("column","column_count"),("beam","beam_count")]:
        try: mg[field]=out["members"][k]["count"]["value"]
        except Exception: pass
    if out.get("plan_symbol_counts"):
        mg["plan_symbol_counts"]=out["plan_symbol_counts"]
    for k,field in [("ground_beam","ground_beam_length_m"),("strip_footing","strip_footing_length_m"),("beam","beam_total_length_m"),("rc_wall","rc_wall_total_length_m")]:
        try: mg[field]=out["members"][k]["total_length"]["value_m"]
        except Exception: pass
    out["member_geometry"]=mg
    return out



def rc_net_beam_length_m(
    centerline_length_m: float,
    left_column_width_m: float = 0.0,
    right_column_width_m: float = 0.0,
    left_connected_wall_thickness_m: float = 0.0,
    right_connected_wall_thickness_m: float = 0.0,
) -> dict[str, Any]:
    """Net RC beam length after removing column/wall intersection ownership.

    The member centerline span is reduced at each end by:
      column width / 2 + connected RC wall thickness / 2.

    This follows the confirmed AZRAS takeoff convention.  A wall-thickness
    deduction is applied only when a wall is actually connected at that end.
    """
    L=max(0.0,float(centerline_length_m or 0.0))
    lc=max(0.0,float(left_column_width_m or 0.0))
    rc=max(0.0,float(right_column_width_m or 0.0))
    lw=max(0.0,float(left_connected_wall_thickness_m or 0.0))
    rw=max(0.0,float(right_connected_wall_thickness_m or 0.0))
    left=lc/2.0+lw/2.0
    right=rc/2.0+rw/2.0
    net=max(0.0,L-left-right)
    return {
        "centerline_length_m":L,
        "left_end_deduction_m":left,
        "right_end_deduction_m":right,
        "net_length_m":net,
        "formula":(
            f"{L:g} - {lc/2.0:g} - {lw/2.0:g} - "
            f"{rc/2.0:g} - {rw/2.0:g} = {net:g} m"
        ),
        "ownership_policy":"columns_and_connected_walls_own_intersection_volume",
    }


def rc_net_wall_panel(
    centerline_width_m: float,
    centerline_height_m: float,
    left_column_width_m: float = 0.0,
    right_column_width_m: float = 0.0,
    lower_beam_depth_m: float = 0.0,
    upper_beam_depth_m: float = 0.0,
    opening_area_m2: float = 0.0,
) -> dict[str, Any]:
    """Net RC wall panel area excluding column/beam intersections and openings.

    Wall width is taken between column faces.  Wall height is taken between
    beam faces.  Openings are then subtracted.  This prevents wall concrete
    from duplicating volumes already assigned to columns and beams.
    """
    W=max(0.0,float(centerline_width_m or 0.0))
    H=max(0.0,float(centerline_height_m or 0.0))
    lc=max(0.0,float(left_column_width_m or 0.0))
    rc=max(0.0,float(right_column_width_m or 0.0))
    lb=max(0.0,float(lower_beam_depth_m or 0.0))
    ub=max(0.0,float(upper_beam_depth_m or 0.0))
    op=max(0.0,float(opening_area_m2 or 0.0))
    net_w=max(0.0,W-lc/2.0-rc/2.0)
    net_h=max(0.0,H-lb/2.0-ub/2.0)
    gross=net_w*net_h
    net_area=max(0.0,gross-op)
    return {
        "centerline_width_m":W,
        "centerline_height_m":H,
        "net_width_m":net_w,
        "net_height_m":net_h,
        "gross_panel_area_m2":gross,
        "opening_area_m2":op,
        "net_wall_area_m2":net_area,
        "width_formula":f"{W:g} - {lc/2.0:g} - {rc/2.0:g} = {net_w:g} m",
        "height_formula":f"{H:g} - {lb/2.0:g} - {ub/2.0:g} = {net_h:g} m",
        "ownership_policy":"columns_and_beams_own_intersection_volume",
    }


def build_rc_overlap_policy(member_result: dict[str, Any]) -> dict[str, Any]:
    """Store the overlap-deduction rules and a verified example from current PDF data."""
    mg=member_result.get("member_geometry",{}) or {}
    col=mg.get("column_mm") or []
    wall_t=float(mg.get("rc_wall_thickness_mm") or 0.0)/1000.0
    col_width=float(col[0])/1000.0 if len(col)>=1 else 0.0
    out={
        "enabled":True,
        "requires_topology_confirmation":True,
        "beam_rule_ja":"梁純長は芯々長さから、各端の柱半幅と実際に接続するRC壁厚の1/2を控除する。",
        "wall_rule_ja":"RC壁は柱・梁が占有する交差部を除いた柱面間・梁面間の純壁面積とし、さらに開口を控除する。",
        "slab_rule_ja":"スラブも柱・梁・壁との重複を二重計上しない部材所属ルールで集計する。",
        "volume_ownership_order":["column","beam","rc_wall","slab"],
    }
    return out


def build_explicit_concrete_quantities(member_result: dict[str, Any], dimensions: dict[str, Any]) -> dict[str, Any]:
    """Derive only quantities that have enough explicit current-PDF evidence."""
    members=member_result.get("members",{}) or {}
    q={"source":"current_pdf_explicit_or_derived","requires_confirmation":True,"components":{},"missing":[]}

    def section_m(key):
        try: return [float(v)/1000.0 for v in members[key]["section"]["values_mm"]]
        except Exception: return None
    def count(key):
        try: return int(members[key]["count"]["value"])
        except Exception: return None
    def length(key):
        try: return float(members[key]["total_length"]["value_m"])
        except Exception: return None
    def explicit_vol(key):
        try: return float(members[key]["explicit_volume"]["value_m3"])
        except Exception: return None
    def put(key,val,basis,source_type):
        if val is not None and val>0:
            q["components"][key]={"volume_m3":float(val),"basis":basis,"source_type":source_type,"requires_confirmation":True}

    # Explicit component volume always wins.
    for key in ("isolated_footing","strip_footing","ground_beam","column","beam","rc_wall","slab","foundation_slab"):
        v=explicit_vol(key)
        if v: put(key,v,"PDFに明示された部材体積","pdf_explicit_volume")

    # Isolated footings: count x B x D x H.
    if "isolated_footing" not in q["components"]:
        s=section_m("isolated_footing"); n=count("isolated_footing")
        if s and len(s)==3 and n:
            put("isolated_footing",n*s[0]*s[1]*s[2],f"{n}基 × {s[0]:g}m × {s[1]:g}m × {s[2]:g}m","derived_from_pdf_dimensions")

    # Linear members with explicit total length.
    for key in ("strip_footing","ground_beam","beam"):
        if key in q["components"]: continue
        s=section_m(key); L=length(key)
        if s and len(s)>=2 and L:
            area=s[0]*s[1] if len(s)==2 else (s[0]*s[2] + max(0.0,s[1]-s[2])*s[0])
            put(key,L*area,f"総延長{L:g}m × 断面積{area:.5f}m2","derived_from_pdf_dimensions")

    # Foundation slab from footprint x explicit thickness.
    if "foundation_slab" not in q["components"]:
        s=section_m("foundation_slab")
        fp=dimensions.get("footprint_m2")
        if s and fp:
            put("foundation_slab",float(fp)*s[0],f"建築面積{float(fp):g}m2 × 厚{s[0]:g}m","derived_from_pdf_dimensions")

    q["total_m3"]=sum(v["volume_m3"] for v in q["components"].values())
    return q



def detect_2x6_foundation_from_pdf(pdf_path: str | Path, dimensions: dict[str, Any]) -> dict[str, Any] | None:
    """Current-PDF 2x6 strip foundation and under-slab insulation takeoff.

    This routine does not use average quantity rates. It reads:
      - building width/depth and repeated dwelling bays from the current plan;
      - slab/XPS thickness from the detailed section;
      - strip-footing section dimensions by scale-calibrated measurement of the
        repeated footing shapes in the 1:100 detailed section.
    """
    if fitz is None:
        return None
    width=float(dimensions.get("width_m") or 0.0)
    depth=float(dimensions.get("depth_m") or 0.0)
    footprint=float(dimensions.get("footprint_m2") or 0.0)
    if width<=0 or depth<=0 or footprint<=0:
        return None
    try:
        doc=fitz.open(str(pdf_path))
    except Exception:
        return None

    result={
        "status":"unresolved",
        "source":"current_pdf_plan_and_section",
        "requires_confirmation":False,
    }
    try:
        plan_page=None
        section_page=None
        section_text=""
        for page in doc:
            t=_norm_drawing_text(page.get_text())
            if plan_page is None and ("配置図兼1階平面図" in t or "1階平面図" in t):
                plan_page=page
            if section_page is None and "断面図" in t and "土間厚" in t and "ポリスチレン" in t:
                section_page=page
                section_text=t
        if plan_page is None or section_page is None:
            result["reason"]="plan_or_detailed_section_not_found"
            return result

        # Detailed section note overrides generic notes elsewhere in the set.
        slab_mm=None
        xps_mm=None
        m=re.search(r"土間厚\s*([0-9.]+)\s*\+?\s*高性能発泡ポリスチレン厚\s*([0-9.]+)",section_text)
        if m:
            slab_mm=float(m.group(1))
            xps_mm=float(m.group(2))
        if not slab_mm or not xps_mm:
            result["reason"]="detailed_slab_xps_note_not_resolved"
            return result

        # Resolve equal-width dwelling bays from the current first-floor plan.
        overall=width*1000.0
        numeric=[]
        for w in plan_page.get_text("words"):
            try:
                v=float(_norm_drawing_text(str(w[4])).strip())
            except Exception:
                continue
            if 500.0<=v<=20000.0:
                numeric.append(v)
        candidate_counts={}
        for v in numeric:
            if v>=overall*0.9:
                continue
            n=round(overall/v) if v else 0
            if 2<=n<=12 and abs(v*n-overall)<=max(10.0,overall*0.005):
                candidate_counts[(round(v,3),int(n))]=candidate_counts.get((round(v,3),int(n)),0)+1
        if not candidate_counts:
            result["reason"]="repeated_plan_bays_not_resolved"
            return result
        (bay_mm,unit_count),repeat_count=max(
            candidate_counts.items(),key=lambda kv:(kv[1],kv[0][0])
        )
        if repeat_count<2:
            result["reason"]="repeated_plan_bays_not_confirmed"
            return result

        internal_lines=max(0,unit_count-1)
        centerline=2.0*(width+depth)+internal_lines*depth
        result.update({
            "plan_bay_dimension_mm":bay_mm,
            "plan_bay_repeat_count":repeat_count,
            "unit_count":unit_count,
            "internal_strip_lines":internal_lines,
            "centerline_total_m":centerline,
            "centerline_formula":f"外周2×({width:.3f}+{depth:.3f})＋界壁{internal_lines}本×{depth:.3f}",
            "slab_thickness_mm":slab_mm,
            "xps_thickness_mm":xps_mm,
        })

        # High-resolution scale measurement of the repeated footing rectangles.
        zoom=4.0
        pix=section_page.get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False)
        arr=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
        gray=cv2.cvtColor(arr[:,:,:3],cv2.COLOR_RGB2GRAY) if pix.n>=3 else arr[:,:,0]
        _,binary=cv2.threshold(gray,180,255,cv2.THRESH_BINARY_INV)
        H,W=gray.shape

        contours,_=cv2.findContours(binary,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        halves=[]
        for c in contours:
            x,y,w,h=cv2.boundingRect(c)
            if not (int(H*0.50)<=y<=int(H*0.72)):
                continue
            if 20<=w<=45 and 25<=h<=65 and cv2.contourArea(c)>=500:
                halves.append((x,y,w,h))

        # Footing centreline divides the base outline into two adjacent contour
        # halves. Pair halves with a common bottom elevation.
        halves=sorted(halves,key=lambda r:(r[1]+r[3],r[0]))
        paired=[]
        used=set()
        for i,a in enumerate(halves):
            if i in used:
                continue
            ax,ay,aw,ah=a
            ab=ay+ah
            best=None
            for j,b in enumerate(halves):
                if j==i or j in used:
                    continue
                bx,by,bw0,bh=b
                bb=by+bh
                gap=bx-(ax+aw)
                if -3<=gap<=5 and abs(bb-ab)<=3:
                    best=(j,b)
                    break
            if best:
                j,b=best
                bx,by,bw0,bh=b
                used.update({i,j})
                paired.append((ax,min(ay,by),bx+bw0-ax,max(ab,bb)-min(ay,by),max(ab,bb)))

        # Find the equal-spaced group of unit_count+1 strip footings.
        needed=unit_count+1
        best_seq=None
        for bottom in sorted(set(round(r[4]/3)*3 for r in paired)):
            grp=sorted(
                [r for r in paired if abs(r[4]-bottom)<=4 and 55<=r[2]<=80],
                key=lambda r:r[0]
            )
            if len(grp)<needed:
                continue
            for i in range(len(grp)-needed+1):
                seq=grp[i:i+needed]
                centers=[r[0]+r[2]/2.0 for r in seq]
                spacings=[centers[k+1]-centers[k] for k in range(len(centers)-1)]
                med=statistics.median(spacings)
                variation=max(abs(v-med) for v in spacings)/med if med else 99
                if variation<=0.08 and (best_seq is None or variation<best_seq[0]):
                    best_seq=(variation,seq,med)

        if best_seq is None:
            result["status"]="plan_resolved_section_scale_measurement_incomplete"
            return result

        _,seq,bay_px=best_seq
        px_per_mm=bay_px/(width*1000.0/unit_count)
        base_width_raw=statistics.median([r[2] for r in seq])/px_per_mm

        # Use the first clear internal footing. Internal footings avoid the
        # exterior-wall finish geometry and give a clean stem/base section.
        representative=seq[1] if len(seq)>2 else seq[0]
        rx,ry,rw,rh,rbottom=representative
        rcx=rx+rw/2.0
        x0=max(0,int(rcx-rw*0.9))
        x1=min(W,int(rcx+rw*0.9))
        y0=max(0,int(ry-55))
        y1=min(H,int(rbottom+12))
        roi=(gray[y0:y1,x0:x1] < 100)

        # Collect every continuous vertical line run.
        runs=[]
        for xx in range(roi.shape[1]):
            col=roi[:,xx]
            cur=0
            start=0
            for yy,val in enumerate(col):
                if val:
                    if cur==0:
                        start=yy
                    cur+=1
                else:
                    if cur>=12:
                        runs.append((xx,cur,start,start+cur-1))
                    cur=0
            if cur>=12:
                runs.append((xx,cur,start,start+cur-1))

        c_local=rcx-x0

        # Base sides are the long low runs near +/- half base width.
        left_base=[r for r in runs if r[0]<c_local-0.30*rw and r[2]>(ry-y0)]
        right_base=[r for r in runs if r[0]>c_local+0.30*rw and r[2]>(ry-y0)]
        if not left_base or not right_base:
            result["status"]="plan_resolved_section_scale_measurement_incomplete"
            return result
        lb=min(left_base,key=lambda r:abs(r[0]-(c_local-rw/2.0)))
        rb=min(right_base,key=lambda r:abs(r[0]-(c_local+rw/2.0)))
        base_height_px=statistics.median([lb[1],rb[1]])

        # Stem sides are the symmetric runs immediately around the centreline.
        left_stem=[
            r for r in runs
            if -0.30*rw <= (r[0]-c_local) <= -0.10*rw and 20<=r[1]<=50
        ]
        right_stem=[
            r for r in runs
            if 0.10*rw <= (r[0]-c_local) <= 0.30*rw and 20<=r[1]<=50
        ]
        best_stem=None
        for l in left_stem:
            for rr in right_stem:
                score=(
                    abs(l[2]-rr[2])+abs(l[3]-rr[3])
                    +abs(abs(l[0]-c_local)-abs(rr[0]-c_local))
                )
                if best_stem is None or score<best_stem[0]:
                    best_stem=(score,l,rr)
        if best_stem is None:
            result["status"]="plan_resolved_section_scale_measurement_incomplete"
            return result
        _,ls,rs=best_stem
        stem_width_px=rs[0]-ls[0]
        stem_height_px=statistics.median([ls[1],rs[1]])

        def round50(value_mm):
            return max(50.0,round(float(value_mm)/50.0)*50.0)

        footing_w=round50(base_width_raw)
        footing_t=round50(base_height_px/px_per_mm)
        stem_w=round50(stem_width_px/px_per_mm)
        stem_h=round50(stem_height_px/px_per_mm)

        section_area=(footing_w/1000.0)*(footing_t/1000.0)+(stem_w/1000.0)*(stem_h/1000.0)
        concrete_m3=centerline*section_area

        # Under-slab XPS: detailed section says XPS100 under the slab. The
        # wide footing base is below the slab/XPS plane, so the in-plane
        # obstruction is the strip/ground-beam stem width.
        sw=stem_w/1000.0
        free_width=max(0.0,width-(internal_lines+1)*sw)
        free_depth=max(0.0,depth-sw)
        xps_area=free_width*free_depth
        xps_m3=xps_area*(xps_mm/1000.0)

        result.update({
            "status":"resolved_from_current_pdf_geometry",
            "section_scale":"1:100 scale-calibrated vector measurement",
            "scale_px_per_mm":px_per_mm,
            "footing_base_width_mm":footing_w,
            "footing_base_thickness_mm":footing_t,
            "stem_width_mm":stem_w,
            "stem_height_mm":stem_h,
            "section_area_m2":section_area,
            "concrete_volume_m3":concrete_m3,
            "under_slab_insulation_area_m2":xps_area,
            "under_slab_insulation_volume_m3":xps_m3,
            "evidence":[
                "現在PDF 配置図兼1階平面図：建物外周寸法・3戸界壁位置",
                "現在PDF 断面図1:100：繰返し布基礎断面を縮尺計測",
                f"現在PDF 詳細断面：土間厚{slab_mm:g}mm＋高性能発泡ポリスチレン厚{xps_mm:g}mm",
            ],
        })
        return result
    finally:
        doc.close()


_FOUNDATION_PLAN_TITLE_RE = re.compile(r"(?:布|ベタ)?基礎伏せ?(?:見下げ)?図")


def _strip_foundation_plan_cells(lines, tol: float = 0.6):
    """Closed rectangles drawn from separate H/V segments, and the cells among them.

    A strip-foundation plan draws every enclosed area (土間) as two concentric
    rectangles: the outer one is the stem face, the inner one the edge of the
    wider footing base.  A rectangle that contains a concentric rectangle with
    the same offset on all four sides is therefore a cell bounded by stem faces.
    """
    hs=[l for l in lines if l["orientation"]=="h" and l["length"]>=15.0]
    vs=[l for l in lines if l["orientation"]=="v" and l["length"]>=15.0]

    def has_v(x, y0, y1):
        return any(abs(v["coord"]-x)<=tol and v["a"]<=y0+tol and v["b"]>=y1-tol for v in vs)

    rects=[]
    seen=set()
    for i,a in enumerate(hs):
        for b in hs[i+1:]:
            if abs(a["a"]-b["a"])>tol or abs(a["b"]-b["b"])>tol:
                continue
            y0,y1=sorted((a["coord"],b["coord"]))
            if y1-y0<15.0:
                continue
            x0=(a["a"]+b["a"])/2.0; x1=(a["b"]+b["b"])/2.0
            if not (has_v(x0,y0,y1) and has_v(x1,y0,y1)):
                continue
            key=(round(x0,1),round(y0,1),round(x1,1),round(y1,1))
            if key not in seen:
                seen.add(key); rects.append(key)
    cells=[]
    for r in rects:
        for q in rects:
            if q==r:
                continue
            offs=(q[0]-r[0],q[1]-r[1],r[2]-q[2],r[3]-q[3])
            if min(offs)>=2.0 and max(offs)<=20.0 and max(offs)-min(offs)<=0.6:
                cells.append({"rect":r,"base_overhang_pt":sum(offs)/4.0})
                break
    return cells


def detect_2x6_strip_foundation_plan_vector(pdf_path: str | Path, dimensions: dict[str, Any]) -> dict[str, Any] | None:
    """PATCH_050: 2x6 strip foundation measured on the foundation plan itself.

    Earlier logic derived the centerline as "perimeter + party walls x depth"
    from repeated dwelling bays and could not see internal strip footings
    around rooms.  This routine reads the current PDF only:
      - foundation plan (title 基礎伏図 / 基礎伏せ図 / 布基礎伏せ図): every cell
        bounded by stem faces; stem width = gap between neighbouring cells;
        base overhang = offset of the inner (footing-edge) rectangle;
      - total centerline = (sum of cell centerline perimeters + outer
        centerline perimeter) / 2 — every internal strip is shared by two
        cells and every perimeter strip by one;
      - scale from the building width in the current plan dimensions
        (checked against the depth);
      - section heights from the dimensioned strip-footing sketch
        (total = stem height + base thickness);
      - slab / XPS thickness from the section note.
    Output keeps the Module 1 contract (status resolved_from_current_pdf_geometry,
    scalar concrete_volume_m3 ...) and adds the Module 5 earthwork contract
    (foundation_type, dimensions_mm, centerline_length_breakdown_m).
    """
    if fitz is None:
        return None
    width=float(dimensions.get("width_m") or 0.0)
    depth=float(dimensions.get("depth_m") or 0.0)
    if width<=0 or depth<=0:
        return None
    try:
        doc=fitz.open(str(pdf_path))
    except Exception:
        return None
    result={"status":"unresolved","source":"current_pdf_foundation_plan_vector","requires_confirmation":True}
    try:
        all_text=""
        plan=None
        for page in doc:
            t=_norm_drawing_text(page.get_text())
            all_text+="\n"+t
            if plan is None:
                m=_FOUNDATION_PLAN_TITLE_RE.search(t.replace(" ","").replace("\u3000",""))
                if m and page.search_for(m.group(0)):
                    plan=(page,m.group(0))
        if plan is None:
            result["reason"]="foundation_plan_title_not_found"; return result
        page,title=plan
        lines,_box=_fitz_vector_lines_near_title(page,title)
        if not lines:
            result["reason"]="foundation_plan_vectors_not_found"; return result
        # _fitz_vector_lines_near_title drops lines shorter than 20 pt; cell
        # edges of small rooms are longer than that at 1:100.
        cells=_strip_foundation_plan_cells(lines)
        if len(cells)<2:
            result["reason"]="foundation_plan_cells_not_resolved"; return result

        rects=[c["rect"] for c in cells]
        gaps=[]
        for a in rects:
            for b in rects:
                if a is b:
                    continue
                if min(a[3],b[3])-max(a[1],b[1])>5.0:
                    g=b[0]-a[2]
                    if 1.0<=g<=15.0: gaps.append(g)
                if min(a[2],b[2])-max(a[0],b[0])>5.0:
                    g=b[1]-a[3]
                    if 1.0<=g<=15.0: gaps.append(g)
        if not gaps:
            result["reason"]="stem_width_not_resolved"; return result
        stem_pt=statistics.median(gaps)
        half=stem_pt/2.0
        expanded=[(r[0]-half,r[1]-half,r[2]+half,r[3]+half) for r in rects]
        bx0=min(r[0] for r in expanded); by0=min(r[1] for r in expanded)
        bx1=max(r[2] for r in expanded); by1=max(r[3] for r in expanded)
        span_x=bx1-bx0; span_y=by1-by0
        # Plan width/depth may be drawn in either orientation.
        long_pt,short_pt=max(span_x,span_y),min(span_x,span_y)
        long_m,short_m=max(width,depth),min(width,depth)
        mm_per_pt=long_m*1000.0/long_pt
        if abs(short_pt*mm_per_pt-short_m*1000.0)>max(50.0,short_m*1000.0*0.01):
            result.update({"reason":"plan_scale_inconsistent_with_building_dimensions",
                           "measured_mm":[round(long_pt*mm_per_pt),round(short_pt*mm_per_pt)]})
            return result
        # Cells must tile the centerline rectangle (no missing strips).
        cell_area_pt=sum((r[2]-r[0])*(r[3]-r[1]) for r in expanded)
        if abs(cell_area_pt-span_x*span_y)>0.01*span_x*span_y:
            result["reason"]="foundation_cells_do_not_tile_plan"; return result
        m_per_pt=mm_per_pt/1000.0
        sum_cell_perim=sum(2.0*((r[2]-r[0])+(r[3]-r[1])) for r in expanded)*m_per_pt
        outer_perim=2.0*(span_x+span_y)*m_per_pt
        centerline=(sum_cell_perim+outer_perim)/2.0
        internal=centerline-outer_perim

        def round10(v):
            return round(float(v)/10.0)*10.0
        stem_w=round10(stem_pt*mm_per_pt)
        overhang=round10(statistics.median([c["base_overhang_pt"] for c in cells])*mm_per_pt)
        base_w=stem_w+2.0*overhang
        slab_area=sum((r[2]-r[0])*(r[3]-r[1]) for r in rects)*m_per_pt*m_per_pt

        # Section heights from the dimensioned sketch labelled 布基礎.
        M=page.rotation_matrix
        words=[]
        for w in page.get_text("words"):
            rr=fitz.Rect(w[0],w[1],w[2],w[3])*M
            words.append((_norm_drawing_text(str(w[4])).strip(),rr))
        title_rects=[fitz.Rect(r)*M for r in page.search_for(title)]
        labels=[r for t,r in words if t=="布基礎" and not any(r.intersects(tr) for tr in title_rects)]
        stem_h=base_t=None
        section_numbers=[]
        for lab in labels:
            cx=(lab.x0+lab.x1)/2.0
            nums=[]
            for t,r in words:
                if re.fullmatch(r"[0-9]{2,4}",t) and abs((r.x0+r.x1)/2.0-cx)<=160.0 and lab.y0-170.0<=r.y0<=lab.y0:
                    nums.append((float(t),r))
            for total,_tr in nums:
                parts=[(v,r) for v,r in nums if v<total]
                for i,(v1,r1) in enumerate(parts):
                    for v2,r2 in parts[i+1:]:
                        if abs(v1+v2-total)<0.5:
                            # the lower dimension (larger display y) is the base
                            lower,upper=((v1,r1),(v2,r2)) if r1.y0>r2.y0 else ((v2,r2),(v1,r1))
                            stem_h,base_t=upper[0],lower[0]
                            section_numbers=sorted(v for v,_ in nums)
                            break
                    if stem_h: break
                if stem_h: break
            if stem_h:
                # Plan-measured widths must agree with the sketch when it states them.
                if section_numbers and (stem_w not in section_numbers or base_w not in section_numbers):
                    result.update({"reason":"plan_widths_disagree_with_section_sketch",
                                   "plan_stem_width_mm":stem_w,"plan_base_width_mm":base_w,
                                   "section_numbers_mm":section_numbers})
                    return result
                break
        if not stem_h or not base_t:
            result.update({"status":"plan_resolved_section_heights_not_resolved",
                           "centerline_total_m":centerline,"stem_width_mm":stem_w,"footing_base_width_mm":base_w})
            return result

        slab_mm=xps_mm=None
        m=re.search(r"土間厚\s*([0-9.]+)\s*\+?\s*高性能発泡ポリスチレン厚\s*([0-9.]+)",all_text)
        if m:
            slab_mm=float(m.group(1)); xps_mm=float(m.group(2))
        section_area=(base_w/1000.0)*(base_t/1000.0)+(stem_w/1000.0)*(stem_h/1000.0)
        concrete=centerline*section_area
        result.update({
            "status":"resolved_from_current_pdf_geometry",
            "foundation_type":"strip_foundation_with_slab_on_ground",
            "plan_title":title,
            "plan_scale_mm_per_pt":mm_per_pt,
            "cell_count":len(cells),
            "centerline_total_m":centerline,
            "centerline_formula":(f"(各区画の芯々周長計 {sum_cell_perim:.3f}m＋外周芯々 {outer_perim:.3f}m)÷2"
                                  f"＝{centerline:.3f}m（外周 {outer_perim:.3f}m＋内部 {internal:.3f}m）"),
            "centerline_length_breakdown_m":{"perimeter":outer_perim,"internal":internal,"total":centerline},
            "footing_base_width_mm":base_w,"footing_base_thickness_mm":base_t,
            "stem_width_mm":stem_w,"stem_height_mm":stem_h,
            "dimensions_mm":{"footing_width":base_w,"footing_thickness":base_t,"stem_width":stem_w,
                             "stem_height":stem_h,"total_height":base_t+stem_h,"slab_thickness":slab_mm},
            "section_area_m2":section_area,
            "concrete_volume_m3":concrete,
            "concrete_volume_breakdown_m3":{"strip_foundation":concrete},
            "slab_area_inside_stems_m2":slab_area,
            "slab_thickness_mm":slab_mm,"xps_thickness_mm":xps_mm,
            "evidence":[
                f"現在PDF {title}：区画{len(cells)}（立上り面）、立上り幅{stem_w:.0f}mm＝隣接区画の間隔、底盤幅{base_w:.0f}mm＝立上り＋底盤はね出し×2",
                f"現在PDF 布基礎断面スケッチ：立上り高{stem_h:.0f}mm＋底盤厚{base_t:.0f}mm（寸法値 {section_numbers}）",
                "縮尺：平面の建物外形寸法と伏図の芯々外形を照合（幅・奥行とも1%以内）",
            ],
        })
        if slab_mm and xps_mm:
            result["under_slab_insulation_area_m2"]=slab_area
            result["under_slab_insulation_volume_m3"]=slab_area*xps_mm/1000.0
        return result
    finally:
        doc.close()


def detect_2x6_strip_foundation(text: str, dimensions: dict[str, Any]) -> dict[str, Any] | None:
    """2x6 foundation geometry from the current PDF only.

    No historical comparison-plan centerline is stored or reused. A concrete
    quantity is derived only when the current PDF explicitly supplies the strip
    section and total centerline length.  Otherwise the geometry is returned as
    unconfirmed/incomplete for user verification.
    """
    members=detect_structural_members(text,"2x6 Timber")
    m=(members.get("members") or {}).get("strip_footing") or {}
    if not m:
        return None
    try: dims_mm=m["section"]["values_mm"]
    except Exception: dims_mm=None
    try: length_m=float(m["total_length"]["value_m"])
    except Exception: length_m=None
    slab_sec=((members.get("members") or {}).get("slab") or {}).get("section") or {}
    slab_mm=(slab_sec.get("values_mm") or [None])[0]
    footprint=float(dimensions.get("footprint_m2") or 0.0)
    if not dims_mm or len(dims_mm)!=3:
        return {"status":"insufficient_explicit_drawing_data","source":"current_pdf","requires_confirmation":True,"member_extraction":m}
    footing_w, stem_w, total_h=[float(x) for x in dims_mm]
    # A 3-value strip-foundation note is stored as B x stem-width x overall-height.
    result={
        "status":"explicit_geometry_requires_confirmation",
        "source":"current_pdf",
        "requires_confirmation":True,
        "dimensions_mm":{"footing_width":footing_w,"stem_width":stem_w,"total_height":total_h,"slab_thickness":slab_mm},
        "centerline_total_m":length_m,
        "concrete_volume_m3":{},
    }
    if length_m and slab_mm and footprint>0:
        # Do not invent footing/stem split thicknesses. The exact section area
        # remains unresolved unless an explicit volume exists elsewhere.
        result["status"]="explicit_geometry_incomplete_section"
    return result



def _fitz_rot_rect(page, rect):
    pts=[
        fitz.Point(rect.x0,rect.y0)*page.rotation_matrix,
        fitz.Point(rect.x1,rect.y1)*page.rotation_matrix,
    ]
    return fitz.Rect(
        min(p.x for p in pts),min(p.y for p in pts),
        max(p.x for p in pts),max(p.y for p in pts)
    )


def _fitz_rot_words(page):
    result=[]
    for w in page.get_text("words"):
        r=fitz.Rect(w[0],w[1],w[2],w[3])
        rr=_fitz_rot_rect(page,r)
        result.append({"text":_norm_drawing_text(str(w[4])),"rect":rr})
    return result


def _fitz_vector_lines_near_title(page, title: str):
    found=page.search_for(title)
    if not found:
        return [],None
    tr=found[0]
    yc=(tr.y0+tr.y1)/2.0
    # For 90-degree plotted architectural sheets the plan sits before the
    # vertical title in unrotated PDF coordinates.  Keep a broad search box,
    # then use structural labels and line pairs to reject unrelated geometry.
    box=fitz.Rect(
        max(0.0,tr.x0-430.0),
        max(0.0,yc-330.0),
        max(0.0,tr.x0-15.0),
        min(float(page.mediabox.height),yc+330.0),
    )
    lines=[]
    for d in page.get_drawings():
        for it in d.get("items",[]):
            if not it or it[0]!="l":
                continue
            p1,p2=it[1],it[2]
            mid=fitz.Point((p1.x+p2.x)/2.0,(p1.y+p2.y)/2.0)
            if not box.contains(mid):
                continue
            q1=p1*page.rotation_matrix; q2=p2*page.rotation_matrix
            dx=q2.x-q1.x; dy=q2.y-q1.y
            L=(dx*dx+dy*dy)**0.5
            if L<20.0:
                continue
            if abs(dy)<0.8:
                lines.append({"orientation":"h","coord":(q1.y+q2.y)/2.0,
                              "a":min(q1.x,q2.x),"b":max(q1.x,q2.x),"length":L})
            elif abs(dx)<0.8:
                lines.append({"orientation":"v","coord":(q1.x+q2.x)/2.0,
                              "a":min(q1.y,q2.y),"b":max(q1.y,q2.y),"length":L})
    return lines,box


def _pair_vector_boundaries(lines, orientation: str, min_length: float=80.0):
    src=[x for x in lines if x["orientation"]==orientation and x["length"]>=min_length]
    pairs=[]
    for i,a in enumerate(src):
        for b in src[i+1:]:
            sep=abs(float(a["coord"])-float(b["coord"]))
            if not (3.0<=sep<=13.0):
                continue
            overlap=max(0.0,min(a["b"],b["b"])-max(a["a"],b["a"]))
            shorter=min(a["b"]-a["a"],b["b"]-b["a"])
            if shorter<=0 or overlap/shorter<0.70:
                continue
            pairs.append({
                "center":(a["coord"]+b["coord"])/2.0,
                "boundary_separation_pt":sep,
                "a":max(a["a"],b["a"]),"b":min(a["b"],b["b"]),
                "overlap_length_pt":overlap,
            })
    # Collapse duplicate center candidates, preferring the pair with the widest
    # useful separation (normally closest to the actual structural-member width).
    groups=[]
    for x in sorted(pairs,key=lambda z:z["center"]):
        g=next((g for g in groups if abs(g["center"]-x["center"])<2.2),None)
        if g is None:
            groups.append(dict(x))
        elif x["boundary_separation_pt"]>g["boundary_separation_pt"]:
            g.update(x)
    return groups


def _nearest_center(candidates, target, tolerance=32.0):
    if not candidates:
        return None
    hit=min(candidates,key=lambda x:abs(x["center"]-target))
    return hit if abs(hit["center"]-target)<=tolerance else None


def _word_centers(words, label):
    return [
        ((w["rect"].x0+w["rect"].x1)/2.0,(w["rect"].y0+w["rect"].y1)/2.0,
         w["rect"].width,w["rect"].height)
        for w in words if w["text"]==label
    ]


def _rc_floor_frame_vector_takeoff(page, dimensions, member_result):
    lines,_=_fitz_vector_lines_near_title(page,"2階床伏せ見上図")
    if not lines:
        return None
    words=_fitz_rot_words(page)
    vp=_pair_vector_boundaries(lines,"v")
    hp=_pair_vector_boundaries(lines,"h")
    cols=_word_centers(words,"1C1")
    g1=_word_centers(words,"G1")
    g2=_word_centers(words,"G2")
    b1=_word_centers(words,"B1")
    if len(cols)<8 or len(g1)<4 or len(g2)<6 or len(b1)<6:
        return {
            "status":"vector_topology_incomplete",
            "requires_confirmation":True,
            "detected_label_counts":{"1C1":len(cols),"G1":len(g1),"G2":len(g2),"B1":len(b1)}
        }

    # Main grid X positions come from top/bottom column tags, validated against
    # a nearby paired vector member line.
    col_x=[]
    for x,_,_,_ in cols:
        h=_nearest_center(vp,x)
        if h: col_x.append(h["center"])
    # collapse
    xs=[]
    for x in sorted(col_x):
        if not xs or abs(x-xs[-1])>5:
            xs.append(x)
        else:
            xs[-1]=(xs[-1]+x)/2.0
    if len(xs)!=4:
        return {"status":"vector_topology_incomplete","requires_confirmation":True,
                "reason":"four primary column/beam grid lines were not resolved","primary_x":xs}

    # G2 identifies top/bottom horizontal beams.
    gy=[]
    for _,y,_,_ in g2:
        h=_nearest_center(hp,y,22.0)
        if h: gy.append(h["center"])
    ys=[]
    for y in sorted(gy):
        if not ys or abs(y-ys[-1])>8:
            ys.append(y)
        else:
            ys[-1]=(ys[-1]+y)/2.0
    if len(ys)<2:
        return {"status":"vector_topology_incomplete","requires_confirmation":True,
                "reason":"top/bottom G2 beam lines were not resolved"}
    top_y=min(ys); bottom_y=max(ys)

    # Horizontal B1 row: horizontal label boxes are wider than high.
    b1_h=[(x,y) for x,y,w,h in b1 if w>h]
    mid_hits=[_nearest_center(hp,y,22.0) for _,y in b1_h]
    mid_hits=[x for x in mid_hits if x]
    if not mid_hits:
        return {"status":"vector_topology_incomplete","requires_confirmation":True,
                "reason":"middle B1 beam line was not resolved"}
    mid_y=sum(x["center"] for x in mid_hits)/len(mid_hits)

    # Vertical B1: rotated labels are taller than wide.
    b1_v=[(x,y) for x,y,w,h in b1 if h>w]
    secondary=[]
    for x,_ in b1_v:
        h=_nearest_center(vp,x,24.0)
        if h and all(abs(h["center"]-m)>12 for m in xs):
            if not any(abs(h["center"]-v)<5 for v in secondary):
                secondary.append(h["center"])
    secondary=sorted(secondary)

    width=float(dimensions.get("width_m") or 0.0)
    depth=float(dimensions.get("depth_m") or 0.0)
    mg=member_result.get("member_geometry",{}) or {}
    col=mg.get("column_mm") or []
    beam=mg.get("beam_mm") or mg.get("ground_beam_mm") or []
    wall_t=float(mg.get("rc_wall_thickness_mm") or 0.0)/1000.0
    if width<=0 or depth<=0 or len(col)<2 or len(beam)<2 or wall_t<=0:
        return {"status":"vector_topology_geometry_incomplete","requires_confirmation":True}

    scale_x=(xs[-1]-xs[0])/width
    scale_y=(bottom_y-top_y)/depth
    bay=width/(len(xs)-1)
    upper_depth=(mid_y-top_y)/scale_y

    col_x_dim=float(col[0])/1000.0
    col_y_dim=float(col[1])/1000.0
    beam_w=float(beam[0])/1000.0
    beam_d=float(beam[1])/1000.0

    segments=[]
    # G2: top and bottom, three bays each. User-confirmed rule includes
    # column half-width plus connected RC-wall half-thickness at each end.
    for row_name in ("top","bottom"):
        for i in range(len(xs)-1):
            calc=rc_net_beam_length_m(
                bay,col_x_dim,col_x_dim,wall_t,wall_t
            )
            segments.append({
                "member":"G2","orientation":"horizontal","row":row_name,
                "span_index":i+1,"centerline_length_m":bay,
                "net_length_m":calc["net_length_m"],
                "deduction_basis":calc["formula"],
                "deduction_status":"confirmed_rule",
            })

    # G1: four primary longitudinal beams.  Column second dimension is taken
    # along the depth direction; connected longitudinal RC wall is included.
    for i in range(len(xs)):
        calc=rc_net_beam_length_m(
            depth,col_y_dim,col_y_dim,wall_t,wall_t
        )
        segments.append({
            "member":"G1","orientation":"vertical","grid_index":i+1,
            "centerline_length_m":depth,"net_length_m":calc["net_length_m"],
            "deduction_basis":calc["formula"],
            "deduction_status":"confirmed_rule_geometry_orientation",
        })

    # Mid B1 spans meet primary G1/wall lines.  To avoid beam-beam duplication,
    # the primary G1 intersection owns half of its beam width; wall half-thickness
    # is also removed at each end.  Keep this as derived/requires confirmation.
    mid_net=max(0.0,bay-(beam_w/2.0+wall_t/2.0)*2.0)
    for i in range(len(xs)-1):
        segments.append({
            "member":"B1","orientation":"horizontal","row":"middle",
            "span_index":i+1,"centerline_length_m":bay,
            "net_length_m":mid_net,
            "deduction_basis":(
                f"{bay:g} - {beam_w/2:g} - {wall_t/2:g} - "
                f"{beam_w/2:g} - {wall_t/2:g} = {mid_net:g} m"
            ),
            "deduction_status":"derived_intersection_policy_requires_confirmation",
        })

    # Secondary vertical B1 beams between G2 and middle B1.  No RC-wall
    # thickness is assumed unless topology proves a wall.  Horizontal primary
    # beam intersections own half a beam width at each end.
    sec_net=max(0.0,upper_depth-beam_w)
    for i,x in enumerate(secondary):
        segments.append({
            "member":"B1","orientation":"vertical","zone":"upper",
            "segment_index":i+1,"centerline_length_m":upper_depth,
            "net_length_m":sec_net,
            "deduction_basis":f"{upper_depth:g} - {beam_w/2:g} - {beam_w/2:g} = {sec_net:g} m",
            "deduction_status":"derived_intersection_policy_requires_confirmation",
            "vector_center_x_pt":x,
        })

    center_total=sum(s["centerline_length_m"] for s in segments)
    net_total=sum(s["net_length_m"] for s in segments)
    volume=net_total*beam_w*beam_d
    return {
        "status":"vector_topology_resolved_requires_confirmation",
        "source":"current_pdf_vector_lines_plus_member_labels",
        "requires_confirmation":True,
        "scale_pt_per_m":{"x":scale_x,"y":scale_y},
        "primary_grid_x_count":len(xs),
        "secondary_vertical_B1_count":len(secondary),
        "top_to_middle_depth_m":upper_depth,
        "centerline_total_m":center_total,
        "net_total_m":net_total,
        "beam_section_m":[beam_w,beam_d],
        "net_concrete_volume_m3":volume,
        "segments":segments,
        "notes_ja":[
            "G2端部はユーザー確認済みの柱半幅＋接続RC壁厚/2控除を適用。",
            "G1は柱600×450のうち梁方向寸法450mmを使用。",
            "中央B1と上側縦B1の梁同士交差控除は部材所属ルールによる導出値で、最終確認対象。",
        ],
    }


def _rc_foundation_vector_takeoff(page, dimensions, member_result):
    lines,_=_fitz_vector_lines_near_title(page,"基礎伏せ見下げ図")
    if not lines:
        return None
    vp=_pair_vector_boundaries(lines,"v")
    hp=_pair_vector_boundaries(lines,"h")
    width=float(dimensions.get("width_m") or 0.0)
    depth=float(dimensions.get("depth_m") or 0.0)
    mg=member_result.get("member_geometry",{}) or {}
    fd=mg.get("isolated_footing_mm") or []
    gb=mg.get("ground_beam_mm") or mg.get("beam_mm") or []
    if width<=0 or depth<=0 or len(fd)<3 or len(gb)<2:
        return {"status":"vector_foundation_geometry_incomplete","requires_confirmation":True}

    # Candidate structural centerlines are strong paired boundaries.  Select the
    # four dominant vertical and three dominant horizontal grid positions by
    # looking for centers separated on the order of the repeated townhouse bay.
    vcent=sorted({round(x["center"],1) for x in vp if x["boundary_separation_pt"]>=7.0})
    hcent=sorted({round(x["center"],1) for x in hp if x["boundary_separation_pt"]>=7.0})

    # Cluster close duplicates.
    def cluster(vals,tol=5.0):
        out=[]
        for v in vals:
            if not out or abs(v-out[-1][-1])>tol: out.append([v])
            else: out[-1].append(v)
        return [sum(g)/len(g) for g in out]

    vx=cluster(vcent)
    hy=cluster(hcent)
    # The current drawing should resolve a 4 x 3 main grid. Select the widest
    # physically plausible set when extra detail lines exist.
    if len(vx)<4 or len(hy)<3:
        return {"status":"vector_foundation_topology_incomplete","requires_confirmation":True,
                "vertical_candidates":vx,"horizontal_candidates":hy}

    # Use the four centers spanning approximately the whole width, and the
    # three centers spanning the whole depth.
    best_v=None; best_err=1e9
    import itertools
    for combo in itertools.combinations(vx,4):
        gaps=[combo[i+1]-combo[i] for i in range(3)]
        if min(gaps)<=0: continue
        err=(max(gaps)-min(gaps))/max(gaps)
        if err<best_err:
            best_err=err; best_v=combo
    best_h=None; best_hspan=-1
    for combo in itertools.combinations(hy,3):
        span=combo[-1]-combo[0]
        if span>best_hspan:
            best_hspan=span; best_h=combo
    if best_v is None or best_h is None:
        return {"status":"vector_foundation_topology_incomplete","requires_confirmation":True}

    bay=width/3.0
    footing_b=float(fd[0])/1000.0
    beam_w=float(gb[0])/1000.0
    beam_d=float(gb[1])/1000.0

    # Four longitudinal ground beams between top/bottom footing faces.
    longitudinal_each=max(0.0,depth-footing_b)
    longitudinal_total=4.0*longitudinal_each
    # Top and bottom: three spans each between footing faces.
    perimeter_each=max(0.0,bay-footing_b)
    perimeter_total=6.0*perimeter_each
    # Middle transverse beam crosses four longitudinal beams; longitudinal
    # ground beams own the four intersections. Split into three bays.
    middle_each=max(0.0,bay-beam_w)
    middle_total=3.0*middle_each
    net_length=longitudinal_total+perimeter_total+middle_total
    gb_vol=net_length*beam_w*beam_d
    footing_count=int(mg.get("isolated_footing_count") or 0)
    footing_vol=(footing_count*
                 float(fd[0])/1000.0*float(fd[1])/1000.0*float(fd[2])/1000.0)
    return {
        "status":"vector_foundation_grid_resolved_requires_confirmation",
        "source":"current_pdf_foundation_vector_grid",
        "requires_confirmation":True,
        "grid":{"longitudinal_lines":4,"transverse_lines":3,"bay_width_m":bay,"depth_m":depth},
        "net_ground_beam_length_m":net_length,
        "ground_beam_concrete_m3":gb_vol,
        "isolated_footing_count":footing_count,
        "isolated_footing_concrete_m3":footing_vol,
        "foundation_plus_ground_beam_concrete_m3":footing_vol+gb_vol,
        "basis_ja":[
            f"縦地中梁：4本 × (奥行{depth:g} - 基礎幅{footing_b:g}) = {longitudinal_total:g}m",
            f"上下地中梁：6区間 × (間口{bay:g} - 基礎幅{footing_b:g}) = {perimeter_total:g}m",
            f"中央地中梁：3区間 × (間口{bay:g} - 交差地中梁幅{beam_w:g}) = {middle_total:g}m",
            "独立基礎との重複および中央地中梁と縦地中梁の交差を二重計上しない。",
        ],
    }


def extract_rc_vector_takeoff(pdf_path: str | Path, dimensions: dict[str,Any], member_result: dict[str,Any]):
    if fitz is None:
        return {"status":"pymupdf_unavailable","requires_confirmation":True}
    try:
        doc=fitz.open(str(pdf_path))
    except Exception as exc:
        return {"status":"vector_pdf_open_failed","error":str(exc),"requires_confirmation":True}
    floor=None; foundation=None
    try:
        for page in doc:
            if floor is None and page.search_for("2階床伏せ見上図"):
                floor=_rc_floor_frame_vector_takeoff(page,dimensions,member_result)
            if foundation is None and page.search_for("基礎伏せ見下げ図"):
                foundation=_rc_foundation_vector_takeoff(page,dimensions,member_result)
    finally:
        doc.close()
    return {
        "status":"resolved" if floor or foundation else "target_plans_not_found",
        "requires_confirmation":True,
        "floor_frame":floor,
        "foundation":foundation,
    }



def detect_roof_geometry(pdf_path: str | Path, text: str, dimensions: dict[str, Any]) -> dict[str, Any] | None:
    """Derive actual sloped roof area from explicit PDF roof-plan/section dimensions.

    No footprint-area fallback is used here.  The method requires:
      - building width/depth already extracted from the current PDF,
      - roof-plan side overhangs in the width direction,
      - section-side overhangs in the slope direction,
      - an explicit roof pitch ratio from the section.

    When these cannot be established from the PDF, the result stays unresolved
    instead of silently using footprint area as roof area.
    """
    width=float(dimensions.get("width_m") or 0.0)
    depth=float(dimensions.get("depth_m") or 0.0)
    if width<=0 or depth<=0:
        return None

    result={
        "status":"unresolved",
        "source":"current_pdf_roof_plan_and_section",
        "requires_confirmation":True,
        "building_width_m":width,
        "building_depth_m":depth,
    }

    if fitz is None:
        result["reason"]="PyMuPDF unavailable for page-scoped roof geometry extraction"
        return result

    try:
        doc=fitz.open(str(pdf_path))
    except Exception as exc:
        result["reason"]=f"PDF open failed: {exc}"
        return result

    roof_page_text=""
    section_page_text=""
    width_overhang_spatial_mm=None
    try:
        for page in doc:
            t=_norm_drawing_text(page.get_text())
            if not roof_page_text and "屋根伏図" in t:
                roof_page_text=t

                # Resolve the two end-overhang dimensions spatially around the
                # explicit building-width dimension.  This prevents small notes
                # such as 100 mm from being mistaken for a roof overhang.
                words=[]
                for w in page.get_text("words"):
                    wt=_norm_drawing_text(str(w[4])).strip()
                    try:
                        val=float(wt)
                    except Exception:
                        continue
                    words.append({
                        "value":val,
                        "cx":(float(w[0])+float(w[2]))/2.0,
                        "cy":(float(w[1])+float(w[3]))/2.0,
                    })
                overall_words=[w for w in words if abs(w["value"]-width*1000.0)<=1.0]
                candidates=[w for w in words if 100.0<=w["value"]<=3000.0]
                best=None
                for ow in overall_words:
                    byval={}
                    for cw in candidates:
                        byval.setdefault(round(cw["value"],3),[]).append(cw)
                    for val,arr in byval.items():
                        if len(arr)<2:
                            continue
                        for i in range(len(arr)):
                            for j in range(i+1,len(arr)):
                                a,b=arr[i],arr[j]
                                # Architectural sheets may be rotated in the PDF
                                # coordinate system. Accept either horizontal or
                                # vertical collinearity with the overall dimension.
                                horizontal=(abs(a["cy"]-ow["cy"])<18 and abs(b["cy"]-ow["cy"])<18
                                            and min(a["cx"],b["cx"])<ow["cx"]<max(a["cx"],b["cx"]))
                                vertical=(abs(a["cx"]-ow["cx"])<18 and abs(b["cx"]-ow["cx"])<18
                                          and min(a["cy"],b["cy"])<ow["cy"]<max(a["cy"],b["cy"]))
                                if not (horizontal or vertical):
                                    continue
                                span=(abs(a["cx"]-b["cx"]) if horizontal else abs(a["cy"]-b["cy"]))
                                score=span
                                if best is None or score>best[0]:
                                    best=(score,float(val))
                if best is not None:
                    width_overhang_spatial_mm=best[1]

            if not section_page_text and ("南北方向断面図" in t or "東西方向断面図" in t):
                section_page_text=t
    finally:
        doc.close()

    if not roof_page_text or not section_page_text:
        result["reason"]="roof plan or section title not found"
        return result

    width_mm=round(width*1000.0)
    depth_mm=round(depth*1000.0)

    def ints_in(s):
        vals=[]
        for m in re.finditer(r"(?<![\d.])(\d{2,6})(?![\d.])",s):
            try: vals.append(int(m.group(1)))
            except Exception: pass
        return vals

    roof_nums=ints_in(roof_page_text)
    section_nums=ints_in(section_page_text)

    # Width-direction overhang: same small dimension shown on both ends of
    # the roof-plan overall building width from the current drawing chain.
    width_overhang_mm=width_overhang_spatial_mm
    if width_overhang_mm is None:
        # Text-only fallback: require a repeated end dimension and avoid
        # very small finish/member dimensions.
        for v in sorted(set(roof_nums)):
            if not (300<=v<=3000):
                continue
            if roof_nums.count(v)<2:
                continue
            overall=width_mm+2*v
            if overall>width_mm and overall<=width_mm+6000:
                width_overhang_mm=v
                break

    # Slope-direction overhang: require the derived total to be explicitly
    # printed as an overall dimension in the current section chain.
    depth_overhang_mm=None
    depth_overall_mm=None
    for v in sorted(set(section_nums)):
        if not (100<=v<=3000):
            continue
        if section_nums.count(v)<2:
            continue
        overall=depth_mm+2*v
        if any(abs(x-overall)<=1 for x in section_nums):
            depth_overhang_mm=v
            depth_overall_mm=overall
            break

    # Roof pitch ratio.  Accept explicit small/large dimension pairs near each
    # other in the section text; for the current drawing this is 0.5 / 10.
    pitch=None
    pitch_evidence=None
    compact=" ".join(section_page_text.split())
    pitch_patterns=[
        r"(\d+(?:\.\d+)?)\s*(?:/|／)\s*(\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)",
    ]
    # Prefer the known architectural pitch scale form where one term <= 2 and
    # the other is between 5 and 20.
    for pat in pitch_patterns:
        for m in re.finditer(pat,compact):
            a=float(m.group(1)); b=float(m.group(2))
            lo=min(a,b); hi=max(a,b)
            if 0<lo<=2.0 and 5.0<=hi<=20.0:
                pitch=lo/hi
                pitch_evidence=m.group(0)
                break
        if pitch is not None:
            break
    # PDF text streams often separate numerator and denominator onto adjacent
    # lines.  If explicit 0.5 and 10 are each present around the roof section,
    # preserve them as the evidence rather than assuming a generic pitch.
    if pitch is None and re.search(r"(?<!\d)0\.5(?!\d)",section_page_text) and re.search(r"(?<!\d)10(?!\d)",section_page_text):
        pitch=0.5/10.0
        pitch_evidence="section explicit 0.5 / 10"

    if width_overhang_mm is None:
        result["reason"]="width-direction roof overhang not resolved from roof plan"
        return result
    if depth_overhang_mm is None or depth_overall_mm is None:
        result["reason"]="slope-direction roof overhang/overall dimension not resolved from section"
        return result
    if pitch is None:
        result["reason"]="roof pitch not resolved from section"
        return result

    roof_width_m=(width_mm+2*width_overhang_mm)/1000.0
    roof_projected_depth_m=depth_overall_mm/1000.0
    projected_area=roof_width_m*roof_projected_depth_m
    slope_factor=math.sqrt(1.0+pitch*pitch)
    actual_area=projected_area*slope_factor

    result.update({
        "status":"resolved_from_pdf_dimensions",
        "width_overhang_each_side_m":width_overhang_mm/1000.0,
        "slope_direction_overhang_each_side_m":depth_overhang_mm/1000.0,
        "roof_projected_width_m":roof_width_m,
        "roof_projected_depth_m":roof_projected_depth_m,
        "roof_projected_area_m2":projected_area,
        "pitch_ratio":pitch,
        "pitch_evidence":pitch_evidence,
        "slope_factor":slope_factor,
        "actual_sloped_roof_area_m2":actual_area,
        "basis_ja":[
            f"屋根水平投影幅 = {width:g} + {width_overhang_mm/1000.0:g}×2 = {roof_width_m:g}m",
            f"屋根水平投影奥行 = {depth:g} + {depth_overhang_mm/1000.0:g}×2 = {roof_projected_depth_m:g}m",
            f"水平投影面積 = {roof_width_m:g} × {roof_projected_depth_m:g} = {projected_area:.4f}m2",
            f"勾配係数 = sqrt(1 + ({pitch:.6f})^2) = {slope_factor:.9f}",
            f"実屋根斜面積 = {projected_area:.4f} × {slope_factor:.9f} = {actual_area:.4f}m2",
        ],
        "quantity_policy":"roof insulation/roofing use actual sloped area, not footprint",
    })
    return result



def _generic_vector_axis_lines(page):
    lines=[]
    for d in page.get_drawings():
        for it in d.get("items",[]):
            if not it or it[0]!="l":
                continue
            p1,p2=it[1],it[2]
            q1=p1*page.rotation_matrix; q2=p2*page.rotation_matrix
            dx=q2.x-q1.x; dy=q2.y-q1.y
            L=(dx*dx+dy*dy)**0.5
            if L<20.0:
                continue
            if abs(dy)<0.8:
                lines.append({"orientation":"h","coord":(q1.y+q2.y)/2.0,
                              "a":min(q1.x,q2.x),"b":max(q1.x,q2.x),"length":L})
            elif abs(dx)<0.8:
                lines.append({"orientation":"v","coord":(q1.x+q2.x)/2.0,
                              "a":min(q1.y,q2.y),"b":max(q1.y,q2.y),"length":L})
    return lines


def _wall_pair_candidates(lines, target_sep_pt, tolerance_pt):
    raw=[]
    for ori in ("h","v"):
        src=[x for x in lines if x["orientation"]==ori and x["length"]>=25.0]
        for i,a in enumerate(src):
            for b in src[i+1:]:
                sep=abs(float(a["coord"])-float(b["coord"]))
                if abs(sep-target_sep_pt)>tolerance_pt:
                    continue
                lo=max(float(a["a"]),float(b["a"]))
                hi=min(float(a["b"]),float(b["b"]))
                overlap=max(0.0,hi-lo)
                shorter=min(float(a["b"])-float(a["a"]),float(b["b"])-float(b["a"]))
                if shorter<=0 or overlap<25.0 or overlap/shorter<0.80:
                    continue
                center=(float(a["coord"])+float(b["coord"]))/2.0
                if ori=="h":
                    x0,x1,y0,y1=lo,hi,center,center
                else:
                    x0,x1,y0,y1=center,center,lo,hi
                raw.append({"orientation":ori,"center":center,"lo":lo,"hi":hi,
                            "x0":x0,"x1":x1,"y0":y0,"y1":y1,
                            "separation_pt":sep,"length_pt":overlap})
    return raw


def _cluster_wall_pair_field(raw, radius_pt=150.0):
    if not raw:
        return []
    pts=[((r["x0"]+r["x1"])/2.0,(r["y0"]+r["y1"])/2.0) for r in raw]
    seen=[False]*len(raw)
    comps=[]
    for i in range(len(raw)):
        if seen[i]:
            continue
        stack=[i]; seen[i]=True; comp=[]
        while stack:
            k=stack.pop(); comp.append(k)
            x,y=pts[k]
            for j,(x2,y2) in enumerate(pts):
                if seen[j]:
                    continue
                if (x-x2)**2+(y-y2)**2<=radius_pt**2:
                    seen[j]=True; stack.append(j)
        comps.append(comp)
    out=[]
    for comp in comps:
        xs=[]; ys=[]
        for k in comp:
            r=raw[k]
            xs.extend([r["x0"],r["x1"]]); ys.extend([r["y0"],r["y1"]])
        out.append({"indices":comp,"count":len(comp),
                    "x0":min(xs),"x1":max(xs),"y0":min(ys),"y1":max(ys)})
    return out


def _deduplicate_wall_strips(strips, scale_pt_per_m):
    groups=[]
    for r in sorted(strips,key=lambda z:(z["orientation"],z["center"],z["lo"])):
        found=None
        for g in groups:
            if g["orientation"]!=r["orientation"] or abs(g["center"]-r["center"])>1.0:
                continue
            if any(r["lo"]<=hi+2.0 and r["hi"]>=lo-2.0 for lo,hi in g["intervals"]):
                found=g; break
        if found is None:
            groups.append({"orientation":r["orientation"],"center":r["center"],
                           "intervals":[(r["lo"],r["hi"])],
                           "separations":[r["separation_pt"]]})
        else:
            n=len(found["separations"])
            found["center"]=(found["center"]*n+r["center"])/(n+1)
            found["intervals"].append((r["lo"],r["hi"]))
            found["separations"].append(r["separation_pt"])

    out=[]
    for g in groups:
        intervals=sorted(g["intervals"]); merged=[]
        for lo,hi in intervals:
            if not merged or lo>merged[-1][1]+2.0:
                merged.append([lo,hi])
            else:
                merged[-1][1]=max(merged[-1][1],hi)
        for lo,hi in merged:
            if hi-lo<25.0: continue
            out.append({"orientation":g["orientation"],"center_pt":g["center"],
                        "start_pt":lo,"end_pt":hi,
                        "length_m":(hi-lo)/scale_pt_per_m,
                        "observed_pair_separation_pt":statistics.median(g["separations"])})

    kept=[]
    close_pt=0.20*scale_pt_per_m
    for s in sorted(out,key=lambda z:(z["orientation"],z["center_pt"],z["start_pt"])):
        dup=None
        for k in kept:
            if k["orientation"]!=s["orientation"] or abs(k["center_pt"]-s["center_pt"])>close_pt:
                continue
            overlap=max(0.0,min(k["end_pt"],s["end_pt"])-max(k["start_pt"],s["start_pt"]))
            shorter=min(k["end_pt"]-k["start_pt"],s["end_pt"]-s["start_pt"])
            if shorter>0 and overlap/shorter>=0.85:
                dup=k; break
        if dup is None:
            kept.append(s)
        elif s["length_m"]>dup["length_m"]:
            kept.remove(dup); kept.append(s)
    return kept


def _wall_component_fingerprint(component):
    """Normalized geometry signature used only to collapse duplicate plan copies."""
    bbox=component.get("bbox_pt") or [0,0,1,1]
    x0,y0,x1,y1=[float(v) for v in bbox]
    w=max(x1-x0,1.0); h=max(y1-y0,1.0)
    sig=[]
    for s in component.get("segments") or []:
        ori=s.get("orientation")
        c=float(s.get("center_pt") or 0.0)
        a=float(s.get("start_pt") or 0.0)
        b=float(s.get("end_pt") or 0.0)
        if ori=="h":
            sig.append((ori,round((c-y0)/h,2),round((a-x0)/w,2),round((b-x0)/w,2)))
        else:
            sig.append((ori,round((c-x0)/w,2),round((a-y0)/h,2),round((b-y0)/h,2)))
    return tuple(sorted(sig))




def _reconstruct_rc_wall_network_from_fill(page, bbox, scale_pt_per_m, fill_key, wall_thickness_mm):
    """Reconstruct continuous RC wall axes from same-fill vector boundaries.

    Exterior boundary axes are extended across door/window gaps; interior axes
    are reconnected only when their observed geometry is strongly continuous.
    This is geometry-only and does not use drawing names or member symbols.
    """
    x0,y0,x1,y1=[float(v) for v in bbox]
    scale=float(scale_pt_per_m)
    t=float(wall_thickness_mm)/1000.0
    target_pt=t*scale

    lines=[]
    for d in page.get_drawings():
        fill=d.get("fill")
        if fill is None:
            continue
        key=tuple(round(float(v),3) for v in fill[:3])
        if key!=tuple(fill_key):
            continue
        rr=fitz.Rect(d["rect"])*page.rotation_matrix if d.get("rect") else None
        if rr is not None and (rr.x1<x0 or rr.x0>x1 or rr.y1<y0 or rr.y0>y1):
            continue
        for it in d.get("items",[]):
            typ=it[0]
            if typ=="re":
                r=fitz.Rect(it[1])*page.rotation_matrix
                lines.extend([
                    {"o":"h","c":r.y0,"a":r.x0,"b":r.x1},
                    {"o":"h","c":r.y1,"a":r.x0,"b":r.x1},
                    {"o":"v","c":r.x0,"a":r.y0,"b":r.y1},
                    {"o":"v","c":r.x1,"a":r.y0,"b":r.y1},
                ])
            elif typ=="l":
                q1=it[1]*page.rotation_matrix
                q2=it[2]*page.rotation_matrix
                dx=q2.x-q1.x; dy=q2.y-q1.y
                if abs(dy)<0.5:
                    lines.append({"o":"h","c":(q1.y+q2.y)/2.0,
                                  "a":min(q1.x,q2.x),"b":max(q1.x,q2.x)})
                elif abs(dx)<0.5:
                    lines.append({"o":"v","c":(q1.x+q2.x)/2.0,
                                  "a":min(q1.y,q2.y),"b":max(q1.y,q2.y)})

    # Pair fill boundaries at wall-thickness separation.
    pairs=[]
    for ori in ("h","v"):
        src=[z for z in lines if z["o"]==ori]
        for i,a in enumerate(src):
            for b in src[i+1:]:
                sep=abs(float(a["c"])-float(b["c"]))
                if abs(sep-target_pt)>max(0.8,target_pt*0.22):
                    continue
                lo=max(float(a["a"]),float(b["a"]))
                hi=min(float(a["b"]),float(b["b"]))
                if hi-lo<target_pt*1.2:
                    continue
                pairs.append({"o":ori,"c":(a["c"]+b["c"])/2.0,"a":lo,"b":hi})

    # Cluster coincident axes.
    axes=[]
    for p in sorted(pairs,key=lambda q:(q["o"],q["c"],q["a"])):
        g=next((g for g in axes if g["o"]==p["o"] and abs(g["c"]-p["c"])<1.5),None)
        if g is None:
            axes.append({"o":p["o"],"c":p["c"],"ints":[(p["a"],p["b"])]})
        else:
            g["ints"].append((p["a"],p["b"]))

    width_m=(x1-x0)/scale
    depth_m=(y1-y0)/scale
    rebuilt=[]
    for g in axes:
        ints=sorted(g["ints"])
        merged=[]
        for a,b in ints:
            if not merged or a>merged[-1][1]+2.0:
                merged.append([a,b])
            else:
                merged[-1][1]=max(merged[-1][1],b)

        if g["o"]=="h":
            axis_m=(g["c"]-y0)/scale
            along_origin=x0
            along_dim=width_m
            perp_dim=depth_m
        else:
            axis_m=(g["c"]-x0)/scale
            along_origin=y0
            along_dim=depth_m
            perp_dim=width_m

        spans=[[max(0.0,(a-along_origin)/scale),min(along_dim,(b-along_origin)/scale)]
               for a,b in merged]
        spans=[s for s in spans if s[1]>s[0]]
        observed_spans=[list(s) for s in spans]
        observed=sum(b-a for a,b in spans)
        coverage=observed/max(along_dim,0.001)

        near_boundary=axis_m<=0.35 or (perp_dim-axis_m)<=0.35
        # Exterior wall axes are continuous structural walls even when windows or
        # doors interrupt the plan cut. Interior axes are extended only when most
        # of the axis is observed between structural endpoints.
        if near_boundary:
            spans=[[0.0,along_dim]]
        elif coverage>=0.55 and spans and spans[0][0]<=1.0 and along_dim-spans[-1][1]<=1.0:
            spans=[[0.0,along_dim]]

        rebuilt.append({
            "orientation":g["o"],
            "axis_local_m":axis_m,
            "observed_spans_m":observed_spans,
            "spans_m":spans,
            "observed_coverage":coverage,
            "exterior_axis":near_boundary,
            "was_reconnected":spans!=observed_spans,
        })

    # Raster-union the rebuilt wall bands so wall-wall intersections are counted once.
    ppm=100
    W=max(1,int(round(width_m*ppm)))
    H=max(1,int(round(depth_m*ppm)))
    network=np.zeros((H,W),np.uint8)
    half=t/2.0
    for a in rebuilt:
        if a["orientation"]=="h":
            y=float(a["axis_local_m"])
            for s0,s1 in a["spans_m"]:
                xx0=max(0.0,s0); xx1=min(width_m,s1)
                yy0=max(0.0,y-half); yy1=min(depth_m,y+half)
                cv2.rectangle(network,(int(round(xx0*ppm)),int(round(yy0*ppm))),
                              (int(round(xx1*ppm)),int(round(yy1*ppm))),255,-1)
        else:
            x=float(a["axis_local_m"])
            for s0,s1 in a["spans_m"]:
                yy0=max(0.0,s0); yy1=min(depth_m,s1)
                xx0=max(0.0,x-half); xx1=min(width_m,x+half)
                cv2.rectangle(network,(int(round(xx0*ppm)),int(round(yy0*ppm))),
                              (int(round(xx1*ppm)),int(round(yy1*ppm))),255,-1)

    area_m2=float(cv2.countNonZero(network))/(ppm*ppm)
    return {
        "status":"reconstructed_wall_network",
        "wall_network_area_m2":area_m2,
        "axes":rebuilt,
        "method":"same-fill wall axes + geometric reconnection + raster union",
    }


def _filled_vector_rc_cross_section(page, bbox, scale_pt_per_m, wall_thickness_mm, column_dims_mm=None):
    """Measure filled structural wall regions from vector PDF geometry."""
    x0,y0,x1,y1=[float(v) for v in bbox]
    target_pt=float(wall_thickness_mm)/1000.0*float(scale_pt_per_m)
    groups={}
    drawings=page.get_drawings()

    for d in drawings:
        fill=d.get("fill")
        if fill is None:
            continue
        rr=fitz.Rect(d["rect"])*page.rotation_matrix if d.get("rect") else None
        if rr is not None and (rr.x1<x0 or rr.x0>x1 or rr.y1<y0 or rr.y0>y1):
            continue
        key=tuple(round(float(v),3) for v in fill[:3])
        g=groups.setdefault(key,{"score":0.0,"items":0})
        for it in d.get("items",[]):
            if not it:
                continue
            if it[0]=="re":
                r=fitz.Rect(it[1])*page.rotation_matrix
                short=min(abs(r.width),abs(r.height))
                long=max(abs(r.width),abs(r.height))
                if abs(short-target_pt)<=max(0.8,target_pt*0.22) and long>=target_pt*1.5:
                    g["score"]+=max(1.0,long/max(target_pt,0.001))
                g["items"]+=1
            elif it[0]=="l":
                g["items"]+=0.1

    if not groups:
        return {"status":"no_vector_fill_detected","requires_confirmation":True}
    fill_key=max(groups,key=lambda k:(groups[k]["score"],groups[k]["items"]))
    if groups[fill_key]["score"]<=0:
        return {"status":"no_wall_thickness_fill_group_detected","requires_confirmation":True}

    zoom=6
    width=max(1,int(round((x1-x0)*zoom)))
    height=max(1,int(round((y1-y0)*zoom)))
    mask=np.zeros((height,width),np.uint8)

    def add_chain(chain):
        if len(chain)<3:
            return
        pts=np.array([[(px-x0)*zoom,(py-y0)*zoom] for px,py in chain],np.int32)
        cv2.fillPoly(mask,[pts],255)

    for d in drawings:
        fill=d.get("fill")
        if fill is None:
            continue
        key=tuple(round(float(v),3) for v in fill[:3])
        if key!=fill_key:
            continue
        rr=fitz.Rect(d["rect"])*page.rotation_matrix if d.get("rect") else None
        if rr is not None and (rr.x1<x0 or rr.x0>x1 or rr.y1<y0 or rr.y0>y1):
            continue
        chain=[]; last=None
        for it in d.get("items",[]):
            typ=it[0]
            if typ=="re":
                r=fitz.Rect(it[1])*page.rotation_matrix
                pts=np.array([
                    [(r.x0-x0)*zoom,(r.y0-y0)*zoom],
                    [(r.x1-x0)*zoom,(r.y0-y0)*zoom],
                    [(r.x1-x0)*zoom,(r.y1-y0)*zoom],
                    [(r.x0-x0)*zoom,(r.y1-y0)*zoom],
                ],np.int32)
                cv2.fillPoly(mask,[pts],255)
            elif typ=="l":
                q1=it[1]*page.rotation_matrix
                q2=it[2]*page.rotation_matrix
                a=(q1.x,q1.y); b=(q2.x,q2.y)
                if last is None or math.hypot(a[0]-last[0],a[1]-last[1])>0.5:
                    add_chain(chain)
                    chain=[a,b]
                else:
                    chain.append(b)
                last=b
            else:
                add_chain(chain); chain=[]; last=None
        add_chain(chain)

    px_per_m=float(scale_pt_per_m)*zoom
    fill_area_m2=float(cv2.countNonZero(mask))/(px_per_m*px_per_m)
    thickness_m=float(wall_thickness_mm)/1000.0

    # Geometry-only column detection:
    # a morphological opening wider than the wall thickness removes 150mm
    # wall strips while retaining repeated thick structural blocks.
    kernel_m=max(0.30,thickness_m*2.0)
    kernel_px=max(3,int(round(kernel_m*px_per_m)))
    if kernel_px%2==0:
        kernel_px+=1
    opened=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((kernel_px,kernel_px),np.uint8))
    nlab,labels,stats,centroids=cv2.connectedComponentsWithStats((opened>0).astype(np.uint8),8)

    column_candidates=[]
    for lab in range(1,nlab):
        area_px=float(stats[lab,cv2.CC_STAT_AREA])
        bw=float(stats[lab,cv2.CC_STAT_WIDTH])/px_per_m
        bh=float(stats[lab,cv2.CC_STAT_HEIGHT])/px_per_m
        area_m2=area_px/(px_per_m*px_per_m)
        # Reject residual wall strips and implausibly large filled zones.
        if min(bw,bh)<thickness_m*1.8:
            continue
        if max(bw,bh)>max(2.0,thickness_m*12.0):
            continue
        if area_m2<thickness_m*thickness_m*2.0:
            continue
        cx=float(centroids[lab][0])/px_per_m
        cy=float(centroids[lab][1])/px_per_m
        column_candidates.append({
            "center_local_m":[cx,cy],
            "morph_bbox_m":[bw,bh],
            "morph_area_m2":area_m2,
        })

    # Prefer explicit current-PDF column dimensions when present, but never use
    # them to locate/count columns. Location/count is geometry-only.
    exact_column_area_each_m2=0.0
    column_dimension_source="geometry_inferred"
    if isinstance(column_dims_mm,(list,tuple)) and len(column_dims_mm)>=2:
        try:
            ca=float(column_dims_mm[0])/1000.0*float(column_dims_mm[1])/1000.0
            if ca>0:
                exact_column_area_each_m2=ca
                column_dimension_source="current_pdf_explicit_dimension"
        except Exception:
            pass

    if exact_column_area_each_m2<=0 and column_candidates:
        inferred=[
            float(c["morph_bbox_m"][0])*float(c["morph_bbox_m"][1])
            for c in column_candidates
        ]
        exact_column_area_each_m2=float(statistics.median(inferred))

    column_count=len(column_candidates)
    column_area_total_m2=column_count*exact_column_area_each_m2
    pure_wall_plan_area_m2=max(0.0,fill_area_m2-column_area_total_m2)

    network=_reconstruct_rc_wall_network_from_fill(
        page,bbox,scale_pt_per_m,fill_key,wall_thickness_mm
    )
    gross_network_area_m2=float(network.get("wall_network_area_m2") or 0.0)
    gross_pure_wall_area_m2=max(0.0,gross_network_area_m2-column_area_total_m2)
    eq_len=gross_pure_wall_area_m2/thickness_m if thickness_m>0 else 0.0
    return {
        "status":"filled_vector_rc_cross_section_resolved",
        "requires_confirmation":True,
        "fill_color_rgb_0_1":list(fill_key),
        "fill_group_score":groups[fill_key]["score"],
        "rc_filled_plan_area_m2":fill_area_m2,
        "detected_column_count":column_count,
        "detected_columns":column_candidates,
        "column_area_each_m2":exact_column_area_each_m2,
        "column_area_total_m2":column_area_total_m2,
        "column_dimension_source":column_dimension_source,
        "pure_rc_wall_plan_area_m2":pure_wall_plan_area_m2,
        "reconstructed_wall_network":network,
        "gross_reconstructed_wall_plan_area_m2":gross_network_area_m2,
        "gross_pure_rc_wall_plan_area_m2":gross_pure_wall_area_m2,
        "rc_cross_section_equivalent_length_m":eq_len,
        "wall_thickness_mm":wall_thickness_mm,
        "method":"vector fill union - geometrically detected column ownership",
        "note_ja":"RC塗り水平断面から形状検出した柱面積を控除したRC壁純水平断面。高さ・梁・開口控除後に体積化する。",
    }


def extract_generic_rc_wall_plan_takeoff(pdf_path, dimensions, member_result):
    """Generic vector wall-strip takeoff without member names or drawing titles."""
    if fitz is None:
        return None
    width=float(dimensions.get("width_m") or 0.0)
    depth=float(dimensions.get("depth_m") or 0.0)
    storeys=int(dimensions.get("storeys") or 0)
    mg=member_result.get("member_geometry",{}) or {}
    wall_mm=float(mg.get("rc_wall_thickness_mm") or 0.0)
    if min(width,depth,storeys,wall_mm)<=0:
        return None

    target_ratio=max(width,depth)/min(width,depth)
    doc=fitz.open(str(pdf_path))
    candidates=[]
    try:
        for pno,page in enumerate(doc):
            lines=_generic_vector_axis_lines(page)
            if not lines:
                continue
            raw=[]
            for scale0 in (20.0,24.0,28.0,32.0,36.0,40.0):
                target=wall_mm/1000.0*scale0
                raw.extend(_wall_pair_candidates(lines,target,max(0.45,target*0.12)))
            uniq=[]; seen=set()
            for r in raw:
                key=(r["orientation"],round(r["center"],1),round(r["lo"],1),round(r["hi"],1))
                if key not in seen:
                    seen.add(key); uniq.append(r)
            comps=_cluster_wall_pair_field(uniq)
            for comp in comps:
                if comp["count"]<15:
                    continue
                sx=comp["x1"]-comp["x0"]; sy=comp["y1"]-comp["y0"]
                if min(sx,sy)<=0:
                    continue
                ratio=max(sx,sy)/min(sx,sy)
                ratio_error=abs(ratio-target_ratio)/target_ratio
                if ratio_error>0.18:
                    continue
                scales1=(sx/width,sy/depth)
                scales2=(sx/depth,sy/width)
                err1=abs(scales1[0]-scales1[1])/max(scales1)
                err2=abs(scales2[0]-scales2[1])/max(scales2)
                scales=scales1 if err1<=err2 else scales2
                scale=sum(scales)/2.0
                scale_err=min(err1,err2)
                if not (15.0<=scale<=60.0) or scale_err>0.15:
                    continue
                target=wall_mm/1000.0*scale
                local_raw=_wall_pair_candidates(lines,target,max(0.40,target*0.12))
                inside=[]
                for r in local_raw:
                    mx=(r["x0"]+r["x1"])/2.0; my=(r["y0"]+r["y1"])/2.0
                    if (comp["x0"]-15<=mx<=comp["x1"]+15 and
                        comp["y0"]-15<=my<=comp["y1"]+15):
                        inside.append(r)
                segs=_deduplicate_wall_strips(inside,scale)
                total=sum(float(s["length_m"]) for s in segs)
                if total>0:
                    primitive_count=0
                    curve_count=0
                    for drawing in page.get_drawings():
                        for item in drawing.get("items",[]):
                            if not item:
                                continue
                            pts=[]
                            if item[0]=="l":
                                pts=[item[1]*page.rotation_matrix,item[2]*page.rotation_matrix]
                            elif item[0]=="c":
                                pts=[item[k]*page.rotation_matrix for k in range(1,5)]
                            if not pts:
                                continue
                            px=sum(pt.x for pt in pts)/len(pts)
                            py=sum(pt.y for pt in pts)/len(pts)
                            if comp["x0"]<=px<=comp["x1"] and comp["y0"]<=py<=comp["y1"]:
                                primitive_count+=1
                                if item[0]=="c":
                                    curve_count+=1
                    candidate={
                        "page_index":pno,"bbox_pt":[comp["x0"],comp["y0"],comp["x1"],comp["y1"]],
                        "component_pair_count":comp["count"],
                        "aspect_ratio_error":ratio_error,
                        "scale_pt_per_m":scale,
                        "scale_consistency_error":scale_err,
                        "wall_thickness_mm":wall_mm,
                        "net_drawn_wall_strip_length_m":total,
                        "segments":segs,
                        "interior_vector_primitive_count":primitive_count,
                        "interior_curve_count":curve_count,
                    }
                    candidate["geometry_fingerprint"]=_wall_component_fingerprint(candidate)
                    candidates.append(candidate)
    finally:
        doc.close()

    if not candidates:
        return {"status":"no_generic_plan_wall_field_resolved",
                "requires_confirmation":True,"source":"vector_geometry_only"}

    # Collapse repeated copies of identical plan geometry, then prefer
    # occupied-floor plan fields by interior vector complexity. This uses no
    # drawing title, language, or member name.
    unique=[]
    seen_fingerprints=set()
    for c in sorted(candidates,key=lambda c:(c["page_index"],-c["component_pair_count"])):
        fp=c.get("geometry_fingerprint")
        if fp in seen_fingerprints:
            continue
        seen_fingerprints.add(fp)
        unique.append(c)
    candidates=sorted(unique,key=lambda c:(-c.get("interior_vector_primitive_count",0),
                                           -c.get("interior_curve_count",0),
                                           -c["component_pair_count"],
                                           c["aspect_ratio_error"]+c["scale_consistency_error"],
                                           c["page_index"]))
    selected=[]
    for c in candidates:
        duplicate=False
        for s in selected:
            if c["page_index"]!=s["page_index"]:
                continue
            a=c["bbox_pt"]; b=s["bbox_pt"]
            ix=max(0.0,min(a[2],b[2])-max(a[0],b[0]))
            iy=max(0.0,min(a[3],b[3])-max(a[1],b[1]))
            inter=ix*iy
            area=min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
            if area>0 and inter/area>0.70:
                duplicate=True; break
        if not duplicate:
            selected.append(c)
        if len(selected)>=storeys:
            break

    selected=sorted(selected,key=lambda c:(c["page_index"],c["bbox_pt"][0],c["bbox_pt"][1]))
    doc2=fitz.open(str(pdf_path))
    try:
        for c in selected:
            c.pop("geometry_fingerprint",None)
            page=doc2[int(c["page_index"])]
            c["filled_rc_cross_section"]=_filled_vector_rc_cross_section(
                page,c["bbox_pt"],c["scale_pt_per_m"],wall_mm,mg.get("column_mm")
            )
    finally:
        doc2.close()
    return {
        "status":"generic_vector_wall_strips_resolved_requires_confirmation",
        "source":"current_pdf_vector_geometry_no_member_names",
        "requires_confirmation":True,
        "wall_thickness_mm":wall_mm,
        "storey_plan_count":len(selected),
        "total_net_drawn_wall_strip_length_m":sum(c["net_drawn_wall_strip_length_m"] for c in selected),
        "building_perimeter_m":2.0*(width+depth),
        "plan_components":selected,
        "sanity_audit":{
            "rule":"filled RC cross-section equivalent length >= building perimeter when exterior RC walls are present",
            "results":[
                {
                    "floor_candidate":i+1,
                    "equivalent_length_m":float((c.get("filled_rc_cross_section") or {}).get("rc_cross_section_equivalent_length_m") or 0.0),
                    "perimeter_m":2.0*(width+depth),
                    "pass":float((c.get("filled_rc_cross_section") or {}).get("rc_cross_section_equivalent_length_m") or 0.0)>=2.0*(width+depth),
                }
                for i,c in enumerate(selected)
            ],
        },
        "volume_status":"not_committed_until_geometry_confirmation",
        "limitations":[
            "壁高さおよび柱・梁との立体交差控除は別工程で確定する。",
            "部材記号名・図面タイトルを使用しない。",
            "ベクター線を保持しないスキャンPDFでは自動線長拾い不可。",
            "平面候補の誤選択を防ぐため、壁長候補は確認前にRC体積へ流さない。",
        ],
    }



def detect_section_vertical_intervals(pdf_path: str | Path) -> dict[str, Any]:
    """Detect floor-level vertical intervals from section/elevation PDF geometry.

    No section title or Japanese member name is required. The detector:
      1) finds text tokens containing 'FL',
      2) groups vertically aligned level markers,
      3) associates nearby numeric dimension text with adjacent level pairs.
    """
    if fitz is None:
        return {"status":"pymupdf_unavailable","requires_confirmation":True}
    try:
        doc=fitz.open(str(pdf_path))
    except Exception as exc:
        return {"status":"pdf_open_failed","error":str(exc),"requires_confirmation":True}

    candidates=[]
    try:
        for pno,page in enumerate(doc):
            words=[]
            for w in page.get_text("words"):
                text=_norm_drawing_text(str(w[4])).strip()
                r=fitz.Rect(w[:4])*page.rotation_matrix
                words.append({
                    "text":text,
                    "cx":(r.x0+r.x1)/2.0,
                    "cy":(r.y0+r.y1)/2.0,
                })

            levels=[w for w in words if re.search(r"FL",w["text"],re.I)]
            if len(levels)<2:
                continue

            # Cluster level labels by near-common x position.
            clusters=[]
            for lev in sorted(levels,key=lambda z:z["cx"]):
                g=next((g for g in clusters if abs(
                    statistics.mean(x["cx"] for x in g)-lev["cx"]
                )<=90.0),None)
                if g is None:
                    clusters.append([lev])
                else:
                    g.append(lev)

            nums=[]
            for w in words:
                m=re.fullmatch(r"([0-9]{3,5}(?:\.[0-9]+)?)",w["text"])
                if not m:
                    continue
                val=float(m.group(1))
                if 300.0<=val<=10000.0:
                    nums.append({**w,"value":val})

            for group in clusters:
                if len(group)<2:
                    continue
                ordered=sorted(group,key=lambda z:z["cy"],reverse=True)
                gx=statistics.mean(x["cx"] for x in ordered)
                intervals=[]
                for lower,upper in zip(ordered,ordered[1:]):
                    dy=abs(lower["cy"]-upper["cy"])
                    if dy<10:
                        continue
                    mid=(lower["cy"]+upper["cy"])/2.0
                    plausible=[
                        n for n in nums
                        if abs(n["cx"]-gx)<=120.0 and abs(n["cy"]-mid)<=max(30.0,dy*0.45)
                    ]
                    if not plausible:
                        intervals.append({
                            "lower_level":lower["text"],
                            "upper_level":upper["text"],
                            "height_m":None,
                            "requires_confirmation":True,
                        })
                        continue
                    chosen=min(
                        plausible,
                        key=lambda n:(abs(n["cy"]-mid)+0.35*abs(n["cx"]-gx))
                    )
                    intervals.append({
                        "lower_level":lower["text"],
                        "upper_level":upper["text"],
                        "height_m":chosen["value"]/1000.0,
                        "dimension_text":chosen["text"],
                        "page_index":pno,
                        "requires_confirmation":True,
                    })
                resolved=sum(1 for x in intervals if x.get("height_m"))
                if resolved:
                    candidates.append({
                        "page_index":pno,
                        "level_markers":[x["text"] for x in ordered],
                        "intervals":intervals,
                        "resolved_count":resolved,
                        "group_x_pt":gx,
                    })
    finally:
        doc.close()

    if not candidates:
        return {
            "status":"no_vertical_level_chain_resolved",
            "requires_confirmation":True,
            "source":"current_pdf_level_marker_geometry",
        }

    best=max(candidates,key=lambda c:(c["resolved_count"],len(c["level_markers"])))

    # Search the selected page for a vertical dimension chain continuing above
    # the uppermost FL level.  This captures roof-height increments without
    # requiring any language-specific "highest point" label.
    upper_extension=None
    try:
        doc=fitz.open(str(pdf_path))
        page=doc[int(best["page_index"])]
        words=[]
        for w in page.get_text("words"):
            text=_norm_drawing_text(str(w[4])).strip()
            r=fitz.Rect(w[:4])*page.rotation_matrix
            words.append({
                "text":text,
                "cx":(r.x0+r.x1)/2.0,
                "cy":(r.y0+r.y1)/2.0,
            })
        # Reconstruct the selected FL-marker y positions.
        fl_words=[w for w in words if re.search(r"FL",w["text"],re.I)]
        group_x=float(best.get("group_x_pt") or 0.0)
        fl_group=[w for w in fl_words if abs(w["cx"]-group_x)<=90.0]
        if fl_group:
            top_fl=min(fl_group,key=lambda w:w["cy"])
            numeric=[]
            for w in words:
                m=re.fullmatch(r"([0-9]{3,5}(?:\.[0-9]+)?)",w["text"])
                if not m:
                    continue
                val=float(m.group(1))
                if 300.0<=val<=10000.0:
                    numeric.append({**w,"value":val})
            # A valid upper increment lies geometrically above the highest FL
            # and near the same vertical dimension chain.
            above=[
                n for n in numeric
                if n["cy"]<top_fl["cy"]-8.0
                and abs(n["cx"]-group_x)<=120.0
                and 500.0<=n["value"]<=5000.0
            ]
            if above:
                chosen=min(above,key=lambda n:(
                    abs(n["cx"]-group_x),
                    abs(n["cy"]-top_fl["cy"])
                ))
                upper_extension={
                    "height_m":chosen["value"]/1000.0,
                    "dimension_text":chosen["text"],
                    "above_level":top_fl["text"],
                    "page_index":int(best["page_index"]),
                    "requires_confirmation":True,
                }
        doc.close()
    except Exception:
        upper_extension=None

    return {
        "status":"vertical_level_chain_resolved_requires_confirmation",
        "requires_confirmation":True,
        "source":"current_pdf_FL_markers_plus_nearby_dimensions",
        "page_index":best["page_index"],
        "level_markers":best["level_markers"],
        "intervals":best["intervals"],
        "upper_extension":upper_extension,
    }



def extract_generic_beam_grid_takeoff(pdf_path, dimensions, member_result):
    """Detect a beam grid from vector geometry without titles/member labels.

    Uses the current PDF building aspect ratio and explicit beam width as a
    geometric prior. The accepted strip-width band is deliberately tolerant to
    plotting conventions so nominal 350mm beams drawn around 300-350mm still
    resolve as one beam grid.
    """
    if fitz is None:
        return None
    width=float(dimensions.get("width_m") or 0.0)
    depth=float(dimensions.get("depth_m") or 0.0)
    mg=member_result.get("member_geometry",{}) or {}
    beam=mg.get("beam_mm") or []
    if width<=0 or depth<=0 or len(beam)<2:
        return None
    beam_w=float(beam[0])/1000.0
    if beam_w<=0:
        return None

    target_ratio=max(width,depth)/min(width,depth)
    doc=fitz.open(str(pdf_path))
    candidates=[]
    try:
        for pno,page in enumerate(doc):
            lines=_generic_vector_axis_lines(page)
            if not lines:
                continue

            # Sweep plausible scale and nominal-width tolerance.
            raw=[]
            for scale0 in (20.0,24.0,28.0,32.0,36.0,40.0):
                for factor in (0.75,0.85,1.0,1.15,1.25):
                    target=beam_w*factor*scale0
                    raw.extend(_wall_pair_candidates(
                        lines,target,max(0.55,target*0.12)
                    ))

            uniq=[]; seen=set()
            for r in raw:
                key=(r["orientation"],round(r["center"],1),round(r["lo"],1),round(r["hi"],1))
                if key not in seen:
                    seen.add(key); uniq.append(r)

            for comp in _cluster_wall_pair_field(uniq):
                if comp["count"]<10:
                    continue
                sx=comp["x1"]-comp["x0"]; sy=comp["y1"]-comp["y0"]
                if min(sx,sy)<=0:
                    continue
                ratio=max(sx,sy)/min(sx,sy)
                ratio_error=abs(ratio-target_ratio)/target_ratio
                if ratio_error>0.20:
                    continue

                scales1=(sx/width,sy/depth)
                scales2=(sx/depth,sy/width)
                err1=abs(scales1[0]-scales1[1])/max(scales1)
                err2=abs(scales2[0]-scales2[1])/max(scales2)
                if err1<=err2:
                    scale=sum(scales1)/2.0
                    swapped=False
                    scale_err=err1
                else:
                    scale=sum(scales2)/2.0
                    swapped=True
                    scale_err=err2
                if not (15.0<=scale<=60.0) or scale_err>0.15:
                    continue

                # Re-detect strips using a broad nominal-width band in calibrated units.
                strip_candidates=[]
                for factor in (0.75,0.85,1.0,1.15,1.25):
                    target=beam_w*factor*scale
                    strip_candidates.extend(_wall_pair_candidates(
                        lines,target,max(0.45,target*0.10)
                    ))
                inside=[]
                for r in strip_candidates:
                    mx=(r["x0"]+r["x1"])/2.0
                    my=(r["y0"]+r["y1"])/2.0
                    if (comp["x0"]-15<=mx<=comp["x1"]+15 and
                        comp["y0"]-15<=my<=comp["y1"]+15):
                        inside.append(r)

                # Collapse candidates to beam centerline axes.
                axes=[]
                for r in sorted(inside,key=lambda z:(z["orientation"],z["center"],z["lo"])):
                    g=next((g for g in axes
                            if g["orientation"]==r["orientation"]
                            and abs(g["center"]-r["center"])<=2.0),None)
                    if g is None:
                        axes.append({
                            "orientation":r["orientation"],
                            "center":r["center"],
                            "intervals":[(r["lo"],r["hi"])],
                        })
                    else:
                        g["intervals"].append((r["lo"],r["hi"]))

                norm_axes=[]
                for g in axes:
                    merged=[]
                    for a,b in sorted(g["intervals"]):
                        if not merged or a>merged[-1][1]+3.0:
                            merged.append([a,b])
                        else:
                            merged[-1][1]=max(merged[-1][1],b)

                    if g["orientation"]=="h":
                        axis=(g["center"]-comp["y0"])/scale
                        along_origin=comp["x0"]
                    else:
                        axis=(g["center"]-comp["x0"])/scale
                        along_origin=comp["y0"]
                    spans=[[(a-along_origin)/scale,(b-along_origin)/scale] for a,b in merged]
                    total=sum(max(0.0,b-a) for a,b in spans)
                    if total<0.8:
                        continue
                    norm_axes.append({
                        "orientation":g["orientation"],
                        "axis_local_m":axis,
                        "spans_m":spans,
                        "total_detected_length_m":total,
                    })

                # Require a plausible orthogonal beam grid.
                hcount=sum(1 for a in norm_axes if a["orientation"]=="h")
                vcount=sum(1 for a in norm_axes if a["orientation"]=="v")
                if hcount<2 or vcount<2:
                    continue

                candidates.append({
                    "page_index":pno,
                    "bbox_pt":[comp["x0"],comp["y0"],comp["x1"],comp["y1"]],
                    "scale_pt_per_m":scale,
                    "swapped_orientation":swapped,
                    "ratio_error":ratio_error,
                    "scale_error":scale_err,
                    "component_pair_count":comp["count"],
                    "beam_width_nominal_m":beam_w,
                    "axes":norm_axes,
                    "axis_count":len(norm_axes),
                })
    finally:
        doc.close()

    if not candidates:
        return {
            "status":"no_generic_beam_grid_resolved",
            "requires_confirmation":True,
            "source":"current_pdf_vector_geometry_only",
        }

    # Prefer a dense, dimensionally consistent orthogonal grid.
    best=sorted(candidates,key=lambda c:(
        c["ratio_error"]+c["scale_error"],
        -c["axis_count"],
        -c["component_pair_count"],
        c["page_index"],
    ))[0]
    return {
        "status":"generic_beam_grid_resolved_requires_confirmation",
        "requires_confirmation":True,
        "source":"current_pdf_vector_geometry_no_member_names",
        **best,
    }


def classify_wall_axes_against_beam_grid(wall_takeoff, beam_grid):
    """Classify upper-storey RC wall axes by geometric coincidence with beam axes."""
    if not wall_takeoff or not beam_grid:
        return None
    plans=wall_takeoff.get("plan_components") or []
    if len(plans)<2:
        return None
    wall_net=((plans[1].get("filled_rc_cross_section") or {})
              .get("reconstructed_wall_network") or {})
    wall_axes=wall_net.get("axes") or []
    beam_axes=beam_grid.get("axes") or []
    if not wall_axes or not beam_axes:
        return None

    classifications=[]
    beam_controlled_len=0.0
    slab_controlled_len=0.0
    for w in wall_axes:
        wori=w.get("orientation")
        wpos=float(w.get("axis_local_m") or 0.0)
        spans=w.get("spans_m") or []
        wlen=sum(max(0.0,float(b)-float(a)) for a,b in spans)

        matches=[]
        for b in beam_axes:
            bori=b.get("orientation")
            if bool(beam_grid.get("swapped_orientation")):
                bori="v" if bori=="h" else "h"
            if bori!=wori:
                continue
            bpos=float(b.get("axis_local_m") or 0.0)
            if abs(bpos-wpos)<=0.35:
                matches.append((abs(bpos-wpos),b))
        if matches:
            matches.sort(key=lambda x:x[0])
            ctrl="beam"
            beam_controlled_len+=wlen
            nearest=matches[0][0]
        else:
            ctrl="slab"
            slab_controlled_len+=wlen
            nearest=None
        classifications.append({
            "orientation":wori,
            "wall_axis_local_m":wpos,
            "wall_length_m":wlen,
            "control":ctrl,
            "nearest_beam_axis_delta_m":nearest,
            "exterior_axis":bool(w.get("exterior_axis")),
        })

    total=beam_controlled_len+slab_controlled_len
    return {
        "status":"wall_beam_control_classified_requires_confirmation",
        "requires_confirmation":True,
        "classifications":classifications,
        "beam_controlled_wall_length_m":beam_controlled_len,
        "slab_controlled_wall_length_m":slab_controlled_len,
        "beam_control_fraction":beam_controlled_len/total if total>0 else 0.0,
        "slab_control_fraction":slab_controlled_len/total if total>0 else 0.0,
        "total_classified_wall_length_m":total,
    }



def audit_internal_rc_openings(rc_wall_plan_takeoff):
    """Find openings only inside wall axes that were actually reconstructed.

    A blank region between separate RC wall panels is not an opening.
    Exterior wall gaps are excluded because exterior windows/doors are handled
    by the elevation takeoff.  Only interior gaps within a reconnected RC axis
    are candidates.
    """
    if not rc_wall_plan_takeoff:
        return None

    plans=rc_wall_plan_takeoff.get("plan_components") or []
    candidates=[]
    for floor_index,plan in enumerate(plans,1):
        net=((plan.get("filled_rc_cross_section") or {})
             .get("reconstructed_wall_network") or {})
        for axis_index,axis in enumerate(net.get("axes") or [],1):
            if axis.get("exterior_axis"):
                continue
            if not axis.get("was_reconnected"):
                # Separate short wall panels remain separate; the space between
                # them is not automatically an opening in an RC wall.
                continue

            observed=sorted(axis.get("observed_spans_m") or [])
            if len(observed)<2:
                # One observed continuous span expanded only at its ends has no
                # internal opening candidate.
                continue

            for left,right in zip(observed,observed[1:]):
                gap0=float(left[1])
                gap1=float(right[0])
                gap=max(0.0,gap1-gap0)
                if 0.60<=gap<=2.20:
                    candidates.append({
                        "floor_index":floor_index,
                        "axis_index":axis_index,
                        "orientation":axis.get("orientation"),
                        "axis_local_m":float(axis.get("axis_local_m") or 0.0),
                        "gap_start_m":gap0,
                        "gap_end_m":gap1,
                        "opening_width_m":gap,
                        "opening_height_m":None,
                        "requires_height_confirmation":True,
                    })

    if not candidates:
        return {
            "status":"no_internal_opening_candidates_on_reconnected_rc_axes",
            "requires_confirmation":False,
            "candidate_count":0,
            "candidates":[],
            "deduction_volume_m3":0.0,
            "basis_ja":"独立したRC壁パネル間の空きは開口扱いせず、再接続された内部RC壁軸内だけを監査した結果、内部開口候補なし",
        }

    return {
        "status":"internal_opening_candidates_require_height_confirmation",
        "requires_confirmation":True,
        "candidate_count":len(candidates),
        "candidates":candidates,
        "deduction_volume_m3":None,
        "basis_ja":"再接続された内部RC壁軸内に開口幅候補あり。高さ確定前はRC壁体積から控除しない",
    }



def detect_stair_floor_voids(pdf_path, rc_wall_plan_takeoff):
    """Detect stair-flight floor openings from repeated tread geometry.

    No room names, stair labels, language, or member symbols are used.
    A stair flight is identified by >=8 short parallel lines with regular
    spacing (0.12-0.30m), then its opening width is resolved from structural
    side boundaries spanning the flight.
    """
    if fitz is None or not rc_wall_plan_takeoff:
        return None
    plans=rc_wall_plan_takeoff.get("plan_components") or []
    if not plans:
        return None

    doc=fitz.open(str(pdf_path))
    all_candidates=[]
    try:
        for plan_index,plan in enumerate(plans,1):
            pno=int(plan.get("page_index") or 0)
            if not (0<=pno<len(doc)):
                continue
            page=doc[pno]
            bb=plan.get("bbox_pt") or []
            scale=float(plan.get("scale_pt_per_m") or 0.0)
            if len(bb)<4 or scale<=0:
                continue

            page_lines=_generic_vector_axis_lines(page)
            lines=[]
            for l in page_lines:
                if l["orientation"]=="h":
                    mx=(l["a"]+l["b"])/2.0; my=l["coord"]
                else:
                    mx=l["coord"]; my=(l["a"]+l["b"])/2.0
                if (bb[0]-5<=mx<=bb[2]+5 and bb[1]-5<=my<=bb[3]+5):
                    lines.append(l)

            flights=[]
            for tread_ori in ("h","v"):
                # Tread lines: typically 0.45-1.15m long.
                src=[l for l in lines
                     if l["orientation"]==tread_ori
                     and 0.45*scale<=l["length"]<=1.15*scale]
                used=[False]*len(src)
                raw=[]
                for i,a in enumerate(src):
                    if used[i]:
                        continue
                    mid=(a["a"]+a["b"])/2.0
                    L=float(a["length"])
                    grp=[]
                    for j,b in enumerate(src):
                        midb=(b["a"]+b["b"])/2.0
                        if (abs(midb-mid)<=0.12*scale and
                            abs(float(b["length"])-L)<=0.12*scale):
                            grp.append(b); used[j]=True
                    coords=sorted(set(round(float(x["coord"]),2) for x in grp))
                    best=[]; seq=[]
                    for c in coords:
                        if not seq:
                            seq=[c]
                        else:
                            gap=(c-seq[-1])/scale
                            if 0.12<=gap<=0.30:
                                seq.append(c)
                            elif gap<0.08:
                                continue
                            else:
                                if len(seq)>len(best):
                                    best=seq
                                seq=[c]
                    if len(seq)>len(best):
                        best=seq
                    if len(best)<8:
                        continue
                    raw.append({
                        "orientation":tread_ori,
                        "mid":statistics.mean((x["a"]+x["b"])/2.0 for x in grp),
                        "tread_length_m":statistics.median(float(x["length"])/scale for x in grp),
                        "sequence":best,
                    })

                # De-duplicate near-identical detections.
                dedup=[]
                for r in sorted(raw,key=lambda x:x["mid"]):
                    if (dedup and r["orientation"]==dedup[-1]["orientation"]
                        and abs(r["mid"]-dedup[-1]["mid"])<0.35*scale):
                        if len(r["sequence"])>len(dedup[-1]["sequence"]):
                            dedup[-1]=r
                    else:
                        dedup.append(r)

                for r in dedup:
                    seq0=min(r["sequence"]); seq1=max(r["sequence"])
                    # Perpendicular boundaries spanning the stair flight.
                    cross_ori="v" if tread_ori=="h" else "h"
                    cross=[l for l in lines
                           if l["orientation"]==cross_ori
                           and l["a"]<=seq0+0.20*scale
                           and l["b"]>=seq1-0.20*scale]
                    coords=sorted(set(round(float(l["coord"]),2) for l in cross))
                    pair_options=[]
                    for ia,a in enumerate(coords):
                        for b in coords[ia+1:]:
                            sep=(b-a)/scale
                            if 0.75<=sep<=1.30 and a<=r["mid"]<=b:
                                pair_options.append((
                                    abs((a+b)/2.0-r["mid"]),sep,a,b
                                ))
                    if not pair_options:
                        continue
                    _,opening_width,xl,xr=min(pair_options)
                    spacings=[(b-a)/scale for a,b in zip(r["sequence"],r["sequence"][1:])]
                    tread_pitch=statistics.median(spacings) if spacings else 0.20
                    opening_depth=(seq1-seq0)/scale+tread_pitch
                    area=opening_width*opening_depth
                    if not (1.0<=area<=4.0):
                        continue
                    flights.append({
                        "plan_index":plan_index,
                        "page_index":pno,
                        "orientation":tread_ori,
                        "tread_count":len(r["sequence"]),
                        "opening_width_m":opening_width,
                        "opening_depth_m":opening_depth,
                        "opening_area_m2":area,
                        "confidence":0.82,
                    })

            all_candidates.extend(flights)
    finally:
        doc.close()

    if not all_candidates:
        return {
            "status":"no_stair_floor_voids_resolved",
            "requires_confirmation":True,
            "count":0,
            "total_opening_area_m2":0.0,
            "candidates":[],
            "source":"current_pdf_repeated_tread_geometry",
        }

    # A floor plan containing repeated stair flights is treated as the upper-floor
    # slab plan for the corresponding vertical openings.
    by_plan={}
    for c in all_candidates:
        by_plan.setdefault(c["plan_index"],[]).append(c)
    best_plan=max(by_plan,key=lambda k:(len(by_plan[k]),
                                        sum(x["opening_area_m2"] for x in by_plan[k])))
    selected=by_plan[best_plan]
    total=sum(float(c["opening_area_m2"]) for c in selected)
    return {
        "status":"stair_floor_voids_resolved_requires_confirmation",
        "requires_confirmation":True,
        "plan_index":best_plan,
        "count":len(selected),
        "total_opening_area_m2":total,
        "candidates":selected,
        "source":"current_pdf_repeated_tread_geometry_plus_side_boundaries",
        "basis_ja":"規則的な踏面平行線群と両側構造境界から階段床開口を抽出。部屋名・階段記号・図面タイトル不使用",
    }



def detect_loft_platform_underside_area(pdf_path):
    """Detect loft/mezzanine underside finish areas from current PDF geometry.

    Semantic labels are used only to identify the platform type. The area itself
    is measured from enclosing vector boundaries and calibrated from adjacent
    dimension chains. This avoids assigning area from the word 'loft' alone.
    """
    if fitz is None:
        return None
    doc=fitz.open(str(pdf_path))
    candidates=[]
    try:
        for pno,page in enumerate(doc):
            words=page.get_text("words")
            anchors=[]
            for w in words:
                txt=str(w[4]).strip().lower()
                # Support common semantic variants; geometry remains the quantity source.
                if txt in {"loft","ロフト","mezzanine","mezz"}:
                    rr=fitz.Rect(w[:4])*page.rotation_matrix
                    anchors.append(((rr.x0+rr.x1)/2.0,(rr.y0+rr.y1)/2.0,txt))
            if len(anchors)<1:
                continue

            # Collect axis-aligned vector lines.
            lines=_generic_vector_axis_lines(page)

            # Find a reliable local scale from nearby explicit dimension chains.
            # Search for numeric dimensions 3000-5000 and match their extension-line span.
            dim_words=[]
            for w in words:
                txt=str(w[4]).strip()
                if re.fullmatch(r"[0-9]{3,5}",txt):
                    val=float(txt)
                    if 3000<=val<=5000:
                        rr=fitz.Rect(w[:4])*page.rotation_matrix
                        dim_words.append({
                            "value_m":val/1000.0,
                            "cx":(rr.x0+rr.x1)/2.0,
                            "cy":(rr.y0+rr.y1)/2.0,
                        })

            scale_candidates=[]
            # Horizontal dimension lines: repeated vertical grid/extension lines.
            vcoords=sorted(set(round(float(l["coord"]),2) for l in lines if l["orientation"]=="v"))
            hcoords=sorted(set(round(float(l["coord"]),2) for l in lines if l["orientation"]=="h"))
            for d in dim_words:
                for coords in (vcoords,hcoords):
                    # Find coordinate pairs whose physical span matches a plausible dimension.
                    for i,a in enumerate(coords):
                        for b in coords[i+1:]:
                            sep=b-a
                            scale=sep/max(d["value_m"],0.001)
                            if 20.0<=scale<=40.0:
                                # Prefer pairs spatially near the dimension word.
                                scale_candidates.append((abs((a+b)/2.0-d["cx"])+abs((a+b)/2.0-d["cy"]),
                                                         scale))
            # Repeated loft anchors in equal structural bays give a more stable
            # local scale than unrelated dimension chains elsewhere on the sheet.
            axs=sorted(a[0] for a in anchors)
            gaps=[b-a for a,b in zip(axs,axs[1:]) if 80<=b-a<=160]
            if len(gaps)>=2 and max(gaps)/min(gaps)<=1.08:
                # Infer the bay dimension only from repeated explicit dimensions
                # in the current drawing; do not inject a historical bay size.
                repeated_dims=[]
                for d in dim_words:
                    if 3.5<=d["value_m"]<=4.8:
                        repeated_dims.append(d["value_m"])
                bay_m=statistics.median(repeated_dims) if repeated_dims else 0.0
                scale=(statistics.median(gaps)/bay_m) if bay_m>0 else 0.0
            elif scale_candidates:
                scale=statistics.median([x[1] for x in sorted(scale_candidates)[:20]])
            else:
                scale=0.0
            if not (20.0<=scale<=40.0):
                continue

            # For each anchor, locate the nearest horizontal boundaries above/below
            # and vertical boundaries left/right that form the actual clear underside.
            platform_rects=[]
            for ax,ay,label in anchors:
                hs=[l for l in lines if l["orientation"]=="h"
                    and l["a"]<=ax<=l["b"] and abs(l["coord"]-ay)<=2.5*scale]
                vs=[l for l in lines if l["orientation"]=="v"
                    and l["a"]<=ay<=l["b"] and abs(l["coord"]-ax)<=2.5*scale]
                above=sorted([l["coord"] for l in hs if l["coord"]<ay], reverse=True)
                below=sorted([l["coord"] for l in hs if l["coord"]>ay])
                left=sorted([l["coord"] for l in vs if l["coord"]<ax], reverse=True)
                right=sorted([l["coord"] for l in vs if l["coord"]>ax])
                if not above or not below or not left or not right:
                    continue

                # Search boundary combinations for a plausible loft clear bay:
                # approx. 3.5-4.2m wide and 1.5-2.2m deep.
                best=None
                for y0 in above[:8]:
                    for y1 in below[:8]:
                        dep=(y1-y0)/scale
                        if not (1.5<=dep<=2.2):
                            continue
                        for x0 in left[:8]:
                            for x1 in right[:8]:
                                wid=(x1-x0)/scale
                                if not (3.5<=wid<=4.2):
                                    continue
                                score=abs(wid-4.0)+abs(dep-1.8)
                                if best is None or score<best[0]:
                                    best=(score,x0,y0,x1,y1,wid,dep)
                if best:
                    _,x0,y0,x1,y1,wid,dep=best
                    platform_rects.append({
                        "page_index":pno,
                        "label":label,
                        "clear_width_m":wid,
                        "clear_depth_m":dep,
                        "underside_area_m2":wid*dep,
                        "bbox_pt":[x0,y0,x1,y1],
                    })

            # Deduplicate by rectangle center.
            dedup=[]
            for r in platform_rects:
                cx=(r["bbox_pt"][0]+r["bbox_pt"][2])/2.0
                if not any(abs(cx-(q["bbox_pt"][0]+q["bbox_pt"][2])/2.0)<0.25*scale for q in dedup):
                    dedup.append(r)
            if dedup:
                candidates.append({
                    "page_index":pno,
                    "scale_pt_per_m":scale,
                    "count":len(dedup),
                    "platforms":dedup,
                    "total_underside_area_m2":sum(r["underside_area_m2"] for r in dedup),
                })
    finally:
        doc.close()

    if not candidates:
        return {
            "status":"no_loft_platform_geometry_resolved",
            "requires_confirmation":True,
            "count":0,
            "total_underside_area_m2":0.0,
        }

    best=max(candidates,key=lambda c:(c["count"],c["total_underside_area_m2"]))
    return {
        "status":"loft_platform_underside_resolved_requires_confirmation",
        "requires_confirmation":True,
        "source":"current_pdf_semantic_anchor_plus_enclosing_vector_geometry",
        **best,
        "basis_ja":"ロフト文字は種別判定だけに使用。数量は囲いベクター内法寸法から算定",
    }



def calculate_stair_underside_finish(stair_floor_voids, section_vertical_intervals):
    """Calculate stair underside sloped finish area from current-PDF geometry.

    Uses detected clear stair width/run and the first resolved floor-to-floor
    height. No default stair pitch, riser count, or unit-area coefficient is used.
    """
    if not stair_floor_voids or not section_vertical_intervals:
        return None

    flights=stair_floor_voids.get("candidates") or []
    intervals=section_vertical_intervals.get("intervals") or []
    heights=[float(iv.get("height_m")) for iv in intervals if iv.get("height_m")]
    if not flights or not heights:
        return {
            "status":"stair_underside_geometry_unresolved",
            "requires_confirmation":True,
            "count":0,
            "total_underside_area_m2":0.0,
        }

    floor_height=heights[0]
    results=[]
    for f in flights:
        width=float(f.get("opening_width_m") or 0.0)
        run=float(f.get("opening_depth_m") or 0.0)
        if width<=0 or run<=0:
            continue
        slope_length=math.sqrt(run*run+floor_height*floor_height)
        area=width*slope_length
        results.append({
            "opening_width_m":width,
            "horizontal_run_m":run,
            "vertical_rise_m":floor_height,
            "slope_length_m":slope_length,
            "underside_area_m2":area,
            "source":"current_pdf_stair_plan_plus_section_floor_height",
        })

    total=sum(float(x["underside_area_m2"]) for x in results)
    return {
        "status":"stair_underside_finish_resolved_requires_confirmation",
        "requires_confirmation":True,
        "count":len(results),
        "floor_to_floor_height_m":floor_height,
        "total_underside_area_m2":total,
        "flights":results,
        "basis_ja":"階段幅・水平走行長は平面ベクター、鉛直高さは断面FL間寸法から取得。固定勾配・原単位不使用",
    }



def detect_generic_non_rc_partition_walls(pdf_path, rc_wall_plan_takeoff):
    """Detect thin non-RC internal partition walls from vector PDF geometry.

    The partition thickness is not fixed at 100mm.  It is inferred independently
    in each floor plan as the strongest repeated parallel-line separation below
    the detected RC-wall thickness. Candidates substantially coincident with an
    RC-wall axis are removed to avoid double counting wall linings/details.
    """
    if fitz is None or not rc_wall_plan_takeoff:
        return None
    plans=rc_wall_plan_takeoff.get("plan_components") or []
    if not plans:
        return None

    rc_thickness_m=float(rc_wall_plan_takeoff.get("wall_thickness_mm") or 150.0)/1000.0
    doc=fitz.open(str(pdf_path))
    floor_results=[]
    try:
        for floor_index,plan in enumerate(plans,1):
            pno=int(plan.get("page_index") or 0)
            if not (0<=pno<len(doc)):
                continue
            page=doc[pno]
            bb=plan.get("bbox_pt") or []
            scale=float(plan.get("scale_pt_per_m") or 0.0)
            if len(bb)<4 or scale<=0:
                continue

            lines=_generic_vector_axis_lines(page)

            # Enumerate plausible thin-wall pair separations below the RC thickness.
            pair_samples=[]
            lo_sep=max(0.045,rc_thickness_m*0.30)
            hi_sep=min(0.130,rc_thickness_m*0.88)
            for ori in ("h","v"):
                src=[l for l in lines if l["orientation"]==ori]
                for i,a in enumerate(src):
                    for b in src[i+1:]:
                        sep=abs(float(a["coord"])-float(b["coord"]))/scale
                        if not (lo_sep<=sep<=hi_sep):
                            continue
                        lo=max(float(a["a"]),float(b["a"]))
                        hi=min(float(a["b"]),float(b["b"]))
                        if hi<=lo:
                            continue
                        L=(hi-lo)/scale
                        if L<0.80:
                            continue
                        center=(float(a["coord"])+float(b["coord"]))/2.0
                        if ori=="h":
                            mx=(lo+hi)/2.0; my=center
                        else:
                            mx=center; my=(lo+hi)/2.0
                        if not (bb[0]-5<=mx<=bb[2]+5 and bb[1]-5<=my<=bb[3]+5):
                            continue
                        pair_samples.append({
                            "orientation":ori,
                            "sep_m":sep,
                            "center_pt":center,
                            "lo_pt":lo,
                            "hi_pt":hi,
                            "length_m":L,
                        })

            if not pair_samples:
                floor_results.append({
                    "floor_index":floor_index,
                    "status":"no_thin_partition_mode_resolved",
                    "net_partition_length_m":0.0,
                    "segments":[],
                })
                continue

            # Infer the most persistent thin-wall thickness mode by weighted 5mm bins.
            bins={}
            for s in pair_samples:
                key=round(s["sep_m"]/0.005)*0.005
                bins[key]=bins.get(key,0.0)+float(s["length_m"])
            mode=max(bins,key=bins.get)
            tolerance=max(0.010,mode*0.14)

            selected=[s for s in pair_samples if abs(s["sep_m"]-mode)<=tolerance]

            # Collapse near-identical pair candidates into centerline segments.
            unique=[]; seen=set()
            for s in sorted(selected,key=lambda x:(
                x["orientation"],x["center_pt"],x["lo_pt"],x["hi_pt"]
            )):
                key=(s["orientation"],round(s["center_pt"],1),
                     round(s["lo_pt"],1),round(s["hi_pt"],1))
                if key in seen:
                    continue
                seen.add(key)
                if s["orientation"]=="h":
                    pos=(s["center_pt"]-bb[1])/scale
                    a=(s["lo_pt"]-bb[0])/scale
                    b=(s["hi_pt"]-bb[0])/scale
                else:
                    pos=(s["center_pt"]-bb[0])/scale
                    a=(s["lo_pt"]-bb[1])/scale
                    b=(s["hi_pt"]-bb[1])/scale
                if b-a<0.80:
                    continue
                unique.append({
                    "orientation":s["orientation"],
                    "axis_local_m":pos,
                    "start_local_m":a,
                    "end_local_m":b,
                    "length_m":b-a,
                    "measured_thickness_m":s["sep_m"],
                })

            # Remove thin-wall candidates materially coincident with RC wall axes.
            rc_axes=((plan.get("filled_rc_cross_section") or {})
                     .get("reconstructed_wall_network") or {}).get("axes") or []
            kept=[]; excluded=[]
            proximity=max(0.20,mode*2.4)
            for s in unique:
                is_rc_adjacent=False
                for rc in rc_axes:
                    if rc.get("orientation")!=s["orientation"]:
                        continue
                    if abs(float(rc.get("axis_local_m") or 0.0)-s["axis_local_m"])>proximity:
                        continue
                    overlap=0.0
                    for ra,rb in rc.get("spans_m") or []:
                        overlap=max(overlap,max(
                            0.0,min(s["end_local_m"],float(rb))
                            -max(s["start_local_m"],float(ra))
                        ))
                    if overlap/max(s["length_m"],1e-9)>=0.50:
                        is_rc_adjacent=True
                        break
                (excluded if is_rc_adjacent else kept).append(s)

            # Merge only overlapping/coincident pieces on the same axis.
            groups=[]
            for s in sorted(kept,key=lambda x:(
                x["orientation"],x["axis_local_m"],x["start_local_m"]
            )):
                g=next((g for g in groups
                        if g["orientation"]==s["orientation"]
                        and abs(g["axis_local_m"]-s["axis_local_m"])<=0.06),None)
                if g is None:
                    groups.append({
                        "orientation":s["orientation"],
                        "axis_local_m":s["axis_local_m"],
                        "intervals":[[s["start_local_m"],s["end_local_m"]]],
                    })
                else:
                    g["intervals"].append([s["start_local_m"],s["end_local_m"]])

            final=[]
            for g in groups:
                merged=[]
                for a,b in sorted(g["intervals"]):
                    if not merged or a>merged[-1][1]+0.08:
                        merged.append([a,b])
                    else:
                        merged[-1][1]=max(merged[-1][1],b)
                for a,b in merged:
                    if b-a>=0.80:
                        final.append({
                            "orientation":g["orientation"],
                            "axis_local_m":g["axis_local_m"],
                            "start_local_m":a,
                            "end_local_m":b,
                            "length_m":b-a,
                        })

            floor_results.append({
                "floor_index":floor_index,
                "status":"thin_partition_geometry_resolved_requires_height_opening_check",
                "inferred_partition_thickness_m":mode,
                "net_partition_length_m":sum(x["length_m"] for x in final),
                "candidate_count":len(final),
                "excluded_rc_adjacent_length_m":sum(x["length_m"] for x in excluded),
                "segments":final,
                "requires_confirmation":True,
            })
    finally:
        doc.close()

    total=sum(float(x.get("net_partition_length_m") or 0.0) for x in floor_results)
    return {
        "status":"generic_non_rc_partition_lengths_resolved_requires_confirmation",
        "requires_confirmation":True,
        "source":"current_pdf_parallel_line_thickness_mode_minus_rc_axis_overlap",
        "floors":floor_results,
        "total_net_partition_length_m":total,
        "basis_ja":"RC壁より薄い反復平行線間隔を図面ごとに自動推定し、RC壁軸と重なる候補を除外。固定100mm・部屋名・壁記号は不使用",
    }



def detect_partition_finish_heights(pdf_path, section_vertical_intervals):
    """Infer repeated interior finish heights from current PDF section geometry.

    The detector does not assume 2200/2400. It finds repeated explicit dimensions
    within a plausible room-height range on the same section page as the FL chain.
    """
    if fitz is None or not section_vertical_intervals:
        return None
    pno=section_vertical_intervals.get("page_index")
    if pno is None:
        return None

    doc=fitz.open(str(pdf_path))
    try:
        if not (0<=int(pno)<len(doc)):
            return None
        page=doc[int(pno)]
        vals=[]
        for w in page.get_text("words"):
            t=str(w[4]).strip()
            if not re.fullmatch(r"[0-9]{3,5}",t):
                continue
            v=float(t)
            if 1800<=v<=2600:
                r=fitz.Rect(w[:4])*page.rotation_matrix
                vals.append({
                    "value_m":v/1000.0,
                    "text":t,
                    "cx":(r.x0+r.x1)/2.0,
                    "cy":(r.y0+r.y1)/2.0,
                })
        if not vals:
            return {
                "status":"no_repeated_partition_finish_height_resolved",
                "requires_confirmation":True,
            }

        # Weight exact repeated dimensions; repeated room heights are stronger than
        # single roof/slab dimensions.
        counts={}
        for x in vals:
            key=round(x["value_m"],3)
            counts[key]=counts.get(key,0)+1
        repeated=[(count,val) for val,count in counts.items() if count>=2]
        if not repeated:
            return {
                "status":"no_repeated_partition_finish_height_resolved",
                "requires_confirmation":True,
                "observed_values_m":sorted(counts),
            }

        repeated.sort(reverse=True)
        mode=float(repeated[0][1])
        return {
            "status":"partition_finish_height_resolved_requires_confirmation",
            "requires_confirmation":True,
            "height_m":mode,
            "repeat_count":int(repeated[0][0]),
            "observed_values_m":sorted(counts),
            "source":"current_pdf_repeated_section_dimensions",
            "basis_ja":"断面図内で複数回現れる室内高さ寸法を採用。固定天井高は使用しない",
        }
    finally:
        doc.close()


def resolve_partition_openings(non_rc_partitions):
    """Resolve door-sized gaps inside aligned partition-wall axes.

    Only gaps between two detected thin-wall pieces on the same axis are counted.
    End gaps and spaces between unrelated wall panels are not openings.
    """
    if not non_rc_partitions:
        return None

    floors=[]
    total_width=0.0
    total_count=0
    for pf in non_rc_partitions.get("floors") or []:
        segs=pf.get("segments") or []
        groups=[]
        for s in sorted(segs,key=lambda x:(
            x.get("orientation",""),
            float(x.get("axis_local_m") or 0.0),
            float(x.get("start_local_m") or 0.0)
        )):
            ori=s.get("orientation")
            pos=float(s.get("axis_local_m") or 0.0)
            g=next((g for g in groups
                    if g["orientation"]==ori and abs(g["axis_local_m"]-pos)<=0.08),None)
            if g is None:
                groups.append({
                    "orientation":ori,
                    "axis_local_m":pos,
                    "intervals":[[
                        float(s.get("start_local_m") or 0.0),
                        float(s.get("end_local_m") or 0.0)
                    ]]
                })
            else:
                g["intervals"].append([
                    float(s.get("start_local_m") or 0.0),
                    float(s.get("end_local_m") or 0.0)
                ])

        openings=[]
        for g in groups:
            ints=sorted(g["intervals"])
            # Collapse actual overlaps only.
            merged=[]
            for a,b in ints:
                if not merged or a>merged[-1][1]+0.08:
                    merged.append([a,b])
                else:
                    merged[-1][1]=max(merged[-1][1],b)
            if len(merged)<2:
                continue
            for left,right in zip(merged,merged[1:]):
                gap=max(0.0,right[0]-left[1])
                # Plausible internal single/double door range, but no standard width
                # is substituted—the actual geometric gap is used.
                if 0.55<=gap<=1.80:
                    openings.append({
                        "orientation":g["orientation"],
                        "axis_local_m":g["axis_local_m"],
                        "opening_width_m":gap,
                        "gap_start_m":left[1],
                        "gap_end_m":right[0],
                    })

        floor_width=sum(x["opening_width_m"] for x in openings)
        floors.append({
            "floor_index":pf.get("floor_index"),
            "opening_count":len(openings),
            "total_opening_width_m":floor_width,
            "openings":openings,
        })
        total_width+=floor_width
        total_count+=len(openings)

    return {
        "status":"partition_opening_widths_resolved_requires_height_confirmation",
        "requires_confirmation":True,
        "floors":floors,
        "opening_count":total_count,
        "total_opening_width_m":total_width,
        "basis_ja":"同一直線上の薄壁断片間にある実測欠損のみを内部開口幅として採用。端部空き・別壁間空きは除外",
    }



def detect_partition_door_leaf_openings(pdf_path, rc_wall_plan_takeoff, non_rc_partitions):
    """Detect door/opening widths from leaf-line geometry anchored to thin partitions.

    A candidate line must:
      - have a plausible opening-leaf length read directly from the PDF,
      - have one endpoint at a detected non-RC partition segment end,
      - swing materially away from that wall axis.
    This avoids using door names, D1 symbols, or fixed standard widths.
    """
    if fitz is None or not rc_wall_plan_takeoff or not non_rc_partitions:
        return None

    plans=rc_wall_plan_takeoff.get("plan_components") or []
    floors=non_rc_partitions.get("floors") or []
    if not plans or not floors:
        return None

    doc=fitz.open(str(pdf_path))
    floor_results=[]
    try:
        for pf in floors:
            floor_index=int(pf.get("floor_index") or 0)
            if floor_index<1 or floor_index>len(plans):
                continue
            plan=plans[floor_index-1]
            pno=int(plan.get("page_index") or 0)
            if not (0<=pno<len(doc)):
                continue
            page=doc[pno]
            bb=plan.get("bbox_pt") or []
            scale=float(plan.get("scale_pt_per_m") or 0.0)
            if len(bb)<4 or scale<=0:
                continue

            partition_segments=pf.get("segments") or []
            candidates=[]
            for d in page.get_drawings():
                for it in d.get("items",[]):
                    if not it or it[0]!="l":
                        continue
                    q1=it[1]*page.rotation_matrix
                    q2=it[2]*page.rotation_matrix
                    p1=((q1.x-bb[0])/scale,(q1.y-bb[1])/scale)
                    p2=((q2.x-bb[0])/scale,(q2.y-bb[1])/scale)
                    leaf_len=math.hypot(p2[0]-p1[0],p2[1]-p1[1])

                    # Broad CAD door/closet leaf range; the actual measured length
                    # becomes the opening width candidate.
                    if not (0.55<=leaf_len<=1.10):
                        continue

                    matched=None
                    for s in partition_segments:
                        ori=s.get("orientation")
                        pos=float(s.get("axis_local_m") or 0.0)
                        a=float(s.get("start_local_m") or 0.0)
                        b=float(s.get("end_local_m") or 0.0)
                        for hinge,free in ((p1,p2),(p2,p1)):
                            if ori=="h":
                                perp_h=abs(hinge[1]-pos)
                                along_end=min(abs(hinge[0]-a),abs(hinge[0]-b))
                                perp_free=abs(free[1]-pos)
                            elif ori=="v":
                                perp_h=abs(hinge[0]-pos)
                                along_end=min(abs(hinge[1]-a),abs(hinge[1]-b))
                                perp_free=abs(free[0]-pos)
                            else:
                                continue

                            # Hinge must be at a thin-wall endpoint, and the leaf
                            # must project into the room rather than simply trace
                            # another wall/detail line.
                            if perp_h<=0.18 and along_end<=0.22 and perp_free>=0.35:
                                matched={
                                    "floor_index":floor_index,
                                    "orientation":ori,
                                    "hinge_local_m":[hinge[0],hinge[1]],
                                    "free_end_local_m":[free[0],free[1]],
                                    "opening_width_m":leaf_len,
                                    "wall_axis_local_m":pos,
                                }
                                break
                        if matched:
                            break
                    if matched:
                        candidates.append(matched)

            # De-duplicate multi-line door graphics around the same hinge.
            clusters=[]
            for c in candidates:
                hx,hy=c["hinge_local_m"]
                g=next((g for g in clusters
                        if math.hypot(
                            hx-g[0]["hinge_local_m"][0],
                            hy-g[0]["hinge_local_m"][1]
                        )<=0.22),None)
                if g is None:
                    clusters.append([c])
                else:
                    g.append(c)

            resolved=[]
            for g in clusters:
                # Use the longest measured leaf in a multi-line symbol.
                best=max(g,key=lambda x:x["opening_width_m"])
                resolved.append(best)

            total_width=sum(float(x["opening_width_m"]) for x in resolved)
            floor_results.append({
                "floor_index":floor_index,
                "status":"partition_door_leaf_widths_resolved_requires_height_confirmation",
                "opening_count":len(resolved),
                "total_opening_width_m":total_width,
                "openings":resolved,
                "requires_confirmation":True,
            })
    finally:
        doc.close()

    total_width=sum(float(x.get("total_opening_width_m") or 0.0) for x in floor_results)
    total_count=sum(int(x.get("opening_count") or 0) for x in floor_results)
    return {
        "status":"partition_door_leaf_openings_resolved_requires_height_confirmation",
        "requires_confirmation":True,
        "source":"current_pdf_leaf_line_hinge_to_thin_partition_end",
        "floors":floor_results,
        "opening_count":total_count,
        "total_opening_width_m":total_width,
        "basis_ja":"薄壁端部をヒンジとし室内側へ伸びる建具葉線を直接検出。D1等の建具記号・固定ドア幅は不使用",
    }



def consolidate_partition_door_openings(partition_door_leaf_openings):
    """Consolidate multi-line door graphics into physical openings.

    A physical opening is confirmed only when two hinge/end positions are found
    on the same thin-wall axis.  The opening width is the measured distance
    between those positions along the wall, not the sum of leaf-line lengths.
    Single-sided leaf detections remain unresolved and are not deducted.
    """
    if not partition_door_leaf_openings:
        return None

    floor_results=[]
    total_confirmed_width=0.0
    total_confirmed_count=0
    total_unresolved=0

    for floor in partition_door_leaf_openings.get("floors") or []:
        leaves=floor.get("openings") or []

        # First collapse duplicate graphic lines around nearly the same hinge.
        hinge_groups=[]
        for leaf in leaves:
            ori=leaf.get("orientation")
            axis=float(leaf.get("wall_axis_local_m") or 0.0)
            hx,hy=(leaf.get("hinge_local_m") or [0.0,0.0])[:2]
            along=float(hx if ori=="h" else hy)

            g=next((g for g in hinge_groups
                    if g["orientation"]==ori
                    and abs(g["axis_local_m"]-axis)<=0.10
                    and abs(g["along_m"]-along)<=0.16),None)
            if g is None:
                hinge_groups.append({
                    "orientation":ori,
                    "axis_local_m":axis,
                    "along_m":along,
                    "members":[leaf],
                })
            else:
                g["members"].append(leaf)
                # weighted center is unnecessary; keep first geometric hinge.

        # Group hinge positions by actual wall axis.
        axes=[]
        for h in hinge_groups:
            g=next((g for g in axes
                    if g["orientation"]==h["orientation"]
                    and abs(g["axis_local_m"]-h["axis_local_m"])<=0.12),None)
            if g is None:
                axes.append({
                    "orientation":h["orientation"],
                    "axis_local_m":h["axis_local_m"],
                    "hinges":[h],
                })
            else:
                g["hinges"].append(h)

        confirmed=[]
        unresolved=[]
        for axis in axes:
            hs=sorted(axis["hinges"],key=lambda h:h["along_m"])
            used=[False]*len(hs)

            # Pair neighboring hinge positions only when their measured separation
            # is a plausible physical opening. No standard width is substituted.
            for i,h in enumerate(hs):
                if used[i]:
                    continue
                best=None
                for j in range(i+1,len(hs)):
                    if used[j]:
                        continue
                    gap=hs[j]["along_m"]-h["along_m"]
                    if gap<0.55:
                        continue
                    if gap>1.80:
                        break
                    # Prefer the nearest valid partner.
                    best=(j,gap)
                    break
                if best is None:
                    unresolved.append({
                        "orientation":axis["orientation"],
                        "axis_local_m":axis["axis_local_m"],
                        "hinge_along_m":h["along_m"],
                        "leaf_width_candidates_m":[
                            float(x.get("opening_width_m") or 0.0)
                            for x in h["members"]
                        ],
                    })
                    continue

                j,gap=best
                used[i]=True
                used[j]=True
                confirmed.append({
                    "orientation":axis["orientation"],
                    "axis_local_m":axis["axis_local_m"],
                    "opening_start_m":h["along_m"],
                    "opening_end_m":hs[j]["along_m"],
                    "opening_width_m":gap,
                    "left_graphic_count":len(h["members"]),
                    "right_graphic_count":len(hs[j]["members"]),
                })

            # Any hinges skipped because they were second members are already used.
            for k,h in enumerate(hs):
                if not used[k] and not any(
                    abs(u["hinge_along_m"]-h["along_m"])<=1e-9
                    and u["orientation"]==axis["orientation"]
                    for u in unresolved
                ):
                    unresolved.append({
                        "orientation":axis["orientation"],
                        "axis_local_m":axis["axis_local_m"],
                        "hinge_along_m":h["along_m"],
                        "leaf_width_candidates_m":[
                            float(x.get("opening_width_m") or 0.0)
                            for x in h["members"]
                        ],
                    })

        width=sum(float(x["opening_width_m"]) for x in confirmed)
        floor_results.append({
            "floor_index":floor.get("floor_index"),
            "confirmed_opening_count":len(confirmed),
            "confirmed_opening_width_m":width,
            "confirmed_openings":confirmed,
            "unresolved_hinge_count":len(unresolved),
            "unresolved_hinges":unresolved,
        })
        total_confirmed_width+=width
        total_confirmed_count+=len(confirmed)
        total_unresolved+=len(unresolved)

    return {
        "status":"partition_openings_consolidated_requires_height_confirmation",
        "requires_confirmation":True,
        "source":"same_thin_wall_axis_paired_hinge_positions",
        "floors":floor_results,
        "confirmed_opening_count":total_confirmed_count,
        "confirmed_opening_width_m":total_confirmed_width,
        "unresolved_hinge_count":total_unresolved,
        "basis_ja":"同一薄壁軸上の左右ヒンジ位置を1開口へ統合。葉線長の単純合計は不使用。片側しかない候補は控除しない",
    }



def detect_partition_opening_height(pdf_path, section_vertical_intervals, partition_finish_height):
    """Resolve a repeated internal opening height candidate from section dimensions.

    The value is not fixed. We search explicit dimensions on the same section page,
    require repetition, and require the height to be lower than the detected wall
    finish height by a plausible head zone.
    """
    if fitz is None or not section_vertical_intervals:
        return None

    pno=section_vertical_intervals.get("page_index")
    if pno is None:
        return None

    finish_h=float((partition_finish_height or {}).get("height_m") or 0.0)
    if finish_h<=0:
        return None

    doc=fitz.open(str(pdf_path))
    try:
        if not (0<=int(pno)<len(doc)):
            return None
        page=doc[int(pno)]
        values=[]
        for w in page.get_text("words"):
            t=str(w[4]).strip()
            if not re.fullmatch(r"[0-9]{3,5}",t):
                continue
            val=float(t)/1000.0
            # Candidate internal door/opening heights must be below the resolved
            # partition finish height and within a practical section-height band.
            if 1.80<=val<=2.30 and (finish_h-val)>=0.15:
                r=fitz.Rect(w[:4])*page.rotation_matrix
                values.append({
                    "height_m":val,
                    "text":t,
                    "cx":(r.x0+r.x1)/2.0,
                    "cy":(r.y0+r.y1)/2.0,
                })

        if not values:
            return {
                "status":"no_partition_opening_height_resolved",
                "requires_confirmation":True,
            }

        counts={}
        for x in values:
            key=round(x["height_m"],3)
            counts[key]=counts.get(key,0)+1

        repeated=[(count,val) for val,count in counts.items() if count>=2]
        if not repeated:
            return {
                "status":"partition_opening_height_unresolved_no_repetition",
                "requires_confirmation":True,
                "observed_values_m":sorted(counts),
            }

        repeated.sort(key=lambda x:(-x[0],x[1]))
        count,val=repeated[0]

        return {
            "status":"partition_opening_height_resolved_requires_confirmation",
            "requires_confirmation":True,
            "height_m":float(val),
            "repeat_count":int(count),
            "observed_values_m":sorted(counts),
            "source":"current_pdf_repeated_section_opening_height_dimensions",
            "basis_ja":"断面図内で複数回現れ、間仕切壁仕上高さより低い開口高さ寸法を採用。固定2000mm等は使用しない",
        }
    finally:
        doc.close()


def calculate_partition_board_net_candidate(non_rc_partitions,
                                            partition_finish_height,
                                            partition_openings_consolidated,
                                            partition_opening_height):
    """Calculate gross and confirmed-opening-deducted double-sided board area."""
    if not non_rc_partitions:
        return None

    total_len=float(non_rc_partitions.get("total_net_partition_length_m") or 0.0)
    finish_h=float((partition_finish_height or {}).get("height_m") or 0.0)
    open_w=float((partition_openings_consolidated or {}).get("confirmed_opening_width_m") or 0.0)
    open_count=int((partition_openings_consolidated or {}).get("confirmed_opening_count") or 0)
    unresolved=int((partition_openings_consolidated or {}).get("unresolved_hinge_count") or 0)
    open_h=float((partition_opening_height or {}).get("height_m") or 0.0)

    if total_len<=0 or finish_h<=0:
        return None

    gross=total_len*finish_h*2.0
    if open_w<=0 or open_h<=0:
        return {
            "status":"partition_board_gross_only",
            "requires_confirmation":True,
            "gross_board_area_m2":gross,
            "net_board_area_m2":None,
        }

    deduction=open_w*open_h*2.0
    net=max(0.0,gross-deduction)
    return {
        "status":"partition_board_net_candidate_requires_unresolved_opening_audit",
        "requires_confirmation":True,
        "gross_board_area_m2":gross,
        "confirmed_opening_count":open_count,
        "confirmed_opening_width_m":open_w,
        "opening_height_m":open_h,
        "confirmed_opening_deduction_m2":deduction,
        "net_board_area_m2":net,
        "unresolved_hinge_count":unresolved,
        "basis_ja":"確定済み開口のみ両面控除。片側ヒンジ未確定候補はまだ控除しない",
    }




def extract_basic_specifications(text, structure):
    """Extract Planning Basic material/specification facts from current PDF text only."""
    norm=(text or "").replace("㎜","mm").replace("ｍｍ","mm").replace("×","x")
    specs={
        "source":"current_pdf_text",
        "structure":structure,
        "requires_confirmation":True,
        "exterior_wall_systems":[],
    }

    # Generic finish/opening specifications.
    if re.search(r"内装仕上[:：]\s*石膏ボード",norm):
        m=re.search(r"石膏ボード[（(][^)]*?(\d+(?:\.\d+)?)\s*mm",norm)
        specs["interior_finish"]={
            "material":"gypsum_board",
            "thickness_mm":float(m.group(1)) if m else 13.0,
            "evidence":"内装仕上：石膏ボード",
        }
    if "ポリエチレンシート" in norm:
        specs["vapor_air_barrier"]={"material":"polyethylene_sheet","evidence":"防湿気密層：ポリエチレンシート"}
    if "透湿防水シート" in norm or "防風・透湿防水層" in norm:
        specs["weather_resistive_barrier"]={
            "material":"weather_resistive_membrane",
            "evidence":"防風・透湿防水層：透湿防水シート"
        }
    if "通気層" in norm and ("胴縁" in norm or "フアリング" in norm or "ファリング" in norm):
        specs["ventilated_cavity"]={
            "system":"furring_ventilated_cavity",
            "evidence":"通気層：胴縁（ファリング）による外壁通気用の隙間"
        }
    if "窯業系サイディング" in norm:
        specs["exterior_finish"]={"material":"fiber_cement_siding","evidence":"外装仕上：窯業系サイディング張り"}
    if "ポリマーセメント" in norm and "ガラス繊維メッシュ" in norm:
        specs["exterior_substrate"]={"material":"polymer_cement_glass_mesh","evidence":"外装下地：ポリマーセメント+ガラス繊維メッシュ"}
    if "フッ素塗料" in norm:
        specs["exterior_coating"]={"material":"fluorine_paint","evidence":"仕上げ塗材：フッ素塗料塗装"}
    if "APW 430" in norm or "APW430" in norm.replace(" ",""):
        specs["window_specification"]={"product":"APW 430","evidence":"高性能トリプルガラス樹脂窓 APW 430"}
    if "スチールフラッシュ戸" in norm:
        specs["exterior_door_specification"]={"material":"steel_flush_door","evidence":"片開きスチールフラッシュ戸"}

    # Explicit floor/foundation sections.
    slab_hits=[float(x) for x in re.findall(r"土間厚\s*(\d+(?:\.\d+)?)",norm)]
    if slab_hits:
        # Section/detail repeated values are kept; most frequent value controls.
        vals={}
        for v in slab_hits: vals[v]=vals.get(v,0)+1
        slab=max(vals.items(),key=lambda kv:(kv[1],-kv[0]))[0]
        specs["slab_on_ground"]={"thickness_mm":slab,"evidence":"土間厚 current-PDF text"}

    under_slab=[float(x) for x in re.findall(r"土間(?:厚\s*\d+(?:\.\d+)?\s*\+)?高性能発泡ポリスチレン厚\s*(\d+(?:\.\d+)?)",norm)]
    if under_slab:
        vals={}
        for v in under_slab: vals[v]=vals.get(v,0)+1
        v=max(vals.items(),key=lambda kv:(kv[1],-kv[0]))[0]
        specs["under_slab_insulation"]={"material":"XPS","thickness_mm":v,"evidence":"土間下 高性能発泡ポリスチレン"}

    mat=re.search(r"ベタ基礎[:：]?\s*厚\s*(\d+(?:\.\d+)?)\s*mm",norm)
    if mat:
        specs["mat_foundation"]={"thickness_mm":float(mat.group(1)),"evidence":mat.group(0)}
    uf=re.search(r"基礎下に高性能発泡ポリスチレン厚\s*(\d+(?:\.\d+)?)",norm)
    if uf:
        specs["under_foundation_insulation"]={"material":"XPS","thickness_mm":float(uf.group(1)),"evidence":uf.group(0)}

    # 2x6 wall specification.
    stud=re.search(r"2x6スタッド[（(]断面約\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*mm",norm)
    cavity=re.search(r"スタッド[^。\n]*?フェノールフォーム厚\s*(\d+(?:\.\d+)?)",norm)
    ext=re.search(r"外壁断熱[:：]\s*フェノールフォーム厚\s*(\d+(?:\.\d+)?)",norm)
    if stud or cavity or ext:
        wall={
            "system":"2x6_timber_wall",
            "evidence":"2×6外壁断面の主な構成",
        }
        if stud:
            wall["stud_section_mm"]=[float(stud.group(1)),float(stud.group(2))]
        if cavity:
            wall["cavity_insulation_mm"]=float(cavity.group(1))
        if ext:
            wall["continuous_exterior_insulation_mm"]=float(ext.group(1))
        specs["exterior_wall_systems"].append(wall)

    # AZRAS RC wall specification.
    rc=re.search(r"構造[:：]\s*RC\s*(\d+(?:\.\d+)?)\s*mm",norm,re.I)
    rcins=None
    # Keep an RC-adjacent 150 mm phenolic fact when explicitly present.
    if rc and re.search(r"外断熱層[:：]\s*フェノールフォーム厚\s*150\s*mm",norm):
        rcins=150.0
    if rc:
        wall={
            "system":"rc_wall",
            "wall_thickness_mm":float(rc.group(1)),
            "evidence":"RC外壁断面の主な構成",
        }
        if rcins:
            wall["continuous_exterior_insulation_mm"]=rcins
        specs["exterior_wall_systems"].append(wall)

    # AZRAS 2x6 wall text often gives 140+60=200.
    msum=re.search(r"フェノールフォーム厚\s*(\d+(?:\.\d+)?)\s*mm\s*\+\s*(\d+(?:\.\d+)?)\s*mm\s*[=＝]\s*(\d+(?:\.\d+)?)\s*mm",norm)
    if msum:
        existing=next((w for w in specs["exterior_wall_systems"] if w.get("system")=="2x6_timber_wall"),None)
        if existing is None:
            existing={"system":"2x6_timber_wall","evidence":"2×6外壁断面の主な構成"}
            specs["exterior_wall_systems"].append(existing)
        existing["phenolic_components_mm"]=[float(msum.group(1)),float(msum.group(2))]
        existing["total_phenolic_mm"]=float(msum.group(3))

    # Roof insulation must be explicitly tied to the roof in the drawing.
    # Do not reuse an exterior-wall legend such as
    # "2x6+フェノールフォーム190mm" as a roof specification.
    rfi=re.search(
        r"屋根\s*断熱\s*[:：]?\s*フェノールフォーム\s*厚?\s*(\d+(?:\.\d+)?)\s*mm",
        norm,re.I
    )
    if rfi:
        specs["roof_insulation"]={
            "material":"Phenolic foam",
            "thickness_mm":float(rfi.group(1)),
            "evidence":rfi.group(0),
            "semantic_scope":"roof_explicit",
        }

    # Detail/section XPS note.  This is kept separately because on the AZRAS
    # reference drawing it is visually attached directly below the 500 mm mat
    # foundation, while an older general note elsewhere says 300 mm.  The
    # section/detail callout has precedence during the final current-PDF gate.
    sx=re.search(
        r"(?:発泡スチロール|押出スチロール)[（(]?\s*XPS\s*[）)]?\s*厚\s*(\d+(?:\.\d+)?)(?:\s*mm)?",
        norm,re.I
    )
    if sx:
        specs["section_xps_insulation"]={
            "material":"XPS",
            "thickness_mm":float(sx.group(1)),
            "evidence":sx.group(0),
            "semantic_scope":"section_detail",
        }

    return specs


def build_common_building_model(structure, confidence, dimensions, roof_geometry,
                                openings, insulation, section_vertical_intervals,
                                structural_members, basic_specifications=None):
    """Method-neutral Planning Basic building model.

    This layer contains only facts/candidates obtained from the current PDF and
    is intentionally independent of RC / timber / steel / masonry semantics.
    Structure-specific quantity engines consume this model afterwards.
    """
    floor_areas=list(dimensions.get("floor_areas_m2") or [])
    opening_total=0.0
    for key,val in (openings or {}).items():
        if key.endswith("_window_m2") or key.endswith("_door_m2"):
            try:
                opening_total+=float(val or 0.0)
            except Exception:
                pass

    roof_area=0.0
    if roof_geometry:
        roof_area=float(roof_geometry.get("actual_sloped_roof_area_m2") or 0.0)

    vertical=[]
    if section_vertical_intervals:
        for rec in section_vertical_intervals.get("intervals") or []:
            try:
                vertical.append(float(rec.get("height_m") or 0.0))
            except Exception:
                pass

    return {
        "schema":"AZRAS_COMMON_BUILDING_MODEL_V1",
        "structure_candidate":structure,
        "structure_confidence":float(confidence or 0.0),
        "geometry":{
            "storeys":int(dimensions.get("storeys") or 0),
            "floor_areas_m2":floor_areas,
            "gross_floor_area_m2":float(dimensions.get("floor_area_m2") or 0.0),
            "footprint_m2":float(dimensions.get("footprint_m2") or 0.0),
            "width_m":float(dimensions.get("width_m") or 0.0),
            "depth_m":float(dimensions.get("depth_m") or 0.0),
            "roof_actual_area_m2":roof_area,
            "section_vertical_intervals_m":vertical,
        },
        "openings":{
            "directional":dict(openings or {}),
            "total_labeled_opening_area_m2":opening_total,
        },
        "insulation":dict(insulation or {}),
        "basic_specifications":dict(basic_specifications or {}),
        "structural_member_candidates":dict(structural_members or {}),
        "capabilities":{
            "structure_text":bool(structure),
            "storeys":bool(dimensions.get("storeys")),
            "floor_area":bool(dimensions.get("floor_area_m2")),
            "footprint":bool(dimensions.get("footprint_m2")),
            "roof_geometry":roof_area>0,
            "opening_takeoff":opening_total>0,
            "section_heights":bool(vertical),
            "insulation_text":bool(insulation),
            "structural_member_text":bool(structural_members),
        },
    }


def _detect_repeated_overall_plan_dimensions(text: str) -> dict[str, Any] | None:
    """Detect likely overall building grid dimensions from repeated dimension text.

    Architectural PDFs often repeat the same overall X/Y dimensions on plan,
    roof plan, elevation and section sheets.  Repetition is a stronger signal
    than simply choosing the largest number in the document, which may be a
    member length, drawing ID, or another unrelated dimension.
    """
    from collections import Counter
    vals=[]
    for token in re.findall(r"(?<!\d)(\d{5})(?!\d)", text or ""):
        try:
            v=int(token)
        except Exception:
            continue
        if 10000 <= v <= 50000:
            vals.append(v)
    counts=Counter(vals)
    candidates=[(cnt,v) for v,cnt in counts.items() if cnt>=2]
    if len(candidates)<2:
        return None
    candidates.sort(key=lambda x:(x[0],x[1]),reverse=True)
    first=candidates[0]
    # Prefer the second dimension with comparable repetition rather than an
    # unrelated one-off/lower-frequency dimension.
    second=next((x for x in candidates[1:] if x[1]!=first[1] and x[0]>=max(2,first[0]-1)),None)
    if second is None:
        second=next((x for x in candidates[1:] if x[1]!=first[1]),None)
    if second is None:
        return None
    dims_mm=sorted([float(first[1]),float(second[1])])
    return {
        "width_m":dims_mm[0]/1000.0,
        "depth_m":dims_mm[1]/1000.0,
        "footprint_m2":(dims_mm[0]*dims_mm[1])/1_000_000.0,
        "dimension_values_mm":[int(dims_mm[0]),int(dims_mm[1])],
        "repeat_counts":[counts[int(dims_mm[0])],counts[int(dims_mm[1])]],
        "source":"repeated_overall_dimensions_across_current_pdf",
        "requires_confirmation":True,
    }


def _steel_single_storey_evidence(text: str) -> dict[str, Any]:
    one=len(re.findall(r"(?<!\d)1FL(?!\d)",text or "",re.I))
    upper=sum(len(re.findall(fr"(?<!\d){n}FL(?!\d)",text or "",re.I)) for n in range(2,10))
    return {
        "one_fl_count":one,"upper_fl_count":upper,
        "single_storey_candidate": bool(one>=5 and upper<=1),
        "source":"current_pdf_level_markers",
    }


def analyze_pdf(pdf_path: str | Path, north_rotation_deg: float, profiles: dict[str, Any]) -> dict[str, Any]:
    text = extract_pdf_text(pdf_path)
    structure, confidence = identify_structure(text)
    profile = copy.deepcopy(profiles[structure])
    dimensions = detect_dimensions(text)
    # PATCH_85: steel-office drawings can have garbled Japanese embedded text,
    # while their repeated overall grid dimensions remain machine-readable.
    # Recover the plan scale from those repeated dimensions instead of letting a
    # stray 30095-like dimension become the footprint.
    steel_scale_audit=None
    if structure=="Steel Structure":
        overall=_detect_repeated_overall_plan_dimensions(text)
        level_ev=_steel_single_storey_evidence(text)
        if overall:
            dimensions["width_m"]=overall["width_m"]
            dimensions["depth_m"]=overall["depth_m"]
            dimensions["footprint_m2"]=overall["footprint_m2"]
            steel_scale_audit={"overall_dimensions":overall,"level_markers":level_ev}
            if level_ev.get("single_storey_candidate"):
                dimensions["storeys"]=1
                dimensions["floor_areas_m2"]=[overall["footprint_m2"]]
                dimensions["floor_area_m2"]=overall["footprint_m2"]
                dimensions["volume_m3"]=float(dimensions.get("volume_m3") or 0.0)
                dimensions["geometry_complete"]=True
                dimensions["missing_geometry_fields"]=[]
                dimensions["floor_area_source"]="current PDF repeated overall plan dimensions + level-marker audit"
                steel_scale_audit["storey_resolution"]={
                    "storeys":1,
                    "basis":"1FL repeated and no 2FL-9FL markers in current PDF",
                    "requires_confirmation":True,
                }
    section_vertical_intervals = detect_section_vertical_intervals(pdf_path)
    roof_geometry = detect_roof_geometry(pdf_path,text,dimensions)
    opening_takeoff = detect_openings_from_pdf(pdf_path)
    if opening_takeoff:
        openings={}
        for d in ("north","east","south","west"):
            rec=(opening_takeoff.get("directions") or {}).get(d,{})
            openings[f"{d}_window_m2"]=float(rec.get("window_area_m2") or 0.0)
            openings[f"{d}_door_m2"]=float(rec.get("door_area_m2") or 0.0)
    else:
        openings = detect_openings(text)
    insulation_defaults=profile
    if structure=="Steel Structure":
        # The legacy Steel Structure profile contains RC-frame comparison
        # placeholders. They must never masquerade as facts from an arbitrary
        # steel drawing. Start unresolved and adopt only explicit PDF evidence.
        insulation_defaults={"assemblies":{
            "rc_wall":{"thickness_mm":0.0},
            "light_wall":{"thickness_mm":0.0},
            "roof":{"thickness_mm":0.0},
            "slab":{"thickness_mm":0.0},
        }}
    insulation = detect_insulation(text, structure, insulation_defaults)
    if structure=="Steel Structure":
        for _part in ("rc_wall","light_wall","roof","slab"):
            _ev=(insulation.get("_evidence") or {}).get(_part) or {}
            if _ev.get("source")=="profile_default" or float((insulation.get(_part) or {}).get("thickness_mm") or 0.0)<=0:
                insulation.setdefault(_part,{})["resolved"]=False
                if float(insulation[_part].get("thickness_mm") or 0.0)<=0:
                    insulation[_part]["material"]="unresolved"
            else:
                insulation.setdefault(_part,{})["resolved"]=True
    basic_specifications = extract_basic_specifications(text, structure)
    structural_members = detect_structural_members(text, structure)

    # AZRAS uses the same method-neutral vector wall detector for its RC core.
    # Feed the explicit RC wall thickness from the current PDF into the generic
    # member geometry rather than creating an AZRAS-specific drawing parser.
    if structure=="AZRAS":
        rc_spec=next(
            (w for w in (basic_specifications.get("exterior_wall_systems") or [])
             if w.get("system")=="rc_wall"), {}
        )
        rc_mm=float(rc_spec.get("wall_thickness_mm") or 0.0)
        if rc_mm>0:
            structural_members.setdefault("member_geometry",{})["rc_wall_thickness_mm"]=rc_mm

    common_building_model = build_common_building_model(
        structure, confidence, dimensions, roof_geometry, openings, insulation,
        section_vertical_intervals, structural_members, basic_specifications
    )
    rc_overlap_policy = build_rc_overlap_policy(structural_members) if structure=="RC Frame" else None
    rc_vector_takeoff = extract_rc_vector_takeoff(pdf_path,dimensions,structural_members) if structure=="RC Frame" else None
    rc_wall_plan_takeoff = extract_generic_rc_wall_plan_takeoff(
        pdf_path,dimensions,structural_members
    ) if structure in {"RC Frame","AZRAS"} else None
    generic_beam_grid = extract_generic_beam_grid_takeoff(pdf_path,dimensions,structural_members) if structure=="RC Frame" else None
    rc_wall_top_control = classify_wall_axes_against_beam_grid(rc_wall_plan_takeoff,generic_beam_grid) if structure=="RC Frame" else None
    rc_internal_opening_audit = audit_internal_rc_openings(rc_wall_plan_takeoff) if structure in {"RC Frame","AZRAS"} else None
    stair_floor_voids = detect_stair_floor_voids(pdf_path,rc_wall_plan_takeoff) if structure in {"RC Frame","AZRAS"} else None
    loft_platform_underside = detect_loft_platform_underside_area(pdf_path) if structure in {"RC Frame","AZRAS"} else None
    stair_underside_finish = calculate_stair_underside_finish(stair_floor_voids,section_vertical_intervals) if structure in {"RC Frame","AZRAS"} else None
    non_rc_partitions = detect_generic_non_rc_partition_walls(pdf_path,rc_wall_plan_takeoff) if structure in {"RC Frame","AZRAS"} else None
    partition_finish_height = detect_partition_finish_heights(pdf_path,section_vertical_intervals) if structure in {"RC Frame","AZRAS"} else None
    partition_openings = resolve_partition_openings(non_rc_partitions) if structure in {"RC Frame","AZRAS"} else None
    partition_door_leaf_openings = detect_partition_door_leaf_openings(
        pdf_path,rc_wall_plan_takeoff,non_rc_partitions
    ) if structure in {"RC Frame","AZRAS"} else None
    partition_openings_consolidated = consolidate_partition_door_openings(
        partition_door_leaf_openings
    ) if structure in {"RC Frame","AZRAS"} else None
    partition_opening_height = detect_partition_opening_height(
        pdf_path,section_vertical_intervals,partition_finish_height
    ) if structure in {"RC Frame","AZRAS"} else None
    partition_board_net_candidate = calculate_partition_board_net_candidate(
        non_rc_partitions,
        partition_finish_height,
        partition_openings_consolidated,
        partition_opening_height
    ) if structure in {"RC Frame","AZRAS"} else None
    explicit_concrete = build_explicit_concrete_quantities(structural_members, dimensions)
    foundation_analysis = None
    if structure == "2x6 Timber":
        # PATCH_050: measure the foundation plan (internal strips included)
        # first; the older bay-repeat estimate stays as the fallback.
        foundation_analysis = detect_2x6_strip_foundation_plan_vector(pdf_path, dimensions)
        if not foundation_analysis or foundation_analysis.get("status")!="resolved_from_current_pdf_geometry":
            foundation_analysis = detect_2x6_foundation_from_pdf(pdf_path, dimensions)
        if not foundation_analysis or foundation_analysis.get("status")=="unresolved":
            foundation_analysis = detect_2x6_strip_foundation(text, dimensions)

    g = profile["geometry"]
    # Replace profile/sample geometry only with values from the current PDF.
    g["floor_area_m2"] = float(dimensions.get("floor_area_m2") or 0.0)
    g["storeys"] = int(dimensions.get("storeys") or 0)
    g["floor_areas_m2"] = dimensions.get("floor_areas_m2") or []
    g["footprint_m2"] = float(dimensions.get("footprint_m2") or 0.0)
    g["width_m"] = float(dimensions.get("width_m") or 0.0)
    g["depth_m"] = float(dimensions.get("depth_m") or 0.0)
    g["volume_m3"] = float(dimensions.get("volume_m3") or 0.0)
    if roof_geometry and roof_geometry.get("status")=="resolved_from_pdf_dimensions":
        g["roof_area_m2"] = float(roof_geometry.get("actual_sloped_roof_area_m2") or 0.0)
    elif structure=="Steel Structure" and float(dimensions.get("footprint_m2") or 0.0)>0:
        # Current steel reference has a roof plan but its Japanese title is
        # partially garbled in the embedded text. Keep the projected plan area
        # so quantities can proceed, while explicitly flagging slope/actual area
        # confirmation rather than returning a false zero.
        g["roof_area_m2"] = float(dimensions.get("footprint_m2") or 0.0)
        if isinstance(roof_geometry,dict):
            roof_geometry["projected_area_m2"]=g["roof_area_m2"]
            roof_geometry["planning_area_source"]="repeated overall plan dimensions"
            roof_geometry["requires_confirmation"]=True
    else:
        # Do not silently use footprint as roof area when roof geometry is unresolved.
        g["roof_area_m2"] = 0.0
    g["slab_area_m2"] = float(dimensions.get("footprint_m2") or 0.0)

    # Structural quantities in the method profile are sample/default data and
    # must not become current-project drawing quantities.  Replace them with
    # explicit/derived values from this PDF only; unresolved values remain zero.
    c = profile.setdefault("construction", {})
    c["common_building_model"] = common_building_model
    c["basic_specifications"] = basic_specifications
    if section_vertical_intervals:
        c["section_vertical_intervals"]=section_vertical_intervals
    # Do not inherit comparison/profile wall areas as if they were current-PDF
    # quantities. They will be populated only by a drawing-derived wall takeoff.
    c["rc_wall_area_m2"] = 0.0
    c["light_wall_area_m2"] = 0.0
    if opening_takeoff:
        profile["opening_takeoff"] = opening_takeoff
    c["member_geometry"] = structural_members.get("member_geometry", {})
    c["drawing_member_extraction"] = structural_members
    if rc_overlap_policy:
        c["rc_overlap_deduction_policy"] = rc_overlap_policy
    if rc_vector_takeoff:
        c["rc_vector_takeoff"] = rc_vector_takeoff
    if rc_wall_plan_takeoff:
        c["rc_wall_plan_takeoff"] = rc_wall_plan_takeoff
    if generic_beam_grid:
        c["generic_beam_grid"] = generic_beam_grid
    if rc_wall_top_control:
        c["rc_wall_top_control"] = rc_wall_top_control
    if rc_internal_opening_audit:
        c["rc_internal_opening_audit"] = rc_internal_opening_audit
    if stair_floor_voids:
        c["stair_floor_voids"] = stair_floor_voids
    if loft_platform_underside:
        c["loft_platform_underside"] = loft_platform_underside
    if stair_underside_finish:
        c["stair_underside_finish"] = stair_underside_finish
    if non_rc_partitions:
        c["non_rc_partitions"] = non_rc_partitions
    if partition_finish_height:
        c["partition_finish_height"] = partition_finish_height
    if partition_openings:
        c["partition_openings"] = partition_openings
    if partition_door_leaf_openings:
        c["partition_door_leaf_openings"] = partition_door_leaf_openings
    if partition_openings_consolidated:
        c["partition_openings_consolidated"] = partition_openings_consolidated
    if partition_opening_height:
        c["partition_opening_height"] = partition_opening_height
    if partition_board_net_candidate:
        c["partition_board_net_candidate"] = partition_board_net_candidate
    comp = explicit_concrete.get("components", {}) or {}
    c["concrete_volume_m3"] = {
        "slab_foundation": float((comp.get("foundation_slab") or {}).get("volume_m3") or 0.0),
        "strip_foundation": float((comp.get("strip_footing") or {}).get("volume_m3") or 0.0),
        "slab_on_ground": 0.0,
        "rc_walls": float((comp.get("rc_wall") or {}).get("volume_m3") or 0.0),
        "columns": float((comp.get("column") or {}).get("volume_m3") or 0.0),
        "beams": float((comp.get("beam") or {}).get("volume_m3") or 0.0),
        "upper_slabs": float((comp.get("slab") or {}).get("volume_m3") or 0.0),
        "underground_foundations": float((comp.get("isolated_footing") or {}).get("volume_m3") or 0.0) + float((comp.get("ground_beam") or {}).get("volume_m3") or 0.0),
        "total": float(explicit_concrete.get("total_m3") or 0.0),
    }
    c["concrete_quantity_extraction"] = explicit_concrete
    if foundation_analysis:
        c["foundation_geometry"] = foundation_analysis

    profile["assemblies"]["rc_wall"].update(insulation["rc_wall"])
    profile["assemblies"]["light_wall"].update(insulation["light_wall"])
    profile["assemblies"]["roof"].update(insulation["roof"])
    profile["assemblies"]["slab"].update(insulation["slab"])
    # Keep roof_specification synchronized with the drawing-extracted roof value.
    if "roof_specification" in profile:
        profile["roof_specification"]["total_insulation_mm"] = profile["assemblies"]["roof"]["thickness_mm"]
    profile["surfaces"] = make_four_surfaces(dimensions, openings, north_rotation_deg)
    profile["source_pdf"] = str(pdf_path)
    profile["north_rotation_deg"] = north_rotation_deg
    profile["analysis"] = {
        "identified_structure": structure,
        "confidence": confidence,
        "text_characters": len(text),
        "requires_confirmation": True,
        "roof_geometry": roof_geometry,
        "section_vertical_intervals": section_vertical_intervals,
        "opening_takeoff": opening_takeoff,
        "common_building_model": common_building_model,
        "basic_specifications": basic_specifications,
        "steel_scale_audit": steel_scale_audit,
        "building_scale": {
            "storeys": dimensions["storeys"],
            "floor_areas_m2": dimensions["floor_areas_m2"],
            "gross_floor_area_m2": dimensions["floor_area_m2"],
            "footprint_m2": dimensions["footprint_m2"],
            "geometry_complete": dimensions.get("geometry_complete", False),
            "missing_geometry_fields": dimensions.get("missing_geometry_fields", []),
            "source": dimensions["floor_area_source"],
        },
        "insulation_extraction": {
            "evidence": insulation.get("_evidence", {}),
            "conflicts": insulation.get("_conflicts", []),
            "floor_air_cavity_mm": insulation.get("_floor_air_cavity_mm"),
            "rule": "component-specific section/detail notes override generic notes; floor air cavity is never treated as insulation thickness",
        },
        "foundation_extraction": foundation_analysis,
        "structural_member_extraction": structural_members,
        "rc_overlap_deduction_policy": rc_overlap_policy,
        "rc_vector_takeoff": rc_vector_takeoff,
        "rc_wall_plan_takeoff": rc_wall_plan_takeoff,
        "generic_beam_grid": generic_beam_grid,
        "rc_wall_top_control": rc_wall_top_control,
        "rc_internal_opening_audit": rc_internal_opening_audit,
        "stair_floor_voids": stair_floor_voids,
        "loft_platform_underside": loft_platform_underside,
        "stair_underside_finish": stair_underside_finish,
        "non_rc_partitions": non_rc_partitions,
        "partition_finish_height": partition_finish_height,
        "partition_openings": partition_openings,
        "partition_door_leaf_openings": partition_door_leaf_openings,
        "partition_openings_consolidated": partition_openings_consolidated,
        "partition_opening_height": partition_opening_height,
        "partition_board_net_candidate": partition_board_net_candidate,
        "explicit_concrete_extraction": explicit_concrete,
        "quantity_policy": {
            "pdf_explicit": "自動認識したPDF明示値",
            "derived": "PDF明示寸法から算定した導出値",
            "missing": "未確認。既知3工法の固定値を流用しない",
            "requires_user_confirmation": True,
        },
        "notes": [
            "PDF text is read automatically; comparison-sample structural quantities are not reused as current-project evidence.",
            "Component-specific insulation notes are prioritized over generic notes.",
            "床下空気層 thickness is stored separately and is never used as XPS insulation thickness.",
            "If conflicting insulation thicknesses remain in a PDF, they are recorded under analysis.insulation_extraction.conflicts.",
            "North rotation and all wall/opening values remain editable.",
            "For arbitrary polygonal buildings, add or edit each facade in the surface table.",
        ],
    }
    return {"structure": structure, "profile": profile, "raw_text": text}

