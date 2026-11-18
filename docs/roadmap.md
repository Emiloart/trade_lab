# Roadmap

This roadmap reflects the current state of the repository and the proposed evolution toward a research and monitoring platform. Items are plans, not implemented features.

## M0 — Baseline hardening (in progress)

- Shared Python package for configuration, indicators, strategy, data, sizing, sessions, state, and Telegram.
- New York timezone-aware session handling and completed-bar filtering.
- Validated atomic JSON state, recovery backup, same-day cache guard, and checkpointed Telegram delivery.
- Pytest and Ruff CI workflow.
- Review and resolve outstanding PR/CI findings before merging or enabling scheduled alerts.\n- Establish and maintain automated documentation contract verification.

## M1 — Documentation and operational clarity

- Document architecture, strategy, risk assumptions, data sources, configuration, operations, and development.\n- Verify documented commands, environment variables, CLI options, package modules, and workflow files against repository contents in CI.
- Replace stale README claims and make the project boundary explicit.
- Record known limitations and distinguish implemented behavior from planned work.

## M2 — Live/backtest parity

- Migrate historical simulation to the shared indicator and signal functions.
- Define candle-level stop/target collision semantics and end-of-day position handling.
- Add realistic spread, commission, slippage, and instrument sizing assumptions.
- Produce reproducible experiment metadata and out-of-sample evaluation.
- Remove or clearly label legacy scripts once their behavior is superseded.

## M3 — Durable event and trade journal

- Replace Actions cache as the authoritative state mechanism with durable database persistence.
- Store immutable signal, alert, manual execution, broker execution (if ever integrated), and P&L events separately.
- Add idempotency keys, event timestamps, strategy/configuration versions, and audit history.
- Retain JSON state only as a local development adapter if useful.

## M4 — Research and monitoring web application

- Build a read-only monitoring and research interface first.
- Show market/system status, signals, backtest runs, performance analytics, and a trade journal.
- Add authentication, authorization, audit logging, and secure secret handling before exposing access beyond a trusted private environment.
- Keep the Python engine independently runnable; the web application should not become the strategy execution authority.

## M5 — Controlled strategy operations

- Add versioned strategy configurations and explicit approval before a configuration becomes active.
- Support reproducible backtests and comparison between versions.
- Add alert delivery observability and health checks.
- Consider broker integration only as a separate, explicitly authorized project with sandbox validation, reconciliation, and fail-safe controls.

## Non-goals for the initial platform

- No automatic order execution.
- No claims of guaranteed returns or validated profitability.
- No public multi-tenant product until security, tenancy, compliance, and operational requirements are designed and reviewed.
