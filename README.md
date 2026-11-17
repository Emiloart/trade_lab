# Trade Lab

A Python-based market-monitoring and Telegram alerting system for a VWAP pullback strategy. The live monitor evaluates completed 5-minute QQQ bars during a New York session window, derives reference levels using a timestamp-aligned QQQ/NQ price ratio, estimates CFD position size from configured risk assumptions, and can send a Telegram alert.

**Trade Lab is an alerting system, not an automated trading system.** It does not place orders, observe broker fills, or reconcile account positions.

## Current capabilities

- New York timezone-aware session handling, including daylight-saving changes.
- Session VWAP, New York-date gap-excluding true range, and a rolling ATR (which can include prior-date bars).
- Long/short pullback signal rules with one first setup per New York trading day.
- Filtering of in-progress candles and stale market data.
- Risk-based lot estimates rounded down to the configured lot step.
- Telegram delivery with credentials supplied through environment variables.
- Atomic JSON state writes; invalid existing state fails closed rather than resetting alert history.
- GitHub Actions cache continuity between successful scheduled runs, without creating empty fallback state.
- Pytest suite and Ruff lint checks in GitHub Actions.

## Important limitations

- QQQ is the signal source; NQ futures are used to scale reference levels. This is an approximation, not a validated mapping to every broker's US100/NAS100 CFD.
- Contract value, lot size, and account currency assumptions must be verified against the actual broker.
- The daily loss gate depends on manually recorded realized P&L. There is no broker/account integration.
- JSON state plus GitHub Actions cache is not a transactional database. A crash after Telegram accepts an alert but before state is saved can permit a duplicate alert. Corrupt or unsupported state stops the monitor rather than silently resetting history.
- Historical scripts under `backtests/` have not yet been migrated to the shared strategy package. Their results are not guaranteed to match live behavior.
- The small historical sample previously shown in this repository is not evidence of strategy robustness or profitability.

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
.venv\Scripts\Activate.ps1
```

Install the package and development tools:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Configuration

The live monitor uses these environment variables:

| Variable | Default | Description |
| --- | ---: | --- |
| `ACCOUNT_SIZE` | `10000` | Nominal account value used for sizing |
| `RISK_PERCENTAGE` | `0.01` | Risk budget per setup |
| `MAX_DAILY_LOSS_PERCENTAGE` | `0.02` | Daily realized-loss threshold |
| `REWARD_RISK` | `1.3` | Target multiple of stop distance |
| `ATR_STOP_MULT` | `1.5` | ATR stop multiplier |
| `POINT_VALUE_PER_LOT` | `10` | Assumed value per point per lot |
| `MIN_LOT` | `0.01` | Minimum lot |
| `LOT_STEP` | `0.01` | Lot increment |
| `BOT_TOKEN` | — | Telegram bot token |
| `CHAT_ID` | — | Telegram destination chat ID |
| `STATE_FILE` | `.state/state.json` | Optional state-file override |

Set Telegram credentials in your shell or repository Actions secrets. Never commit credentials or state files.

PowerShell example:

```powershell
$env:BOT_TOKEN = "your_bot_token"
$env:CHAT_ID = "your_chat_id"
```

See [Configuration](docs/configuration.md) for all supported settings and validation details.

## Run the monitor

Run a dry evaluation without sending a Telegram message or writing an alert record:

```bash
python -m trade_lab.live --dry-run
```

Use an explicit timestamp for a reproducible check:

```bash
python -m trade_lab.live --dry-run --now "2026-11-18T16:17:00Z"
```

A live run requires both Telegram variables:

```bash
python -m trade_lab.live
```

The GitHub Actions workflow sends alerts on scheduled events. Manual workflow dispatch runs in dry-run mode. Configure `BOT_TOKEN` and `CHAT_ID` as repository Actions secrets before enabling scheduled delivery.

### Record realized P&L

The daily loss gate uses manually entered realized P&L; it does not read broker results:

```bash
python -m trade_lab.live --record-pnl -100
python -m trade_lab.live --record-pnl 45.50
```

Amounts accumulate against the current New York trading date.

## Tests and lint

```bash
python -m pytest
ruff check trade_lab tests
```

## Backtesting

The repository contains standalone historical scripts and a Yahoo Finance downloader. Generate the local input data first:

```bash
python strategies/data_downloader.py
python backtests/recent_backtest.py
```

The downloader writes `data/us100_5m.csv`; downloaded data is not committed. **Backtest/live parity is not yet complete.** Review [Backtesting](docs/backtesting.md) before interpreting any result.

## Documentation

- [Documentation index](docs/README.md)
- [Architecture](docs/architecture.md)
- [Strategy specification](docs/strategy.md)
- [Risk management](docs/risk-management.md)
- [Data sources and instrument mapping](docs/data-sources.md)
- [Configuration](docs/configuration.md)
- [Operations](docs/operations.md)
- [Backtesting](docs/backtesting.md)
- [Development](docs/development.md)
- [Roadmap](docs/roadmap.md)
- [Engineering decisions](docs/decisions.md)
- [Testing and verification](docs/testing.md)
- [Troubleshooting and recovery](docs/troubleshooting.md)

## Roadmap

The next major engineering priority is to migrate historical simulation onto the shared strategy implementation and establish reproducible, realistic backtesting. A durable event journal/database should follow before building a web research and monitoring interface. Automated broker execution is explicitly outside the initial scope.

## Attribution

Maintained by **Emiloart**.
