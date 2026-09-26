from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from core.ui_style import fit_window_to_screen
from core.error_text import friendly_exception_text

from services.automatic_weather_retrieval_v9_3_2 import (
    WeatherDownloadError, retrieve_nearest_epw,
)
from services.weather_catalog_v9_2_9 import WeatherCatalog, read_epw_metadata

from core.project_store import save_project, comparison_copy_block_reason
from regional_analysis.project_generator import generate_selected_projects, build_module10_snapshot
from services.project_export_paths import weather_method_directory, project_data_directory
from services.regional_coefficient_registry import (
    COEFFICIENT_GROUPS, GROUP_LABELS_EN, GROUP_LABELS_JA,
    STATUS_FORMAL, STATUS_MISSING, STATUS_PROVISIONAL,
    RegionalCoefficientRegistry,
)


class RegionalLocationManager(tk.Toplevel):
    def __init__(self, master, root_dir: Path, language="ja", project_context=None):
        super().__init__(master)
        self.root_dir = Path(root_dir)
        self.language = language
        self.project_context = project_context
        self.db = json.loads(
            (
                self.root_dir
                / "data"
                / "regional_suitability_database_v1.json"
            ).read_text(encoding="utf-8")
        )
        self.rows = []
        # EPW data belongs beside the external Project JSON/CSV data, not inside
        # the application build or the user's Documents folder.
        self.data_root = self._resolve_data_root()
        project_for_method = None
        try:
            if self.project_context is not None:
                project_for_method = self.project_context.reload()
        except Exception:
            project_for_method = None
        self.weather_root = weather_method_directory(self.data_root, project_for_method)
        self.weather_catalog = WeatherCatalog(self.root_dir)
        self.coefficient_registry = RegionalCoefficientRegistry(self.data_root, self.db)
        self.climate_names_ja = {
            "tropical_humid": "熱帯・高温多湿",
            "hot_arid": "高温乾燥（砂漠）",
            "hot_semi_arid": "高温半乾燥",
            "humid_subtropical": "温暖湿潤",
            "humid_continental": "湿潤大陸性",
            "marine_temperate": "西岸海洋性",
            "mediterranean": "地中海性",
            "cold_snow": "寒冷・積雪",
            "cool_temperate": "冷温帯",
            "cold": "寒冷",
            "subtropical_highland": "亜熱帯高地",
        }
        self.climate_names_en = {
            "tropical_humid": "Tropical humid",
            "hot_arid": "Hot arid / desert",
            "hot_semi_arid": "Hot semi-arid",
            "humid_subtropical": "Humid subtropical",
            "humid_continental": "Humid continental",
            "marine_temperate": "Marine temperate",
            "mediterranean": "Mediterranean",
            "cold_snow": "Cold / snowy",
            "cool_temperate": "Cool temperate",
            "cold": "Cold",
            "subtropical_highland": "Subtropical highland",
        }
        self.city_display_map = {}
        self.refresh_city_weather_status()
        self.generated_files = []
        self.title(
            "Module 9：同一工法・地域別Project JSON生成"
            if language == "ja"
            else "Module 9: Same-Method Regional Project JSON Generator"
        )
        fit_window_to_screen(self,1280,820,760,500)
        self.build()
        self.restore()

    def t(self, ja, en):
        return ja if self.language == "ja" else en

    def _apply_global_language(self, language):
        self.language = "ja" if language == "ja" else "en"
        self.title(
            "Module 9：同一工法・地域別Project JSON生成"
            if self.language == "ja"
            else "Module 9: Same-Method Regional Project JSON Generator"
        )
        for child in list(self.winfo_children()):
            if isinstance(child, tk.Toplevel):
                continue
            child.destroy()
        self.build()
        self.restore()

    def _resolve_data_root(self):
        """Resolve runtime regional data inside the active Project folder.

        PATCH_536: never create/use an unrelated top-level ``Data`` directory.
        Project-owned weather/catalog/coefficient data is kept under
        ``<Project folder>/Data``.  If no Project is loaded, use a non-created
        path under the application root only as a placeholder; write actions
        require an active Project.
        """
        try:
            if self.project_context is not None and self.project_context.path is not None:
                return project_data_directory(self.project_context.path, create=False)
        except Exception:
            pass
        return self.root_dir / "data" / "unassigned_runtime"

    def _sync_project_storage_roots(self):
        """Rebind project-owned runtime storage to the currently active Project.

        Module 9 can remain open while Module 0 changes/reloads the active Project.
        The old implementation resolved ``data_root``/``weather_root`` only once
        in ``__init__``; subsequent EPW downloads could therefore be written into
        the previous Project's Data folder even though generated regional JSONs
        were saved for the newly active Project.  Always derive the roots from
        the live ProjectContext before any read/write operation.
        """
        self.data_root = self._resolve_data_root()
        project_for_method = None
        try:
            if self.project_context is not None and self.project_context.path is not None:
                project_for_method = self.project_context.reload()
        except Exception:
            project_for_method = None
        self.weather_root = weather_method_directory(self.data_root, project_for_method)
        self.weather_catalog = WeatherCatalog(self.root_dir)
        self.coefficient_registry = RegionalCoefficientRegistry(self.data_root, self.db)
        return project_for_method

    def _reconstruct_saved_regions(self, project):
        """Recover Module 9 rows from already-generated regional Project JSONs.

        Module 10 can legitimately keep working from generated independent JSONs
        even if ``regional_analysis.additional_locations`` in the base Project was
        lost by an older/stale save.  In that case Module 9 previously reopened as
        a blank table.  Reconstruct only JSONs that explicitly point back to this
        base Project; never infer unrelated files by filename alone.
        """
        if self.project_context is None or self.project_context.path is None:
            return [], []
        base_path = Path(self.project_context.path).resolve()
        base_id = str((project or {}).get('project_id') or '')
        rows=[]
        generated=[]
        seen=set()
        for path in sorted(base_path.parent.glob('*.json')):
            try:
                if path.resolve() == base_path:
                    continue
                candidate=json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            if not isinstance(candidate,dict):
                continue
            rd=candidate.get('regional_derivation') or {}
            if not isinstance(rd,dict) or not rd.get('is_derived_project'):
                continue
            same_id=bool(base_id and str(rd.get('base_project_id') or '') == base_id)
            same_file=str(rd.get('base_project_file') or '') == base_path.name
            if not (same_id or same_file):
                continue
            city_name=str(rd.get('derived_city') or (candidate.get('common') or {}).get('city') or '').strip()
            if not city_name or city_name in seen:
                continue
            seen.add(city_name)
            master=self.find_city(city_name)
            common=candidate.get('common') or {}
            regional=candidate.get('regional_analysis') or {}
            row={
                'enabled': True,
                **(dict(master) if isinstance(master,dict) else {}),
                'name': (master or {}).get('name') if isinstance(master,dict) else city_name,
                'ja': (master or {}).get('ja') if isinstance(master,dict) else city_name,
                'country': rd.get('derived_country') or common.get('country') or (master or {}).get('country',''),
                'latitude': rd.get('derived_latitude') if rd.get('derived_latitude') not in (None,'') else common.get('latitude'),
                'longitude': rd.get('derived_longitude') if rd.get('derived_longitude') not in (None,'') else common.get('longitude'),
                'climate': rd.get('climate_code') or regional.get('climate_code') or (master or {}).get('climate',''),
                'climate_name_ja': rd.get('climate_name_ja') or regional.get('climate_name_ja') or (master or {}).get('climate_name_ja',''),
                'climate_name_en': rd.get('climate_name_en') or regional.get('climate_name_en') or (master or {}).get('climate_name_en',''),
                'epw_path': rd.get('epw_path') or regional.get('weather_file') or '',
                'epw_station': rd.get('epw_station') or regional.get('weather_station') or '',
                'epw_available': bool((rd.get('epw_path') or regional.get('weather_file')) and Path(str(rd.get('epw_path') or regional.get('weather_file'))).exists()),
                'regional_coefficients': rd.get('regional_coefficients') or regional.get('regional_coefficients') or {},
            }
            rows.append(row)
            generated.append({
                'city': row.get('name') or city_name,
                'country': row.get('country',''),
                'latitude': row.get('latitude',''),
                'longitude': row.get('longitude',''),
                'file': path.name,
                'path': str(path),
                'project_id': candidate.get('project_id',''),
                'generated_at': rd.get('generated_at') or candidate.get('updated_at',''),
                'independent_project': True,
                'climate': row.get('climate',''),
                'climate_name_ja': row.get('climate_name_ja',''),
                'climate_name_en': row.get('climate_name_en',''),
                'epw_path': row.get('epw_path',''),
                'epw_station': row.get('epw_station',''),
                'regional_coefficient_evaluation_level': rd.get('regional_coefficient_evaluation_level') or regional.get('regional_coefficient_evaluation_level','D'),
                'regional_coefficients': row.get('regional_coefficients') or {},
            })
        return rows, generated

    @staticmethod
    def _country_folder_name(country):
        aliases = {
            "United Kingdom": "UK",
            "United States": "USA",
            "United States of America": "USA",
            "United Arab Emirates": "UAE",
        }
        return aliases.get(str(country or "").strip(), str(country or "Global").strip() or "Global")


    def build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=5)

        ttk.Button(
            top,
            text=self.t(
                "追加地域JSONを計算・物件フォルダーへ保存",
                "Calculate and Save Regional JSONs in the Project Folder",
            ),
            command=self.start_calculate_save,
        ).pack(side="right", padx=4)

        self.save_path_var = tk.StringVar(value="")
        ttk.Label(
            top,
            text=self.t("保存先：", "Save folder:"),
        ).pack(side="left")
        ttk.Label(
            top,
            textvariable=self.save_path_var,
            foreground="#444444",
            wraplength=760,
        ).pack(side="left", padx=5)

        ttk.Label(
            self,
            text=self.t(
                "Module 0の基本地域以外を登録してください。チェックされた各都市について、"
                "基本Project JSONと同じ物件フォルダーへ独立したProject JSONを生成します。"
                "派生JSONのModule 0（国・都市・所在地・緯度・経度）も各地域へ置き換えます。",
                "Register locations other than the Module 0 base location. "
                "An independent Project JSON is generated in the same folder for each checked city, "
                "with Module 0 country, city, address and coordinates replaced.",
            ),
            foreground="#8b0000",
            wraplength=1220,
        ).pack(fill="x", padx=12, pady=5)

        add = ttk.Frame(self)
        add.pack(fill="x", padx=10, pady=5)
        self.city_var = tk.StringVar()
        names = self.city_display_values()
        ttk.Label(
            add,
            text=self.t("都市名", "City"),
        ).pack(side="left")
        self.city_combo = ttk.Combobox(
            add,
            textvariable=self.city_var,
            values=names,
            width=30,
        )
        self.city_combo.pack(side="left", padx=5)
        ttk.Button(
            add,
            text=self.t("追加", "Add"),
            command=self.add_city,
        ).pack(side="left", padx=4)
        ttk.Button(
            add,
            text=self.t("選択都市のEPWを取得", "Download EPW for Selected City"),
            command=self.download_selected_epw,
        ).pack(side="left", padx=4)
        ttk.Button(
            add,
            text=self.t("EPW状態を再読込", "Refresh EPW Status"),
            command=self.reload_epw_status,
        ).pack(side="left", padx=4)
        ttk.Button(
            add,
            text=self.t("選択削除", "Remove Selected"),
            command=self.remove_selected,
        ).pack(side="left", padx=4)
        ttk.Button(
            add,
            text=self.t("地域係数の登録状況", "Regional coefficient status"),
            command=self.open_coefficient_manager,
        ).pack(side="left", padx=4)

        self.tree = ttk.Treeview(
            self,
            columns=(
                "use", "city", "climate", "country", "lat", "lon",
                "epw", "electricity", "lifecycle", "level", "file"
            ),
            show="headings",
        )
        columns = [
            ("use", self.t("使用", "Use"), 60),
            ("city", self.t("都市", "City"), 145),
            ("climate", self.t("気候名称", "Climate"), 160),
            ("country", self.t("国", "Country"), 150),
            ("lat", self.t("緯度", "Latitude"), 80),
            ("lon", self.t("経度", "Longitude"), 80),
            ("epw", self.t("EPW気象地点", "EPW weather station"), 220),
            ("electricity", self.t("電力CO₂", "Electricity CO2"), 95),
            ("lifecycle", self.t("地域係数", "Regional coefficients"), 150),
            ("level", self.t("評価レベル", "Evaluation level"), 90),
            ("file", self.t("生成JSON", "Generated JSON"), 220),
        ]
        for key, label, width in columns:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree.bind("<Double-1>", self.toggle_use)

        ttk.Label(
            self,
            text=self.t(
                "操作：都市行をダブルクリックすると使用／不使用を切り替えます。"
                "同じ都市を再生成した場合は、既存の同名JSONを更新します。",
                "Double-click a row to toggle use. Regenerating the same city updates the existing JSON.",
            ),
            foreground="#555555",
        ).pack(fill="x", padx=12, pady=(0, 8))

    def climate_label(self, city):
        key = str(city.get("climate") or "")
        table = self.climate_names_ja if self.language == "ja" else self.climate_names_en
        return table.get(key, key or "-")

    @staticmethod
    def _distance_km(lat1, lon1, lat2, lon2):
        import math
        radius = 6371.0088
        p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
        dlat = p2 - p1
        dlon = math.radians(float(lon2) - float(lon1))
        value = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
        return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))

    def _epw_coordinates(self, path):
        try:
            first = Path(path).open("r", encoding="utf-8", errors="replace").readline().strip()
            parts = [x.strip() for x in first.split(",")]
            if len(parts) >= 8 and parts[0].upper() == "LOCATION":
                return float(parts[6]), float(parts[7])
        except Exception:
            pass
        return None

    def refresh_city_weather_status(self):
        epw_files = list(self.weather_root.rglob("*.epw"))
        for city in self.db.get("cities", []):
            best = None
            for path in epw_files:
                coords = self._epw_coordinates(path)
                if coords is None:
                    continue
                distance = self._distance_km(city.get("latitude", 0), city.get("longitude", 0), *coords)
                if best is None or distance < best[0]:
                    best = (distance, path)
            if best and best[0] <= 350.0:
                metadata = read_epw_metadata(best[1])
                city["epw_path"] = str(best[1])
                city["epw_station"] = metadata.get("name") or best[1].stem
                city["epw_distance_km"] = round(best[0], 1)
                city["epw_available"] = True
            else:
                city.pop("epw_path", None)
                city.pop("epw_station", None)
                city.pop("epw_distance_km", None)
                city["epw_available"] = False

    def city_display_values(self):
        self.city_display_map = {}
        values = []
        for city in self.db.get("cities", []):
            city_name = city.get("ja") if self.language == "ja" else city.get("name")
            climate = self.climate_label(city)
            status = self.t("EPW登録済", "EPW installed") if city.get("epw_available") else self.t("EPW未登録", "EPW missing")
            label = f"{city_name}｜{climate}｜{status}"
            self.city_display_map[label] = city
            values.append(label)
        return values

    def reload_epw_status(self):
        self._sync_project_storage_roots()
        self.refresh_city_weather_status()
        self.city_combo["values"] = self.city_display_values()
        self.refresh()

    def download_selected_epw(self):
        self._sync_project_storage_roots()
        city = self.city_display_map.get(self.city_var.get()) or self.find_city(self.city_var.get())
        if not city:
            messagebox.showwarning(self.title(), self.t("代表都市を選択してください。", "Select a representative city."), parent=self)
            return
        try:
            result = retrieve_nearest_epw(
                float(city["latitude"]),
                float(city["longitude"]),
                str(city.get("country") or ""),
                self.data_root,
                weather_root=self.weather_root,
                country_folder=self._country_folder_name(city.get("country")),
                catalog_root=self.weather_root.parent / "Catalog",
            )
            local_path = Path(result["local_path"])
            if not local_path.exists() or local_path.suffix.casefold() != ".epw":
                raise WeatherDownloadError(
                    f"EPW保存を確認できませんでした: {local_path}"
                )
            first_line = local_path.open(
                "r", encoding="utf-8", errors="replace"
            ).readline().strip()
            if not first_line.upper().startswith("LOCATION,"):
                raise WeatherDownloadError(
                    f"保存ファイルがEPW形式ではありません: {local_path.name}"
                )
            self.weather_catalog.register(local_path, str(city.get("country") or ""))
        except WeatherDownloadError as exc:
            messagebox.showerror(self.title(), friendly_exception_text(exc,self.language), parent=self)
            return
        except Exception as exc:
            messagebox.showerror(self.title(), f"EPW取得エラー: {exc}", parent=self)
            return
        self.reload_epw_status()
        city = self.find_city(city.get("name", "")) or city
        if not city.get("epw_available") or not city.get("epw_path"):
            messagebox.showerror(
                self.title(),
                self.t(
                    "EPWファイルは取得されましたが、保存先での登録確認に失敗しました。",
                    "The EPW was downloaded, but registration at the target folder could not be verified.",
                ),
                parent=self,
            )
            return
        self._close_save_busy_before_dialog()
        messagebox.showinfo(
            self.title(),
            self.t(
                f"{city.get('ja') or city.get('name')}の最寄りEPWを登録しました。",
                f"Registered the nearest EPW for {city.get('name')}.",
            ), parent=self,
        )

    def find_city(self, name):
        if name in self.city_display_map:
            return self.city_display_map[name]
        normalized = name.strip().lower()
        for city in self.db["cities"]:
            if normalized in (
                str(city["name"]).lower(),
                str(city.get("ja", "")).lower(),
            ):
                return city
        return None

    def add_city(self):
        city = self.find_city(self.city_var.get())
        if not city:
            messagebox.showwarning(
                self.title(),
                self.t(
                    "登録都市一覧から選択してください。",
                    "Select a city from the registered list.",
                ),
                parent=self,
            )
            return
        if not city.get("epw_available") or not city.get("epw_path"):
            messagebox.showwarning(
                self.title(),
                self.t(
                    "この都市のEPWが未登録です。先に『選択都市のEPWを取得』を実行してください。",
                    "EPW is not installed for this city. Download it first.",
                ), parent=self,
            )
            return
        for index, row in enumerate(self.rows):
            if str(row.get("name")) == str(city.get("name")):
                # Re-registering the same city refreshes EPW/location metadata
                # instead of silently doing nothing. Old generated-result/cache
                # references are discarded and rebuilt on the next calculation.
                enabled = bool(row.get("enabled", True))
                refreshed = {"enabled": enabled, **city}
                self.rows[index] = refreshed
                self.persist_selection_state()
                self.refresh()
                return
        self.rows.append({"enabled": True, **city})
        self.persist_selection_state()
        self.refresh()

    def remove_selected(self):
        selected = self.tree.selection()
        indexes = sorted(
            [self.tree.index(item) for item in selected],
            reverse=True,
        )
        for index in indexes:
            self.rows.pop(index)
        self.persist_selection_state()
        self.refresh()

    def toggle_use(self, event=None):
        item = self.tree.identify_row(event.y) if event else ""
        if not item:
            return
        index = self.tree.index(item)
        self.rows[index]["enabled"] = not self.rows[index].get(
            "enabled", True
        )
        self.persist_selection_state()
        self.refresh()

    def open_coefficient_manager(self):
        RegionalCoefficientManager(
            self,
            registry=self.coefficient_registry,
            city_database=self.db,
            language=self.language,
            epw_status_callback=lambda city: bool(city.get("epw_available")),
        )

    @staticmethod
    def _status_mark(status):
        return {
            STATUS_FORMAL: "正式",
            STATUS_PROVISIONAL: "暫定",
            STATUS_MISSING: "未登録",
        }.get(status, "未登録")

    def _coefficient_summary(self, city):
        entry = self.coefficient_registry.get(str(city.get("name") or ""))
        groups = entry.get("groups") or {}
        electricity = self._status_mark((groups.get("electricity") or {}).get("status"))
        registered = sum(
            1 for key in COEFFICIENT_GROUPS
            if (groups.get(key) or {}).get("status") != STATUS_MISSING
        )
        level, _ = self.coefficient_registry.evaluation_level(
            bool(city.get("epw_available")), entry
        )
        return electricity, f"{registered}/{len(COEFFICIENT_GROUPS)}", level

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        generated_by_city = {
            str(item.get("city")): item
            for item in self.generated_files
        }

        for row in self.rows:
            generated = generated_by_city.get(str(row.get("name")), {})
            result = row.get("result") or {}
            electricity_status, coefficient_count, level = self._coefficient_summary(row)
            self.tree.insert(
                "",
                "end",
                values=(
                    "☑" if row.get("enabled", True) else "□",
                    row.get("ja") if self.language == "ja" else row.get("name"),
                    self.climate_label(row),
                    row.get("country"),
                    row.get("latitude"),
                    row.get("longitude"),
                    row.get("epw_station") or self.t("未登録", "Missing"),
                    electricity_status,
                    coefficient_count,
                    level,
                    generated.get("file", "-"),
                ),
            )

    def persist_selection_state(self):
        """Persist the Module 9 city list immediately, without running calculations."""
        self._sync_project_storage_roots()
        if self.project_context is None or self.project_context.path is None:
            return
        project = self.project_context.reload()
        if not isinstance(project, dict):
            return
        regional = project.setdefault("regional_analysis", {})
        regional["additional_locations"] = self.rows
        regional["generated_region_files"] = self.generated_files
        regional["generated_region_folder"] = str(Path(self.project_context.path).parent)
        regional["location_database_version"] = self.db.get("version")
        regional["generator_version"] = "3.7.5-module9-persist"
        # PATCH_043: regional analysis is not re-run on a comparison copy.
        if comparison_copy_block_reason(project, "module9", self.language):
            return
        save_project(project, self.project_context.path)
        self.project_context.set(self.project_context.path, project)

    def restore(self):
        if self.project_context is None or self.project_context.path is None:
            return
        project = self._sync_project_storage_roots() or self.project_context.reload()
        # Refresh EPW availability from the *current* Project-owned weather folder.
        self.refresh_city_weather_status()
        regional = project.get("regional_analysis") or {}
        self.rows = regional.get("additional_locations") or []
        self.generated_files = regional.get("generated_region_files") or []

        # PATCH 538: Module 10 may still have valid generated regional JSONs even
        # when an older/stale base-Project save lost the Module 9 selection list.
        # Never reopen as an unexplained blank screen: recover the list from the
        # derived JSON provenance and immediately persist the repaired index.
        if not self.rows:
            recovered_rows, recovered_files = self._reconstruct_saved_regions(project)
            if recovered_rows:
                self.rows = recovered_rows
                self.generated_files = recovered_files
                regional = project.setdefault("regional_analysis", {})
                regional["additional_locations"] = self.rows
                regional["generated_region_files"] = self.generated_files
                regional["generated_region_folder"] = str(Path(self.project_context.path).parent)
                regional["location_database_version"] = self.db.get("version")
                regional["generator_version"] = "3.7.6-patch538-recovery"
                if not comparison_copy_block_reason(project, "module9", self.language):
                    save_project(project, self.project_context.path)
                self.project_context.set(self.project_context.path, project)

        self.save_path_var.set(str(Path(self.project_context.path).parent))
        self.refresh()

    def _show_save_busy(self):
        """Show the regional JSON calculation/save status before heavy work starts."""
        try:
            old=getattr(self,"_save_busy_win",None)
            if old is not None:
                try:
                    if old.winfo_exists():
                        old.deiconify()
                        old.lift()
                        old.update()
                        return old
                except Exception:
                    pass

            win=tk.Toplevel(self)
            win.title(self.t("計算・保存中", "Calculating / Saving"))
            win.transient(self)
            win.resizable(False,False)
            win.protocol("WM_DELETE_WINDOW",lambda:None)
            try:
                win.attributes("-topmost",True)
            except Exception:
                pass

            frm=tk.Frame(win,bg="#fff4bf",bd=4,relief="ridge",width=520,height=200)
            frm.pack(fill="both",expand=True)
            frm.pack_propagate(False)

            tk.Label(
                frm,
                text=self.t("計算・保存中", "CALCULATING / SAVING"),
                bg="#fff4bf",fg="#202020",
                font=("Yu Gothic UI",24,"bold"),
            ).pack(fill="x",pady=(20,6))

            tk.Label(
                frm,text="◌",bg="#fff4bf",fg="#4d9bd6",
                font=("Yu Gothic UI",22,"bold"),
            ).pack(fill="x",pady=(0,3))

            tk.Label(
                frm,
                text=self.t(
                    "地域別Project JSONを計算し、物件フォルダーへ保存しています",
                    "Calculating regional Project JSON files and saving them in the project folder",
                ),
                bg="#fff4bf",fg="#202020",
                font=("Yu Gothic UI",9,"bold"),
            ).pack(fill="x",pady=(0,1))

            tk.Label(
                frm,
                text=self.t(
                    "しばらくお待ちください...",
                    "Please wait...",
                ),
                bg="#fff4bf",fg="#202020",
                font=("Yu Gothic UI",9,"bold"),
            ).pack(fill="x",pady=(0,12))

            self.update_idletasks()
            w,h=520,200
            x=self.winfo_rootx()+max(0,(self.winfo_width()-w)//2)
            y=self.winfo_rooty()+max(0,(self.winfo_height()-h)//2)
            win.geometry(f"{w}x{h}+{x}+{y}")
            win.lift()
            self.configure(cursor="watch")
            self._save_busy_win=win

            win.update_idletasks()
            win.update()
            self.update_idletasks()
            return win
        except Exception:
            return None

    def _hide_save_busy(self,win=None):
        try:
            self.configure(cursor="")
        except Exception:
            pass
        target=win or getattr(self,"_save_busy_win",None)
        try:
            if target is not None and target.winfo_exists():
                target.destroy()
        except Exception:
            pass
        self._save_busy_win=None
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _close_save_busy_before_dialog(self):
        """PATCH_525: modal dialogs must never be displayed while the busy window remains visible."""
        self._hide_save_busy(getattr(self, "_save_busy_win", None))
        try:
            self.update()
        except Exception:
            pass

    def start_calculate_save(self):
        """Button entry point: wait 1 second, show status, then start calculation."""
        try:
            existing=getattr(self,"_save_busy_win",None)
            if existing is not None and existing.winfo_exists():
                existing.lift()
                return
        except Exception:
            pass
        self.after(1000,self._start_calculate_save_after_delay)

    def _start_calculate_save_after_delay(self):
        self._save_busy_win=self._show_save_busy()
        # Return control to Tk once so all text is painted before calculation.
        self.after(150,self._run_calculate_save_with_busy)

    def _run_calculate_save_with_busy(self):
        try:
            self._calculate_save_impl()
        finally:
            self._hide_save_busy(getattr(self,"_save_busy_win",None))

    def _calculate_save_impl(self):
        self._sync_project_storage_roots()
        if self.project_context is None or self.project_context.path is None:
            self._close_save_busy_before_dialog()
            messagebox.showwarning(
                self.title(),
                self.t(
                    "先にProject JSONを作成・読込してください。",
                    "Create or load a Project JSON first.",
                ),
                parent=self,
            )
            return

        project = self.project_context.reload()
        # PATCH_043: stop before any regional file is generated for a copy.
        _blocked = comparison_copy_block_reason(project, "module10", self.language)
        if _blocked:
            self._close_save_busy_before_dialog()
            messagebox.showwarning(self.title(), _blocked, parent=self)
            return
        missing = [
            row.get("ja") or row.get("name")
            for row in self.rows
            if row.get("enabled", True) and (not row.get("epw_path") or not Path(row.get("epw_path", "")).exists())
        ]
        if missing:
            self._close_save_busy_before_dialog()
            messagebox.showerror(
                self.title(),
                self.t(
                    "EPW未登録またはファイルが見つからない都市があります: " + ", ".join(missing),
                    "EPW is missing for: " + ", ".join(missing),
                ), parent=self,
            )
            return
        regional = project.setdefault("regional_analysis", {})
        required = int(
            regional.get("required_durability_years", 100)
        )

        for row in self.rows:
            row["regional_coefficients"] = self.coefficient_registry.snapshot(
                str(row.get("name") or row.get("ja") or ""),
                epw_available=bool(row.get("epw_available")),
            )

        try:
            generated = generate_selected_projects(
                base_project=project,
                base_project_path=self.project_context.path,
                rows=self.rows,
                database=self.db,
                required_years=required,
                overwrite=True,
            )
        except Exception as exc:
            self._close_save_busy_before_dialog()
            messagebox.showerror(
                self.title(),
                str(exc),
                parent=self,
            )
            return

        generated_by_city = {
            str(item.get("city")): item for item in generated
        }
        for row in self.rows:
            generated_item = generated_by_city.get(str(row.get("name")))
            if generated_item:
                row["generated_project"] = generated_item

        regional["required_durability_years"] = required
        regional["additional_locations"] = self.rows
        regional["generated_region_files"] = generated
        regional["generated_region_folder"] = str(
            Path(self.project_context.path).parent
        )
        regional["location_database_version"] = self.db.get("version")
        regional["generator_version"] = "3.7.4-module10-rebuild"
        # Save the base region in exactly the same display schema as every
        # generated regional Project JSON. Module 10 only reads this payload.
        regional["module10_snapshot"] = build_module10_snapshot(project)

        # PATCH_043: safety net - the copy keeps the source Project's 8760
        # snapshot; energy is independent of unit price and must stay identical.
        if comparison_copy_block_reason(project, "module10", self.language):
            return
        save_project(project, self.project_context.path)
        self.project_context.set(self.project_context.path, project)

        self.generated_files = generated
        self.save_path_var.set(
            str(Path(self.project_context.path).parent)
        )
        self.refresh()

        self._close_save_busy_before_dialog()
        messagebox.showinfo(
            self.title(),
            self.t(
                f"{len(generated)}件の地域別独立Project JSONを、同じ物件フォルダーへ保存しました。",
                f"Saved {len(generated)} independent regional Project JSON files in the same folder as the base JSON.",
            ),
            parent=self,
        )


class RegionalCoefficientManager(tk.Toplevel):
    def __init__(self, master, registry, city_database, language="ja", epw_status_callback=None):
        super().__init__(master)
        self.registry = registry
        self.city_database = city_database
        self.language = language
        self.epw_status_callback = epw_status_callback or (lambda city: False)
        self.title("地域係数登録状況" if language == "ja" else "Regional coefficient status")
        fit_window_to_screen(self,1500,760,820,500)
        self.transient(master)
        self.build()
        self.refresh()

    def t(self, ja, en):
        return ja if self.language == "ja" else en

    @staticmethod
    def _status_label(status, ja=True):
        labels_ja = {STATUS_MISSING: "未登録", STATUS_PROVISIONAL: "暫定", STATUS_FORMAL: "正式"}
        labels_en = {STATUS_MISSING: "Missing", STATUS_PROVISIONAL: "Provisional", STATUS_FORMAL: "Formal"}
        return (labels_ja if ja else labels_en).get(status, status)

    def build(self):
        note = self.t(
            "EPWと地域係数は別に管理します。未登録値は推定しません。行をダブルクリックすると係数を編集できます。",
            "EPW and regional coefficients are managed separately. Missing values are not estimated. Double-click a row to edit.",
        )
        ttk.Label(self, text=note, foreground="#8b0000", wraplength=1450).pack(fill="x", padx=10, pady=8)
        columns = ("city", "country", "epw", *COEFFICIENT_GROUPS, "level", "reason")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        labels = GROUP_LABELS_JA if self.language == "ja" else GROUP_LABELS_EN
        self.tree.heading("city", text=self.t("都市", "City"))
        self.tree.heading("country", text=self.t("国", "Country"))
        self.tree.heading("epw", text="EPW")
        self.tree.column("city", width=125)
        self.tree.column("country", width=125)
        self.tree.column("epw", width=80, anchor="center")
        for key in COEFFICIENT_GROUPS:
            self.tree.heading(key, text=labels[key])
            self.tree.column(key, width=110, anchor="center")
        self.tree.heading("level", text=self.t("評価レベル", "Level"))
        self.tree.column("level", width=85, anchor="center")
        self.tree.heading("reason", text=self.t("判定理由", "Reason"))
        self.tree.column("reason", width=290)
        y = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        x = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree.grid(in_=frame, row=0, column=0, sticky="nsew")
        y.grid(in_=frame, row=0, column=1, sticky="ns")
        x.grid(in_=frame, row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=8)
        ttk.Button(buttons, text=self.t("選択都市を編集", "Edit selected city"), command=self.edit_selected).pack(side="left")
        ttk.Button(buttons, text=self.t("再読込", "Refresh"), command=self.refresh).pack(side="left", padx=6)
        ttk.Label(buttons, textvariable=tk.StringVar(value=str(self.registry.path)), foreground="#555555").pack(side="right")

    def refresh(self):
        # PATCH_633: the whole population loop previously had no error
        # handling. In the packaged EXE (no console window), a single bad
        # city entry or registry read failure raised silently — Tkinter's
        # default callback handler swallows it — leaving the table visibly
        # empty with no indication of what happened. Now each city is
        # isolated so one bad row cannot blank the rest, and any top-level
        # failure (e.g. the registry file itself) shows a visible error
        # instead of failing silently.
        try:
            self.registry.ensure_cities()
            for item in self.tree.get_children():
                self.tree.delete(item)
            ja = self.language == "ja"
            skipped = 0
            for city in self.city_database.get("cities", []):
                try:
                    name = str(city.get("name") or "")
                    if not name:
                        skipped += 1
                        continue
                    entry = self.registry.get(name)
                    groups = entry.get("groups") or {}
                    epw = bool(city.get("epw_available"))
                    level, reason = self.registry.evaluation_level(epw, entry)
                    values = [
                        city.get("ja") if ja else name,
                        city.get("country", ""),
                        self.t("登録済", "Installed") if epw else self.t("未登録", "Missing"),
                    ]
                    values.extend(self._status_label((groups.get(k) or {}).get("status"), ja) for k in COEFFICIENT_GROUPS)
                    values.extend([level, reason])
                    if self.tree.exists(name):
                        # Duplicate/blank names would otherwise raise a Tcl
                        # "item already exists" error and abort the loop.
                        name = f"{name}_{skipped}"
                    self.tree.insert("", "end", iid=name, values=values)
                except Exception:
                    skipped += 1
                    continue
            if skipped:
                print(f"[RegionalCoefficientManager] skipped {skipped} city row(s) while refreshing.")
        except Exception as exc:
            messagebox.showerror(self.title(), friendly_exception_text(exc, self.language), parent=self)

    def edit_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(self.title(), self.t("都市を選択してください。", "Select a city."), parent=self)
            return
        city_name = selected[0]
        city = next((c for c in self.city_database.get("cities", []) if c.get("name") == city_name), None)
        if not city:
            return
        RegionalCoefficientEditor(self, self.registry, city, self.language, on_saved=self.refresh)


class RegionalCoefficientEditor(tk.Toplevel):
    STATUS_OPTIONS_JA = ("未登録", "暫定", "正式")
    STATUS_OPTIONS_EN = ("Missing", "Provisional", "Formal")
    STATUS_FROM_LABEL_JA = {"未登録": STATUS_MISSING, "暫定": STATUS_PROVISIONAL, "正式": STATUS_FORMAL}
    STATUS_FROM_LABEL_EN = {"Missing": STATUS_MISSING, "Provisional": STATUS_PROVISIONAL, "Formal": STATUS_FORMAL}

    def __init__(self, master, registry, city, language="ja", on_saved=None):
        super().__init__(master)
        self.registry = registry
        self.city = city
        self.language = language
        self.on_saved = on_saved
        self.vars = {}
        self.title((city.get("ja") if language == "ja" else city.get("name")) + " - " + ("地域係数" if language == "ja" else "Regional coefficients"))
        fit_window_to_screen(self,1050,690,700,460)
        self.transient(master)
        self.grab_set()
        self.build()

    def t(self, ja, en):
        return ja if self.language == "ja" else en

    def build(self):
        entry = self.registry.get(str(self.city.get("name")))
        groups = entry.get("groups") or {}
        labels = GROUP_LABELS_JA if self.language == "ja" else GROUP_LABELS_EN
        canvas = tk.Canvas(self, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        headers = [self.t("係数区分", "Group"), self.t("状態", "Status"), self.t("値", "Value"), self.t("単位", "Unit"), self.t("出典・決定根拠", "Source / basis"), self.t("備考", "Note")]
        for col, text in enumerate(headers):
            ttk.Label(body, text=text, font=("", 9, "bold")).grid(row=0, column=col, padx=3, pady=4, sticky="w")
        for row_no, key in enumerate(COEFFICIENT_GROUPS, start=1):
            group = groups.get(key) or {}
            status_map = self.STATUS_FROM_LABEL_JA if self.language == "ja" else self.STATUS_FROM_LABEL_EN
            reverse = {v: k for k, v in status_map.items()}
            status_var = tk.StringVar(value=reverse.get(group.get("status"), list(status_map)[0]))
            value_var = tk.StringVar(value="" if group.get("value") is None else str(group.get("value")))
            unit_var = tk.StringVar(value=str(group.get("unit") or ""))
            source_var = tk.StringVar(value=str(group.get("source") or ""))
            note_var = tk.StringVar(value=str(group.get("note") or ""))
            self.vars[key] = (status_var, value_var, unit_var, source_var, note_var)
            ttk.Label(body, text=labels[key], width=18).grid(row=row_no, column=0, padx=3, pady=3, sticky="w")
            ttk.Combobox(body, textvariable=status_var, values=self.STATUS_OPTIONS_JA if self.language == "ja" else self.STATUS_OPTIONS_EN, state="readonly", width=11).grid(row=row_no, column=1, padx=3, pady=3)
            ttk.Entry(body, textvariable=value_var, width=14).grid(row=row_no, column=2, padx=3, pady=3)
            ttk.Entry(body, textvariable=unit_var, width=16).grid(row=row_no, column=3, padx=3, pady=3)
            ttk.Entry(body, textvariable=source_var, width=36).grid(row=row_no, column=4, padx=3, pady=3, sticky="ew")
            ttk.Entry(body, textvariable=note_var, width=34).grid(row=row_no, column=5, padx=3, pady=3, sticky="ew")
        body.columnconfigure(4, weight=1)
        body.columnconfigure(5, weight=1)
        ttk.Label(body, text=self.t("注意：未登録値は空欄のまま保存できます。『正式』は確認できる出典を記載してください。", "Note: Missing values may remain blank. Formal data should include a verifiable source."), foreground="#8b0000", wraplength=950).grid(row=len(COEFFICIENT_GROUPS)+1, column=0, columnspan=6, sticky="w", padx=5, pady=12)
        buttons = ttk.Frame(body)
        buttons.grid(row=len(COEFFICIENT_GROUPS)+2, column=0, columnspan=6, sticky="e", padx=5, pady=8)
        ttk.Button(buttons, text=self.t("保存", "Save"), command=self.save).pack(side="left", padx=5)
        ttk.Button(buttons, text=self.t("キャンセル", "Cancel"), command=self.destroy).pack(side="left")

    def save(self):
        status_map = self.STATUS_FROM_LABEL_JA if self.language == "ja" else self.STATUS_FROM_LABEL_EN
        city_name = str(self.city.get("name"))
        for key, variables in self.vars.items():
            status_var, value_var, unit_var, source_var, note_var = variables
            raw_value = value_var.get().strip()
            value = raw_value
            if raw_value:
                try:
                    value = float(raw_value.replace(",", ""))
                except ValueError:
                    value = raw_value
            else:
                value = None
            self.registry.update_group(city_name, key, {
                "status": status_map.get(status_var.get(), STATUS_MISSING),
                "value": value,
                "unit": unit_var.get().strip(),
                "source": source_var.get().strip(),
                "note": note_var.get().strip(),
            })
        if self.on_saved:
            self.on_saved()
        self.destroy()
