/**
 * Queries GraphQL — Módulo Gestión Económico-Financiera
 */
import { gqlClient } from './client.js'
import { gql } from 'graphql-request'

// ── Años fiscales disponibles ─────────────────────────────────────────────────
const FISCAL_YEARS_QUERY = gql`
  query FiscalYears {
    fiscalYears {
      id
      year
      initialBudgetDate
      approvalDelayDays
      publicationDelayDays
      isExtension
    }
  }
`

// ── Métricas de rigor de un ejercicio ─────────────────────────────────────────
const RIGOR_METRICS_QUERY = gql`
  query RigorMetrics($year: Int!) {
    rigorMetrics(fiscalYear: $year) {
      fiscalYear
      computedAt
      expenseExecutionRate
      revenueExecutionRate
      modificationRate
      numModifications
      approvalDelayDays
      publicationDelayDays
      precisionIndex
      timelinessIndex
      transparencyIndex
      globalRigorScore
      byChapter
      byProgram
    }
  }
`

// ── Tendencia de rigor (serie histórica) ──────────────────────────────────────
const RIGOR_TREND_QUERY = gql`
  query RigorTrend($years: [Int!]!) {
    rigorTrend(years: $years) {
      fiscalYear
      globalRigorScore
      precisionIndex
      timelinessIndex
      transparencyIndex
      expenseExecutionRate
      revenueExecutionRate
      modificationRate
    }
  }
`

// ── Análisis de desviaciones ──────────────────────────────────────────────────
const DEVIATION_ANALYSIS_QUERY = gql`
  query DeviationAnalysis($year: Int!, $by: String!) {
    deviationAnalysis(fiscalYear: $year, by: $by) {
      fiscalYear
      dimension
      code
      name
      initialAmount
      finalAmount
      executedAmount
      absoluteDeviation
      deviationPct
      modificationPct
      executionRate
    }
  }
`

// ── Resumen de modificaciones ─────────────────────────────────────────────────
const MODIFICATIONS_SUMMARY_QUERY = gql`
  query ModificationsSummary($year: Int!) {
    modificationsSummary(fiscalYear: $year) {
      fiscalYear
      totalModifications
      totalApproved
      totalInProgress
      totalRejected
      modificationRate
      byType {
        modType
        count
        totalAmount
      }
    }
  }
`

// ── Sostenibilidad financiera (Cuenta General) ────────────────────────────────

const CUENTA_GENERAL_YEARS_QUERY = gql`
  query { cuentaGeneralYears }
`

const SOSTENIBILIDAD_RESUMEN_QUERY = gql`
  query SostenibilidadResumen($ejercicio: Int!) {
    sostenibilidadResumen(ejercicio: $ejercicio) {
      ejercicio
      remanenteTesoreriaGastosGenerales
      remanenteTesoreriaTotal
      endeudamiento
      endeudamientoHabitante
      liquidezInmediata
      liquidezGeneral
      liquidezCortoPlazo
      pmpAcreedores
      resultadoGestionOrdinaria
      resultadoNetoEjercicio
      resultadoOperacionesNoFinancieras
      activoTotal
      pasivoNoCorriente
      patrimonioNeto
      ratioGastosPersonal
      ratioIngresosTributarios
      ingresosGestionOrdinariaCr
      gastosGestionOrdinariaCr
      habitantes
      cashFlow
      fuentes
    }
  }
`

const CUENTA_GENERAL_TREND_QUERY = gql`
  query CuentaGeneralTrend($kpis: [String!]!) {
    cuentaGeneralTrend(kpis: $kpis) {
      ejercicio
      kpi
      valor
    }
  }
`

// ── KPIs derivados de liquidaciones presupuestarias ──────────────────────────

const LIQUIDACION_KPIS_QUERY = gql`
  query LiquidacionKpis($years: [Int!]) {
    liquidacionKpis(years: $years) {
      ejercicio
      snapshotDate
      gastosCorrientes
      gastosCapital
      gastosFinancieros
      amortizacionDeuda
      gastosTotales
      ingresosCorrientes
      ingresosCapital
      ingresosTributarios
      ingresosTotales
      estabilidadPresupuestaria
      resultadoPresupuestario
      autonomiaFiscal
      ratioGastosPersonal
    }
  }
`

// ── Eficacia en recaudación ───────────────────────────────────────────────────

const RECAUDACION_KPIS_QUERY = gql`
  query RecaudacionKpis($fiscalYear: Int!) {
    recaudacionKpis(fiscalYear: $fiscalYear) {
      ejercicio
      snapshotDate
      totalInitialForecast
      totalFinalForecast
      totalRecognizedRights
      totalNetCollection
      totalPendingCollection
      executionRate
      collectionRate
      totalInitialForecastAll
      totalFinalForecastAll
      totalRecognizedRightsAll
      totalNetCollectionAll
      byChapter {
        chapter
        chapterName
        initialForecast
        finalForecast
        recognizedRights
        netCollection
        pendingCollection
        executionRate
        collectionRate
        deviationInitialPct
      }
      byConcept {
        code
        conceptName
        finalForecast
        recognizedRights
        netCollection
        pendingCollection
        collectionRate
      }
    }
  }
`

const RECAUDACION_CONCEPT_TREND_QUERY = gql`
  query RecaudacionConceptTrend($code: String!, $years: [Int!]) {
    recaudacionConceptTrend(code: $code, years: $years) {
      ejercicio
      snapshotDate
      isPartial
      finalForecast
      recognizedRights
      netCollection
      pendingCollection
      collectionRate
    }
  }
`

const RECAUDACION_TREND_QUERY = gql`
  query RecaudacionTrend($years: [Int!]) {
    recaudacionTrend(years: $years) {
      ejercicio
      snapshotDate
      isPartial
      totalFinalForecast
      totalRecognizedRights
      totalNetCollection
      totalPendingCollection
      executionRate
      collectionRate
    }
  }
`

// ── API pública ───────────────────────────────────────────────────────────────

export async function fetchFiscalYears() {
  const data = await gqlClient.request(FISCAL_YEARS_QUERY)
  return data.fiscalYears
}

export async function fetchRigorMetrics(year) {
  const data = await gqlClient.request(RIGOR_METRICS_QUERY, { year })
  return data.rigorMetrics
}

export async function fetchRigorTrend(years) {
  const data = await gqlClient.request(RIGOR_TREND_QUERY, { years })
  return data.rigorTrend
}

export async function fetchDeviationAnalysis(year, by = 'chapter') {
  const data = await gqlClient.request(DEVIATION_ANALYSIS_QUERY, { year, by })
  return data.deviationAnalysis
}

export async function fetchModificationsSummary(year) {
  const data = await gqlClient.request(MODIFICATIONS_SUMMARY_QUERY, { year })
  return data.modificationsSummary
}

export async function fetchCuentaGeneralYears() {
  const data = await gqlClient.request(CUENTA_GENERAL_YEARS_QUERY)
  return data.cuentaGeneralYears
}

export async function fetchSostenibilidadResumen(ejercicio) {
  const data = await gqlClient.request(SOSTENIBILIDAD_RESUMEN_QUERY, { ejercicio })
  return data.sostenibilidadResumen
}

export async function fetchCuentaGeneralTrend(kpis) {
  const data = await gqlClient.request(CUENTA_GENERAL_TREND_QUERY, { kpis })
  return data.cuentaGeneralTrend
}

export async function fetchLiquidacionKpis(years = null) {
  const data = await gqlClient.request(LIQUIDACION_KPIS_QUERY, { years })
  return data.liquidacionKpis
}

export async function fetchRecaudacionKpis(fiscalYear) {
  const data = await gqlClient.request(RECAUDACION_KPIS_QUERY, { fiscalYear })
  return data.recaudacionKpis
}

export async function fetchRecaudacionConceptTrend(code, years = null) {
  const data = await gqlClient.request(RECAUDACION_CONCEPT_TREND_QUERY, { code, years })
  return data.recaudacionConceptTrend
}

export async function fetchRecaudacionTrend(years = null) {
  const data = await gqlClient.request(RECAUDACION_TREND_QUERY, { years })
  return data.recaudacionTrend
}

// ── PMP mensual (Ley 15/2010) ─────────────────────────────────────────────────

const PMP_MENSUAL_QUERY = gql`
  query PmpMensual($year: Int!, $ineCode: String) {
    pmpMensual(year: $year, ineCode: $ineCode) {
      ejercicio
      mes
      entidadNif
      entidadNombre
      entidadTipo
      pmpDias
      alerta
    }
  }
`

const PMP_ANUAL_QUERY = gql`
  query PmpAnual($ineCode: String) {
    pmpAnual(ineCode: $ineCode) {
      ejercicio
      entidadNif
      entidadNombre
      entidadTipo
      pmpPromedio
      mesesDisponibles
      mesesIncumplimiento
      alerta
    }
  }
`

export async function fetchPmpMensual(year, ineCode = null) {
  const data = await gqlClient.request(PMP_MENSUAL_QUERY, { year, ineCode })
  return data.pmpMensual
}

export async function fetchPmpAnual(ineCode = null) {
  const data = await gqlClient.request(PMP_ANUAL_QUERY, { ineCode })
  return data.pmpAnual
}

// ── S12: Deuda y Morosidad ────────────────────────────────────────────────────

const DEUDA_HISTORICA_QUERY = gql`
  query DeudaHistorica($ineCode: String) {
    deudaHistorica(ineCode: $ineCode) {
      ejercicio
      deudaViva
      deudaPrivada
      deudaIco
      deudaTotal
      deudaPercapita
      habitantes
    }
  }
`

const MOROSIDAD_TRIMESTRAL_QUERY = gql`
  query MorosidadTrimestral($year: Int, $ineCode: String) {
    morosidadTrimestral(year: $year, ineCode: $ineCode) {
      ejercicio
      trimestre
      pmpTrimestral
      pagosPlazoCount
      pagosPlazoImporte
      pagosFueraPlazoCount
      pagosFueraPlazoImporte
      facturasPendientesFueraPlazoCount
      facturasPendientesFueraPlazoImporte
      interesesDemora
      ratioFueraPlazo
    }
  }
`

export async function fetchDeudaHistorica(ineCode = null) {
  const data = await gqlClient.request(DEUDA_HISTORICA_QUERY, { ineCode })
  return data.deudaHistorica
}

export async function fetchMorosidadTrimestral(year = null, ineCode = null) {
  const data = await gqlClient.request(MOROSIDAD_TRIMESTRAL_QUERY, { year, ineCode })
  return data.morosidadTrimestral
}

// ── S12: Comparativa CONPREL ──────────────────────────────────────────────────

const PEER_GROUPS_QUERY = gql`
  query PeerGroups {
    peerGroups {
      id
      slug
      name
      description
      memberCount
    }
  }
`

const CONPREL_COMPARATIVA_QUERY = gql`
  query ConprelComparativa($peerGroupSlug: String!, $fiscalYear: Int, $dataType: String) {
    conprelComparativa(peerGroupSlug: $peerGroupSlug, fiscalYear: $fiscalYear, dataType: $dataType) {
      peerGroupSlug
      peerGroupName
      fiscalYear
      dataType
      availableYears
      rows {
        ineCode
        name
        population
        isCity
        totalExpenseExecuted
        totalRevenueExecuted
        expenseExecutedPerCapita
        revenueExecutedPerCapita
        expenseExecutionRate
        revenueExecutionRate
        rankExpensePerCapita
        chapters {
          chapter
          direction
          executedAmount
          executedPerCapita
          executionRate
        }
      }
    }
  }
`

export async function fetchPeerGroups() {
  const data = await gqlClient.request(PEER_GROUPS_QUERY)
  return data.peerGroups
}

export async function fetchConprelComparativa(peerGroupSlug, fiscalYear = null, dataType = 'liquidation') {
  const data = await gqlClient.request(CONPREL_COMPARATIVA_QUERY, { peerGroupSlug, fiscalYear, dataType })
  return data.conprelComparativa
}
