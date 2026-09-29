"""Tests for actorio_cli.commands._filters.build_params — the shared
mapping from tool/CLI arguments to webapp query params."""

import pytest
from actorio_cli.commands._filters import build_params


def test_empty():
    assert build_params() == {}


def test_none_values_dropped():
    assert build_params(country=None, marketplace=None, query=None) == {}


def test_empty_string_dropped():
    assert build_params(query="") == {}


def test_bool_true_becomes_string_true():
    params = build_params(missing_fba=True, multipack=True, hazmat=True,
                          variations=True, suppressed_buybox=True, actorio_only=True)
    assert params == {
        "missing_fba": "true",
        "multipack": "true",
        "hazmat": "true",
        "variations": "true",
        "suppressed_buybox": "true",
        "actorio_only": "true",
    }


def test_bool_false_dropped():
    """False boolean filters are not sent (they mean 'no filter')."""
    params = build_params(missing_fba=False, multipack=False)
    assert "missing_fba" not in params
    assert "multipack" not in params


def test_string_values_passthrough():
    params = build_params(query="lego", country="DE", marketplace="ES")
    assert params == {"query": "lego", "country": "DE", "marketplace": "ES"}


def test_numeric_values_passthrough():
    params = build_params(roi_min=30, profit_min=5.5, price_max=100)
    assert params == {"roi_min": 30, "profit_min": 5.5, "price_max": 100}


def test_numeric_zero_passthrough():
    """0 is a valid filter value (not falsy in the same way as None/'')."""
    params = build_params(roi_min=0, price_min=0)
    assert params == {"roi_min": 0, "price_min": 0}


def test_list_values_passthrough():
    params = build_params(store=["shop1", "shop2"], category=["toys", "games"])
    assert params == {"store": ["shop1", "shop2"], "category": ["toys", "games"]}


def test_tuple_values_passthrough():
    params = build_params(size=("LGT_ENV", "STD_ENV"))
    # Tuples pass through as-is (same isinstance check as list)
    assert params == {"size": ["LGT_ENV", "STD_ENV"]}


def test_empty_list_dropped():
    params = build_params(store=[], category=[])
    assert "store" not in params
    assert "category" not in params


def test_mixed_values():
    params = build_params(
        query="test",
        country="DE",
        roi_min=25.0,
        missing_fba=True,
        multipack=False,
        category=["toys"],
        store=[],
        size_tier=None,
    )
    assert params == {
        "query": "test",
        "country": "DE",
        "roi_min": 25.0,
        "missing_fba": "true",
        "category": ["toys"],
    }


def test_sort_param_passthrough():
    params = build_params(sort="-profit")
    assert params == {"sort": "-profit"}


def test_last_update_enum_passthrough():
    params = build_params(last_update="48")
    assert params == {"last_update": "48"}


def test_price_reference_enum_passthrough():
    params = build_params(price_reference="avg30")
    assert params == {"price_reference": "avg30"}


def test_competitive_price_range():
    params = build_params(competitive_price_min=10.0, competitive_price_max=50.0)
    assert params == {"competitive_price_min": 10.0, "competitive_price_max": 50.0}


def test_profit_month_range():
    params = build_params(profit_month_min=100, profit_month_max=500)
    assert params == {"profit_month_min": 100, "profit_month_max": 500}


def test_sales_month_range():
    params = build_params(sales_month_min=50, sales_month_max=200)
    assert params == {"sales_month_min": 50, "sales_month_max": 200}


def test_similarity_passthrough():
    params = build_params(similarity=2)
    assert params == {"similarity": 2}
