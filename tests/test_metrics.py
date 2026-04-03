"""
Tests de las fórmulas de métricas de rigor.
Se testean las fórmulas puras sin necesidad de base de datos.
"""
from decimal import Decimal
import pytest


# ── Helpers que replican las fórmulas del servicio ───────────────────────────

def calc_ipp(execution_rate: float) -> float:
    """IPP = 100 - |1 - tasa_ejecución| × 100"""
    return max(0.0, 100.0 * (1 - abs(1 - execution_rate)))


def calc_itp(delay_days: int, is_extension: bool = False) -> float:
    """ITP = 0 si prórroga, max(0, 100 - días × 0.5) si no"""
    if is_extension:
        return 0.0
    return max(0.0, 100.0 - delay_days * 0.5)


def calc_itr(pub_delay_days: int) -> float:
    """ITR = max(0, 100 - días_publicación × 1.0)"""
    return max(0.0, 100.0 - pub_delay_days * 1.0)


def calc_global(ipp: float, itp: float, itr: float) -> float:
    return round(ipp * 0.50 + itp * 0.30 + itr * 0.20, 2)


# ── Tests IPP ────────────────────────────────────────────────────────────────

class TestIPP:
    def test_perfect_execution(self):
        assert calc_ipp(1.0) == 100.0

    def test_90_pct_execution(self):
        assert calc_ipp(0.90) == pytest.approx(90.0)

    def test_70_pct_execution(self):
        assert calc_ipp(0.70) == pytest.approx(70.0)

    def test_over_execution(self):
        # Ejecutar más de lo presupuestado también penaliza
        assert calc_ipp(1.10) == pytest.approx(90.0)

    def test_zero_execution(self):
        assert calc_ipp(0.0) == pytest.approx(0.0)

    def test_symmetry(self):
        # 80% y 120% deben dar el mismo IPP
        assert calc_ipp(0.80) == pytest.approx(calc_ipp(1.20))

    def test_floor_at_zero(self):
        # Ejecución del 300% → no puede ser negativo
        assert calc_ipp(3.0) == 0.0


# ── Tests ITP ────────────────────────────────────────────────────────────────

class TestITP:
    def test_on_time(self):
        # Aprobado el 31 de diciembre del año anterior = 0 días de retraso
        assert calc_itp(0) == 100.0

    def test_slight_delay(self):
        # 10 días de retraso = -5 puntos
        assert calc_itp(10) == pytest.approx(95.0)

    def test_200_days_delay(self):
        # 200 días = 100 puntos de penalización → score = 0
        assert calc_itp(200) == 0.0

    def test_prorroga_is_zero(self):
        # Prórroga siempre = 0 independientemente del número de días
        assert calc_itp(0, is_extension=True) == 0.0
        assert calc_itp(30, is_extension=True) == 0.0

    def test_floor_at_zero(self):
        assert calc_itp(1000) == 0.0


# ── Tests ITR ────────────────────────────────────────────────────────────────

class TestITR:
    def test_same_day(self):
        assert calc_itr(0) == 100.0

    def test_one_week(self):
        assert calc_itr(7) == pytest.approx(93.0)

    def test_one_month(self):
        assert calc_itr(30) == pytest.approx(70.0)

    def test_over_100_days(self):
        assert calc_itr(100) == 0.0

    def test_floor_at_zero(self):
        assert calc_itr(500) == 0.0


# ── Tests Score Global ───────────────────────────────────────────────────────

class TestGlobalScore:
    def test_perfect_score(self):
        assert calc_global(100, 100, 100) == 100.0

    def test_zero_score(self):
        assert calc_global(0, 0, 0) == 0.0

    def test_case_2026_prorroga(self):
        # 2026: prórroga (ITP=0), ejecución ~60% (IPP≈60), publicación rápida (ITR=90)
        ipp = calc_ipp(0.60)  # 60.0
        itp = calc_itp(0, is_extension=True)  # 0.0
        itr = calc_itr(10)  # 90.0
        score = calc_global(ipp, itp, itr)
        # Score = 60×0.5 + 0×0.3 + 90×0.2 = 30 + 0 + 18 = 48
        assert score == pytest.approx(48.0)

    def test_weights_sum_to_one(self):
        # Los pesos 0.5 + 0.3 + 0.2 = 1.0
        assert 0.50 + 0.30 + 0.20 == pytest.approx(1.0)

    def test_itp_dominance_when_prorroga(self):
        # Con prórroga, el ITP=0 arrastra el score
        score_with_prorroga = calc_global(ipp=90, itp=0, itr=90)
        score_without_delay = calc_global(ipp=90, itp=100, itr=90)
        assert score_with_prorroga < score_without_delay

    def test_realistic_good_year(self):
        # Año con buena gestión: 95% ejecución, aprobado 15 días tarde, publicado a los 5 días
        ipp = calc_ipp(0.95)      # ≈ 95
        itp = calc_itp(15)        # = 92.5
        itr = calc_itr(5)         # = 95
        score = calc_global(ipp, itp, itr)
        assert score > 90.0

    def test_realistic_poor_year(self):
        # Año con mala gestión: 60% ejecución, prórroga, publicación tardía (60 días)
        ipp = calc_ipp(0.60)               # 60
        itp = calc_itp(0, is_extension=True)  # 0
        itr = calc_itr(60)                 # 40
        score = calc_global(ipp, itp, itr)
        assert score < 50.0
