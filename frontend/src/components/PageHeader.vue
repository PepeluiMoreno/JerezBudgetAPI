<template>
  <div class="mb-6">
    <!-- Ciudad + selector de ejercicio en la misma línea -->
    <div class="flex items-center gap-4 flex-wrap">
      <h1 class="text-2xl font-bold text-white tracking-tight">{{ cityName }}</h1>
      <slot />
    </div>
    <!-- Título de sección + subtítulo -->
    <div class="mt-1">
      <h2 class="text-sm font-semibold text-blue-400 uppercase tracking-widest">{{ title }}</h2>
      <p v-if="subtitle" class="text-xs text-gray-500 mt-0.5">{{ subtitle }}</p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title:    { type: String, required: true },
  subtitle: { type: String, default: null  },
})

const cityName = import.meta.env.VITE_CITY_NAME || 'Jerez de la Frontera'
</script>
