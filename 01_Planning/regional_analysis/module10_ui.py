from __future__ import annotations
import re

import json
import math
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from core.ui_style import fit_window_to_screen
from typing import Any

from batch_analysis.engine import _epw_climate
from core.project_coordinator import module_output_is_current
from regional_analysis.hourly_comparison_engine import calculate_hourly_snapshot


MONTHS_JA = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LINE_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2"]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    """Read JSON booleans without treating the string 'false' as True."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on", "有", "あり"}:
        return True
    if text in {"false", "0", "no", "off", "無", "なし", ""}:
        return False
    return default


def _recursive_find_text(obj: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key]:
                return str(obj[key])
        for value in obj.values():
            found = _recursive_find_text(value, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _recursive_find_text(value, keys)
            if found:
                return found
    return None


def _recursive_find(obj: Any, keys: tuple[str, ...]) -> float | None:
    if isinstance(obj, dict):
        for key in keys:
            if key in obj:
                try:
                    return float(obj[key])
                except (TypeError, ValueError):
                    pass
        for value in obj.values():
            found = _recursive_find(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _recursive_find(value, keys)
            if found is not None:
                return found
    return None


def _normalised(values: list[float]) -> list[float]:
    total = sum(values)
    return [v / total for v in values] if total > 0 else [0.0] * len(values)




def _monthly_temperature_profile(annual_mean: float, climate_zone: str = "", latitude: float = 35.0, city: str = "") -> list[dict[str, float]]:
    """Create transparent monthly planning temperatures.

    Values are monthly mean / mean daily high / mean daily low estimates used
    only for the regional planning table. Formal design must read the selected
    EPW or another verified local weather file.
    """
    zone = str(climate_zone or "").lower()
    city_key = str(city or "").strip().lower()

    # Seasonal amplitude of monthly mean temperature and typical half daily range.
    seasonal_amp = 10.0
    half_daily_range = 5.0
    if "tropical" in zone:
        seasonal_amp, half_daily_range = 1.8, 3.5
    elif "hot_arid" in zone or "semi_arid" in zone:
        seasonal_amp, half_daily_range = 8.5, 7.0
    elif "marine" in zone:
        seasonal_amp, half_daily_range = 6.5, 4.0
    elif "mediterranean" in zone:
        seasonal_amp, half_daily_range = 8.5, 5.5
    elif "cold" in zone or "snow" in zone:
        seasonal_amp, half_daily_range = 14.0, 5.5
    elif "continental" in zone:
        seasonal_amp, half_daily_range = 13.0, 5.5
    elif "subtropical" in zone:
        seasonal_amp, half_daily_range = 9.0, 5.0

    # Registered-city refinements. These remain planning estimates, not EPW values.
    if city_key in {"sapporo", "札幌", "札幌市"}:
        seasonal_amp, half_daily_range = 14.0, 5.0
    elif city_key in {"london", "ロンドン"}:
        seasonal_amp, half_daily_range = 6.5, 4.0
    elif city_key in {"new york", "ニューヨーク"}:
        seasonal_amp, half_daily_range = 13.0, 5.5
    elif city_key in {"dubai", "ドバイ"}:
        seasonal_amp, half_daily_range = 8.5, 6.0
    elif city_key in {"singapore", "シンガポール"}:
        seasonal_amp, half_daily_range = 1.2, 3.5
    elif city_key in {"delhi", "デリー"}:
        seasonal_amp, half_daily_range = 10.5, 6.5
    elif city_key in {"sydney", "シドニー"}:
        seasonal_amp, half_daily_range = 5.8, 4.5
    elif city_key in {"nagoya", "kasugai", "春日井", "春日井市", "名古屋", "名古屋市"}:
        seasonal_amp, half_daily_range = 11.0, 5.0

    # Northern hemisphere peaks around July; southern hemisphere around January.
    peak_month = 6 if latitude >= 0 else 0
    profile = []
    for month_index in range(12):
        angle = 2.0 * math.pi * (month_index - peak_month) / 12.0
        mean_c = annual_mean + seasonal_amp * math.cos(angle)
        profile.append({
            "mean_C": round(mean_c, 1),
            "mean_high_C": round(mean_c + half_daily_range, 1),
            "mean_low_C": round(mean_c - half_daily_range, 1),
        })
    return profile

def _monthly_profile(annual_heating: float, annual_cooling: float, annual_pv: float, base_load: float, climate_zone: str = "", latitude: float = 35.0) -> list[dict[str, float]]:
    zone = str(climate_zone or "").lower()
    # Northern-hemisphere default profiles. Heating and cooling are annual
    # Module 2 loads, so the drawing-derived insulation and RC thermal storage
    # remain embedded; only their monthly climate distribution changes here.
    heating_weights = [0.19, 0.17, 0.13, 0.07, 0.02, 0.0, 0.0, 0.0, 0.01, 0.06, 0.14, 0.21]
    cooling_weights = [0.0, 0.0, 0.0, 0.01, 0.05, 0.14, 0.24, 0.25, 0.18, 0.09, 0.03, 0.01]
    pv_weights = [0.055, 0.065, 0.085, 0.095, 0.105, 0.11, 0.115, 0.11, 0.095, 0.075, 0.05, 0.04]

    if "hot_arid" in zone:
        heating_weights = [0.30, 0.22, 0.12, 0.04, 0.0, 0.0, 0.0, 0.0, 0.0, 0.02, 0.10, 0.20]
        cooling_weights = [0.045, 0.045, 0.055, 0.075, 0.105, 0.125, 0.135, 0.135, 0.115, 0.085, 0.045, 0.035]
    elif "tropical" in zone:
        heating_weights = [0.0] * 12
        cooling_weights = [0.078, 0.077, 0.081, 0.084, 0.087, 0.087, 0.086, 0.086, 0.085, 0.084, 0.083, 0.082]
    elif "cold" in zone or "snow" in zone:
        heating_weights = [0.205, 0.185, 0.145, 0.085, 0.025, 0.0, 0.0, 0.0, 0.005, 0.055, 0.125, 0.175]
        cooling_weights = [0.0, 0.0, 0.0, 0.0, 0.02, 0.12, 0.30, 0.31, 0.17, 0.06, 0.0, 0.0]

    heating_weights = _normalised(heating_weights)
    cooling_weights = _normalised(cooling_weights)
    pv_weights = _normalised(pv_weights)

    # Reverse seasons for southern-hemisphere cities such as Sydney.
    if latitude < 0:
        heating_weights = heating_weights[6:] + heating_weights[:6]
        cooling_weights = cooling_weights[6:] + cooling_weights[:6]
        pv_weights = pv_weights[6:] + pv_weights[:6]

    monthly_base = base_load / 12.0
    rows = []
    for i in range(12):
        heating = annual_heating * heating_weights[i]
        cooling = annual_cooling * cooling_weights[i]
        use = monthly_base + heating + cooling
        pv = annual_pv * pv_weights[i]
        rows.append({
            "use": use,
            "pv": pv,
            "net": use - pv,
            "heating": heating,
            "cooling": cooling,
        })
    return rows



# PATCH_278 — Module 10 English-canonical comparison contract.
_M10_JP_RE = re.compile(r"[ぁ-んァ-ヶ一-龯々〆ヵヶ]")

def _m10_canonical_reason(value):
    """Prevent legacy source-language status/reason text from entering Module 10 logic."""
    text = "" if value is None else str(value)
    if not text or _M10_JP_RE.search(text):
        return "Module 1 orientation-specific exterior-wall/window data is unresolved."
    return text


class LineChart(tk.Canvas):
    HOVER_DISTANCE_PX = 12

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._hover_points: list[dict[str, Any]] = []
        self._hover_tip_id: int | None = None
        self._hover_bg_id: int | None = None
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _event: self._hide_hover())

    def _hide_hover(self):
        if self._hover_tip_id is not None:
            self.delete(self._hover_tip_id)
            self._hover_tip_id = None
        if self._hover_bg_id is not None:
            self.delete(self._hover_bg_id)
            self._hover_bg_id = None

    def _on_motion(self, event):
        if not self._hover_points:
            self._hide_hover()
            return

        nearest = min(
            self._hover_points,
            key=lambda point: (point["x"] - event.x) ** 2 + (point["y"] - event.y) ** 2,
        )
        distance_sq = (nearest["x"] - event.x) ** 2 + (nearest["y"] - event.y) ** 2
        if distance_sq > self.HOVER_DISTANCE_PX ** 2:
            self._hide_hover()
            return

        self._hide_hover()
        label = f'{nearest["name"]}  {nearest["x_label"]}  {nearest["value"]:,.1f}'
        text_x = min(max(event.x + 14, 8), max(self.winfo_width() - 220, 8))
        text_y = max(event.y - 24, 8)
        self._hover_tip_id = self.create_text(
            text_x + 7,
            text_y + 5,
            text=label,
            anchor="nw",
            font=("Yu Gothic UI", 9, "bold"),
            fill="#111111",
        )
        bbox = self.bbox(self._hover_tip_id)
        if bbox:
            self._hover_bg_id = self.create_rectangle(
                bbox[0] - 5,
                bbox[1] - 3,
                bbox[2] + 5,
                bbox[3] + 3,
                fill="#fffde7",
                outline="#666666",
            )
            self.tag_raise(self._hover_tip_id, self._hover_bg_id)

    def draw(self, x_labels: list[str], series: list[tuple[str, list[float]]], y_title: str, title: str):
        self.delete("all")
        self._hover_points = []
        self._hover_tip_id = None
        self._hover_bg_id = None
        self.update_idletasks()
        width = max(self.winfo_width(), 720)
        height = max(self.winfo_height(), 420)

        # Reserve a dedicated legend band below the x-axis labels.  Previously
        # the legend was anchored to the bottom edge while the plot used a
        # fixed 65 px bottom margin, so 2+ legend rows overlapped month/year
        # tick labels.  Size the reserved band from the actual series count.
        legend_columns = 4
        legend_rows = max(1, math.ceil(len(series) / legend_columns))
        legend_row_h = 20
        legend_gap = 18
        left, right, top = 85, 30, 52
        bottom = 65 + legend_gap + legend_rows * legend_row_h
        plot_w = width - left - right
        plot_h = max(80, height - top - bottom)
        values = [v for _, data in series for v in data]
        if not values:
            self.create_text(width / 2, height / 2, text="No data")
            return
        ymin = min(0.0, min(values))
        ymax = max(values)
        if math.isclose(ymax, ymin):
            ymax = ymin + 1.0
        pad = (ymax - ymin) * 0.08
        ymax += pad
        ymin -= pad

        self.create_text(width / 2, 22, text=title, font=("Yu Gothic UI", 13, "bold"))
        self.create_text(18, top + plot_h / 2, text=y_title, angle=90, font=("Yu Gothic UI", 9))

        for level in range(6):
            ratio = level / 5
            y = top + plot_h * ratio
            value = ymax - (ymax - ymin) * ratio
            self.create_line(left, y, left + plot_w, y, fill="#dddddd")
            self.create_text(left - 8, y, text=f"{value:,.0f}", anchor="e", font=("Yu Gothic UI", 8))

        count = max(len(x_labels), 1)
        for i, label in enumerate(x_labels):
            x = left + (plot_w * i / max(count - 1, 1))
            self.create_line(x, top, x, top + plot_h, fill="#eeeeee")
            self.create_text(x, top + plot_h + 18, text=label, font=("Yu Gothic UI", 8))

        for idx, (name, data) in enumerate(series):
            color = LINE_COLORS[idx % len(LINE_COLORS)]
            points = []
            for i, value in enumerate(data):
                x = left + (plot_w * i / max(len(data) - 1, 1))
                y = top + (ymax - value) / (ymax - ymin) * plot_h
                points.extend([x, y])
                self._hover_points.append({
                    "x": x,
                    "y": y,
                    "name": name,
                    "x_label": x_labels[i] if i < len(x_labels) else str(i + 1),
                    "value": float(value),
                })
                self.create_oval(x - 2.5, y - 2.5, x + 2.5, y + 2.5, fill=color, outline=color)
            if len(points) >= 4:
                self.create_line(points, fill=color, width=2)
            legend_col = idx % legend_columns
            legend_row = idx // legend_columns
            legend_x = left + 10 + legend_col * max(150, (plot_w - 20) / legend_columns)
            legend_y = top + plot_h + 18 + legend_gap + legend_row * legend_row_h
            self.create_line(legend_x, legend_y, legend_x + 24, legend_y, fill=color, width=3)
            self.create_text(legend_x + 30, legend_y, text=name, anchor="w", font=("Yu Gothic UI", 8))


class BarChart(tk.Canvas):
    def draw(self, labels: list[str], values: list[float], y_title: str, title: str):
        self.delete("all")
        self.update_idletasks()
        width = max(self.winfo_width(), 720)
        height = max(self.winfo_height(), 420)
        left, right, top, bottom = 90, 35, 55, 95
        plot_w = max(1, width - left - right)
        plot_h = max(1, height - top - bottom)
        self.create_text(width / 2, 22, text=title, font=("Yu Gothic UI", 13, "bold"))
        self.create_text(20, top + plot_h / 2, text=y_title, angle=90, font=("Yu Gothic UI", 9))
        if not labels or not values:
            self.create_text(width / 2, height / 2, text="No data")
            return
        vmax = max(max(values), 0.0)
        if vmax <= 0:
            vmax = 1.0
        for i in range(6):
            value = vmax * i / 5
            y = top + plot_h - plot_h * i / 5
            self.create_line(left, y, width - right, y, fill="#dddddd")
            self.create_text(left - 8, y, text=f"{value:,.2f}", anchor="e", font=("Yu Gothic UI", 8))
        count = len(labels)
        slot = plot_w / max(count, 1)
        bar_w = min(70, slot * 0.62)
        for i, (label, value) in enumerate(zip(labels, values)):
            x = left + slot * (i + 0.5)
            y = top + plot_h - (max(value, 0.0) / vmax) * plot_h
            self.create_rectangle(x - bar_w / 2, y, x + bar_w / 2, top + plot_h, fill="#4e79a7", outline="#2f4f6f")
            self.create_text(x, y - 8, text=f"{value:,.3f}", anchor="s", font=("Yu Gothic UI", 8, "bold"))
            self.create_text(x, top + plot_h + 10, text=label, anchor="n", width=max(70, int(slot - 4)), font=("Yu Gothic UI", 8))
        self.create_line(left, top, left, top + plot_h, width=1)
        self.create_line(left, top + plot_h, width - right, top + plot_h, width=1)


class RegionalComparisonApp(tk.Toplevel):
    def __init__(self, master, root_dir: Path, language="ja", project_context=None):
        super().__init__(master)
        self.language = language
        self.project_context = project_context
        self.projects: list[dict[str, Any]] = []
        self.hourly_cache: dict[str, Any] = {}
        self.hourly_rows: list[dict[str, Any]] = []
        self.title(self.t("同一工法・地域差比較", "Same Method: Regional Comparison"))
        fit_window_to_screen(self,1480,900,820,520)
        self.build()
        self.load_generated_projects()

    def t(self, ja, en):
        return ja if self.language == "ja" else en

    def _apply_global_language(self, language):
        self.language = "ja" if language == "ja" else "en"
        self.title(self.t("同一工法・地域差比較", "Same Method: Regional Comparison"))
        for child in list(self.winfo_children()):
            if isinstance(child, tk.Toplevel):
                continue
            child.destroy()
        self.build()
        self.load_generated_projects()

    def build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=6)
        ttk.Button(top, text=self.t("地域別Project JSONを再読込", "Reload Regional Project JSONs"), command=self.load_generated_projects).pack(side="right")
        self.folder_var = tk.StringVar(value="")
        ttk.Label(top, text=self.t("読込元：", "Source folder:")) .pack(side="left")
        ttk.Label(top, textvariable=self.folder_var, wraplength=900).pack(side="left", padx=5)

        ttk.Label(
            self,
            text=self.t(
                "同一工法について地域差を比較します。比較対象はPV自家消費を反映した月別買電量と、50年・100年・150年・200年の運用CO₂および累積CO₂です。年間差引（使用量－PV）と売電量は表で確認できます。法規・災害・材料施工性等の採点は行いません。",
                "Compares regional differences for the same construction method. It shows monthly grid import after PV self-consumption, plus operational and cumulative CO₂ at 50, 100, 150 and 200 years. Annual net energy and grid export remain available in the tables. No legal, hazard or availability scoring is used.",
            ),
            foreground="#8b0000",
            wraplength=1420,
        ).pack(fill="x", padx=12, pady=(0, 6))

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=5)
        self.energy_tab = ttk.Frame(self.tabs)
        self.co2_operational_tab = ttk.Frame(self.tabs)
        self.co2_tab = ttk.Frame(self.tabs)
        self.hourly_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.energy_tab, text=self.t("月別エネルギー地域比較", "Monthly Energy by Region"))
        self.tabs.add(self.hourly_tab, text=self.t("指定日時・地域別グラフ", "Selected Hour by Region"))
        self.tabs.add(self.co2_operational_tab, text=self.t("運用CO₂地域比較", "Operational CO₂ by Region"))
        self.tabs.add(self.co2_tab, text=self.t("累積CO₂地域比較", "Cumulative CO₂ by Region"))

        # The energy graph and the result tables are separated by a movable
        # horizontal sash.  Dragging the sash upward enlarges the tables;
        # dragging it downward enlarges the graph.
        self.energy_pane = ttk.Panedwindow(self.energy_tab, orient=tk.VERTICAL)
        self.energy_pane.pack(fill="both", expand=True, padx=4, pady=4)

        self.energy_chart_frame = ttk.Frame(self.energy_pane)
        self.energy_table_area = ttk.Frame(self.energy_pane)
        self.energy_pane.add(self.energy_chart_frame, weight=3)
        self.energy_pane.add(self.energy_table_area, weight=2)

        self.energy_chart = LineChart(self.energy_chart_frame, bg="white", highlightthickness=1, highlightbackground="#cccccc")
        self.energy_chart.pack(fill="both", expand=True)
        self.energy_tables = ttk.Notebook(self.energy_table_area)
        self.energy_tables.pack(fill="both", expand=True)
        self.annual_table_frame = ttk.Frame(self.energy_tables)
        self.monthly_table_frame = ttk.Frame(self.energy_tables)
        self.pv_table_frame = ttk.Frame(self.energy_tables)
        self.epw_table_frame = ttk.Frame(self.energy_tables)
        self.energy_tables.add(self.annual_table_frame, text=self.t("年間概要", "Annual Summary"))
        self.energy_tables.add(self.monthly_table_frame, text=self.t("月別暖房・冷房", "Monthly Heating/Cooling"))
        self.energy_tables.add(self.pv_table_frame, text=self.t("月別PV発電", "Monthly PV Generation"))
        self.energy_tables.add(self.epw_table_frame, text=self.t("EPW気象データ A", "EPW Weather Data A"))

        # Start with the original balanced graph/table split.  A single
        # after_idle callback can run before Windows has assigned a real height,
        # which collapses the graph.  Retry after layout completion.
        self.after_idle(lambda: self._set_initial_energy_sash(0))
        self.after(150, lambda: self._set_initial_energy_sash(1))
        self.after(400, lambda: self._set_initial_energy_sash(2))

        self.energy_tree = ttk.Treeview(self.annual_table_frame, columns=("region", "use", "pv", "purchase", "export", "net", "heating", "cooling"), show="headings", height=7)
        for key, label, width in [
            ("region", self.t("地域", "Region"), 180),
            ("use", self.t("年間使用量 kWh", "Annual use kWh"), 150),
            ("pv", self.t("年間PV kWh", "Annual PV kWh"), 135),
            ("purchase", self.t("年間買電 kWh", "Annual grid import kWh"), 145),
            ("export", self.t("年間売電 kWh", "Annual grid export kWh"), 145),
            ("net", self.t("年間差引 kWh", "Annual net kWh"), 140),
            ("heating", self.t("年間暖房 kWh", "Annual heating kWh"), 150),
            ("cooling", self.t("年間冷房 kWh", "Annual cooling kWh"), 150),
        ]:
            self.energy_tree.heading(key, text=label)
            self.energy_tree.column(key, width=width, anchor="center")
        self.energy_tree.pack(fill="x")

        monthly_wrap = ttk.Frame(self.monthly_table_frame)
        monthly_wrap.pack(fill="both", expand=True)
        self.monthly_tree = ttk.Treeview(monthly_wrap, columns=("region", "month", "temp_mean", "temp_high", "temp_low", "heating", "cooling", "use", "pv", "grid_import", "grid_export", "net"), show="headings", height=10)
        for key, label, width in [
            ("region", self.t("地域", "Region"), 150),
            ("month", self.t("月", "Month"), 65),
            ("temp_mean", self.t("平均気温 ℃", "Mean temp °C"), 110),
            ("temp_high", self.t("平均最高 ℃", "Mean high °C"), 110),
            ("temp_low", self.t("平均最低 ℃", "Mean low °C"), 110),
            ("heating", self.t("暖房 kWh/月", "Heating kWh/month"), 135),
            ("cooling", self.t("冷房 kWh/月", "Cooling kWh/month"), 150),
            ("use", self.t("使用量 kWh/月", "Use kWh/month"), 150),
            ("pv", self.t("PV kWh/月", "PV kWh/month"), 120),
            ("grid_import", self.t("買電 kWh/月", "Grid import kWh/month"), 130),
            ("grid_export", self.t("売電 kWh/月", "Grid export kWh/month"), 130),
            ("net", self.t("差引 kWh/月", "Net kWh/month"), 125),
        ]:
            self.monthly_tree.heading(key, text=label)
            self.monthly_tree.column(key, width=width, anchor="center")
        monthly_scroll = ttk.Scrollbar(monthly_wrap, orient="vertical", command=self.monthly_tree.yview)
        self.monthly_tree.configure(yscrollcommand=monthly_scroll.set)
        self.monthly_tree.pack(side="left", fill="both", expand=True)
        monthly_scroll.pack(side="right", fill="y")

        pv_wrap = ttk.Frame(self.pv_table_frame)
        pv_wrap.pack(fill="both", expand=True)
        self.pv_monthly_tree = ttk.Treeview(
            pv_wrap,
            columns=("region", "month", "pv"),
            show="headings",
            height=12,
        )
        for key, label, width in [
            ("region", self.t("地域", "Region"), 220),
            ("month", self.t("月", "Month"), 100),
            ("pv", self.t("PV月間発電量 kWh/月", "Monthly PV generation kWh/month"), 240),
        ]:
            self.pv_monthly_tree.heading(key, text=label)
            self.pv_monthly_tree.column(key, width=width, anchor="center")
        pv_y = ttk.Scrollbar(pv_wrap, orient="vertical", command=self.pv_monthly_tree.yview)
        self.pv_monthly_tree.configure(yscrollcommand=pv_y.set)
        self.pv_monthly_tree.pack(side="left", fill="both", expand=True)
        pv_y.pack(side="right", fill="y")

        epw_wrap = ttk.Frame(self.epw_table_frame)
        epw_wrap.pack(fill="both", expand=True)
        epw_columns = ("region", "month", "rh", "dew", "wind", "wind_dir", "ghi", "dni", "dhi", "hir", "sky", "opaque", "hdd", "cdd")
        self.epw_tree = ttk.Treeview(epw_wrap, columns=epw_columns, show="headings", height=10)
        for key, label, width in [
            ("region", self.t("地域", "Region"), 145),
            ("month", self.t("月", "Month"), 55),
            ("rh", self.t("相対湿度 %", "RH %"), 90),
            ("dew", self.t("露点 ℃", "Dew point °C"), 90),
            ("wind", self.t("風速 m/s", "Wind m/s"), 85),
            ("wind_dir", self.t("卓越風向 °", "Wind dir °"), 90),
            ("ghi", self.t("GHI kWh/m²", "GHI kWh/m²"), 100),
            ("dni", self.t("DNI kWh/m²", "DNI kWh/m²"), 100),
            ("dhi", self.t("DHI kWh/m²", "DHI kWh/m²"), 100),
            ("hir", self.t("水平面赤外 W/m²", "Horiz. IR W/m²"), 120),
            ("sky", self.t("全雲量 0-10", "Total sky 0-10"), 105),
            ("opaque", self.t("不透明雲量 0-10", "Opaque sky 0-10"), 120),
            ("hdd", self.t("HDD18 ℃日", "HDD18 °C-day"), 100),
            ("cdd", self.t("CDD24 ℃日", "CDD24 °C-day"), 100),
        ]:
            self.epw_tree.heading(key, text=label)
            self.epw_tree.column(key, width=width, anchor="center")
        epw_x = ttk.Scrollbar(epw_wrap, orient="horizontal", command=self.epw_tree.xview)
        epw_y = ttk.Scrollbar(epw_wrap, orient="vertical", command=self.epw_tree.yview)
        self.epw_tree.configure(xscrollcommand=epw_x.set, yscrollcommand=epw_y.set)
        self.epw_tree.grid(row=0, column=0, sticky="nsew")
        epw_y.grid(row=0, column=1, sticky="ns")
        epw_x.grid(row=1, column=0, sticky="ew")
        epw_wrap.rowconfigure(0, weight=1)
        epw_wrap.columnconfigure(0, weight=1)


        hourly_controls = ttk.LabelFrame(
            self.hourly_tab,
            text=self.t("日時と表示指標", "Date, time and chart metric"),
            padding=8,
        )
        hourly_controls.pack(fill="x", padx=6, pady=6)
        self.hour_month = tk.IntVar(value=8)
        self.hour_day = tk.IntVar(value=1)
        self.hour_hour = tk.IntVar(value=13)
        ttk.Label(hourly_controls, text=self.t("月", "Month")).pack(side="left")
        ttk.Spinbox(hourly_controls, from_=1, to=12, width=5, textvariable=self.hour_month).pack(side="left", padx=(3, 10))
        ttk.Label(hourly_controls, text=self.t("日", "Day")).pack(side="left")
        ttk.Spinbox(hourly_controls, from_=1, to=31, width=5, textvariable=self.hour_day).pack(side="left", padx=(3, 10))
        ttk.Label(hourly_controls, text=self.t("時", "Hour")).pack(side="left")
        ttk.Spinbox(hourly_controls, from_=0, to=23, width=5, textvariable=self.hour_hour).pack(side="left", padx=(3, 14))

        self.hourly_metric_labels = {
            self.t("外気温 ℃", "Outdoor temperature °C"): ("outdoor_C", self.t("外気温 ℃", "Outdoor temperature °C")),
            self.t("GHI日射 W/m²", "GHI W/m²"): ("ghi_Wm2", self.t("GHI W/m²", "GHI W/m²")),
            self.t("暖房電力量 kWh", "Heating electricity kWh"): ("heating_electricity_kWh", self.t("暖房電力量 kWh", "Heating electricity kWh")),
            self.t("冷房電力量 kWh", "Cooling electricity kWh"): ("cooling_electricity_kWh", self.t("冷房電力量 kWh", "Cooling electricity kWh")),
            self.t("総使用電力量 kWh", "Total electricity use kWh"): ("total_use_kWh", self.t("総使用電力量 kWh", "Total electricity use kWh")),
            self.t("PV発電量 kWh", "PV generation kWh"): ("pv_generation_kWh", self.t("PV発電量 kWh", "PV generation kWh")),
            self.t("買電量 kWh", "Grid import kWh"): ("grid_import_kWh", self.t("買電量 kWh", "Grid import kWh")),
            self.t("売電量 kWh", "Grid export kWh"): ("grid_export_kWh", self.t("売電量 kWh", "Grid export kWh")),
        }
        self.hourly_metric = tk.StringVar(value=list(self.hourly_metric_labels)[0])
        ttk.Combobox(
            hourly_controls, textvariable=self.hourly_metric,
            values=list(self.hourly_metric_labels), state="readonly", width=27,
        ).pack(side="left", padx=(0, 10))
        ttk.Button(hourly_controls, text=self.t("全地域を計算・グラフ表示", "Calculate all regions and draw"), command=self.calculate_selected_hour).pack(side="left", padx=4)
        ttk.Button(hourly_controls, text=self.t("CSV保存", "Save CSV"), command=self.save_hourly_csv).pack(side="left", padx=4)
        self.hourly_status = tk.StringVar(value=self.t("日時を指定して計算してください。", "Select a date and hour, then calculate."))
        ttk.Label(hourly_controls, textvariable=self.hourly_status, foreground="#555555").pack(side="left", padx=10)

        hourly_pane = ttk.Panedwindow(self.hourly_tab, orient=tk.VERTICAL)
        hourly_pane.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        chart_frame = ttk.Frame(hourly_pane)
        table_frame = ttk.Frame(hourly_pane)
        hourly_pane.add(chart_frame, weight=3)
        hourly_pane.add(table_frame, weight=2)
        self.hourly_chart = BarChart(chart_frame, bg="white", highlightthickness=1, highlightbackground="#cccccc")
        self.hourly_chart.pack(fill="both", expand=True)
        hourly_columns = ("region", "datetime", "outdoor", "ghi", "dni", "dhi", "heating", "cooling", "other", "use", "pv", "import", "export")
        self.hourly_tree = ttk.Treeview(table_frame, columns=hourly_columns, show="headings", height=9)
        for key, label, width in [
            ("region", self.t("地域", "Region"), 145), ("datetime", self.t("日時", "Date/time"), 120),
            ("outdoor", self.t("外気温 ℃", "Outdoor °C"), 90), ("ghi", "GHI W/m²", 90),
            ("dni", "DNI W/m²", 90), ("dhi", "DHI W/m²", 90),
            ("heating", self.t("暖房 kWh", "Heating kWh"), 95), ("cooling", self.t("冷房 kWh", "Cooling kWh"), 95),
            ("other", self.t("その他 kWh", "Other kWh"), 95), ("use", self.t("使用量 kWh", "Use kWh"), 95),
            ("pv", self.t("PV kWh", "PV kWh"), 90), ("import", self.t("買電 kWh", "Import kWh"), 90),
            ("export", self.t("売電 kWh", "Export kWh"), 90),
        ]:
            self.hourly_tree.heading(key, text=label)
            self.hourly_tree.column(key, width=width, anchor="center")
        hx = ttk.Scrollbar(table_frame, orient="horizontal", command=self.hourly_tree.xview)
        hy = ttk.Scrollbar(table_frame, orient="vertical", command=self.hourly_tree.yview)
        self.hourly_tree.configure(xscrollcommand=hx.set, yscrollcommand=hy.set)
        self.hourly_tree.grid(row=0, column=0, sticky="nsew")
        hy.grid(row=0, column=1, sticky="ns")
        hx.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)


        self.co2_operational_chart = LineChart(self.co2_operational_tab, bg="white", highlightthickness=1, highlightbackground="#cccccc")
        self.co2_operational_chart.pack(fill="both", expand=True, padx=4, pady=4)
        self.co2_operational_tree = ttk.Treeview(
            self.co2_operational_tab,
            columns=("region", "annual", "y50", "y100", "y150", "y200", "factor"),
            show="headings",
            height=7,
        )
        for key, label, width in [
            ("region", self.t("地域", "Region"), 180),
            ("annual", self.t("年間運用CO₂ kg", "Annual operational CO₂ kg"), 175),
            ("y50", self.t("50年 kg", "50 years kg"), 140),
            ("y100", self.t("100年 kg", "100 years kg"), 140),
            ("y150", self.t("150年 kg", "150 years kg"), 140),
            ("y200", self.t("200年 kg", "200 years kg"), 140),
            ("factor", self.t("電力係数 kg-CO₂/kWh", "Grid factor kg-CO₂/kWh"), 190),
        ]:
            self.co2_operational_tree.heading(key, text=label)
            self.co2_operational_tree.column(key, width=width, anchor="center")
        self.co2_operational_tree.pack(fill="x", padx=4, pady=(0, 4))

        self.co2_chart = LineChart(self.co2_tab, bg="white", highlightthickness=1, highlightbackground="#cccccc")
        self.co2_chart.pack(fill="both", expand=True, padx=4, pady=4)
        self.co2_tree = ttk.Treeview(self.co2_tab, columns=("region", "initial", "y50", "y100", "y150", "y200", "factor"), show="headings", height=7)
        for key, label, width in [
            ("region", self.t("地域", "Region"), 180),
            ("initial", self.t("建設時CO₂ kg", "Initial CO₂ kg"), 160),
            ("y50", self.t("50年 kg", "50 years kg"), 150),
            ("y100", self.t("100年 kg", "100 years kg"), 150),
            ("y150", self.t("150年 kg", "150 years kg"), 150),
            ("y200", self.t("200年 kg", "200 years kg"), 150),
            ("factor", self.t("電力係数 kg-CO₂/kWh", "Grid factor kg-CO₂/kWh"), 190),
        ]:
            self.co2_tree.heading(key, text=label)
            self.co2_tree.column(key, width=width, anchor="center")
        self.co2_tree.pack(fill="x", padx=4, pady=(0, 4))

        # CO2 calculation breakdown for debugging and verification.
        self.co2_detail_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.co2_detail_tab, text=self.t("CO₂計算内訳", "CO₂ calculation breakdown"))
        detail_wrap = ttk.Frame(self.co2_detail_tab)
        detail_wrap.pack(fill="both", expand=True, padx=4, pady=4)
        detail_columns = (
            "region", "heating", "cooling", "base", "annual_use", "pv",
            "annual_net", "factor", "annual_co2", "initial", "y50", "y100", "y150", "y200"
        )
        self.co2_detail_tree = ttk.Treeview(detail_wrap, columns=detail_columns, show="headings", height=16)
        for key, label, width in [
            ("region", self.t("地域", "Region"), 145),
            ("heating", self.t("年間暖房電力 kWh", "Annual heating electricity kWh"), 135),
            ("cooling", self.t("年間冷房電力 kWh", "Annual cooling electricity kWh"), 135),
            ("base", self.t("年間その他 kWh", "Annual other kWh"), 120),
            ("annual_use", self.t("年間使用量 kWh", "Annual use kWh"), 125),
            ("pv", self.t("年間PV kWh", "Annual PV kWh"), 115),
            ("annual_net", self.t("年間差引 kWh", "Annual net kWh"), 120),
            ("factor", self.t("電力CO₂係数", "Grid CO₂ factor"), 105),
            ("annual_co2", self.t("年間運用CO₂ kg", "Annual operational CO₂ kg"), 135),
            ("initial", self.t("建設時CO₂ kg", "Initial CO₂ kg"), 125),
            ("y50", self.t("50年 kg", "50 years kg"), 115),
            ("y100", self.t("100年 kg", "100 years kg"), 115),
            ("y150", self.t("150年 kg", "150 years kg"), 115),
            ("y200", self.t("200年 kg", "200 years kg"), 115),
        ]:
            self.co2_detail_tree.heading(key, text=label)
            self.co2_detail_tree.column(key, width=width, anchor="center")
        detail_x = ttk.Scrollbar(detail_wrap, orient="horizontal", command=self.co2_detail_tree.xview)
        detail_y = ttk.Scrollbar(detail_wrap, orient="vertical", command=self.co2_detail_tree.yview)
        self.co2_detail_tree.configure(xscrollcommand=detail_x.set, yscrollcommand=detail_y.set)
        self.co2_detail_tree.grid(row=0, column=0, sticky="nsew")
        detail_y.grid(row=0, column=1, sticky="ns")
        detail_x.grid(row=1, column=0, sticky="ew")
        detail_wrap.rowconfigure(0, weight=1)
        detail_wrap.columnconfigure(0, weight=1)
        ttk.Label(
            self.co2_detail_tab,
            text=self.t(
                "確認式：暖冷房負荷はCOPで電力量へ換算します。月別買電量＝月間使用量－月間PV自家消費量、月別売電量＝月間PV－月間PV自家消費量です。年間運用CO₂＝年間買電量×電力CO₂係数。合計累積CO₂＝建設時CO₂＋年間運用CO₂×年数です。",
                "Check formula: heating and cooling loads are converted to electricity using COP. Annual grid purchase is the sum of max(monthly use - monthly PV, 0). Annual operational CO₂ = annual grid purchase × grid factor. Total cumulative CO₂ = initial CO₂ + annual operational CO₂ × years.",
            ),
            foreground="#555555",
        ).pack(fill="x", padx=8, pady=(0, 6))

        ttk.Label(
            self,
            text=self.t(
                "注：気温、露点、湿度、風、日射、水平面赤外放射、雲量、HDD・CDDは登録EPWの8760時間値（品質A）です。暖冷房、PV、CO₂は建物条件とEPWから算定する計算値であり、実測値ではありません。",
                "Note: Temperature, dew point, humidity, wind, solar radiation, horizontal infrared radiation, sky cover and degree-days are A-level values read from the registered EPW. Heating/cooling, PV and CO₂ are calculated results, not measured values.",
            ),
            wraplength=1420,
            foreground="#555555",
        ).pack(fill="x", padx=12, pady=(0, 8))

        self.bind("<Configure>", lambda _e: self.after_idle(self.redraw))

    def _regional_files(self, base_project):
        regional = base_project.get("regional_analysis") or {}
        entries = regional.get("generated_region_files") or []
        base_folder = Path(self.project_context.path).parent
        files = []
        # Include base project first.
        if Path(self.project_context.path).exists():
            files.append(({"city": (base_project.get("common") or {}).get("city") or "Base region"}, Path(self.project_context.path)))
        for entry in entries:
            path = Path(entry.get("path") or "")
            if not path.is_absolute():
                path = base_folder / (entry.get("file") or path.name)
            if path.exists():
                files.append((entry, path))
        return files

    def _weather_path(self, project: dict[str, Any], entry: dict[str, Any]) -> str:
        candidates = [
            entry.get("epw_path"),
            (project.get("regional_analysis") or {}).get("weather_file"),
            (project.get("regional_derivation") or {}).get("epw_path"),
            ((project.get("batch_location_analysis") or {}).get("climate_estimate") or {}).get("epw_path"),
            _recursive_find_text(project.get("module_outputs") or {}, ("weather_file", "epw_path")),
        ]
        for value in candidates:
            if value and Path(str(value)).exists():
                return str(value)
        return ""

    def _extract(self, project: dict[str, Any], entry: dict[str, Any], path: Path, base_pv_settings: dict[str, Any] | None = None) -> dict[str, Any]:
        """Read the Module 9 snapshot. No energy or CO2 recalculation occurs here."""
        regional = project.get("regional_analysis") or {}
        snapshot = regional.get("module10_snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError(
                f"{path.name}: " + self.t(
                    "Module 9のmodule10_snapshotがありません。Module 9で地域別Project JSONを再生成してください。",
                    "Module 9 module10_snapshot is missing. Regenerate the regional Project JSON in Module 9.",
                )
            )
        status = str(snapshot.get("status") or snapshot.get("analysis_status") or "")
        if status in {"pending_directional_surface_data", "pending"}:
            raw_reason = str(snapshot.get("reason") or "")
            reason = _m10_canonical_reason(raw_reason)
            if self.i18n.language == "ja":
                raise ValueError(
                    f"{path.name}: Module 10は保留です。"
                    "Module 1の方位別外壁・窓データが未確定です。"
                    "AI積算JSONでN/E/S/W等の方位別外壁面積・窓面積を確定してから再計算してください。"
                )
            raise ValueError(
                f"{path.name}: Module 10 is on hold. {reason} "
                "Confirm N/E/S/W orientation-specific exterior-wall and window areas using the AI takeoff JSON, then recalculate."
            )
        annual = snapshot.get("annual") or {}
        source_monthly = snapshot.get("monthly") or []
        if not isinstance(source_monthly, list) or len(source_monthly) != 12:
            raise ValueError(
                f"{path.name}: " + self.t(
                    "module10_snapshot.monthlyは12か月分必要です。",
                    "module10_snapshot.monthly must contain 12 months of data.",
                )
            )

        monthly = []
        for row in source_monthly:
            weather = row.get("weather") if isinstance(row, dict) else {}
            weather = weather if isinstance(weather, dict) else {}
            monthly.append({
                "use": _f(row.get("total_use_kWh")),
                "pv": _f(row.get("pv_generation_kWh")),
                "net": _f(row.get("net_energy_kWh")),
                "grid_import": _f(row.get("grid_import_kWh")),
                "grid_export": _f(row.get("grid_export_kWh")),
                "heating": _f(row.get("heating_electricity_kWh")),
                "cooling": _f(row.get("cooling_electricity_kWh")),
                "other": _f(row.get("other_electricity_kWh")),
                "temp_mean": _f(weather.get("mean_C")),
                "temp_high": _f(weather.get("mean_high_C")),
                "temp_low": _f(weather.get("mean_low_C")),
                "epw": weather,
            })

        city = str(snapshot.get("city") or (project.get("common") or {}).get("city") or entry.get("city") or path.stem)
        initial = _f(annual.get("initial_construction_co2_kg"))
        timeline_raw = snapshot.get("co2_timeline") or {}
        points = {year: _f(timeline_raw.get(str(year)), initial) for year in (0, 50, 100, 150, 200)}
        return {
            "canonical_metadata": {
                "canonical_language": "en",
                "canonical_schema_version": "2.6",
                "module": "module10",
                "result_standard": "English Canonical",
                "ui_language_independent": True,
            },
            "city": city,
            "path": path,
            "monthly": monthly,
            "heating": _f(annual.get("heating_electricity_kWh")),
            "cooling": _f(annual.get("cooling_electricity_kWh")),
            "pv": _f(annual.get("pv_generation_kWh")),
            "annual_base": _f(annual.get("other_electricity_kWh")),
            "annual_use": _f(annual.get("total_use_kWh")),
            "annual_net": _f(annual.get("net_energy_kWh")),
            "annual_purchase": _f(annual.get("grid_import_kWh")),
            "annual_export": _f(annual.get("grid_export_kWh")),
            "annual_operational_co2": _f(annual.get("operational_co2_kg")),
            "initial_co2": initial,
            "grid_factor": _f(annual.get("electricity_co2_factor_kg_per_kWh")),
            "co2_points": points,
            "climate_zone": str(regional.get("climate_code") or ""),
            "weather_path": str(snapshot.get("weather_file") or ""),
            "weather_quality": "A" if snapshot.get("weather_file") else "",
            "pv_enabled": _f(annual.get("pv_generation_kWh")) > 0.0,
            "raw_project": project,
            "settings": dict(((project.get("module_outputs") or {}).get("module2") or {}).get("settings") or {}),
        }

    def load_generated_projects(self):
        if self.project_context is None or self.project_context.path is None:
            return
        base_project = self.project_context.reload()
        self.folder_var.set(str(Path(self.project_context.path).parent))

        # PATCH 376: do not present previously generated regional snapshots as
        # a current comparison when the base Module 2 result has since become
        # stale.  The files remain available for audit but must be regenerated
        # after the current environmental calculation is saved.
        if not module_output_is_current(base_project, "module2"):
            messagebox.showwarning(
                self.title(),
                self.t(
                    "Module 2 の結果が古くなっています。環境・エネルギー解析を再計算して保存後、地域別Projectを再生成してください。",
                    "Module 2 results are stale. Recalculate and save the environment/energy analysis, then regenerate the regional projects.",
                ),
                parent=self,
            )
            self.projects = []
            self.hourly_cache.clear()
            self.hourly_rows = []
            self.redraw()
            return

        # Use the base Module 2 PV setting as the common comparison condition.
        # This prevents regional JSON files from re-enabling PV independently.
        base_renewable = dict((base_project.get("common") or {}).get("renewable_energy") or {})

        files = self._regional_files(base_project)
        if len(files) < 2:
            messagebox.showwarning(self.title(), self.t("Module 9で追加地域Project JSONを生成してください。", "Generate additional regional Project JSON files in Module 9."), parent=self)
            return
        self.projects = []
        self.hourly_cache.clear()
        self.hourly_rows = []
        errors = []
        for entry, path in files:
            try:
                project = json.loads(path.read_text(encoding="utf-8"))
                self.projects.append(self._extract(project, entry, path, base_pv_settings=base_renewable))
            except Exception as exc:
                errors.append(str(exc))
        for project in self.projects:
            for warning in project.get("consistency_warnings") or []:
                errors.append(f'{project["city"]}: {warning}')

        self.redraw()
        if errors:
            messagebox.showwarning(
                self.title(),
                self.t(
                    "一部の地域JSONに不整合または読込エラーがあります。\n"
                    "表示値は12か月の保存値から統一集計しました。\n\n",
                    "Some regional JSON files contain inconsistencies or read errors.\n"
                    "Displayed values were consistently totalled from the saved 12-month values.\n\n",
                ) + "\n".join(errors[:12]),
                parent=self,
            )


    def calculate_selected_hour(self):
        if not self.projects:
            return
        try:
            month = int(self.hour_month.get())
            day = int(self.hour_day.get())
            hour = int(self.hour_hour.get())
        except (TypeError, ValueError):
            messagebox.showwarning(self.title(), self.t("月・日・時を数値で指定してください。", "Enter numeric month, day and hour."), parent=self)
            return
        if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23):
            messagebox.showwarning(self.title(), self.t("月1～12、日1～31、時0～23で指定してください。", "Use month 1-12, day 1-31 and hour 0-23."), parent=self)
            return

        rows = []
        errors = []
        self.hourly_status.set(self.t("8760時間計算中…", "Calculating 8760 hours…"))
        self.update_idletasks()
        for project in self.projects:
            try:
                key = str(project["path"])
                hourly = self.hourly_cache.get(key)
                if hourly is None:
                    result = calculate_hourly_snapshot(
                        project["raw_project"], project["weather_path"], project["settings"],
                        project["grid_factor"], include_hourly=True,
                    )
                    hourly = result["hourly"]
                    self.hourly_cache[key] = hourly
                selected = hourly[(hourly["datetime"].dt.month == month) & (hourly["datetime"].dt.day == day) & (hourly["datetime"].dt.hour == hour)]
                if selected.empty:
                    raise ValueError(self.t("指定日時がEPW内にありません。", "Selected time is not present in the EPW."))
                r = selected.iloc[0].to_dict()
                r["region"] = project["city"]
                rows.append(r)
            except Exception as exc:
                errors.append(f'{project["city"]}: {exc}')

        self.hourly_rows = rows
        for item in self.hourly_tree.get_children():
            self.hourly_tree.delete(item)
        for row in rows:
            dt = row["datetime"]
            self.hourly_tree.insert("", "end", values=(
                row["region"], f"{int(dt.month):02d}/{int(dt.day):02d} {int(dt.hour):02d}:00",
                f'{_f(row.get("outdoor_C")):,.2f}', f'{_f(row.get("ghi_Wm2")):,.1f}',
                f'{_f(row.get("dni_Wm2")):,.1f}', f'{_f(row.get("dhi_Wm2")):,.1f}',
                f'{_f(row.get("heating_electricity_kWh")):,.4f}', f'{_f(row.get("cooling_electricity_kWh")):,.4f}',
                f'{_f(row.get("other_electricity_kWh")):,.4f}', f'{_f(row.get("total_use_kWh")):,.4f}',
                f'{_f(row.get("pv_generation_kWh")):,.4f}', f'{_f(row.get("grid_import_kWh")):,.4f}',
                f'{_f(row.get("grid_export_kWh")):,.4f}',
            ))
        metric_key, y_title = self.hourly_metric_labels[self.hourly_metric.get()]
        labels = [row["region"] for row in rows]
        values = [_f(row.get(metric_key)) for row in rows]
        title = self.t(
            f"{month}月{day}日 {hour}:00　全地域比較",
            f"All regions at {month}/{day} {hour}:00",
        )
        self.hourly_chart.draw(labels, values, y_title, title)
        self.hourly_status.set(self.t(f"{len(rows)}地域を表示", f"Showing {len(rows)} regions"))
        if errors:
            messagebox.showwarning(self.title(), "\n".join(errors[:12]), parent=self)

    def save_hourly_csv(self):
        if not self.hourly_rows:
            messagebox.showwarning(self.title(), self.t("先に日時を指定して計算してください。", "Calculate a selected hour first."), parent=self)
            return
        month, day, hour = int(self.hour_month.get()), int(self.hour_day.get()), int(self.hour_hour.get())
        path = filedialog.asksaveasfilename(
            parent=self,
            title=self.t("指定日時地域比較CSV保存", "Save selected-hour regional CSV"),
            initialfile=f"Module10_{month:02d}{day:02d}_{hour:02d}00_Regional_Comparison.csv",
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        from core.csv_export import write_dict_rows_csv
        fields = ["region", "datetime", "outdoor_C", "ghi_Wm2", "dni_Wm2", "dhi_Wm2",
                  "heating_electricity_kWh", "cooling_electricity_kWh", "other_electricity_kWh",
                  "total_use_kWh", "pv_generation_kWh", "grid_import_kWh", "grid_export_kWh", "net_energy_kWh"]
        export_rows = []
        for source in self.hourly_rows:
            row = {key: source.get(key, "") for key in fields}
            row["datetime"] = str(source.get("datetime", ""))
            export_rows.append(row)
        # PATCH_049: header follows the UI language; English output unchanged.
        write_dict_rows_csv(path, export_rows, self.language, fields=fields)
        messagebox.showinfo(self.title(), self.t("CSVを保存しました。", "CSV saved."), parent=self)


    def _set_initial_energy_sash(self, attempt=0):
        """Restore the original graph/table balance without collapsing either pane."""
        try:
            self.energy_pane.update_idletasks()
            height = int(self.energy_pane.winfo_height())
            # Ignore the provisional 1-pixel geometry returned during startup.
            if height < 300:
                if attempt < 4:
                    self.after(180, lambda: self._set_initial_energy_sash(attempt + 1))
                return
            # Roughly 58% graph and 42% tables, close to the original screen.
            position = max(260, min(height - 220, int(height * 0.58)))
            self.energy_pane.sashpos(0, position)
        except Exception:
            pass

    def redraw(self):
        if not self.projects:
            return
        months = MONTHS_JA if self.language == "ja" else MONTHS_EN
        # Display purchased electricity rather than annual/monthly net energy.
        # Net energy can be negative when PV export exceeds use and is not the
        # electricity quantity used by the operational CO2 calculation.
        energy_series = [(p["city"], [r["grid_import"] for r in p["monthly"]]) for p in self.projects]
        pv_enabled = any(bool(p.get("pv_enabled")) for p in self.projects)
        if pv_enabled:
            energy_y_title = self.t("買電量 kWh/月", "Grid import kWh/month")
            energy_title = self.t("同一工法の地域別 月間買電量（PV自家消費反映）", "Same method: monthly grid import after PV self-consumption")
        else:
            energy_y_title = self.t("買電量 kWh/月", "Grid import kWh/month")
            energy_title = self.t("同一工法の地域別 月間買電量（PVなし＝使用量）", "Same method: monthly grid import (equals use when PV is disabled)")
        self.energy_chart.draw(months, energy_series, energy_y_title, energy_title)
        for item in self.energy_tree.get_children():
            self.energy_tree.delete(item)
        for p in self.projects:
            self.energy_tree.insert("", "end", values=(p["city"], f'{p["annual_use"]:,.1f}', f'{p["pv"]:,.1f}', f'{p["annual_purchase"]:,.1f}', f'{p["annual_export"]:,.1f}', f'{p["annual_net"]:,.1f}', f'{p["heating"]:,.1f}', f'{p["cooling"]:,.1f}'))

        for item in self.monthly_tree.get_children():
            self.monthly_tree.delete(item)
        for p in self.projects:
            for idx, row in enumerate(p["monthly"]):
                self.monthly_tree.insert("", "end", values=(
                    p["city"], months[idx], f'{row["temp_mean"]:,.1f}', f'{row["temp_high"]:,.1f}', f'{row["temp_low"]:,.1f}',
                    f'{row["heating"]:,.1f}', f'{row["cooling"]:,.1f}', f'{row["use"]:,.1f}',
                    f'{row["pv"]:,.1f}', f'{row["grid_import"]:,.1f}', f'{row["grid_export"]:,.1f}', f'{row["net"]:,.1f}'
                ))

        for item in self.pv_monthly_tree.get_children():
            self.pv_monthly_tree.delete(item)
        for p in self.projects:
            for idx, row in enumerate(p["monthly"]):
                self.pv_monthly_tree.insert("", "end", values=(
                    p["city"], months[idx], f'{row["pv"]:,.1f}'
                ))

        for item in self.epw_tree.get_children():
            self.epw_tree.delete(item)
        for p in self.projects:
            for idx, row in enumerate(p["monthly"]):
                e = row.get("epw") or {}
                self.epw_tree.insert("", "end", values=(
                    p["city"], months[idx],
                    f'{_f(e.get("mean_relative_humidity_pct")):,.1f}',
                    f'{_f(e.get("mean_dew_point_C")):,.1f}',
                    f'{_f(e.get("mean_wind_speed_m_s")):,.2f}',
                    f'{_f(e.get("prevailing_wind_direction_deg")):,.1f}',
                    f'{_f(e.get("global_horizontal_irradiation_kWh_m2")):,.1f}',
                    f'{_f(e.get("direct_normal_irradiation_kWh_m2")):,.1f}',
                    f'{_f(e.get("diffuse_horizontal_irradiation_kWh_m2")):,.1f}',
                    f'{_f(e.get("mean_horizontal_infrared_W_m2")):,.1f}',
                    f'{_f(e.get("mean_total_sky_cover_tenths")):,.2f}',
                    f'{_f(e.get("mean_opaque_sky_cover_tenths")):,.2f}',
                    f'{_f(e.get("heating_degree_days_18C")):,.1f}',
                    f'{_f(e.get("cooling_degree_days_24C")):,.1f}',
                ))

        years = ["0", "50", "100", "150", "200"]

        operational_series = [
            (p["city"], [
                0.0,
                p["annual_operational_co2"] * 50,
                p["annual_operational_co2"] * 100,
                p["annual_operational_co2"] * 150,
                p["annual_operational_co2"] * 200,
            ])
            for p in self.projects
        ]
        self.co2_operational_chart.draw(
            years,
            operational_series,
            "kg-CO₂",
            self.t("同一工法の地域別 累積運用CO₂", "Same method: cumulative operational CO₂ by region"),
        )
        for item in self.co2_operational_tree.get_children():
            self.co2_operational_tree.delete(item)
        for p in self.projects:
            annual = p["annual_operational_co2"]
            self.co2_operational_tree.insert("", "end", values=(
                p["city"],
                f'{annual:,.1f}',
                f'{annual * 50:,.1f}',
                f'{annual * 100:,.1f}',
                f'{annual * 150:,.1f}',
                f'{annual * 200:,.1f}',
                f'{p["grid_factor"]:.3f}',
            ))

        co2_series = [(p["city"], [
            p["co2_points"][0],
            p["co2_points"][50],
            p["co2_points"][100],
            p["co2_points"][150],
            p["co2_points"][200],
        ]) for p in self.projects]
        self.co2_chart.draw(years, co2_series, "kg-CO₂", self.t("同一工法の地域別 累積CO₂（建設＋運用）", "Same method: cumulative CO₂ (initial + operation) by region"))
        for item in self.co2_tree.get_children():
            self.co2_tree.delete(item)
        for p in self.projects:
            c = p["co2_points"]
            self.co2_tree.insert("", "end", values=(
                p["city"], f'{c[0]:,.1f}', f'{c[50]:,.1f}', f'{c[100]:,.1f}',
                f'{c[150]:,.1f}', f'{c[200]:,.1f}', f'{p["grid_factor"]:.3f}'
            ))

        for item in self.co2_detail_tree.get_children():
            self.co2_detail_tree.delete(item)
        for p in self.projects:
            c = p["co2_points"]
            self.co2_detail_tree.insert("", "end", values=(
                p["city"],
                f'{p["heating"]:,.1f}',
                f'{p["cooling"]:,.1f}',
                f'{p["annual_base"]:,.1f}',
                f'{p["annual_use"]:,.1f}',
                f'{p["pv"]:,.1f}',
                f'{p["annual_net"]:,.1f}',
                f'{p["grid_factor"]:.3f}',
                f'{p["annual_operational_co2"]:,.1f}',
                f'{p["initial_co2"]:,.1f}',
                f'{c[50]:,.1f}',
                f'{c[100]:,.1f}',
                f'{c[150]:,.1f}',
                f'{c[200]:,.1f}',
            ))
