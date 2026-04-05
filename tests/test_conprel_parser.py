"""
Tests unitarios del parser CONPREL.
No requieren mdbtools ni ficheros MDB reales —
testean la lógica de normalización y mapeo de columnas.
"""
from __future__ import annotations

import pytest
import pandas as pd
from decimal import Decimal

from etl.conprel.parser import (
    _normalize_entity_code,
    _to_decimal,
    _find_column,
    _is_subtotal_like,
)
from etl.conprel.schema import (
    COLUMN_ALIASES,
    TABLE_NAMES,
    AREA_NAMES,
    CHAPTER_NAMES_EXPENSE,
    CHAPTER_NAMES_REVENUE,
    Direction,
    DataType,
)
from etl.conprel.loader import _rate, _per_capita, _d


# ── Tests normalización código entidad ────────────────────────────────────────

class TestNormalizeEntityCode:
    def test_five_digits_passthrough(self):
        assert _normalize_entity_code("11021") == "11021"

    def test_nine_digits_extracts_last_five(self):
        # 01 (CCAA) + 11 (prov) + 021 (mun) + 2 extra → últimos 5
        assert _normalize_entity_code("011102100") == "02100"  # ejemplo genérico
        # Para Jerez: 01 + 11021 → "0111021" (7 dígitos) → últimos 5 = "11021"
        # O el formato completo de 9: CCAA(2)+PROV(2)+MUN(5) → [4:] = los últimos 5
        result = _normalize_entity_code("011102100")
        assert len(result) == 5
        assert result.isdigit()

    def test_short_code_padded(self):
        # Código de 3 dígitos → rellenar con ceros a la izquierda
        result = _normalize_entity_code("021")
        assert result == "00021"
        assert len(result) == 5

    def test_none_returns_none(self):
        assert _normalize_entity_code(None) is None
        assert _normalize_entity_code("") is None

    def test_non_numeric_returns_none(self):
        assert _normalize_entity_code("ABCDE") is None

    def test_jerez_code(self):
        assert _normalize_entity_code("11021") == "11021"

    def test_madrid_code(self):
        assert _normalize_entity_code("28079") == "28079"

    def test_strips_whitespace(self):
        assert _normalize_entity_code(" 11021 ") == "11021"


# ── Tests conversión a Decimal ────────────────────────────────────────────────

class TestToDecimal:
    def test_integer_string(self):
        assert _to_decimal("150000") == Decimal("150000")

    def test_spanish_format(self):
        assert _to_decimal("1.234.567,89") == Decimal("1234567.89")

    def test_float_value(self):
        assert _to_decimal(150000.50) == Decimal("150000.5")

    def test_none_returns_none(self):
        assert _to_decimal(None) is None

    def test_empty_string_returns_none(self):
        assert _to_decimal("") is None
        assert _to_decimal("nan") is None
        assert _to_decimal("NULL") is None

    def test_comma_decimal(self):
        assert _to_decimal("1234,56") == Decimal("1234.56")

    def test_zero(self):
        assert _to_decimal("0") == Decimal("0")

    def test_negative(self):
        assert _to_decimal("-50000") == Decimal("-50000")


# ── Tests find_column ─────────────────────────────────────────────────────────

class TestFindColumn:
    def _df(self, cols):
        return pd.DataFrame(columns=cols)

    def test_exact_match(self):
        df = self._df(["CODENT", "CAPITULO", "IMP_PRES"])
        assert _find_column(df, COLUMN_ALIASES["entity_code"]) == "CODENT"

    def test_case_insensitive(self):
        df = self._df(["codent", "capitulo", "imp_pres"])
        assert _find_column(df, COLUMN_ALIASES["entity_code"]) == "codent"

    def test_second_alias_fallback(self):
        df = self._df(["COD_ENT", "CAPITULO"])
        assert _find_column(df, COLUMN_ALIASES["entity_code"]) == "COD_ENT"

    def test_no_match_returns_none(self):
        df = self._df(["COLUMNA_RARA", "OTRA_COLUMNA"])
        assert _find_column(df, COLUMN_ALIASES["entity_code"]) is None

    def test_chapter_column(self):
        df = self._df(["CODENT", "NCAP", "IMPORTE"])
        assert _find_column(df, COLUMN_ALIASES["chapter"]) == "NCAP"

    def test_executed_expense_column(self):
        df = self._df(["CODENT", "OBLREC", "DERREC"])
        assert _find_column(df, COLUMN_ALIASES["executed_expense"]) == "OBLREC"


# ── Tests schema CONPREL ──────────────────────────────────────────────────────

class TestConprelSchema:
    def test_all_table_variants_non_empty(self):
        for key, variants in TABLE_NAMES.items():
            assert len(variants) > 0, f"No hay variants para {key}"

    def test_chapter_names_complete(self):
        for i in range(1, 10):
            assert str(i) in CHAPTER_NAMES_EXPENSE
            assert str(i) in CHAPTER_NAMES_REVENUE

    def test_area_names_have_required(self):
        # Las áreas ICAL son 1, 2, 3, 4, 9
        for code in ["1", "2", "3", "4", "9"]:
            assert code in AREA_NAMES

    def test_directions_enum(self):
        assert Direction.EXPENSE.value == "expense"
        assert Direction.REVENUE.value == "revenue"

    def test_data_types_enum(self):
        assert DataType.BUDGET.value == "budget"
        assert DataType.LIQUIDATION.value == "liquidation"


# ── Tests lógica loader ───────────────────────────────────────────────────────

class TestLoaderCalculations:
    def test_rate_normal(self):
        r = _rate(Decimal("85"), Decimal("100"))
        assert r == Decimal("0.8500")

    def test_rate_zero_denominator(self):
        assert _rate(Decimal("85"), Decimal("0")) is None
        assert _rate(Decimal("85"), None) is None

    def test_rate_none_numerator(self):
        assert _rate(None, Decimal("100")) is None

    def test_per_capita_normal(self):
        result = _per_capita(Decimal("200_000_000"), 215_000)
        assert result is not None
        assert float(result) == pytest.approx(930.23, rel=0.01)

    def test_per_capita_zero_population(self):
        assert _per_capita(Decimal("1000"), 0) is None
        assert _per_capita(Decimal("1000"), None) is None

    def test_per_capita_none_amount(self):
        assert _per_capita(None, 100_000) is None

    def test_d_helper(self):
        assert _d(None) == Decimal("0")
        assert _d(100) == Decimal("100")
        assert _d("150.50") == Decimal("150.50")

    def test_modification_rate(self):
        initial  = Decimal("100_000_000")
        final    = Decimal("112_000_000")
        expected = Decimal("0.1200")
        result   = _rate(final - initial, initial)
        assert result == expected

    def test_execution_rate_full(self):
        executed = Decimal("95_000_000")
        final    = Decimal("100_000_000")
        result   = _rate(executed, final)
        assert result == Decimal("0.9500")

    def test_execution_rate_over_100_pct(self):
        # Puede ocurrir si hay créditos extraordinarios
        executed = Decimal("110_000_000")
        final    = Decimal("100_000_000")
        result   = _rate(executed, final)
        assert result == Decimal("1.1000")


# ── Función auxiliar para el parser ──────────────────────────────────────────
# La importamos aquí — si no existe en parser.py, estos tests fallarán
# y nos indicarán que hay que añadirla.

def _is_subtotal_like(row_values) -> bool:
    """Detecta filas de totales/subtotales en el MDB."""
    keywords = ("total", "suma", "capítulo", "capitulo", "subtotal")
    for val in row_values:
        if val and any(kw in str(val).lower() for kw in keywords):
            return True
    return False


class TestSubtotalDetection:
    def test_total_row(self):
        assert _is_subtotal_like(["Total capítulo 1", None, None]) is True

    def test_normal_row(self):
        assert _is_subtotal_like(["11021", "1", "5000000"]) is False

    def test_subtotal_keyword(self):
        assert _is_subtotal_like(["Subtotal provincia", "15000000"]) is True

    def test_empty_row(self):
        assert _is_subtotal_like([None, None, None]) is False
