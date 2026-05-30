"""Market inputs used for dynamic DCF assumptions."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import StringIO
import re

import pandas as pd
import requests


FRED_10Y_TREASURY_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
DAMODARAN_HISTORICAL_ERP_URL = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histimplX.htm"


@dataclass(frozen=True)
class MarketInputs:
    risk_free_rate: float
    equity_risk_premium: float
    risk_free_source: str
    equity_risk_premium_source: str
    warnings: list[str]


def _fetch_latest_fred_rate() -> tuple[float, str]:
    response = requests.get(FRED_10Y_TREASURY_CSV, timeout=10)
    response.raise_for_status()
    rows = pd.read_csv(StringIO(response.text))
    rows = rows[rows["DGS10"] != "."].dropna(subset=["DGS10"])
    if rows.empty:
        raise ValueError("FRED DGS10 response had no usable observations.")
    latest = rows.iloc[-1]
    return float(latest["DGS10"]) / 100.0, f"FRED DGS10 10Y Treasury ({latest['observation_date']})"


def _fetch_latest_damodaran_erp() -> tuple[float, str]:
    response = requests.get(DAMODARAN_HISTORICAL_ERP_URL, timeout=10)
    response.raise_for_status()
    text = re.sub(r"<[^>]+>", " ", response.text)
    rows = []
    for line in text.splitlines():
        parts = [part.strip() for part in re.split(r"\s{2,}", line) if part.strip()]
        if not parts or not re.fullmatch(r"\d{4}", parts[0]):
            continue
        percentages = [part for part in parts if re.search(r"-?\d+\.?\d*%", part)]
        if len(percentages) >= 3:
            try:
                implied = float(percentages[-1].replace("%", "").replace(",", "")) / 100.0
            except ValueError:
                continue
            rows.append((int(parts[0]), implied))

    if not rows:
        raise ValueError("Damodaran ERP page had no parseable implied premium rows.")
    year, erp = rows[-1]
    return erp, f"Damodaran historical implied ERP table ({year})"


@lru_cache(maxsize=1)
def get_market_inputs() -> MarketInputs:
    warnings = []

    try:
        risk_free_rate, risk_free_source = _fetch_latest_fred_rate()
    except Exception as exc:
        risk_free_rate = 0.045
        risk_free_source = "Fallback 4.50% long-term US Treasury proxy"
        warnings.append(f"Risk-free rate fallback used: {exc}")

    try:
        equity_risk_premium, erp_source = _fetch_latest_damodaran_erp()
    except Exception as exc:
        equity_risk_premium = 0.05
        erp_source = "Fallback 5.00% mature-market equity risk premium"
        warnings.append(f"Equity risk premium fallback used: {exc}")

    return MarketInputs(
        risk_free_rate=risk_free_rate,
        equity_risk_premium=equity_risk_premium,
        risk_free_source=risk_free_source,
        equity_risk_premium_source=erp_source,
        warnings=warnings,
    )
