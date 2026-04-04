"""
Tests de integración del schema GraphQL.
Usan el cliente de test de Strawberry — no necesitan servidor ni base de datos real.
Los resolvers se mockean para testear solo el schema y el wiring.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import strawberry
from strawberry.test import BaseGraphQLTestClient

from graphql.schema import schema


# ── Cliente de test ──────────────────────────────────────────────────────────

class SyncGraphQLClient(BaseGraphQLTestClient):
    """Cliente síncrono sobre el schema Strawberry para tests."""

    def request(self, body: dict[str, Any], headers=None, files=None):
        # Strawberry schema.execute_sync para tests
        result = schema.execute_sync(
            body["query"],
            variable_values=body.get("variables"),
            context_value={"db": AsyncMock()},
        )
        return {"data": result.data, "errors": result.errors}


# ── Fixtures de datos de prueba ──────────────────────────────────────────────

def make_fiscal_year(year=2025):
    from graphql.types import FiscalYearType
    return FiscalYearType(
        id=1, year=year, is_extension=False, extended_from_year=None,
        status="approved",
        initial_budget_date=date(year - 1, 12, 28),
        publication_date=date(year - 1, 12, 30),
        stability_report_date=date(year - 1, 12, 27),
        approval_delay_days=-3,
        publication_delay_days=2,
        notes=None,
    )


def make_fiscal_year_extension(year=2026):
    from graphql.types import FiscalYearType
    return FiscalYearType(
        id=2, year=year, is_extension=True, extended_from_year=2025,
        status="extended",
        initial_budget_date=date(year, 1, 22),
        publication_date=date(year, 1, 22),
        stability_report_date=None,
        approval_delay_days=22,
        publication_delay_days=0,
        notes=None,
    )


def make_budget_line():
    from graphql.types import BudgetLineType
    return BudgetLineType(
        id=1, snapshot_id=1, description="Sueldos y salarios",
        economic_code="12000", economic_description="Sueldos y salarios",
        chapter="1", direction="expense",
        functional_code="9120", program_description="Gobierno y Administración General",
        organic_code="0101", section="01",
        initial_credits=Decimal("1000000"), modifications=Decimal("50000"),
        final_credits=Decimal("1050000"), commitments=Decimal("900000"),
        recognized_obligations=Decimal("850000"), payments_made=Decimal("800000"),
        pending_payment=Decimal("50000"),
        initial_forecast=None, final_forecast=None, recognized_rights=None,
        net_collection=None, pending_collection=None,
        execution_rate=0.8095, revenue_execution_rate=None,
        deviation_amount=Decimal("200000"), modification_rate=0.05,
    )


def make_rigor_metrics(year=2025):
    from graphql.types import RigorMetricsType
    return RigorMetricsType(
        id=1, fiscal_year=year,
        computed_at=datetime(year, 3, 23, 10, 0, 0),
        expense_execution_rate=0.87,
        revenue_execution_rate=0.92,
        modification_rate=0.08,
        num_modifications=5,
        approval_delay_days=-3,
        publication_delay_days=2,
        precision_index=87.0,
        timeliness_index=100.0,
        transparency_index=98.0,
        global_rigor_score=92.1,
        by_chapter={"1": {"execution_rate": 0.95, "initial": 5000000}},
        by_program={"9120": {"execution_rate": 0.90}},
    )


# ── Tests de schema ──────────────────────────────────────────────────────────

class TestFiscalYearsQuery:

    @pytest.mark.asyncio
    async def test_fiscal_years_query(self):
        query = """
            query {
              fiscalYears {
                id year isExtension status
                approvalDelayDays publicationDelayDays
              }
            }
        """
        with patch(
            "graphql.resolvers.fiscal_years.resolve_fiscal_years",
            new=AsyncMock(return_value=[make_fiscal_year(), make_fiscal_year_extension()])
        ):
            result = await schema.execute(
                query,
                context_value={"db": AsyncMock()},
            )
        assert result.errors is None
        data = result.data["fiscalYears"]
        assert len(data) == 2
        assert data[0]["year"] == 2025
        assert data[0]["isExtension"] is False
        assert data[0]["approvalDelayDays"] == -3
        assert data[1]["year"] == 2026
        assert data[1]["isExtension"] is True

    @pytest.mark.asyncio
    async def test_fiscal_year_single(self):
        query = """
            query($year: Int!) {
              fiscalYear(year: $year) {
                year isExtension extendedFromYear approvalDelayDays
              }
            }
        """
        with patch(
            "graphql.resolvers.fiscal_years.resolve_fiscal_year",
            new=AsyncMock(return_value=make_fiscal_year_extension(2026))
        ):
            result = await schema.execute(
                query,
                variable_values={"year": 2026},
                context_value={"db": AsyncMock()},
            )
        assert result.errors is None
        fy = result.data["fiscalYear"]
        assert fy["isExtension"] is True
        assert fy["extendedFromYear"] == 2025
        assert fy["approvalDelayDays"] == 22

    @pytest.mark.asyncio
    async def test_fiscal_year_not_found_returns_null(self):
        query = "query { fiscalYear(year: 1999) { year } }"
        with patch(
            "graphql.resolvers.fiscal_years.resolve_fiscal_year",
            new=AsyncMock(return_value=None)
        ):
            result = await schema.execute(
                query, context_value={"db": AsyncMock()}
            )
        assert result.errors is None
        assert result.data["fiscalYear"] is None


class TestBudgetLinesQuery:

    @pytest.mark.asyncio
    async def test_budget_lines_basic(self):
        from graphql.types import BudgetLinePage
        mock_page = BudgetLinePage(
            items=[make_budget_line()],
            total=1, page=1, page_size=200, has_next=False
        )
        query = """
            query($year: Int!) {
              budgetLines(fiscalYear: $year) {
                total hasNext page
                items {
                  id chapter direction economicCode
                  finalCredits recognizedObligations executionRate deviationAmount
                }
              }
            }
        """
        with patch(
            "graphql.resolvers.budget_lines.resolve_budget_lines",
            new=AsyncMock(return_value=mock_page)
        ):
            result = await schema.execute(
                query,
                variable_values={"year": 2025},
                context_value={"db": AsyncMock()},
            )
        assert result.errors is None
        data = result.data["budgetLines"]
        assert data["total"] == 1
        assert data["hasNext"] is False
        item = data["items"][0]
        assert item["chapter"] == "1"
        assert item["direction"] == "expense"
        assert float(item["executionRate"]) == pytest.approx(0.8095)

    @pytest.mark.asyncio
    async def test_budget_lines_page_size_capped_at_500(self):
        """El resolver debe recibir page_size <= 500."""
        from graphql.types import BudgetLinePage
        called_with = {}

        async def mock_resolver(db, fiscal_year, filters, page, page_size):
            called_with["page_size"] = page_size
            return BudgetLinePage(items=[], total=0, page=page, page_size=page_size, has_next=False)

        query = """
            query {
              budgetLines(fiscalYear: 2025, pageSize: 9999) {
                total pageSize
              }
            }
        """
        with patch("graphql.resolvers.budget_lines.resolve_budget_lines", new=mock_resolver):
            result = await schema.execute(
                query, context_value={"db": AsyncMock()}
            )
        assert result.errors is None
        assert called_with["page_size"] <= 500


class TestRigorMetricsQuery:

    @pytest.mark.asyncio
    async def test_rigor_metrics_all_fields(self):
        query = """
            query($year: Int!) {
              rigorMetrics(fiscalYear: $year) {
                fiscalYear computedAt
                expenseExecutionRate revenueExecutionRate modificationRate
                numModifications approvalDelayDays
                precisionIndex timelinessIndex transparencyIndex
                globalRigorScore byChapter
              }
            }
        """
        with patch(
            "graphql.resolvers.metrics.resolve_rigor_metrics",
            new=AsyncMock(return_value=make_rigor_metrics(2025))
        ):
            result = await schema.execute(
                query,
                variable_values={"year": 2025},
                context_value={"db": AsyncMock()},
            )
        assert result.errors is None
        m = result.data["rigorMetrics"]
        assert m["fiscalYear"] == 2025
        assert float(m["globalRigorScore"]) == pytest.approx(92.1)
        assert float(m["precisionIndex"]) == pytest.approx(87.0)
        assert float(m["timelinessIndex"]) == pytest.approx(100.0)
        assert m["byChapter"] is not None

    @pytest.mark.asyncio
    async def test_rigor_metrics_null_for_missing_year(self):
        query = "query { rigorMetrics(fiscalYear: 2000) { globalRigorScore } }"
        with patch(
            "graphql.resolvers.metrics.resolve_rigor_metrics",
            new=AsyncMock(return_value=None)
        ):
            result = await schema.execute(
                query, context_value={"db": AsyncMock()}
            )
        assert result.errors is None
        assert result.data["rigorMetrics"] is None


class TestRigorTrendQuery:

    @pytest.mark.asyncio
    async def test_rigor_trend_sorted(self):
        from graphql.types import RigorTrendPointType
        trend = [
            RigorTrendPointType(
                fiscal_year=y, is_extension=(y == 2026),
                global_rigor_score=70.0 + y - 2020,
                precision_index=80.0, timeliness_index=60.0, transparency_index=90.0,
                expense_execution_rate=0.85, revenue_execution_rate=0.90,
                modification_rate=0.05, approval_delay_days=0 if y != 2026 else 22,
                num_modifications=3,
            )
            for y in [2020, 2021, 2022, 2023, 2024, 2025, 2026]
        ]
        query = """
            query {
              rigorTrend(years: [2020,2021,2022,2023,2024,2025,2026]) {
                fiscalYear isExtension globalRigorScore approvalDelayDays
              }
            }
        """
        with patch(
            "graphql.resolvers.modifications_summary.resolve_rigor_trend",
            new=AsyncMock(return_value=trend)
        ):
            result = await schema.execute(
                query, context_value={"db": AsyncMock()}
            )
        assert result.errors is None
        points = result.data["rigorTrend"]
        assert len(points) == 7
        years = [p["fiscalYear"] for p in points]
        assert years == sorted(years)
        prorroga = next(p for p in points if p["fiscalYear"] == 2026)
        assert prorroga["isExtension"] is True


class TestDeviationAnalysisQuery:

    @pytest.mark.asyncio
    async def test_deviation_by_chapter(self):
        from graphql.types import DeviationAnalysisType
        devs = [
            DeviationAnalysisType(
                fiscal_year=2025, dimension="chapter", code="1",
                name="Cap. 1 — Personal",
                initial_amount=Decimal("5000000"), final_amount=Decimal("5200000"),
                executed_amount=Decimal("4900000"),
                absolute_deviation=Decimal("300000"),
                deviation_pct=5.77, modification_pct=4.0, execution_rate=0.942,
            ),
        ]
        query = """
            query {
              deviationAnalysis(fiscalYear: 2025, by: "chapter") {
                code name deviationPct modificationPct executionRate
              }
            }
        """
        with patch(
            "graphql.resolvers.metrics.resolve_deviation_analysis",
            new=AsyncMock(return_value=devs)
        ):
            result = await schema.execute(
                query, context_value={"db": AsyncMock()}
            )
        assert result.errors is None
        data = result.data["deviationAnalysis"]
        assert len(data) == 1
        assert data[0]["code"] == "1"
        assert float(data[0]["executionRate"]) == pytest.approx(0.942)


class TestModificationsQuery:

    @pytest.mark.asyncio
    async def test_modifications_with_filter(self):
        from graphql.types import BudgetModificationType
        mods = [
            BudgetModificationType(
                id=1, fiscal_year_id=1, ref="T003/2026",
                mod_type="carry_forward", status="approved",
                resolution_date=date(2026, 2, 10),
                publication_date=date(2026, 2, 18),
                total_amount=Decimal("450000"),
                description="Incorporación remanentes ejercicio anterior",
                source_url="https://transparencia.jerez.es/...",
            )
        ]
        query = """
            query {
              budgetModifications(
                fiscalYear: 2026,
                filters: { status: "approved", modType: "carry_forward" }
              ) {
                ref modType status totalAmount resolutionDate
              }
            }
        """
        with patch(
            "graphql.resolvers.modifications.resolve_budget_modifications",
            new=AsyncMock(return_value=mods)
        ):
            result = await schema.execute(
                query, context_value={"db": AsyncMock()}
            )
        assert result.errors is None
        data = result.data["budgetModifications"]
        assert len(data) == 1
        assert data[0]["ref"] == "T003/2026"
        assert data[0]["modType"] == "carry_forward"
