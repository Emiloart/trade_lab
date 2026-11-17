"""Small JSON state store: what has already been alerted, per New York day."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .strategy import Signal

log = logging.getLogger("trade_lab.state")

SCHEMA_VERSION = 1
KEEP_DAYS = 14


class StateStore:
    """File-backed state with atomic writes.

    Each day holds a list of ``entries`` (alerts sent or setups missed) and an
    optional manually recorded ``realized_pnl``. A day with any entry is
    closed: the strategy takes at most one trade per day.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    # -- persistence -----------------------------------------------------
    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": SCHEMA_VERSION, "days": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("days"), dict):
                raise ValueError("unexpected structure")
            return data
        except (ValueError, OSError) as exc:
            log.warning("State file unreadable (%s); starting with empty state", exc)
            return {"version": SCHEMA_VERSION, "days": {}}

    def _save(self, data: dict[str, Any]) -> None:
        if data["days"]:
            newest = date.fromisoformat(max(data["days"]))
            cutoff = (newest - timedelta(days=KEEP_DAYS)).isoformat()
            data["days"] = {d: v for d, v in data["days"].items() if d >= cutoff}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
            os.replace(tmp_name, self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    @staticmethod
    def _day(data: dict[str, Any], day: str) -> dict[str, Any]:
        return data["days"].setdefault(day, {"entries": [], "realized_pnl": 0.0})

    # -- queries ---------------------------------------------------------
    def day_closed(self, day: str) -> bool:
        entries = self._load()["days"].get(day, {}).get("entries", [])
        return len(entries) > 0

    def realized_pnl(self, day: str) -> float:
        return float(self._load()["days"].get(day, {}).get("realized_pnl", 0.0))

    def entries(self, day: str) -> list[dict[str, Any]]:
        return list(self._load()["days"].get(day, {}).get("entries", []))

    # -- updates ---------------------------------------------------------
    def record_sent(self, day: str, sig: Signal, entry: float, lots: float) -> None:
        data = self._load()
        self._day(data, day)["entries"].append(
            {
                "status": "sent",
                "side": sig.side,
                "bar_time": sig.time.isoformat(),
                "entry": round(entry, 2),
                "lots": lots,
            }
        )
        self._save(data)

    def record_missed(self, day: str, reason: str, sig: Signal) -> None:
        data = self._load()
        self._day(data, day)["entries"].append(
            {
                "status": "missed",
                "reason": reason,
                "side": sig.side,
                "bar_time": sig.time.isoformat(),
            }
        )
        self._save(data)

    def record_pnl(self, day: str, pnl: float) -> None:
        """Add realized P&L (negative for a loss) for the day."""
        data = self._load()
        record = self._day(data, day)
        record["realized_pnl"] = round(float(record["realized_pnl"]) + pnl, 2)
        self._save(data)
