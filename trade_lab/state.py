"""Small JSON state store: what has already been alerted, per New York day."""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .strategy import Signal

SCHEMA_VERSION = 1
KEEP_DAYS = 14


class StateError(RuntimeError):
    """Raised when persisted state exists but cannot be trusted."""


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
        except (json.JSONDecodeError, OSError) as exc:
            raise StateError(
                f"State file exists but cannot be read: {self.path}. "
                "Preserve a copy and repair or restore it before resuming."
            ) from exc

        if not isinstance(data, dict):
            raise StateError(f"Invalid state structure in {self.path}: expected an object")
        if data.get("version") != SCHEMA_VERSION:
            raise StateError(
                f"Unsupported state schema in {self.path}: "
                f"expected version {SCHEMA_VERSION}, got {data.get('version')!r}"
            )
        days = data.get("days")
        if not isinstance(days, dict):
            raise StateError(f"Invalid state structure in {self.path}: 'days' must be an object")
        for day, record in days.items():
            try:
                date.fromisoformat(day)
            except (TypeError, ValueError) as exc:
                raise StateError(f"Invalid date key in state file {self.path}: {day!r}") from exc
            if not isinstance(record, dict) or not isinstance(record.get("entries", []), list):
                raise StateError(f"Invalid day record in state file {self.path}: {day}")
        return data

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
        value = float(pnl)
        if not math.isfinite(value):
            raise ValueError("realized P&L must be finite")
        record = self._day(data, day)
        record["realized_pnl"] = round(float(record["realized_pnl"]) + value, 2)
        self._save(data)
