<template>
  <div class="mb-6">
    <div class="flex items-center gap-4 flex-wrap">
      <div>
        <h2 class="section-title">{{ title }}</h2>
        <p v-if="subtitle" class="section-subtitle">{{ subtitle }}</p>
      </div>
      <!-- Slot para controles: selector de año, botones, etc. -->
      <div v-if="$slots.default" class="flex items-center gap-2">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title:    { type: String, required: true },
  subtitle: { type: String, default: null  },
})
</script>
