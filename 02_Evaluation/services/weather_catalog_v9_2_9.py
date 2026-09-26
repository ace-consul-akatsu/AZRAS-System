
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def normalize_country(value: str) -> str:
    value = str(value or "").strip()
    aliases = {
        "日本": "Japan",
        "JPN": "Japan",
        "JP": "Japan",
        "USA": "United States",
        "US": "United States",
        "United States of America": "United States",
        "GBR": "United Kingdom",
        "UK": "United Kingdom",
        "KOR": "South Korea",
        "Korea, Republic of": "South Korea",
        "Republic of Korea": "South Korea",
        "CHN": "China",
        "CAN": "Canada",
        "AUS": "Australia",
        "DEU": "Germany",
        "FRA": "France",
        "ITA": "Italy",
        "ESP": "Spain",
        "IND": "India",
        "BRA": "Brazil",
        "MEX": "Mexico",
        "IDN": "Indonesia",
        "THA": "Thailand",
        "VNM": "Vietnam",
        "SGP": "Singapore",
        "MYS": "Malaysia",
        "PHL": "Philippines",
        "TWN": "Taiwan",
    }
    return aliases.get(value, value)


def read_epw_metadata(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="replace") as file:
        first = file.readline().strip()
    parts = [part.strip() for part in first.split(",")]
    if not parts or parts[0].upper() != "LOCATION":
        return {
            "name": path.stem,
            "city": path.stem,
            "state": "",
            "country": "",
            "source": "",
        }
    return {
        "name": " / ".join(x for x in [parts[1], parts[2], parts[3]] if x),
        "city": parts[1] if len(parts) > 1 else "",
        "state": parts[2] if len(parts) > 2 else "",
        "country": normalize_country(parts[3] if len(parts) > 3 else ""),
        "source": parts[4] if len(parts) > 4 else "",
    }


class WeatherCatalog:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        user_dir = Path.home() / "Documents" / "AZRAS_Platform"
        user_dir.mkdir(parents=True, exist_ok=True)
        self.path = user_dir / "weather_catalog_user_v9_2_10.json"
        self.entries: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.entries = list(data.get("entries", []))
            except Exception:
                self.entries = []
        else:
            self.entries = []

    def save(self) -> None:
        self.path.write_text(
            json.dumps({"version":"1.0","entries":self.entries},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def register(self, file_path: str | Path, selected_country: str) -> dict[str, Any]:
        file_path = Path(file_path).resolve()
        suffix = file_path.suffix.lower()
        selected_country = normalize_country(selected_country)
        if suffix == ".epw":
            metadata = read_epw_metadata(file_path)
            country = metadata.get("country") or selected_country
            name = metadata.get("name") or file_path.stem
            city = metadata.get("city", "")
            state = metadata.get("state", "")
        else:
            country = selected_country
            name = file_path.stem
            city = ""
            state = ""

        entry = {
            "id": str(file_path),
            "name": name,
            "country": country,
            "city": city,
            "state": state,
            "format": suffix.lstrip(".").upper(),
            "path": str(file_path),
        }
        self.entries = [x for x in self.entries if x.get("path") != str(file_path)]
        self.entries.append(entry)
        self.entries.sort(key=lambda x: (x.get("country",""), x.get("name","")))
        self.save()
        return entry

    def available(self, country: str) -> list[dict[str, Any]]:
        country = normalize_country(country).casefold()
        valid = []
        for entry in self.entries:
            entry_country = normalize_country(entry.get("country", "")).casefold()
            if entry_country != country:
                continue
            path = Path(entry.get("path",""))
            if path.exists():
                valid.append(entry)
        return valid
