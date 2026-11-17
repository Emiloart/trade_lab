# Operations

## Local dry run

Install dependencies, then evaluate without Telegram delivery:

```bash
python -m pip install -e .
python -m trade_lab.live --dry-run
```

A dry run still requires the market-data request to succeed and the current time to pass the session/data/signal gates. It prints a message only when a valid, fresh setup is found. It does not send a Telegram message or record a sent/missed setup.

For a deterministic test timestamp:

```bash
python -m trade_lab.live --dry-run --now "2026-11-18T16:17:00Z"
```

The timestamp must be timezone-aware for unambiguous use; naive CLI values are treated as UTC.

## Telegram setup

1. Create a bot with Telegram's BotFather.
2. Obtain the bot token and destination chat ID.
3. Store them as environment variables locally or repository Actions secrets.
4. Run a dry run first; then verify delivery in a controlled private chat before enabling scheduled notifications.

The live monitor requires both `BOT_TOKEN` and `CHAT_ID`. Telegram errors are wrapped so the bot token is not included in logged exception text.

## GitHub Actions

The workflow at `.github/workflows/trading_bot.yml`:

- schedules weekday runs every five minutes across a broad UTC window;
- relies on the application to enforce the New York-local 10:00–15:00 window;
- serializes runs with a concurrency group;
- restores `.state/state.json` using date-scoped Actions cache keys and saves only after a successful scheduled run when the application has produced a state file;
- sends alerts for scheduled events and uses dry-run mode for manual dispatch.

Configure `BOT_TOKEN` and `CHAT_ID` in repository Actions secrets before expecting scheduled Telegram delivery. Manual dispatch is deliberately dry-run.

The cron schedule is not an exchange calendar. The application’s stale-data check is a secondary guard, not a holiday-calendar implementation. GitHub-hosted runners and Actions cache are operational dependencies and should not be treated as a durable always-on service. Scheduled workflows run from the repository's default branch; pushing this workflow to a feature branch does not activate that branch's schedule on the default branch. Manual dispatch remains dry-run.

## State and manual P&L

By default state is stored at `.state/state.json`. A missing file is treated as first-run state. An existing unreadable, malformed, structurally invalid, or unsupported-version file causes the monitor to stop with a non-zero exit; it is never silently replaced with an empty history. Locally, back up this file if you need to preserve alert history. Do not commit it if it contains personal trading records.

Record realized P&L manually:

```bash
python -m trade_lab.live --record-pnl -100
python -m trade_lab.live --record-pnl 45.50
```

Each command adds to the current New York date. The loss gate uses the accumulated value. There is no automatic import from a broker.

## Common statuses

| Status | Meaning |
| --- | --- |
| `outside_window` | Current time is outside configured New York session |
| `already_closed` | A sent or missed setup already closed the day |
| `daily_loss_limit` | Manually recorded realized loss reached the configured threshold |
| `data_error` | Provider request failed or returned unusable data |
| `stale_data` | Latest closed market-data bar is too old |
| `no_setup` | No qualifying setup on the current day |
| `missed_stale` | First setup was too old to alert; it was recorded as missed |
| `no_conversion` | QQQ and NQ have no shared usable bar timestamp |
| `below_min_lot` | Nominal risk budget cannot fund the configured minimum lot |
| `dry_run` | Alert was formatted but not sent or persisted |
| `send_failed` | Telegram delivery failed; the setup remains eligible for retry |
| `sent` | Telegram accepted the alert and state was recorded |

## Incident response

- If a Telegram token may have leaked, revoke it with BotFather and replace the Actions secret.
- If state is corrupt or unexpectedly missing, stop scheduled delivery while investigating; do not assume an empty state is safe because it can permit duplicate alerts. See [troubleshooting and recovery](troubleshooting.md) for the recovery procedure.
- If data timestamps or converted levels look wrong, disable scheduled delivery and inspect both QQQ and NQ source bars before resuming.
- If an alert was delivered but not recorded, a later run may resend it. Verify Telegram history before manually changing state.
- Never treat a GitHub Actions green check as evidence of strategy profitability or broker execution correctness.
