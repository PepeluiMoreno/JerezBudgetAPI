<template>
  <div class="space-y-8">
    <PageHeader
      title="Eficacia en Recaudación"
      subtitle="Cobro de derechos reconocidos e índice de morosidad"
    />

    <!-- Selector de ejercicio -->
    <YearSelector v-model="selectedYear" :years="availableYears" />

    <!-- Estado de carga / error -->
    <div v-if="loading" class="text-center py-16 text-gray-400">Cargando datos…</div>
    <div v-else-if="error" class="text-center py-16 text-red-400">{{ error }}</div>
    <div v-else-if="!kpis" class="text-center py-16 text-gray-500">
      No hay datos de recaudación para {{ selectedYear }}.
      <p class="text-xs mt-2 text-gray-600">Es necesario cargar el XLSX de ejecución de ingresos (fase executed_revenue).</p>
    </div>

    <template v-else>
      <!-- KPIs globales -->
      <section>
        <SectionHeader title="Resumen del ejercicio" />
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">

          <KpiCard
            :value="pct(kpis.collectionRate)"
            suffix="%"
            label="Eficacia de cobro"
            :sub="subEficacia(kpis)"
            :badge="badgeColl(kpis.collectionRate)"
            :source="source"
            :year="selectedYear"
            :trend-data="trendColl"
            trend-unit="%"
            :kpi-info="{
              description: 'Recaudación neta / Derechos reconocidos. Mide qué porcentaje de lo liquidado se ha cobrado efectivamente en tesorería.',
              optimal: '> 93 % — Buena gestión (nivel Navarra, Asturias, PVasco, CyL)\n85–93 % — Aceptable (media nacional 90,7 %)\n< 85 % — Deficiente (por debajo de Andalucía 83,3 %)\n< 70 % — Muy deficiente (problemas estructurales graves)',
              warning: 'Andalucía, la CCAA más baja, alcanza el 83,3 %. Por debajo de ese umbral la gestión recaudatoria es inferior a la peor comunidad autónoma del país. El factor clave diferenciador es la tasa de domiciliación bancaria.',
              source: 'Ministerio de Hacienda — Datos de Haciendas Locales 2022'
            }"
          />

          <KpiCard
            :value="eur(kpis.totalPendingCollection)"
            label="Pendiente de cobro"
            :sub="'Derechos reconocidos – recaudación neta'"
            :source="source"
            :year="selectedYear"
            :trend-data="trendPend"
            :kpi-info="{
              description: 'Importe de derechos reconocidos que aún no se ha ingresado en la tesorería. Incluye tanto el pendiente corriente como el de ejercicios anteriores.',
              source: 'Liquidaciones presupuestarias — transparencia.jerez.es'
            }"
          />

          <KpiCard
            :value="eur(kpis.totalRecognizedRights)"
            label="Derechos reconocidos"
            :sub="'Ingresos liquidados en el ejercicio'"
            :source="source"
            :year="selectedYear"
            :trend-data="trendRec"
            :kpi-info="{
              description: 'Total de derechos reconocidos netos en el ejercicio. Representan los ingresos liquidados, independientemente de si se han cobrado.',
              source: 'Liquidaciones presupuestarias — transparencia.jerez.es'
            }"
          />

        </div>
      </section>

      <!-- Previsiones -->
      <section>
        <SectionHeader title="Previsiones vs ejecución (Caps. I–VII)" />
        <p class="text-xs text-gray-500 -mt-4 mb-4">
          Excluye Caps. VIII–IX (operaciones financieras) que pueden distorsionar los totales con modificaciones no ejecutadas.
        </p>
        <div class="grid grid-cols-2 md:grid-cols-3 gap-4">

          <KpiCard
            :value="eur(kpis.totalInitialForecast)"
            label="Previsión inicial"
            :source="source"
            :year="selectedYear"
          />

          <KpiCard
            :value="eur(kpis.totalFinalForecast)"
            label="Previsión definitiva"
            :sub="desvIni(kpis)"
            :source="source"
            :year="selectedYear"
            :kpi-info="{
              description: 'Previsión operativa de ingresos (Caps. I-VII) tras modificaciones. Excluye operaciones financieras (VIII-IX) que habitualmente se presupuestan pero no se ejecutan.',
              source: 'Liquidaciones presupuestarias — transparencia.jerez.es'
            }"
          />

          <KpiCard
            :value="eur(kpis.totalNetCollection)"
            label="Recaudación neta"
            :source="source"
            :year="selectedYear"
          />

        </div>
        <div v-if="kpis.totalFinalForecastAll" class="mt-3 text-xs text-gray-600">
          Total presupuesto incluyendo Caps. VIII–IX:
          prev. definitiva {{ eur(kpis.totalFinalForecastAll) }} ·
          derechos reconocidos {{ eur(kpis.totalRecognizedRightsAll) }}
        </div>
      </section>

      <!-- Tabla por conceptos recaudatorios (Caps. I-III y V) -->
      <section>
        <SectionHeader title="Desglose por concepto recaudatorio" />
        <p class="text-xs text-gray-500 -mt-4 mb-4">
          Ingresos de gestión propia: tributos (Caps. I-II), tasas y otros (Cap. III) e ingresos patrimoniales (Cap. V).
        </p>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-gray-500 uppercase border-b border-gray-700">
                <th class="py-2 pr-3">Cód.</th>
                <th class="py-2 pr-3">Concepto</th>
                <th class="py-2 pr-3 text-right">D. reconocidos</th>
                <th class="py-2 pr-3 text-right">Pendiente</th>
                <th class="py-2 pr-3 text-right">% Cobrado</th>
                <th class="py-2 text-center w-10">Evol.</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="c in kpis.byConcept"
                :key="c.code"
                class="border-b border-gray-800 hover:bg-gray-800/40 transition-colors"
              >
                <td class="py-1.5 pr-3 font-mono text-xs text-gray-400">{{ c.code }}</td>
                <td class="py-1.5 pr-3 text-gray-300 text-xs">{{ c.conceptName }}</td>
                <td class="py-1.5 pr-3 text-right text-gray-300 tabular-nums text-xs">{{ eurShort(c.recognizedRights) }}</td>
                <td class="py-1.5 pr-3 text-right tabular-nums text-xs" :class="pendingClass(c.pendingCollection)">
                  {{ eurShort(c.pendingCollection) }}
                </td>
                <td class="py-1.5 pr-3 text-right tabular-nums text-xs">
                  <span :class="collRateClass(c.collectionRate)">{{ pct(c.collectionRate) }}%</span>
                </td>
                <td class="py-1.5 text-center">
                  <button
                    @click="openConceptTrend(c)"
                    title="Ver evolución histórica"
                    class="w-6 h-6 flex items-center justify-center mx-auto rounded bg-gray-700
                           hover:bg-blue-700 text-gray-400 hover:text-white transition-colors text-sm"
                  >📈</button>
                </td>
              </tr>
            </tbody>
          </table>
          <p class="mt-2 text-xs text-gray-600">Fuente: {{ source }} · Snapshot: {{ kpis.snapshotDate ?? '—' }}</p>
        </div>
      </section>

      <!-- Modal: evolución de concepto -->
      <BaseModal
        v-if="activeConcept"
        v-model="showConceptModal"
        :title="`[${activeConcept.code}] ${activeConcept.conceptName}`"
        subtitle="Evolución histórica por ejercicio"
        max-width="max-w-2xl"
      >
        <div v-if="loadingConceptTrend" class="text-center py-10 text-gray-400">Cargando…</div>
        <VChart v-else ref="conceptChartRef" :option="conceptTrendOption" style="height: 300px;" autoresize />
        <template #footer>
          <div class="flex items-center justify-between gap-3">
            <span class="text-xs text-gray-500">Fuente: {{ source }}</span>
            <button
              @click="saveConceptChartImage"
              class="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700
                     text-white text-sm rounded-lg transition-colors"
            >⬇ Guardar imagen</button>
          </div>
        </template>
      </BaseModal>

    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { use } from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { TooltipComponent, GridComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import PageHeader    from '../../components/PageHeader.vue'
import SectionHeader from '../../components/SectionHeader.vue'
import YearSelector  from '../../components/YearSelector.vue'
import KpiCard       from '../../components/KpiCard.vue'
import BaseModal     from '../../components/BaseModal.vue'
import { fetchFiscalYears, fetchRecaudacionKpis, fetchRecaudacionTrend, fetchRecaudacionConceptTrend } from '../../api/financiero.js'

use([LineChart, BarChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer])

const source = 'Liquidaciones presupuestarias — transparencia.jerez.es'

const availableYears = ref([])
const selectedYear   = ref(null)
const kpis           = ref(null)
const trend          = ref([])
const loading        = ref(false)
const error          = ref(null)

// ── Evolución por concepto ────────────────────────────────────────────────────
const activeConcept       = ref(null)
const showConceptModal    = ref(false)
const conceptTrendData    = ref([])
const loadingConceptTrend = ref(false)
const conceptChartRef     = ref(null)

async function openConceptTrend(concept) {
  activeConcept.value    = concept
  showConceptModal.value = true
  loadingConceptTrend.value = true
  try {
    conceptTrendData.value = await fetchRecaudacionConceptTrend(concept.code)
  } catch {
    conceptTrendData.value = []
  } finally {
    loadingConceptTrend.value = false
  }
}

async function saveConceptChartImage() {
  const instance = conceptChartRef.value?.chart
  if (!instance) return
  const chartDataUrl = instance.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#111827' })
  const chartImg = await new Promise((res, rej) => {
    const img = new Image(); img.onload = () => res(img); img.onerror = rej; img.src = chartDataUrl
  })
  const W = chartImg.width
  const HEADER = 88
  const FOOTER = 44
  const H = chartImg.height + HEADER + FOOTER
  const canvas = document.createElement('canvas')
  canvas.width = W; canvas.height = H
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#111827'; ctx.fillRect(0, 0, W, H)
  ctx.fillStyle = '#1f2937'; ctx.fillRect(0, HEADER - 2, W, 2)
  ctx.fillStyle = '#6b7280'; ctx.font = '22px system-ui,sans-serif'
  ctx.fillText((import.meta.env.VITE_CITY_NAME || 'Jerez de la Frontera').toUpperCase(), 32, 34)
  ctx.fillStyle = '#ffffff'; ctx.font = 'bold 28px system-ui,sans-serif'
  ctx.fillText(activeConcept.value?.conceptName ?? '', 32, 68)
  ctx.drawImage(chartImg, 0, HEADER)
  ctx.fillStyle = '#1f2937'; ctx.fillRect(0, HEADER + chartImg.height, W, FOOTER)
  ctx.fillStyle = '#6b7280'; ctx.font = '20px system-ui,sans-serif'
  ctx.fillText('Fuente: ' + source, 32, HEADER + chartImg.height + 30)
  const a = document.createElement('a')
  a.href = canvas.toDataURL('image/png')
  a.download = `recaudacion_${activeConcept.value?.code ?? 'concepto'}.png`
  a.click()
}

onMounted(async () => {
  try {
    const fy = await fetchFiscalYears()
    availableYears.value = fy.map(y => y.year).sort((a, b) => b - a)
    selectedYear.value   = availableYears.value[0] ?? new Date().getFullYear()

    const tr = await fetchRecaudacionTrend()
    trend.value = tr ?? []
  } catch (e) {
    error.value = 'Error cargando años fiscales: ' + e.message
  }
})

watch(selectedYear, async (yr) => {
  if (!yr) return
  loading.value = true
  error.value   = null
  kpis.value    = null
  try {
    kpis.value = await fetchRecaudacionKpis(yr)
  } catch (e) {
    error.value = 'Error cargando datos: ' + e.message
  } finally {
    loading.value = false
  }
}, { immediate: false })

// ── Gráfico de evolución de concepto ─────────────────────────────────────────

const conceptTrendOption = computed(() => {
  const data = conceptTrendData.value
  if (!data.length) return {}

  const years = data.map(r => String(r.ejercicio))

  // Tres segmentos apilados: recaudado + pendiente + brecha_prevision
  // Para ejercicios parciales aplicamos opacidad reducida por segmento
  const collected = data.map(r => ({
    value: Number(r.netCollection ?? 0),
    itemStyle: { color: r.isPartial ? 'rgba(34,197,94,0.45)' : '#22c55e' },
  }))
  const pending = data.map(r => ({
    value: Number(r.pendingCollection ?? 0),
    itemStyle: { color: r.isPartial ? 'rgba(245,158,11,0.45)' : '#f59e0b' },
  }))
  const gap = data.map(r => ({
    value: Math.max(0, Number(r.finalForecast ?? 0) - Number(r.recognizedRights ?? 0)),
    itemStyle: { color: r.isPartial ? 'rgba(75,85,99,0.45)' : '#4b5563' },
  }))

  const fmtEur = v => Number(v).toLocaleString('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
  const fmtK   = v => {
    const k = Math.abs(v) / 1000
    return (k >= 1000 ? (v / 1e6).toFixed(1) + 'M€' : Math.round(v / 1000) + 'k€')
  }

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: params => {
        const yr  = params[0].axisValue
        const row = data.find(r => String(r.ejercicio) === yr)
        const mor = row?.collectionRate != null ? ((1 - row.collectionRate) * 100).toFixed(1) + '%' : '–'
        const iniF = fmtEur(row?.finalForecast ?? 0)   // no tenemos initial en trend, usamos final
        const finF = fmtEur(row?.finalForecast ?? 0)
        const rec  = fmtEur(row?.recognizedRights ?? 0)
        const col  = fmtEur(row?.netCollection ?? 0)
        const pend = fmtEur(row?.pendingCollection ?? 0)
        const noEje = fmtEur(Math.max(0, Number(row?.finalForecast ?? 0) - Number(row?.recognizedRights ?? 0)))
        const parcial = row?.isPartial
          ? '<br/><span style="color:#fbbf24">⚠ Datos parciales — ejercicio en curso</span>' : ''
        return `<b>${yr}</b>${parcial}<br/>
          <span style="color:#6b7280">●</span> Previsión definitiva: <b>${finF}</b><br/>
          <span style="color:#a78bfa">●</span> Derechos reconocidos: <b>${rec}</b><br/>
          <span style="color:#6b7280">●</span> No liquidado: <b>${noEje}</b><br/>
          <span style="color:#22c55e">●</span> Recaudado: <b>${col}</b><br/>
          <span style="color:#f59e0b">●</span> Pendiente de cobro: <b>${pend}</b><br/>
          <hr style="border-color:#374151;margin:4px 0"/>
          Morosidad: <b style="color:#f87171">${mor}</b>`
      },
    },
    legend: {
      data: ['Recaudado', 'Pendiente de cobro', 'No liquidado'],
      textStyle: { color: '#9ca3af', fontSize: 11 },
      bottom: 0,
    },
    grid: { left: 16, right: 16, top: 16, bottom: 36, containLabel: true },
    xAxis: {
      type: 'category',
      data: years,
      axisLabel: {
        color: '#9ca3af',
        formatter: yr => {
          const row = data.find(r => String(r.ejercicio) === yr)
          return row?.isPartial ? `{partial|${yr}}` : yr
        },
        rich: { partial: { color: '#fbbf24' } },
      },
      axisLine: { lineStyle: { color: '#374151' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: '#9ca3af',
        formatter: v => {
          const a = Math.abs(v)
          if (a >= 1e6) return (v / 1e6).toFixed(1) + 'M'
          if (a >= 1e3) return (v / 1e3).toFixed(0) + 'k'
          return v
        },
      },
      splitLine: { lineStyle: { color: '#1f2937' } },
    },
    series: [
      {
        name: 'Recaudado',
        type: 'bar',
        stack: 'total',
        itemStyle: { color: '#22c55e' },
        data: collected,
        barMaxWidth: 52,
        label: {
          show: true,
          position: 'inside',
          color: '#fff',
          fontSize: 10,
          formatter: p => p.value > 0 ? fmtK(p.value) : '',
        },
      },
      {
        name: 'Pendiente de cobro',
        type: 'bar',
        stack: 'total',
        itemStyle: { color: '#f59e0b' },
        data: pending,
        barMaxWidth: 52,
        label: {
          show: true,
          position: 'inside',
          color: '#fff',
          fontSize: 10,
          formatter: p => p.value > 0 ? fmtK(p.value) : '',
        },
      },
      {
        name: 'No liquidado',
        type: 'bar',
        stack: 'total',
        itemStyle: { color: '#4b5563' },
        data: gap,
        barMaxWidth: 52,
        label: {
          show: true,
          position: 'top',
          color: '#9ca3af',
          fontSize: 10,
          formatter: p => {
            const row = data[p.dataIndex]
            const total = Number(row?.finalForecast ?? 0)
            return total > 0 ? fmtK(total) : ''
          },
        },
      },
    ],
  }
})

// ── Formateadores ──────────────────────────────────────────────────────────────

function pct(v) {
  if (v == null) return '–'
  return (v * 100).toFixed(1)
}

function eur(v) {
  if (v == null) return '–'
  return Number(v).toLocaleString('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
}

function eurShort(v) {
  if (v == null) return '–'
  return Number(v).toLocaleString('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
}

function subEficacia(k) {
  if (!k?.totalRecognizedRights || !k?.totalPendingCollection) return null
  const rec  = Number(k.totalRecognizedRights)
  const pend = Number(k.totalPendingCollection)
  const recM  = (rec  / 1e6).toFixed(1)
  const pendM = (pend / 1e6).toFixed(1)
  return `${pendM} M€ sin cobrar sobre ${recM} M€ liquidados`
}

function desvIni(k) {
  if (!k?.totalInitialForecast || !k?.totalFinalForecast) return null
  const ini = Number(k.totalInitialForecast)
  const fin = Number(k.totalFinalForecast)
  if (ini === 0) return null
  const pctVal = ((fin - ini) / ini * 100).toFixed(1)
  const sign = pctVal >= 0 ? '+' : ''
  return `Desviación sobre inicial: ${sign}${pctVal}%`
}

// ── Badges y clases ────────────────────────────────────────────────────────────

// Umbrales basados en datos empíricos del Ministerio de Hacienda (Haciendas Locales 2022):
// >93 % — nivel de Navarra/Asturias/PVasco/CyL (mejor gestión nacional)
// 85–93 % — entorno de la media nacional (90,7 %) y Extremadura (87,5 %)
// <85 % — por debajo de Andalucía (83,3 %) y Baleares (84,2 %)
// <70 % — muy deficiente, solo municipios con problemas estructurales graves
function badgeColl(rate) {
  if (rate == null) return null
  const v = rate * 100
  if (v >= 93) return { text: 'Buena gestión',      class: 'badge-green' }
  if (v >= 85) return { text: 'Gestión aceptable',  class: 'badge-blue' }
  if (v >= 70) return { text: 'Gestión deficiente', class: 'badge-yellow' }
  return { text: 'Muy deficiente', class: 'badge-red' }
}

function collRateClass(rate) {
  if (rate == null) return 'text-gray-500'
  const v = rate * 100
  if (v >= 93) return 'text-green-400'
  if (v >= 85) return 'text-blue-400'
  if (v >= 70) return 'text-yellow-400'
  return 'text-red-400'
}

function pendingClass(amount) {
  if (amount == null) return 'text-gray-500'
  return Number(amount) > 0 ? 'text-yellow-400' : 'text-gray-500'
}

// ── Series para KpiCard trend ─────────────────────────────────────────────────

const trendColl = computed(() =>
  trend.value.map(r => ({
    label:   String(r.ejercicio),
    value:   r.collectionRate != null ? +(r.collectionRate * 100).toFixed(2) : null,
    partial: r.isPartial,
  }))
)

const trendPend = computed(() =>
  trend.value.map(r => ({
    label:   String(r.ejercicio),
    value:   r.totalPendingCollection != null ? Number(r.totalPendingCollection) : null,
    partial: r.isPartial,
  }))
)

const trendRec = computed(() =>
  trend.value.map(r => ({
    label:   String(r.ejercicio),
    value:   r.totalRecognizedRights != null ? Number(r.totalRecognizedRights) : null,
    partial: r.isPartial,
  }))
)
</script>
