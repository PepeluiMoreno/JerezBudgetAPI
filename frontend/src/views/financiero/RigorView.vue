<template>
  <div>
    <PageHeader
      title="Rigor Presupuestario"
      subtitle="Índices de precisión, puntualidad y transparencia"
    >
      <YearSelector :years="fiscalYears.map(fy => fy.year)" v-model="selectedYear" @update:modelValue="loadData" />
    </PageHeader>

    <!-- Estado de carga / error -->
    <div v-if="loading" class="flex items-center justify-center h-48 text-gray-400">
      <div class="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full mr-3"></div>
      Cargando datos…
    </div>
    <div v-else-if="error" class="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300 text-sm">
      {{ error }}
    </div>

    <template v-else-if="metrics">
      <!-- ── KPI Cards ───────────────────────────────────────────── -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiCard
          :value="formatScore(metrics.globalRigorScore)"
          suffix="/100"
          label="Score Global Rigor"
          :badge="{ text: scoreLabel(metrics.globalRigorScore), class: scoreBadge(metrics.globalRigorScore) }"
          source="Liquidación presupuestaria"
          source-icon="🏛️"
          :year="selectedYear"
          :kpiInfo="kpiInfoScore"
        />

        <KpiCard
          :value="formatScore(metrics.precisionIndex)"
          suffix="/100"
          label="Índice de Precisión (IPP)"
          :sub="`Eje. gasto ${formatPct(metrics.expenseExecutionRate)} · Eje. ingreso ${formatPct(metrics.revenueExecutionRate)}`"
          source="XLSX transparencia.jerez.es"
          source-icon="📊"
          :year="selectedYear"
          :kpiInfo="kpiInfoIpp"
        />

        <KpiCard
          :value="formatScore(metrics.timelinessIndex)"
          suffix="/100"
          label="Índice de Puntualidad (ITP)"
          :sub="`Aprobación ${metrics.approvalDelayDays ?? '–'} días · Publicación ${metrics.publicationDelayDays ?? '–'} días`"
          source="BOP Cádiz · BOE"
          source-icon="📰"
          :year="selectedYear"
        />

        <KpiCard
          :value="formatScore(metrics.transparencyIndex)"
          suffix="/100"
          label="Índice de Transparencia (ITR)"
          :sub="`${metrics.numModifications} modificaciones · Tasa ${formatPct(metrics.modificationRate)}`"
          source="Portal de Transparencia"
          source-icon="🔍"
          :year="selectedYear"
        />
      </div>

      <!-- ── Gráfico de tendencia ────────────────────────────────── -->
      <div class="bg-gray-800 border border-gray-700 rounded-xl p-5 mb-6">
        <h3 class="text-sm font-medium text-gray-300 mb-4">Evolución del Score Global de Rigor</h3>
        <VChart
          :option="trendChartOption"
          style="height: 240px;"
          autoresize
        />
      </div>

      <!-- ── Desviaciones por capítulo ──────────────────────────── -->
      <DataTable
        :columns="deviationColumns"
        :rows="deviations"
        empty-text="Sin datos de desglose"
        source="Liquidación presupuestaria"
        source-icon="📊"
        :year="selectedYear"
      >
        <template #toolbar>
          <h3 class="text-sm font-medium text-gray-300">Desviaciones por Capítulo</h3>
          <div class="flex gap-1 ml-4">
            <button
              v-for="d in ['chapter', 'program']" :key="d"
              @click="deviationBy = d; loadDeviations()"
              class="px-3 py-1 rounded text-xs transition-colors"
              :class="deviationBy === d ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:text-white'"
            >
              {{ d === 'chapter' ? 'Capítulo' : 'Programa' }}
            </button>
          </div>
        </template>

        <template #row="{ row }">
          <tr
            :key="row.code + row.dimension"
            :class="isFinancialChapter(row.code) && Math.abs(Number(row.absoluteDeviation)) > 5_000_000
              ? 'bg-amber-950/30 border-l-2 border-amber-600'
              : ''"
          >
            <td class="font-medium py-2 px-3 text-sm">
              {{ row.name }}
              <span
                v-if="isFinancialChapter(row.code)"
                class="ml-1 text-xs text-amber-500"
                title="Cap. VIII/IX — operaciones financieras. Bajas tasas de ejecución son frecuentes pero deben justificarse."
              >⚠</span>
            </td>
            <td class="text-right font-mono text-xs py-2 px-3">{{ formatEur(row.initialAmount) }}</td>
            <td class="text-right font-mono text-xs py-2 px-3">{{ formatEur(row.finalAmount) }}</td>
            <td class="text-right font-mono text-xs py-2 px-3">{{ formatEur(row.executedAmount) }}</td>
            <td class="text-right py-2 px-3">
              <span :class="execRateBadge(row.executionRate)">{{ formatPct(row.executionRate) }}</span>
            </td>
            <td class="text-right font-mono text-xs py-2 px-3"
              :class="row.absoluteDeviation >= 0 ? 'text-yellow-400' : 'text-green-400'">
              {{ formatEur(row.absoluteDeviation) }}
            </td>
          </tr>
        </template>
      </DataTable>

      <!-- ── Ejecución de ingresos por capítulo ────────────────────── -->
      <div v-if="ingresosByChapter.length" class="mt-6">
        <h3 class="text-sm font-medium text-gray-300 mb-3">Ejecución de Ingresos por Capítulo</h3>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-gray-500 uppercase border-b border-gray-700">
                <th class="py-2 pr-4">Cap.</th>
                <th class="py-2 pr-4">Concepto</th>
                <th class="py-2 pr-4 text-right">Prev. definitiva</th>
                <th class="py-2 pr-4 text-right">D. reconocidos</th>
                <th class="py-2 pr-4 text-right">Tasa ejecución</th>
                <th class="py-2 text-right">Desv. inicial</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="ch in ingresosByChapter"
                :key="ch.chapter"
                class="border-b border-gray-800 hover:bg-gray-800/40 transition-colors"
                :class="isFinancialChapter(ch.chapter) ? 'bg-amber-950/20' : ''"
              >
                <td class="py-2 pr-4 font-mono text-gray-400">
                  {{ ch.chapter }}
                  <span
                    v-if="isFinancialChapter(ch.chapter)"
                    class="text-amber-500 ml-0.5"
                    title="Cap. VIII/IX — operaciones financieras"
                  >⚠</span>
                </td>
                <td class="py-2 pr-4 text-gray-300">{{ ch.chapterName }}</td>
                <td class="py-2 pr-4 text-right font-mono text-xs text-gray-400">{{ eurShort(ch.finalForecast) }}</td>
                <td class="py-2 pr-4 text-right font-mono text-xs text-gray-300">{{ eurShort(ch.recognizedRights) }}</td>
                <td class="py-2 pr-4 text-right">
                  <span :class="execRateBadge(ch.executionRate)">{{ formatPct(ch.executionRate) }}</span>
                </td>
                <td class="py-2 text-right font-mono text-xs"
                  :class="ch.deviationInitialPct > 0 ? 'text-yellow-400' : ch.deviationInitialPct < 0 ? 'text-green-400' : 'text-gray-500'">
                  {{ ch.deviationInitialPct != null ? (ch.deviationInitialPct >= 0 ? '+' : '') + (ch.deviationInitialPct * 100).toFixed(1) + '%' : '–' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="mt-2 text-xs text-gray-600">
          Fuente: Liquidaciones presupuestarias — transparencia.jerez.es · Fase: executed_revenue
        </p>
        <p class="mt-1 text-xs text-amber-700">
          ⚠ Caps. VIII (Activos financieros) y IX (Pasivos financieros): suelen presupuestarse como "colchón de liquidez" y rara vez se ejecutan íntegramente. Bajas tasas de ejecución son frecuentes pero penalizan el IPP.
        </p>
      </div>

    </template>

    <div v-else class="flex items-center justify-center h-48 text-gray-500">
      {{ selectedYear ? `Sin métricas calculadas para ${selectedYear}` : 'Selecciona un ejercicio para ver los indicadores.' }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  fetchFiscalYears,
  fetchRigorMetrics,
  fetchRigorTrend,
  fetchDeviationAnalysis,
  fetchRecaudacionKpis,
} from '../../api/financiero.js'
import PageHeader    from '../../components/PageHeader.vue'
import YearSelector  from '../../components/YearSelector.vue'
import KpiCard       from '../../components/KpiCard.vue'
import DataTable     from '../../components/DataTable.vue'

const cityName = import.meta.env.VITE_CITY_NAME || 'Jerez de la Frontera'

const kpiInfoScore = {
  description: 'Índice sintético de rigor presupuestario. Pondera tres dimensiones: Precisión (IPP, 50%), Puntualidad (ITP, 30%) y Transparencia (ITR, 20%).',
  optimal: 'Score ≥ 75: rigor alto. 50-75: medio. < 50: bajo. Los municipios con mejor gestión superan los 70 puntos de forma sostenida.',
  warning: 'Las operaciones financieras (Caps. VIII y IX) penalizan el Score cuando se presupuestan como colchón de liquidez (pólizas, préstamos BEI) pero no se ejecutan, bajando el IPP y con él el Score Global.',
  notes: 'Fórmula: Score = IPP×0,5 + ITP×0,3 + ITR×0,2. Cap. VIII = Activos financieros. Cap. IX = Pasivos financieros (nuevos préstamos, BEI, bonos municipales).',
}

const kpiInfoIpp = {
  description: 'Mide cuánto se acerca la ejecución real al presupuesto definitivo. Se calcula como 100 − |1 − tasa_ejecución| × 100, ponderado por capítulo.',
  optimal: 'IPP de 100 significa ejecución perfecta. Entre 90-100 es habitual en una gestión correcta.',
  warning: 'Los Caps. VIII (Activos financieros) y IX (Pasivos financieros) se presupuestan como colchón de liquidez pero raramente se ejecutan íntegramente (tasas 0-30% son comunes). Esto arrastra el IPP medio hacia abajo penalizando artificialmente el índice global.',
  notes: 'Cap. VIII: remanente de tesorería, pólizas de crédito, devolución de préstamos concedidos. Cap. IX: nuevos préstamos bancarios, financiación BEI, emisión de bonos municipales.',
}

const fiscalYears      = ref([])
const selectedYear     = ref(null)
const metrics          = ref(null)
const trend            = ref([])
const deviations       = ref([])
const ingresosByChapter = ref([])
const deviationBy      = ref('chapter')
const loading          = ref(true)
const error            = ref(null)

const deviationColumns = [
  { key: 'name',              label: 'Concepto'    },
  { key: 'initialAmount',     label: 'Inicial',    align: 'right' },
  { key: 'finalAmount',       label: 'Definitivo', align: 'right' },
  { key: 'executedAmount',    label: 'Ejecutado',  align: 'right' },
  { key: 'executionRate',     label: 'Tasa Eje.',  align: 'right' },
  { key: 'absoluteDeviation', label: 'Desviación', align: 'right' },
]

// ── Formato ────────────────────────────────────────────────────────────────────
function formatScore(v) { return v == null ? '–' : Math.round(v) }
function formatPct(v)   { return v == null ? '–' : (v * 100).toFixed(1) + '%' }
function formatEur(v) {
  if (v == null) return '–'
  return new Intl.NumberFormat('es-ES', {
    style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
  }).format(Number(v))
}
function scoreBadge(score) {
  if (score == null) return 'badge-gray'
  if (score >= 75) return 'badge-green'
  if (score >= 50) return 'badge-yellow'
  return 'badge-red'
}
function scoreLabel(score) {
  if (score == null) return 'Sin datos'
  if (score >= 75) return 'Alto'
  if (score >= 50) return 'Medio'
  return 'Bajo'
}
function execRateBadge(rate) {
  if (rate == null) return 'badge-gray'
  if (rate >= 0.85) return 'badge-green'
  if (rate >= 0.65) return 'badge-yellow'
  return 'badge-red'
}
function eurShort(v) {
  if (v == null) return '–'
  return Number(v).toLocaleString('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
}

function isFinancialChapter(code) {
  // code puede ser "8", "9", "VIII", "IX" según el resolver
  const s = String(code).trim()
  return s === '8' || s === '9' || s === 'VIII' || s === 'IX'
}

// ── ECharts: tendencia ────────────────────────────────────────────────────────
const trendChartOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' },
  legend: {
    data: ['Score Global', 'IPP', 'ITP', 'ITR'],
    textStyle: { color: '#9ca3af' },
  },
  grid: { left: 40, right: 20, top: 40, bottom: 30 },
  xAxis: {
    type: 'category',
    data: trend.value.map(p => p.fiscalYear),
    axisLabel: { color: '#9ca3af' },
    axisLine: { lineStyle: { color: '#374151' } },
  },
  yAxis: {
    type: 'value',
    max: 100,
    axisLabel: { color: '#9ca3af', formatter: '{value}' },
    splitLine: { lineStyle: { color: '#1f2937' } },
  },
  series: [
    {
      name: 'Score Global',
      type: 'line',
      data: trend.value.map(p => p.globalRigorScore != null ? +(p.globalRigorScore).toFixed(1) : null),
      itemStyle: { color: '#3b82f6' },
      lineStyle: { width: 2 },
      symbol: 'circle', symbolSize: 6,
    },
    {
      name: 'IPP',
      type: 'line',
      data: trend.value.map(p => p.precisionIndex != null ? +(p.precisionIndex).toFixed(1) : null),
      itemStyle: { color: '#10b981' },
      lineStyle: { width: 1, type: 'dashed' },
    },
    {
      name: 'ITP',
      type: 'line',
      data: trend.value.map(p => p.timelinessIndex != null ? +(p.timelinessIndex).toFixed(1) : null),
      itemStyle: { color: '#f59e0b' },
      lineStyle: { width: 1, type: 'dashed' },
    },
    {
      name: 'ITR',
      type: 'line',
      data: trend.value.map(p => p.transparencyIndex != null ? +(p.transparencyIndex).toFixed(1) : null),
      itemStyle: { color: '#8b5cf6' },
      lineStyle: { width: 1, type: 'dashed' },
    },
  ],
}))

// ── Carga de datos ────────────────────────────────────────────────────────────
async function loadData() {
  if (!selectedYear.value) return
  loading.value = true
  error.value = null
  try {
    const [m, devs, rec] = await Promise.all([
      fetchRigorMetrics(selectedYear.value),
      fetchDeviationAnalysis(selectedYear.value, deviationBy.value),
      fetchRecaudacionKpis(selectedYear.value).catch(() => null),
    ])
    metrics.value = m
    deviations.value = devs
    ingresosByChapter.value = rec?.byChapter ?? []
  } catch (e) {
    error.value = 'Error al cargar los datos: ' + (e?.message ?? e)
  } finally {
    loading.value = false
  }
}

async function loadDeviations() {
  if (!selectedYear.value) return
  try {
    deviations.value = await fetchDeviationAnalysis(selectedYear.value, deviationBy.value)
  } catch {}
}

async function loadTrend(years) {
  try {
    trend.value = await fetchRigorTrend(years)
  } catch {}
}

onMounted(async () => {
  try {
    const fys = await fetchFiscalYears()
    fiscalYears.value = fys
    if (fys.length) {
      const years = fys.map(fy => fy.year).sort((a, b) => b - a)
      // Seleccionar el año más reciente que tenga métricas calculadas
      for (const yr of years) {
        const m = await fetchRigorMetrics(yr)
        if (m) { selectedYear.value = yr; break }
      }
      if (!selectedYear.value) selectedYear.value = years[0]
      await Promise.all([loadData(), loadTrend(fys.map(fy => fy.year))])
    }
  } catch (e) {
    error.value = 'No se pudo conectar con la API: ' + (e?.message ?? e)
    loading.value = false
  }
})
</script>
