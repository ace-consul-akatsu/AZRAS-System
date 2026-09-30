
from __future__ import annotations
import json
import threading
import copy
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from services.project_export_paths import default_export_path, project_data_directory, weather_method_directory

from core.i18n import I18N
from core.error_text import friendly_exception_text
from core.canonical_language import LANGUAGE_OPTIONS
from core.ui_style import (apply_common_style, standardize_module_window, create_scrollable_module_page, add_module_text_copy_button)
from core.module_report_ui import attach_module_report_button
from core.project_store import load_project, save_project
from core.project_coordinator import update_module_and_propagate, format_report, module_output_is_current, require_current_module_output
from ui.table import AZRASTable
from ui.splitter import AZRASSplitter
from ui.graph import MultiSeriesBarChart
from services.environment_engine_v9_1 import run_environment, _component_concrete_quantities
from services.envelope_insulation_model_v1 import (
    MATERIALS, MATERIAL_LABELS_JA, POSITION_LABELS_JA, COMPONENT_LABELS_JA,
    lambda_for, normalize_position
)
from services.weather_catalog_v9_2_9 import WeatherCatalog, normalize_country
from services.automatic_weather_retrieval_v9_3_2 import (
    ENERGYPLUS_WEATHER_PAGE,
    retrieve_nearest_epw,
)

INPUT_BG = "#fff4b8"
AUTO_BG = "#d9efff"
RESULT_BG = "#dff3df"


# PATCH_276 — Module 2 English-canonical result contract.
_M2_GENERATED_TEXT_KEYS = {
    "status","source","source_mode","method","basis","calculation_basis",
    "reason","message","note","description","remark","classification_status",
}

def _m2_canonicalize_generated(value, key=None):
    """Keep Module 2 machine results English-canonical.
    UI labels and user-entered/source text are not translated here.
    """
    if isinstance(value, dict):
        return {k: _m2_canonicalize_generated(v, k) for k,v in value.items()}
    if isinstance(value, list):
        return [_m2_canonicalize_generated(v, key) for v in value]
    if isinstance(value, str) and key in _M2_GENERATED_TEXT_KEYS:
        # Module 2 engines are already authored in English.  This boundary exists
        # to prevent future UI-language strings from leaking into saved results.
        aliases={
            "確認済":"confirmed",
            "推定":"estimated",
            "未確定":"unresolved",
            "要確認":"review required",
            "自動":"automatic",
            "手動":"manual",
        }
        return aliases.get(value, value)
    return value

def _resolve_project_currency(project, root_dir):
    """Resolve PV tariff currency without reinterpreting legacy JPY as foreign money."""
    project=project if isinstance(project,dict) else {}
    common=project.get("common") if isinstance(project.get("common"),dict) else {}
    ident=common.get("project_identity") if isinstance(common.get("project_identity"),dict) else {}
    loc=common.get("location") if isinstance(common.get("location"),dict) else {}
    country=str(loc.get("country") or "").strip()
    declared=str(ident.get("currency") or "").strip().upper()
    if country.lower()=="japan":
        return "JPY"
    if declared and declared!="JPY":
        return declared
    try:
        db=json.loads((Path(root_dir)/"data"/"construction_cost_database_v9_4.json").read_text(encoding="utf-8"))
        currencies=set()
        for name,rec in (db.get("locations") or {}).items():
            if str(name).lower().startswith(country.lower()+" /") and rec.get("currency"):
                currencies.add(str(rec.get("currency")).upper())
        if len(currencies)==1:
            return next(iter(currencies))
    except Exception:
        pass
    return "UNSET"


class Module2App(tk.Toplevel):
    def __init__(self, master, root_dir: Path, language: str = "ja", project_context=None):
        super().__init__(master)
        apply_common_style(self)
        standardize_module_window(self,2)
        self.project_context = project_context
        self.root_dir = Path(root_dir)
        self.i18n = I18N(self.root_dir, language)
        self.project = None
        self.project_path = None
        self.hourly = None
        self.summary = None

        self.project_file = tk.StringVar()
        self.weather_file = tk.StringVar()
        self.project_country = tk.StringVar(value="")
        self.weather_choice = tk.StringVar(value="")
        self.weather_choice_map = {}
        self.weather_status = tk.StringVar(value="")
        self.weather_source_url = tk.StringVar(value=ENERGYPLUS_WEATHER_PAGE)
        self.auto_weather_started = False
        self.weather_catalog = WeatherCatalog(self.root_dir)
        self.region_profile = tk.StringVar(value="Japan / Nagoya")
        renewable = (
            (self.project_context.project.get("common", {}).get("renewable_energy") or {})
            if self.project_context is not None
            and self.project_context.project is not None
            else {}
        )
        self.pv_enabled = tk.BooleanVar(
            value=bool(renewable.get("pv_enabled", True))
        )
        self.pv_vars = {
            "roof_utilization_percent": tk.StringVar(
                value=str(renewable.get("roof_utilization_percent", 80.0))
            ),
            "panel_efficiency_percent": tk.StringVar(
                value=str(renewable.get("panel_efficiency_percent", 22.0))
            ),
            "pcs_efficiency_percent": tk.StringVar(
                value=str(renewable.get("pcs_efficiency_percent", 97.0))
            ),
            "self_consumption_percent": tk.StringVar(
                value=str(renewable.get("self_consumption_percent", 80.0))
            ),
            "purchase_price_local_currency_per_kWh": tk.StringVar(
                value=str(
                    renewable.get("purchase_price_local_currency_per_kWh")
                    if renewable.get("purchase_price_local_currency_per_kWh") is not None
                    else (renewable.get("purchase_price_JPY_per_kWh",30.0)
                          if _resolve_project_currency(
                              self.project_context.project if self.project_context and self.project_context.project else {},
                              self.root_dir)=="JPY" else 0.0)
                )
            ),
            "export_price_local_currency_per_kWh": tk.StringVar(
                value=str(
                    renewable.get("export_price_local_currency_per_kWh")
                    if renewable.get("export_price_local_currency_per_kWh") is not None
                    else (renewable.get("export_price_JPY_per_kWh",16.0)
                          if _resolve_project_currency(
                              self.project_context.project if self.project_context and self.project_context.project else {},
                              self.root_dir)=="JPY" else 0.0)
                )
            ),
        }
        self.pv_roof_area = tk.StringVar(value="")
        self.pv_area = tk.StringVar(value="")
        self.analysis_mode = tk.StringVar(value="simple")
        self.analysis_mode_display = tk.StringVar(value="簡易" if self.i18n.language == "ja" else "Simple")
        self.strategy_enabled = {
            "thermal_mass_enabled": tk.BooleanVar(value=True),
            "external_insulation_enabled": tk.BooleanVar(value=True),
            "night_heat_release_enabled": tk.BooleanVar(value=True),
            "natural_night_ventilation_enabled": tk.BooleanVar(value=True),
        }
        self.strategy_vars = {
            "external_insulation_reference_u_multiplier": tk.StringVar(value="3.0"),
            "night_release_start_hour": tk.StringVar(value="22"),
            "night_release_end_hour": tk.StringVar(value="6"),
            "night_release_conductance_W_K": tk.StringVar(value="360"),
            "night_ventilation_ach": tk.StringVar(value="3.0"),
            "night_ventilation_delta_C": tk.StringVar(value="2.0"),
        }
        self.vars = {
            "heating_setpoint": tk.StringVar(value="20"),
            "cooling_setpoint": tk.StringVar(value="27"),
            "heating_cop": tk.StringVar(value="3.5"),
            "cooling_cop": tk.StringVar(value="3.2"),
            "ach": tk.StringVar(value="0.5"),
            "heat_recovery": tk.StringVar(value="0.70"),
            "window_shgc": tk.StringVar(value="0.45"),
            "solar_shading": tk.StringVar(value="0.75"),
            "electricity_co2": tk.StringVar(value="0.43"),
            "primary_energy_factor": tk.StringVar(value="9.76"),
            "ground_mean": tk.StringVar(value="16"),
            "ground_amplitude": tk.StringVar(value="5.5"),
            "ground_phase_day": tk.StringVar(value="45"),
            "active_fraction_wall": tk.StringVar(value="0.35"),
            "active_fraction_slab": tk.StringVar(value="0.25"),
            "internal_gain_day": tk.StringVar(value="5.0"),
            "internal_gain_night": tk.StringVar(value="2.0"),
        }
        # Detailed ground-floor / foundation / RC thermal-mass conditions.
        # Saved under Module 2 settings to preserve compatibility with older projects.
        self.floor_thermal_vars = {
            "ground_floor_type": tk.StringVar(value=""),
            "air_gap_mm": tk.StringVar(value=""),
            "insulation_position": tk.StringVar(value=""),
            "foundation_bottom_insulation": tk.BooleanVar(value=False),
            "slab_under_insulation": tk.BooleanVar(value=False),
            "slab_insulation_thickness_mm": tk.StringVar(value="100"),
            "slab_insulation_conductivity_W_mK": tk.StringVar(value="0.028"),
            "exterior_rc_active_fraction": tk.StringVar(value="0.35"),
            "partition_rc_active_fraction": tk.StringVar(value="0.60"),
            "frame_rc_active_fraction": tk.StringVar(value="0.35"),
            "slab_active_fraction_direct": tk.StringVar(value="0.35"),
            "slab_active_fraction_raised": tk.StringVar(value="0.10"),
            "exterior_rc_volume_m3": tk.StringVar(value=""),
            "partition_rc_volume_m3": tk.StringVar(value=""),
            "other_floor_name": tk.StringVar(value=""),
            "other_floor_detail": tk.StringVar(value=""),
            "other_slab_concrete_m3": tk.StringVar(value=""),
            "other_effective_fraction": tk.StringVar(value="0.20"),
            "other_ground_u_W_m2K": tk.StringVar(value="0.50"),
        }
        # Module 1 quantities are display-only in Module 2.  Hidden volume
        # variables above are populated from Module 1 to prevent accidental
        # double entry and double counting.
        self.rc_quantity_display = {
            "exterior_volume_m3": tk.StringVar(value="—"),
            "partition_volume_m3": tk.StringVar(value="—"),
            "exterior_surface_m2": tk.StringVar(value="—"),
            "partition_surface_m2": tk.StringVar(value="—"),
            "classification_status": tk.StringVar(value=""),
        }

        self.region_db = json.loads(
            (self.root_dir / "data" / "environment_region_profiles_v9_1.json")
            .read_text(encoding="utf-8")
        )
        if self.project_context is not None and self.project_context.path is not None:
            self.project = self.project_context.reload()
            self.project_path = self.project_context.path
            self.project_file.set(self.project_context.display_path)
            self._configure_project_weather_storage()
        self.title(self.i18n.t("module2"))
        self.build();attach_module_report_button(self,2)
        if self.project is not None:
            country = normalize_country(self.project.get("common", {}).get("country", ""))
            self.project_country.set(country)
            self.restore_saved_weather_selection()
            self.restore_saved_environment_state()
            self.after(350, self.start_automatic_weather_if_needed)
        self.bind("<FocusIn>", self.refresh_project_from_context)

    def _configure_project_weather_storage(self):
        """Bind weather downloads/catalog to the active Project folder."""
        if self.project_path is None:
            return None
        data_root = project_data_directory(self.project_path, create=False)
        self.weather_catalog = WeatherCatalog(self.root_dir, data_root / "Catalog")
        return data_root

    def refresh_project_from_context(self, event=None):
        """Use only the Project JSON selected or created in Module 0."""
        if self.project_context is None or self.project_context.path is None:
            return False
        active_path = self.project_context.path
        current_path = getattr(self, "project_path", None)
        path_changed = current_path is None or Path(current_path) != Path(active_path)
        if path_changed:
            self.project = self.project_context.reload()
            self.project_path = active_path
            self._configure_project_weather_storage()
            if hasattr(self, "project_file"):
                self.project_file.set(self.project_context.display_path)
            # A newly loaded Project JSON must repopulate Module 2.
            if hasattr(self, "floor_type_display"):
                self.restore_saved_weather_selection()
                self.restore_saved_environment_state()
        else:
            # Important: another Module may have saved to the same Project JSON.
            # Merge the latest disk state before Module 2 saves so regional data
            # and other Module outputs are not overwritten by a stale copy.
            latest = self.project_context.synchronize_from_disk()
            if latest is not None:
                self.project = latest
        return True

    def build(self):
        for w in self.winfo_children():
            w.destroy()
        page=create_scrollable_module_page(self)
        base_t = self.i18n.t
        strategy_ja = {
            "passive_strategy_conditions": "パッシブ性能・運転条件",
            "analysis_input_mode": "入力モード",
            "simple_mode_notice": "簡易版：主要4効果を共通条件で比較します。",
            "thermal_mass_peak_cut": "構造体蓄熱によるピークカット",
            "external_insulation_load_reduction": "外断熱による負荷低減",
            "night_heat_release_storage": "夜間放熱・夜間蓄熱",
            "natural_night_ventilation": "自然換気・夜間通風",
            "uninsulated_u_multiplier": "無断熱時U値倍率",
            "night_release_start": "夜間放熱開始",
            "night_release_end": "夜間放熱終了",
            "night_release_capacity": "夜間放熱能力",
            "night_ventilation_ach": "夜間換気回数",
            "night_ventilation_delta": "夜間通風開始温度差",
            "passive_strategy_non_additive_notice":
                "注：各効果は相互に影響するため、個別の削減量を単純合計しません。",
            "remark": "備考",
            "detail": "詳細",
            "heating_load": "年間暖房負荷",
            "cooling_load": "年間冷房負荷",
            "annual_heating_electricity": "年間暖房電力量",
            "annual_cooling_electricity": "年間冷房電力量",
            "hvac_electricity": "空調年間電力",
            "peak_heating_capacity": "最大暖房能力",
            "peak_cooling_capacity": "最大冷房能力",
            "peak_heating_duration": "暖房ピーク継続時間",
            "peak_cooling_duration": "冷房ピーク継続時間",
            "other_equipment_electricity": "照明・コンセント・換気・冷蔵庫等",
            "total_electricity": "建物年間電力",
            "primary_energy": "年間一次エネルギー",
            "operational_co2": "年間運用CO₂",
            "floor_area_intensity": "延床面積当たり年間電力",
            "heat_capacity": "有効熱容量",
            "pv_area_m2": "PV設置面積",
            "annual_generation_kWh": "年間PV発電量",
            "annual_self_consumption_kWh": "年間PV自家消費量",
            "annual_export_kWh": "年間売電量",
            "annual_grid_import_kWh": "年間購入電力量",
            "electricity_self_sufficiency_percent": "電力自給率",
            "annual_cost_saving_JPY": "年間電気料金削減額",
            "annual_export_revenue_JPY": "年間売電収入",
            "annual_total_economic_benefit_JPY": "年間PV経済効果",
            "annual_co2_reduction_kg": "年間PVによるCO₂削減量",
            "net_operational_CO2_kg_per_year": "PV反映後年間運用CO₂",
            "remark_heating_load": "設定温度を維持するために必要な年間暖房熱量です。",
            "remark_cooling_load": "設定温度を維持するために必要な年間冷房熱量です。",
            "remark_heating_electricity": "年間暖房負荷を暖房COP（{cop:.2f}）で除した電力量です。",
            "remark_cooling_electricity": "年間冷房負荷を冷房COP（{cop:.2f}）で除した電力量です。",
            "remark_hvac_electricity": "暖房電力量と冷房電力量の合計です。",
            "remark_peak_datetime": "最大値が発生した日時：{datetime}",
            "remark_peak_duration": "年間最大値の90％以上となった時間数です。",
            "remark_other_equipment": "1戸当たり定格容量×対象戸数×年間運転時間×負荷率÷効率で算定します。",
            "remark_total_electricity": "空調電力と照明・コンセント・換気・冷蔵庫等の合計です。",
            "remark_primary_energy": "建物年間電力に一次エネルギー係数を乗じた値です。",
            "remark_operational_co2": "年間購入電力量に電力CO₂係数を乗じた値です。",
            "remark_floor_area_intensity": "建物年間電力を延床面積で除した値です。",
            "remark_heat_capacity": "室温変動に寄与する構造体等の有効動的熱容量です。",
            "remark_pv_area": "屋根面積と屋根利用率から算定したPV設置面積です。",
            "remark_pv_generation": "EPWの日射量を用いて算定した年間PV発電量です。",
            "remark_pv_self": "PV発電量のうち建物内で同時に消費された電力量です。",
            "remark_pv_export": "PV発電量のうち系統へ売電した電力量です。",
            "remark_grid_import": "各時間の不足電力を合計した年間購入電力量です。",
            "remark_self_sufficiency": "建物使用電力のうちPV自家消費で賄った割合です。",
            "remark_cost_saving": "PV自家消費によって削減された年間購入電力料金です。",
            "remark_export_revenue": "年間売電量×売電単価です。",
            "remark_pv_benefit": "電気料金削減額と売電収入の合計です。",
            "remark_pv_co2": "PV自家消費量×電力CO₂係数による削減量です。",
            "remark_net_co2": "年間運用CO₂からPVによる削減量を反映した値です。",
        }
        strategy_en = {
            "passive_strategy_conditions": "Passive strategy and operating conditions",
            "analysis_input_mode": "Analysis input mode",
            "simple_mode_notice": "Simple mode: compares the four principal effects under common conditions.",
            "thermal_mass_peak_cut": "Peak reduction by structural thermal mass",
            "external_insulation_load_reduction": "Load reduction by external insulation",
            "night_heat_release_storage": "Night heat release / thermal storage",
            "natural_night_ventilation": "Natural ventilation / night purge",
            "uninsulated_u_multiplier": "Uninsulated U-value multiplier",
            "night_release_start": "Night heat-release start",
            "night_release_end": "Night heat-release end",
            "night_release_capacity": "Night heat-release capacity",
            "night_ventilation_ach": "Night ventilation air changes",
            "night_ventilation_delta": "Night ventilation start temperature difference",
            "passive_strategy_non_additive_notice":
                "Note: the effects interact with each other, so individual reductions are not simply added.",
            "remark": "Remarks",
            "detail": "Detail",
            "heating_load": "Annual Heating Load",
            "cooling_load": "Annual Cooling Load",
            "annual_heating_electricity": "Annual Heating Electricity",
            "annual_cooling_electricity": "Annual Cooling Electricity",
            "hvac_electricity": "Annual HVAC Electricity",
            "peak_heating_capacity": "Peak Heating Capacity",
            "peak_cooling_capacity": "Peak Cooling Capacity",
            "peak_heating_duration": "Peak Heating Duration",
            "peak_cooling_duration": "Peak Cooling Duration",
            "other_equipment_electricity": "Lighting, Plug Loads, Ventilation, Refrigerator, etc.",
            "total_electricity": "Annual Building Electricity",
            "primary_energy": "Annual Primary Energy",
            "operational_co2": "Annual Operational CO₂",
            "floor_area_intensity": "Annual Electricity per Gross Floor Area",
            "heat_capacity": "Effective Heat Capacity",
            "pv_area_m2": "PV Area",
            "annual_generation_kWh": "Annual PV Generation",
            "annual_self_consumption_kWh": "Annual PV Self-Consumption",
            "annual_export_kWh": "Annual Exported Electricity",
            "annual_grid_import_kWh": "Annual Grid Import",
            "electricity_self_sufficiency_percent": "Electricity Self-Sufficiency",
            "annual_cost_saving_JPY": "Annual Electricity Cost Saving",
            "annual_export_revenue_JPY": "Annual Export Revenue",
            "annual_total_economic_benefit_JPY": "Annual PV Economic Benefit",
            "annual_co2_reduction_kg": "Annual PV CO₂ Reduction",
            "net_operational_CO2_kg_per_year": "Annual Operational CO₂ after PV",
            "remark_heating_load": "Annual heating energy required to maintain the heating setpoint.",
            "remark_cooling_load": "Annual cooling energy required to maintain the cooling setpoint.",
            "remark_heating_electricity": "Electricity calculated by dividing annual heating load by heating COP ({cop:.2f}).",
            "remark_cooling_electricity": "Electricity calculated by dividing annual cooling load by cooling COP ({cop:.2f}).",
            "remark_hvac_electricity": "Sum of annual heating and cooling electricity.",
            "remark_peak_datetime": "Date and time of annual maximum: {datetime}",
            "remark_peak_duration": "Annual hours at or above 90% of the annual maximum.",
            "remark_other_equipment": "Calculated from rated capacity per dwelling × target dwellings × annual operating hours × load factor ÷ efficiency.",
            "remark_total_electricity": "Sum of HVAC electricity and lighting, plug loads, ventilation, refrigerator, etc.",
            "remark_primary_energy": "Annual building electricity multiplied by the primary-energy factor.",
            "remark_operational_co2": "Annual purchased electricity multiplied by the electricity CO₂ factor.",
            "remark_floor_area_intensity": "Annual building electricity divided by gross floor area.",
            "remark_heat_capacity": "Effective dynamic heat capacity of the structure and other elements contributing to indoor temperature stability.",
            "remark_pv_area": "PV installation area calculated from roof area and roof utilization rate.",
            "remark_pv_generation": "Annual PV generation calculated using EPW solar radiation.",
            "remark_pv_self": "PV electricity consumed simultaneously within the building.",
            "remark_pv_export": "PV electricity exported to the grid.",
            "remark_grid_import": "Annual purchased electricity obtained by summing hourly deficits.",
            "remark_self_sufficiency": "Share of building electricity demand supplied by PV self-consumption.",
            "remark_cost_saving": "Annual purchased-electricity cost avoided through PV self-consumption.",
            "remark_export_revenue": "Annual exported electricity × export tariff.",
            "remark_pv_benefit": "Sum of annual electricity-cost saving and export revenue.",
            "remark_pv_co2": "CO₂ reduction from PV self-consumption × electricity CO₂ factor.",
            "remark_net_co2": "Annual operational CO₂ after accounting for PV CO₂ reduction.",
            "detail_heating_load": "8760-hour heating-load calculation",
            "detail_cooling_load": "8760-hour cooling-load calculation",
            "detail_heating_electricity": "Heating load / COP",
            "detail_cooling_electricity": "Cooling load / COP",
            "detail_hvac_electricity": "Heating + cooling electricity",
            "detail_peak_heating": "Annual maximum heating load",
            "detail_peak_cooling": "Annual maximum cooling load",
            "detail_peak_duration": "Hours at or above 90% of peak",
            "detail_other_equipment": "Module 1 building data + equipment-use assumptions",
            "detail_total_electricity": "Annual electricity aggregation",
            "detail_primary_energy": "Electricity × primary-energy factor",
            "detail_operational_co2": "Grid electricity × electricity CO₂ factor",
            "detail_floor_area_intensity": "Annual electricity / gross floor area",
            "detail_heat_capacity": "Effective dynamic thermal mass",
            "detail_pv_area": "Roof area × PV utilization rate",
            "detail_pv_generation": "EPW solar radiation + PV settings",
            "detail_pv_self": "Hourly PV self-consumption",
            "detail_pv_export": "Hourly PV surplus",
            "detail_grid_import": "Hourly grid deficit",
            "detail_self_sufficiency": "PV self-consumption / annual demand",
            "detail_cost_saving": "PV self-consumption × purchased electricity price",
            "detail_export_revenue": "PV export × export tariff",
            "detail_pv_benefit": "Cost saving + export revenue",
            "detail_pv_co2": "PV self-consumption × electricity CO₂ factor",
            "detail_net_co2": "Operational CO₂ − PV CO₂ reduction",
        }

        def _is_japanese_language():
            lang_value = str(getattr(self.i18n, "language", "") or "").strip().lower()
            return lang_value in {"ja", "jp", "japanese", "日本語"} or lang_value.startswith("ja-") or lang_value.startswith("ja_")

        def t(key):
            # Module-local fallback prevents untranslated internal keys from
            # appearing when the global language dictionary has no entry.
            if _is_japanese_language() and key in strategy_ja:
                return strategy_ja[key]
            if (not _is_japanese_language()) and key in strategy_en:
                return strategy_en[key]
            translated = base_t(key)
            if translated == key or not str(translated).strip():
                return strategy_ja.get(key, key) if _is_japanese_language() else strategy_en.get(key, key)
            return translated

        self.ui_t = t

        top = ttk.Frame(page)
        top.pack(fill="x", padx=10, pady=6)
        add_module_text_copy_button(self,top)
        ttk.Label(top, text=t("language")).pack(side="left")
        lang = tk.StringVar(value="日本語" if self.i18n.language == "ja" else "English")
        cb = ttk.Combobox(top, textvariable=lang, values=LANGUAGE_OPTIONS,
                          state="readonly", width=12)
        cb.pack(side="left", padx=5)
        cb.bind("<<ComboboxSelected>>",
                lambda e: self.change_language("ja" if lang.get() == "日本語" else "en"))



        ttk.Button(
            top, text=t("print_this_module"), style="Primary.TButton",
            command=lambda: self.print_module_report()
        ).pack(side="right", padx=4)
        ttk.Button(
            top, text=t("save_module2"), command=self.save_output
        ).pack(side="right", padx=4)
        ttk.Button(
            top,
            text=("月別暖冷房確認" if _is_japanese_language() else "Monthly Heating/Cooling"),
            command=self.show_monthly_thermal,
        ).pack(side="right", padx=4)
        ttk.Button(
            top,
            text=("年間熱収支詳細" if _is_japanese_language() else "Annual Thermal Balance Details"),
            command=self.show_summer_heat_balance,
        ).pack(side="right", padx=4)
        ttk.Button(
            top,
            text=("断熱・蓄熱比較" if _is_japanese_language() else "Insulation / Thermal Mass"),
            command=self.show_envelope_mass_comparison,
        ).pack(side="right", padx=4)

        self.main_splitter = AZRASSplitter(page, key="module2.main", initial=575)
        self.main_splitter.pack(fill="both", expand=True, padx=6, pady=4)
        input_pane = ttk.Frame(self.main_splitter)
        result_pane = ttk.Frame(self.main_splitter)
        self.main_splitter.add_panes(input_pane, result_pane)

        files = ttk.LabelFrame(input_pane, text=t("project"))
        files.pack(fill="x", padx=10, pady=5)

        ttk.Label(files, text=t("project_json")).grid(
            row=0, column=0, padx=5, pady=4
        )
        tk.Entry(
            files, textvariable=self.project_file,  width=85
        ,state="readonly",readonlybackground=AUTO_BG).grid(row=0, column=1, columnspan=3, padx=5, pady=4, sticky="ew")

        ttk.Label(files, text=t("country")).grid(
            row=1, column=0, padx=5, pady=4
        )
        tk.Entry(
            files,
            textvariable=self.project_country,
            state="readonly",
            readonlybackground=AUTO_BG,
            width=30,
        ).grid(row=1, column=1, padx=5, pady=4, sticky="w")

        ttk.Label(files, text=t("country_weather_data")).grid(
            row=2, column=0, padx=5, pady=4
        )
        self.weather_box = ttk.Combobox(
            files,
            textvariable=self.weather_choice,
            state="readonly",
            width=72,
        )
        self.weather_box.grid(
            row=2, column=1, columnspan=2, padx=5, pady=4, sticky="ew"
        )
        self.weather_box.bind(
            "<<ComboboxSelected>>", self.weather_selected
        )
        ttk.Button(
            files,
            text=t("automatic_nearest_weather"),
            command=self.start_automatic_weather,
        ).grid(row=2, column=3, padx=5)
        ttk.Button(
            files,
            text=t("open_official_weather_site"),
            command=self.open_official_weather_site,
        ).grid(row=2, column=4, padx=5)

        ttk.Label(files, text=t("selected_weather_file")).grid(
            row=3, column=0, padx=5, pady=4
        )
        tk.Entry(
            files,
            textvariable=self.weather_file,
            state="readonly",
            readonlybackground=AUTO_BG,
            width=85,
        ).grid(
            row=3, column=1, columnspan=4, padx=5, pady=4, sticky="ew"
        )

        ttk.Label(files, text=t("weather_retrieval_status")).grid(
            row=4, column=0, padx=5, pady=4
        )
        ttk.Label(
            files,
            textvariable=self.weather_status,
            foreground="#005a9c",
            wraplength=1050,
        ).grid(row=4, column=1, columnspan=4, padx=5, pady=4, sticky="w")

        ttk.Button(
            files,
            text=t("register_weather_files"),
            command=self.register_weather_files,
        ).grid(row=5, column=3, padx=5, pady=4)
        ttk.Button(
            files,
            text=t("select_weather_file_directly"),
            command=self.choose_weather,
        ).grid(row=5, column=4, padx=5, pady=4)
        ttk.Label(
            files,
            text=t("manual_weather_fallback"),
            foreground="#555555",
        ).grid(row=5, column=0, columnspan=3, padx=5, pady=4, sticky="w")
        files.columnconfigure(1, weight=1)
        files.columnconfigure(2, weight=1)

        conditions = ttk.LabelFrame(input_pane, text=t("thermal_conditions"))
        conditions.pack(fill="x", padx=10, pady=5)
        fields = [
            ("heating_setpoint", "heating_setpoint"),
            ("cooling_setpoint", "cooling_setpoint"),
            ("heating_cop", "heating_cop"),
            ("cooling_cop", "cooling_cop"),
            ("ach", "ach"),
            ("heat_recovery", "heat_recovery"),
            ("window_shgc", "window_shgc"),
            ("solar_shading", "solar_shading"),
            ("electricity_co2", "electricity_co2"),
            ("primary_energy_factor", "primary_energy_factor"),
            ("ground_mean", "ground_mean"),
            ("ground_amplitude", "ground_amplitude"),
        ]
        for i, (key, label_key) in enumerate(fields):
            r = i // 4
            c = (i % 4) * 2
            ttk.Label(conditions, text=t(label_key)).grid(
                row=r, column=c, padx=4, pady=4, sticky="e")
            tk.Entry(conditions, textvariable=self.vars[key],
                     bg=INPUT_BG, width=13).grid(
                row=r, column=c+1, padx=4, pady=4)

        floor_box = ttk.LabelFrame(input_pane, text=("1階床・基礎・RC蓄熱詳細" if self.i18n.language == "ja" else "Ground floor, foundation and RC thermal mass"))
        floor_box.pack(fill="x", padx=10, pady=5)

        floor_values_ja = [
            "土のたたき",
            "土間コン",
            "ベタ基礎",
            "土のたたき＋床下空気層＋木造床",
            "土間コン＋床下空気層＋木造床",
            "ベタ基礎＋床下空気層＋木造床",
            "高床式",
            "その他床下詳細による",
        ]
        floor_values_en = [
            "Compacted earth floor",
            "Slab-on-ground concrete floor",
            "Mat foundation floor",
            "Compacted earth + underfloor air space + timber floor",
            "Slab-on-ground concrete + underfloor air space + timber floor",
            "Mat foundation + underfloor air space + timber floor",
            "Raised floor",
            "Other - see underfloor details",
        ]
        floor_keys = [
            "compacted_earth",
            "slab_on_ground",
            "mat_foundation",
            "compacted_earth_airspace_timber",
            "slab_on_ground_airspace_timber",
            "mat_foundation_airspace_timber",
            "raised_floor",
            "other_underfloor_detail",
        ]
        # Keep the display/key tables on the instance so saved Project JSON
        # can be restored outside build().
        self.floor_values_ja = floor_values_ja
        self.floor_values_en = floor_values_en
        self.floor_keys = floor_keys
        self.floor_type_display = tk.StringVar(value="")
        ttk.Label(floor_box, text=("1階床形式" if self.i18n.language == "ja" else "Ground-floor type")).grid(row=0,column=0,padx=4,pady=4,sticky="e")
        floor_combo = ttk.Combobox(floor_box, textvariable=self.floor_type_display, state="readonly", width=30, values=(floor_values_ja if self.i18n.language == "ja" else floor_values_en))
        floor_combo.grid(row=0,column=1,columnspan=3,padx=4,pady=4,sticky="w")
        def _floor_changed(_event=None):
            vals = floor_values_ja if self.i18n.language == "ja" else floor_values_en
            try:
                idx = vals.index(self.floor_type_display.get())
            except ValueError:
                self.floor_thermal_vars["ground_floor_type"].set("")
                return
            self.floor_thermal_vars["ground_floor_type"].set(floor_keys[idx])
        floor_combo.bind("<<ComboboxSelected>>", _floor_changed)

        ttk.Label(floor_box, text=("床下空気層高さ" if self.i18n.language == "ja" else "Underfloor air-space height")).grid(row=0,column=4,padx=4,pady=4,sticky="e")
        tk.Entry(floor_box,textvariable=self.floor_thermal_vars["air_gap_mm"],bg=INPUT_BG,width=9).grid(row=0,column=5,padx=4,pady=4)
        ttk.Label(floor_box,text="mm").grid(row=0,column=6,sticky="w")

        insulation_values_ja = ["外断熱", "内断熱", "充填断熱", "無断熱", "その他"]
        insulation_values_en = ["External insulation", "Internal insulation", "Cavity insulation", "No insulation", "Other"]
        insulation_keys = ["external", "internal", "cavity", "none", "other"]
        self.insulation_position_display = tk.StringVar(value="")
        ttk.Label(floor_box,text=("断熱位置" if self.i18n.language == "ja" else "Insulation position")).grid(row=1,column=0,padx=4,pady=4,sticky="e")
        insulation_combo = ttk.Combobox(floor_box,textvariable=self.insulation_position_display,state="readonly",width=20,values=(insulation_values_ja if self.i18n.language == "ja" else insulation_values_en))
        insulation_combo.grid(row=1,column=1,padx=4,pady=4,sticky="w")
        # PATCH_349: No-insulation is a true state, not merely a label.
        # Keep the last entered insulation values only in memory so they can be
        # restored if the user switches back to an insulated assembly.  They
        # must not remain visible or be serialized/calculated while "none" is
        # selected.
        self._floor_insulation_value_cache = {
            "slab_insulation_thickness_mm": str(self.floor_thermal_vars["slab_insulation_thickness_mm"].get() or "100"),
            "slab_insulation_conductivity_W_mK": str(self.floor_thermal_vars["slab_insulation_conductivity_W_mK"].get() or "0.028"),
        }

        def _on_foundation_bottom_toggle():
            # BUGFIX: the two insulation-position checkboxes were not mutually
            # exclusive, so both could be checked at once even though the
            # engine only applies one (slab_under_insulation silently took
            # priority), leaving the other checkbox visually checked but
            # physically ignored. Enforce single-selection so the checked box
            # always matches what is actually calculated.
            if self.floor_thermal_vars["foundation_bottom_insulation"].get():
                self.floor_thermal_vars["slab_under_insulation"].set(False)

        def _on_slab_under_toggle():
            if self.floor_thermal_vars["slab_under_insulation"].get():
                self.floor_thermal_vars["foundation_bottom_insulation"].set(False)

        foundation_bottom_cb = ttk.Checkbutton(
            floor_box,
            text=("ベタ基礎底断熱あり" if self.i18n.language == "ja" else "Mat-foundation bottom insulation"),
            variable=self.floor_thermal_vars["foundation_bottom_insulation"],
            command=_on_foundation_bottom_toggle,
        )
        foundation_bottom_cb.grid(row=1,column=2,columnspan=2,padx=5,pady=4,sticky="w")
        slab_under_cb = ttk.Checkbutton(
            floor_box,
            text=("土間下断熱あり" if self.i18n.language == "ja" else "Under-slab insulation"),
            variable=self.floor_thermal_vars["slab_under_insulation"],
            command=_on_slab_under_toggle,
        )
        slab_under_cb.grid(row=1,column=4,columnspan=2,padx=5,pady=4,sticky="w")

        self._floor_insulation_widgets = {
            "foundation_bottom_cb": foundation_bottom_cb,
            "slab_under_cb": slab_under_cb,
        }

        def _apply_floor_insulation_ui_state():
            no_insulation = str(self.floor_thermal_vars["insulation_position"].get() or "") == "none"
            widgets = getattr(self, "_floor_insulation_widgets", {})
            if no_insulation:
                # Preserve only non-empty prior inputs in RAM; clear the live
                # variables so the screen and saved Project JSON both express
                # an unambiguous no-insulation condition.
                for key in ("slab_insulation_thickness_mm", "slab_insulation_conductivity_W_mK"):
                    cur = str(self.floor_thermal_vars[key].get() or "").strip()
                    if cur:
                        self._floor_insulation_value_cache[key] = cur
                    self.floor_thermal_vars[key].set("")
                self.floor_thermal_vars["foundation_bottom_insulation"].set(False)
                self.floor_thermal_vars["slab_under_insulation"].set(False)
                for name in ("foundation_bottom_cb", "slab_under_cb", "thickness_entry", "conductivity_entry"):
                    w = widgets.get(name)
                    if w is not None:
                        try: w.configure(state="disabled")
                        except Exception: pass
            else:
                for name in ("foundation_bottom_cb", "slab_under_cb", "thickness_entry", "conductivity_entry"):
                    w = widgets.get(name)
                    if w is not None:
                        try: w.configure(state="normal")
                        except Exception: pass
                # Restore the user's last values only when leaving the explicit
                # no-insulation state.
                for key, fallback in (("slab_insulation_thickness_mm", "100"), ("slab_insulation_conductivity_W_mK", "0.028")):
                    if not str(self.floor_thermal_vars[key].get() or "").strip():
                        self.floor_thermal_vars[key].set(self._floor_insulation_value_cache.get(key, fallback))

        self._apply_floor_insulation_ui_state = _apply_floor_insulation_ui_state

        def _insulation_changed(_event=None):
            vals = insulation_values_ja if self.i18n.language == "ja" else insulation_values_en
            try: idx = vals.index(self.insulation_position_display.get())
            except ValueError:
                self.floor_thermal_vars["insulation_position"].set("")
                _apply_floor_insulation_ui_state()
                return
            self.floor_thermal_vars["insulation_position"].set(insulation_keys[idx])
            _apply_floor_insulation_ui_state()
        insulation_combo.bind("<<ComboboxSelected>>", _insulation_changed)

        labels = [
            # BUGFIX: this single thickness/conductivity pair is shared by both
            # the "ベタ基礎底断熱あり" and "土間下断熱あり" checkboxes above (see
            # environment_engine_v9_1.py), but the label used to always say
            # "土間下断熱厚" even when the user had checked foundation-bottom
            # insulation instead, which is what looked like the wrong position
            # being recorded. The label is now position-neutral.
            ("slab_insulation_thickness_mm", "断熱厚さ（上のチェックで選んだ位置に適用）" if self.i18n.language == "ja" else "Insulation thickness (applies to whichever position is checked above)", "mm"),
            ("slab_insulation_conductivity_W_mK", "断熱材熱伝導率" if self.i18n.language == "ja" else "Insulation conductivity", "W/mK"),
            ("exterior_rc_active_fraction", "外壁RC蓄熱利用率" if self.i18n.language == "ja" else "Exterior RC thermal-mass utilization", "0–1"),
            ("partition_rc_active_fraction", "隔壁RC蓄熱利用率" if self.i18n.language == "ja" else "Partition RC thermal-mass utilization", "0–1"),
            ("frame_rc_active_fraction", "柱・梁RC蓄熱利用率" if self.i18n.language == "ja" else "Column/beam RC thermal-mass utilization", "0–1"),
            ("slab_active_fraction_direct", "直床土間蓄熱利用率" if self.i18n.language == "ja" else "Direct slab thermal-mass utilization", "0–1"),
            ("slab_active_fraction_raised", "床下空間時土間蓄熱利用率" if self.i18n.language == "ja" else "Raised-floor slab thermal-mass utilization", "0–1"),
        ]
        for i,(key,label,unit) in enumerate(labels):
            r=2+i//3; c=(i%3)*3
            ttk.Label(floor_box,text=label).grid(row=r,column=c,padx=4,pady=3,sticky="e")
            entry = tk.Entry(floor_box,textvariable=self.floor_thermal_vars[key],bg=INPUT_BG,width=10)
            entry.grid(row=r,column=c+1,padx=4,pady=3)
            if key == "slab_insulation_thickness_mm":
                self._floor_insulation_widgets["thickness_entry"] = entry
            elif key == "slab_insulation_conductivity_W_mK":
                self._floor_insulation_widgets["conductivity_entry"] = entry
            ttk.Label(floor_box,text=unit).grid(row=r,column=c+2,padx=(0,6),pady=3,sticky="w")

        _apply_floor_insulation_ui_state()

        qty = ttk.LabelFrame(floor_box, text=("Module1から取得したRC数量・表面積（表示専用）" if self.i18n.language == "ja" else "RC quantities and surfaces from Module 1 (read only)"))
        qty.grid(row=5,column=0,columnspan=9,padx=4,pady=6,sticky="ew")
        quantity_rows = [
            ("exterior_volume_m3", "RC外壁コンクリート体積" if self.i18n.language == "ja" else "Exterior RC concrete volume", "m³"),
            ("partition_volume_m3", "RC隔壁コンクリート体積" if self.i18n.language == "ja" else "Partition RC concrete volume", "m³"),
            ("exterior_surface_m2", "RC外壁室内側表面積" if self.i18n.language == "ja" else "Exterior RC interior surface", "m²"),
            ("partition_surface_m2", "RC隔壁両面表面積" if self.i18n.language == "ja" else "Partition RC two-sided surface", "m²"),
        ]
        for i,(key,label,unit) in enumerate(quantity_rows):
            r=i//2; c=(i%2)*3
            ttk.Label(qty,text=label).grid(row=r,column=c,padx=4,pady=3,sticky="e")
            ttk.Entry(qty,textvariable=self.rc_quantity_display[key],state="readonly",width=14).grid(row=r,column=c+1,padx=4,pady=3)
            ttk.Label(qty,text=unit).grid(row=r,column=c+2,padx=(0,8),pady=3,sticky="w")
        ttk.Label(qty,textvariable=self.rc_quantity_display["classification_status"],foreground="#8b0000").grid(row=2,column=0,columnspan=6,padx=4,pady=3,sticky="w")

        r=6
        ttk.Label(floor_box,text=("その他床名称" if self.i18n.language == "ja" else "Other floor name")).grid(row=r,column=0,padx=4,pady=3,sticky="e")
        tk.Entry(floor_box,textvariable=self.floor_thermal_vars["other_floor_name"],bg=INPUT_BG,width=20).grid(row=r,column=1,padx=4,pady=3,sticky="w")
        ttk.Label(floor_box,text=("床構成説明" if self.i18n.language == "ja" else "Floor construction detail")).grid(row=r,column=2,padx=4,pady=3,sticky="e")
        tk.Entry(floor_box,textvariable=self.floor_thermal_vars["other_floor_detail"],bg=INPUT_BG,width=34).grid(row=r,column=3,columnspan=3,padx=4,pady=3,sticky="we")
        ttk.Label(floor_box,text=("その他土間コンクリート体積" if self.i18n.language == "ja" else "Other slab concrete volume")).grid(row=7,column=0,padx=4,pady=3,sticky="e")
        tk.Entry(floor_box,textvariable=self.floor_thermal_vars["other_slab_concrete_m3"],bg=INPUT_BG,width=10).grid(row=7,column=1,padx=4,pady=3)
        ttk.Label(floor_box,text="m³").grid(row=7,column=2,sticky="w")
        ttk.Label(floor_box,text=("その他床蓄熱利用率" if self.i18n.language == "ja" else "Other floor thermal-mass utilization")).grid(row=7,column=3,padx=4,pady=3,sticky="e")
        tk.Entry(floor_box,textvariable=self.floor_thermal_vars["other_effective_fraction"],bg=INPUT_BG,width=10).grid(row=7,column=4,padx=4,pady=3)
        ttk.Label(floor_box,text=("地盤U値" if self.i18n.language == "ja" else "Ground U-value")).grid(row=7,column=5,padx=4,pady=3,sticky="e")
        tk.Entry(floor_box,textvariable=self.floor_thermal_vars["other_ground_u_W_m2K"],bg=INPUT_BG,width=10).grid(row=7,column=6,padx=4,pady=3)

        strategies = ttk.LabelFrame(input_pane, text=t("passive_strategy_conditions"))
        strategies.pack(fill="x", padx=10, pady=5)
        ttk.Label(strategies, text=t("analysis_input_mode")).grid(row=0, column=0, padx=5, pady=4, sticky="e")
        mode_values = ["簡易", "詳細"] if self.i18n.language == "ja" else ["Simple", "Detailed"]
        current_mode_label = mode_values[1] if self.analysis_mode.get() == "detailed" else mode_values[0]
        self.analysis_mode_display.set(current_mode_label)
        mode_box = ttk.Combobox(
            strategies, textvariable=self.analysis_mode_display, state="readonly", width=14,
            values=mode_values,
        )
        mode_box.grid(row=0, column=1, padx=5, pady=4, sticky="w")
        def _change_mode(_event=None):
            selected = self.analysis_mode_display.get()
            self.analysis_mode.set(
                "detailed" if selected in {"詳細", "Detailed"} else "simple"
            )
            self.update_strategy_mode()
        mode_box.bind("<<ComboboxSelected>>", _change_mode)
        ttk.Label(strategies, text=t("simple_mode_notice"), foreground="#005a9c").grid(
            row=0, column=2, columnspan=6, padx=8, pady=4, sticky="w")

        strategy_rows = [
            ("thermal_mass_enabled", "thermal_mass_peak_cut"),
            ("external_insulation_enabled", "external_insulation_load_reduction"),
            ("night_heat_release_enabled", "night_heat_release_storage"),
            ("natural_night_ventilation_enabled", "natural_night_ventilation"),
        ]
        for idx, (key, label_key) in enumerate(strategy_rows):
            ttk.Checkbutton(
                strategies, text=t(label_key), variable=self.strategy_enabled[key]
            ).grid(row=1, column=idx * 2, columnspan=2, padx=6, pady=4, sticky="w")

        detail_fields = [
            ("external_insulation_reference_u_multiplier", "uninsulated_u_multiplier", "x"),
            ("night_release_start_hour", "night_release_start", "h"),
            ("night_release_end_hour", "night_release_end", "h"),
            ("night_release_conductance_W_K", "night_release_capacity", "W/K"),
            ("night_ventilation_ach", "night_ventilation_ach", "1/h"),
            ("night_ventilation_delta_C", "night_ventilation_delta", "°C"),
        ]
        self.strategy_detail_widgets = []
        for idx, (key, label_key, unit) in enumerate(detail_fields):
            row = 2 + idx // 3
            col = (idx % 3) * 3
            label = ttk.Label(strategies, text=t(label_key))
            entry = tk.Entry(strategies, textvariable=self.strategy_vars[key], bg=INPUT_BG, width=10)
            unit_label = ttk.Label(strategies, text=unit)
            label.grid(row=row, column=col, padx=4, pady=4, sticky="e")
            entry.grid(row=row, column=col+1, padx=4, pady=4)
            unit_label.grid(row=row, column=col+2, padx=(0, 8), pady=4, sticky="w")
            self.strategy_detail_widgets.extend([label, entry, unit_label])
        ttk.Label(
            strategies, text=t("passive_strategy_non_additive_notice"),
            foreground="#8b0000", wraplength=1320
        ).grid(row=4, column=0, columnspan=9, padx=5, pady=4, sticky="w")
        self.update_strategy_mode()

        pv = ttk.LabelFrame(input_pane, text=t("pv_conditions"))
        pv.pack(fill="x", padx=10, pady=5)

        ttk.Checkbutton(
            pv,
            text=t("pv_enabled"),
            variable=self.pv_enabled,
            command=self.update_pv_area_display,
        ).grid(row=0, column=0, columnspan=3, padx=5, pady=4, sticky="w")

        pv_fields = [
            ("roof_utilization_percent", "roof_utilization_percent", "%"),
            ("panel_efficiency_percent", "panel_efficiency_percent", "%"),
            ("pcs_efficiency_percent", "pcs_efficiency_percent", "%"),
            ("self_consumption_percent", "self_consumption_percent", "%"),
            ("purchase_price_local_currency_per_kWh", "purchase_price_JPY_per_kWh", f"{self._pv_currency()}/kWh"),
            ("export_price_local_currency_per_kWh", "export_price_JPY_per_kWh", f"{self._pv_currency()}/kWh"),
        ]
        for index, (key, label_key, unit) in enumerate(pv_fields):
            row = 1 + index // 3
            col = (index % 3) * 3
            ttk.Label(pv, text=t(label_key)).grid(
                row=row, column=col, padx=4, pady=4, sticky="e"
            )
            entry = tk.Entry(
                pv,
                textvariable=self.pv_vars[key],
                bg=INPUT_BG,
                width=12,
            )
            entry.grid(row=row, column=col + 1, padx=4, pady=4)
            entry.bind(
                "<FocusOut>",
                lambda _event: self.update_pv_area_display(),
            )
            ttk.Label(pv, text=unit).grid(
                row=row, column=col + 2, padx=(0, 8), pady=4, sticky="w"
            )

        ttk.Label(pv, text=t("roof_area_m2")).grid(
            row=3, column=0, padx=4, pady=4, sticky="e"
        )
        tk.Entry(
            pv,
            textvariable=self.pv_roof_area,
            state="readonly",
            readonlybackground=AUTO_BG,
            width=16,
        ).grid(row=3, column=1, padx=4, pady=4)
        ttk.Label(pv, text="m²").grid(row=3, column=2, sticky="w")

        ttk.Label(pv, text=t("pv_area_m2")).grid(
            row=3, column=3, padx=4, pady=4, sticky="e"
        )
        tk.Entry(
            pv,
            textvariable=self.pv_area,
            state="readonly",
            readonlybackground=AUTO_BG,
            width=16,
        ).grid(row=3, column=4, padx=4, pady=4)
        ttk.Label(pv, text="m²").grid(row=3, column=5, sticky="w")

        ttk.Label(
            pv,
            text=t("pv_model_notice"),
            foreground="#8b0000",
            wraplength=1320,
        ).grid(
            row=4, column=0, columnspan=9, padx=5, pady=4, sticky="w"
        )
        self.update_pv_area_display()

        ttk.Label(input_pane, text=t("model_notice"), foreground="#8b0000",
                  wraplength=1360).pack(fill="x", padx=12, pady=4)
        ttk.Button(input_pane, text=t("calculate_environment"),
                   command=self.calculate).pack(pady=7, ipady=5)

        result_box = ttk.LabelFrame(result_pane, text=t("environment_result"))
        result_box.pack(fill="both", expand=True, padx=6, pady=4)
        basis_heading = "算定根拠" if self.i18n.language == "ja" else "Calculation basis"
        source_heading = "参照元" if self.i18n.language == "ja" else "Source"
        self.tree = AZRASTable(
            result_box,
            columns=("no", "item", "value", "unit", "basis", "source"),
            headings={
                "no": "No.",
                "item": t("item"),
                "value": t("value"),
                "unit": t("unit"),
                "basis": basis_heading,
                "source": source_heading,
            },
            widths={
                "no": 58,
                "item": 330,
                "value": 155,
                "unit": 120,
                "basis": 520,
                "source": 260,
            },
            anchors={
                "no": "center",
                "item": "w",
                "value": "e",
                "unit": "center",
                "basis": "w",
                "source": "w",
            },
            settings_key="module2.environment_result",
            height=13,
        )
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)

        # Esc clears the current result-table selection.  Bind both to the
        # table and to this module window so it also works after keyboard
        # navigation inside the table.
        def _clear_result_selection(_event=None):
            try:
                selected = self.tree.selection()
                if selected:
                    self.tree.selection_remove(*selected)
                self.tree.focus("")
            except (AttributeError, tk.TclError):
                pass
            return "break"

        self.tree.bind("<Escape>", _clear_result_selection, add="+")
        self.bind("<Escape>", _clear_result_selection, add="+")


    def update_strategy_mode(self):
        detailed = self.analysis_mode.get() == "detailed"
        for widget in getattr(self, "strategy_detail_widgets", []):
            try:
                if isinstance(widget, tk.Entry):
                    widget.configure(state="normal" if detailed else "disabled")
                else:
                    widget.configure(foreground="" if detailed else "#777777")
            except tk.TclError:
                pass

    def strategy_settings(self):
        values = {key: bool(var.get()) for key, var in self.strategy_enabled.items()}
        values["analysis_mode"] = self.analysis_mode.get()
        for key, var in self.strategy_vars.items():
            try:
                values[key] = float(var.get().replace(",", ""))
            except (TypeError, ValueError):
                values[key] = 0.0
        return values

    def change_language(self, language):
        host = self.master
        coordinator = None
        while host is not None:
            coordinator = getattr(host, "request_global_language", None)
            if callable(coordinator):
                break
            host = getattr(host, "master", None)
        if callable(coordinator):
            coordinator(language, source=self)
            return
        self._apply_global_language(language)

    def _apply_global_language(self, language):
        self.i18n.set_language(language)
        self.title(self.i18n.t("module2"))
        self.build();attach_module_report_button(self,2)
        self.restore_saved_weather_selection()
        self.restore_saved_environment_state()

    def choose_project(self):
        path = filedialog.askopenfilename(
            initialdir=self.root_dir / "projects",
            filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            project = load_project(path)
            if not project.get("module_outputs", {}).get("module1"):
                raise ValueError(self.i18n.t("module1_required"))
            self.project = project
            self.project_path = Path(path)
            self._configure_project_weather_storage()
            self.project_file.set(path)
            country = normalize_country(
                project.get("common", {}).get("country", "")
            )
            self.project_country.set(country)
            self.refresh_weather_choices()
            self.apply_country_region_profile()
        except Exception as exc:
            messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language))

    def project_coordinates(self):
        common = (self.project or {}).get("common", {})
        location = common.get("location") or {}

        latitude = common.get("latitude")
        longitude = common.get("longitude")
        if latitude in (None, ""):
            latitude = location.get("latitude")
        if longitude in (None, ""):
            longitude = location.get("longitude")

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            return None

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return None
        return latitude, longitude


    def open_official_weather_site(self):
        webbrowser.open(ENERGYPLUS_WEATHER_PAGE)

    def start_automatic_weather_if_needed(self):
        if self.auto_weather_started:
            return
        coordinates = self.project_coordinates()
        if coordinates is None:
            self.weather_status.set(self.i18n.t("coordinates_not_found_in_project"))
            return

        # PATCH347: do not blindly trust a previously saved automatic EPW.
        # Older builds could retain a same-country but geographically remote
        # station (e.g. New York for a Williamsburg, Virginia project).
        # If the saved automatic station is clearly remote, re-run the
        # coordinate-based nearest-station resolver.  Manual/direct selections
        # remain user overrides and are never replaced here.
        common = (self.project or {}).get("common", {}) or {}
        source = common.get("weather_source") or {}
        method = str(source.get("selection_method") or "")
        existing = self.weather_file.get().strip()
        if existing and method == "nearest_to_project_coordinates":
            try:
                import math
                lat1, lon1 = map(math.radians, coordinates)
                lat2 = math.radians(float(source.get("station_latitude")))
                lon2 = math.radians(float(source.get("station_longitude")))
                dlat, dlon = lat2-lat1, lon2-lon1
                a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
                station_distance = 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(a)))
            except Exception:
                station_distance = None
            if station_distance is not None and station_distance > 150.0:
                self.weather_status.set(
                    ("保存EPWがプロジェクト座標から遠いため最寄り地点を再検索します。 "
                     if self.i18n.language == "ja" else
                     "Saved EPW is remote from the project; rechecking the nearest station. ")
                    + f"({station_distance:.1f} km)"
                )
                self.start_automatic_weather()
                return

        if existing:
            self.weather_status.set(self.i18n.t("existing_weather_file_in_use"))
            return
        self.start_automatic_weather()

    def start_automatic_weather(self):
        coordinates = self.project_coordinates()
        if coordinates is None:
            messagebox.showwarning(
                "Warning", self.i18n.t("coordinates_required_for_weather")
            )
            return
        if self.auto_weather_started:
            return
        self.auto_weather_started = True
        latitude, longitude = coordinates
        self.weather_status.set(
            self.i18n.t("weather_catalog_searching")
            + f" ({latitude:.8f}, {longitude:.8f})"
        )
        country = self.project_country.get().strip()
        data_root = self._configure_project_weather_storage()
        if data_root is None:
            messagebox.showwarning("Warning", self.i18n.t("coordinates_required_for_weather"))
            self.auto_weather_started = False
            return
        weather_root = weather_method_directory(data_root, self.project, create=False)

        def worker():
            try:
                result = retrieve_nearest_epw(
                    latitude, longitude, country, data_root,
                    weather_root=weather_root,
                    catalog_root=data_root / "Catalog",
                )
                self.after(
                    0,
                    lambda retrieved=result: self.finish_automatic_weather(
                        retrieved, None
                    ),
                )
            except Exception as exc:
                error_message = f"{type(exc).__name__}: {exc}"
                self.after(
                    0,
                    lambda message=error_message: self.finish_automatic_weather(
                        None, message
                    ),
                )

        threading.Thread(target=worker, daemon=True).start()

    def finish_automatic_weather(self, result, error):
        self.auto_weather_started = False
        if error is not None:
            self.weather_status.set(
                self.i18n.t("automatic_weather_failed") + "\n" + str(error)
            )
            messagebox.showwarning(
                "Warning",
                self.i18n.t("automatic_weather_failed") + "\n" + str(error),
                parent=self,
            )
            return

        local_path = result["local_path"]
        self.weather_file.set(local_path)
        self.weather_source_url.set(result.get("source_page", ""))
        distance = float(result.get("distance_km", 0.0))
        station = result.get("name", "")
        self.weather_status.set(
            self.i18n.t("automatic_weather_complete").format(
                station=station,
                distance=distance,
            )
        )

        try:
            entry = self.weather_catalog.register(
                local_path, self.project_country.get().strip()
            )
            self.refresh_weather_choices()
            self.weather_file.set(local_path)
            selected_label = ""
            for label, candidate in self.weather_choice_map.items():
                if Path(candidate.get("path", "")).resolve() == Path(entry.get("path", "")).resolve():
                    selected_label = label
                    break
            if selected_label:
                self.weather_choice.set(selected_label)
                self.weather_box.set(selected_label)
            else:
                fallback_label = f'{entry.get("name", "")} [{entry.get("format", "")}]'
                self.weather_choice_map[fallback_label] = entry
                values = list(self.weather_box["values"])
                if fallback_label not in values:
                    values.append(fallback_label)
                    self.weather_box["values"] = values
                self.weather_choice.set(fallback_label)
                self.weather_box.set(fallback_label)
        except Exception:
            pass

        if self.project is not None:
            common = self.project.setdefault("common", {})
            common["weather_source"] = {
                "provider": "EnergyPlus Weather Data",
                "station": station,
                "station_latitude": result.get("latitude"),
                "station_longitude": result.get("longitude"),
                "distance_km": distance,
                "epw_url": result.get("epw_url"),
                "catalog_url": result.get("catalog_url"),
                "source_page": result.get("source_page"),
                "local_path": local_path,
                "selection_method": "nearest_to_project_coordinates",
            }

    def populate_module1_rc_quantities(self):
        """Populate read-only RC quantities from Module 1 without user re-entry.

        Current Module 1 projects may contain only total RC-wall volume/area.
        When exterior/partition values are not separately available, the total
        is assigned once to the exterior field and the partition field is zero
        to prevent double counting.  The UI states this limitation explicitly.
        """
        if not isinstance(self.project, dict):
            return
        m1 = (self.project.get("module_outputs", {}).get("module1") or {})
        profile = m1.get("profile") or (m1.get("drawing_analysis") or {}).get("profile") or {}
        construction = profile.get("construction") or {}
        concrete = construction.get("concrete_volume_m3") or {}

        ext_v = construction.get("exterior_rc_volume_m3")
        part_v = construction.get("partition_rc_volume_m3")
        ext_a = construction.get("exterior_rc_interior_surface_m2")
        part_a = construction.get("partition_rc_two_sided_surface_m2")

        # PATCH_527: old Project JSONs can persist 0.0 in the profile even when
        # the final Module 1 takeoff already contains exterior/partition RC rows.
        # Re-run the same physical component bridge used by the 8760 engine so
        # the UI and solver show identical quantities.
        detected=_component_concrete_quantities(m1)
        det_ext=float(detected.get("exterior_rc_m3") or 0.0)
        det_part=float(detected.get("partition_rc_m3") or 0.0)
        if (ext_v in (None,0,0.0,"")) and det_ext>0:
            ext_v=det_ext
        if (part_v in (None,0,0.0,"")) and det_part>0:
            part_v=det_part

        separately_classified = (float(ext_v or 0.0)>0.0 or float(part_v or 0.0)>0.0)
        if not separately_classified:
            total_v = float(detected.get("generic_rc_wall_m3") or concrete.get("rc_walls", 0.0) or 0.0)
            total_a = construction.get("rc_wall_area_m2", 0.0) or 0.0
            ext_v, part_v = float(total_v), 0.0
            ext_a, part_a = float(total_a), 0.0
            status = (
                "※Module1では外壁・隔壁が未区分のため、RC壁総量を外壁側へ1回だけ計上しています。"
                if self.i18n.language == "ja" else
                "Module 1 does not yet separate exterior and partition RC; total RC wall quantity is counted once as exterior RC."
            )
        else:
            status = ("Module1最終数量の外壁・隔壁RC区分値を使用" if self.i18n.language == "ja" else "Using final Module 1 exterior/partition RC component quantities")

        self.floor_thermal_vars["exterior_rc_volume_m3"].set(str(float(ext_v or 0.0)))
        self.floor_thermal_vars["partition_rc_volume_m3"].set(str(float(part_v or 0.0)))
        self.rc_quantity_display["exterior_volume_m3"].set(f"{float(ext_v or 0.0):,.3f}")
        self.rc_quantity_display["partition_volume_m3"].set(f"{float(part_v or 0.0):,.3f}")
        self.rc_quantity_display["exterior_surface_m2"].set(f"{float(ext_a or 0.0):,.3f}")
        self.rc_quantity_display["partition_surface_m2"].set(f"{float(part_a or 0.0):,.3f}")
        self.rc_quantity_display["classification_status"].set(status)


    def _infer_ground_floor_from_module1(self):
        """Bridge a defensible ground-floor type from Module 1 into Module 2.

        This is deliberately conservative: it only selects a type when Module 1
        contains an explicit physical floor/foundation quantity or an explicit
        resolved slab assembly.  It never guesses insulation or an air-space
        floor from the construction method name alone.
        """
        if not isinstance(self.project, dict):
            return False
        if str(self.floor_thermal_vars["ground_floor_type"].get() or "").strip():
            return True

        m1 = (self.project.get("module_outputs", {}) or {}).get("module1") or {}
        qt = m1.get("quantity_takeoff") or {}
        rows = qt.get("rows") or []

        def _text(row):
            return " ".join(str(row.get(k) or "") for k in (
                "item", "item_ja", "item_en", "calculation_basis",
                "formula", "source", "evidence"
            )).lower()

        # Strongest evidence first.  These phrases describe the physical
        # ground-floor build-up, not merely a material specification.
        key = ""
        evidence = ""
        for row in rows:
            if not isinstance(row, dict):
                continue
            txt = _text(row)
            state = str(row.get("quantity_adoption_class") or row.get("evidence_status") or "").lower()
            # Ignore audit/spec-only records as physical-floor evidence.
            if state in {"audit", "audit_only", "spec", "spec_only"}:
                continue
            if any(x in txt for x in ("土間コンクリート", "土間concrete", "slab-on-ground concrete", "slab on ground concrete", "ground slab concrete")):
                key = "slab_on_ground"
                evidence = str(row.get("item") or row.get("item_ja") or row.get("item_en") or "Module 1 slab-on-ground quantity")
                break

        if not key:
            profile = m1.get("profile") or (m1.get("drawing_analysis") or {}).get("profile") or {}
            construction = profile.get("construction") or {}
            concrete = construction.get("concrete_volume_m3") or {}
            try:
                slab_v = float(concrete.get("slab_on_ground") or concrete.get("slab_foundation") or 0.0)
            except (TypeError, ValueError):
                slab_v = 0.0
            if slab_v > 0:
                key = "slab_on_ground"
                evidence = "Module 1 concrete-volume contract"

        if not key:
            return False

        self.floor_thermal_vars["ground_floor_type"].set(key)
        vals = self.floor_values_ja if self.i18n.language == "ja" else self.floor_values_en
        keys = self.floor_keys
        self.floor_type_display.set(vals[keys.index(key)] if key in keys else "")

        # Publish a traceable bridge contract into common.  This is not a user
        # override; Module 2 may still be changed manually before calculation.
        common = self.project.setdefault("common", {})
        common["module1_ground_floor_bridge"] = {
            "ground_floor_type": key,
            "source": "module1_drawing_quantity_analysis",
            "evidence": evidence,
            "inference_policy": "explicit_physical_floor_evidence_only",
        }
        return True

    def restore_saved_environment_state(self):
        if self.project is None:
            return
        saved = (
            self.project.get("module_outputs", {}).get("module2") or {}
        )
        if not isinstance(saved, dict) or not saved:
            # A new Module 2 run has no saved floor_thermal snapshot yet.
            # Apply regional defaults, then bridge the physical ground-floor
            # type from Module 1 instead of forcing duplicate user entry.
            self.apply_country_region_profile()
            self._infer_ground_floor_from_module1()
            self.populate_module1_rc_quantities()
            self.update_strategy_mode()
            self.update_pv_area_display()
            return

        snapshot = saved.get("_input_snapshot") or {}
        settings = snapshot.get("settings") or saved.get("settings") or {}
        for key, variable in self.vars.items():
            if key in settings:
                variable.set(str(settings[key]))
        if "analysis_mode" in settings:
            self.analysis_mode.set(str(settings.get("analysis_mode") or "simple"))
            self.analysis_mode_display.set(
                ("詳細" if self.analysis_mode.get() == "detailed" else "簡易")
                if self.i18n.language == "ja"
                else ("Detailed" if self.analysis_mode.get() == "detailed" else "Simple")
            )
        for key, variable in self.strategy_enabled.items():
            if key in settings:
                value = settings[key]
                if isinstance(value, str):
                    value = value.strip().lower() in {"1", "true", "yes", "on"}
                variable.set(bool(value))
        for key, variable in self.strategy_vars.items():
            if key in settings:
                variable.set(str(settings[key]))
        floor_saved = settings.get("floor_thermal") or saved.get("floor_thermal") or {}
        if isinstance(floor_saved, dict):
            for key, variable in self.floor_thermal_vars.items():
                if key in floor_saved:
                    value = floor_saved[key]
                    if isinstance(variable, tk.BooleanVar):
                        if isinstance(value, str): value = value.strip().lower() in {"1","true","yes","on"}
                        variable.set(bool(value))
                    else:
                        # Optional numeric/text fields saved as JSON null must
                        # return to the UI as a blank field, not the literal
                        # string "None".  The latter causes float("None")
                        # failures during Project JSON save.
                        variable.set("" if value is None else str(value))
            raw_key = str(floor_saved.get("ground_floor_type") or "")
            legacy_map = {
                "direct_concrete": "slab_on_ground",
                "raised_timber_300": "mat_foundation_airspace_timber",
                "crawlspace_timber_500": "compacted_earth_airspace_timber",
                "airspace_timber": "mat_foundation_airspace_timber",
                "mat_airspace_timber": "mat_foundation_airspace_timber",
                "auto": "",
            }
            key = legacy_map.get(raw_key, raw_key)
            self.floor_thermal_vars["ground_floor_type"].set(key)
            vals = self.floor_values_ja if self.i18n.language == "ja" else self.floor_values_en
            keys = self.floor_keys
            self.floor_type_display.set(vals[keys.index(key)] if key in keys else "")
            insulation_key = str(floor_saved.get("insulation_position") or "")
            insulation_keys = ["external", "internal", "cavity", "none", "other"]
            insulation_vals = (["外断熱", "内断熱", "充填断熱", "無断熱", "その他"] if self.i18n.language == "ja" else ["External insulation", "Internal insulation", "Cavity insulation", "No insulation", "Other"])
            self.insulation_position_display.set(insulation_vals[insulation_keys.index(insulation_key)] if insulation_key in insulation_keys else "")
            try:
                self._apply_floor_insulation_ui_state()
            except Exception:
                pass
        else:
            # No method-dependent defaults.  The user must explicitly choose
            # the floor system and insulation conditions for every method.
            self.floor_thermal_vars["ground_floor_type"].set("")
            self.floor_type_display.set("")
            self.floor_thermal_vars["air_gap_mm"].set("")
            self.floor_thermal_vars["insulation_position"].set("")
            self.insulation_position_display.set("")
            self.floor_thermal_vars["foundation_bottom_insulation"].set(False)
            self.floor_thermal_vars["slab_under_insulation"].set(False)
        # Older Module 2 snapshots may exist without ground_floor_type.
        # Recover it from the current Module 1 result only when still blank.
        self._infer_ground_floor_from_module1()
        try:
            self._apply_floor_insulation_ui_state()
        except Exception:
            pass
        self.populate_module1_rc_quantities()
        self.update_strategy_mode()

        saved_pv = (
            snapshot.get("pv")
            or settings.get("pv")
            or saved.get("pv")
            or self.project.get("common", {}).get("renewable_energy", {})
        )
        if isinstance(saved_pv, dict):
            if "pv_enabled" in saved_pv:
                self.pv_enabled.set(bool(saved_pv["pv_enabled"]))
            for key, variable in self.pv_vars.items():
                if key in saved_pv:
                    variable.set(str(saved_pv[key]))
            currency=self._pv_currency()
            if currency=="JPY":
                if "purchase_price_local_currency_per_kWh" not in saved_pv and "purchase_price_JPY_per_kWh" in saved_pv:
                    self.pv_vars["purchase_price_local_currency_per_kWh"].set(str(saved_pv["purchase_price_JPY_per_kWh"]))
                if "export_price_local_currency_per_kWh" not in saved_pv and "export_price_JPY_per_kWh" in saved_pv:
                    self.pv_vars["export_price_local_currency_per_kWh"].set(str(saved_pv["export_price_JPY_per_kWh"]))
            elif "purchase_price_local_currency_per_kWh" not in saved_pv:
                self.pv_vars["purchase_price_local_currency_per_kWh"].set("0")
                self.pv_vars["export_price_local_currency_per_kWh"].set("0")
        self.update_pv_area_display()

        weather_path = (
            snapshot.get("weather_file")
            or saved.get("weather_file")
            or self.project.get("common", {}).get("weather_source", {}).get("local_path")
            or ""
        )
        if weather_path:
            self.weather_file.set(str(weather_path))

        choice = snapshot.get("weather_choice")
        if choice:
            self.weather_choice.set(str(choice))
            try:
                self.weather_box.set(str(choice))
            except Exception:
                pass

        # The saved Module 2 object already contains the summary fields used
        # by the result table. Hourly rows are intentionally not embedded in
        # Project JSON because they are large.
        required = (
            "heating_load_kWh_per_year",
            "cooling_load_kWh_per_year",
            "total_building_electricity_kWh_per_year",
            "operational_CO2_kg_per_year",
        )
        # PATCH 375: stale Module 2 output may be retained for audit and its
        # input snapshot remains useful, but the old energy/CO2 summary must
        # not reappear as a current result after Project JSON reload.
        if module_output_is_current(self.project, "module2") and all(key in saved for key in required):
            self.summary = _m2_canonicalize_generated(saved)
            if isinstance(self.summary, dict):
                self.summary.setdefault("canonical_metadata", {}).update({
                    "canonical_language": "en",
                    "canonical_schema_version": "2.6",
                    "module": "module2",
                    "result_standard": "English Canonical",
                    "ui_language_independent": True,
                })
            try:
                self.show_result()
            except Exception:
                pass

        if weather_path:
            self.weather_status.set(self.i18n.t("saved_environment_result_restored"))
        else:
            self.apply_country_region_profile()

    def restore_saved_weather_selection(self):
        saved_path = ""
        if self.project is not None:
            module2 = (
                self.project.get("module_outputs", {}).get("module2") or {}
            )
            snapshot = module2.get("_input_snapshot") or {}
            saved_path = str(
                snapshot.get("weather_file")
                or self.project.get("common", {}).get("weather_source", {}).get("local_path")
                or ""
            )

        if saved_path and Path(saved_path).exists():
            try:
                self.weather_catalog.register(
                    saved_path, self.project_country.get().strip()
                )
            except Exception:
                pass

        self.refresh_weather_choices()

        if saved_path and Path(saved_path).exists():
            self.weather_file.set(saved_path)
            for label, candidate in self.weather_choice_map.items():
                try:
                    same = (
                        Path(candidate.get("path", "")).resolve()
                        == Path(saved_path).resolve()
                    )
                except Exception:
                    same = candidate.get("path", "") == saved_path
                if same:
                    self.weather_choice.set(label)
                    self.weather_box.set(label)
                    break

    def refresh_weather_choices(self):
        country = self.project_country.get().strip()
        self.weather_catalog.load()
        entries = self.weather_catalog.available(country)
        self.weather_choice_map = {}
        labels = []
        for entry in entries:
            city = entry.get("city", "")
            country_name = normalize_country(entry.get("country", ""))
            display_name = entry.get("name", "") or city or Path(entry.get("path", "")).stem
            label = f'{display_name} / {country_name} [{entry.get("format", "")}]'
            base = label
            number = 2
            while label in self.weather_choice_map:
                label = f"{base} ({number})"
                number += 1
            labels.append(label)
            self.weather_choice_map[label] = entry

        self.weather_box["values"] = labels
        if labels:
            current = self.weather_choice.get()
            selected = current if current in labels else labels[0]
            self.weather_choice.set(selected)
            self.weather_selected()
        else:
            self.weather_choice.set("")
            self.weather_file.set("")

    def weather_selected(self, _event=None):
        entry = self.weather_choice_map.get(self.weather_choice.get())
        if entry:
            self.weather_file.set(entry.get("path", ""))

    def register_weather_files(self):
        country = self.project_country.get().strip()
        if not country:
            messagebox.showwarning(
                "Warning", self.i18n.t("select_project_country_first")
            )
            return

        paths = filedialog.askopenfilenames(
            title=self.i18n.t("register_weather_files"),
            filetypes=[
                ("Weather", "*.epw *.csv"),
                ("EPW", "*.epw"),
                ("CSV", "*.csv"),
            ],
        )
        if not paths:
            return

        mismatches = []
        for path in paths:
            entry = self.weather_catalog.register(path, country)
            if normalize_country(entry.get("country", "")) != normalize_country(country):
                mismatches.append(
                    f'{Path(path).name}: {entry.get("country", "")}'
                )

        self.refresh_weather_choices()
        if mismatches:
            messagebox.showwarning(
                "Warning",
                self.i18n.t("weather_country_mismatch") + "\n" + "\n".join(mismatches),
            )
        else:
            messagebox.showinfo(
                "OK", self.i18n.t("weather_files_registered")
            )

    def choose_weather(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("Weather", "*.epw *.csv"),
                ("EPW", "*.epw"),
                ("CSV", "*.csv"),
            ]
        )
        if not path:
            return

        country = self.project_country.get().strip()
        if country:
            entry = self.weather_catalog.register(path, country)
            self.refresh_weather_choices()
            for label, candidate in self.weather_choice_map.items():
                if candidate.get("path") == entry.get("path"):
                    self.weather_choice.set(label)
                    break
        self.weather_file.set(path)

    def apply_country_region_profile(self):
        # PATCH348: Regional Environmental Profile selection was removed.
        # Location/weather is governed by Module 0 coordinates + nearest EPW.
        # Non-weather regional coefficients remain explicit editable inputs and
        # are never silently overwritten by Tokyo/Nagoya/Sapporo templates.
        return

    def apply_region_profile(self):
        profile = self.region_db["profiles"].get(self.region_profile.get(), {})
        mapping = {
            "electricity_co2_kg_per_kWh": "electricity_co2",
            "primary_energy_factor_MJ_per_kWh": "primary_energy_factor",
            "ground_annual_mean_C": "ground_mean",
            "ground_amplitude_C": "ground_amplitude",
            "ground_phase_day": "ground_phase_day",
        }
        for source_key, var_key in mapping.items():
            if source_key in profile:
                self.vars[var_key].set(str(profile[source_key]))

    def roof_area_from_project(self):
        """Return the best available positive roof area from the project.

        Older project JSON files often keep the recognized area under Module 1
        geometry/footprint instead of common.roof_area_m2.  A stored zero is
        treated as missing, not as an authoritative area.
        """
        project = self.project or {}
        common = project.get("common", {}) or {}
        building = common.get("building") or {}
        m1 = (project.get("module_outputs", {}) or {}).get("module1") or {}

        candidates = [
            common.get("roof_area_m2"),
            building.get("roof_area_m2"),
            (m1.get("building_scale") or {}).get("roof_area_m2"),
            (m1.get("building_scale") or {}).get("footprint_m2"),
            ((m1.get("profile") or {}).get("geometry") or {}).get("roof_area_m2"),
            ((m1.get("profile") or {}).get("geometry") or {}).get("footprint_m2"),
            (((m1.get("drawing_analysis") or {}).get("profile") or {}).get("geometry") or {}).get("roof_area_m2"),
            (((m1.get("drawing_analysis") or {}).get("profile") or {}).get("geometry") or {}).get("footprint_m2"),
        ]

        # For a normal multi-storey building, the first-floor area is a better
        # roof-plan fallback than gross floor area.
        floor_areas = common.get("floor_areas_m2") or building.get("floor_areas_m2") or []
        if floor_areas:
            candidates.append(floor_areas[0])
        storeys = common.get("storeys") or building.get("storeys") or 0
        gfa = common.get("scale_gfa_m2") or building.get("gross_floor_area_m2") or 0
        try:
            if float(storeys) > 0 and float(gfa) > 0:
                candidates.append(float(gfa) / float(storeys))
        except (TypeError, ValueError, ZeroDivisionError):
            pass

        for value in candidates:
            try:
                area = float(str(value).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if area > 0:
                # Synchronize the stable common interface so subsequent saves
                # and regional JSON generation retain the recovered area.
                common["roof_area_m2"] = area
                building["roof_area_m2"] = area
                common["building"] = building
                project["common"] = common
                return area
        return 0.0

    def _pv_currency(self):
        return _resolve_project_currency(self.project or {}, self.root_dir)

    def pv_settings(self):
        values = {}
        for key, variable in self.pv_vars.items():
            values[key] = float(variable.get().replace(",", ""))
        values["pv_enabled"] = bool(self.pv_enabled.get())
        currency=self._pv_currency()
        values["currency"]=currency
        values["tariff_status"]="user_input_local_currency" if currency!="UNSET" else "currency_unresolved"
        if currency=="JPY":
            values["purchase_price_JPY_per_kWh"]=values.get("purchase_price_local_currency_per_kWh",0.0)
            values["export_price_JPY_per_kWh"]=values.get("export_price_local_currency_per_kWh",0.0)
        return values

    def update_pv_area_display(self):
        roof = self.roof_area_from_project()
        try:
            utilization = float(
                self.pv_vars["roof_utilization_percent"].get().replace(",", "")
            )
        except (TypeError, ValueError):
            utilization = 80.0
        area = roof * max(0.0, min(100.0, utilization)) / 100.0
        if not self.pv_enabled.get():
            area = 0.0
        self.pv_roof_area.set(f"{roof:,.2f}")
        self.pv_area.set(f"{area:,.2f}")

    def settings(self):
        settings = {
            key: float(var.get().replace(",", ""))
            for key, var in self.vars.items()
        }
        settings["pv"] = self.pv_settings()
        settings.update(self.strategy_settings())
        floor_settings = {}
        for key, var in self.floor_thermal_vars.items():
            value = var.get()
            if isinstance(var, tk.BooleanVar):
                floor_settings[key] = bool(value)
            elif key in {"ground_floor_type", "insulation_position", "other_floor_name", "other_floor_detail"}:
                floor_settings[key] = str(value)
            else:
                text = str(value).strip().replace(",", "")
                # Treat common representations of an unspecified optional
                # value as JSON null.  This also safely opens projects saved
                # by the earlier build that displayed None in the entry box.
                if text.lower() in {"", "none", "null", "nan", "-"}:
                    floor_settings[key] = None
                else:
                    floor_settings[key] = float(text)
        if not floor_settings.get("ground_floor_type"):
            # Last-chance bridge for callers that reach settings() without the
            # normal restore lifecycle (for example older project contexts).
            if self._infer_ground_floor_from_module1():
                floor_settings["ground_floor_type"] = str(self.floor_thermal_vars["ground_floor_type"].get() or "")
            if not floor_settings.get("ground_floor_type"):
                raise ValueError("1階床形式を選択してください。" if self.i18n.language == "ja" else "Select the ground-floor type.")
        if str(floor_settings.get("ground_floor_type") or "").endswith("_airspace_timber") and not floor_settings.get("air_gap_mm"):
            raise ValueError("床下空気層高さ(mm)を入力してください。" if self.i18n.language == "ja" else "Enter the underfloor air-space height (mm).")
        # PATCH_349: Explicit no-insulation must serialize as no insulation.
        # Never leak stale defaults such as 100 mm / 0.028 W/mK downstream.
        if str(floor_settings.get("insulation_position") or "") == "none":
            floor_settings["foundation_bottom_insulation"] = False
            floor_settings["slab_under_insulation"] = False
            floor_settings["slab_insulation_thickness_mm"] = None
            floor_settings["slab_insulation_conductivity_W_mK"] = None
        floor_settings["schema_version"] = "2.0"
        floor_settings["rc_quantity_bridge_mode"] = "auto_module1_final_components"
        settings["floor_thermal"] = floor_settings
        settings["floor_thermal_schema_version"] = "2.0"
        settings["canonical_metadata"] = {
            "canonical_language": "en",
            "canonical_schema_version": "2.6",
            "ground_floor_type_storage": "stable English ID",
            "insulation_position_storage": "stable English ID",
            "ui_language_independent": True,
        }

        # PATCH_171: carry Module 1's effective thermal capacity into the
        # 8760-hour engine.  AI-first projects can have little/no RC quantity,
        # so deriving capacity only from RC volumes collapses to ~0.20 MJ/K and
        # destabilizes the explicit dynamic solver.
        try:
            m1 = (self.project.get("module_outputs", {}) or {}).get("module1") or {}
            perf = m1.get("building_performance") or {}
            tm = perf.get("thermal_mass") or {}
            cap = float(tm.get("effective_heat_capacity_MJ_K") or 0.0)
            if cap > 0.0:
                settings["module1_effective_heat_capacity_MJ_K"] = cap
                settings["module1_effective_heat_capacity_status"] = str(tm.get("status") or "")
        except Exception:
            pass
        return settings

    def calculate(self):
        # PATCH_509: Module 1 may have been recalculated/saved while Module 2
        # remained open.  Reload/synchronize the active Project JSON before
        # checking the Module 1 prerequisite, otherwise a stale in-memory copy
        # can incorrectly report that Drawing Analysis / Quantity Calculation
        # has not been saved.
        self.refresh_project_from_context()
        if self.project is None:
            messagebox.showwarning("Warning", self.i18n.t("module1_required"))
            return
        if not self.weather_file.get():
            messagebox.showwarning("Warning", self.i18n.t("weather_required"))
            return
        # PATCH_507: 8760 analysis is downstream of the current Module 1 drawing/quantity result.
        # Never silently calculate from a missing/stale planning baseline.
        try:
            require_current_module_output(self.project, "module1", "Module 1")
        except Exception:
            messagebox.showwarning(
                "Warning",
                ("8760時間解析の前に、先に『図面解析・数量計算』を実行し、最新の数量結果をProject JSONへ反映してください。"
                 if self.i18n.language=="ja" else
                 "Before the 8,760-hour analysis, run Drawing Analysis / Quantity Calculation first and save the current quantity result to the Project JSON."),
                parent=self)
            return
        # PATCH_612: unresolved true north must never become an implicit 0°.
        _common=self.project.get("common") if isinstance(self.project.get("common"),dict) else {}
        _north=_common.get("north_rotation_deg")
        if _north in (None,""):
            messagebox.showwarning(
                "True North Required",
                ("真北回転角（°）が未確定です。Module 1の結果は保存できますが、"
                 "方位別8760時間解析は実行できません。図面から真北を確認して入力してください。"
                 if self.i18n.language=="ja" else
                 "True North Rotation (°) is unresolved. Module 1 may be saved, "
                 "but directional 8,760-hour analysis cannot run until true north is confirmed."),
                parent=self,
            )
            return
        try:
            float(_north)
        except (TypeError,ValueError):
            messagebox.showwarning(
                "True North Required",
                ("真北回転角（°）が数値ではありません。確認して再入力してください。"
                 if self.i18n.language=="ja" else
                 "True North Rotation (°) is not numeric. Verify and re-enter it."),
                parent=self,
            )
            return
        try:
            self.hourly, self.summary = run_environment(
                self.project, self.weather_file.get(), self.settings())
            self.summary = _m2_canonicalize_generated(self.summary)
            if isinstance(self.summary, dict):
                self.summary.setdefault("canonical_metadata", {}).update({
                    "canonical_language": "en",
                    "canonical_schema_version": "2.6",
                    "module": "module2",
                    "result_standard": "English Canonical",
                    "ui_language_independent": True,
                })
            renewable = self.project.setdefault("common", {}).setdefault(
                "renewable_energy", {}
            )
            renewable.update(self.summary.get("pv", {}))
            self.show_result()
            messagebox.showinfo("OK", self.i18n.t("environment_complete"))
        except Exception as exc:
            messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language))

    def show_result(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        t = getattr(self, "ui_t", self.i18n.t)
        s = self.summary

        def dt_text(raw):
            # PATCH_549: datetime text is presentation-localized.  Rows 06/07
            # previously emitted Japanese 月/日 notation even in the English UI.
            if not raw:
                return "-"
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if self.i18n.language == "ja":
                    return f"{dt.month}月{dt.day}日 {dt.hour:02d}:{dt.minute:02d}"
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                return str(raw)

        heat_dt = dt_text(s.get("peak_heating_datetime"))
        cool_dt = dt_text(s.get("peak_cooling_datetime"))
        heat_cop = float((s.get("settings") or {}).get("heating_cop", 0.0) or 0.0)
        cool_cop = float((s.get("settings") or {}).get("cooling_cop", 0.0) or 0.0)

        # Result-table sources are explicit so a reviewer can trace each value
        # back to the input or calculation stage that produced it.
        src_weather = "Module 2：8760時間気象・熱負荷計算" if self.i18n.language == "ja" else "Module 2: 8760-hour weather / load calculation"
        src_hvac = "Module 2：熱負荷＋COP設定" if self.i18n.language == "ja" else "Module 2: thermal load + COP settings"
        src_equipment = "Module 1建物条件＋Module 2設備条件" if self.i18n.language == "ja" else "Module 1 building data + Module 2 equipment settings"
        src_energy = "Module 2：年間エネルギー集計" if self.i18n.language == "ja" else "Module 2: annual energy aggregation"
        src_co2 = "Module 2：電力CO₂係数＋年間電力量" if self.i18n.language == "ja" else "Module 2: electricity CO2 factor + annual electricity"
        src_project = "Project JSON／Module 1" if self.i18n.language == "ja" else "Project JSON / Module 1"
        src_pv = "Module 2：PV設定・気象データ" if self.i18n.language == "ja" else "Module 2: PV settings + weather data"
        src_passive = "Module 2：パッシブ性能設定・8760時間計算" if self.i18n.language == "ja" else "Module 2: passive-strategy settings + 8760-hour calculation"

        # PATCH_400: expose the exact facade/orientation inputs actually consumed by
        # the 8760-hour solver so the diagnostic screen and calculation result can
        # be cross-checked without reading Project JSON by hand.
        _ftb400 = s.get("floor_thermal_breakdown") or {}
        _orient400 = _ftb400.get("orientation_window_reconciliation") or {}
        _surface_count400 = float(_orient400.get("surface_count") or 0.0)
        _directional_area400 = float(_orient400.get("directional_window_area_m2") or _orient400.get("authoritative_window_area_m2") or 0.0)
        _north400_raw = _orient400.get("north_rotation_deg")
        _north400 = float(_north400_raw) if _north400_raw not in (None,"") else None

        rows = [
            (t("heating_load"), s.get("heating_load_kWh_per_year", 0.0), "kWh/year",
             t("remark_heating_load"), src_weather, t("detail_heating_load")),
            (t("cooling_load"), s.get("cooling_load_kWh_per_year", 0.0), "kWh/year",
             t("remark_cooling_load"), src_weather, t("detail_cooling_load")),
            (t("annual_heating_electricity"), s.get("heating_electricity_kWh_per_year", 0.0), "kWh/year",
             t("remark_heating_electricity").format(cop=heat_cop), src_hvac, t("detail_heating_electricity")),
            (t("annual_cooling_electricity"), s.get("cooling_electricity_kWh_per_year", 0.0), "kWh/year",
             t("remark_cooling_electricity").format(cop=cool_cop), src_hvac, t("detail_cooling_electricity")),
            (t("hvac_electricity"), s.get("hvac_electricity_kWh_per_year", 0.0), "kWh/year",
             t("remark_hvac_electricity"), src_hvac, t("detail_hvac_electricity")),
            (t("peak_heating_capacity"), s.get("peak_heating_kW", 0.0), "kW",
             t("remark_peak_datetime").format(datetime=heat_dt), src_weather, t("detail_peak_heating")),
            (t("peak_cooling_capacity"), s.get("peak_cooling_kW", 0.0), "kW",
             t("remark_peak_datetime").format(datetime=cool_dt), src_weather, t("detail_peak_cooling")),
            (t("peak_heating_duration"), s.get("peak_heating_duration_hours_90pct", 0.0), "hours/year",
             t("remark_peak_duration"), src_weather, t("detail_peak_duration")),
            (t("peak_cooling_duration"), s.get("peak_cooling_duration_hours_90pct", 0.0), "hours/year",
             t("remark_peak_duration"), src_weather, t("detail_peak_duration")),
            (t("other_equipment_electricity"), s.get("other_equipment_electricity_kWh_per_year", 0.0), "kWh/year",
             t("remark_other_equipment"), src_equipment, t("detail_other_equipment")),
            (t("total_electricity"), s.get("total_building_electricity_kWh_per_year", 0.0), "kWh/year",
             t("remark_total_electricity"), src_energy, t("detail_total_electricity")),
            (t("primary_energy"), s.get("primary_energy_MJ_per_year", 0.0), "MJ/year",
             t("remark_primary_energy"), src_energy, t("detail_primary_energy")),
            (t("operational_co2"), s.get("operational_CO2_kg_per_year", 0.0), "kg-CO₂/year",
             t("remark_operational_co2"), src_co2, t("detail_operational_co2")),
            (t("floor_area_intensity"), s.get("electricity_intensity_kWh_m2_year", 0.0), "kWh/m²·year",
             t("remark_floor_area_intensity"), src_project, t("detail_floor_area_intensity")),
            (t("heat_capacity"), s.get("effective_dynamic_heat_capacity_MJ_per_K", 0.0), "MJ/K",
             t("remark_heat_capacity"), src_project, t("detail_heat_capacity")),
            (t("pv_area_m2"), s.get("pv_area_m2", 0.0), "m²", t("remark_pv_area"), src_pv, t("detail_pv_area")),
            (t("annual_generation_kWh"), s.get("annual_pv_generation_kWh", 0.0), "kWh/year", t("remark_pv_generation"), src_pv, t("detail_pv_generation")),
            (t("annual_self_consumption_kWh"), s.get("annual_pv_self_consumption_kWh", 0.0), "kWh/year", t("remark_pv_self"), src_pv, t("detail_pv_self")),
            (t("annual_export_kWh"), s.get("annual_pv_export_kWh", 0.0), "kWh/year", t("remark_pv_export"), src_pv, t("detail_pv_export")),
            (t("annual_grid_import_kWh"), s.get("annual_grid_import_kWh", 0.0), "kWh/year", t("remark_grid_import"), src_pv, t("detail_grid_import")),
            (t("electricity_self_sufficiency_percent"), s.get("electricity_self_sufficiency_percent", 0.0), "%", t("remark_self_sufficiency"), src_pv, t("detail_self_sufficiency")),
            (t("annual_cost_saving_JPY"), s.get("annual_electricity_cost_saving_local_currency", 0.0), f"{self._pv_currency()}/year", t("remark_cost_saving"), src_pv, t("detail_cost_saving")),
            (t("annual_export_revenue_JPY"), s.get("annual_export_revenue_local_currency", 0.0), f"{self._pv_currency()}/year", t("remark_export_revenue"), src_pv, t("detail_export_revenue")),
            (t("annual_total_economic_benefit_JPY"), s.get("annual_pv_economic_benefit_local_currency", 0.0), f"{self._pv_currency()}/year", t("remark_pv_benefit"), src_pv, t("detail_pv_benefit")),
            (t("annual_co2_reduction_kg"), s.get("annual_pv_co2_reduction_kg", 0.0), "kg-CO₂/year", t("remark_pv_co2"), src_pv, t("detail_pv_co2")),
            (t("net_operational_CO2_kg_per_year"), s.get("net_operational_CO2_kg_per_year", 0.0), "kg-CO₂/year", t("remark_net_co2"), src_co2, t("detail_net_co2")),
            (("8760方位日射 使用面数" if self.i18n.language == "ja" else "8760 directional-solar surfaces used"), _surface_count400, "faces",
             ("Module 1図面由来面を8760時間日射計算へ直接使用" if self.i18n.language == "ja" else "Module 1 drawing-derived facades used directly by the 8760-hour solar calculation"), src_project,
             ("0なら方位別日射は無効、4なら今回の4外壁面を使用。" if self.i18n.language == "ja" else "0 means directional solar is inactive; 4 means the four current facades are active.")),
            (("8760方位日射 窓面積" if self.i18n.language == "ja" else "8760 directional-solar window area"), _directional_area400, "m²",
             ("方位別日射計算が実際に使用した窓面積" if self.i18n.language == "ja" else "Window area actually used by the directional solar calculation"), src_project,
             ("Module 1総窓面積と一致することを確認します。" if self.i18n.language == "ja" else "Verify this equals the Module 1 total window area.")),
            (("8760方位日射 真北回転角" if self.i18n.language == "ja" else "8760 directional-solar north rotation"), _north400, "deg",
             ("Project真北＋図面ローカル方位で真方位を算定" if self.i18n.language == "ja" else "True azimuth = Project north + drawing-local azimuth"), src_project,
             ("今回のProject真北回転角を8760時間計算でも同じ値で使用します。" if self.i18n.language == "ja" else "The 8760-hour calculation uses the same Project north rotation.")),
        ]

        effects = s.get("passive_technology_effects") or {}
        labels = [
            ("thermal_mass", "structural_thermal_mass_effect", "detail_structural_thermal_mass"),
            ("external_insulation", "envelope_insulation_effect", "detail_envelope_insulation"),
            ("night_heat_release", "night_heat_release_effect", "detail_night_heat_release"),
            ("natural_night_ventilation", "night_ventilation_effect", "detail_night_ventilation"),
        ]
        for key, label_key, detail_key in labels:
            effect = effects.get(key) or {}
            if not effect.get("enabled"):
                continue
            base_label = t(label_key)
            annual = float(effect.get("annual_hvac_saving_kWh", 0.0) or 0.0)
            annual_pct = float(effect.get("annual_hvac_saving_percent", 0.0) or 0.0)
            cool_kw = float(effect.get("peak_cooling_reduction_kW", 0.0) or 0.0)
            cool_pct = float(effect.get("peak_cooling_reduction_percent", 0.0) or 0.0)
            heat_kw = float(effect.get("peak_heating_reduction_kW", 0.0) or 0.0)
            heat_pct = float(effect.get("peak_heating_reduction_percent", 0.0) or 0.0)
            cool_hours = float(effect.get("peak_cooling_duration_reduction_hours", 0.0) or 0.0)
            heat_hours = float(effect.get("peak_heating_duration_reduction_hours", 0.0) or 0.0)
            rows.extend([
                (base_label + " - " + t("annual_hvac_saving"), annual, "kWh/year",
                 t("remark_effect_percent").format(percent=annual_pct), src_passive, t(detail_key)),
                (base_label + " - " + t("peak_cooling_capacity_reduction"), cool_kw, "kW",
                 t("remark_effect_percent").format(percent=cool_pct), src_passive, t(detail_key)),
                (base_label + " - " + t("peak_heating_capacity_reduction"), heat_kw, "kW",
                 t("remark_effect_percent").format(percent=heat_pct), src_passive, t(detail_key)),
                (base_label + " - " + t("cooling_peak_duration_reduction"), cool_hours, "hours/year",
                 t("remark_duration_reduction"), src_passive, t(detail_key)),
                (base_label + " - " + t("heating_peak_duration_reduction"), heat_hours, "hours/year",
                 t("remark_duration_reduction"), src_passive, t(detail_key)),
            ])

        for index, (item, value, unit, basis, source, detail) in enumerate(rows, start=1):
            iid = self.tree.insert(
                "", "end",
                values=(f"{index:02d}", item, f"{float(value):,.2f}", unit, basis, source),
            )
            # Preserve the existing detailed explanation for row activation / detail viewers.
            self.tree.set_detail(iid, item, detail + "\n\n" + basis + "\n\n" + source)

    def show_monthly_thermal(self):
        """PATCH_175: show the 12-month heating/cooling profile for review."""
        if not self.summary:
            messagebox.showwarning(
                "Warning",
                "先に8760時間環境計算を実行してください。" if self.i18n.language == "ja"
                else "Run the 8760-hour environment calculation first.",
            )
            return
        rows = list(self.summary.get("monthly_thermal") or [])
        if not rows:
            messagebox.showwarning(
                "Warning",
                "月別データがありません。再計算してください。" if self.i18n.language == "ja"
                else "No monthly data are available. Recalculate Module 2.",
            )
            return

        win = tk.Toplevel(self)
        win.title("月別暖冷房確認" if self.i18n.language == "ja" else "Monthly Heating/Cooling Review")
        win.geometry("930x500")
        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        cols = ("month", "heat_load", "cool_load", "heat_elec", "cool_elec", "heat_peak", "cool_peak")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=14)
        labels_ja = ("月", "暖房負荷 kWh", "冷房負荷 kWh", "暖房電力 kWh", "冷房電力 kWh", "暖房ピーク kW", "冷房ピーク kW")
        labels_en = ("Month", "Heating Load kWh", "Cooling Load kWh", "Heating Elec. kWh", "Cooling Elec. kWh", "Heating Peak kW", "Cooling Peak kW")
        labels = labels_ja if self.i18n.language == "ja" else labels_en
        widths = (65, 135, 135, 135, 135, 135, 135)
        for c, label, width in zip(cols, labels, widths):
            tree.heading(c, text=label)
            tree.column(c, width=width, anchor="e" if c != "month" else "center")
        for r in rows:
            m = int(r.get("month", 0) or 0)
            month_label = f"{m}月" if self.i18n.language == "ja" else str(m)
            tree.insert("", "end", values=(
                month_label,
                f"{float(r.get('heating_load_kWh', 0.0) or 0.0):,.2f}",
                f"{float(r.get('cooling_load_kWh', 0.0) or 0.0):,.2f}",
                f"{float(r.get('heating_electricity_kWh', 0.0) or 0.0):,.2f}",
                f"{float(r.get('cooling_electricity_kWh', 0.0) or 0.0):,.2f}",
                f"{float(r.get('peak_heating_kW', 0.0) or 0.0):,.2f}",
                f"{float(r.get('peak_cooling_kW', 0.0) or 0.0):,.2f}",
            ))
        tree.pack(fill="both", expand=True)

        note = (
            "6～9月の冷房負荷、冬期の暖房負荷、月別ピークの分布を確認してください。"
            if self.i18n.language == "ja"
            else "Review summer cooling, winter heating, and the monthly peak distribution."
        )
        ttk.Label(frame, text=note).pack(anchor="w", pady=(8, 0))

        def save_monthly_csv():
            if self.project_path is None:
                return
            import csv
            from datetime import datetime, timezone
            project_dir = Path(self.project_path).resolve().parent
            out_dir = project_dir / "8760_Results"
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%y%m%d_%H%M")
            project_name = Path(self.project_path).stem
            default_name = f"{stamp}_AZRAS_MONTHLY_HEATING_COOLING_{project_name}.csv"
            path = filedialog.asksaveasfilename(
                parent=win, initialdir=out_dir, initialfile=default_name,
                defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            )
            if not path:
                return
            headers = [
                "月 / Month",
                "暖房負荷 kWh / Heating Load kWh",
                "冷房負荷 kWh / Cooling Load kWh",
                "暖房電力 kWh / Heating Electricity kWh",
                "冷房電力 kWh / Cooling Electricity kWh",
                "暖房ピーク kW / Heating Peak kW",
                "冷房ピーク kW / Cooling Peak kW",
            ]
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(headers)
                for r in rows:
                    w.writerow([
                        int(r.get("month", 0) or 0),
                        float(r.get("heating_load_kWh", 0.0) or 0.0),
                        float(r.get("cooling_load_kWh", 0.0) or 0.0),
                        float(r.get("heating_electricity_kWh", 0.0) or 0.0),
                        float(r.get("cooling_electricity_kWh", 0.0) or 0.0),
                        float(r.get("peak_heating_kW", 0.0) or 0.0),
                        float(r.get("peak_cooling_kW", 0.0) or 0.0),
                    ])
            messagebox.showinfo(
                "Saved",
                (("日英併記CSVを保存しました。\n" if self.i18n.language == "ja" else "Saved bilingual Japanese/English CSV.\n") + str(path)),
                parent=win,
            )

        ttk.Button(
            frame, text=("月別CSV保存（日英併記）" if self.i18n.language == "ja" else "Save Monthly CSV (JP/EN)"),
            command=save_monthly_csv,
        ).pack(anchor="e", pady=(8, 0))


    def show_envelope_mass_comparison(self):
        # PATCH_393: Module 1 may have re-analysed/imported AI data while Module 2
        # remains open.  Always synchronize the active Project JSON immediately
        # before building this dialog; otherwise the window can show a stale
        # in-memory envelope/surface snapshot even though Module 1 already saved
        # the latest data to disk.
        self.refresh_project_from_context()
        """PATCH_193: common envelope insulation + thermal-mass comparison.

        The comparison is intentionally project-specific and evidence-preserving:
        it starts from the current Module 1/2 baseline, replaces only the selected
        insulation layer, and runs the same 8760-hour engine for the alternative.
        RC/slab insulation position also changes the reduced-order indoor thermal-
        mass coupling so external vs internal insulation can be compared at the
        same nominal U-value/material thickness.
        """
        if self.project is None or not self.weather_file.get():
            messagebox.showwarning("Warning", "Project / weather data is required.")
            return

        win = tk.Toplevel(self)
        win.title("断熱・蓄熱 8760時間比較 PATCH_402" if self.i18n.language == "ja" else "Insulation / Thermal Mass 8760 Comparison PATCH_402")
        win.geometry("1720x820")

        note = (
            "現状仕様を基準に、断熱材・λ・厚さ・断熱位置を変更した比較案を同じ8760時間気象で再計算します。\n"
            "材料名は初期λ値の選択用です。実製品値が分かる場合はλを直接上書きしてください。\n"
            "RC壁・床では断熱位置により室内側に有効な蓄熱量も変化させます（企画比較用の縮約モデル）。\n"
            "左の□は『その部位を比較案で変更する』指定です。未チェック行は現状のままです。天井裏敷込みは屋根断熱とは別層として扱います。"
            if self.i18n.language == "ja" else
            "Runs the same 8760-hour weather for a baseline and an alternative insulation/mass scenario. "
            "Material names only provide initial lambda values; use product declared lambda when known. "
            "Check the box at left only for parts you want to change; unchecked parts remain at the baseline. "
            "Attic-ceiling insulation is a separate layer from the roof sandwich and applies only to its resolved room-mapped area. "
            "RC wall/slab insulation position also changes reduced-order indoor mass coupling."
        )
        ttk.Label(win, text=note, justify="left", wraplength=1420).pack(fill="x", padx=12, pady=8)

        # PATCH_195: render the window shell before scanning the project profile.
        # The comparison dialog must not run the 8760-hour solver merely by
        # opening it; the solver is invoked only by the explicit Run button.
        # update() here gives Windows/Tk a chance to paint the Toplevel first,
        # so the user sees the dialog immediately even with a large Project JSON.
        try:
            win.update_idletasks()
            win.update()
        except Exception:
            pass

        table = ttk.Frame(win)
        table.pack(fill="x", padx=12, pady=4)
        # PATCH_196: show the baseline as structured fields instead of one
        # truncated sentence.  Unknown baseline values stay explicitly unknown;
        # the comparison side is editable and never changes the stored baseline.
        headers = (["部位", "比較", "現状材料", "現状λ", "現状厚さ", "現状断熱位置", "根拠", "比較断熱材", "比較λ", "比較厚さ", "比較断熱位置"]
                   if self.i18n.language == "ja" else
                   ["Part","Compare","Current material","Current λ","Current thickness","Current position","Evidence","Alternative material","Alt λ","Alt thickness","Alt position"])
        for c,h in enumerate(headers):
            ttk.Label(table, text=h, font=("", 9, "bold")).grid(row=0,column=c,padx=3,pady=3,sticky="w")

        # PATCH_195: cache only the small baseline envelope snapshot used by
        # this dialog.  Do not copy/scan hourly 8760 data while the window is
        # opening.  The cache is automatically invalidated when the Project
        # object changes.
        m1 = (((self.project or {}).get("module_outputs") or {}).get("module1") or {})
        profile = m1.get("profile") or ((m1.get("drawing_analysis") or {}).get("profile") or {})
        # PATCH_384: id(project) alone is not a valid cache key because AI imports
        # and Module 1 refreshes mutate the same project dict in place.  Include
        # the actual envelope assembly payload and takeoff row count so reopening
        # this dialog always reflects the latest imported/analysed evidence.
        try:
            _asm_sig=json.dumps(profile.get("assemblies") or {},ensure_ascii=False,sort_keys=True,default=str)
        except Exception:
            _asm_sig=str(profile.get("assemblies") or {})
        _qt_rows=((m1.get("quantity_takeoff") or {}).get("rows") or [])
        cache_key=(id(self.project),_asm_sig,len(_qt_rows))
        cache = getattr(self, "_envelope_compare_baseline_cache", None)
        if not isinstance(cache, dict) or cache.get("project_key") != cache_key:
            assemblies = copy.deepcopy(profile.get("assemblies") or {})

            # PATCH_383: backward-compatible recovery for projects analysed before
            # the wall-insulation assembly bridge existed.  The Module 1 takeoff can
            # already contain a drawing-confirmed wall-section row such as
            # "グラスウール16K t100（矩計図記載）" even when profile.assemblies
            # still says the light wall is unresolved.  Recover that evidence here so
            # opening this comparison does NOT require re-running Drawing/Quantity.
            light = assemblies.get("light_wall") or {}
            _light_material = str(light.get("material") or "").lower() if isinstance(light, dict) else ""
            _insulation_tokens = ("glass wool","グラスウール","gw16","gw10","phenol","フェノール","xps","eps","pir","pur","rock wool","ロックウール","insulation","断熱")
            light_has_insulation = (
                isinstance(light, dict)
                and float(light.get("thickness_mm") or 0.0) > 0
                and any(tok in _light_material for tok in _insulation_tokens)
            )
            if not light_has_insulation:
                rows = ((m1.get("quantity_takeoff") or {}).get("rows") or [])
                for rec in rows:
                    if not isinstance(rec, dict):
                        continue
                    txt = " ".join(str(rec.get(k) or "") for k in ("item","specification","source_text_original","formula","evidence","calculation_basis"))
                    lowtxt = txt.lower()
                    # PATCH_389: a ceiling/roof GW row must never become exterior-wall insulation.
                    if not (("外壁" in txt or "exterior wall" in lowtxt) and not ("天井" in txt or "屋根" in txt or "ceiling" in lowtxt or "roof" in lowtxt)):
                        continue
                    mm = None
                    if ("グラスウール16K" in txt or "GW16K" in txt or "Glass wool 16K" in txt):
                        import re as _re
                        m = _re.search(r"(?:GW16K|グラスウール16K|Glass wool 16K)[^0-9]{0,20}(?:t\s*)?(\d+(?:\.\d+)?)", txt, _re.I)
                        if m:
                            try: mm=float(m.group(1))
                            except Exception: mm=None
                    if mm and mm > 0:
                        assemblies["light_wall"]={
                            "material":"Glass wool 16K",
                            "thickness_mm":mm,
                            "lambda_W_mK":0.038,
                            "insulation_position":"cavity",
                            "resolved":True,
                            "evidence_status":"confirmed",
                            "position_evidence_status":"estimated",
                            "source":str(rec.get("evidence") or rec.get("source") or "Module 1 wall-section takeoff: GW16K"),
                            "bridge_recovered_from_takeoff":True,
                        }
                        break

            # PATCH_389: recover roof sandwich and attic-ceiling insulation as
            # independent assemblies from takeoff evidence.  This fixes the old
            # one-row "roof" model that could not represent roof + ceiling layers.
            rows = ((m1.get("quantity_takeoff") or {}).get("rows") or [])
            for rec in rows:
                if not isinstance(rec, dict):
                    continue
                ev = str(rec.get("evidence_status") or "").lower()
                if ev in {"unresolved","unreadable","conflicting"}:
                    continue
                txt = " ".join(str(rec.get(k) or "") for k in ("item","specification","source_text_original","formula","evidence","calculation_basis"))
                lowtxt = txt.lower()
                if not any(k in lowtxt for k in ("glass wool","gw16","gw10")) and "グラスウール" not in txt:
                    continue
                import re as _re
                mm=None
                m=_re.search(r"(?:GW(?:16|10)K?|グラスウール(?:16|10)K?|Glass wool(?: 16K| 10K)?)[^0-9]{0,24}(?:t\s*)?(\d+(?:\.\d+)?)",txt,_re.I)
                if m:
                    try: mm=float(m.group(1))
                    except Exception: mm=None
                if not mm:
                    m=_re.search(r"(?:t|厚(?:さ)?)\s*[=:]?\s*(\d+(?:\.\d+)?)\s*(?:mm)?",txt,_re.I)
                    if m:
                        try: mm=float(m.group(1))
                        except Exception: mm=None
                if not mm or mm<=0:
                    continue
                is_ceiling = ("天井" in txt or "ceiling" in lowtxt or "attic" in lowtxt)
                is_roof = ("屋根" in txt or "roof" in lowtxt or "折板" in txt) and not is_ceiling
                part = "ceiling_attic" if is_ceiling else ("roof" if is_roof else None)
                if not part:
                    continue
                existing=assemblies.get(part) or {}
                if isinstance(existing,dict) and float(existing.get("thickness_mm") or 0)>0:
                    continue
                density = "16K" if ("16K" in txt.upper() or "16Ｋ" in txt) else ("10K" if ("10K" in txt.upper() or "10Ｋ" in txt) else "")
                q=rec.get("quantity")
                try: area=float(q) if str(rec.get("unit") or "").lower() in {"m2","m²","㎡"} else None
                except Exception: area=None
                assemblies[part]={
                    "material":("Glass wool "+density).strip(),
                    "thickness_mm":mm,
                    "lambda_W_mK":0.038 if density=="16K" else (0.050 if density=="10K" else None),
                    "insulation_position":"cavity" if part=="roof" else "interior",
                    "resolved":True,"evidence_status":ev or "confirmed",
                    "source":str(rec.get("evidence") or rec.get("source") or "Module 1 takeoff"),
                    "area_m2":area,
                    "bridge_recovered_from_takeoff":True,
                }

            # PATCH_401: old Project JSONs may have the attic-ceiling layer
            # material/thickness but no area_m2 because the quantity was saved as
            # m3. Recover coverage from A-11 geometry first, then from the
            # insulation-volume row. This lets existing projects use the fixed
            # model without another Module 1 analysis.
            _ca = assemblies.get("ceiling_attic") or {}
            if isinstance(_ca, dict) and float(_ca.get("area_m2") or 0.0) <= 0.0:
                _area = 0.0
                _a11 = ((m1.get("quantity_takeoff") or {}).get("a11_finish_schedule_geometry") or {})
                try:
                    _area = float(((_a11.get("totals") or {}).get("ceiling_gw16k_t100_area_m2")) or 0.0)
                except Exception:
                    _area = 0.0
                if _area <= 0.0:
                    _th = float(_ca.get("thickness_mm") or 0.0)
                    for rec in rows:
                        if not isinstance(rec, dict):
                            continue
                        _txt = " ".join(str(rec.get(k) or "") for k in ("item","specification","source_text_original","formula","evidence","calculation_basis")).lower()
                        if not (("ceiling" in _txt or "天井" in _txt) and ("glass wool" in _txt or "グラスウール" in _txt or "gw16" in _txt)):
                            continue
                        try:
                            _q = float(rec.get("accepted_quantity", rec.get("quantity")) or 0.0)
                        except Exception:
                            _q = 0.0
                        _u = str(rec.get("unit") or "").strip().lower()
                        if _q > 0 and _u in {"m2","m²","㎡"}:
                            _area = _q
                            break
                        if _q > 0 and _u in {"m3","m³","㎥"} and _th > 0:
                            _area = _q / (_th / 1000.0)
                            break
                if _area > 0.0:
                    _ca = dict(_ca)
                    _ca["area_m2"] = _area
                    _ca["area_recovered_by_patch401"] = True
                    assemblies["ceiling_attic"] = _ca

            floor_saved_cached = ((self.summary or {}).get("floor_thermal_settings") or {})
            cache = {
                "project_key": cache_key,
                "assemblies": assemblies,
                "floor_saved": floor_saved_cached,
            }
            self._envelope_compare_baseline_cache = cache
        assemblies = cache.get("assemblies") or {}

        def guess_material(raw):
            txt = str(raw or "").lower()
            aliases = [
                ("phenol", "Phenolic foam"), ("フェノール", "Phenolic foam"),
                ("pir", "PIR"), ("ウレタン", "PUR"), ("pur", "PUR"),
                ("xps", "XPS"), ("押出", "XPS"), ("eps", "EPS"),
                ("10k", "Glass wool 10K"), ("16k", "Glass wool 16K"),
                ("glass", "Glass wool 16K"), ("グラス", "Glass wool 16K"),
                ("rock", "Rock wool"), ("ロック", "Rock wool"),
            ]
            for key,val in aliases:
                if key in txt:
                    return val
            return "Custom"

        def evidence_known(a):
            if not isinstance(a, dict) or not a:
                return False
            if a.get("resolved") is True:
                return True
            st=str(a.get("evidence_status") or "").lower()
            return st in {"confirmed","estimated"} and any(a.get(k) not in (None, "", 0, 0.0) for k in ("material","thickness_mm","u_value_W_m2K","lambda_W_mK"))

        # PATCH (260917): removed the separate "foundation" row. Module 1 never
        # populates a distinct assemblies["foundation"] entry (only roof/
        # light_wall/rc_wall/slab exist), and this project's construction uses
        # an integrated mat foundation (べた基礎) where the foundation and the
        # ground-floor slab are the same physical pour -- so a separate
        # "基礎" row was structurally unable to ever show anything but
        # unresolved, regardless of what was confirmed in the floor thermal
        # settings panel. Renamed the slab row's label to 床・土間・ベタ基礎
        # (see COMPONENT_LABELS_JA) to make explicit that it now covers the
        # mat foundation too.
        components = ["roof","ceiling_attic","light_wall","rc_wall","slab"]
        vars_by = {}
        material_keys = list(MATERIALS.keys())
        material_display = {k:(MATERIAL_LABELS_JA.get(k,k) if self.i18n.language=="ja" else k) for k in material_keys}
        display_to_key = {v:k for k,v in material_display.items()}
        pos_keys = ["exterior","interior","cavity","none","other"]
        pos_display = {k:(POSITION_LABELS_JA.get(k,k) if self.i18n.language=="ja" else k) for k in pos_keys}
        pos_to_key = {v:k for k,v in pos_display.items()}

        floor_saved = cache.get("floor_saved") or {}
        for r,part in enumerate(components, start=1):
            a = assemblies.get(part) or {}
            known = evidence_known(a)
            material = guess_material(a.get("material"))
            thick = float(a.get("thickness_mm") or 0.0)
            lam = lambda_for(material, a.get("lambda_W_mK"))
            # BUGFIX: this used to default an unresolved insulation_position to
            # "other" (mass_coupling factor 0.50 in environment_engine_v9_1.py).
            # The baseline (unchecked) run never applies any position factor at
            # all and is therefore always effectively full mass coupling (1.00,
            # same as "exterior"). So the moment a user checked *any* wall/RC
            # wall/slab comparison row without also remembering to change
            # 比較断熱位置 away from its default, that row's active thermal mass
            # was silently halved relative to baseline -- for a reason
            # completely unrelated to the thickness change they were actually
            # testing, and enough on its own to swing an 8760-hour cooling/
            # heating total by a large margin. Default the unresolved case to
            # "exterior" instead, matching the baseline's implicit assumption,
            # so comparisons only vary the thing the user actually checked.
            pos = normalize_position(a.get("insulation_position")) if a.get("insulation_position") else "exterior"

            # A saved slab-under-insulation OR mat-foundation-bottom-insulation
            # setting is explicit project evidence. BUGFIX: this used to check
            # only slab_under_insulation, exactly the same omission PATCH_016
            # fixed in environment_engine_v9_1.py's calculation -- a project
            # with foundation_bottom_insulation=True and slab_under_insulation
            # =False (mat-foundation-bottom insulation, no separate under-slab
            # insulation) fell through to the generic "unresolved" material
            # lookup here, showing 現状断熱位置 as 未確認 even though the
            # floor thermal settings panel has this fully confirmed.
            if part == "slab" and (floor_saved.get("slab_under_insulation") or floor_saved.get("foundation_bottom_insulation")):
                known = True
                thick = float(floor_saved.get("slab_insulation_thickness_mm") or 0.0)
                lam = float(floor_saved.get("slab_insulation_conductivity_W_mK") or 0.0) or None
                material = "XPS" if lam and abs(lam-0.028)<0.003 else "Custom"
                pos = "exterior"

            # PATCH_194/196: never infer RC insulation merely from the
            # construction method.  Baseline cells show only project evidence.
            status = str(a.get("evidence_status") or ("confirmed" if known else "unresolved"))
            unknown = "未確認" if self.i18n.language=="ja" else "Unresolved"
            current_material = str(a.get("material") or unknown) if known else unknown
            explicit_lam = a.get("lambda_W_mK") if isinstance(a, dict) else None
            try:
                current_lambda = f"{float(explicit_lam):.3f}" if explicit_lam not in (None, "") and float(explicit_lam)>0 else unknown
            except Exception:
                current_lambda = unknown
            # PATCH_389: when the drawing resolves the insulation family/density
            # but omits lambda, show the model's material initial value explicitly
            # rather than the misleading "unresolved".  Evidence is downgraded to
            # estimated because this is a material-library value, not a drawing value.
            if current_lambda == unknown and known and material != "Custom" and lam:
                current_lambda = f"{float(lam):.3f}"
                if status == "confirmed":
                    status = "estimated"
            explicit_thick = a.get("thickness_mm") if isinstance(a, dict) else None
            try:
                current_thickness = f"{float(explicit_thick):.1f} mm" if explicit_thick not in (None, "") and float(explicit_thick)>0 else unknown
            except Exception:
                current_thickness = unknown
            explicit_pos = a.get("insulation_position") if isinstance(a, dict) else None
            current_position = (POSITION_LABELS_JA.get(normalize_position(explicit_pos), str(explicit_pos)) if self.i18n.language=="ja" else normalize_position(explicit_pos)) if explicit_pos else unknown

            # Explicit saved slab-under-insulation OR foundation-bottom-insulation
            # settings are baseline evidence (see BUGFIX note above).
            if part == "slab" and (floor_saved.get("slab_under_insulation") or floor_saved.get("foundation_bottom_insulation")):
                current_material = (MATERIAL_LABELS_JA.get(material, material) if self.i18n.language=="ja" else material)
                current_lambda = f"{lam:.3f}" if lam else unknown
                current_thickness = f"{thick:.1f} mm" if thick>0 else unknown
                current_position = POSITION_LABELS_JA.get("exterior", "外断熱") if self.i18n.language=="ja" else "exterior"
                status = "confirmed"

            enabled=tk.BooleanVar(value=False)
            # The alternative may start from a recognizable material family for
            # convenience, but blank/unknown numeric evidence is not fabricated.
            matvar=tk.StringVar(value=material_display.get(material, material_display["Custom"]))
            lamvar=tk.StringVar(value=(f"{lam:.3f}" if lam else ""))
            thickvar=tk.StringVar(value=(f"{thick:.1f}" if thick>0 else ""))
            posvar=tk.StringVar(value=pos_display.get(pos,pos_display["other"]))
            vars_by[part]=(enabled,matvar,lamvar,thickvar,posvar)

            ttk.Label(table,text=(("天井裏敷込み" if part=="ceiling_attic" else COMPONENT_LABELS_JA.get(part,part)) if self.i18n.language=="ja" else ("attic ceiling" if part=="ceiling_attic" else part))).grid(row=r,column=0,padx=3,pady=3,sticky="w")
            ttk.Checkbutton(table,variable=enabled).grid(row=r,column=1,padx=3)
            ttk.Label(table,text=current_material,width=30).grid(row=r,column=2,padx=3,pady=3,sticky="w")
            ttk.Label(table,text=current_lambda,width=10).grid(row=r,column=3,padx=3,pady=3,sticky="w")
            ttk.Label(table,text=current_thickness,width=12).grid(row=r,column=4,padx=3,pady=3,sticky="w")
            ttk.Label(table,text=current_position,width=12).grid(row=r,column=5,padx=3,pady=3,sticky="w")
            ttk.Label(table,text=status,width=11).grid(row=r,column=6,padx=3,pady=3,sticky="w")
            cmb=ttk.Combobox(table,textvariable=matvar,values=list(material_display.values()),state="readonly",width=24)
            cmb.grid(row=r,column=7,padx=3,pady=3,sticky="w")
            ttk.Entry(table,textvariable=lamvar,width=9).grid(row=r,column=8,padx=3,pady=3)
            ttk.Entry(table,textvariable=thickvar,width=9).grid(row=r,column=9,padx=3,pady=3)
            ttk.Combobox(table,textvariable=posvar,values=list(pos_display.values()),state="readonly",width=13).grid(row=r,column=10,padx=3,pady=3)
            def on_mat(_e, mv=matvar, lv=lamvar):
                key=display_to_key.get(mv.get(),"Custom")
                val=MATERIALS.get(key)
                if val:
                    lv.set(f"{val:.3f}")
            cmb.bind("<<ComboboxSelected>>", on_mat)

        result = ttk.LabelFrame(win, text=("8760時間比較結果" if self.i18n.language=="ja" else "8760-hour comparison result"))
        result.pack(fill="both", expand=True, padx=12, pady=8)
        cols=("metric","baseline","alternative","delta","percent")
        tree=ttk.Treeview(result,columns=cols,show="headings",height=12)
        labels=["指標","現状","比較案","差","差%"] if self.i18n.language=="ja" else ["Metric","Baseline","Alternative","Delta","Delta %"]
        for c,l,w in zip(cols,labels,[310,150,150,150,120]):
            tree.heading(c,text=l); tree.column(c,width=w,anchor="e" if c!="metric" else "w")
        tree.pack(fill="both",expand=True,padx=6,pady=6)

        status=tk.StringVar(value=("画面起動時は8760時間計算を実行しません。比較計算はボタン押下時のみ実行します。" if self.i18n.language=="ja" else "Opening this dialog does not run the 8760-hour solver; comparison runs only when the button is pressed."))
        ttk.Label(win,textvariable=status,justify="left",wraplength=1640).pack(fill="x",padx=12,pady=2)

        # PATCH_511: retain the most recent comparison in this dialog so the
        # user can archive exactly the scenario that produced the displayed
        # results.  Saving is intentionally separate from Project JSON update:
        # historical comparison files are immutable dated records.
        comparison_snapshot = {"value": None}

        def _project_comparison_folder():
            if self.project_path is None:
                return None
            project_json = Path(self.project_path)
            folder = project_json.parent / "8760_Comparison"
            folder.mkdir(parents=True, exist_ok=True)
            return folder

        def save_comparison_result():
            snap = comparison_snapshot.get("value")
            if not snap:
                messagebox.showwarning(
                    "Warning",
                    "先に『8760時間比較を実行』してください。" if self.i18n.language == "ja" else "Run the 8760 comparison before saving.",
                    parent=win,
                )
                return
            folder = _project_comparison_folder()
            if folder is None:
                messagebox.showwarning(
                    "Warning",
                    "Project JSONを先に保存してください。" if self.i18n.language == "ja" else "Save the Project JSON first.",
                    parent=win,
                )
                return
            from datetime import datetime, timezone
            import csv
            stamp = datetime.now(timezone.utc).strftime("%y%m%d_%H%M")
            project_name = Path(self.project_path).stem
            safe_name = "".join(ch if ch not in '<>:"/\\|?*' else '_' for ch in project_name).strip() or "Project"
            base = f"{stamp}_AZRAS_8760_COMPARISON_{safe_name}"
            json_path = folder / f"{base}.json"
            csv_path = folder / f"{base}.csv"
            # Do not overwrite a historical record if two saves happen within
            # the same minute.  Add a numeric suffix while retaining the date.
            if json_path.exists() or csv_path.exists():
                seq = 2
                while True:
                    j2 = folder / f"{base}_{seq}.json"
                    c2 = folder / f"{base}_{seq}.csv"
                    if not j2.exists() and not c2.exists():
                        json_path, csv_path = j2, c2
                        break
                    seq += 1
            payload = copy.deepcopy(snap)
            payload["saved_at"] = datetime.now(timezone.utc).isoformat()
            payload["project_json"] = str(self.project_path)
            payload["weather_file"] = str(self.weather_file.get() or "")
            payload["archive_folder"] = str(folder)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
            rows = payload.get("display_rows") or []
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                # PATCH_049: header follows the UI language (the metric labels in
                # display_rows are already in the UI language); English unchanged.
                from core.csv_export import header_label
                w.writerow([header_label(k, self.i18n.language) for k in ("metric", "baseline", "alternative", "delta", "delta_percent")])
                for row in rows:
                    w.writerow(list(row))
            messagebox.showinfo(
                "Saved",
                (("8760時間比較結果を保存しました。\n\n" + str(json_path) + "\n" + str(csv_path))
                 if self.i18n.language == "ja" else
                 ("Saved the 8760 comparison result.\n\n" + str(json_path) + "\n" + str(csv_path))),
                parent=win,
            )

        def load_comparison_result():
            """PATCH_512: reload an archived 8760 comparison in this dialog.

            JSON archives restore both the alternative insulation inputs and the
            displayed results. CSV archives restore the displayed result table
            only because CSV intentionally does not contain the scenario payload.
            Loading never changes the Project JSON baseline automatically.
            """
            folder = _project_comparison_folder()
            initialdir = str(folder) if folder is not None else str(Path(self.project_path).parent if self.project_path else self.root_dir)
            path = filedialog.askopenfilename(
                parent=win,
                title=("保存済み8760比較結果を開く" if self.i18n.language == "ja" else "Open saved 8760 comparison"),
                initialdir=initialdir,
                filetypes=[
                    ("AZRAS 8760 comparison", "*.json *.csv"),
                    ("JSON", "*.json"),
                    ("CSV", "*.csv"),
                    ("All files", "*.*"),
                ],
            )
            if not path:
                return
            archive_path = Path(path)
            try:
                if archive_path.suffix.lower() == ".json":
                    with open(archive_path, "r", encoding="utf-8-sig") as f:
                        payload = json.load(f)
                    if not isinstance(payload, dict) or payload.get("schema") != "AZRAS_8760_COMPARISON_ARCHIVE_V1":
                        raise ValueError("AZRAS 8760 comparison archive JSONではありません。" if self.i18n.language == "ja" else "This is not an AZRAS 8760 comparison archive JSON.")

                    # Guard against accidentally viewing another project's result
                    # as if it belonged to the currently open Project.
                    archived_project = str(payload.get("project_json") or "")
                    if archived_project and self.project_path:
                        old_name = Path(archived_project).stem
                        cur_name = Path(self.project_path).stem
                        if old_name and cur_name and old_name != cur_name:
                            proceed = messagebox.askyesno(
                                "Warning",
                                ((f"この比較結果は別Project用です。\n\n保存時Project: {old_name}\n現在Project: {cur_name}\n\n読み込みを続けますか？")
                                 if self.i18n.language == "ja" else
                                 (f"This comparison was saved for another Project.\n\nArchived Project: {old_name}\nCurrent Project: {cur_name}\n\nContinue loading?")),
                                parent=win,
                            )
                            if not proceed:
                                return

                    scenario = payload.get("scenario") or {}
                    if not isinstance(scenario, dict):
                        scenario = {}
                    for part, (enabled, mv, lv, tv, pv) in vars_by.items():
                        rec = scenario.get(part) if isinstance(scenario.get(part), dict) else None
                        if not rec or not rec.get("enabled", True):
                            enabled.set(False)
                            continue
                        enabled.set(True)
                        material = str(rec.get("material") or "Custom")
                        mv.set(material_display.get(material, material_display.get("Custom", "Custom")))
                        lam = rec.get("lambda_W_mK")
                        thick = rec.get("thickness_mm")
                        pos = normalize_position(rec.get("insulation_position") or "other")
                        lv.set("" if lam in (None, "") else f"{float(lam):.3f}")
                        tv.set("" if thick in (None, "") else f"{float(thick):.1f}")
                        pv.set(pos_display.get(pos, pos_display.get("other", "other")))

                    for iid in tree.get_children():
                        tree.delete(iid)
                    rows = payload.get("display_rows") or []
                    for row in rows:
                        if isinstance(row, (list, tuple)):
                            vals = list(row)[:5]
                            while len(vals) < 5:
                                vals.append("")
                            tree.insert("", "end", values=vals)
                    comparison_snapshot["value"] = copy.deepcopy(payload)
                    ev = str(payload.get("evidence_text") or "")
                    saved_at = str(payload.get("saved_at") or "")
                    loaded_msg = (
                        f"保存済み比較結果を読み込みました: {archive_path.name}" +
                        (f" / 保存日時: {saved_at}" if saved_at else "") +
                        ("\n" + ev if ev else "")
                    ) if self.i18n.language == "ja" else (
                        f"Loaded saved comparison: {archive_path.name}" +
                        (f" / Saved at: {saved_at}" if saved_at else "") +
                        ("\n" + ev if ev else "")
                    )
                    status.set(loaded_msg)
                elif archive_path.suffix.lower() == ".csv":
                    import csv
                    with open(archive_path, "r", encoding="utf-8-sig", newline="") as f:
                        rows = list(csv.reader(f))
                    for iid in tree.get_children():
                        tree.delete(iid)
                    # PATCH_049: accept both the English ("metric") and the
                    # Japanese ("指標") header written by the save function.
                    data_rows = rows[1:] if rows and rows[0] and str(rows[0][0]).strip().lower() in ("metric", "指標") else rows
                    clean_rows = []
                    for row in data_rows:
                        if not row:
                            continue
                        vals = list(row)[:5]
                        while len(vals) < 5:
                            vals.append("")
                        tree.insert("", "end", values=vals)
                        clean_rows.append(vals)
                    comparison_snapshot["value"] = {
                        "schema": "AZRAS_8760_COMPARISON_ARCHIVE_V1",
                        "comparison_type": "insulation_thermal_mass_8760",
                        "loaded_from_csv": str(archive_path),
                        "display_rows": clean_rows,
                    }
                    csv_msg = (
                        f"保存済みCSV比較結果を読み込みました: {archive_path.name}\nCSVには比較条件が含まれないため、表のみ復元しています。条件も復元する場合は同名のJSONを読み込んでください。"
                        if self.i18n.language == "ja" else
                        f"Loaded saved CSV comparison: {archive_path.name}\nCSV does not contain scenario settings, so only the result table was restored. Load the matching JSON to restore settings as well."
                    )
                    status.set(csv_msg)
                else:
                    raise ValueError("JSONまたはCSVを選択してください。" if self.i18n.language == "ja" else "Select a JSON or CSV file.")
            except Exception as exc:
                messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language), parent=win)

        def _scenario_label(payload):
            """Build a short human-readable label for one archived/live scenario,
            e.g. '屋根:フェノールフォーム150mm' -- falls back to the save
            timestamp or filename when no changed part is recorded (e.g. a
            CSV-only archive)."""
            scenario = payload.get("scenario") if isinstance(payload.get("scenario"), dict) else {}
            parts = []
            for part, rec in scenario.items():
                if not isinstance(rec, dict) or not rec.get("enabled", True):
                    continue
                name = ("天井裏敷込み" if part == "ceiling_attic" else COMPONENT_LABELS_JA.get(part, part)) if self.i18n.language == "ja" else ("attic ceiling" if part == "ceiling_attic" else part)
                thick = rec.get("thickness_mm")
                mat = str(rec.get("material") or "")
                thick_txt = f"{float(thick):.0f}mm" if thick not in (None, "") else ""
                parts.append(f"{name}:{mat}{thick_txt}")
            if parts:
                return " / ".join(parts)
            saved_at = str(payload.get("saved_at") or "")
            if saved_at:
                return saved_at[:16].replace("T", " ")
            src = payload.get("_source_label")
            return str(src) if src else ("(未保存)" if self.i18n.language == "ja" else "(unsaved)")

        def show_comparison_graph():
            folder = _project_comparison_folder()
            payloads = []
            if folder is not None and folder.exists():
                for p in sorted(folder.glob("*.json")):
                    try:
                        with open(p, "r", encoding="utf-8-sig") as f:
                            data = json.load(f)
                    except Exception:
                        continue
                    if isinstance(data, dict) and data.get("schema") == "AZRAS_8760_COMPARISON_ARCHIVE_V1" and data.get("display_rows"):
                        data = dict(data)
                        data["_source_label"] = p.stem
                        payloads.append(data)

            # PATCH_013: two saved comparisons with the same scenario
            # (identical changed parts) and identical resulting values for
            # every metric are visually indistinguishable in the graph --
            # they show as two bars with the same label and the same
            # height. Keep only the first such saved comparison and drop
            # later exact duplicates, so re-saving the same scenario twice
            # does not clutter the chart with redundant bars.
            def _dedup_key(payload):
                label = _scenario_label(payload)
                rows = tuple(sorted(
                    (str(r[0]), str(r[2])) for r in (payload.get("display_rows") or []) if r and len(r) > 2
                ))
                return (label, rows)

            deduped, seen_keys = [], set()
            for payload in payloads:
                key = _dedup_key(payload)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                deduped.append(payload)
            payloads = deduped

            live = comparison_snapshot.get("value")
            if isinstance(live, dict) and live.get("display_rows"):
                already_saved = any(
                    lv.get("saved_at") and lv.get("saved_at") == p.get("saved_at")
                    for p in payloads for lv in [live]
                )
                if not already_saved:
                    live = dict(live)
                    live["_source_label"] = "(未保存の現在の比較)" if self.i18n.language == "ja" else "(current unsaved comparison)"
                    if _dedup_key(live) not in seen_keys:
                        payloads.append(live)

            if not payloads:
                messagebox.showwarning(
                    "Warning",
                    ("保存済みの比較結果がありません。先に『8760時間比較を実行』し、必要なら『比較結果を保存』してください。"
                     if self.i18n.language == "ja" else
                     "No comparison results are available yet. Run the 8760 comparison first (and optionally save it)."),
                    parent=win,
                )
                return

            # PATCH_009: display_rows mixes three kinds of entries -- genuine
            # numeric energy/performance metrics, pure text/audit fields
            # (e.g. "Module 1 version", "AI積算元" -- a filename), and
            # physical-quantity "根拠" (basis) numbers that are often the SAME
            # across every saved scenario for this project (e.g. a wall area
            # that never changes because only the insulation material/
            # thickness changed, not the building geometry). All three ended
            # up in the metric dropdown with no distinction, so picking a
            # text field produced an empty chart and picking a
            # never-changing quantity produced an all-zero/flat chart with
            # no comparative value. Keep only labels that (a) are numeric in
            # every payload that has them, and (b) actually vary across the
            # payloads shown (or there is only one payload, in which case
            # variance cannot be judged yet).
            def _numeric_alt_values(label):
                values=[]
                for payload in payloads:
                    row=next((r for r in (payload.get("display_rows") or []) if r and str(r[0])==label), None)
                    if row is None or len(row)<3:
                        continue
                    try:
                        values.append(float(str(row[2]).replace(",","")))
                    except (ValueError, TypeError):
                        return None  # non-numeric in at least one payload -> exclude entirely
                return values

            candidate_labels=[]
            seen_labels=set()
            for payload in payloads:
                for row in (payload.get("display_rows") or []):
                    if row and str(row[0]) not in seen_labels:
                        seen_labels.add(str(row[0])); candidate_labels.append(str(row[0]))

            metrics=[]
            for label in candidate_labels:
                vals=_numeric_alt_values(label)
                if not vals:
                    continue
                if len(vals)>=2 and max(vals)-min(vals) <= max(abs(max(vals)),abs(min(vals)),1e-9)*1e-6:
                    continue  # identical across every saved scenario -- nothing to compare
                metrics.append(label)

            if not metrics:
                messagebox.showwarning(
                    "Warning",
                    ("比較できる数値指標がありません（すべて同一の値か、数値以外の項目でした）。"
                     if self.i18n.language == "ja" else
                     "No numeric metric varies across the saved comparisons (everything was identical or non-numeric)."),
                    parent=win,
                )
                return

            gwin = tk.Toplevel(win)
            gwin.title("8760時間比較グラフ" if self.i18n.language == "ja" else "8760-hour comparison graph")
            gwin.geometry("1100x680")

            top_bar = ttk.Frame(gwin)
            top_bar.pack(fill="x", padx=10, pady=8)
            ttk.Label(top_bar, text=("指標: " if self.i18n.language == "ja" else "Metric: ")).pack(side="left")
            metric_var = tk.StringVar(value=metrics[0] if metrics else "")
            metric_box = ttk.Combobox(top_bar, textvariable=metric_var, values=metrics, state="readonly", width=42)
            metric_box.pack(side="left", padx=(0, 12))
            ttk.Label(
                top_bar,
                text=(f"保存済み比較 {len(payloads)} 件を表示" if self.i18n.language == "ja" else f"Showing {len(payloads)} saved comparison(s)"),
            ).pack(side="left")

            chart = MultiSeriesBarChart(gwin, bg="white", highlightthickness=0)
            chart.pack(fill="both", expand=True, padx=10, pady=(0, 10))

            def redraw(_event=None):
                metric = metric_var.get()
                labels, values = [], []
                # PATCH_012: always show 現状仕様 (baseline) as the leftmost
                # bar, taken from row[1] (baseline) of the first saved
                # comparison that has this metric -- baseline is the same
                # design across every saved scenario for a given project, so
                # any one payload's baseline value is representative.
                baseline_row = next(
                    (r for payload in payloads for r in (payload.get("display_rows") or []) if r and str(r[0]) == metric),
                    None,
                )
                if baseline_row is not None:
                    try:
                        baseline_value = float(str(baseline_row[1]).replace(",", ""))
                        labels.append("現状仕様" if self.i18n.language == "ja" else "Current specification")
                        values.append(baseline_value)
                    except (ValueError, IndexError):
                        pass
                for payload in payloads:
                    row = next((r for r in (payload.get("display_rows") or []) if r and str(r[0]) == metric), None)
                    if row is None:
                        continue
                    try:
                        alt_value = float(str(row[2]).replace(",", ""))
                    except (ValueError, IndexError):
                        continue
                    labels.append(_scenario_label(payload))
                    values.append(alt_value)
                if not values:
                    chart.delete("all")
                    chart.create_text(20, 20, anchor="nw", text=("この指標のデータがありません。" if self.i18n.language == "ja" else "No data for this metric."))
                    return
                chart.draw(
                    labels, values,
                    y_title=metric,
                    title=(f"比較案別 {metric}" if self.i18n.language == "ja" else f"{metric} by alternative"),
                )

            metric_box.bind("<<ComboboxSelected>>", redraw)
            gwin.bind("<Configure>", lambda e: redraw() if e.widget is gwin else None)
            gwin.after(50, redraw)

        def run_compare():
            try:
                scenario={}
                for part,(enabled,mv,lv,tv,pv) in vars_by.items():
                    if not enabled.get():
                        continue
                    material=display_to_key.get(mv.get(),"Custom")
                    if not lv.get().strip() or not tv.get().strip():
                        raise ValueError(("比較対象のλと厚さを入力してください: " if self.i18n.language=="ja" else "Enter lambda and thickness for: ") + (("天井裏敷込み" if part=="ceiling_attic" else COMPONENT_LABELS_JA.get(part,part)) if self.i18n.language=="ja" else ("attic ceiling" if part=="ceiling_attic" else part)))
                    scenario[part]={
                        "enabled":True,
                        "material":material,
                        "lambda_W_mK":float(lv.get()),
                        "thickness_mm":float(tv.get()),
                        "insulation_position":pos_to_key.get(pv.get(),"other"),
                    }
                base_settings=self.settings()
                alt_settings=copy.deepcopy(base_settings)
                alt_settings["envelope_thermal_scenario"]=scenario
                status.set("8760時間比較計算中..." if self.i18n.language=="ja" else "Running 8760-hour comparison...")
                win.update_idletasks()
                _hb, sb=run_environment(self.project,self.weather_file.get(),base_settings)
                _ha, sa=run_environment(self.project,self.weather_file.get(),alt_settings)
                for iid in tree.get_children(): tree.delete(iid)
                # PATCH_204: bridge audit fields are stored inside
                # floor_thermal_breakdown, not at the summary top level.  The
                # PATCH_202/203 comparison table therefore displayed false 0.000
                # values even when Module 1 had been resolved correctly.
                bb=(sb.get("floor_thermal_breakdown") or {})
                ab=(sa.get("floor_thermal_breakdown") or {})

                numeric_metrics=(
                    [
                        ("年間暖房負荷 kWh","heating_load_kWh_per_year", False),
                        ("年間冷房負荷 kWh","cooling_load_kWh_per_year", False),
                        ("年間空調電力 kWh","hvac_electricity_kWh_per_year", False),
                        ("最大暖房能力 kW","peak_heating_kW", False),
                        ("最大冷房能力 kW","peak_cooling_kW", False),
                        ("8760計算で使用した有効熱容量 MJ/K","solver_used_effective_heat_capacity_MJ_K", False),
                        ("Module 1入力 有効蓄熱量 MJ/K","module1_input_effective_heat_capacity_MJ_K", False),
                        ("Project JSON 積算行数","quantity_bridge_takeoff_row_count", True),
                        ("Project JSON コンクリートm3行数","quantity_bridge_concrete_m3_row_count", True),
                        ("8760使用 軽量外壁面積 m²","light_wall_area_m2_used", True),
                        ("8760使用 軽量外壁U値 W/m²K","light_wall_u_W_m2K_used", True),
                        ("8760使用 RC外壁面積 m²","rc_wall_area_m2_used", True),
                        ("8760使用 RC外壁U値 W/m²K","rc_wall_u_W_m2K_used", True),
                        ("8760使用 床・土間面積 m²","slab_area_m2_used", True),
                        ("8760使用 床・地盤U値 W/m²K","slab_ground_u_W_m2K_used", True),
                        ("8760使用 天井裏断熱面積 m²","attic_ceiling_area_m2_used", True),
                        ("8760使用 有効屋根U値 W/m²K","effective_roof_u_W_m2K_used", True),
                        ("8760使用 地盤追加断熱R m²K/W","ground_added_insulation_R_m2K_W", True),
                        ("Module 1補完として追加した熱容量 MJ/K","module1_fallback_added_heat_capacity_MJ_K", True),
                        ("年間一次エネルギー MJ","primary_energy_MJ_per_year", False),
                        ("年間運用CO2 kg","operational_CO2_kg_per_year", False),
                    ] if self.i18n.language=="ja" else [
                        ("Annual heating load kWh","heating_load_kWh_per_year", False),
                        ("Annual cooling load kWh","cooling_load_kWh_per_year", False),
                        ("Annual HVAC electricity kWh","hvac_electricity_kWh_per_year", False),
                        ("Peak heating capacity kW","peak_heating_kW", False),
                        ("Peak cooling capacity kW","peak_cooling_kW", False),
                        ("Effective heat capacity used by 8760 solver MJ/K","solver_used_effective_heat_capacity_MJ_K", False),
                        ("Module 1 input effective heat capacity MJ/K","module1_input_effective_heat_capacity_MJ_K", False),
                        ("Project JSON takeoff row count","quantity_bridge_takeoff_row_count", True),
                        ("Project JSON concrete-m3 row count","quantity_bridge_concrete_m3_row_count", True),
                        ("8760 light-wall area used m²","light_wall_area_m2_used", True),
                        ("8760 light-wall U-value used W/m²K","light_wall_u_W_m2K_used", True),
                        ("8760 exterior-RC wall area used m²","rc_wall_area_m2_used", True),
                        ("8760 exterior-RC wall U-value used W/m²K","rc_wall_u_W_m2K_used", True),
                        ("8760 floor/ground slab area used m²","slab_area_m2_used", True),
                        ("8760 slab-to-ground U-value used W/m²K","slab_ground_u_W_m2K_used", True),
                        ("8760 attic-ceiling insulated area used m²","attic_ceiling_area_m2_used", True),
                        ("8760 effective roof U-value used W/m²K","effective_roof_u_W_m2K_used", True),
                        ("8760 added ground-insulation R m²K/W","ground_added_insulation_R_m2K_W", True),
                        ("Heat capacity added as Module 1 fallback MJ/K","module1_fallback_added_heat_capacity_MJ_K", True),
                        ("Annual primary energy MJ","primary_energy_MJ_per_year", False),
                        ("Annual operational CO2 kg","operational_CO2_kg_per_year", False),
                    ]
                )
                for label,key,nested in numeric_metrics:
                    bsrc=bb if nested else sb
                    asrc=ab if nested else sa
                    b=float(bsrc.get(key,0.0) or 0.0); a=float(asrc.get(key,0.0) or 0.0); d=a-b
                    pct=(d/b*100.0) if abs(b)>1e-9 else 0.0
                    tree.insert("", "end", values=(label,f"{b:,.3f}",f"{a:,.3f}",f"{d:+,.3f}",f"{pct:+.2f}%"))

                # Text/boolean audit fields must not be coerced to float.
                text_metrics=(
                    [
                        ("Module 1解決状態","quantity_bridge_module1_resolved"),
                        ("Module 1 version","quantity_bridge_module1_version"),
                        ("上流構造数量状態","quantity_bridge_upstream_structural_quantity_status"),
                        ("AI積算元","ai_takeoff_source_json"),
                    ] if self.i18n.language=="ja" else [
                        ("Module 1 resolution status","quantity_bridge_module1_resolved"),
                        ("Module 1 version","quantity_bridge_module1_version"),
                        ("Upstream structural quantity status","quantity_bridge_upstream_structural_quantity_status"),
                        ("AI takeoff source","ai_takeoff_source_json"),
                    ]
                )
                for label,key in text_metrics:
                    bv=bb.get(key,"")
                    av=ab.get(key,"")
                    if isinstance(bv, bool): bv="resolved" if bv else "unresolved"
                    if isinstance(av, bool): av="resolved" if av else "unresolved"
                    delta=("一致" if str(bv)==str(av) else "変更") if self.i18n.language=="ja" else ("Match" if str(bv)==str(av) else "Changed")
                    tree.insert("", "end", values=(label,str(bv),str(av),delta,"—"))

                # PATCH_197: expose the structural thermal-mass contribution by
                # component.  These values use the same active-volume and
                # insulation-position coupling assumptions actually passed to
                # the 8760-hour solver; they are not a second calculation.
                # PATCH_201: show the actual Module 1 concrete quantities that
                # fed the thermal-mass bridge before showing their active heat
                # capacities.  Foundation RC is displayed for audit purposes;
                # it is not silently added to the indoor active-mass nodes.
                quantity_metrics=(
                    [
                        ("RC外壁 数量根拠 m³","exterior_rc_volume_m3"),
                        ("RC隔壁 数量根拠 m³","partition_rc_volume_m3"),
                        ("柱・梁RC 数量根拠 m³","frame_rc_volume_m3"),
                        ("床・土間 数量根拠 m³","ground_slab_volume_m3"),
                        ("上階・屋根スラブ 数量根拠 m³","upper_slab_volume_m3"),
                        ("基礎RC 数量根拠 m³（蓄熱未算入）","foundation_rc_volume_m3"),
                    ] if self.i18n.language=="ja" else [
                        ("Exterior RC quantity basis m³","exterior_rc_volume_m3"),
                        ("Partition RC quantity basis m³","partition_rc_volume_m3"),
                        ("Column/beam RC quantity basis m³","frame_rc_volume_m3"),
                        ("Floor/ground slab quantity basis m³","ground_slab_volume_m3"),
                        ("Upper-floor/roof slab quantity basis m³","upper_slab_volume_m3"),
                        ("Foundation RC quantity basis m³ (not in active mass)","foundation_rc_volume_m3"),
                    ]
                )
                for label,key in quantity_metrics:
                    b=float(bb.get(key,0.0) or 0.0); a=float(ab.get(key,0.0) or 0.0); d=a-b
                    pct=(d/b*100.0) if abs(b)>1e-9 else 0.0
                    tree.insert("", "end", values=(label,f"{b:,.3f}",f"{a:,.3f}",f"{d:+,.3f}",f"{pct:+.2f}%"))

                component_metrics=(
                    [
                        ("RC壁 有効蓄熱容量 MJ/K","rc_wall_active_heat_capacity_MJ_K"),
                        ("床・土間 有効蓄熱容量 MJ/K","slab_active_heat_capacity_MJ_K"),
                        ("構造体 有効蓄熱容量合計 MJ/K","structural_active_heat_capacity_MJ_K"),
                    ] if self.i18n.language=="ja" else [
                        ("RC wall active heat capacity MJ/K","rc_wall_active_heat_capacity_MJ_K"),
                        ("Floor/ground slab active heat capacity MJ/K","slab_active_heat_capacity_MJ_K"),
                        ("Total structural active heat capacity MJ/K","structural_active_heat_capacity_MJ_K"),
                    ]
                )
                for label,key in component_metrics:
                    b=float(bb.get(key,0.0) or 0.0); a=float(ab.get(key,0.0) or 0.0); d=a-b
                    pct=(d/b*100.0) if abs(b)>1e-9 else 0.0
                    tree.insert("", "end", values=(label,f"{b:,.3f}",f"{a:,.3f}",f"{d:+,.3f}",f"{pct:+.2f}%"))

                br=(ab.get("envelope_thermal_scenario") or {})
                if self.i18n.language=="ja":
                    evidence = (
                        "8760計算使用熱容量="
                        f"{float(sa.get('solver_used_effective_heat_capacity_MJ_K',0.0) or 0.0):,.3f} MJ/K / "
                        "Module 1入力="
                        f"{float(sa.get('module1_input_effective_heat_capacity_MJ_K',0.0) or 0.0):,.3f} MJ/K / "
                        "断熱位置の蓄熱結合係数: "
                        f"RC={br.get('rc_mass_position_factor','-')}, slab={br.get('slab_mass_position_factor','-')} / "
                        "数量根拠: "
                        f"RC外壁={float(ab.get('exterior_rc_volume_m3',0.0) or 0.0):,.3f}m³, "
                        f"RC隔壁={float(ab.get('partition_rc_volume_m3',0.0) or 0.0):,.3f}m³, "
                        f"土間={float(ab.get('ground_slab_volume_m3',0.0) or 0.0):,.3f}m³, "
                        f"柱梁RC={float(ab.get('frame_rc_volume_m3',0.0) or 0.0):,.3f}m³, "
                        f"基礎RC={float(ab.get('foundation_rc_volume_m3',0.0) or 0.0):,.3f}m³（基礎は室内有効蓄熱へ自動加算しない） / "
                        "一致行: " + "; ".join(
                            f"{r.get('item','')}={float(r.get('quantity_m3',0.0) or 0.0):,.3f}m³"
                            for r in (ab.get('quantity_bridge_matched_rows') or [])
                        )
                    )
                else:
                    evidence = (
                        "8760 solver capacity="
                        f"{float(sa.get('solver_used_effective_heat_capacity_MJ_K',0.0) or 0.0):,.3f} MJ/K / "
                        "Module 1 input="
                        f"{float(sa.get('module1_input_effective_heat_capacity_MJ_K',0.0) or 0.0):,.3f} MJ/K / "
                        "mass coupling: "
                        f"RC={br.get('rc_mass_position_factor','-')}, slab={br.get('slab_mass_position_factor','-')} / "
                        "quantity basis: "
                        f"exterior RC={float(ab.get('exterior_rc_volume_m3',0.0) or 0.0):,.3f}m³, "
                        f"partition RC={float(ab.get('partition_rc_volume_m3',0.0) or 0.0):,.3f}m³, "
                        f"ground slab={float(ab.get('ground_slab_volume_m3',0.0) or 0.0):,.3f}m³, "
                        f"frame RC={float(ab.get('frame_rc_volume_m3',0.0) or 0.0):,.3f}m³, "
                        f"foundation RC={float(ab.get('foundation_rc_volume_m3',0.0) or 0.0):,.3f}m³ (not auto-added to indoor active mass) / "
                        "matched rows: " + "; ".join(
                            f"{r.get('item','')}={float(r.get('quantity_m3',0.0) or 0.0):,.3f}m³"
                            for r in (ab.get('quantity_bridge_matched_rows') or [])
                        )
                    )
                status.set(evidence)

                # PATCH_511: capture both the changed insulation inputs and the
                # complete baseline/alternative summaries used by the displayed
                # table.  This makes each dated archive reproducible/auditable.
                comparison_snapshot["value"] = {
                    "schema": "AZRAS_8760_COMPARISON_ARCHIVE_V1",
                    "comparison_type": "insulation_thermal_mass_8760",
                    "scenario": copy.deepcopy(scenario),
                    "baseline_settings": copy.deepcopy(base_settings),
                    "alternative_settings": copy.deepcopy(alt_settings),
                    "baseline_summary": copy.deepcopy(sb),
                    "alternative_summary": copy.deepcopy(sa),
                    "evidence_text": evidence,
                    "display_rows": [list(tree.item(iid, "values")) for iid in tree.get_children()],
                }
            except Exception as exc:
                messagebox.showerror("Error",friendly_exception_text(exc,self.i18n.language),parent=win)
                status.set("")

        btns=ttk.Frame(win); btns.pack(fill="x",padx=12,pady=6)
        ttk.Button(btns,text=("8760時間比較を実行" if self.i18n.language=="ja" else "Run 8760 comparison"),command=run_compare).pack(side="left")
        ttk.Button(btns,text=("比較結果を保存" if self.i18n.language=="ja" else "Save comparison result"),command=save_comparison_result).pack(side="left",padx=(8,0))
        ttk.Button(btns,text=("保存結果を読込" if self.i18n.language=="ja" else "Load saved result"),command=load_comparison_result).pack(side="left",padx=(8,0))
        ttk.Button(btns,text=("グラフ表示" if self.i18n.language=="ja" else "Show graph"),command=show_comparison_graph).pack(side="left",padx=(8,0))
        ttk.Label(btns,text=("保存先: Projectフォルダー / 8760_Comparison" if self.i18n.language=="ja" else "Save to: Project folder / 8760_Comparison")).pack(side="left",padx=(12,0))
        ttk.Button(btns,text=("閉じる" if self.i18n.language=="ja" else "Close"),command=win.destroy).pack(side="right")

    def show_slab_ground_diagnostic(self):
        """PATCH_192: audit geometry-aware slab/ground coupling."""
        import math
        import pandas as pd

        cfg = (self.summary or {}).get("thermal_model_config") or {}
        breakdown = (self.summary or {}).get("floor_thermal_breakdown") or {}
        if not cfg:
            messagebox.showwarning(
                "Warning",
                "8760時間計算後に実行してください。" if self.i18n.language == "ja"
                else "Run the 8760-hour calculation first.",
            )
            return

        def fv(v, default=0.0):
            try:
                x = float(v)
                return x if math.isfinite(x) else default
            except Exception:
                return default

        area = max(0.0, fv(cfg.get("slab_area_m2")))
        u_ground = max(0.0, fv(cfg.get("u_slab_to_ground_W_m2K")))
        h_inside = max(0.0, fv(cfg.get("h_inside_slab_W_m2K")))
        g_ground = area * u_ground
        g_inside = area * h_inside
        if area > 0 and u_ground > 0 and h_inside > 0:
            u_series = 1.0 / (1.0/u_ground + 1.0/h_inside)
            g_series = u_series * area
        else:
            u_series = g_series = 0.0

        floor_cfg = {}
        try:
            floor_cfg = self._floor_thermal_settings() or {}
        except Exception:
            try:
                floor_cfg = {k: v.get() for k, v in self.floor_thermal_vars.items()}
            except Exception:
                floor_cfg = {}
        no_insulation = str(floor_cfg.get("insulation_position") or "") == "none"
        insulated = (not no_insulation) and bool(floor_cfg.get("slab_under_insulation", False))
        if no_insulation:
            thick_mm = 0.0
            lam = 0.0
        else:
            thick_mm = max(0.0, fv(floor_cfg.get("slab_insulation_thickness_mm"), 100.0))
            lam = max(0.005, fv(floor_cfg.get("slab_insulation_conductivity_W_mK"), 0.028))
        t_m = thick_mm / 1000.0
        u_with_ins = u_ground
        if h_inside > 0 and u_with_ins > 0:
            u_series_ins = 1.0 / (1.0/u_with_ins + 1.0/h_inside)
        else:
            u_series_ins = 0.0
        perimeter_m = fv(breakdown.get("ground_floor_perimeter_m"))
        bp_m = fv(breakdown.get("ground_characteristic_dimension_Bp_m"))
        soil_lambda = fv(breakdown.get("ground_soil_conductivity_W_mK"), 2.0)
        ground_method = str(breakdown.get("ground_u_method") or "-")

        july = None
        if self.hourly is not None and len(self.hourly):
            try:
                hh = self.hourly.copy()
                hh["datetime"] = pd.to_datetime(hh["datetime"], errors="coerce")
                july = hh[hh["datetime"].dt.month == 7].copy()
            except Exception:
                july = None

        def mean_col(col):
            if july is None or july.empty or col not in july.columns:
                return None
            x = pd.to_numeric(july[col], errors="coerce").dropna()
            return float(x.mean()) if len(x) else None

        def sum_col(col):
            if july is None or july.empty or col not in july.columns:
                return None
            x = pd.to_numeric(july[col], errors="coerce").fillna(0.0)
            return float(x.sum())

        zone = mean_col("zone_air_C")
        slab = mean_col("slab_C")
        ground = mean_col("ground_C")
        slab_zone = sum_col("slab_to_zone_kWh")
        ground_slab = sum_col("ground_to_slab_kWh")

        win = tk.Toplevel(self)
        win.title("土間・地盤診断 PATCH_192" if self.i18n.language == "ja" else "Slab / Ground Diagnostic PATCH_192")
        win.geometry("980x560")
        fr = ttk.Frame(win)
        fr.pack(fill="both", expand=True, padx=12, pady=12)

        if self.i18n.language == "ja":
            title = (
                f"現在モデル: 土間面積 {area:,.2f} m² / 地盤側U {u_ground:.3f} W/m²K / "
                f"室内側h {h_inside:.3f} W/m²K\n"
                f"床外周長 {perimeter_m:,.2f} m / B′ {bp_m:,.3f} m / 地盤λ {soil_lambda:.2f} W/mK\n"
                f"地盤側コンダクタンス U×A = {g_ground:,.1f} W/K / "
                f"室内-地盤の定常直列換算 U = {u_series:.3f} W/m²K ({g_series:,.1f} W/K)"
            )
            ttk.Label(fr, text=title, wraplength=940).pack(anchor="w", pady=(0, 10))
            ins = (
                f"土間下断熱: {'あり' if insulated else 'なし'} / 入力厚 {thick_mm:.1f} mm / λ={lam:.3f} W/mK / "
                f"現在計算へ反映済みの地盤側U {u_ground:.3f} W/m²K / "
                f"算定方式 {ground_method}"
            )
            ttk.Label(fr, text=ins, wraplength=940).pack(anchor="w", pady=(0, 10))
        else:
            title = (
                f"Current model: slab area {area:,.2f} m² / ground-side U {u_ground:.3f} W/m²K / "
                f"inside h {h_inside:.3f} W/m²K\n"
                f"floor perimeter {perimeter_m:,.2f} m / B′ {bp_m:.3f} m / soil λ {soil_lambda:.2f} W/mK\n"
                f"Ground conductance U×A = {g_ground:,.1f} W/K / steady zone-ground series U = "
                f"{u_series:.3f} W/m²K ({g_series:,.1f} W/K)"
            )
            ttk.Label(fr, text=title, wraplength=940).pack(anchor="w", pady=(0, 10))
            ins = (
                f"Under-slab insulation: {'ON' if insulated else 'OFF'} / {thick_mm:.1f} mm / λ={lam:.3f} W/mK / "
                f"ground-side U applied in current run {u_ground:.3f} W/m²K / method {ground_method}"
            )
            ttk.Label(fr, text=ins, wraplength=940).pack(anchor="w", pady=(0, 10))

        vals = [
            ("7月平均室温" if self.i18n.language == "ja" else "July mean zone temp", zone, "°C"),
            ("7月平均土間温度" if self.i18n.language == "ja" else "July mean slab temp", slab, "°C"),
            ("7月平均地盤温度" if self.i18n.language == "ja" else "July mean ground temp", ground, "°C"),
            ("7月 床→室" if self.i18n.language == "ja" else "July slab→zone", slab_zone, "kWh"),
            ("7月 地盤→床" if self.i18n.language == "ja" else "July ground→slab", ground_slab, "kWh"),
        ]
        tree = ttk.Treeview(fr, columns=("item","value","unit"), show="headings", height=7)
        for c, lab, w in (("item", "項目" if self.i18n.language=="ja" else "Item", 360),
                          ("value", "値" if self.i18n.language=="ja" else "Value", 180),
                          ("unit", "単位" if self.i18n.language=="ja" else "Unit", 100)):
            tree.heading(c, text=lab); tree.column(c, width=w, anchor="center")
        for name, value, unit in vals:
            tree.insert("", "end", values=(name, "未取得" if value is None else f"{value:,.2f}", unit))
        tree.pack(fill="x", pady=(4, 12))

        note_ja = (
            "判定方法: 現行3ノードモデルでは『地盤→床』は床ノード温度の更新だけに使用し、室内負荷へ直接加算しません。"
            "室内へ作用するのは『床→室』です。したがって二重計上ではありません。\n"
            "PATCH_192では固定U値を廃止し、床面積Aと外周長Pから特性寸法B′=A/(0.5P)を求め、"
            "ISO 13370の特性寸法による定常式を縮約3ノードモデルの等価地盤Uとして使用します。"
            "半球や固定季節月による補正は行いません。これは企画比較用の縮約モデルであり、詳細設計用の多次元地盤解析ではありません。"
        )
        note_en = (
            "The reduced 3-node model uses ground→slab only to update the slab node; it is not added directly to the zone load. "
            "Only slab→zone acts on the zone, so there is no double counting.\n"
            "PATCH_192 replaces the fixed ground U with a geometry-aware equivalent based on floor area A, perimeter P, "
            "and characteristic dimension B′=A/(0.5P), using the ISO 13370 steady slab form inside the reduced 3-node model. "
            "No hemisphere or fixed-season-month correction is applied. This remains a planning reduced model, not a multidimensional ground solver."
        )
        ttk.Label(fr, text=note_ja if self.i18n.language=="ja" else note_en, wraplength=940).pack(anchor="w")

    def show_summer_heat_balance(self):
        """PATCH_191 core retained: hemisphere-independent 12-month annual thermal-balance details."""
        if self.hourly is None or len(self.hourly) == 0:
            messagebox.showwarning("Warning", "先に8760時間環境計算を実行してください。" if self.i18n.language == "ja" else "Run the 8760-hour environment calculation first.")
            return
        try:
            import pandas as pd
            h = self.hourly.copy()
            h["datetime"] = pd.to_datetime(h["datetime"], errors="coerce")
            h = h[h["datetime"].notna()].copy()
        except Exception as exc:
            messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language)); return
        required = ["direct_envelope_kWh", "rc_wall_to_zone_kWh", "slab_to_zone_kWh", "ground_to_slab_kWh", "ventilation_kWh", "internal_gain_kWh", "window_solar_total_kWh", "opaque_roof_solar_kWh", "heating_load_kWh", "cooling_load_kWh"]
        missing = [k for k in required if k not in h.columns]
        if missing:
            messagebox.showwarning("Warning", ("年間熱収支の詳細列が不足しています。8760時間計算を再実行してください。\n" if self.i18n.language == "ja" else "Annual thermal-balance detail fields are missing. Recalculate Module 2.\n") + ", ".join(missing)); return

        win = tk.Toplevel(self)
        win.title("年間熱収支詳細" if self.i18n.language == "ja" else "Annual Thermal Balance Details")
        win.geometry("1540x880")
        outer = ttk.Frame(win); outer.pack(fill="both", expand=True, padx=8, pady=8)
        note = ("1～12月を実気象・8760時間計算結果から判定します。北半球/南半球の固定季節月は使用しません。" if self.i18n.language == "ja" else "All 12 months are classified from actual weather and 8760-hour results; no fixed Northern/Southern Hemisphere season months are used.")
        ttk.Label(outer, text=note, wraplength=1480).pack(fill="x", pady=(0,6))

        def msum(df, col):
            return float(pd.to_numeric(df[col], errors="coerce").fillna(0.0).sum()) if col in df.columns else 0.0
        def classify(heat, cool):
            eps=0.01
            if heat > eps and cool > eps: return "暖冷房併存" if self.i18n.language=="ja" else "Mixed"
            if heat > eps: return "暖房" if self.i18n.language=="ja" else "Heating"
            if cool > eps: return "冷房" if self.i18n.language=="ja" else "Cooling"
            return "中間期" if self.i18n.language=="ja" else "Neutral"

        mframe=ttk.LabelFrame(outer, text=("1～12月 熱収支・暖冷房判定" if self.i18n.language=="ja" else "Jan-Dec Heat Balance / HVAC Classification")); mframe.pack(fill="x", pady=(0,8))
        mcols=("month","mode","heat","cool","solar","roofsolar","internal","vent","envelope","rc","slab","ground")
        labs=("月","判定","暖房負荷kWh","冷房負荷kWh","窓日射kWh","屋根吸収日射kWh","内部発熱kWh","換気kWh","外皮直接熱kWh","RC壁→室kWh","床→室kWh","地盤→床kWh") if self.i18n.language=="ja" else ("Month","Mode","Heating kWh","Cooling kWh","Window solar","Roof solar","Internal","Ventilation","Envelope","RC wall→zone","Slab→zone","Ground→slab")
        mtree=ttk.Treeview(mframe, columns=mcols, show="headings", height=10)
        for c,lab in zip(mcols,labs): mtree.heading(c,text=lab); mtree.column(c,width=120 if c not in ("month","mode") else (55 if c=="month" else 90),anchor="center" if c in ("month","mode") else "e")
        for m in range(1,13):
            mm=h[h["datetime"].dt.month==m]; heat=msum(mm,"heating_load_kWh"); cool=msum(mm,"cooling_load_kWh")
            mtree.insert("","end",values=(f"{m}月" if self.i18n.language=="ja" else str(m),classify(heat,cool),f"{heat:,.2f}",f"{cool:,.2f}",f"{msum(mm,'window_solar_total_kWh'):,.2f}",f"{msum(mm,'opaque_roof_solar_kWh'):,.2f}",f"{msum(mm,'internal_gain_kWh'):,.2f}",f"{msum(mm,'ventilation_kWh'):,.2f}",f"{msum(mm,'direct_envelope_kWh'):,.2f}",f"{msum(mm,'rc_wall_to_zone_kWh'):,.2f}",f"{msum(mm,'slab_to_zone_kWh'):,.2f}",f"{msum(mm,'ground_to_slab_kWh'):,.2f}"))
        mtree.pack(fill="x")

        control=ttk.Frame(outer); control.pack(fill="x",pady=(0,5))
        ttk.Label(control,text=("時間別表示月:" if self.i18n.language=="ja" else "Hourly month:")).pack(side="left")
        month_var=tk.IntVar(value=7)
        cb=ttk.Combobox(control,textvariable=month_var,values=list(range(1,13)),state="readonly",width=5); cb.pack(side="left",padx=5)
        # PATCH_524: Keep the annual CSV save action in the always-visible control row.
        # On 1080p-class displays the requested heights of the monthly + hourly trees can
        # push the old bottom-only save button below the visible client area.
        ttk.Button(
            control,
            text=("年間熱収支CSV保存（日英併記）" if self.i18n.language=="ja" else "Save Annual Thermal Balance CSV (JP/EN)"),
            command=lambda: save_diag_csv()
        ).pack(side="right", padx=(8,0))
        table_frame=ttk.Frame(outer); table_frame.pack(fill="both",expand=True)
        cols=("datetime","outdoor","zone","ground","ghi","roofsolar","envelope","rcwall","slabzone","groundslab","solar","vent","internal","heating","cooling")
        labels=("日時","外気℃","室温℃","地盤℃","日射W/m²","屋根吸収日射kWh","外壁・屋根等kWh","RC壁→室kWh","床→室kWh","地盤→床kWh","窓日射kWh","換気kWh","内部発熱kWh","暖房負荷kWh","冷房負荷kWh") if self.i18n.language=="ja" else ("Datetime","Outdoor°C","Zone°C","Ground°C","GHI W/m²","Roof solar","Envelope","RC wall→zone","Slab→zone","Ground→slab","Window solar","Ventilation","Internal","Heating","Cooling")
        tree=ttk.Treeview(table_frame,columns=cols,show="headings",height=14)
        for c,lab in zip(cols,labels): tree.heading(c,text=lab); tree.column(c,width=105 if c!="datetime" else 135,anchor="center" if c=="datetime" else "e")
        ybar=ttk.Scrollbar(table_frame,orient="vertical",command=tree.yview); xbar=ttk.Scrollbar(table_frame,orient="horizontal",command=tree.xview); tree.configure(yscrollcommand=ybar.set,xscrollcommand=xbar.set)
        tree.grid(row=0,column=0,sticky="nsew"); ybar.grid(row=0,column=1,sticky="ns"); xbar.grid(row=1,column=0,sticky="ew"); table_frame.rowconfigure(0,weight=1); table_frame.columnconfigure(0,weight=1)
        def populate_hourly(*_):
            tree.delete(*tree.get_children()); m=int(month_var.get()); mm=h[h["datetime"].dt.month==m]
            for _,r in mm.iterrows():
                dt=pd.Timestamp(r["datetime"])
                vals=[dt.strftime("%m/%d %H:%M"),r.get("outdoor_C",0),r.get("zone_air_C",0),r.get("ground_C",0),r.get("ghi_Wm2",0),r.get("opaque_roof_solar_kWh",0),r.get("direct_envelope_kWh",0),r.get("rc_wall_to_zone_kWh",0),r.get("slab_to_zone_kWh",0),r.get("ground_to_slab_kWh",0),r.get("window_solar_total_kWh",0),r.get("ventilation_kWh",0),r.get("internal_gain_kWh",0),r.get("heating_load_kWh",0),r.get("cooling_load_kWh",0)]
                tree.insert("","end",values=(vals[0],)+tuple(f"{float(v or 0):.4f}" for v in vals[1:]))
        cb.bind("<<ComboboxSelected>>",populate_hourly); populate_hourly()

        buttons=ttk.Frame(outer); buttons.pack(fill="x",pady=(8,0))
        def save_diag_csv():
            if self.project_path is None:
                return
            import csv
            from datetime import datetime, timezone
            project_dir = Path(self.project_path).resolve().parent
            out_dir = project_dir / "8760_Results"
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%y%m%d_%H%M")
            project_name = Path(self.project_path).stem
            default_name = f"{stamp}_AZRAS_ANNUAL_THERMAL_BALANCE_{project_name}.csv"
            path=filedialog.asksaveasfilename(
                parent=win, initialdir=out_dir, initialfile=default_name,
                defaultextension=".csv", filetypes=[("CSV","*.csv")]
            )
            if not path:
                return

            mode_map = {
                "暖冷房併存": "暖冷房併存 / Mixed", "Mixed": "暖冷房併存 / Mixed",
                "暖房": "暖房 / Heating", "Heating": "暖房 / Heating",
                "冷房": "冷房 / Cooling", "Cooling": "冷房 / Cooling",
                "中間期": "中間期 / Neutral", "Neutral": "中間期 / Neutral",
            }
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["年間熱収支詳細 / Annual Thermal Balance Details"])
                w.writerow(["Project / プロジェクト", project_name])
                w.writerow([])
                w.writerow(["1～12月 熱収支・暖冷房判定 / Jan-Dec Heat Balance and HVAC Classification"])
                w.writerow([
                    "月 / Month", "判定 / Mode",
                    "暖房負荷 kWh / Heating Load kWh", "冷房負荷 kWh / Cooling Load kWh",
                    "窓日射 kWh / Window Solar kWh", "屋根吸収日射 kWh / Roof Solar kWh",
                    "内部発熱 kWh / Internal Gain kWh", "換気 kWh / Ventilation kWh",
                    "外皮直接熱 kWh / Direct Envelope kWh", "RC壁→室 kWh / RC Wall to Zone kWh",
                    "床→室 kWh / Slab to Zone kWh", "地盤→床 kWh / Ground to Slab kWh",
                ])
                for m in range(1,13):
                    mm=h[h["datetime"].dt.month==m]
                    heat=msum(mm,"heating_load_kWh"); cool=msum(mm,"cooling_load_kWh")
                    mode = mode_map.get(classify(heat,cool), classify(heat,cool))
                    w.writerow([
                        m, mode, heat, cool,
                        msum(mm,"window_solar_total_kWh"), msum(mm,"opaque_roof_solar_kWh"),
                        msum(mm,"internal_gain_kWh"), msum(mm,"ventilation_kWh"),
                        msum(mm,"direct_envelope_kWh"), msum(mm,"rc_wall_to_zone_kWh"),
                        msum(mm,"slab_to_zone_kWh"), msum(mm,"ground_to_slab_kWh"),
                    ])

                w.writerow([])
                w.writerow(["8760時間詳細 / 8760-Hour Details"])
                hourly_headers = [
                    ("datetime", "日時 / Datetime"),
                    ("outdoor_C", "外気温 °C / Outdoor °C"),
                    ("zone_air_C", "室温 °C / Zone Air °C"),
                    ("ground_C", "地盤温度 °C / Ground °C"),
                    ("ghi_Wm2", "日射 W/m² / GHI W/m²"),
                    ("opaque_roof_solar_kWh", "屋根吸収日射 kWh / Roof Solar kWh"),
                    ("direct_envelope_kWh", "外皮直接熱 kWh / Direct Envelope kWh"),
                    ("rc_wall_to_zone_kWh", "RC壁→室 kWh / RC Wall to Zone kWh"),
                    ("slab_to_zone_kWh", "床→室 kWh / Slab to Zone kWh"),
                    ("ground_to_slab_kWh", "地盤→床 kWh / Ground to Slab kWh"),
                    ("window_solar_total_kWh", "窓日射 kWh / Window Solar kWh"),
                    ("ventilation_kWh", "換気 kWh / Ventilation kWh"),
                    ("internal_gain_kWh", "内部発熱 kWh / Internal Gain kWh"),
                    ("heating_load_kWh", "暖房負荷 kWh / Heating Load kWh"),
                    ("cooling_load_kWh", "冷房負荷 kWh / Cooling Load kWh"),
                ]
                hourly_headers = [(k, lab) for k, lab in hourly_headers if k in h.columns]
                w.writerow([lab for _, lab in hourly_headers])
                for _, r in h.iterrows():
                    vals=[]
                    for k,_lab in hourly_headers:
                        v=r.get(k, "")
                        if k == "datetime":
                            try:
                                v = pd.Timestamp(v).strftime("%Y-%m-%d %H:%M")
                            except Exception:
                                v = str(v)
                        vals.append(v)
                    w.writerow(vals)
            messagebox.showinfo(
                "Saved",
                (("日英併記CSVを保存しました。\n" if self.i18n.language == "ja" else "Saved bilingual Japanese/English CSV.\n") + str(path)),
                parent=win,
            )
        # PATCH_524: Save button moved to the control row above the hourly table
        # so it remains visible regardless of window height/tree requested size.

    def save_output(self):
        self.refresh_project_from_context()
        if self.project is None or self.project_path is None or self.summary is None:
            messagebox.showwarning("Warning", self.i18n.t("save_conditions_missing"))
            return
        try:
            report = update_module_and_propagate(
                self.project,
                self.project_path,
                "module2",
                self.summary,
                {
    "weather_file": self.weather_file.get(),
    "country": self.project_country.get(),
    "weather_choice": self.weather_choice.get(),
    "weather_source_url": self.weather_source_url.get(),
    "weather_selection_method": "nearest_to_project_coordinates",
    "settings": self.settings(),
    "pv": self.pv_settings(),
    "ui_language": self.i18n.language,
    "language": self.i18n.language,
    "canonical_language": "en",
    "canonical_schema_version": "2.6",
},
                self.root_dir,
            )
            if self.project_context is not None:
                self.project_context.set(self.project_path, self.project)
            messagebox.showinfo(
                self.i18n.t("saved"),
                format_report(report, self.i18n.language),
            )
        except Exception as exc:
            messagebox.showerror("Error", friendly_exception_text(exc,self.i18n.language))
