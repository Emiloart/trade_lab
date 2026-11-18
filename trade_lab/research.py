"""Chronological strategy research with instrument-specific execution assumptions.

Variants are ranked on validation intervals. Their selected configurations are
then evaluated on subsequent test intervals, which do not participate in selection.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import pandas as pd

from .backtest import BacktestCosts, performance_summary, run_backtest
from .config import AccountRiskConfig, StrategyParameters
from .instruments import InstrumentSpec
from .sessions import NY, in_window
from .strategy import Signal, signal_for_bar


@dataclass(frozen=True)
class ResearchVariant:
    """Named strategy configuration included in a research universe."""
    name: str
    config: StrategyParameters

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("variant name cannot be empty")


@dataclass(frozen=True)
class WalkForwardWindow:
    """Chronological date ranges; boundaries are inclusive."""
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date


def make_walk_forward_windows(
    trading_dates: list[date],
    train_days: int,
    validation_days: int,
    test_days: int,
    step_days: int | None = None,
) -> list[WalkForwardWindow]:
    """Create expanding-history, rolling-forward windows over observed sessions."""
    sizes = (train_days, validation_days, test_days)
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in sizes):
        raise ValueError("train_days, validation_days and test_days must be positive integers")
    step = test_days if step_days is None else step_days
    if isinstance(step, bool) or not isinstance(step, int) or step < 1:
        raise ValueError("step_days must be a positive integer")
    dates = sorted(set(trading_dates))
    windows: list[WalkForwardWindow] = []
    first_test = train_days + validation_days
    for test_start in range(first_test, len(dates) - test_days + 1, step):
        windows.append(
            WalkForwardWindow(
                train_start=dates[0],
                train_end=dates[test_start - validation_days - 1],
                validation_start=dates[test_start - validation_days],
                validation_end=dates[test_start - 1],
                test_start=dates[test_start],
                test_end=dates[test_start + test_days - 1],
            )
        )
    return windows


def _summary_for_range(
    trades: pd.DataFrame, start: date, end: date
) -> dict[str, float | int]:
    if trades.empty:
        selected = trades
    else:
        selected = trades.loc[trades["Date"].map(date.fromisoformat).between(start, end)]
    return performance_summary(selected)


def _selection_key(summary: Mapping[str, float | int]) -> tuple[float, float, int]:
    expectancy = float(summary["expectancy_r"])
    profit_factor = float(summary["profit_factor"])
    if not math.isfinite(profit_factor):
        profit_factor = 1_000_000.0
    return expectancy, profit_factor, int(summary["closed"])


def run_walk_forward_research(
    datasets: Mapping[str, pd.DataFrame],
    instruments: Mapping[str, InstrumentSpec],
    costs: Mapping[str, BacktestCosts],
    variants: list[ResearchVariant],
    *,
    train_days: int,
    validation_days: int,
    test_days: int,
    step_days: int | None = None,
    value_to_account_rates: Mapping[str, float] | None = None,
    risk: AccountRiskConfig | None = None,
) -> pd.DataFrame:
    """Evaluate symbols with mandatory per-symbol specs and execution costs.

    Validation expectancy selects the variant. The subsequent test interval is
    evaluated only after selection. Full history is passed to the backtester so
    indicator warm-up uses only prior observations without truncating history.
    """
    if not datasets:
        raise ValueError("at least one dataset is required")
    if not variants:
        raise ValueError("at least one research variant is required")
    if len({variant.name for variant in variants}) != len(variants):
        raise ValueError("research variant names must be unique")
    rates = value_to_account_rates or {}
    output: list[dict[str, object]] = []

    for symbol, bars in datasets.items():
        if symbol not in instruments or symbol not in costs:
            raise ValueError(f"{symbol} requires explicit instrument economics and costs")
        instrument = instruments[symbol]
        if instrument.symbol != symbol:
            raise ValueError(f"instrument key {symbol!r} does not match {instrument.symbol!r}")
        if bars.empty or not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
            raise ValueError(f"{symbol} requires non-empty timezone-aware bars")
        sessions = sorted(set(bars.index.tz_convert("America/New_York").date))
        windows = make_walk_forward_windows(
            sessions, train_days, validation_days, test_days, step_days
        )
        if not windows:
            raise ValueError(
                f"{symbol} has {len(sessions)} sessions; insufficient for requested windows"
            )

        for window_number, window in enumerate(windows, start=1):
            evaluated = []
            for variant in variants:
                trades = run_backtest(
                    bars, variant.config, costs=costs[symbol], instrument=instrument,
                    value_to_account_rate=rates.get(symbol, 1.0), risk=risk,
                )
                train = _summary_for_range(trades, window.train_start, window.train_end)
                validation = _summary_for_range(
                    trades, window.validation_start, window.validation_end
                )
                evaluated.append((variant, validation))
                output.append({
                    "symbol": symbol, "window": window_number, "variant": variant.name,
                    "role": "candidate", "train_start": window.train_start.isoformat(),
                    "train_end": window.train_end.isoformat(),
                    "validation_start": window.validation_start.isoformat(),
                    "validation_end": window.validation_end.isoformat(),
                    "test_start": window.test_start.isoformat(),
                    "test_end": window.test_end.isoformat(),
                    **{f"train_{key}": value for key, value in train.items()},
                    **{f"validation_{key}": value for key, value in validation.items()},
                })

            selected_variant, _ = max(evaluated, key=lambda item: _selection_key(item[1]))
            test_trades = run_backtest(
                bars, selected_variant.config, costs=costs[symbol], instrument=instrument,
                value_to_account_rate=rates.get(symbol, 1.0), risk=risk,
            )
            test = _summary_for_range(test_trades, window.test_start, window.test_end)
            output.append({
                "symbol": symbol, "window": window_number,
                "variant": selected_variant.name, "role": "selected_test",
                "selected_on": "validation_expectancy_r",
                "train_start": window.train_start.isoformat(),
                "train_end": window.train_end.isoformat(),
                "validation_start": window.validation_start.isoformat(),
                "validation_end": window.validation_end.isoformat(),
                "test_start": window.test_start.isoformat(),
                "test_end": window.test_end.isoformat(),
                **{f"test_{key}": value for key, value in test.items()},
            })
    return pd.DataFrame(output)



def measure_reclaim_outcomes(
    prepared: pd.DataFrame,
    config: StrategyParameters,
    horizons_bars: tuple[int, ...] = (3, 6, 12),
) -> pd.DataFrame:
    """Measure forward excursion after every qualifying reclaim candidate.

    Outcomes are normalized by the signal's initial stop distance (R). Only
    complete horizons contained within the same New York session date are
    included. This is a descriptive label study, not a trade simulation.
    """
    if not horizons_bars or any(
        isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1
        for horizon in horizons_bars
    ):
        raise ValueError("horizons_bars must contain positive integers")
    if len(set(horizons_bars)) != len(horizons_bars):
        raise ValueError("horizons_bars must not contain duplicates")
    if not isinstance(prepared.index, pd.DatetimeIndex) or prepared.index.tz is None:
        raise ValueError("prepared bars require a timezone-aware DatetimeIndex")
    if prepared.index.has_duplicates or not prepared.index.is_monotonic_increasing:
        raise ValueError("prepared bars must be sorted with unique timestamps")

    ny_dates = prepared.index.tz_convert(NY).date
    rows: list[dict[str, object]] = []
    for position, (stamp, bar) in enumerate(prepared.iterrows()):
        if not in_window(stamp, config):
            continue
        signal: Signal | None = signal_for_bar(stamp, bar, config)
        if signal is None:
            continue
        for horizon in horizons_bars:
            end_position = position + horizon
            if end_position >= len(prepared):
                continue
            if ny_dates[end_position] != ny_dates[position]:
                continue
            future = prepared.iloc[position + 1 : end_position + 1]
            direction = signal.direction
            favorable = (
                future["High"].astype(float) - signal.entry
                if direction == 1
                else signal.entry - future["Low"].astype(float)
            )
            adverse = (
                signal.entry - future["Low"].astype(float)
                if direction == 1
                else future["High"].astype(float) - signal.entry
            )
            rows.append(
                {
                    "signal_time": stamp.isoformat(),
                    "direction": signal.side,
                    "entry": signal.entry,
                    "risk_distance": signal.risk_distance,
                    "horizon_bars": horizon,
                    "horizon_end_time": future.index[-1].isoformat(),
                    "follow_through_r": (
                        (float(future["Close"].iloc[-1]) - signal.entry)
                        * direction
                        / signal.risk_distance
                    ),
                    "mfe_r": max(0.0, float(favorable.max())) / signal.risk_distance,
                    "mae_r": max(0.0, float(adverse.max())) / signal.risk_distance,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "signal_time", "direction", "entry", "risk_distance", "horizon_bars",
            "horizon_end_time", "follow_through_r", "mfe_r", "mae_r",
        ],
    )
