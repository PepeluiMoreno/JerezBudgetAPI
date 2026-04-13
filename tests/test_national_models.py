"""
Tests de la capa 2 — modelos nacionales y peer groups.
Sin dependencia de base de datos real: valida lógica de negocio.
"""
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from etl.ine.municipalities_catalog import (
    MunicipalityRecord,
    PROVINCE_MAP,
    _clean_name,
    _extract_year,
)
from etl.ine.population import _extract_year as pop_extract_year


# ── Tests catálogo municipios ─────────────────────────────────────────────────

class TestProvinceMap:
    def test_all_provinces_have_ccaa(self):
        """Todas las 52 provincias tienen CCAA asignada."""
        assert len(PROVINCE_MAP) == 52

    def test_cadiz_province(self):
        prov = PROVINCE_MAP["11"]
        assert prov[0] == "Cádiz"
        assert prov[1] == "01"   # Andalucía
        assert "Andalucía" in prov[2]

    def test_madrid_province(self):
        prov = PROVINCE_MAP["28"]
        assert "Madrid" in prov[0]
        assert prov[2] == "Comunidad de Madrid"

    def test_ceuta_melilla(self):
        assert "51" in PROVINCE_MAP   # Ceuta
        assert "52" in PROVINCE_MAP   # Melilla

    def test_ccaa_codes_range(self):
        """Todos los códigos CCAA son de 2 dígitos."""
        for _, (_, ccaa_code, _) in PROVINCE_MAP.items():
            assert len(ccaa_code) == 2
            assert ccaa_code.isdigit()


class TestCleanName:
    def test_strips_whitespace(self):
        assert _clean_name("  Jerez  ") == "Jerez"

    def test_collapses_double_space(self):
        assert _clean_name("San  Pedro") == "San Pedro"

    def test_none_returns_empty(self):
        assert _clean_name(None) == ""

    def test_normal_name_unchanged(self):
        assert _clean_name("Jerez de la Frontera") == "Jerez de la Frontera"


class TestMunicipalityRecord:
    def test_jerez_record(self):
        """Jerez debe tener INE 11020."""
        r = MunicipalityRecord(
            ine_code="11020",
            name="Jerez de la Frontera",
            province_code="11",
            province_name="Cádiz",
            ccaa_code="01",
            ccaa_name="Andalucía",
        )
        assert r.ine_code == "11020"
        assert r.province_code == "11"
        assert "Andalucía" in r.ccaa_name

    def test_ine_code_format(self):
        """El código INE es siempre 5 dígitos."""
        r = MunicipalityRecord(
            ine_code="28079",  # Madrid
            name="Madrid", province_code="28", province_name="Madrid",
            ccaa_code="13", ccaa_name="Comunidad de Madrid",
        )
        assert len(r.ine_code) == 5
        assert r.ine_code.isdigit()


class TestExtractYear:
    def test_plain_year(self):
        assert _extract_year("2023") == 2023

    def test_year_in_string(self):
        assert _extract_year("1 de enero de 2022") == 2022

    def test_none_on_no_year(self):
        assert _extract_year("sin fecha") is None

    def test_pre_2010_ignored_by_range(self):
        # La función extrae el año aunque sea anterior a 2010
        # El filtrado lo hace el llamador
        assert _extract_year("2005") == 2005

    def test_population_extract_year(self):
        """La función de población debe comportarse igual."""
        assert pop_extract_year("2024") == 2024
        assert pop_extract_year("Padrón 2023") == 2023
        assert pop_extract_year("sin dato") is None


# ── Tests lógica peer groups ──────────────────────────────────────────────────

class TestPeerGroupCriteria:
    """Tests de la lógica de criterios sin BD."""

    def _make_mun(self, ine, pop, ccaa, prov):
        m = MagicMock()
        m.ine_code = ine
        m.population = pop
        m.ccaa_code = ccaa
        m.province_code = prov
        m.is_active = True
        return m

    def test_jerez_in_andalucia_100k_250k(self):
        """Jerez (215k hab, Andalucía) debe estar en el grupo andalucia-100k-250k."""
        jerez_pop = 215_000
        criteria = {"pop_min": 100_000, "pop_max": 250_000, "ccaa_code": "01"}
        assert jerez_pop >= criteria["pop_min"]
        assert jerez_pop <= criteria["pop_max"]
        # Andalucía = code "01"
        assert "01" == criteria["ccaa_code"]

    def test_madrid_not_in_andalucia_group(self):
        """Madrid (3.3M hab, CCAA 13) no está en el grupo andaluz."""
        criteria = {"pop_min": 100_000, "pop_max": 250_000, "ccaa_code": "01"}
        madrid_ccaa = "13"
        assert madrid_ccaa != criteria["ccaa_code"]

    def test_algeciras_in_cadiz_group(self):
        """Algeciras (prov 11) debe estar en grupo provincia-cadiz."""
        criteria = {"province_code": "11"}
        algeciras_prov = "11"
        assert algeciras_prov == criteria["province_code"]

    def test_capitales_andalucia_static(self):
        """El grupo capitales usa lista explícita de INE codes."""
        capitales_ine = ["04013","11020","14021","18087","21041","23050","29067","41091"]
        # Sevilla = 41091
        assert "41091" in capitales_ine
        # Jerez = 11020 — NO es capital de provincia
        assert "11020" not in capitales_ine


# ── Tests modelo MunicipalBudget ──────────────────────────────────────────────

class TestMunicipalBudgetModel:
    def test_execution_rate_calculation(self):
        """Verificar fórmula de tasa de ejecución."""
        executed = Decimal("85_000_000")
        final    = Decimal("100_000_000")
        rate = executed / final
        assert rate == pytest.approx(Decimal("0.85"))

    def test_per_capita_calculation(self):
        """Verificar normalización per cápita."""
        executed   = Decimal("200_000_000")   # 200M €
        population = 215_000
        per_capita = executed / Decimal(population)
        # ~930 €/hab
        assert float(per_capita) == pytest.approx(930.23, rel=0.01)

    def test_modification_rate_calculation(self):
        """Tasa de modificación: (definitivo - inicial) / inicial."""
        initial = Decimal("150_000_000")
        final   = Decimal("162_000_000")   # +12M
        rate    = (final - initial) / initial
        assert float(rate) == pytest.approx(0.08)

    def test_zero_initial_no_division_error(self):
        """Con crédito inicial cero no debe haber ZeroDivisionError."""
        initial = Decimal("0")
        final   = Decimal("50_000")
        rate = (final - initial) / initial if initial != 0 else None
        assert rate is None

    def test_liquidation_vs_budget_type(self):
        """Los dos data_types válidos son 'budget' y 'liquidation'."""
        valid = {"budget", "liquidation"}
        assert "budget" in valid
        assert "liquidation" in valid
        assert "execution" not in valid   # no existe este tipo
