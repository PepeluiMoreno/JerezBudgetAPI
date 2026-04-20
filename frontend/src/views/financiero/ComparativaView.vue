<template>
  <div class="space-y-8">
    <PageHeader
      title="Comparativa Municipal"
      subtitle="Liquidaciones CONPREL — Hacienda · grupo de municipios comparables"
    >
      <!-- Selector de grupo de pares -->
      <select
        v-model="selectedGroupSlug"
        @change="loadComparativa"
        class="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none"
        :disabled="loadingGroups"
      >
        <option v-for="g in groups" :key="g.slug" :value="g.slug">
          {{ g.name }} ({{ g.memberCount }})
        </option>
      </select>

      <!-- Selector de año -->
      <select
        v-if="availableYears.length"
        v-model="selectedYear"
        @change="loadComparativa"
        class="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none"
      >
        <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
      </select>

      <!-- Tipo de dato -->
      <select
        v-model="selectedDataType"
        @change="loadComparativa"
        class="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none"
      >
        <option value="liquidation">Liquidación</option>
        <option value="budget">Presupuesto inicial</option>
      </select>
    </PageHeader>

    <!-- Estado de carga -->
    <div v-if="loading" class="text-center py-16 text-gray-400">
      <div class="animate-spin inline-block h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full mr-3 align-middle"></div>
      Cargando datos CONPREL…
    </div>
    <div v-else-if="error" class="text-center py-16 text-red-400">{{ error }}</div>

    <!-- Sin datos CONPREL aún -->
    <div v-else-if="!rows.length" class="bg-gray-800 border border-gray-700 rounded-xl p-8 text-center">
      <div class="text-4xl mb-4">📊</div>
      <h3 class="text-lg font-medium text-gray-300 mb-2">Sin datos CONPREL</h3>
      <p class="text-sm text-gray-500 max-w-md mx-auto">
        Las liquidaciones CONPREL aún no han sido ingestadas. Ejecuta la carga de datos:
      </p>
      <pre class="mt-4 inline-block bg-gray-900 text-green-400 text-xs px-4 py-3 rounded-lg text-left">make load-conprel   # ~25 min</pre>
      <p class="text-xs text-gray-600 mt-3">
        Fuente: Ministerio de Hacienda — CONPREL (liquidaciones anuales de todos los municipios españoles)
      </p>
    </div>

    <template v-else>

      <!-- ── KPIs posición de la ciudad ──────────────────────────────── -->
      <section v-if="cityRow">
        <SectionHeader :title="`${cityRow.name} en el grupo — ${selectedYear}`" />
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">

          <KpiCard
            :value="cityRow.expenseExecutedPerCapita != null ? fmtNum(cityRow.expenseExecutedPerCapita) : '—'"
            suffix=" €/hab"
            label="Gasto ejecutado per cápita"
            :badge="rankBadge(cityRow.rankExpensePerCapita, rows.length)"
            :sub="`Posición ${cityRow.rankExpensePerCapita} de ${rows.length}`"
            source="Ministerio de Hacienda — CONPREL"
            source-icon="📊"
            :year="selectedYear"
            :kpi-info="{
              description: 'Obligaciones reconocidas netas (gasto ejecutado) divididas entre la población del municipio.',
              source: 'CONPREL — Haciendas Locales, Ministerio de Hacienda',
              optimal: 'El gasto per cápita mide la intensidad del gasto municipal. Valores muy altos o muy bajos respecto al grupo pueden indicar diferencias en servicios prestados o eficiencia.'
            }"
            :trend-data="cityTrendExpPerCapita"
            trend-unit=" €/hab"
          />

          <KpiCard
            :value="cityRow.revenueExecutedPerCapita != null ? fmtNum(cityRow.revenueExecutedPerCapita) : '—'"
            suffix=" €/hab"
            label="Ingreso ejecutado per cápita"
            :sub="`Derechos reconocidos netos`"
            source="CONPREL — Hacienda"
            source-icon="💰"
            :year="selectedYear"
          />

          <KpiCard
            :value="cityRow.expenseExecutionRate != null ? pct(cityRow.expenseExecutionRate) : '—'"
            suffix="%"
            label="Ejecución de gastos"
            :badge="execBadge(cityRow.expenseExecutionRate)"
            :sub="`Obligaciones / créditos definitivos`"
            source="CONPREL — Hacienda"
            source-icon="📈"
            :year="selectedYear"
          />

          <KpiCard
            :value="medianExpPerCapita != null ? fmtNum(medianExpPerCapita) : '—'"
            suffix=" €/hab"
            label="Mediana del grupo"
            :sub="`${currentGroupName}`"
            source="CONPREL — Hacienda"
            source-icon="⚖️"
            :year="selectedYear"
          />

        </div>
      </section>

      <!-- ── Tabla ranking ───────────────────────────────────────────── -->
      <section>
        <SectionHeader title="Ranking — gasto ejecutado per cápita" />

        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-gray-700 text-gray-400 text-xs uppercase tracking-wider">
                <th class="text-right py-2 pr-3 font-medium w-10">#</th>
                <th class="text-left py-2 pr-4 font-medium">Municipio</th>
                <th class="text-right py-2 px-2 font-medium">Población</th>
                <th class="text-right py-2 px-2 font-medium">Gasto total</th>
                <th class="text-right py-2 px-2 font-medium">€/hab gastos</th>
                <th class="text-right py-2 px-2 font-medium">€/hab ingresos</th>
                <th class="text-right py-2 px-2 font-medium">Ejec. gastos</th>
                <th class="text-right py-2 px-2 font-medium">Ejec. ingresos</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in rows"
                :key="row.ineCode"
                class="border-b border-gray-800 hover:bg-gray-800/40"
                :class="{ 'bg-blue-900/20 ring-1 ring-blue-700/40': row.isCity }"
              >
                <td class="text-right py-2 pr-3 text-gray-500 text-xs">{{ row.rankExpensePerCapita }}</td>
                <td class="py-2 pr-4">
                  <span class="font-medium" :class="row.isCity ? 'text-blue-300' : 'text-gray-200'">
                    {{ row.name }}
                    <span v-if="row.isCity" class="ml-1 text-xs text-blue-400">★</span>
                  </span>
                </td>
                <td class="text-right py-2 px-2 text-gray-400">{{ row.population ? fmtInt(row.population) : '—' }}</td>
                <td class="text-right py-2 px-2 text-gray-300">{{ fmtEur(row.totalExpenseExecuted) }}</td>
                <td class="text-right py-2 px-2 font-medium" :class="percapitaClass(row.expenseExecutedPerCapita)">
                  {{ row.expenseExecutedPerCapita != null ? fmtNum(row.expenseExecutedPerCapita) : '—' }}
                </td>
                <td class="text-right py-2 px-2 text-gray-300">
                  {{ row.revenueExecutedPerCapita != null ? fmtNum(row.revenueExecutedPerCapita) : '—' }}
                </td>
                <td class="text-right py-2 px-2">
                  <span v-if="row.expenseExecutionRate != null" :class="execClass(row.expenseExecutionRate)">
                    {{ pct(row.expenseExecutionRate) }}%
                  </span>
                  <span v-else class="text-gray-600">—</span>
                </td>
                <td class="text-right py-2 px-2 text-gray-400">
                  {{ row.revenueExecutionRate != null ? pct(row.revenueExecutionRate) + '%' : '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- ── Desglose por capítulo de la ciudad ─────────────────────── -->
      <section v-if="cityRow && cityChapters.expense.length">
        <SectionHeader :title="`Desglose por capítulo — ${cityRow.name}`" />
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">

          <!-- Gastos -->
          <div>
            <p class="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">Gastos</p>
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-gray-700 text-gray-400 text-xs">
                  <th class="text-left py-1.5 font-medium">Cap.</th>
                  <th class="text-left py-1.5 font-medium">Descripción</th>
                  <th class="text-right py-1.5 font-medium">Ejecutado</th>
                  <th class="text-right py-1.5 font-medium">€/hab</th>
                  <th class="text-right py-1.5 font-medium">Ejec.</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="c in cityChapters.expense"
                  :key="c.chapter"
                  class="border-b border-gray-800"
                >
                  <td class="py-1.5 pr-3 font-mono text-gray-400">{{ c.chapter }}</td>
                  <td class="py-1.5 pr-3 text-gray-300 text-xs">{{ chapterName(c.chapter, 'expense') }}</td>
                  <td class="text-right py-1.5 px-1 text-gray-300">{{ fmtEur(c.executedAmount) }}</td>
                  <td class="text-right py-1.5 px-1 text-gray-300">
                    {{ c.executedPerCapita != null ? fmtNum(c.executedPerCapita) : '—' }}
                  </td>
                  <td class="text-right py-1.5 px-1">
                    <span v-if="c.executionRate != null" :class="execClass(c.executionRate)">
                      {{ pct(c.executionRate) }}%
                    </span>
                    <span v-else class="text-gray-600">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Ingresos -->
          <div>
            <p class="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-3">Ingresos</p>
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-gray-700 text-gray-400 text-xs">
                  <th class="text-left py-1.5 font-medium">Cap.</th>
                  <th class="text-left py-1.5 font-medium">Descripción</th>
                  <th class="text-right py-1.5 font-medium">Ejecutado</th>
                  <th class="text-right py-1.5 font-medium">€/hab</th>
                  <th class="text-right py-1.5 font-medium">Ejec.</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="c in cityChapters.revenue"
                  :key="c.chapter"
                  class="border-b border-gray-800"
                >
                  <td class="py-1.5 pr-3 font-mono text-gray-400">{{ c.chapter }}</td>
                  <td class="py-1.5 pr-3 text-gray-300 text-xs">{{ chapterName(c.chapter, 'revenue') }}</td>
                  <td class="text-right py-1.5 px-1 text-gray-300">{{ fmtEur(c.executedAmount) }}</td>
                  <td class="text-right py-1.5 px-1 text-gray-300">
                    {{ c.executedPerCapita != null ? fmtNum(c.executedPerCapita) : '—' }}
                  </td>
                  <td class="text-right py-1.5 px-1">
                    <span v-if="c.executionRate != null" :class="execClass(c.executionRate)">
                      {{ pct(c.executionRate) }}%
                    </span>
                    <span v-else class="text-gray-600">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

        </div>
      </section>

      <!-- ── Comparativa per cápita por capítulo vs grupo ──────────── -->
      <section v-if="cityRow && groupMedianByChapter.length">
        <SectionHeader title="Ciudad vs. mediana del grupo — gasto €/hab por capítulo" />
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-gray-700 text-gray-400 text-xs uppercase tracking-wider">
                <th class="text-left py-2 font-medium">Capítulo</th>
                <th class="text-right py-2 px-3 font-medium">{{ cityRow.name }}</th>
                <th class="text-right py-2 px-3 font-medium">Mediana grupo</th>
                <th class="text-right py-2 px-3 font-medium">Diferencia</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in groupMedianByChapter"
                :key="item.chapter"
                class="border-b border-gray-800 hover:bg-gray-800/30"
              >
                <td class="py-2 pr-3 text-gray-300">
                  <span class="font-mono text-gray-500 mr-2">{{ item.chapter }}</span>
                  {{ chapterName(item.chapter, 'expense') }}
                </td>
                <td class="text-right py-2 px-3 font-medium" :class="item.city != null ? 'text-blue-300' : 'text-gray-600'">
                  {{ item.city != null ? fmtNum(item.city) : '—' }}
                </td>
                <td class="text-right py-2 px-3 text-gray-300">{{ fmtNum(item.median) }}</td>
                <td class="text-right py-2 px-3">
                  <span v-if="item.city != null && item.median != null" :class="diffClass(item.city - item.median)">
                    {{ item.city - item.median > 0 ? '+' : '' }}{{ fmtNum(item.city - item.median) }} €
                  </span>
                  <span v-else class="text-gray-600">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="text-xs text-gray-600 mt-2">
          Fuente: Ministerio de Hacienda — CONPREL {{ selectedYear }} · {{ currentGroupName }}
        </p>
      </section>

    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import PageHeader from '../../components/PageHeader.vue'
import SectionHeader from '../../components/SectionHeader.vue'
import KpiCard from '../../components/KpiCard.vue'
import { fetchPeerGroups, fetchConprelComparativa } from '../../api/financiero.js'

// ── State ─────────────────────────────────────────────────────────────────────

const loadingGroups = ref(true)
const loading = ref(false)
const error = ref(null)
const groups = ref([])
const selectedGroupSlug = ref('')
const selectedYear = ref(null)
const selectedDataType = ref('liquidation')
const comparativaData = ref(null)

// ── Derived ───────────────────────────────────────────────────────────────────

const rows = computed(() => comparativaData.value?.rows ?? [])
const availableYears = computed(() => [...(comparativaData.value?.availableYears ?? [])].sort((a, b) => b - a))
const currentGroupName = computed(() => comparativaData.value?.peerGroupName ?? '')

const cityRow = computed(() => rows.value.find(r => r.isCity) ?? null)

const medianExpPerCapita = computed(() => {
  const vals = rows.value
    .map(r => r.expenseExecutedPerCapita)
    .filter(v => v != null)
    .sort((a, b) => a - b)
  if (!vals.length) return null
  const mid = Math.floor(vals.length / 2)
  return vals.length % 2 === 0 ? (vals[mid - 1] + vals[mid]) / 2 : vals[mid]
})

const cityChapters = computed(() => {
  if (!cityRow.value) return { expense: [], revenue: [] }
  const chapters = cityRow.value.chapters ?? []
  return {
    expense: chapters.filter(c => c.direction === 'expense').sort((a, b) => a.chapter.localeCompare(b.chapter)),
    revenue: chapters.filter(c => c.direction === 'revenue').sort((a, b) => a.chapter.localeCompare(b.chapter)),
  }
})

const groupMedianByChapter = computed(() => {
  const chapNums = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
  const cityExpMap = Object.fromEntries(
    cityChapters.value.expense.map(c => [c.chapter, c.executedPerCapita])
  )
  return chapNums
    .map(ch => {
      const vals = rows.value
        .filter(r => !r.isCity)
        .map(r => r.chapters?.find(c => c.chapter === ch && c.direction === 'expense')?.executedPerCapita)
        .filter(v => v != null)
        .sort((a, b) => a - b)
      if (!vals.length) return null
      const mid = Math.floor(vals.length / 2)
      const median = vals.length % 2 === 0 ? (vals[mid - 1] + vals[mid]) / 2 : vals[mid]
      return { chapter: ch, city: cityExpMap[ch] ?? null, median }
    })
    .filter(Boolean)
    .filter(item => item.median > 0 || item.city != null)
})

// Trend histórico del gasto per cápita de la ciudad (todas las liquidaciones disponibles)
const cityTrendExpPerCapita = computed(() => {
  // Sin datos históricos en este resolver — dejamos vacío
  return []
})

// ── Helpers ───────────────────────────────────────────────────────────────────

const EUR_FMT = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
const NUM_FMT = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 })
const INT_FMT = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 })

function fmtEur(v) { return v != null ? EUR_FMT.format(v) : '—' }
function fmtNum(v) { return v != null ? NUM_FMT.format(v) : '—' }
function fmtInt(v) { return v != null ? INT_FMT.format(v) : '—' }
function pct(v) { return v != null ? (v * 100).toFixed(1) : '—' }

function rankBadge(rank, total) {
  if (rank == null) return null
  if (rank <= Math.ceil(total * 0.33)) return { text: `#${rank}`, variant: 'green' }
  if (rank <= Math.ceil(total * 0.66)) return { text: `#${rank}`, variant: 'yellow' }
  return { text: `#${rank}`, variant: 'red' }
}

function execBadge(rate) {
  if (rate == null) return null
  if (rate >= 0.85) return { text: `${pct(rate)}%`, variant: 'green' }
  if (rate >= 0.70) return { text: `${pct(rate)}%`, variant: 'yellow' }
  return { text: `${pct(rate)}%`, variant: 'red' }
}

function execClass(rate) {
  if (rate == null) return 'text-gray-500'
  if (rate >= 0.85) return 'text-green-400'
  if (rate >= 0.70) return 'text-yellow-400'
  return 'text-red-400'
}

function percapitaClass(val) {
  if (val == null || !medianExpPerCapita.value) return 'text-gray-300'
  const ratio = val / medianExpPerCapita.value
  if (ratio >= 1.15) return 'text-red-300'
  if (ratio >= 1.05) return 'text-yellow-300'
  if (ratio <= 0.85) return 'text-blue-300'
  return 'text-green-300'
}

function diffClass(diff) {
  if (diff > 100) return 'text-red-300'
  if (diff > 0) return 'text-yellow-300'
  if (diff < -100) return 'text-blue-300'
  return 'text-green-300'
}

const CHAPTER_NAMES_EXPENSE = {
  '1': 'Gastos de personal',
  '2': 'Gastos corrientes en bienes y servicios',
  '3': 'Gastos financieros',
  '4': 'Transferencias corrientes',
  '5': 'Fondo de contingencia',
  '6': 'Inversiones reales',
  '7': 'Transferencias de capital',
  '8': 'Activos financieros',
  '9': 'Pasivos financieros',
}

const CHAPTER_NAMES_REVENUE = {
  '1': 'Impuestos directos',
  '2': 'Impuestos indirectos',
  '3': 'Tasas, precios públicos y otros ingresos',
  '4': 'Transferencias corrientes',
  '5': 'Ingresos patrimoniales',
  '6': 'Enajenación de inversiones reales',
  '7': 'Transferencias de capital',
  '8': 'Activos financieros',
  '9': 'Pasivos financieros',
}

function chapterName(ch, direction) {
  return direction === 'expense'
    ? CHAPTER_NAMES_EXPENSE[ch] ?? `Capítulo ${ch}`
    : CHAPTER_NAMES_REVENUE[ch] ?? `Capítulo ${ch}`
}

// ── Carga de datos ────────────────────────────────────────────────────────────

async function loadComparativa() {
  if (!selectedGroupSlug.value) return
  loading.value = true
  error.value = null
  try {
    comparativaData.value = await fetchConprelComparativa(
      selectedGroupSlug.value,
      selectedYear.value,
      selectedDataType.value,
    )
    // Actualizar año seleccionado si el resolver devolvió el más reciente
    if (comparativaData.value?.fiscalYear && comparativaData.value.fiscalYear !== selectedYear.value) {
      selectedYear.value = comparativaData.value.fiscalYear
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  loadingGroups.value = true
  try {
    groups.value = await fetchPeerGroups()
    if (groups.value.length) {
      selectedGroupSlug.value = groups.value[0].slug
      await loadComparativa()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loadingGroups.value = false
  }
})
</script>
