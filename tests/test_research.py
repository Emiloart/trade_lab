from datetime import date

import pandas as pd
import pytest

from trade_lab.backtest import BacktestCosts
from trade_lab.config import StrategyConfig
from trade_lab.filters import StrategyFilters
from trade_lab.instruments import AssetClass, InstrumentSpec
from trade_lab.research import (
    ResearchVariant,
    make_walk_forward_windows,
    run_walk_forward_research,
)


def instrument(symbol):
    return InstrumentSpec(
        symbol=symbol, asset_class=AssetClass.ETF, quote_currency="USD",
        tick_size=0.01, tick_value=0.01, tick_value_currency="USD",
        quantity_unit="share", min_quantity=1, quantity_step=1, max_quantity=100_000,
    )


def bars_for_sessions(sessions=12):
    parts = []
    for day in pd.date_range("2026-01-05", periods=sessions, freq="B"):
        index = pd.date_range(
            day.strftime("%Y-%m-%d") + " 15:00", periods=4, freq="5min", tz="UTC"
        )
        parts.append(pd.DataFrame({
            "Open": [100.0, 100.0, 100.5, 101.0],
            "High": [101.0, 101.0, 102.0, 103.0],
            "Low": [99.0, 99.0, 100.0, 100.5],
            "Close": [100.0, 100.5, 101.0, 102.0],
            "Volume": [1000.0] * 4,
        }, index=index))
    return pd.concat(parts)


def test_walk_forward_windows_are_ordered_and_non_overlapping():
    dates = [date(2026, 1, day) for day in range(1, 13)]
    windows = make_walk_forward_windows(dates, 4, 2, 2, step_days=2)
    assert len(windows) == 3
    assert windows[0].train_end < windows[0].validation_start
    assert windows[0].validation_end < windows[0].test_start
    assert windows[0].test_end < windows[1].test_start


def test_walk_forward_requires_enough_sessions():
    with pytest.raises(ValueError, match="insufficient"):
        run_walk_forward_research(
            {"ETF": bars_for_sessions(5)}, {"ETF": instrument("ETF")},
            {"ETF": BacktestCosts(spread_points=0.02)},
            [ResearchVariant("baseline", StrategyConfig(atr_period=1))],
            train_days=3, validation_days=2, test_days=2,
        )


def test_research_requires_explicit_symbol_economics_and_costs():
    with pytest.raises(ValueError, match="explicit instrument"):
        run_walk_forward_research(
            {"ETF": bars_for_sessions()}, {}, {},
            [ResearchVariant("baseline", StrategyConfig(atr_period=1))],
            train_days=4, validation_days=2, test_days=2,
        )


def test_research_emits_candidates_and_separate_selected_test_rows():
    result = run_walk_forward_research(
        {"ETF": bars_for_sessions()}, {"ETF": instrument("ETF")},
        {"ETF": BacktestCosts(spread_points=0.02, slippage_points=0.01)},
        [
            ResearchVariant("baseline", StrategyConfig(atr_period=1)),
            ResearchVariant("filtered", StrategyConfig(
                atr_period=1, filters=StrategyFilters(min_atr_pct=0.1)
            )),
        ],
        train_days=4, validation_days=2, test_days=2, step_days=2,
    )
    assert set(result["role"]) == {"candidate", "selected_test"}
    selected = result.loc[result["role"] == "selected_test"]
    assert len(selected) == 3
    assert set(selected["selected_on"]) == {"validation_expectancy_r"}
    assert selected["test_closed"].notna().all()
