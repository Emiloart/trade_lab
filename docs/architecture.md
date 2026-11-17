# Architecture

## System boundary

Trade Lab is a Python application that evaluates a VWAP pullback setup and can send a Telegram alert. GitHub Actions currently provides scheduled invocation. The application does not place orders or connect to a broker.

The main implementation is the `trade_lab/` package:

| Module | Responsibility |
| --- | --- |
| `config.py` | Immutable strategy/risk configuration and environment overrides |
| `data.py` | Yahoo Finance retrieval, OHLCV normalization, and cross-instrument ratio |
| `indicators.py` | Session VWAP, true range, and ATR |
| `sessions.py` | New York time handling, session window, closed-bar and freshness checks |
| `strategy.py` | VWAP pullback signal definition |
| `sizing.py` | Risk-based unit/lot sizing and daily loss comparison |
| `state.py` | Atomic JSON state persistence |
| `alert.py` | Human-readable Telegram alert formatting |
| `notify.py` | Telegram Bot API delivery |
| `live.py` | One-run orchestration and command-line interface |

## Live run sequence

1. Load configuration from defaults and supported environment variables.
2. Determine the current timestamp (UTC by default) and convert it to New York time for session decisions.
3. Stop if outside the configured 10:00–15:00 New York window.
4. Load JSON state; stop if the New York trading day is already closed by a sent or missed setup.
5. Apply the daily realized-loss gate using manually recorded P&L.
6. Fetch QQQ 5-minute bars, normalize timestamps to UTC, remove the still-open candle, and reject stale data.
7. Calculate session VWAP and ATR, then scan the current New York day for its first qualifying setup.
8. Reject and record a setup that is too old to alert, rather than moving to a later setup that would violate the one-setup-per-day rule.
9. Fetch NQ futures bars and calculate a price ratio at the newest timestamp shared by both instruments.
10. Scale the QQQ-derived levels, calculate CFD lot size using configured contract assumptions, and format the alert.
11. In dry-run mode, print the alert without sending or recording it. Otherwise send via Telegram and record the sent setup after successful delivery.

## Data flow

`Yahoo Finance → normalized QQQ bars → indicators → signal → NQ/QQQ ratio → scaled reference levels → lot estimate → Telegram`

The QQQ-to-NQ conversion is a ratio, not a broker-grade instrument mapping. The resulting levels may differ from the user's CFD quote. The alert explicitly warns the recipient to re-anchor levels to the actual fill.

## Persistence and consistency

`StateStore` writes a local JSON file using a temporary file followed by an atomic replace. It tracks sent or missed setups and manually entered realized P&L, retaining a limited recent history. A missing file initializes a new store; an existing unreadable, malformed, structurally invalid, or unsupported-version file raises `StateError` and stops the monitor. The application no longer treats corruption as an empty history.

On GitHub Actions, the workflow restores and saves this file through date-scoped Actions cache keys and serializes scheduled runs. This is a lightweight continuity mechanism, not a transactional database. Cache behavior is not equivalent to a durable event store or a multi-writer lock. A process interruption after Telegram accepts a message but before state is saved can result in a duplicate alert on a later run.

## Current boundaries

- No broker API, order placement, fill ingestion, or position reconciliation.
- No exchange holiday calendar; stale-data checks are the current protection against many no-session/outage cases.
- No database or web application.
- Existing scripts under `backtests/` are legacy implementations and have not yet been migrated to the package's strategy functions.
- No guarantee that Yahoo Finance QQQ/NQ data is suitable for execution or CFD pricing.
