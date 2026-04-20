<template>
  <div>
    <PageHeader
      title="Explorador de Líneas Presupuestarias"
      subtitle="Detalle de créditos y ejecución por línea"
    >
      <select
        v-model="direction"
        @change="loadLines"
        class="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none"
      >
        <option value="">Todos</option>
        <option value="expense">Gastos</option>
        <option value="revenue">Ingresos</option>
      </select>
      <YearSelector :years="availableYears" v-model="selectedYear" @update:modelValue="loadLines" />
    </PageHeader>

    <DataTable
      :columns="columns"
      :rows="filteredLines"
      :loading="loading"
      empty-text="Selecciona un ejercicio para explorar las líneas presupuestarias."
      row-label="líneas"
      source="Liquidación presupuestaria"
      source-icon="📊"
      :year="selectedYear"
    >
      <template #toolbar>
        <input
          v-model="filter"
          placeholder="Filtrar por descripción, capítulo…"
          class="bg-gray-700 rounded px-3 py-1.5 text-sm text-gray-200 border border-gray-600
                 focus:outline-none focus:ring-1 focus:ring-blue-500 w-72"
        />
      </template>

      <template #row="{ row }">
        <tr>
          <td class="py-2 px-3 text-gray-400 font-mono text-xs">{{ row.chapter }}</td>
          <td class="py-2 px-3 max-w-xs truncate text-sm">{{ row.description }}</td>
          <td class="py-2 px-3 text-right font-mono text-xs">{{ formatEur(row.initialCredits ?? row.initialForecast) }}</td>
          <td class="py-2 px-3 text-right font-mono text-xs">{{ formatEur(row.finalCredits ?? row.finalForecast) }}</td>
          <td class="py-2 px-3 text-right font-mono text-xs">{{ formatEur(row.recognizedObligations ?? row.recognizedRights) }}</td>
          <td class="py-2 px-3 text-right">
            <span :class="execRateBadge(row.executionRate)">
              {{ row.executionRate != null ? (row.executionRate * 100).toFixed(0) + '%' : '–' }}
            </span>
          </td>
        </tr>
      </template>
    </DataTable>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { gqlClient } from '../../api/client.js'
import { gql } from 'graphql-request'
import { fetchFiscalYears } from '../../api/financiero.js'
import PageHeader    from '../../components/PageHeader.vue'
import YearSelector  from '../../components/YearSelector.vue'
import DataTable     from '../../components/DataTable.vue'

const cityName = import.meta.env.VITE_CITY_NAME || 'Jerez de la Frontera'

const availableYears = ref([])
const selectedYear   = ref(null)
const direction      = ref('')
const filter         = ref('')
const lines          = ref([])
const loading        = ref(false)

const columns = [
  { key: 'chapter',     label: 'Cap.' },
  { key: 'description', label: 'Descripción' },
  { key: 'initial',     label: 'Inicial',    align: 'right' },
  { key: 'final',       label: 'Definitivo', align: 'right' },
  { key: 'executed',    label: 'Ejecutado',  align: 'right' },
  { key: 'rate',        label: 'Tasa',       align: 'right' },
]

const LINES_QUERY = gql`
  query BudgetLines($year: Int!, $page: Int!, $pageSize: Int!, $filters: BudgetLineFilter) {
    budgetLines(fiscalYear: $year, page: $page, pageSize: $pageSize, filters: $filters) {
      items {
        id
        description
        chapter
        initialCredits
        finalCredits
        recognizedObligations
        initialForecast
        finalForecast
        recognizedRights
        executionRate
      }
      total
    }
  }
`

const filteredLines = computed(() => {
  if (!filter.value) return lines.value
  const q = filter.value.toLowerCase()
  return lines.value.filter(l =>
    (l.description ?? '').toLowerCase().includes(q) ||
    (l.chapter ?? '').toLowerCase().includes(q)
  )
})

function formatEur(v) {
  if (v == null) return '–'
  return new Intl.NumberFormat('es-ES', {
    style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
  }).format(Number(v))
}
function execRateBadge(rate) {
  if (rate == null) return 'badge-gray'
  if (rate >= 0.85) return 'badge-green'
  if (rate >= 0.65) return 'badge-yellow'
  return 'badge-red'
}

async function loadLines() {
  if (!selectedYear.value) return
  loading.value = true
  try {
    const filters = direction.value ? { direction: direction.value } : null
    const data = await gqlClient.request(LINES_QUERY, {
      year: selectedYear.value,
      page: 1,
      pageSize: 500,
      filters,
    })
    lines.value = data.budgetLines.items
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const fys = await fetchFiscalYears()
  availableYears.value = fys.map(fy => fy.year)
  if (availableYears.value.length) {
    selectedYear.value = availableYears.value[0]
    await loadLines()
  }
})
</script>
