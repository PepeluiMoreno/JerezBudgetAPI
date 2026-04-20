<template>
  <div class="mt-3 pt-2 border-t border-gray-700 flex items-center gap-1.5 text-xs text-gray-500">
    <span class="flex-shrink-0">{{ icon }}</span>
    <span>{{ source }}</span>
    <span v-if="year" class="ml-auto text-gray-600">{{ year }}</span>
  </div>
</template>

<script setup>
defineProps({
  source: { type: String, required: true },
  icon:   { type: String, default: '📂' },
  year:   { type: [String, Number], default: null },
})
</script>
