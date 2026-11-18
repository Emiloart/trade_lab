# Running multi-instrument research

Run the walk-forward engine without writing a Python harness:

~~~bash
python -m trade_lab.research_cli --config research.json --output reports/walk-forward.csv
~~~

The JSON document contains positive train, validation, and test session counts;
optional step and final-holdout counts; a complete account-risk object; named
strategy variants; and a symbol-keyed instrument universe.

Every symbol requires:

- csv: OHLCV CSV path. Relative paths resolve from the JSON file's directory.
- data_source: vendor or collection method, symbol, interval, and adjustment policy.
- value_to_account_rate: explicit conversion from tick-value currency to account currency.
- instrument: actual venue tick and quantity economics.
- costs: explicit spread, slippage, and per-unit-per-side commission assumptions.

All instrument fields and all three cost fields are mandatory. Zero costs and a
conversion rate of 1.0 are accepted only when explicitly entered. The CLI does
not infer contract values from tickers or apply hidden zero-cost assumptions.
Unknown and duplicate JSON keys are rejected. CSV input uses the repository's
Datetime, Open, High, Low, Close, Volume format; timestamps are parsed as UTC.

Strategy parameters omitted from a variant use StrategyParameters defaults.
Optional filters are nested under that variant's strategy.filters object.
The report separates candidate training/validation rows, selected subsequent
test rows, and an optional final holdout row. Validation expectancy selects a
variant; test data does not participate in that window's selection.

The report is written to a temporary file in the destination directory,
flushed, then atomically replaces the destination. The command does not
download market data, verify broker specifications, or connect to a broker.

See docs/research.md for the research methodology and report interpretation.
Example numbers in any schema illustration are placeholders, not verified
market assumptions or recommendations.
