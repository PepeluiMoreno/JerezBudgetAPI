"""
Tests del motor OLAP babbage.
Testean el parsing de parámetros y la construcción de queries
sin necesidad de base de datos real.
"""
from __future__ import annotations

import pytest

from api.olap.query_engine import (
    parse_cut,
    parse_drilldown,
    parse_order,
    _resolve_column,
    _safe_col,
)
from api.olap.cube_model import MUNICIPAL_SPAIN_MODEL, JEREZ_RIGOR_MODEL, CUBE_REGISTRY


# ── Tests parse_cut ───────────────────────────────────────────────────────────

class TestParseCut:
    def test_single_filter(self):
        result = parse_cut("year.fiscal_year:2023")
        assert len(result) == 1
        assert result[0] == ("year", "fiscal_year", "2023")

    def test_multiple_filters(self):
        result = parse_cut("year.fiscal_year:2023|data_type.data_type:liquidation")
        assert len(result) == 2
        assert result[0] == ("year", "fiscal_year", "2023")
        assert result[1] == ("data_type", "data_type", "liquidation")

    def test_municipality_filter(self):
        result = parse_cut("municipality.ine_code:11020")
        assert result[0] == ("municipality", "ine_code", "11020")

    def test_empty_string_returns_empty(self):
        assert parse_cut("") == []
        assert parse_cut(None) == []

    def test_no_dot_in_key(self):
        result = parse_cut("fiscal_year:2023")
        assert result[0] == ("fiscal_year", "fiscal_year", "2023")

    def test_value_with_spaces_preserved(self):
        result = parse_cut("municipality.name:Jerez de la Frontera")
        assert result[0][2] == "Jerez de la Frontera"

    def test_range_value(self):
        result = parse_cut("year.fiscal_year:2020;2024")
        assert result[0] == ("year", "fiscal_year", "2020;2024")


# ── Tests parse_drilldown ─────────────────────────────────────────────────────

class TestParseDrilldown:
    def test_single_dimension(self):
        result = parse_drilldown("municipality.ine_code")
        assert result == [("municipality", "ine_code")]

    def test_multiple_dimensions(self):
        result = parse_drilldown("year.fiscal_year|chapter.chapter")
        assert result == [("year", "fiscal_year"), ("chapter", "chapter")]

    def test_no_dot(self):
        result = parse_drilldown("municipality")
        assert result == [("municipality", "municipality")]

    def test_empty_returns_empty(self):
        assert parse_drilldown(None) == []
        assert parse_drilldown("") == []

    def test_three_dimensions(self):
        result = parse_drilldown(
            "municipality.ine_code|year.fiscal_year|chapter.chapter"
        )
        assert len(result) == 3


# ── Tests parse_order ─────────────────────────────────────────────────────────

class TestParseOrder:
    def test_single_desc(self):
        result = parse_order("executed_per_capita:desc")
        assert result == [("executed_per_capita", "DESC")]

    def test_multiple_orders(self):
        result = parse_order("fiscal_year:asc|executed_amount:desc")
        assert len(result) == 2
        assert result[0] == ("fiscal_year", "ASC")
        assert result[1] == ("executed_amount", "DESC")

    def test_default_direction_desc(self):
        result = parse_order("executed_amount")
        assert result[0][1] == "DESC"

    def test_invalid_direction_defaults_to_desc(self):
        result = parse_order("fiscal_year:invalid")
        assert result[0][1] == "DESC"

    def test_empty_returns_empty(self):
        assert parse_order(None) == []


# ── Tests _resolve_column ─────────────────────────────────────────────────────

class TestResolveColumn:
    def test_municipality_ine_code(self):
        col = _resolve_column(MUNICIPAL_SPAIN_MODEL, "municipality", "ine_code")
        assert col == "m.ine_code"

    def test_year_fiscal_year(self):
        col = _resolve_column(MUNICIPAL_SPAIN_MODEL, "year", "fiscal_year")
        assert col == "mb.fiscal_year"

    def test_chapter_column(self):
        col = _resolve_column(MUNICIPAL_SPAIN_MODEL, "chapter", "chapter")
        assert col == "mbc.chapter"

    def test_unknown_dimension_returns_none(self):
        col = _resolve_column(MUNICIPAL_SPAIN_MODEL, "nonexistent", "attr")
        assert col is None

    def test_unknown_attr_returns_none(self):
        col = _resolve_column(MUNICIPAL_SPAIN_MODEL, "municipality", "nonexistent_attr")
        assert col is None

    def test_rigor_model_score(self):
        col = _resolve_column(JEREZ_RIGOR_MODEL, "global_rigor_score", "global_rigor_score")
        # La medida está en measures, no en dimensions
        assert col is not None

    def test_ccaa_attribute(self):
        col = _resolve_column(MUNICIPAL_SPAIN_MODEL, "municipality", "ccaa")
        assert col == "m.ccaa_name"


# ── Tests _safe_col ───────────────────────────────────────────────────────────

class TestSafeCol:
    def test_simple_column(self):
        assert _safe_col("m.ine_code") == "m.ine_code"

    def test_with_function(self):
        assert _safe_col("SUM(mbc.executed_amount)") == "SUM(mbc.executed_amount)"

    def test_raises_on_injection(self):
        with pytest.raises(ValueError):
            _safe_col("m.ine_code; DROP TABLE municipalities;--")

    def test_raises_on_semicolon(self):
        with pytest.raises(ValueError):
            _safe_col("col; DELETE")


# ── Tests CUBE_REGISTRY ───────────────────────────────────────────────────────

class TestCubeRegistry:
    def test_all_required_cubes_present(self):
        required = {
            "municipal-spain",
            "municipal-spain-func",
            "jerez-detail",
            "jerez-rigor",
        }
        assert required.issubset(set(CUBE_REGISTRY.keys()))

    def test_each_cube_has_model(self):
        for name, info in CUBE_REGISTRY.items():
            assert "model" in info, f"Cubo {name} sin 'model'"

    def test_each_model_has_dimensions(self):
        for name, info in CUBE_REGISTRY.items():
            assert "dimensions" in info["model"], f"Cubo {name} sin 'dimensions'"

    def test_each_model_has_measures(self):
        for name, info in CUBE_REGISTRY.items():
            assert "measures" in info["model"], f"Cubo {name} sin 'measures'"

    def test_each_model_has_fact_table(self):
        for name, info in CUBE_REGISTRY.items():
            assert "fact_table" in info["model"], f"Cubo {name} sin 'fact_table'"

    def test_municipal_spain_has_key_dimensions(self):
        model = CUBE_REGISTRY["municipal-spain"]["model"]
        dims = model["dimensions"]
        assert "municipality" in dims
        assert "year" in dims
        assert "chapter" in dims
        assert "data_type" in dims

    def test_jerez_rigor_has_all_indices(self):
        model = CUBE_REGISTRY["jerez-rigor"]["model"]
        measures = model["measures"]
        assert "global_rigor_score" in measures
        assert "precision_index" in measures
        assert "timeliness_index" in measures
        assert "transparency_index" in measures

    def test_cube_info_has_period(self):
        for name, info in CUBE_REGISTRY.items():
            assert "period" in info, f"Cubo {name} sin 'period'"

    def test_municipal_spain_period(self):
        assert "2010" in CUBE_REGISTRY["municipal-spain"]["period"]

    def test_jerez_cubes_period(self):
        assert "2020" in CUBE_REGISTRY["jerez-detail"]["period"]
        assert "2020" in CUBE_REGISTRY["jerez-rigor"]["period"]
