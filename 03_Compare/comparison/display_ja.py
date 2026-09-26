# -*- coding: utf-8 -*-
"""Japanese DISPLAY names for English-canonical identifiers (03 Compare).

AZRAS keeps English-canonical identifiers in Project JSON (construction method
ids, cost_item_key, Module 6 setting keys, region names).  03 Compare showed
those raw identifiers on the Japanese screen, so English was mixed into the
Japanese tables and graphs.  This module is PRESENTATION ONLY: it never
changes a stored value, a dictionary key or a comparison key.

Sources (copied, not invented):
  STRUCTURE_JA / METHOD_JA / NAME_EN_JA  <- 01 Planning data/construction_method_profiles.json
  COST_ITEM_JA / PACKAGE_JA              <- 01 Planning data/construction_cost_database_v9_4.json
  SETTING_JA["module6"]                  <- 02 Evaluation lang/ja.json + module6 on-screen labels
  CITY_JA / USE_JA / UNIT_JA / VALUE_JA  <- standard Japanese names for the regions offered by
                                            01 Planning regional_suitability_database_v1.json and
                                            for fixed code values; unknown values pass through.
An identifier that is not listed is shown unchanged (never guessed).
"""
from __future__ import annotations

STRUCTURE_JA = {
    "wood_post_beam": "木造軸組構造",
    "wood_frame": "木造枠組壁構造",
    "mass_timber": "Mass Timber構造",
    "steel": "S造",
    "rc_frame": "RCラーメン構造",
    "rc_wall": "RC壁式構造",
    "masonry": "組積造・ブロック造",
    "earth": "土・伝統構造",
    "other": "その他",
    "azras": "AZRAS Platform"
}

METHOD_JA = {
    "traditional": "在来軸組",
    "hardware": "金物工法",
    "se": "SE構法",
    "post_beam": "ポスト&ビーム",
    "timber_frame_post_beam": "Timber Frame（柱梁式）",
    "2x4": "2×4",
    "2x6": "2×6",
    "platform": "Platform Framing",
    "balloon": "Balloon Framing",
    "timber_frame_wall": "Timber Frame（壁式）",
    "clt": "CLT",
    "glt": "GLT",
    "lvl": "LVL",
    "nlt": "NLT",
    "dlt": "DLT",
    "mass_plywood": "Mass Plywood",
    "conventional_steel": "一般鉄骨造",
    "light_gauge_steel": "軽量鉄骨造",
    "heavy_steel": "重量鉄骨造",
    "peb": "PEB（プレエンジニアード）",
    "steel_prefab": "鉄骨プレハブ",
    "conventional_rc": "一般RC",
    "rcc_frame": "RCC Frame",
    "icf": "ICF",
    "precast_rc": "プレキャストRC",
    "src": "SRC",
    "cast_in_place": "現場打ちRC壁式",
    "precast_wall": "プレキャストRC壁式",
    "insulated_rc_panel": "断熱RCパネル",
    "brick": "レンガ造",
    "cmu": "CMU",
    "aac": "AAC",
    "maconnerie": "Maçonnerie",
    "stone": "石造",
    "adobe": "Adobe",
    "rammed_earth": "Rammed Earth",
    "cob": "Cob",
    "earth_wall": "土壁",
    "modular": "モジュール工法",
    "manufactured_home": "マニュファクチャード・ホーム",
    "three_d_printed": "3Dプリント工法",
    "hybrid": "複合・ハイブリッド工法",
    "other": "その他",
    "azras_platform": "AZRAS Platform"
}

NAME_EN_JA = {
    "Wood Post-and-Beam": "木造軸組構造",
    "Traditional Post-and-Beam": "在来軸組",
    "Metal Connector System": "金物工法",
    "SE System": "SE構法",
    "Post & Beam": "ポスト&ビーム",
    "Timber Frame (Post-and-Beam)": "Timber Frame（柱梁式）",
    "Wood Framed-Wall": "木造枠組壁構造",
    "2×4": "2×4",
    "2×6": "2×6",
    "Platform Framing": "Platform Framing",
    "Balloon Framing": "Balloon Framing",
    "Timber Frame (Wall System)": "Timber Frame（壁式）",
    "Mass Timber": "Mass Timber構造",
    "CLT": "CLT",
    "GLT": "GLT",
    "LVL": "LVL",
    "NLT": "NLT",
    "DLT": "DLT",
    "Mass Plywood": "Mass Plywood",
    "Steel Structure": "S造",
    "Conventional Steel Frame": "一般鉄骨造",
    "Light-Gauge Steel Frame": "軽量鉄骨造",
    "Heavy Steel Frame": "重量鉄骨造",
    "Pre-Engineered Building": "PEB（プレエンジニアード）",
    "Steel Prefabricated": "鉄骨プレハブ",
    "RC Moment Frame": "RCラーメン構造",
    "Conventional RC": "一般RC",
    "RCC Frame": "RCC Frame",
    "ICF": "ICF",
    "Precast RC": "プレキャストRC",
    "SRC": "SRC",
    "RC Wall Structure": "RC壁式構造",
    "Cast-in-Place RC Wall": "現場打ちRC壁式",
    "Precast RC Wall": "プレキャストRC壁式",
    "Insulated RC Panel": "断熱RCパネル",
    "Masonry / Block": "組積造・ブロック造",
    "Brick Masonry": "レンガ造",
    "CMU": "CMU",
    "AAC": "AAC",
    "Maçonnerie": "Maçonnerie",
    "Stone Masonry": "石造",
    "Earth / Traditional": "土・伝統構造",
    "Adobe": "Adobe",
    "Rammed Earth": "Rammed Earth",
    "Cob": "Cob",
    "Earth Wall": "土壁",
    "Other": "その他",
    "Modular Construction": "モジュール工法",
    "Manufactured Home": "マニュファクチャード・ホーム",
    "3D-Printed Construction": "3Dプリント工法",
    "Hybrid Construction": "複合・ハイブリッド工法"
}

COST_ITEM_JA = {
    "concrete": "コンクリート",
    "reinforcing_steel": "鉄筋",
    "structural_steel": "構造用鉄骨",
    "dimension_lumber": "2×6・一般木材",
    "clt": "CLT・Mass Timber",
    "phenolic_foam": "フェノールフォーム",
    "xps": "XPS",
    "glass": "ガラス・窓",
    "gypsum_board": "石膏ボード",
    "roofing": "屋根・防水",
    "doors": "ドア・建具",
    "interior_finish": "内装最終仕上（下地・石膏ボード除外）",
    "external_finish": "外装最終仕上（断熱・下地除外）",
    "formwork": "型枠工事",
    "structural_plywood": "構造用合板12mm",
    "external_finish_rc": "RC部外装最終仕上（断熱・下地除外）",
    "external_finish_timber": "木造部外装最終仕上（断熱・構造用合板除外）",
    "excavation": "根切り・掘削",
    "backfill": "埋戻し",
    "imported_fill": "客土・購入土",
    "soil_disposal": "残土処分",
    "blinding_concrete": "捨てコンクリート",
    "ground_preparation": "基礎下地業・砕石",
    "phc_pile": "PHC杭（杭長）",
    "shutter": "シャッター",
    "louver": "ガラリ",
    "roof_glass_wool": "屋根グラスウール",
    "tempered_glass": "強化ガラス",
    "oa_floor": "OAフロア",
    "vapor_barrier": "防湿層",
    "ceiling_lgs": "天井下地 LGS",
    "ceiling_glass_wool": "天井グラスウール",
    "ceiling_insulation_area": "天井断熱（面積基準）",
    "parapet_coping": "笠木",
    "rainwater_gutter": "雨樋（軒樋・竪樋）"
}

PACKAGE_JA = {
    "hvac": "空調設備一式",
    "electrical": "電気設備一式",
    "plumbing": "給排水衛生設備一式",
    "kitchen": "キッチン一式",
    "bathroom": "ユニットバス等一式",
    "other": "その他設備一式"
}

SETTING_JA = {
    "module6": {
        "analysis_years": "評価期間（年）",
        "annual_rent_per_m2": "市場家賃入力：年間賃料単価（/m²・年）",
        "vacancy_rate_percent": "空室率（%）",
        "rent_growth_percent": "賃料成長率（%）",
        "operating_expense_percent": "運営費率（賃料比%）",
        "annual_maintenance_percent_of_cost": "日常維持管理費率（Module 7外・%/年）",
        "insurance_percent_of_cost": "保険料率（建設費比%）",
        "discount_rate_percent": "割引率 (%)",
        "terminal_cap_rate_percent": "最終還元利回り（Cap Rate）（%）",
        "terminal_sale_cost_percent": "売却費用率（%）",
        "land_cost": "土地取得費",
        "other_initial_cost": "その他初期費用",
        "loan_to_cost_percent": "借入比率（LTV）",
        "annual_interest_rate_percent": "借入金利（年%）",
        "loan_term_years": "借入期間（年）",
        "construction_cost_escalation_percent": "建設・更新工事費上昇率 (%)",
        "general_inflation_percent": "一般物価上昇率 (%)",
        "earthquake_insurance_share_percent": "保険料のうち地震保険相当分 (%)",
        "earthquake_insurance_discount_percent": "地震保険割引率（確認済みのみ・%）",
        "target_gross_yield_percent": "目標表面利回り (%)",
        "rent_setting_method": "家賃の設定方法"
    },
    "module5": {
        "overhead_rate": "諸経費率 (%)"
    },
    "module7": {}
}

CITY_JA = {
    "Tokyo": "東京",
    "Sapporo": "札幌",
    "London": "ロンドン",
    "Paris": "パリ",
    "New York": "ニューヨーク",
    "Los Angeles": "ロサンゼルス",
    "Dubai": "ドバイ",
    "Singapore": "シンガポール",
    "Bangkok": "バンコク",
    "Delhi": "デリー",
    "Sydney": "シドニー",
    "Berlin": "ベルリン",
    "Oslo": "オスロ",
    "Toronto": "トロント",
    "Mexico City": "メキシコシティ",
    "Kasugai": "春日井",
    "Nagoya": "名古屋",
    "Osaka": "大阪",
    "Japan": "日本",
    "United Kingdom": "イギリス",
    "France": "フランス",
    "United States": "アメリカ",
    "United Arab Emirates": "アラブ首長国連邦",
    "Thailand": "タイ",
    "India": "インド",
    "Australia": "オーストラリア",
    "Germany": "ドイツ",
    "Norway": "ノルウェー",
    "Canada": "カナダ",
    "Mexico": "メキシコ",
    "Base region": "基準地域"
}

USE_JA = {
    "residential": "住宅",
    "house": "住宅",
    "apartment": "共同住宅",
    "office": "事務所",
    "commercial": "商業施設",
    "retail": "店舗",
    "factory": "工場",
    "warehouse": "倉庫",
    "school": "学校",
    "hospital": "病院",
    "hotel": "ホテル",
    "mixed use": "複合用途",
    "unknown": "不明",
    "other": "その他"
}

UNIT_JA = {
    "lump_sum": "一式",
    "m2": "m²",
    "m3": "m³",
    "set": "式",
    "item": "個所"
}

VALUE_JA = {
    "market_rent": "市場家賃を直接入力",
    "gross_yield": "表面利回りから逆算（標準）",
    "True": "はい",
    "False": "いいえ",
    "installed_all_in": "施工込み一本値",
    "ai_session": "AI概算セッション",
    "ui_local_currency": "画面入力（現地通貨）"
}

KIND_JA = {
    "item": "工種",
    "unit_mismatch": "単位不一致",
    "family": "必須部位",
    "package": "設備一式",
    "unit_cost": "単価",
    "equipment_package": "設備一式"
}

MODULE_JA = {"module5": "Module 5", "module6": "Module 6", "module7": "Module 7"}


def _clean(v):
    return "" if v is None else str(v)


def structure_ja(structure_id="", name_ja="", name_en=""):
    """Japanese structure name: saved *_ja first, then the Planning registry."""
    if _clean(name_ja).strip():
        return str(name_ja)
    sid = _clean(structure_id)
    if sid in STRUCTURE_JA:
        return STRUCTURE_JA[sid]
    return NAME_EN_JA.get(_clean(name_en), _clean(name_en) or sid)


def method_ja(method_id="", name_ja="", name_en=""):
    if _clean(name_ja).strip():
        return str(name_ja)
    mid = _clean(method_id)
    if mid in METHOD_JA:
        return METHOD_JA[mid]
    return NAME_EN_JA.get(_clean(name_en), _clean(name_en) or mid)


def city_ja(name):
    s = _clean(name)
    return CITY_JA.get(s, s)


def use_ja(name):
    s = _clean(name)
    return USE_JA.get(s.strip().lower(), s)


def unit_ja(unit):
    s = _clean(unit)
    return UNIT_JA.get(s, s)


def value_ja(value):
    s = _clean(value)
    return VALUE_JA.get(s, s)


def kind_ja(kind):
    s = _clean(kind)
    return KIND_JA.get(s, s)


def cost_key_ja(key):
    s = _clean(key)
    return COST_ITEM_JA.get(s) or PACKAGE_JA.get(s) or s


def setting_ja(row_id):
    """'module6:discount_rate_percent' -> 'Module 6：割引率 (%)'."""
    module, _, key = _clean(row_id).partition(":")
    if not key:
        return _clean(row_id)
    label = (SETTING_JA.get(module) or {}).get(key, key)
    return f"{MODULE_JA.get(module, module)}：{label}"


def component_ja(text):
    """'structure_rc_frame, structure_azras' -> '構造躯体（RCラーメン構造）, ...'."""
    out = []
    for part in [p.strip() for p in _clean(text).split(",")]:
        if part.startswith("structure_"):
            sid = part[len("structure_"):]
            out.append("構造躯体（" + STRUCTURE_JA.get(sid, sid) + "）")
        else:
            out.append(part)
    return ", ".join(out)
