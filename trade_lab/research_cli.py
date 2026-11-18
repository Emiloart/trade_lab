"""Configuration-driven command line for reproducible multi-instrument research."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import fields
from datetime import time
from pathlib import Path
from typing import Any

from .backtest import BacktestCosts, load_csv
from .config import AccountRiskConfig, StrategyParameters
from .filters import StrategyFilters
from .instruments import AssetClass, InstrumentSpec
from .research import ResearchVariant, run_walk_forward_research


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _keys(value: Mapping[str, Any], allowed: set[str], required: set[str], label: str) -> None:
    unknown, missing = set(value) - allowed, required - set(value)
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {sorted(unknown)}")
    if missing:
        raise ValueError(f"{label} is missing required fields: {sorted(missing)}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strategy(raw: Any, label: str) -> StrategyParameters:
    values = dict(_object(raw, label))
    _keys(values, {f.name for f in fields(StrategyParameters)}, set(), label)
    filters = _object(values.pop("filters", {}), f"{label}.filters")
    _keys(filters, {f.name for f in fields(StrategyFilters)}, set(), f"{label}.filters")
    for name in ("session_start", "session_end"):
        if name in values:
            try:
                values[name] = time.fromisoformat(values[name])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{label}.{name} must be an ISO time") from exc
    return StrategyParameters(filters=StrategyFilters(**filters), **values)


def _instrument(raw: Any, symbol: str) -> InstrumentSpec:
    values = dict(_object(raw, f"symbols.{symbol}.instrument"))
    required = {
        "asset_class", "quote_currency", "tick_size", "tick_value",
        "tick_value_currency", "quantity_unit", "min_quantity",
        "quantity_step", "max_quantity",
    }
    _keys(values, required | {"symbol"}, required, f"symbols.{symbol}.instrument")
    values["symbol"] = values.get("symbol", symbol)
    try:
        values["asset_class"] = AssetClass(values["asset_class"])
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in AssetClass)
        raise ValueError(f"asset_class must be one of: {choices}") from exc
    return InstrumentSpec(**values)


def _load(path: Path) -> dict[str, Any]:
    try:
        return _object(
            json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object),
            "configuration",
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def run_from_config(config_path: str | Path, output_path: str | Path) -> int:
    """Run the configured research universe and atomically write its CSV report."""
    source_path = Path(config_path).expanduser().resolve()
    config = _load(source_path)
    allowed = {
        "train_days", "validation_days", "test_days", "step_days",
        "final_holdout_days", "risk", "variants", "symbols",
    }
    required = {"train_days", "validation_days", "test_days", "risk", "variants", "symbols"}
    _keys(config, allowed, required, "configuration")

    risk_values = _object(config["risk"], "risk")
    risk_fields = {f.name for f in fields(AccountRiskConfig)}
    _keys(risk_values, risk_fields, risk_fields, "risk")
    risk = AccountRiskConfig(**risk_values)

    raw_variants = config["variants"]
    if not isinstance(raw_variants, list) or not raw_variants:
        raise ValueError("variants must be a non-empty JSON array")
    variants = []
    for index, raw in enumerate(raw_variants):
        label = f"variants[{index}]"
        item = _object(raw, label)
        _keys(item, {"name", "strategy"}, {"name", "strategy"}, label)
        if not isinstance(item["name"], str):
            raise ValueError(f"{label}.name must be a string")
        strategy = _strategy(item["strategy"], f"{label}.strategy")
        variants.append(ResearchVariant(item["name"], strategy))

    raw_symbols = _object(config["symbols"], "symbols")
    if not raw_symbols:
        raise ValueError("symbols must contain at least one instrument")
    datasets, instruments, costs, rates, sources = {}, {}, {}, {}, {}
    for symbol, item_raw in raw_symbols.items():
        if not symbol.strip():
            raise ValueError("symbol keys cannot be empty")
        label = f"symbols.{symbol}"
        item = _object(item_raw, label)
        required_item = {"csv", "data_source", "instrument", "costs", "value_to_account_rate"}
        _keys(item, required_item, required_item, label)
        if not isinstance(item["csv"], str) or not item["csv"].strip():
            raise ValueError(f"{label}.csv must be a non-empty path")
        if not isinstance(item["data_source"], str) or not item["data_source"].strip():
            raise ValueError(f"{label}.data_source must describe provenance")
        rate = item["value_to_account_rate"]
        invalid_rate = (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not math.isfinite(rate)
            or rate <= 0
        )
        if invalid_rate:
            raise ValueError(f"{label}.value_to_account_rate must be a positive finite number")
        csv_path = Path(item["csv"]).expanduser()
        if not csv_path.is_absolute():
            csv_path = source_path.parent / csv_path
        datasets[symbol] = load_csv(csv_path)
        instruments[symbol] = _instrument(item["instrument"], symbol)
        cost_values = _object(item["costs"], f"{label}.costs")
        cost_fields = {f.name for f in fields(BacktestCosts)}
        _keys(cost_values, cost_fields, cost_fields, f"{label}.costs")
        costs[symbol] = BacktestCosts(**cost_values)
        rates[symbol], sources[symbol] = rate, item["data_source"]

    report = run_walk_forward_research(
        datasets=datasets, instruments=instruments, costs=costs, variants=variants,
        train_days=config["train_days"], validation_days=config["validation_days"],
        test_days=config["test_days"], step_days=config.get("step_days"),
        value_to_account_rates=rates, risk=risk, data_sources=sources,
        final_holdout_days=config.get("final_holdout_days", 0),
    )
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", suffix=".tmp",
            prefix=f".{destination.name}.", dir=destination.parent, delete=False,
        ) as temporary:
            temporary_name = temporary.name
            report.to_csv(temporary, index=False)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    print(f"Research report written: {destination}")
    print(f"Symbols: {', '.join(datasets)}")
    print(f"Rows: {len(report)}; roles: {report['role'].value_counts().to_dict()}")
    print("Historical simulation only; this is not evidence of future performance.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run multi-instrument VWAP walk-forward research.")
    parser.add_argument("--config", required=True, help="JSON research configuration.")
    parser.add_argument("--output", required=True, help="Destination CSV report.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_from_config(args.config, args.output)
    except (OSError, TypeError, ValueError) as exc:
        print(f"research failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
