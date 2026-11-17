# Backtesting

## Current state

The repository contains historical scripts under `backtests/`, including:

- `backtests/vwap_backtest.py`
- `backtests/recent_backtest.py`
- `backtests/monthly_seasonality.py`
- `backtests/analyze_live_trades.py`
- `backtests/verify_recent_trade.py`

The data downloader is `strategies/data_downloader.py`. It downloads QQQ 5-minute data from Yahoo Finance and writes `data/us100_5m.csv`. The `data/` directory and downloaded market data are not included in the tracked source tree; generate the input locally before running scripts that require it.

## Important parity warning

The legacy backtest scripts contain their own indicator, session, entry, stop, target, and trade-simulation logic. They are not currently wired to the `trade_lab.strategy` and `trade_lab.indicators` package functions used by the live monitor.

Their behavior also differs across versions. For example, the legacy scripts have used different reward/risk values, risk budgets, ATR calculations, and local-time assumptions. Do not interpret their output as a verified simulation of the current live monitor.

Migrating the backtests to call the shared strategy implementation is a required engineering milestone before using historical results to assess the live strategy.

## Data preparation

From the repository root:

```bash
python strategies/data_downloader.py
```

This requires network access and the yfinance dependency. Yahoo Finance intraday history is limited and can change; record the downloaded date range and provider assumptions alongside any experiment.

## Running a legacy backtest

The scripts are currently standalone Python files. A representative invocation is:

```bash
python backtests/recent_backtest.py
```

Inspect each script's constants and expected input path before running it. Some scripts write result CSV files under the `data/` directory. The repository does not currently provide a unified backtest CLI or a reproducible experiment manifest.

## Interpreting results

A backtest result is only as meaningful as its data, assumptions, and execution model. Before treating a result as evidence, document:

- source symbol, provider, download timestamp, timezone, interval, and date range;
- exact strategy/configuration version and parameter values;
- entry timing and whether the signal bar close is realistically executable;
- stop/target ordering when both levels are touched within one candle;
- spread, commission, slippage, financing, and gaps;
- position sizing, contract multiplier, lot rounding, and currency;
- treatment of unclosed positions, missing bars, holidays, and look-ahead bias;
- trade count, expectancy, profit factor, drawdown, and out-of-sample results.

The README's previously displayed six-trade sample is not sufficient to establish statistical significance, robustness, or profitability. It should not be presented as proof that risk logic is “bulletproof.”

## Planned direction

The backtest runner should consume the same signal and indicator functions as live monitoring, while keeping execution simulation explicit and independently testable. Historical signals, simulated trades, alerts, and broker-confirmed trades must remain distinct record types.
