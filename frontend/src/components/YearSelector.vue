<template>
  <div class="flex items-center gap-2">
    <span class="text-xs text-gray-400 uppercase tracking-wide whitespace-nowrap">{{ label }}</span>
    <select
      :value="modelValue"
      @change="$emit('update:modelValue', Number($event.target.value))"
      class="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200
             focus:outline-none focus:ring-1 focus:ring-blue-500"
    >
      <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
    </select>
  </div>
</template>

<script setup>
defineProps({
  years:      { type: Array,  required: true },
  modelValue: { type: Number, default: null  },
  label:      { type: String, default: 'Ejercicio' },
})
defineEmits(['update:modelValue'])
</script>
