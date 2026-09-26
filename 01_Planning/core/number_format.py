
from __future__ import annotations

import math
from typing import Any


INTEGER_UNITS = {
    "JPY", "円", "kg", "日", "年", "year", "days", "month", "months"
}
TWO_DECIMAL_UNITS = {
    "%", "x", "kg-CO₂", "kg_co2", "MJ", "m²", "m2",
    "kg-CO₂/m²·year", "MJ/m²·year", "JPY/m²", "JPY/year",
    "円／年", "円／m²・年"
}
THREE_DECIMAL_UNITS = {"m³", "m3", "t"}


def format_number(value: Any, unit: str = "", decimals: int | None = None) -> str:
    if value is None:
        return "－"
    if isinstance(value, str):
        return value

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if math.isnan(number) or math.isinf(number):
        return "－"

    normalized = str(unit or "").strip()

    if decimals is None:
        if normalized in THREE_DECIMAL_UNITS:
            decimals = 3
        elif normalized in TWO_DECIMAL_UNITS:
            decimals = 2
        elif normalized in INTEGER_UNITS or normalized.startswith("JPY"):
            decimals = 0
        else:
            decimals = 2

    return f"{number:,.{decimals}f}"


def header_with_unit(label: str, unit: str) -> str:
    label = str(label)
    unit = str(unit or "").strip()
    return f"{label}（{unit}）" if unit else label


def parse_number(value, default=0.0):
    if value is None:
        return default
    text=str(value).strip().replace(',', '')
    for token in ('JPY','USD','EUR','GBP','CNY','KRW','kg-CO₂','kg-CO2','MJ','kWh','m²','m3','m³','kg','t','%','円','年','日'):
        text=text.replace(token,'')
    text=text.strip()
    if not text:
        return default
    try:
        return float(text)
    except (TypeError,ValueError):
        return default


def format_input_number(value, unit='', decimals=0):
    number=parse_number(value)
    return f"{number:,.{decimals}f}"
