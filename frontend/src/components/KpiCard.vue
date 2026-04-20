<template>
  <div class="kpi-card relative">

    <!-- ── Icono de evolución (siempre visible, esquina superior derecha) ── -->
    <div class="absolute top-3 right-3 flex gap-1.5">
      <button
        v-if="kpiInfo"
        @click="showInfo = true"
        title="¿Qué mide este indicador?"
        class="w-7 h-7 flex items-center justify-center rounded-full bg-gray-700 hover:bg-blue-700
               text-gray-400 hover:text-white transition-colors text-sm leading-none"
      >ℹ</button>
      <button
        v-if="trendData && trendData.length"
        @click="showTrend = true"
        title="Ver evolución histórica"
        class="w-7 h-7 flex items-center justify-center rounded-full bg-gray-700 hover:bg-blue-700
               text-gray-300 hover:text-white transition-colors text-base leading-none"
      >📈</button>
    </div>

    <!-- ── Valor principal ──────────────────────────────────────── -->
    <div class="kpi-value">
      {{ value }}
      <span v-if="suffix" class="text-sm font-normal text-gray-400">{{ suffix }}</span>
    </div>

    <!-- ── Etiqueta ─────────────────────────────────────────────── -->
    <div class="kpi-label">{{ label }}</div>

    <!-- ── Badge de estado ──────────────────────────────────────── -->
    <div v-if="badge" class="mt-2">
      <span :class="badge.class">{{ badge.text }}</span>
    </div>

    <!-- ── Subtexto ──────────────────────────────────────────────── -->
    <div v-if="sub" class="mt-2 text-xs text-gray-500">{{ sub }}</div>

    <!-- ── Slot para contenido adicional ────────────────────────── -->
    <slot />

    <!-- ── Pie con fuente ────────────────────────────────────────── -->
    <CardFooter v-if="source" :source="source" :icon="sourceIcon" :year="year" />

    <!-- ── Modal: Información del indicador ─────────────────────── -->
    <BaseModal
      v-if="kpiInfo"
      v-model="showInfo"
      :title="label"
      subtitle="Información del indicador"
    >
      <div class="space-y-4 text-sm">
        <section v-if="kpiInfo.description">
          <h4 class="text-xs font-semibold text-blue-400 uppercase tracking-wide mb-1">¿Qué mide?</h4>
          <p class="text-gray-300 leading-relaxed">{{ kpiInfo.description }}</p>
        </section>

        <section v-if="kpiInfo.source">
          <h4 class="text-xs font-semibold text-blue-400 uppercase tracking-wide mb-1">Fuente</h4>
          <p class="text-gray-300">{{ kpiInfo.source }}</p>
        </section>

        <section v-if="kpiInfo.optimal">
          <h4 class="text-xs font-semibold text-green-400 uppercase tracking-wide mb-1">Valor óptimo / referencia</h4>
          <p class="text-gray-300 leading-relaxed">{{ kpiInfo.optimal }}</p>
        </section>

        <section v-if="kpiInfo.warning">
          <h4 class="text-xs font-semibold text-yellow-400 uppercase tracking-wide mb-1">Señales de alerta</h4>
          <p class="text-gray-300 leading-relaxed">{{ kpiInfo.warning }}</p>
        </section>

        <section v-if="kpiInfo.notes">
          <h4 class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Notas</h4>
          <p class="text-gray-400 leading-relaxed text-xs">{{ kpiInfo.notes }}</p>
        </section>

        <!-- Valor actual resaltado -->
        <div class="mt-2 p-3 bg-gray-800 rounded-lg flex items-center justify-between gap-3">
          <span class="text-xs text-gray-500 whitespace-nowrap">Valor ({{ year ?? '–' }})</span>
          <span class="text-lg font-bold text-white tabular-nums">
            {{ value }}<span v-if="suffix" class="text-sm font-normal text-gray-400 ml-1">{{ suffix }}</span>
          </span>
          <span v-if="badge" :class="badge.class">{{ badge.text }}</span>
        </div>
      </div>
    </BaseModal>

    <!-- ── Modal: Evolución histórica ───────────────────────────── -->
    <BaseModal
      v-if="trendData && trendData.length"
      v-model="showTrend"
      :title="label"
      subtitle="Evolución histórica"
      max-width="max-w-2xl"
    >
      <VChart
        ref="chartRef"
        :option="trendChartOption"
        style="height: 300px;"
        autoresize
      />

      <template #footer>
        <div class="flex items-center justify-between gap-3">
          <span v-if="trendSource || source" class="text-xs text-gray-500">
            Fuente: {{ trendSource ?? source }}
          </span>
          <span v-else class="flex-1" />
          <button
            @click="saveChartImage"
            class="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700
                   text-white text-sm rounded-lg transition-colors"
          >
            ⬇ Guardar imagen
          </button>
        </div>
      </template>
    </BaseModal>

  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import CardFooter from './CardFooter.vue'
import BaseModal  from './BaseModal.vue'

const cityName = import.meta.env.VITE_CITY_NAME || 'Jerez de la Frontera'

const props = defineProps({
  value:      { type: [String, Number], required: true },
  suffix:     { type: String,  default: null },
  label:      { type: String,  required: true },
  sub:        { type: String,  default: null },
  badge:      { type: Object,  default: null },
  source:     { type: String,  default: null },
  sourceIcon: { type: String,  default: '📂' },
  year:       { type: [String, Number], default: null },
  // { description, source, optimal, warning, notes }
  kpiInfo:     { type: Object,  default: null },
  // [{ label: '2022', value: 4543800, partial?: true }]
  trendData:   { type: Array,   default: null },
  trendUnit:   { type: String,  default: '' },
  // Fuente que se muestra en el footer del modal de evolución histórica.
  // Si no se indica, se reutiliza `source`. Útil cuando la serie combina
  // varias fuentes según el tramo temporal (p.ej. CG + Liquidaciones).
  trendSource: { type: String,  default: null },
})

const showInfo  = ref(false)
const showTrend = ref(false)
const chartRef  = ref(null)

const trendChartOption = computed(() => {
  if (!props.trendData?.length) return {}
  const labels  = props.trendData.map(p => p.label ?? p.year ?? p.ejercicio)
  const rawVals = props.trendData.map(p => p.value ?? p.valor ?? null)
  const partial = props.trendData.map(p => !!p.partial)

  // Línea principal: los puntos parciales se sustituyen por null (rompe la línea)
  const lineVals    = rawVals.map((v, i) => partial[i] ? null : v)
  // Serie scatter: sólo los puntos parciales con valor real
  const scatterVals = rawVals.map((v, i) => (partial[i] && v != null) ? v : null)
  const hasPartial  = scatterVals.some(v => v != null)

  const fmtVal = v => v != null
    ? Number(v).toLocaleString('es-ES') + (props.trendUnit ? ' ' + props.trendUnit : '')
    : '–'

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      formatter: params => {
        const lines = params
          .filter(p => p.value != null)
          .map(p => {
            const isPartialPt = p.seriesIndex === 1
            const label = isPartialPt
              ? `<span style="color:#9ca3af">${fmtVal(p.value)} <i>(datos parciales)</i></span>`
              : `<b>${fmtVal(p.value)}</b>`
            return label
          })
        return `${params[0].axisValue}<br/>${lines.join('<br/>') || '–'}`
      },
    },
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { color: '#9ca3af' },
      axisLine:  { lineStyle: { color: '#374151' } },
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
        type:         'line',
        data:         lineVals,
        connectNulls: false,
        itemStyle:    { color: '#3b82f6' },
        lineStyle:    { width: 2, color: '#3b82f6' },
        areaStyle:    { color: 'rgba(59,130,246,0.1)' },
        symbol:       'circle',
        symbolSize:   v => v == null ? 0 : 6,
      },
      ...(hasPartial ? [{
        type:       'scatter',
        data:       scatterVals,
        symbol:     'circle',
        symbolSize: 9,
        itemStyle:  { color: '#f59e0b' },
        tooltip:    { show: true },
        z:          5,
      }] : []),
    ],
  }
})

/**
 * Exporta la gráfica como PNG añadiendo cabecera (ciudad, indicador) y fuente
 * mediante composición en un canvas 2D — sin dependencias externas.
 */
async function saveChartImage() {
  const instance = chartRef.value?.chart
  if (!instance) return

  // Obtener imagen del gráfico ECharts (@2x)
  const chartDataUrl = instance.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#111827' })
  const chartImg = await loadImage(chartDataUrl)

  const W = chartImg.width
  const HEADER = 88   // píxeles @2x
  const FOOTER = props.source ? 44 : 0
  const H = chartImg.height + HEADER + FOOTER

  const canvas = document.createElement('canvas')
  canvas.width  = W
  canvas.height = H

  const ctx = canvas.getContext('2d')

  // Fondo
  ctx.fillStyle = '#111827'
  ctx.fillRect(0, 0, W, H)

  // Separador superior
  ctx.fillStyle = '#1f2937'
  ctx.fillRect(0, HEADER - 2, W, 2)

  // Ciudad (pequeño, gris)
  ctx.fillStyle = '#6b7280'
  ctx.font = '22px system-ui,-apple-system,sans-serif'
  ctx.fillText(cityName.toUpperCase(), 32, 34)

  // Indicador (blanco, negrita)
  ctx.fillStyle = '#ffffff'
  ctx.font = 'bold 30px system-ui,-apple-system,sans-serif'
  ctx.fillText(props.label, 32, 68)

  // Gráfico
  ctx.drawImage(chartImg, 0, HEADER)

  // Fuente (pie)
  if (props.source) {
    ctx.fillStyle = '#1f2937'
    ctx.fillRect(0, HEADER + chartImg.height, W, FOOTER)
    ctx.fillStyle = '#6b7280'
    ctx.font = '20px system-ui,-apple-system,sans-serif'
    ctx.fillText('Fuente: ' + props.source, 32, HEADER + chartImg.height + 30)
  }

  const a = document.createElement('a')
  a.href = canvas.toDataURL('image/png')
  a.download = `${props.label.replace(/\s+/g, '_')}.png`
  a.click()
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })
}
</script>
