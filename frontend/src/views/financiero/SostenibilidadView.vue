<template>
  <div>
    <PageHeader
      title="Sostenibilidad Financiera"
      subtitle="Cuenta General (IGAE · 2015–2022) + Liquidaciones presupuestarias (transparencia.jerez.es · 2020–presente)"
    >
      <YearSelector :years="years" v-model="selectedYear" @update:modelValue="loadData" />
    </PageHeader>

    <div v-if="loading" class="flex items-center justify-center h-48 text-gray-400">
      <div class="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full mr-3"></div>
      Cargando datos…
    </div>
    <div v-else-if="error" class="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300 text-sm">
      {{ error }}
    </div>

    <template v-else-if="d || liq">

      <!-- ── Reglas fiscales LOEPSF ────────────────────────────── -->
      <p class="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">Reglas fiscales LOEPSF</p>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiCard
          :value="fmtEur(d.remanenteTesoreriaGastosGenerales)"
          label="Remanente de Tesorería GG"
          :badge="rtggBadge"
          :source="srcCg('remanente_tesoreria_gastos_generales')"
          source-icon="🏦"
          :year="selectedYear"
          :kpi-info="{
            description: 'Capacidad del ayuntamiento para hacer frente a sus obligaciones inmediatas. Diferencia entre derechos pendientes de cobro y obligaciones pendientes de pago, ajustada por saldos de dudoso cobro.',
            source: 'Estado de Remanente de Tesorería — Cuenta General anual (rendiciondecuentas.es)',
            optimal: 'Debe ser positivo. Valores negativos obligan a aprobar un plan de ajuste y limitan el endeudamiento (art. 193 TRLRHL).',
            warning: 'Jerez tuvo RTGG negativo desde 2015 hasta 2020 (mínimo –153 M€ en 2015). Recuperó saldo positivo en 2021.',
            notes: 'No confundir con el Remanente Total, que incluye fondos afectados (subvenciones, créditos específicos) que no son de libre disposición.',
          }"
          :trend-data="trendByKpi('remanente_tesoreria_gastos_generales')"
          trend-unit="€"
        />
        <KpiCard
          :value="fmtEur(valHybrid('resultadoOperacionesNoFinancieras', 'estabilidadPresupuestaria'))"
          label="Estabilidad Presupuestaria"
          :badge="resultadoBadge(valHybrid('resultadoOperacionesNoFinancieras', 'estabilidadPresupuestaria'))"
          :source="srcHybrid('resultadoOperacionesNoFinancieras', 'resultado_operaciones_no_financieras', 'Cuenta General — IGAE (rendiciondecuentas.es)', 'Liquidación presupuestaria (transparencia.jerez.es)')"
          source-icon="⚖️"
          :year="selectedYear"
          :kpi-info="{
            description: 'Capacidad (+) o necesidad (–) de financiación. Diferencia entre ingresos y gastos no financieros. Es el indicador oficial de estabilidad presupuestaria de la LOEPSF.',
            source: 'Liquidación Presupuestaria — art. 16 LOEPSF',
            optimal: 'Positivo o cero (superávit o equilibrio). Indica que el ayuntamiento no necesita financiación externa para sus operaciones ordinarias.',
            warning: 'Déficit continuado implica la aprobación de un plan económico-financiero y la intervención del Ministerio de Hacienda.',
          }"
          :trend-data="trendHybrid('resultado_operaciones_no_financieras', 'estabilidadPresupuestaria')"
          trend-unit="€"
          trend-source="Cuenta General — IGAE (2015–2022) · Liquidación presupuestaria (2023–presente)"
        />
        <KpiCard
          :value="fmtRatio(d.endeudamiento)"
          label="Ratio de Endeudamiento"
          :badge="deudaBadge"
          :source="srcCg('endeudamiento')"
          source-icon="📊"
          :year="selectedYear"
          :kpi-info="{
            description: 'Deuda financiera a largo plazo dividida entre los ingresos tributarios netos garantizados (ITNG). Mide cuántas veces la deuda supera los ingresos propios.',
            source: 'Balance y Liquidación Presupuestaria — Cuenta General (IGAE)',
            optimal: 'Inferior a 0,75. Entre 0,75 y 1,10 es zona de alerta. Por encima de 1,10 se necesita autorización del Estado para contratar nueva deuda (art. 53 TRLRHL).',
            warning: 'Jerez supera 1,10 desde 2016 y llega a 1,24 en 2022, lo que restringe su autonomía financiera.',
          }"
          :trend-data="trendByKpi('endeudamiento')"
        />
        <KpiCard
          :value="fmtDays(d.pmpAcreedores)"
          suffix=" días"
          label="Período Medio de Pago"
          :badge="pmpBadge"
          :source="srcCg('pmp_acreedores')"
          source-icon="🗓️"
          :year="selectedYear"
          :kpi-info="{
            description: 'Días medios que tarda el ayuntamiento en pagar a sus proveedores desde la aprobación de la factura.',
            source: 'Informe de Morosidad trimestral (MHFP) + Cuenta General',
            optimal: 'Máximo 30 días (Ley 3/2004 de Morosidad). Se publica en BOE si se supera.',
            warning: 'Superar 60 días activa retención de participación en tributos del Estado (art. 18 bis LOEPSF). Jerez registra 213 días en 2022, más de 7 veces el límite legal.',
          }"
          :trend-data="trendByKpi('pmp_acreedores')"
          trend-unit="días"
        />
      </div>

      <!-- ── 3. Liquidez ─────────────────────────────────────────── -->
      <p class="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">Liquidez</p>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiCard
          :value="fmtRatio(d?.liquidezInmediata)"
          label="Liquidez Inmediata"
          :badge="liquidezBadge(d?.liquidezInmediata, 0.1, 0.05)"
          :source="srcCg('liquidez_inmediata', 'Balance — Cuenta General (IGAE)')"
          source-icon="💧"
          :year="selectedYear"
          :kpi-info="{
            description: 'Fondos líquidos (caja y bancos) divididos entre el pasivo corriente. Mide la capacidad de atender pagos urgentes sin recurrir a cobros pendientes.',
            source: 'Balance de situación — Cuenta General (IGAE)',
            optimal: 'Superior a 0,10. Entre 0,05 y 0,10 indica liquidez ajustada.',
            warning: 'Por debajo de 0,05 existe riesgo de incapacidad para atender pagos inmediatos.',
          }"
          :trend-data="trendByKpi('liquidez_inmediata')"
        />
        <KpiCard
          :value="fmtRatio(d?.liquidezGeneral)"
          label="Liquidez General"
          :badge="liquidezBadge(d?.liquidezGeneral, 1.0, 0.5)"
          :source="srcCg('liquidez_general', 'Balance — Cuenta General (IGAE)')"
          source-icon="💧"
          :year="selectedYear"
          :kpi-info="{
            description: 'Activo corriente dividido entre pasivo corriente. Indica si el ayuntamiento puede cubrir sus deudas a corto plazo con sus activos más líquidos.',
            source: 'Balance de situación — Cuenta General (IGAE)',
            optimal: 'Superior a 1,0. Entre 0,5 y 1,0 señala tensiones de tesorería a corto plazo.',
          }"
          :trend-data="trendByKpi('liquidez_general')"
        />
        <KpiCard
          :value="fmtRatio(d?.liquidezCortoPlazo)"
          label="Liquidez Corto Plazo"
          :badge="liquidezBadge(d?.liquidezCortoPlazo, 0.5, 0.2)"
          :source="srcCg('liquidez_corto_plazo', 'Balance — Cuenta General (IGAE)')"
          source-icon="💧"
          :year="selectedYear"
          :kpi-info="{
            description: 'Activos líquidos y realizables a corto plazo divididos entre el pasivo corriente. Excluye activos menos líquidos respecto a la liquidez general.',
            source: 'Balance de situación — Cuenta General (IGAE)',
            optimal: 'Superior a 0,5. Por debajo de 0,2 indica riesgo de tensión de pagos.',
          }"
          :trend-data="trendByKpi('liquidez_corto_plazo')"
        />
        <KpiCard
          :value="fmtEur(ahorrobruto)"
          label="Ahorro Bruto"
          :badge="resultadoBadge(ahorrobruto)"
          :source="srcHybrid('cashFlow', 'cash_flow', 'Cuenta General — IGAE (rendiciondecuentas.es)', 'Liquidación presupuestaria — Ingresos corrientes − Gastos corrientes')"
          source-icon="💰"
          :year="selectedYear"
          :kpi-info="{
            description: 'Diferencia entre ingresos y gastos corrientes liquidados. Mide la capacidad del ayuntamiento para generar recursos propios con los que atender el servicio de la deuda e invertir sin recurrir a financiación externa.',
            source: 'Liquidación Presupuestaria — Caps. I–V Ingresos menos Caps. I–V Gastos',
            optimal: 'Positivo. Cuanto mayor, mayor margen para amortizar deuda e invertir sin endeudarse.',
            warning: 'Negativo indica que los gastos corrientes superan los ingresos corrientes: el ayuntamiento financia su funcionamiento ordinario con deuda o con el remanente.',
            notes: 'También conocido como «capacidad de ahorro» o «superávit corriente». Equivale al cash-flow operativo en terminología empresarial.',
          }"
          :trend-data="ahorrobrutotTrend"
          trend-unit="€"
          trend-source="Cuenta General — IGAE (2015–2022) · Liquidación presupuestaria (2023–presente)"
        />
      </div>

      <!-- ── 4. Resultados económicos ────────────────────────────── -->
      <p class="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">Resultados económicos</p>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiCard
          :value="fmtEur(d.resultadoGestionOrdinaria)"
          label="Resultado Gestión Ordinaria"
          :badge="resultadoBadge(d.resultadoGestionOrdinaria)"
          :source="srcCg('resultado_gestion_ordinaria', 'Cuenta Resultado Económico-Patrimonial')"
          source-icon="📈"
          :year="selectedYear"
          :kpi-info="{
            description: 'Diferencia entre ingresos y gastos de gestión ordinaria. Mide si las operaciones habituales generan ahorro o déficit antes de operaciones extraordinarias.',
            source: 'Cuenta del Resultado Económico-Patrimonial — Cuenta General (IGAE)',
            optimal: 'Positivo. Varios ejercicios negativos indican desequilibrio estructural.',
          }"
          :trend-data="trendByKpi('resultado_gestion_ordinaria')"
          trend-unit="€"
        />
        <KpiCard
          :value="fmtEur(d.resultadoNetoEjercicio)"
          label="Resultado Neto del Ejercicio"
          :badge="resultadoBadge(d.resultadoNetoEjercicio)"
          :source="srcCg('resultado_neto_ejercicio', 'Cuenta Resultado Económico-Patrimonial')"
          source-icon="📈"
          :year="selectedYear"
          :kpi-info="{
            description: 'Resultado final del ejercicio incluyendo operaciones extraordinarias, amortizaciones y provisiones. Afecta directamente al patrimonio neto.',
            source: 'Cuenta del Resultado Económico-Patrimonial — Cuenta General (IGAE)',
            optimal: 'Positivo o nulo. Resultado negativo erosiona el patrimonio neto acumulado.',
            warning: 'Resultado negativo continuado puede llevar al patrimonio neto a territorio negativo (fondos propios negativos).',
          }"
          :trend-data="trendByKpi('resultado_neto_ejercicio')"
          trend-unit="€"
        />
        <KpiCard
          :value="fmtEur(valHybrid('ingresosGestionOrdinariaCr', 'ingresosCorrientes'))"
          label="Ingresos Corrientes"
          :source="srcHybrid('ingresosGestionOrdinariaCr', 'ingresos_gestion_ordinaria_cr', 'Cuenta General — IGAE (rendiciondecuentas.es)', 'Liquidación presupuestaria — Caps. I–V ingresos')"
          source-icon="💰"
          :year="selectedYear"
          :kpi-info="{
            description: 'Total de ingresos corrientes liquidados: impuestos, tasas, transferencias corrientes e ingresos patrimoniales (capítulos I a V).',
            source: 'Liquidación Presupuestaria (transparencia.jerez.es) + Cuenta General (IGAE) para 2015-2022',
            optimal: 'Tendencia creciente sostenida. Crecimiento inferior a IPC indica pérdida de capacidad real.',
          }"
          :trend-data="trendHybrid('ingresos_gestion_ordinaria_cr', 'ingresosCorrientes')"
          trend-unit="€"
          trend-source="Cuenta General — IGAE (2015–2022) · Liquidación presupuestaria (2023–presente)"
        />
        <KpiCard
          :value="fmtEur(liq?.gastosFinancieros)"
          label="Coste Financiero Deuda"
          source="Liquidación presupuestaria (cap. III gastos)"
          source-icon="💳"
          :year="selectedYear"
          :kpi-info="{
            description: 'Gastos financieros reconocidos: intereses de préstamos a largo plazo, intereses de mora y otras cargas financieras (Capítulo III del presupuesto de gastos).',
            source: 'Liquidación Presupuestaria — Capítulo III Gastos Financieros (transparencia.jerez.es)',
            optimal: 'Tendencia decreciente. Indica reducción del coste de la deuda al ir amortizando préstamos.',
            notes: 'No incluye la amortización del principal (Capítulo IX). El coste financiero depende del saldo vivo de deuda y de los tipos de interés vigentes.',
          }"
          :trend-data="trendLiq('gastosFinancieros')"
          trend-unit="€"
        />
        <KpiCard
          :value="fmtPct(valHybrid('ratioIngresosTributarios', 'autonomiaFiscal'))"
          label="Autonomía Fiscal"
          :source="srcHybrid('ratioIngresosTributarios', 'ratio_ingresos_tributarios', 'Cuenta General — IGAE (rendiciondecuentas.es)', 'Liquidación presupuestaria — Caps. I+II / ingresos corrientes')"
          source-icon="🏛️"
          :year="selectedYear"
          :kpi-info="{
            description: 'Porcentaje de los ingresos corrientes que proviene de ingresos tributarios propios (impuestos y tasas). Mide la independencia financiera respecto a las transferencias del Estado.',
            source: 'Liquidación Presupuestaria — Capítulos I y II Ingresos',
            optimal: 'Cuanto mayor, mayor autonomía. Por debajo del 40% indica dependencia elevada de transferencias.',
            notes: 'Un ratio alto indica mayor margen de maniobra fiscal pero también mayor exposición a ciclos económicos locales.',
          }"
          :trend-data="trendHybrid('ratio_ingresos_tributarios', 'autonomiaFiscal')"
          trend-unit="%"
          trend-source="Cuenta General — IGAE (2015–2022) · Liquidación presupuestaria (2023–presente)"
        />
      </div>

      <!-- ── 5. Deuda y estructura patrimonial ─────────────────── -->
      <p class="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">Deuda y patrimonio</p>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard
          :value="fmtEurHab(d.endeudamientoHabitante)"
          suffix=" €/hab"
          label="Deuda Viva por Habitante"
          :badge="deudaHabBadge"
          :source="srcCg('endeudamiento_habitante', 'Cuenta General (IGAE) · INE Padrón')"
          source-icon="👤"
          :year="selectedYear"
          :kpi-info="{
            description: 'Deuda financiera total dividida entre el número de habitantes. El indicador más intuitivo para comunicación ciudadana y comparativas entre municipios.',
            source: 'Pasivo no corriente — Cuenta General (IGAE) · Padrón Municipal (INE)',
            optimal: 'Media nacional de grandes municipios: 1.000–1.500 €/hab. Por encima de 3.000 €/hab se considera elevado.',
            warning: 'Jerez supera los 5.000 €/hab en 2022, más del triple de la media nacional. Tendencia al alza desde 4.430 €/hab en 2016.',
          }"
          :trend-data="trendByKpi('endeudamiento_habitante')"
          trend-unit="€/hab"
        />
        <KpiCard
          :value="fmtEur(d.pasivoNoCorriente)"
          label="Deuda Bruta Total"
          :source="srcCg('pasivo_no_corriente', 'Balance — Cuenta General (IGAE)')"
          source-icon="🏦"
          :year="selectedYear"
          :kpi-info="{
            description: 'Total del pasivo no corriente: deuda financiera a largo plazo con entidades financieras, Estado y otros acreedores.',
            source: 'Balance de situación — Cuenta General (IGAE)',
            optimal: 'Tendencia decreciente. El volumen absoluto debe contextualizarse con los ingresos (ratio endeudamiento) y la población (€/hab).',
          }"
          :trend-data="trendByKpi('pasivo_no_corriente')"
          trend-unit="€"
        />
        <KpiCard
          :value="fmtEur(d.activoTotal)"
          label="Activo Total"
          :source="srcCg('activo_total', 'Balance — Cuenta General (IGAE)')"
          source-icon="🏗️"
          :year="selectedYear"
          :kpi-info="{
            description: 'Valor contable total de los bienes y derechos del ayuntamiento: inmovilizado (infraestructuras, edificios), activo corriente y derechos a cobrar.',
            source: 'Balance de situación — Cuenta General (IGAE)',
            notes: 'El activo municipal incluye infraestructuras valoradas a coste histórico. No refleja el valor de mercado real del patrimonio.',
          }"
          :trend-data="trendByKpi('activo_total')"
          trend-unit="€"
        />
        <KpiCard
          :value="fmtEur(d.patrimonioNeto)"
          label="Patrimonio Neto"
          :badge="resultadoBadge(d.patrimonioNeto)"
          :source="srcCg('patrimonio_neto', 'Balance — Cuenta General (IGAE)')"
          source-icon="⚖️"
          :year="selectedYear"
          :kpi-info="{
            description: 'Diferencia entre el activo total y el pasivo total. Representa los fondos propios acumulados del ayuntamiento.',
            source: 'Balance de situación — Cuenta General (IGAE)',
            optimal: 'Positivo y creciente. El deterioro sostenido del patrimonio neto es señal de desequilibrio estructural.',
            warning: 'Patrimonio neto negativo indica que las deudas superan el valor de los activos.',
          }"
          :trend-data="trendByKpi('patrimonio_neto')"
          trend-unit="€"
        />
      </div>

    </template>

    <div v-else class="flex items-center justify-center h-48 text-gray-500">
      Selecciona un ejercicio para ver los indicadores.
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  fetchCuentaGeneralYears,
  fetchSostenibilidadResumen,
  fetchCuentaGeneralTrend,
  fetchLiquidacionKpis,
} from '../../api/financiero.js'
import PageHeader   from '../../components/PageHeader.vue'
import YearSelector from '../../components/YearSelector.vue'
import KpiCard      from '../../components/KpiCard.vue'

const years        = ref([])   // unión de CG + liquidaciones
const selectedYear = ref(null)
const d            = ref(null) // Cuenta General (puede ser null si año > 2022)
const trend        = ref([])   // Cuenta General trend
const liqAll       = ref([])   // todas las liquidaciones (todos los años)
const loading      = ref(true)
const error        = ref(null)

// ── liqByYear: map año → objeto liquidación ───────────────────────────────────
const liqByYear = computed(() => {
  const m = {}
  for (const row of liqAll.value) m[row.ejercicio] = row
  return m
})

// Datos del año seleccionado desde liquidaciones (para KPIs sin CG)
const liq = computed(() => liqByYear.value[selectedYear.value] ?? null)

// ── Formato es-ES ──────────────────────────────────────────────────────────────
const eurFmt  = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
const numFmt  = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 })
const ratFmt  = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const pctFmt  = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

function fmtEur(v)    { return v == null ? '–' : eurFmt.format(Number(v)) }
function fmtEurHab(v) { return v == null ? '–' : numFmt.format(Number(v)) }
function fmtRatio(v)  { return v == null ? '–' : ratFmt.format(Number(v)) }
function fmtDays(v)   { return v == null ? '–' : numFmt.format(Math.round(Number(v))) }
function fmtPct(v)    { return v == null ? '–' : pctFmt.format(Number(v) * 100) + '%' }

// ── Ahorro Bruto = ingresos corrientes − gastos corrientes ────────────────────
// CG tiene cash_flow; liquidaciones lo calculamos en tiempo real
const ahorrobruto = computed(() => {
  // Intentar desde Cuenta General (campo más preciso)
  if (d.value?.cashFlow != null) return d.value.cashFlow
  // Derivar desde liquidaciones
  const ic = liq.value?.ingresosCorrientes
  const gc = liq.value?.gastosCorrientes
  if (ic != null && gc != null) return Number(ic) - Number(gc)
  return null
})

const ahorrobrutotTrend = computed(() => {
  // Puntos desde Cuenta General (cash_flow)
  const cgPoints = trend.value
    .filter(r => r.kpi === 'cash_flow')
    .map(r => ({ label: String(r.ejercicio), value: Number(r.valor) }))
  const cgYears = new Set(cgPoints.map(p => p.label))

  // Puntos desde liquidaciones (años sin CG)
  const liqPoints = liqAll.value
    .filter(row => {
      if (cgYears.has(String(row.ejercicio))) return false
      return row.ingresosCorrientes != null && row.gastosCorrientes != null
    })
    .map(row => ({
      label:   String(row.ejercicio),
      value:   Number(row.ingresosCorrientes) - Number(row.gastosCorrientes),
      partial: isPartialLiq(row),
    }))

  const merged = [...cgPoints, ...liqPoints].sort((a, b) => Number(a.label) - Number(b.label))
  return fillGaps(merged)
})

// ── Semáforos ──────────────────────────────────────────────────────────────────
const rtggBadge = computed(() => {
  const v = Number(d.value?.remanenteTesoreriaGastosGenerales ?? 0)
  if (!d.value) return null
  if (v > 0) return { text: 'Positivo', class: 'badge-green' }
  return { text: 'Negativo', class: 'badge-red' }
})

const deudaBadge = computed(() => {
  if (!d.value?.endeudamiento) return null
  const v = Number(d.value.endeudamiento)
  if (v < 0.75) return { text: 'Bajo',  class: 'badge-green' }
  if (v < 1.10) return { text: 'Medio', class: 'badge-yellow' }
  return { text: 'Alto', class: 'badge-red' }
})

const deudaHabBadge = computed(() => {
  if (!d.value?.endeudamientoHabitante) return null
  const v = Number(d.value.endeudamientoHabitante)
  if (v < 1500) return { text: 'Bajo',    class: 'badge-green' }
  if (v < 3000) return { text: 'Medio',   class: 'badge-yellow' }
  return { text: 'Elevado', class: 'badge-red' }
})

const pmpBadge = computed(() => {
  if (!d.value?.pmpAcreedores) return null
  const v = Number(d.value.pmpAcreedores)
  if (v <= 30) return { text: '≤ 30 días', class: 'badge-green' }
  if (v <= 60) return { text: '≤ 60 días', class: 'badge-yellow' }
  return { text: '> 60 días', class: 'badge-red' }
})


function liquidezBadge(val, good, warn) {
  if (val == null) return null
  const v = Number(val)
  if (v >= good) return { text: 'OK',       class: 'badge-green' }
  if (v >= warn) return { text: 'Ajustado', class: 'badge-yellow' }
  return { text: 'Bajo', class: 'badge-red' }
}

function resultadoBadge(val) {
  if (val == null) return null
  return Number(val) >= 0
    ? { text: 'Superávit', class: 'badge-green' }
    : { text: 'Déficit',   class: 'badge-red' }
}

// ── Helpers trend ─────────────────────────────────────────────────────────────

/**
 * Un año de liquidación es parcial cuando su snapshot_date no es el cierre
 * definitivo del ejercicio (antes del 28 de diciembre del mismo año).
 */
function isPartialLiq(row) {
  if (!row.snapshotDate) return false
  const d   = new Date(row.snapshotDate)
  const yr  = Number(row.ejercicio)
  return d.getFullYear() !== yr || d.getMonth() < 11 || d.getDate() < 28
}

/**
 * Rellena huecos en la serie con null para que ECharts interrumpa la línea.
 * El rango va desde el primer año con dato hasta el último.
 * Preserva la propiedad `partial` de los puntos originales.
 */
function fillGaps(points) {
  if (!points.length) return []
  const byYear = Object.fromEntries(points.map(p => [Number(p.label), p]))
  const years  = Object.keys(byYear).map(Number)
  const minY   = Math.min(...years)
  const maxY   = Math.max(...years)
  const result = []
  for (let y = minY; y <= maxY; y++) {
    if (y in byYear) {
      result.push(byYear[y])
    } else {
      result.push({ label: String(y), value: null })
    }
  }
  return result
}

/** Serie histórica desde Cuenta General */
function trendByKpi(kpiCode) {
  const pts = trend.value
    .filter(r => r.kpi === kpiCode)
    .map(r => ({ label: String(r.ejercicio), value: Number(r.valor) }))
    .sort((a, b) => Number(a.label) - Number(b.label))
  return fillGaps(pts)
}

/**
 * Serie histórica extendida: CG + liquidaciones (años sin CG).
 * Para los años solapados el dato de CG es autoritativo.
 * Los puntos de liquidación con snapshot parcial se marcan como partial: true.
 */
function trendHybrid(kpiCode, liqField) {
  const cgPoints = trend.value
    .filter(r => r.kpi === kpiCode)
    .map(r => ({ label: String(r.ejercicio), value: Number(r.valor) }))
  const cgYears  = new Set(cgPoints.map(p => p.label))

  const liqPoints = liqAll.value
    .filter(row => !cgYears.has(String(row.ejercicio)) && row[liqField] != null)
    .map(row => ({
      label:   String(row.ejercicio),
      value:   Number(row[liqField]),
      partial: isPartialLiq(row),
    }))

  const merged = [...cgPoints, ...liqPoints].sort((a, b) => Number(a.label) - Number(b.label))
  return fillGaps(merged)
}

/** Tendencia desde liquidaciones pura (sin equivalente en CG) */
function trendLiq(liqField) {
  const pts = liqAll.value
    .filter(row => row[liqField] != null)
    .map(row => ({
      label:   String(row.ejercicio),
      value:   Number(row[liqField]),
      partial: isPartialLiq(row),
    }))
    .sort((a, b) => Number(a.label) - Number(b.label))
  return fillGaps(pts)
}

// ── Getters de valor y fuente para el año seleccionado ───────────────────────

function valHybrid(cgField, liqField) {
  const cgVal = d.value?.[cgField]
  if (cgVal != null) return cgVal
  return liq.value?.[liqField] ?? null
}

// Mapa de códigos técnicos de fuente → etiquetas legibles
const SRC_LABELS = {
  'rendiciondecuentas_cg': 'Cuenta General (IGAE · rendiciondecuentas.es)',
}

// Mapa parseado de fuentes (JSON string → objeto)
const fuentesMap = computed(() => {
  try { return d.value?.fuentes ? JSON.parse(d.value.fuentes) : {} }
  catch { return {} }
})

/**
 * Fuente dinámica para KPIs exclusivamente de Cuenta General.
 * Traduce códigos técnicos a etiquetas legibles; usa el fallback si no hay fuente.
 */
function srcCg(kpiCode, fallback = 'Cuenta General (IGAE)') {
  const raw = fuentesMap.value[kpiCode]
  if (!raw) return fallback
  return SRC_LABELS[raw] ?? raw
}

/**
 * Fuente dinámica híbrida.
 * Comprueba si el campo CG (camelCase) tiene valor en el año seleccionado;
 * si lo tiene devuelve la fuente de CG (con srcCg); si no, devuelve la etiqueta
 * de liquidación con la fecha del snapshot cuando está disponible.
 *
 * @param {string} cgFieldCamel  - campo camelCase en el objeto d (CG)
 * @param {string} kpiCode       - código snake_case del KPI en la BD
 * @param {string} cgFallback    - etiqueta CG cuando fuente_cuenta es null
 * @param {string} liqLabel      - etiqueta base para liquidaciones
 */
function srcHybrid(cgFieldCamel, kpiCode, cgFallback, liqLabel) {
  if (d.value?.[cgFieldCamel] != null) return srcCg(kpiCode, cgFallback)
  const snapDate = liq.value?.snapshotDate
  if (snapDate) {
    const dt = new Date(snapDate)
    const isYearEnd = dt.getMonth() === 11 && dt.getDate() === 31
    return isYearEnd
      ? `${liqLabel} — liquidación definitiva`
      : `${liqLabel} — datos a ${dt.toLocaleDateString('es-ES')}`
  }
  return liqLabel
}

// ── Carga ──────────────────────────────────────────────────────────────────────
async function loadData() {
  if (!selectedYear.value) return
  loading.value = true
  error.value = null
  try {
    // Intentar CG primero; si no hay datos para ese año, d queda null
    try {
      d.value = await fetchSostenibilidadResumen(selectedYear.value)
    } catch {
      d.value = null
    }
  } catch (e) {
    error.value = 'Error al cargar los datos: ' + (e?.message ?? e)
  } finally {
    loading.value = false
  }
}

async function loadTrend() {
  try {
    const [cgTrend, liqData] = await Promise.all([
      fetchCuentaGeneralTrend([
        'remanente_tesoreria_gastos_generales',
        'resultado_operaciones_no_financieras',
        'endeudamiento',
        'endeudamiento_habitante',
        'pmp_acreedores',
        'liquidez_inmediata',
        'liquidez_general',
        'liquidez_corto_plazo',
        'cash_flow',
        'resultado_gestion_ordinaria',
        'resultado_neto_ejercicio',
        'ingresos_gestion_ordinaria_cr',
        'ratio_ingresos_tributarios',
        'pasivo_no_corriente',
        'activo_total',
        'patrimonio_neto',
      ]),
      fetchLiquidacionKpis(),
    ])
    trend.value  = cgTrend
    liqAll.value = liqData
  } catch {}
}

onMounted(async () => {
  try {
    const [cgYears, liqData] = await Promise.all([
      fetchCuentaGeneralYears(),
      fetchLiquidacionKpis(),
    ])
    liqAll.value = liqData

    // Combinar años: CG + liquidaciones, eliminar duplicados, orden desc
    const liqYears = liqData.map(r => r.ejercicio)
    const allYears = [...new Set([...cgYears, ...liqYears])].sort((a, b) => b - a)
    years.value = allYears

    // Ir al año más reciente disponible en cualquier fuente
    selectedYear.value = allYears[0] ?? null

    await Promise.all([loadData(), loadTrend()])
  } catch (e) {
    error.value = 'No se pudo conectar con la API: ' + (e?.message ?? e)
    loading.value = false
  }
})
</script>
