from trade_lab.backtest import BacktestCosts
from trade_lab.config import StrategyConfig
from trade_lab.research import ResearchVariant, run_walk_forward_research

from tests.test_research import bars_for_sessions, instrument


def test_walk_forward_reports_uncertainty_sensitivity_and_cost_stress():
    report = run_walk_forward_research(
        {"ETF": bars_for_sessions(12)},
        {"ETF": instrument("ETF")},
        {"ETF": BacktestCosts(spread_points=0.02, slippage_points=0.01)},
        [
            ResearchVariant("baseline", StrategyConfig(atr_period=1), "atr-neighborhood"),
            ResearchVariant("alternate", StrategyConfig(atr_period=2), "atr-neighborhood"),
        ],
        train_days=4,
        validation_days=2,
        test_days=2,
        step_days=2,
        data_sources={"ETF": "synthetic fixture, 5m"},
        bootstrap_samples=200,
        bootstrap_block_length=2,
        cost_stress_multipliers=(1.0, 2.0),
    )
    candidates = report.loc[report["role"] == "candidate"]
    selected = report.loc[report["role"] == "selected_test"]
    assert candidates["validation_sample_trades"].notna().all()
    assert candidates["validation_adjusted_expectancy_ci_low"].notna().all() or (
        candidates["validation_sample_days"].eq(0).any()
    )
    assert candidates["sensitivity_group"].eq("atr-neighborhood").all()
    assert candidates["sensitivity_variant_count"].eq(2).all()
    assert selected["decision"].eq("REJECT").all()
    assert "test_cost_2x_adjusted_ci_low" in selected.columns
    assert "COST_STRESS_FAILURE" in ";".join(selected["rejection_reasons"].astype(str))
