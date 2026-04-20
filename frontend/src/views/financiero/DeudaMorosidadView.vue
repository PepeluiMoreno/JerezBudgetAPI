<template>
  <div class="space-y-8">
    <PageHeader
      title="Deuda y Morosidad"
      subtitle="Deuda financiera anual · Morosidad trimestral Ley 15/2010"
    />

    <div v-if="loading" class="text-center py-16 text-gray-400">Cargando datos…</div>
    <div v-else-if="error" class="text-center py-16 text-red-400">{{ error }}</div>

    <template v-else>

      <!-- ── Deuda financiera ──────────────────────────────────────── -->
      <section>
        <SectionHeader title="Deuda financiera a 31 de diciembre" />

        <div v-if="!deudaRows.length" class="text-sm text-gray-500 py-4">
          Sin datos. Se cargan vía ODM (recurso <code>jerez_deuda_financiera</code>).
        </div>

        <template v-else>
          <!-- KPIs último año disponible -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <KpiCard
              :value="fmtEur(ultimo.deudaTotal)"
              label="Deuda total"
              :sub="`31-dic-${ultimo.ejercicio}`"
              source="transparencia.jerez.es — Deuda financiera PDF"
              source-icon="💳"
              :year="ultimo.ejercicio"
              :trend-data="trendDeudaTotal"
              trend-unit="€"
              :kpi-info="{
                description: 'Deuda financiera viva a 31 de diciembre. Suma de endeudamiento con entidades de crédito privadas e ICO.',
                source: 'Portal de transparencia — Deuda financiera a 31-dic'
              }"
            />
            <KpiCard
              :value="fmtEur(ultimo.deudaPrivada)"
              label="Deuda privada"
              :sub="`Entidades de crédito`"
              source="transparencia.jerez.es — Deuda financiera PDF"
              source-icon="🏦"
              :year="ultimo.ejercicio"
            />
            <KpiCard
              :value="fmtEur(ultimo.deudaIco)"
              label="Deuda ICO"
              :sub="`Préstamos ICO`"
              source="transparencia.jerez.es — Deuda financiera PDF"
              source-icon="🏛️"
              :year="ultimo.ejercicio"
            />
            <KpiCard
              :value="ultimo.deudaPercapita != null ? fmtNum(ultimo.deudaPercapita) : '—'"
              suffix=" €/hab"
              label="Deuda per cápita"
              :sub="`${ultimo.habitantes ? fmtNum(ultimo.habitantes) + ' hab.' : ''}`"
              source="transparencia.jerez.es · INE Padrón"
              source-icon="👤"
              :year="ultimo.ejercicio"
              :trend-data="trendDeudaPercapita"
              trend-unit=" €/hab"
            />
          </div>

          <!-- Tabla histórica -->
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-gray-700 text-gray-400 text-xs uppercase tracking-wider">
                  <th class="text-left py-2 pr-4 font-medium">Ejercicio</th>
                  <th class="text-right py-2 px-2 font-medium">Deuda privada</th>
                  <th class="text-right py-2 px-2 font-medium">ICO</th>
                  <th class="text-right py-2 px-2 font-medium">Total</th>
                  <th class="text-right py-2 px-2 font-medium">Per cápita</th>
                  <th class="text-right py-2 px-2 font-medium">Var. interanual</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, i) in deudaRows"
                  :key="row.ejercicio"
                  class="border-b border-gray-800 hover:bg-gray-800/40"
                >
                  <td class="py-2 pr-4 font-medium text-gray-200">{{ row.ejercicio }}</td>
                  <td class="text-right py-2 px-2 text-gray-300">{{ fmtEur(row.deudaPrivada) }}</td>
                  <td class="text-right py-2 px-2 text-gray-300">{{ fmtEur(row.deudaIco) }}</td>
                  <td class="text-right py-2 px-2 font-medium text-gray-100">{{ fmtEur(row.deudaTotal) }}</td>
                  <td class="text-right py-2 px-2 text-gray-300">
                    {{ row.deudaPercapita != null ? fmtNum(row.deudaPercapita) + ' €' : '—' }}
                  </td>
                  <td class="text-right py-2 px-2">
                    <span v-if="variacionDeuda(i) != null" :class="variacionClass(variacionDeuda(i))">
                      {{ variacionDeuda(i) > 0 ? '+' : '' }}{{ variacionDeuda(i).toFixed(1) }}%
                    </span>
                    <span v-else class="text-gray-600">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>

      <!-- ── Morosidad trimestral ──────────────────────────────────── -->
      <section>
        <SectionHeader title="Morosidad trimestral — Ley 15/2010" />
        <p class="text-xs text-gray-500 -mt-4 mb-4">
          Plazo máximo de pago: 30 días desde aprobación de la factura (art. 4 Ley 15/2010).
        </p>

        <div v-if="!morosidadRows.length" class="text-sm text-gray-500 py-4">
          Sin datos. Se cargan vía ODM (recurso <code>jerez_morosidad_trimestral</code>).
        </div>

        <template v-else>
          <!-- KPIs últimos 4 trimestres -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <KpiCard
              v-for="row in ultimos4T"
              :key="`${row.ejercicio}-${row.trimestre}`"
              :value="row.pmpTrimestral != null ? fmtNum(row.pmpTrimestral) : '—'"
              suffix=" días"
              :label="`PMP ${row.trimestre} ${row.ejercicio}`"
              :badge="pmpBadge(row.pmpTrimestral)"
              source="transparencia.jerez.es — Morosidad Ley 15/2010"
              source-icon="🗓️"
              :kpi-info="{
                description: 'Período medio de pago a proveedores calculado trimestralmente según Ley 15/2010.',
                optimal: '≤ 30 días — Cumplimiento\n30–60 días — Alerta\n> 60 días — Incumplimiento',
                source: 'Ley 15/2010, de 5 de julio, de medidas de lucha contra la morosidad'
              }"
            />
          </div>

          <!-- Tabla completa -->
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-gray-700 text-gray-400 text-xs uppercase tracking-wider">
                  <th class="text-left py-2 pr-2 font-medium">Trim.</th>
                  <th class="text-right py-2 px-2 font-medium">PMP (días)</th>
                  <th class="text-right py-2 px-2 font-medium">Pagos plazo (€)</th>
                  <th class="text-right py-2 px-2 font-medium">Fuera plazo (€)</th>
                  <th class="text-right py-2 px-2 font-medium">% fuera plazo</th>
                  <th class="text-right py-2 px-2 font-medium">Fact. pend. f.p.</th>
                  <th class="text-right py-2 px-2 font-medium">Intereses demora</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in morosidadRows"
                  :key="`${row.ejercicio}-${row.trimestre}`"
                  class="border-b border-gray-800 hover:bg-gray-800/40"
                >
                  <td class="py-2 pr-2 font-medium text-gray-200">
                    {{ row.ejercicio }} {{ row.trimestre }}
                  </td>
                  <td class="text-right py-2 px-2">
                    <span :class="pmpClass(row.pmpTrimestral)">
                      {{ row.pmpTrimestral != null ? fmtNum(row.pmpTrimestral) : '—' }}
                    </span>
                  </td>
                  <td class="text-right py-2 px-2 text-gray-300">{{ fmtEur(row.pagosPlazoImporte) }}</td>
                  <td class="text-right py-2 px-2 text-gray-300">{{ fmtEur(row.pagosFueraPlazoImporte) }}</td>
                  <td class="text-right py-2 px-2">
                    <span v-if="row.ratioFueraPlazo != null" :class="ratioBadgeClass(row.ratioFueraPlazo)">
                      {{ pct(row.ratioFueraPlazo) }}%
                    </span>
                    <span v-else class="text-gray-600">—</span>
                  </td>
                  <td class="text-right py-2 px-2 text-gray-400 text-xs">
                    {{ row.facturasPendientesFueraPlazoCount != null ? row.facturasPendientesFueraPlazoCount : '—' }}
                    <span v-if="row.facturasPendientesFueraPlazoImporte">
                      ({{ fmtEur(row.facturasPendientesFueraPlazoImporte) }})
                    </span>
                  </td>
                  <td class="text-right py-2 px-2 text-gray-400">{{ fmtEur(row.interesesDemora) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>

    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import PageHeader from '../../components/PageHeader.vue'
import SectionHeader from '../../components/SectionHeader.vue'
import KpiCard from '../../components/KpiCard.vue'
import { fetchDeudaHistorica, fetchMorosidadTrimestral } from '../../api/financiero.js'

const loading = ref(false)
const error = ref(null)
const deudaRows = ref([])
const morosidadRows = ref([])

// ── Derived ──────────────────────────────────────────────────────────────────

const ultimo = computed(() => deudaRows.value.at(-1) || {})

const trendDeudaTotal = computed(() =>
  deudaRows.value
    .filter(r => r.deudaTotal != null)
    .map(r => ({ label: String(r.ejercicio), value: r.deudaTotal }))
)

const trendDeudaPercapita = computed(() =>
  deudaRows.value
    .filter(r => r.deudaPercapita != null)
    .map(r => ({ label: String(r.ejercicio), value: r.deudaPercapita }))
)

const ultimos4T = computed(() => morosidadRows.value.slice(-4))

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtEur(val) {
  if (val == null) return '—'
  return new Intl.NumberFormat('es-ES', {
    style: 'currency', currency: 'EUR', maximumFractionDigits: 0
  }).format(val)
}

function fmtNum(val) {
  if (val == null) return '—'
  return new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 }).format(val)
}

function pct(val) {
  if (val == null) return '—'
  return (val * 100).toFixed(1)
}

function variacionDeuda(i) {
  if (i === 0) return null
  const prev = deudaRows.value[i - 1].deudaTotal
  const curr = deudaRows.value[i].deudaTotal
  if (!prev || !curr) return null
  return ((curr - prev) / prev) * 100
}

function variacionClass(v) {
  if (v > 0)  return 'text-red-400'
  if (v < -1) return 'text-green-400'
  return 'text-gray-400'
}

function pmpBadge(val) {
  if (val == null) return null
  if (val <= 30)  return { text: 'OK',       variant: 'green' }
  if (val <= 60)  return { text: 'Alerta',   variant: 'yellow' }
  return               { text: 'Incumple', variant: 'red' }
}

function pmpClass(val) {
  if (val == null) return 'text-gray-500'
  if (val <= 30)  return 'text-green-400 font-medium'
  if (val <= 60)  return 'text-yellow-400 font-medium'
  return               'text-red-400 font-bold'
}

function ratioBadgeClass(r) {
  if (r <= 0.20) return 'text-green-400'
  if (r <= 0.40) return 'text-yellow-400'
  return              'text-red-400 font-bold'
}

// ── Carga ─────────────────────────────────────────────────────────────────────

onMounted(async () => {
  loading.value = true
  try {
    const [deuda, morosidad] = await Promise.all([
      fetchDeudaHistorica(),
      fetchMorosidadTrimestral(),
    ])
    deudaRows.value     = deuda
    morosidadRows.value = morosidad
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>
