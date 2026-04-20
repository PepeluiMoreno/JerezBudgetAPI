<template>
  <div class="space-y-8">
    <PageHeader
      title="Período Medio de Pago"
      subtitle="Plazo de pago a proveedores por entidad del grupo municipal · Ley 15/2010 — máximo 30 días"
    >
      <YearSelector :years="availableYears" v-model="selectedYear" @update:modelValue="loadMensual" />
    </PageHeader>

    <!-- Estado de carga / error -->
    <div v-if="loading" class="text-center py-16 text-gray-400">Cargando datos…</div>
    <div v-else-if="error" class="text-center py-16 text-red-400">{{ error }}</div>

    <template v-else>

      <!-- ── KPIs resumen del año ──────────────────────────────────── -->
      <section>
        <SectionHeader title="Resumen del ejercicio" />
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">

          <KpiCard
            v-for="entidad in entidades"
            :key="entidad.nif"
            :value="pmpLabel(resumenPorEntidad[entidad.nif]?.promedio)"
            suffix=" días"
            :label="entidad.nombre"
            :sub="entidad.tipo === 'ayto' ? 'Ayuntamiento' : entidad.tipo"
            :badge="alertaBadge(resumenPorEntidad[entidad.nif]?.alerta)"
            source="transparencia.jerez.es — PMP mensual"
            source-icon="🗓️"
            :year="selectedYear"
            :kpi-info="{
              description: 'Período medio de pago a proveedores (días). Media de los meses con datos disponibles en el ejercicio.',
              optimal: '≤ 30 días — Cumplimiento Ley 15/2010\n30–60 días — Zona de alerta\n> 60 días — Incumplimiento grave',
              source: 'Portal de transparencia · Ley 15/2010 art. 5 — plazo máximo 30 días desde la aprobación de la factura'
            }"
            :trend-data="trendEntidad(entidad.nif)"
            trend-unit=" días"
          />

        </div>
      </section>

      <!-- ── Grid mensual ──────────────────────────────────────────── -->
      <section v-if="mensualRows.length">
        <SectionHeader title="Evolución mensual" />
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-gray-700 text-gray-400 text-xs uppercase tracking-wider">
                <th class="text-left py-2 pr-4 font-medium">Entidad</th>
                <th
                  v-for="mes in MESES"
                  :key="mes.n"
                  class="text-center py-2 px-1 font-medium w-14"
                >{{ mes.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="entidad in entidades"
                :key="entidad.nif"
                class="border-b border-gray-800"
              >
                <td class="py-2 pr-4 text-gray-300 text-xs whitespace-nowrap">{{ entidad.nombre }}</td>
                <td
                  v-for="mes in MESES"
                  :key="mes.n"
                  class="text-center py-2 px-1"
                >
                  <span
                    v-if="cellValue(entidad.nif, mes.n) !== null"
                    class="inline-block px-1.5 py-0.5 rounded text-xs font-medium"
                    :class="cellClass(entidad.nif, mes.n)"
                  >
                    {{ cellValue(entidad.nif, mes.n) }}
                  </span>
                  <span v-else class="text-gray-700 text-xs">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- Leyenda -->
        <div class="flex gap-4 mt-3 text-xs text-gray-500">
          <span class="flex items-center gap-1"><span class="inline-block w-3 h-3 rounded bg-green-700"></span> ≤ 30 días</span>
          <span class="flex items-center gap-1"><span class="inline-block w-3 h-3 rounded bg-yellow-700"></span> 30–60 días</span>
          <span class="flex items-center gap-1"><span class="inline-block w-3 h-3 rounded bg-red-700"></span> &gt; 60 días</span>
        </div>
      </section>

      <!-- ── Tendencia anual ───────────────────────────────────────── -->
      <section v-if="anualRows.length">
        <SectionHeader title="Evolución anual del PMP promedio" />
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-gray-700 text-gray-400 text-xs uppercase tracking-wider">
                <th class="text-left py-2 pr-4 font-medium">Entidad</th>
                <th
                  v-for="year in anualYears"
                  :key="year"
                  class="text-center py-2 px-2 font-medium w-16"
                >{{ year }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="entidad in entidadesAnual"
                :key="entidad.nif"
                class="border-b border-gray-800"
              >
                <td class="py-2 pr-4 text-gray-300 text-xs whitespace-nowrap">{{ entidad.nombre }}</td>
                <td
                  v-for="year in anualYears"
                  :key="year"
                  class="text-center py-2 px-2"
                >
                  <span
                    v-if="anualCell(entidad.nif, year) !== null"
                    class="inline-block text-xs font-medium"
                    :class="anualCellClass(entidad.nif, year)"
                  >
                    {{ anualCell(entidad.nif, year) }} d
                    <span class="text-gray-500 font-normal" v-if="anualIncumpl(entidad.nif, year)">
                      ({{ anualIncumpl(entidad.nif, year) }}m)
                    </span>
                  </span>
                  <span v-else class="text-gray-700 text-xs">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="text-xs text-gray-600 mt-2">d = días · m = meses en incumplimiento (PMP &gt; 30 días)</p>
      </section>

      <div v-if="!mensualRows.length && !loading" class="text-center py-12 text-gray-500">
        No hay datos de PMP para {{ selectedYear }}.
        <p class="text-xs mt-2 text-gray-600">Los datos se cargan vía OpenDataManager (recurso <code>jerez_pmp_mensual</code>).</p>
      </div>

    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import PageHeader from '../../components/PageHeader.vue'
import SectionHeader from '../../components/SectionHeader.vue'
import YearSelector from '../../components/YearSelector.vue'
import KpiCard from '../../components/KpiCard.vue'
import { fetchPmpMensual, fetchPmpAnual, fetchFiscalYears } from '../../api/financiero.js'

const MESES = [
  { n: 1, label: 'Ene' }, { n: 2, label: 'Feb' }, { n: 3, label: 'Mar' },
  { n: 4, label: 'Abr' }, { n: 5, label: 'May' }, { n: 6, label: 'Jun' },
  { n: 7, label: 'Jul' }, { n: 8, label: 'Ago' }, { n: 9, label: 'Sep' },
  { n: 10, label: 'Oct' }, { n: 11, label: 'Nov' }, { n: 12, label: 'Dic' },
]

const loading = ref(false)
const error = ref(null)
const selectedYear = ref(new Date().getFullYear())
const availableYears = ref([])
const mensualRows = ref([])
const anualRows = ref([])

// ── Datos derivados ──────────────────────────────────────────────────────────

// Mapa rápido: nif → { mes → row }
const mensualMap = computed(() => {
  const m = {}
  for (const r of mensualRows.value) {
    if (!m[r.entidadNif]) m[r.entidadNif] = {}
    m[r.entidadNif][r.mes] = r
  }
  return m
})

// Entidades únicas del año mensual
const entidades = computed(() => {
  const seen = new Map()
  for (const r of mensualRows.value) {
    if (!seen.has(r.entidadNif)) {
      seen.set(r.entidadNif, { nif: r.entidadNif, nombre: r.entidadNombre, tipo: r.entidadTipo })
    }
  }
  return [...seen.values()]
})

// Entidades únicas del histórico anual
const entidadesAnual = computed(() => {
  const seen = new Map()
  for (const r of anualRows.value) {
    if (!seen.has(r.entidadNif)) {
      seen.set(r.entidadNif, { nif: r.entidadNif, nombre: r.entidadNombre, tipo: r.entidadTipo })
    }
  }
  return [...seen.values()]
})

// Años disponibles en el histórico anual
const anualYears = computed(() => {
  const years = [...new Set(anualRows.value.map(r => r.ejercicio))].sort()
  return years
})

// Resumen por entidad (promedio + alerta dominante del año)
const resumenPorEntidad = computed(() => {
  const res = {}
  for (const r of anualRows.value.filter(r => r.ejercicio === selectedYear.value)) {
    res[r.entidadNif] = {
      promedio: r.pmpPromedio,
      mesesIncumplimiento: r.mesesIncumplimiento,
      alerta: r.alerta,
    }
  }
  return res
})

// ── Helpers de celda ─────────────────────────────────────────────────────────

function cellValue(nif, mes) {
  const r = mensualMap.value[nif]?.[mes]
  return r ? Math.round(r.pmpDias) : null
}

function cellClass(nif, mes) {
  const r = mensualMap.value[nif]?.[mes]
  if (!r) return ''
  return alertaClass(r.alerta)
}

function alertaClass(alerta) {
  if (alerta === 'verde')    return 'bg-green-900 text-green-300'
  if (alerta === 'amarillo') return 'bg-yellow-900 text-yellow-300'
  return 'bg-red-900 text-red-300'
}

function alertaBadge(alerta) {
  if (!alerta) return null
  if (alerta === 'verde')    return { text: 'OK',      variant: 'green' }
  if (alerta === 'amarillo') return { text: 'Alerta',  variant: 'yellow' }
  return                            { text: 'Incumple', variant: 'red' }
}

function pmpLabel(val) {
  if (val == null) return '—'
  return Math.round(val * 10) / 10
}

// ── Helpers tabla anual ───────────────────────────────────────────────────────

// Mapa anual rápido
const anualMap = computed(() => {
  const m = {}
  for (const r of anualRows.value) {
    if (!m[r.entidadNif]) m[r.entidadNif] = {}
    m[r.entidadNif][r.ejercicio] = r
  }
  return m
})

function anualCell(nif, year) {
  const r = anualMap.value[nif]?.[year]
  return r ? Math.round(r.pmpPromedio * 10) / 10 : null
}

function anualCellClass(nif, year) {
  const r = anualMap.value[nif]?.[year]
  if (!r) return ''
  return alertaClass(r.alerta)
}

function anualIncumpl(nif, year) {
  const r = anualMap.value[nif]?.[year]
  return r?.mesesIncumplimiento || 0
}

// ── Trend data para KpiCard ───────────────────────────────────────────────────

function trendEntidad(nif) {
  return anualYears.value
    .map(year => {
      const r = anualMap.value[nif]?.[year]
      return r ? { label: String(year), value: Math.round(r.pmpPromedio * 10) / 10 } : null
    })
    .filter(Boolean)
}

// ── Carga de datos ────────────────────────────────────────────────────────────

async function loadMensual() {
  loading.value = true
  error.value = null
  try {
    mensualRows.value = await fetchPmpMensual(selectedYear.value)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadAnual() {
  try {
    anualRows.value = await fetchPmpAnual()
  } catch {
    // No bloquear la vista si el histórico falla
  }
}

onMounted(async () => {
  const years = await fetchFiscalYears()
  availableYears.value = years.map(y => y.year).sort((a, b) => b - a)
  if (availableYears.value.length) selectedYear.value = availableYears.value[0]
  await Promise.all([loadMensual(), loadAnual()])
})
</script>
