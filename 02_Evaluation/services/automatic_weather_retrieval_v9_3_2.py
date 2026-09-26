
from __future__ import annotations

import json
import math
import re
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

ENERGYPLUS_WEATHER_PAGE = "https://energyplus.net/weather"
ENERGYPLUS_CATALOG_URLS = (
    "https://raw.githubusercontent.com/NatLabRockies/EnergyPlus/develop/weather/master.geojson",
    "https://github.com/NatLabRockies/EnergyPlus/raw/develop/weather/master.geojson",
    "https://raw.githubusercontent.com/NREL/EnergyPlus/develop/weather/master.geojson",
    "https://github.com/NREL/EnergyPlus/raw/develop/weather/master.geojson",
)
ENERGYPLUS_CATALOG_URL = ENERGYPLUS_CATALOG_URLS[0]
USER_AGENT = "AZRAS-Platform/9.3.2 (+EnergyPlus weather retrieval)"


class WeatherDownloadError(RuntimeError):
    pass


def _request(url: str, timeout: int = 45):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


def download_catalog(cache_path: str | Path) -> tuple[dict[str, Any], str]:
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    failures = []

    for catalog_url in ENERGYPLUS_CATALOG_URLS:
        try:
            with _request(catalog_url) as response:
                raw = response.read()
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict) or not data.get("features"):
                raise ValueError("地点データが含まれていません。")
            cache_path.write_bytes(raw)
            return data, catalog_url
        except Exception as exc:
            failures.append(f"{catalog_url}: {type(exc).__name__}: {exc}")

    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("features"):
                return data, str(cache_path)
        except Exception as exc:
            failures.append(f"cache: {type(exc).__name__}: {exc}")

    raise WeatherDownloadError(
        "EnergyPlus気象地点カタログを取得できませんでした。"
        + " / ".join(failures)
    )


def _coordinates(feature: dict[str, Any]) -> tuple[float, float] | None:
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates")
    if (
        geometry.get("type") == "Point"
        and isinstance(coords, (list, tuple))
        and len(coords) >= 2
    ):
        try:
            return float(coords[1]), float(coords[0])
        except (TypeError, ValueError):
            return None

    properties = feature.get("properties") or {}
    latitude_keys = ("latitude", "lat", "Latitude", "LAT")
    longitude_keys = ("longitude", "lon", "lng", "Longitude", "LON")
    lat = next((properties.get(k) for k in latitude_keys if properties.get(k) is not None), None)
    lon = next((properties.get(k) for k in longitude_keys if properties.get(k) is not None), None)
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def _extract_url(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, dict):
        for key in ("url", "href", "download", "path"):
            if value.get(key):
                return str(value[key])
        return ""
    text = str(value)
    href = re.search(r'href=["\']?([^"\' >]+)', text, re.I)
    if href:
        text = href.group(1)
    else:
        url = re.search(r'https?://[^\s"\'<>]+', text)
        if url:
            text = url.group(0)
    return text.replace("&amp;", "&").strip()


def _epw_url(feature: dict[str, Any]) -> str:
    properties = feature.get("properties") or {}
    for key in ("epw", "EPW", "epw_url", "download_url"):
        url = _extract_url(properties.get(key))
        if url:
            return urllib.parse.urljoin(ENERGYPLUS_CATALOG_URL, url)
    return ""


def _station_name(feature: dict[str, Any]) -> str:
    p = feature.get("properties") or {}
    for key in ("title", "name", "location", "city", "station"):
        if p.get(key):
            return re.sub(r"<[^>]+>", "", str(p[key])).strip()
    url = _epw_url(feature)
    return Path(urllib.parse.urlparse(url).path).stem or "EnergyPlus Weather"


def _country(feature: dict[str, Any]) -> str:
    p = feature.get("properties") or {}
    for key in ("country", "Country", "region"):
        if p.get(key):
            return str(p[key]).strip()
    return ""


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearest_station(
    catalog: dict[str, Any],
    latitude: float,
    longitude: float,
    preferred_country: str = "",
) -> dict[str, Any]:
    candidates = []
    for feature in catalog.get("features", []):
        coords = _coordinates(feature)
        url = _epw_url(feature)
        if coords is None or not url:
            continue
        station_lat, station_lon = coords
        distance = haversine_km(latitude, longitude, station_lat, station_lon)
        candidates.append(
            {
                "feature": feature,
                "name": _station_name(feature),
                "country": _country(feature),
                "latitude": station_lat,
                "longitude": station_lon,
                "distance_km": distance,
                "epw_url": url,
            }
        )

    if not candidates:
        raise WeatherDownloadError("EnergyPlusカタログに利用可能なEPW地点がありません。")

    preferred = str(preferred_country or "").strip().lower()
    same_country = [
        c for c in candidates
        if preferred and preferred in c["country"].lower()
    ]
    pool = same_country or candidates
    return min(pool, key=lambda item: item["distance_km"])


def _safe_filename(name: str) -> str:
    name = urllib.parse.unquote(name)
    name = re.sub(r'[<>:"/\\|?*]+', "_", name)
    return name.strip(" .") or "weather.epw"


def download_epw(station: dict[str, Any], target_dir: str | Path) -> Path:
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    url = station["epw_url"]
    url_path = Path(urllib.parse.urlparse(url).path)
    downloaded_name = _safe_filename(url_path.name or "weather.epw")
    downloaded_path = target_dir / downloaded_name

    try:
        with _request(url, timeout=90) as response:
            with downloaded_path.open("wb") as file:
                shutil.copyfileobj(response, file)
    except Exception as exc:
        raise WeatherDownloadError(
            f"EPWファイルをダウンロードできませんでした: {exc}"
        ) from exc

    if downloaded_path.suffix.lower() == ".epw":
        return downloaded_path

    if downloaded_path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(downloaded_path) as archive:
                epw_names = [
                    name for name in archive.namelist()
                    if name.lower().endswith(".epw")
                ]
                if not epw_names:
                    raise WeatherDownloadError("ZIP内にEPWファイルがありません。")
                selected = epw_names[0]
                output = target_dir / _safe_filename(Path(selected).name)
                with archive.open(selected) as source, output.open("wb") as target:
                    shutil.copyfileobj(source, target)
            return output
        finally:
            downloaded_path.unlink(missing_ok=True)

    # Some servers omit a useful extension. Check the first EPW header.
    try:
        first = downloaded_path.open(
            "r", encoding="utf-8", errors="replace"
        ).readline()
        if first.upper().startswith("LOCATION,"):
            output = downloaded_path.with_suffix(".epw")
            downloaded_path.replace(output)
            return output
    except Exception:
        pass

    raise WeatherDownloadError(
        f"取得ファイルがEPW形式ではありません: {downloaded_path.name}"
    )


def retrieve_nearest_epw(
    latitude: float,
    longitude: float,
    country: str,
    user_root: str | Path,
    *,
    weather_root: str | Path | None = None,
    country_folder: str | None = None,
    catalog_root: str | Path | None = None,
) -> dict[str, Any]:
    """Download the nearest EPW to an explicit, verifiable destination.

    The optional arguments preserve backward compatibility while allowing the
    caller to store weather data under the project's external Data folder.
    """
    user_root = Path(user_root)
    catalog_dir = Path(catalog_root) if catalog_root is not None else user_root / "catalog"
    catalog, catalog_source = download_catalog(
        catalog_dir / "energyplus_master.geojson"
    )
    station = find_nearest_station(catalog, latitude, longitude, country)
    folder_name = country_folder or country or "Global"
    folder_name = re.sub(r'[<>:"/\\|?*]+', "_", folder_name)
    destination_root = (
        Path(weather_root)
        if weather_root is not None
        else user_root / "weather" / "EnergyPlus"
    )
    epw_path = download_epw(
        station,
        destination_root / folder_name,
    )
    if not epw_path.exists():
        raise WeatherDownloadError(f"EPW保存に失敗しました: {epw_path}")
    return {
        **station,
        "local_path": str(epw_path),
        "catalog_url": catalog_source,
        "source_page": ENERGYPLUS_WEATHER_PAGE,
    }
