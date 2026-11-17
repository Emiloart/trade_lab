"""The VWAP pullback rule, defined once and used by live and backtest code."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import StrategyConfig
from .indicators import atr, session_vwap
from .sessions import in_window

LONG = 1
SHORT = -1


@dataclass(frozen=True)
class Signal:
    """A trade setup detected on a closed bar."""

    time: pd.Timestamp
    direction: int
    entry: float
    stop: float
    target: float
    risk_distance: float

    @property
    def side(self) -> str:
        return "LONG" if self.direction == LONG else "SHORT"


def prepare(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    """Return a copy of ``df`` with VWAP and ATR columns added."""
    out = df.sort_index().copy()
    out["VWAP"] = session_vwap(out)
    out["ATR"] = atr(out, cfg.atr_period)
    return out


def signal_for_bar(
    ts: pd.Timestamp, bar: pd.Series, cfg: StrategyConfig
) -> Signal | None:
    """Evaluate one closed bar that already has VWAP and ATR values.

    Long: the bar closes above VWAP after its low touched (or came within the
    tolerance of) VWAP. Short is the mirror image. Entry is the bar close.
    """
    vwap = bar["VWAP"]
    bar_atr = bar["ATR"]
    if pd.isna(vwap) or pd.isna(bar_atr) or bar_atr <= 0:
        return None

    close = float(bar["Close"])
    risk = cfg.atr_stop_mult * float(bar_atr)

    if close > vwap and float(bar["Low"]) <= vwap * (1 + cfg.vwap_tolerance):
        return Signal(
            time=ts,
            direction=LONG,
            entry=close,
            stop=close - risk,
            target=close + risk * cfg.reward_risk,
            risk_distance=risk,
        )
    if close < vwap and float(bar["High"]) >= vwap * (1 - cfg.vwap_tolerance):
        return Signal(
            time=ts,
            direction=SHORT,
            entry=close,
            stop=close + risk,
            target=close - risk * cfg.reward_risk,
            risk_distance=risk,
        )
    return None


def latest_signal(prepared: pd.DataFrame, cfg: StrategyConfig) -> Signal | None:
    """Signal for the newest bar of a prepared frame, only inside the window."""
    if prepared.empty:
        return None
    ts = prepared.index[-1]
    if not in_window(ts, cfg):
        return None
    return signal_for_bar(ts, prepared.iloc[-1], cfg)
