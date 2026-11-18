# Trade Lab

A Python market-monitoring and Telegram alerting system for a VWAP pullback strategy. Live monitoring and maintained historical backtests share one strategy implementation. Trade Lab does not yet place broker orders or reconcile live positions.

## Current capabilities

- New York timezone-aware session handling and completed-bar filtering.
- Shared VWAP, true-range, ATR, and first-signal logic for live monitoring and historical backtests.
- Configurable spread, slippage, and commission simulation with risk-adjusted sizing.
- Trade ledger with gross/net P&L, execution costs, risk budget, and R-multiple metrics.
- Telegram alerting with validated, checkpointed state persistence.
- Pytest, Ruff, and documentation verification in GitHub Actions.

## Important limitations

- Zero-cost backtests remain the default for backwards compatibility and are not realistic performance estimates.
- QQQ/NQ reference conversion is not a validated Exness US100 execution price.
- Historical input snapshots are not versioned; Yahoo Finance coverage and quality vary.
- No broker adapter or live order execution is implemented yet.
- A backtest is not evidence of profitability.

## Quick start

Requires Python 3.10 or newer.

```bash
git clone https://github.com/Emiloart/trade_lab.git
cd trade_lab
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\\Scripts\\Activate.ps1
```

Install:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the monitor

```bash
python -m trade_lab.live --dry-run
```

## Backtesting

```bash
python strategies/data_downloader.py
python backtests/vwap_backtest.py
python backtests/recent_backtest.py
```

See [Backtesting](docs/backtesting.md) for execution-cost assumptions and interpretation.

## Tests and lint

```bash
python -m pytest -q
ruff check .
python scripts/verify_docs.py
```

## Attribution

Maintained by **Emiloart**.
