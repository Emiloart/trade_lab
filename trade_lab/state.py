"""Validated, crash-conscious JSON state for daily alert history."""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .strategy import Signal

SCHEMA_VERSION = 1
KEEP_DAYS = 14


class StateError(RuntimeError):
    """Raised when persisted state exists but cannot be trusted or saved."""


class StateStore:
    """File-backed state with atomic replacement and a last-known-good backup.

    The primary file is authoritative. A missing primary with an existing
    backup is treated as an incident, not as a new empty installation.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.backup_path = self.path.with_name(self.path.name + ".bak")

    @staticmethod
    def _validate(data: Any, path: Path) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise StateError(f"Invalid state structure in {path}: expected an object")
        version = data.get("version")
        if isinstance(version, bool) or version != SCHEMA_VERSION:
            raise StateError(
                f"Unsupported state schema in {path}: "
                f"expected version {SCHEMA_VERSION}, got {version!r}"
            )
        days = data.get("days")
        if not isinstance(days, dict):
            raise StateError(f"Invalid state structure in {path}: 'days' must be an object")

        for day, record in days.items():
            try:
                parsed_day = date.fromisoformat(day)
            except (TypeError, ValueError) as exc:
                raise StateError(f"Invalid date key in state file {path}: {day!r}") from exc
            if parsed_day.isoformat() != day:
                raise StateError(f"Non-canonical date key in state file {path}: {day!r}")
            if not isinstance(record, dict):
                raise StateError(f"Invalid day record in state file {path}: {day}")
            entries = record.get("entries")
            if not isinstance(entries, list):
                raise StateError(f"Invalid entries in state file {path}: {day}")
            pnl = record.get("realized_pnl")
            if isinstance(pnl, bool) or not isinstance(pnl, (int, float)) or not math.isfinite(pnl):
                raise StateError(f"Invalid realized P&L in state file {path}: {day}")

            for entry in entries:
                if not isinstance(entry, dict):
                    raise StateError(f"Invalid entry in state file {path}: {day}")
                status = entry.get("status")
                if status not in {"sent", "missed", "delivery_unknown"}:
                    raise StateError(f"Invalid entry status in state file {path}: {day}")
                if entry.get("side") not in {"LONG", "SHORT"}:
                    raise StateError(f"Invalid entry side in state file {path}: {day}")
                bar_time = entry.get("bar_time")
                try:
                    parsed_time = datetime.fromisoformat(bar_time)
                except (TypeError, ValueError) as exc:
                    raise StateError(f"Invalid bar_time in state file {path}: {day}") from exc
                if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
                    raise StateError(f"Naive bar_time in state file {path}: {day}")
                if status == "sent":
                    for field in ("entry", "lots"):
                        value = entry.get(field)
                        if (
                            isinstance(value, bool)
                            or not isinstance(value, (int, float))
                            or not math.isfinite(value)
                            or value <= 0
                        ):
                            raise StateError(f"Invalid {field} in state file {path}: {day}")
                elif not isinstance(entry.get("reason"), str) or not entry["reason"]:
                    raise StateError(f"Missing entry reason in state file {path}: {day}")
        return data

    def _load(self, require_existing: bool = False) -> dict[str, Any]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            if self.backup_path.exists():
                raise StateError(
                    f"Primary state is missing but backup exists: {self.backup_path}. "
                    "Restore it explicitly after inspection; refusing an empty state."
                ) from exc
            if require_existing:
                raise StateError(f"Expected cached state file is missing: {self.path}") from exc
            return {"version": SCHEMA_VERSION, "days": {}}
        except OSError as exc:
            raise StateError(
                f"State file exists but cannot be read: {self.path}. "
                "Preserve a copy and repair or restore it before resuming."
            ) from exc

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise StateError(
                f"State file is malformed: {self.path}. "
                "Preserve a copy and repair or restore it before resuming."
            ) from exc
        return self._validate(data, self.path)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        try:
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            # Some platforms/filesystems do not support fsync on directories.
            pass

    @classmethod
    def _atomic_write(cls, path: Path, payload: bytes) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
            cls._fsync_directory(path.parent)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def _save(self, data: dict[str, Any]) -> None:
        if data["days"]:
            newest = date.fromisoformat(max(data["days"]))
            cutoff = (newest - timedelta(days=KEEP_DAYS)).isoformat()
            data["days"] = {d: v for d, v in data["days"].items() if d >= cutoff}
        self._validate(data, self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        try:
            if self.path.exists():
                # Preserve the last known-good primary before replacing it.
                previous = self.path.read_bytes()
                self._atomic_write(self.backup_path, previous)
            self._atomic_write(self.path, payload)
        except OSError as exc:
            raise StateError(f"Could not persist state safely to {self.path}: {exc}") from exc

    def initialize(self) -> bool:
        """Validate existing state or atomically create first-run state.

        Returns True only when a new primary state file was created.
        """
        data = self._load()
        if self.path.exists():
            return False
        self._save(data)
        return True

    def validate_cached_state(self) -> None:
        """Require a real primary file and validate it before using a cache hit."""
        self._load(require_existing=True)

    @staticmethod
    def _day(data: dict[str, Any], day: str) -> dict[str, Any]:
        return data["days"].setdefault(day, {"entries": [], "realized_pnl": 0.0})

    def day_closed(self, day: str) -> bool:
        return len(self._load()["days"].get(day, {}).get("entries", [])) > 0

    def realized_pnl(self, day: str) -> float:
        return float(self._load()["days"].get(day, {}).get("realized_pnl", 0.0))

    def entries(self, day: str) -> list[dict[str, Any]]:
        return list(self._load()["days"].get(day, {}).get("entries", []))

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
        self._record_non_sent(day, reason, sig, "missed")

    def record_delivery_unknown(self, day: str, reason: str, sig: Signal) -> None:
        """Close the day when Telegram may have accepted a timed-out request."""
        self._record_non_sent(day, reason, sig, "delivery_unknown")

    def _record_non_sent(self, day: str, reason: str, sig: Signal, status: str) -> None:
        data = self._load()
        self._day(data, day)["entries"].append(
            {
                "status": status,
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
        total = float(record["realized_pnl"]) + value
        if not math.isfinite(total):
            raise ValueError("accumulated realized P&L must be finite")
        record["realized_pnl"] = round(total, 2)
        self._save(data)
