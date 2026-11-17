# Strategy specification

## Instrument and timeframe

The live monitor uses Yahoo Finance 5-minute bars for QQQ as the signal instrument and NQ futures (`NQ=F`) as the reference instrument for scaling alert levels. The alert labels the result as a US100 setup, but this does not make QQQ, NQ futures, and a broker's US100/ NAS100 CFD interchangeable.

## Session

The default signal window is 10:00 inclusive to 15:00 exclusive in `America/New_York`. The IANA timezone is used so daylight-saving transitions are handled by the runtime. Bars are timestamped in UTC after normalization.

## Indicators

### Session VWAP

For each New York calendar date, the implementation computes cumulative typical-price volume divided by cumulative volume:

`Typical Price = (High + Low + Close) / 3`

`VWAP = cumulative(Typical Price × Volume) / cumulative(Volume)`

The calculation resets by New York calendar date and accumulates from the first bar returned for that date. It does not explicitly enforce a 09:30 New York cash-session reset; the current Yahoo Finance request uses the provider's default regular-session behavior. A zero cumulative volume produces an undefined VWAP rather than an invented price.

### ATR

True range is the maximum of high-low, absolute high minus previous close, and absolute low minus previous close. The previous close is grouped by New York calendar date, so the first bar of a new date uses high-low only. ATR is a simple rolling mean over the resulting true-range series with a default period of 14 bars. The rolling ATR window is not grouped or reset by date; it can include true-range observations from the prior date.

## Entry signal

A signal is evaluated only on a completed bar with valid VWAP and ATR.

- Long: close is above VWAP and the bar low is at or below VWAP × (1 + tolerance).
- Short: close is below VWAP and the bar high is at or above VWAP × (1 − tolerance).

The default VWAP tolerance is 0.001 (0.1%). Entry reference is the signal bar close.

## Stop and target

Risk distance is `ATR × ATR_STOP_MULT`. The default multiplier is 1.5.

- Long stop = entry − risk distance; target = entry + risk distance × reward/risk.
- Short stop = entry + risk distance; target = entry − risk distance × reward/risk.

The default reward/risk multiple is 1.3.

## Frequency and signal selection

The strategy takes at most one setup per New York trading day. The shared `first_signal` function scans in-window bars in chronological order and returns the first qualifying setup. The live monitor uses that first setup even when it is no longer fresh; if too old, it records it as missed instead of selecting a later setup.

The monitor removes the current in-progress 5-minute bar before evaluating. It also rejects data whose latest closed bar is more than 15 minutes old and rejects signals more than 10 minutes past the end of their bar.

## Important distinction

A detected signal is a rule match, not proof of an executable trade. The live system sends a reference alert; it does not establish whether an order was placed, whether it filled, or what slippage occurred. Backtest scripts currently have separate logic and must not be assumed to produce results identical to live monitoring.
