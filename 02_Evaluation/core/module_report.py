
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from core.number_format import format_number
from core.branding import DISPLAY_NAME, COMPANY_EN, COMPANY_JA, COPYRIGHT


FONT_NAME = "HeiseiKakuGo-W5"
MODULE_NAMES_JA = {
    0: "共通データ・座標",
    1: "図面・数量・建物性能",
    2: "環境・CO₂・エネルギー",
    3: "修繕・更新・解体シナリオ",
    4: "長期・200年環境評価",
    5: "建設費",
    6: "投資評価",
    7: "修繕・解体積算",
    8: "200年事業収支",
    9: "災害復旧シナリオ",
}
MODULE_NAMES_EN = {
    0: "Common Project Data and Coordinates",
    1: "Drawing, Quantity and Building Performance",
    2: "Environment, CO2 and Energy",
    3: "Repair, Renewal and Demolition Scenario",
    4: "Long-Term / 200-Year Environmental Evaluation",
    5: "Construction Cost",
    6: "Investment Evaluation",
    7: "Repair and Demolition Cost",
    8: "200-Year Business Cash Flow",
    9: "Disaster Recovery Scenario",
}



KEYS_JA = {'schema_version': 'JSONスキーマ版', 'platform_version': 'プラットフォーム版', 'save_revision': '保存改訂番号', 'last_saved_by': '最終保存元', 'project_identity': 'プロジェクト識別情報', 'location': '所在地・気象情報', 'building': '建物共通情報', 'thermal': '断熱・空調共通情報', 'renewable_energy': '再生可能エネルギー情報', 'comparison_interface': '比較ソフト連携情報', 'comparison_export': '比較ソフト出力情報', 'roof_area_m2': '屋根面積', 'exterior_wall_area_m2': '外壁面積', 'window_area_m2': '窓面積', 'north_window_area_m2': '北面窓面積', 'east_window_area_m2': '東面窓面積', 'south_window_area_m2': '南面窓面積', 'west_window_area_m2': '西面窓面積', 'ua_W_m2K': 'UA値', 'average_u_value_W_m2K': '平均熱貫流率', 'effective_thermal_capacity_MJ_K': '有効熱容量', 'heating_cop': '暖房COP', 'cooling_cop': '冷房COP', 'heat_recovery_efficiency_percent': '熱交換効率', 'ventilation_ach': '換気回数', 'pv_enabled': 'PV設置', 'roof_utilization_percent': '屋根利用率', 'pv_area_m2': 'PV設置面積', 'panel_efficiency_percent': 'PV変換効率', 'pcs_efficiency_percent': 'PCS効率', 'self_consumption_percent': 'PV自家消費率', 'annual_generation_kWh': '年間PV発電量', 'annual_self_consumption_kWh': '年間PV自家消費量', 'annual_export_kWh': '年間売電量', 'annual_grid_import_kWh': '年間購入電力量', 'annual_cost_saving_JPY': '年間電気料金削減額', 'annual_export_revenue_JPY': '年間売電収入', 'annual_co2_reduction_kg': '年間CO₂削減量', 'calculation_status': '計算状態', 'reserved_for_v9_4_1': 'V9.4.1で計算予定', 'status': '状態', 'disclaimer': '注意事項', 'provisional_planning_value': '企画比較用暫定値', 'inspection': '点検', 'repair': '修繕', 'replacement': '更新', 'demolition': '解体', 'rebuild': '再建', 'repair_cycle': '修繕周期', 'equipment_life': '設備耐用年数', 'replacement_cycle': '更新周期', 'end_of_life': '耐用年数到達', 'source_module': '参照Module', 'requires_confirmation': '要確認', 'project_language': 'プロジェクト言語', 'currency': '通貨', 'weather_source': '気象データ取得元', 'export_ready': '比較出力準備完了', 'fixed_common_conditions': '固定共通条件'}
KEYS_EN = {'schema_version': 'JSON Schema Version', 'platform_version': 'Platform Version', 'save_revision': 'Save Revision', 'last_saved_by': 'Last Saved By', 'project_identity': 'Project Identity', 'location': 'Location and Weather', 'building': 'Common Building Data', 'thermal': 'Thermal and HVAC Data', 'renewable_energy': 'Renewable Energy Data', 'comparison_interface': 'Comparison Platform Interface', 'comparison_export': 'Comparison Export', 'roof_area_m2': 'Roof Area', 'exterior_wall_area_m2': 'Exterior Wall Area', 'window_area_m2': 'Window Area', 'north_window_area_m2': 'North Window Area', 'east_window_area_m2': 'East Window Area', 'south_window_area_m2': 'South Window Area', 'west_window_area_m2': 'West Window Area', 'ua_W_m2K': 'UA Value', 'average_u_value_W_m2K': 'Average U-Value', 'effective_thermal_capacity_MJ_K': 'Effective Thermal Capacity', 'heating_cop': 'Heating COP', 'cooling_cop': 'Cooling COP', 'heat_recovery_efficiency_percent': 'Heat Recovery Efficiency', 'ventilation_ach': 'Ventilation Rate', 'pv_enabled': 'PV Installed', 'roof_utilization_percent': 'Roof Utilization', 'pv_area_m2': 'PV Area', 'panel_efficiency_percent': 'Panel Efficiency', 'pcs_efficiency_percent': 'PCS Efficiency', 'self_consumption_percent': 'PV Self-Consumption Rate', 'annual_generation_kWh': 'Annual PV Generation', 'annual_self_consumption_kWh': 'Annual PV Self-Consumption', 'annual_export_kWh': 'Annual Export', 'annual_grid_import_kWh': 'Annual Grid Import', 'annual_cost_saving_JPY': 'Annual Electricity Cost Saving', 'annual_export_revenue_JPY': 'Annual Export Revenue', 'annual_co2_reduction_kg': 'Annual CO2 Reduction', 'calculation_status': 'Calculation Status', 'reserved_for_v9_4_1': 'Calculation planned for V9.4.1', 'status': 'Status', 'disclaimer': 'Disclaimer', 'provisional_planning_value': 'Provisional Planning Value', 'inspection': 'Inspection', 'repair': 'Repair', 'replacement': 'Replacement', 'demolition': 'Demolition', 'rebuild': 'Rebuild', 'repair_cycle': 'Repair Cycle', 'equipment_life': 'Equipment Life', 'replacement_cycle': 'Replacement Cycle', 'end_of_life': 'End of Life', 'source_module': 'Source Module', 'requires_confirmation': 'Confirmation Required', 'project_language': 'Project Language', 'currency': 'Currency', 'weather_source': 'Weather Data Source', 'export_ready': 'Comparison Export Ready', 'fixed_common_conditions': 'Fixed Common Conditions'}
VALUE_JA = {
    "Yes": "はい", "No": "いいえ", "True": "はい", "False": "いいえ",
    "provisional_planning_value": "企画比較用暫定値",
    "Provisional planning comparison only.": "本結果は企画比較用の暫定値です。実施設計では図面・仕様書・構造計算・設備表等に置き換えてください。",
    "inspection": "点検", "repair": "修繕", "replace_equipment": "設備更新",
    "replacement": "更新", "demolition": "解体", "rebuild": "再建",
    "inspection_cycle": "点検周期", "repair_cycle": "修繕周期",
    "equipment_life": "設備耐用年数", "replacement_cycle": "更新周期",
    "end_of_life": "耐用年数到達",
}

def _translate_key(key: str, language: str) -> str:
    leaf = str(key).split(".")[-1]
    table = KEYS_JA if language == "ja" else KEYS_EN
    translated = table.get(leaf, leaf)
    prefix = ".".join(str(key).split(".")[:-1])
    return f"{prefix}.{translated}" if prefix else translated

def _translate_value(value: Any, language: str) -> Any:
    if language == "ja" and isinstance(value, str):
        return VALUE_JA.get(value, value)
    return value


def _register_font() -> None:
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))
    except Exception:
        pass


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ModuleTitle", parent=base["Title"], fontName=FONT_NAME,
            fontSize=18, leading=24, textColor=colors.HexColor("#123b5d"),
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "ModuleSubtitle", parent=base["Normal"], fontName=FONT_NAME,
            fontSize=10, leading=15, textColor=colors.HexColor("#555555"),
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "ModuleH1", parent=base["Heading1"], fontName=FONT_NAME,
            fontSize=13, leading=18, textColor=colors.HexColor("#245b7a"),
            spaceBefore=7, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "ModuleBody", parent=base["BodyText"], fontName=FONT_NAME,
            fontSize=8.5, leading=13,
        ),
        "small": ParagraphStyle(
            "ModuleSmall", parent=base["BodyText"], fontName=FONT_NAME,
            fontSize=7, leading=10,
        ),
        "warning": ParagraphStyle(
            "ModuleWarning", parent=base["BodyText"], fontName=FONT_NAME,
            fontSize=7.5, leading=11, textColor=colors.HexColor("#8b0000"),
        ),
    }


def _escape(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_escape(value), style)


def _display_scalar(value: Any, key: str = "", language: str = "ja") -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return ("はい" if value else "いいえ") if language == "ja" else ("Yes" if value else "No")
    if isinstance(value, (int, float)):
        lower = key.lower()
        if "percent" in lower or lower.endswith("_rate"):
            return format_number(value, "%")
        if "cost" in lower or "rent" in lower or "investment" in lower or "npv" in lower or "cashflow" in lower:
            return format_number(value, "JPY")
        if "co2" in lower:
            return format_number(value, "kg-CO₂")
        if "energy" in lower or lower.endswith("_mj"):
            return format_number(value, "MJ")
        if "area" in lower or lower.endswith("_m2"):
            return format_number(value, "m²")
        if "day" in lower or "duration" in lower:
            return format_number(value, "日", 0)
        if "year" in lower:
            return format_number(value, "年", 0)
        if "kg" in lower or "waste" in lower:
            return format_number(value, "kg")
        return format_number(value)
    return str(_translate_value(value, language))


def _flatten(
    value: Any,
    prefix: str = "",
    rows: list[list[str]] | None = None,
    depth: int = 0,
    max_rows: int = 220,
    language: str = "ja",
) -> list[list[str]]:
    if rows is None:
        rows = []
    if len(rows) >= max_rows:
        return rows
    if depth > 6:
        rows.append([prefix or "-", "(nested data omitted)"])
        return rows

    if isinstance(value, dict):
        for key, item in value.items():
            if len(rows) >= max_rows:
                break
            label = f"{prefix}.{key}" if prefix else str(key)
            if key in ("cashflow", "annual_timeline", "hourly_results") and isinstance(item, list):
                rows.append([_translate_key(label, language), f"{len(item):,}件（集計のみ）" if language == "ja" else f"{len(item):,} rows (summary only)"])
                continue
            if isinstance(item, (dict, list)):
                _flatten(item, label, rows, depth + 1, max_rows, language)
            else:
                rows.append([_translate_key(label, language), _display_scalar(item, str(key), language)])
    elif isinstance(value, list):
        for index, item in enumerate(value[:80]):
            if len(rows) >= max_rows:
                break
            label = f"{prefix}[{index + 1}]"
            if isinstance(item, (dict, list)):
                _flatten(item, label, rows, depth + 1, max_rows, language)
            else:
                rows.append([_translate_key(label, language), _display_scalar(item, prefix, language)])
        if len(value) > 80:
            rows.append([_translate_key(prefix, language), f"... 残り{len(value) - 80:,}件は省略" if language == "ja" else f"... {len(value) - 80:,} additional entries omitted"])
    else:
        rows.append([_translate_key(prefix or "value", language), _display_scalar(value, prefix, language)])
    return rows


def _table(rows: list[list[Any]], widths: list[float]) -> Table:
    styles = _styles()
    converted = [
        [cell if isinstance(cell, Paragraph) else _p(cell, styles["small"]) for cell in row]
        for row in rows
    ]
    table = Table(converted, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#9ca9b3")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dceef8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#123b5d")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7f9")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


class _ModuleDoc(BaseDocTemplate):
    def __init__(self, output: Path, title: str):
        super().__init__(
            str(output),
            pagesize=A4,
            rightMargin=15 * mm,
            leftMargin=15 * mm,
            topMargin=16 * mm,
            bottomMargin=15 * mm,
            title=title,
            author=COMPANY_EN,
        )
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        self.addPageTemplates(PageTemplate(id="main", frames=[frame], onPage=self._footer))

    def _footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT_NAME, 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(15 * mm, 8 * mm, f"{DISPLAY_NAME} — Module Report — Page {doc.page}")
        canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"{COMPANY_EN} / {COMPANY_JA}")
        canvas.restoreState()


def generate_module_report(
    project: dict[str, Any],
    module_no: int,
    output_path: str | Path,
    source_path: str | Path | None = None,
    language: str = "ja",
) -> Path:
    _register_font()
    styles = _styles()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    names = MODULE_NAMES_JA if language == "ja" else MODULE_NAMES_EN
    module_name = names.get(module_no, f"Module {module_no}")
    common = project.get("common", {})
    project_name = common.get("project_name") or "AZRAS Project"

    if module_no == 0:
        content = common
    else:
        content = project.get("module_outputs", {}).get(f"module{module_no}") or {}

    story = [
        _p(f"Module {module_no} - {module_name}", styles["title"]),
        _p(project_name, styles["subtitle"]),
        _table([
            ["Project", project_name],
            ["Project ID", common.get("azras_project_number") or common.get("project_id") or "-"],
            ["Project JSON", source_path or "-"],
            ["Output Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            ["Gross Floor Area", f'{_display_scalar(common.get("scale_gfa_m2"), "area")} m²'],
        ], [45 * mm, 130 * mm]),
        Spacer(1, 6 * mm),
        _p("Module Content" if language == "en" else "Module内容", styles["h1"]),
    ]

    if content:
        rows = [["Item" if language == "en" else "項目", "Value" if language == "en" else "内容"]]
        rows.extend(_flatten(content, language=language))
        story.append(_table(rows, [75 * mm, 100 * mm]))
    else:
        story.append(_p(
            "No saved result is available for this module."
            if language == "en"
            else "このModuleの保存済み結果はありません。",
            styles["body"],
        ))

    story += [
        Spacer(1, 7 * mm),
        _p(
            "This report is generated from the current Project JSON. Confirm drawings, specifications, "
            "structural and equipment design, estimates, laws, official data and third-party verification "
            "before design, contract, certification or investment decisions."
            if language == "en"
            else
            "本印刷物は現在のProject JSONに保存された内容から作成しています。"
            "実施設計・契約・認証・投資判断では、図面、仕様書、構造・設備設計、見積書、"
            "法令、公的資料および第三者検証を確認してください。",
            styles["warning"],
        ),
    ]

    doc = _ModuleDoc(output, f"AZRAS Module {module_no} Report")
    doc.build(story)
    return output
