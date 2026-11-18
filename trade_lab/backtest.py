"""Historical execution simulation built on the live strategy and indicators."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from .config import AccountRiskConfig, StrategyConfig, StrategyParameters
from .data import normalize_bars
from .instruments import InstrumentSpec
from .sessions import NY, in_window
from .sizing import quantity_for_instrument_risk
from .strategy import LONG, first_signal, prepare


@dataclass(frozen=True)
class BacktestCosts:
    """Per-fill costs: full spread/slippage in price points, commission per unit per side."""

    spread_points: float = 0.0
    slippage_points: float = 0.0
    commission_per_unit: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("spread_points", self.spread_points),
            ("slippage_points", self.slippage_points),
            ("commission_per_unit", self.commission_per_unit),
        ):
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative number")

    @property
    def total_risk_cost_per_unit(self) -> float:
        return self.spread_points + 2.0 * self.slippage_points + 2.0 * self.commission_per_unit


def load_csv(path: str | Path) -> pd.DataFrame:
    """Load the repository's Datetime + OHLCV CSV format as normalized UTC bars."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Market data file not found: {source}")
    raw = pd.read_csv(source)
    if "Datetime" not in raw.columns:
        raise ValueError("CSV must contain a Datetime column")
    raw["Datetime"] = pd.to_datetime(raw["Datetime"], utc=True, errors="raise")
    return normalize_bars(raw.set_index("Datetime"))


def _exit_for_bar(
    direction: int, row: pd.Series, stop: float, target: float
) -> tuple[float, str] | None:
    """Resolve OHLC stop/target touches conservatively; stop wins collisions."""
    open_price = float(row["Open"])
    high = float(row["High"])
    low = float(row["Low"])
    if direction == LONG:
        if low <= stop:
            return min(open_price, stop), "STOP"
        if high >= target:
            return target, "TARGET"
    else:
        if high >= stop:
            return max(open_price, stop), "STOP"
        if low <= target:
            return target, "TARGET"
    return None


def run_backtest(
    bars: pd.DataFrame,
    cfg: StrategyParameters | None = None,
    start_date: date | None = None,
    costs: BacktestCosts | None = None,
    instrument: InstrumentSpec | None = None,
    value_to_account_rate: float = 1.0,
    risk: AccountRiskConfig | None = None,
) -> pd.DataFrame:
    """Simulate one first-signal trade per NY date with configurable execution costs.

    Entry remains at signal-bar close as a documented research convention.
    Fills incur half-spread plus adverse slippage on both sides. Commission is
    charged per unit per side. Sizing includes modeled round-trip costs so the
    stop-risk budget is not exceeded under these assumptions.
    """
    config = cfg or StrategyParameters()
    risk_config = risk or (
        AccountRiskConfig(config.account_size, config.risk_pct, config.max_daily_loss_pct)
        if isinstance(config, StrategyConfig)
        else AccountRiskConfig()
    )
    execution = costs or BacktestCosts()
    if bars.empty:
        return pd.DataFrame()
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("backtest bars require a timezone-aware DatetimeIndex")
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError("backtest bars must be sorted with unique timestamps")
    missing = {"Open", "High", "Low", "Close", "Volume"} - set(bars.columns)
    if missing:
        raise ValueError(f"backtest bars missing required columns: {sorted(missing)}")
    if bars[["Open", "High", "Low", "Close"]].isna().any().any():
        raise ValueError("backtest OHLC values cannot be missing")

    prepared = prepare(bars, config)
    ny_dates = prepared.index.tz_convert(NY).date
    trades: list[dict[str, object]] = []
    fill_cost = execution.spread_points / 2.0 + execution.slippage_points
    if instrument is not None and not isinstance(instrument, InstrumentSpec):
        raise TypeError("instrument must be an InstrumentSpec")

    for day in sorted(set(ny_dates)):
        if start_date is not None and day < start_date:
            continue
        signal = first_signal(prepared, config, day)
        if signal is None:
            continue

        entry_position = prepared.index.get_loc(signal.time)
        day_positions = [
            pos for pos, bar_day in enumerate(ny_dates)
            if bar_day == day and pos > entry_position and in_window(prepared.index[pos], config)
        ]
        if instrument is None:
            risk_per_unit = signal.risk_distance + execution.total_risk_cost_per_unit
            units = risk_config.risk_dollars / risk_per_unit
        else:
            base_risk_per_unit = instrument.risk_per_quantity(
                signal.risk_distance, value_to_account_rate
            )
            tick_value_per_price_point = base_risk_per_unit / signal.risk_distance
            commission_price_points = (
                2.0 * execution.commission_per_unit / tick_value_per_price_point
            )
            effective_stop_distance = (
                signal.risk_distance
                + execution.spread_points
                + 2.0 * execution.slippage_points
                + commission_price_points
            )
            units = quantity_for_instrument_risk(
                config.risk_dollars,
                effective_stop_distance,
                instrument,
                value_to_account_rate,
            )
            if units <= 0:
                continue
            risk_per_unit = (
                base_risk_per_unit
                + instrument.price_cost_per_quantity(
                    execution.spread_points + 2.0 * execution.slippage_points,
                    value_to_account_rate,
                )
                + 2.0 * execution.commission_per_unit
            )
        entry_fill = signal.entry + signal.direction * fill_cost
        exit_price: float | None = None
        exit_fill: float | None = None
        exit_time: pd.Timestamp | None = None
        exit_reason = "OPEN_AT_SESSION_END"
        status = "OPEN"
        last_mark: float | None = None

        for pos in day_positions:
            row = prepared.iloc[pos]
            last_mark = float(row["Close"])
            outcome = _exit_for_bar(signal.direction, row, signal.stop, signal.target)
            if outcome is None:
                continue
            exit_price, exit_reason = outcome
            exit_fill = exit_price - signal.direction * fill_cost
            exit_time = prepared.index[pos]
            status = "CLOSED"
            break

        if status == "OPEN" and day_positions:
            last_pos = day_positions[-1]
            last_mark = float(prepared.iloc[last_pos]["Close"])
            exit_time = prepared.index[last_pos]
            exit_fill = last_mark - signal.direction * fill_cost

        if exit_fill is not None and last_mark is not None:
            raw_exit = exit_price if exit_price is not None else last_mark
            if instrument is None:
                gross_pnl = (raw_exit - signal.entry) * signal.direction * units
                net_pnl = (
                    (exit_fill - entry_fill) * signal.direction * units
                    - 2.0 * execution.commission_per_unit * units
                )
            else:
                account_value_per_point = (
                    instrument.tick_value / instrument.tick_size * value_to_account_rate
                )
                gross_pnl = (
                    (raw_exit - signal.entry)
                    * signal.direction
                    * account_value_per_point
                    * units
                )
                net_pnl = (
                    (exit_fill - entry_fill)
                    * signal.direction
                    * account_value_per_point
                    * units
                    - 2.0 * execution.commission_per_unit * units
                )
            modeled_costs = gross_pnl - net_pnl
            mark_price = float(raw_exit)
        else:
            gross_pnl = net_pnl = modeled_costs = 0.0
            mark_price = signal.entry

        realized = net_pnl if status == "CLOSED" else 0.0
        unrealized = net_pnl if status == "OPEN" else 0.0
        risk_budget = units * risk_per_unit
        r_multiple = net_pnl / risk_budget if status == "CLOSED" and risk_budget else 0.0
        trades.append(
            {
                "Date": day.isoformat(),
                "Symbol": instrument.symbol if instrument is not None else "",
                "Quantity_Unit": instrument.quantity_unit if instrument is not None else "unit",
                "Entry_Time": signal.time.isoformat(),
                "Exit_Time": exit_time.isoformat() if exit_time is not None else "",
                "Direction": signal.side,
                "Entry": signal.entry,
                "Signal_Entry": signal.entry,
                "Entry_Fill": entry_fill,
                "Stop": signal.stop,
                "Target": signal.target,
                "Exit": exit_price if exit_price is not None else "",
                "Exit_Fill": exit_fill if exit_fill is not None else "",
                "Units": units,
                "Risk_Budget_$": round(risk_budget, 2),
                "Status": status,
                "Exit_Reason": exit_reason,
                "Gross_PnL_$": round(gross_pnl, 2),
                "Execution_Costs_$": round(modeled_costs, 2),
                "Realized_PnL_$": round(realized, 2),
                "Unrealized_PnL_$": round(unrealized, 2),
                "R_Multiple": round(r_multiple, 4),
                "Mark_Price": mark_price,
            }
        )
    return pd.DataFrame(trades)


def performance_summary(trades: pd.DataFrame) -> dict[str, float | int]:
    """Summarize closed trades only; open marks are excluded from realized metrics."""
    if trades.empty:
        return {
            "trades": 0, "closed": 0, "open": 0, "win_rate_pct": 0.0,
            "realized_pnl": 0.0, "max_drawdown": 0.0, "profit_factor": 0.0,
            "average_r": 0.0, "expectancy_r": 0.0, "execution_costs": 0.0,
        }
    closed = trades.loc[trades["Status"] == "CLOSED"].copy()
    pnl = closed["Realized_PnL_$"].astype(float)
    cumulative = pnl.cumsum()
    peak = cumulative.cummax().clip(lower=0)
    drawdown = cumulative - peak
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = abs(float(pnl[pnl < 0].sum()))
    profit_factor = gross_profit / gross_loss if gross_loss else (
        float("inf") if gross_profit else 0.0
    )
    r_values = (
        closed["R_Multiple"].astype(float)
        if "R_Multiple" in closed
        else pd.Series(dtype=float)
    )
    costs_total = (
        float(trades["Execution_Costs_$"].astype(float).sum())
        if "Execution_Costs_$" in trades else 0.0
    )
    average_r = float(r_values.mean()) if len(r_values) else 0.0
    return {
        "trades": int(len(trades)),
        "closed": int(len(closed)),
        "open": int((trades["Status"] == "OPEN").sum()),
        "win_rate_pct": float((pnl > 0).mean() * 100) if len(pnl) else 0.0,
        "realized_pnl": float(pnl.sum()) if len(pnl) else 0.0,
        "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
        "profit_factor": profit_factor,
        "average_r": average_r,
        "expectancy_r": average_r,
        "execution_costs": costs_total,
    }
