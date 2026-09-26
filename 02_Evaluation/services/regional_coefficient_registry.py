from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

STATUS_MISSING = "missing"
STATUS_PROVISIONAL = "provisional"
STATUS_FORMAL = "formal"
VALID_STATUSES = {STATUS_MISSING, STATUS_PROVISIONAL, STATUS_FORMAL}

COEFFICIENT_GROUPS = (
    "electricity",
    "materials",
    "construction",
    "transport",
    "repair_update",
    "demolition_waste",
    "recycling",
    "cost_labor",
)

GROUP_LABELS_JA = {
    "electricity": "電力CO₂",
    "materials": "材料製造CO₂",
    "construction": "施工CO₂",
    "transport": "輸送",
    "repair_update": "修繕・更新",
    "demolition_waste": "解体・廃棄",
    "recycling": "再使用・リサイクル",
    "cost_labor": "建設費・労務",
}
GROUP_LABELS_EN = {
    "electricity": "Electricity CO2",
    "materials": "Material production CO2",
    "construction": "Construction CO2",
    "transport": "Transport",
    "repair_update": "Repair / renewal",
    "demolition_waste": "Demolition / waste",
    "recycling": "Reuse / recycling",
    "cost_labor": "Cost / labor",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _blank_group() -> dict[str, Any]:
    return {
        "status": STATUS_MISSING,
        "value": None,
        "unit": "",
        "source": "",
        "note": "",
        "updated_at": "",
    }


def _normalize_group(value: Any) -> dict[str, Any]:
    group = _blank_group()
    if isinstance(value, dict):
        group.update(value)
    if group.get("status") not in VALID_STATUSES:
        group["status"] = STATUS_MISSING
    return group


class RegionalCoefficientRegistry:
    """Persistent region-coefficient completeness registry.

    The registry deliberately separates EPW availability from lifecycle/cost
    coefficient registration. It does not invent missing values.
    """

    schema_version = "1.0"

    def __init__(self, data_root: str | Path, city_database: dict[str, Any]):
        self.data_root = Path(data_root)
        self.folder = self.data_root / "Regional_Coefficients"
        self.path = self.folder / "regional_coefficients.json"
        self.city_database = city_database
        self.data = self._load()
        self.ensure_cities()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data.setdefault("schema_version", self.schema_version)
                    data.setdefault("cities", {})
                    return data
            except Exception:
                pass
        return {
            "schema_version": self.schema_version,
            "notice_ja": "未登録値は推定せず、未登録として扱います。正式値と暫定値を区別して管理します。",
            "notice_en": "Missing values are not estimated. Formal and provisional registrations are managed separately.",
            "cities": {},
            "updated_at": _now(),
        }

    def ensure_cities(self) -> None:
        cities = self.data.setdefault("cities", {})
        changed = False
        for city in self.city_database.get("cities", []):
            name = str(city.get("name") or city.get("ja") or "").strip()
            if not name:
                continue
            entry = cities.setdefault(name, {})
            entry.setdefault("city", name)
            entry.setdefault("city_ja", city.get("ja", name))
            entry.setdefault("country", city.get("country", ""))
            groups = entry.setdefault("groups", {})
            for key in COEFFICIENT_GROUPS:
                groups[key] = _normalize_group(groups.get(key))
            # Existing database electricity values are useful planning values,
            # but are not silently promoted to formal data.
            electricity = groups["electricity"]
            if electricity["status"] == STATUS_MISSING and city.get("electricity_co2_kg_per_kwh") is not None:
                electricity.update({
                    "status": STATUS_PROVISIONAL,
                    "value": city.get("electricity_co2_kg_per_kwh"),
                    "unit": "kg-CO₂/kWh",
                    "source": "regional_suitability_database_v1.json（企画比較用初期値）",
                    "note": "正式評価時は公的資料または電力会社等の最新値へ置換してください。",
                    "updated_at": _now(),
                })
                changed = True
        if changed or not self.path.exists():
            self.save()

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = _now()
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, city_name: str) -> dict[str, Any]:
        entry = deepcopy(self.data.setdefault("cities", {}).setdefault(city_name, {}))
        groups = entry.setdefault("groups", {})
        for key in COEFFICIENT_GROUPS:
            groups[key] = _normalize_group(groups.get(key))
        return entry

    def update_group(self, city_name: str, key: str, values: dict[str, Any]) -> None:
        if key not in COEFFICIENT_GROUPS:
            raise KeyError(key)
        entry = self.data.setdefault("cities", {}).setdefault(city_name, {"city": city_name, "groups": {}})
        groups = entry.setdefault("groups", {})
        group = _normalize_group(groups.get(key))
        group.update(values)
        if group.get("status") not in VALID_STATUSES:
            group["status"] = STATUS_MISSING
        group["updated_at"] = _now()
        groups[key] = group
        self.save()

    @staticmethod
    def evaluation_level(epw_available: bool, entry: dict[str, Any]) -> tuple[str, str]:
        groups = entry.get("groups") or {}
        statuses = {key: _normalize_group(groups.get(key))["status"] for key in COEFFICIENT_GROUPS}
        if not epw_available or statuses["electricity"] == STATUS_MISSING:
            return "D", "EPWまたは電力CO₂係数が未登録"
        if all(statuses[key] == STATUS_FORMAL for key in COEFFICIENT_GROUPS):
            return "A", "EPWおよび全地域係数が正式登録済み"
        major = ("materials", "construction", "repair_update", "demolition_waste")
        if all(statuses[key] in {STATUS_PROVISIONAL, STATUS_FORMAL} for key in major):
            return "B", "EPW・電力CO₂・主要ライフサイクル係数が登録済み"
        return "C", "EPWと電力CO₂係数を中心とした評価"

    def snapshot(self, city_name: str, epw_available: bool = False) -> dict[str, Any]:
        entry = self.get(city_name)
        level, reason = self.evaluation_level(epw_available, entry)
        return {
            "schema_version": self.schema_version,
            "city": city_name,
            "evaluation_level": level,
            "evaluation_reason": reason,
            "epw_available": bool(epw_available),
            "groups": entry.get("groups", {}),
            "registry_file": str(self.path),
            "registry_updated_at": self.data.get("updated_at", ""),
        }
