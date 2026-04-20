<template>
  <div class="bg-gray-800 border border-gray-700 rounded-xl p-10 text-center max-w-2xl mx-auto mt-8">
    <div class="text-5xl mb-4">{{ icon }}</div>
    <h3 class="text-lg font-medium text-gray-300 mb-2">{{ title }}</h3>
    <p class="text-sm text-gray-500 mb-6">{{ description }}</p>
    <div class="text-left inline-block">
      <p class="text-xs text-gray-600 font-mono mb-2">Pendiente implementar ({{ sprint }}):</p>
      <ul class="text-xs text-gray-600 space-y-1 font-mono">
        <li v-for="item in pending" :key="item">• {{ item }}</li>
      </ul>
    </div>
    <div class="mt-6">
      <span class="badge-gray text-xs">{{ sprint }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  sprint: String,
  icon: { type: String, default: '🔧' },
  title: String,
  description: String,
  pending: { type: Array, default: () => [] },
})
</script>
