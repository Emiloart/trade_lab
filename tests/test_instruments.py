import pytest

from trade_lab.instruments import AssetClass, InstrumentSpec


def stock():
    return InstrumentSpec(
        symbol="AAPL",
        asset_class=AssetClass.EQUITY,
        quote_currency="USD",
        tick_size=0.01,
        tick_value=0.01,
        tick_value_currency="USD",
        quantity_unit="share",
        min_quantity=1,
        quantity_step=1,
        max_quantity=100_000,
    )


def cfd():
    return InstrumentSpec(
        symbol="US100",
        asset_class=AssetClass.INDEX_CFD,
        quote_currency="USD",
        tick_size=0.1,
        tick_value=1.0,
        tick_value_currency="USD",
        quantity_unit="lot",
        min_quantity=0.01,
        quantity_step=0.01,
        max_quantity=100,
    )


def test_stock_and_cfd_have_independent_contract_economics():
    assert stock().risk_per_quantity(1.0) == pytest.approx(1.0)
    assert cfd().risk_per_quantity(1.0) == pytest.approx(10.0)


def test_tick_value_conversion_to_account_currency():
    assert stock().risk_per_quantity(1.0, value_to_account_rate=1.5) == pytest.approx(1.5)


def test_price_cost_conversion():
    assert cfd().price_cost_per_quantity(0.2) == pytest.approx(2.0)


@pytest.mark.parametrize("kwargs", [
    {"tick_size": 0},
    {"tick_value": -1},
    {"min_quantity": 0},
    {"quantity_step": float("inf")},
    {"max_quantity": 0.001},
])
def test_invalid_instrument_economics_are_rejected(kwargs):
    values = dict(
        symbol="TEST", asset_class=AssetClass.OTHER, quote_currency="USD",
        tick_size=0.01, tick_value=0.01, tick_value_currency="USD",
        quantity_unit="unit", min_quantity=1, quantity_step=1, max_quantity=10,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        InstrumentSpec(**values)
