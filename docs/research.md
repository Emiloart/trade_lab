# Strategy research and validation

## Configuration and instrument boundary

New research code separates `StrategyParameters` from `AccountRiskConfig`.
The live monitor retains the combined `StrategyConfig` as a backwards-compatible
adapter, including legacy CFD lot-sizing fields. Backtests accept the separated
objects directly. Research runs must supply an explicit
`InstrumentSpec` and `BacktestCosts` for every symbol. Never infer tick
economics from a ticker or reuse one instrument's costs for another.

## Optional filters

`StrategyFilters` exposes opt-in, instrument-independent criteria. All are
disabled by default. Pullback depth is measured in ATR units; directional VWAP
slope is normalized by ATR; ATR percentage is ATR divided by absolute close.
They are candidate filters, not established improvements.

## Walk-forward research

Use `trade_lab.research.run_walk_forward_research` with symbol-keyed OHLCV
datasets, instrument specifications, and execution costs. Supply an explicit
list of `ResearchVariant` configurations. The runner creates chronological
expanding-history windows, reports candidate training and validation metrics,
selects by validation expectancy in R, then evaluates the selected variant on
the subsequent test interval. Test data does not participate in selection.

```python
from trade_lab.backtest import BacktestCosts
from trade_lab.config import StrategyConfig
from trade_lab.filters import StrategyFilters
from trade_lab.research import ResearchVariant, run_walk_forward_research

variants = [
    ResearchVariant("baseline", StrategyConfig()),
    ResearchVariant("shallow-pullback", StrategyConfig(
        filters=StrategyFilters(max_pullback_atr=0.5)
    )),
]
report = run_walk_forward_research(
    datasets={"SYMBOL_A": bars_a, "SYMBOL_B": bars_b},
    instruments={"SYMBOL_A": spec_a, "SYMBOL_B": spec_b},
    costs={
        "SYMBOL_A": BacktestCosts(spread_points=spread_a, slippage_points=slippage_a,
                                  commission_per_unit=commission_a),
        "SYMBOL_B": BacktestCosts(spread_points=spread_b, slippage_points=slippage_b,
                                  commission_per_unit=commission_b),
    },
    variants=variants, train_days=120, validation_days=20,
    test_days=20, step_days=20,
)
report.to_csv("walk_forward_report.csv", index=False)
```

The caller must document each symbol's actual instrument specification,
account-currency conversion rate, spread, slippage, commission, and data
provenance. No placeholder economics should be presented as observed costs.

## Limitations and interpretation

- The live monitor still assumes QQQ signal bars and NQ reference-price
  conversion. It is not a generic multi-instrument live monitor.
- `StrategyConfig` still contains legacy risk and lot fields; a clean
  strategy/risk/account configuration migration remains outstanding.
- No verified multi-instrument historical datasets or broker cost schedules
  are bundled. This repository therefore cannot yet support a factual
  cross-instrument performance conclusion.
- Reclaim quality still needs a predefined outcome study (post-reclaim
  excursion, adverse excursion, and follow-through at fixed horizons).
- Rolling test windows are out-of-sample relative to their own validation
  selection, but are not one untouched final holdout. Reserve a later,
  untouched date range for final confirmation.
