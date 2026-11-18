# Testing and verification

## What the current suite covers

The automated pytest suite is organized around the package boundaries:

| Area | Coverage focus |
| --- | --- |
| Data normalization | Timezone handling, column normalization, duplicate/incomplete rows |
| Instrument conversion | Newest shared timestamp and missing overlap |
| Indicators | VWAP grouping, true range, ATR rolling behavior |
| Strategy | Directional conditions, tolerance boundary, stop/target levels, session gating |
| Sessions | New York timezone, daylight-saving behavior, closed-bar and freshness rules |
| Sizing | Risk budget, lot-step rounding, minimum and maximum lot behavior |
| State and notifications | JSON persistence, daily closure, P&L accumulation, corruption handling, Telegram error handling |
| Live orchestration | One-alert rule, dry-run behavior, stale signals/data, conversion failure, retry behavior |

Tests use synthetic bars and fakes. They validate deterministic code behavior; they do not validate Yahoo Finance data quality, Telegram service availability, broker pricing, order execution, or profitability.

## Local verification

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check trade_lab tests
```

The CI workflow at `.github/workflows/ci.yml` runs pytest, Ruff, and `scripts/verify_docs.py` on pushes to main and refactor branches, pull requests, and manual dispatches. The documentation verifier checks local Markdown links, executable Python module/script paths and Ruff targets in fenced commands, CLI options, environment-variable references, the package module inventory, and workflow file references.

## Required checks for state and workflow changes

When changing persistence or Actions cache behavior, verify at least:

- A missing state file initializes as a new empty store.
- A malformed JSON file raises a state error and is not overwritten.
- An unsupported schema version fails closed.
- A successful scheduled run can save an application-created state file.
- A failed run cannot save a newly manufactured empty state file.
- A manual dry run does not write or save scheduled state.
- A cache miss before 10:00 New York time may initialize and checkpoint the empty first-run state.
- A cache miss at or after 10:00 New York time fails closed.
- A pending alert is checkpointed before Telegram is called.
- A pending alert restored from an earlier workflow attempt becomes `delivery_unknown` and is not sent again automatically.
- A successful send is followed by a final cache save; if that save fails, the pre-send pending checkpoint remains.

The workflow's conditional save is reviewed in source; GitHub Actions must also be checked for the exact commit after it runs.

## Required checks for strategy changes

- Unit tests for exact inequality boundaries and representative edge cases.
- Indicator tests across a New York date boundary and across daylight-saving changes.
- A documented comparison against the previous strategy version.
- Historical evaluation using the same data, timestamps, fees, and assumptions for both versions.
- Separate reporting of signal counts, hypothetical fills, and actual broker fills (if broker integration is later introduced).

Do not describe a green test suite as evidence of strategy profitability. Passing tests establish conformance to encoded rules, not whether those rules have positive expectancy.
