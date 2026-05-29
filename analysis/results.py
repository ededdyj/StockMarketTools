"""Shared result containers for batch analyses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd


@dataclass
class SkippedTicker:
    ticker: str
    reason: str
    detail: str = ""


@dataclass
class BatchAnalysisResult:
    dataframe: Optional[pd.DataFrame]
    skipped: List[SkippedTicker] = field(default_factory=list)
