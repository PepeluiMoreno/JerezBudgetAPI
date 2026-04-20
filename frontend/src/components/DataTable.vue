<template>
  <div class="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden">
    <!-- Barra superior: slot para filtros/controles + contador -->
    <div v-if="$slots.toolbar || showCount"
         class="flex items-center justify-between px-4 py-3 border-b border-gray-700">
      <slot name="toolbar" />
      <span v-if="showCount" class="text-xs text-gray-500 ml-auto">
        {{ rows.length }} {{ rowLabel }}
      </span>
    </div>

    <!-- Tabla -->
    <div :class="maxHeight ? `overflow-y-auto ${maxHeight}` : ''" class="overflow-x-auto">
      <table class="data-table w-full">
        <thead :class="stickyHeader ? 'sticky top-0 bg-gray-800 z-10' : ''">
          <tr>
            <th
              v-for="col in columns"
              :key="col.key"
              :class="['py-2 px-3 text-left border-b border-gray-700 text-xs text-gray-400 uppercase tracking-wide',
                       col.align === 'right' ? 'text-right' : '',
                       col.class ?? '']"
            >
              {{ col.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="columns.length" class="text-center py-10 text-gray-500">
              <div class="flex items-center justify-center gap-2">
                <div class="animate-spin h-5 w-5 border-2 border-blue-500 border-t-transparent rounded-full"></div>
                Cargando…
              </div>
            </td>
          </tr>
          <tr v-else-if="!rows.length">
            <td :colspan="columns.length" class="text-center py-10 text-gray-500 text-sm">
              {{ emptyText }}
            </td>
          </tr>
          <!-- Slot por fila: permite celdas con formato personalizado -->
          <slot v-else name="row" v-for="row in rows" :row="row" />
        </tbody>
      </table>
    </div>

    <!-- Pie con fuente -->
    <div v-if="source" class="px-4 py-2 border-t border-gray-700">
      <CardFooter :source="source" :icon="sourceIcon" :year="year" />
    </div>
  </div>
</template>

<script setup>
import CardFooter from './CardFooter.vue'

defineProps({
  // [ { key: 'name', label: 'Nombre', align: 'left', class: '' } ]
  columns:      { type: Array,   required: true },
  rows:         { type: Array,   default: () => [] },
  loading:      { type: Boolean, default: false },
  emptyText:    { type: String,  default: 'Sin datos' },
  stickyHeader: { type: Boolean, default: true },
  maxHeight:    { type: String,  default: 'max-h-[60vh]' },
  showCount:    { type: Boolean, default: true },
  rowLabel:     { type: String,  default: 'filas' },
  source:       { type: String,  default: null },
  sourceIcon:   { type: String,  default: '📂' },
  year:         { type: [String, Number], default: null },
})
</script>
