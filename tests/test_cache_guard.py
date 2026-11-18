from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from trade_lab.cache_guard import guard_cache
from trade_lab.state import StateError, StateStore

NY = ZoneInfo("America/New_York")


def test_cache_miss_before_session_bootstraps_empty_state(tmp_path):
    store = StateStore(tmp_path / "state.json")
    result = guard_cache(store, None, datetime(2026, 11, 18, 9, 0, tzinfo=NY), time(10))
    assert result == "initialized"
    store.validate_cached_state()


def test_cache_miss_during_session_fails_closed(tmp_path):
    store = StateStore(tmp_path / "state.json")
    with pytest.raises(StateError, match="No same-day Actions cache"):
        guard_cache(store, None, datetime(2026, 11, 18, 10, 0, tzinfo=NY), __import__("datetime").time(10))
    assert not store.path.exists()


def test_cache_hit_requires_real_valid_primary_file(tmp_path):
    store = StateStore(tmp_path / "state.json")
    with pytest.raises(StateError, match="missing"):
        guard_cache(store, "trade-state-2026-11-18-old", datetime(2026, 11, 18, 10, 0, tzinfo=NY), __import__("datetime").time(10))


def test_cache_hit_validates_state_before_monitor_runs(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.initialize()
    assert guard_cache(store, "trade-state-2026-11-18-old", datetime(2026, 11, 18, 10, 0, tzinfo=NY), __import__("datetime").time(10)) == "restored"
