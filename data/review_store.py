"""Optional on-disk storage for a private ESMT instance."""

from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

from models.investment_review import InvestmentReview


class ReviewStore:
    def __init__(self, path):
        self.path = Path(path).expanduser()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)

    def save(self, review: InvestmentReview) -> None:
        review.validate_for_save()
        review.evaluate()
        payload = json.dumps(asdict(review), allow_nan=False)
        with closing(self._connect()) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS reviews "
                "(id INTEGER PRIMARY KEY, ticker TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            db.execute("INSERT INTO reviews (ticker, payload) VALUES (?, ?)", (review.ticker, payload))

    def recent(self) -> dict[str, list[InvestmentReview]]:
        if not self.path.exists():
            return {}
        with closing(self._connect()) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reviews'").fetchone():
                return {}
            rows = db.execute(
                "SELECT ticker, payload FROM (SELECT ticker, payload, id, "
                "ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY id DESC) AS revision "
                "FROM reviews) WHERE revision <= 2 ORDER BY id"
            ).fetchall()
        history: dict[str, list[InvestmentReview]] = {}
        for ticker, payload in rows:
            history.setdefault(ticker, []).append(InvestmentReview.from_dict(json.loads(payload)))
        return history
