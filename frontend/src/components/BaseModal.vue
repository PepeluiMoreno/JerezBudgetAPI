<template>
  <teleport to="body">
    <transition name="modal">
      <div
        v-if="modelValue"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        @click.self="$emit('update:modelValue', false)"
      >
        <!-- Fondo -->
        <div class="absolute inset-0 bg-black/70 backdrop-blur-sm" @click="$emit('update:modelValue', false)" />

        <!-- Contenedor -->
        <div
          class="relative bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-full flex flex-col"
          :class="maxWidth"
          :style="maxHeight ? `max-height: ${maxHeight}` : 'max-height: 90vh'"
        >
          <!-- Cabecera -->
          <div class="flex items-start justify-between px-5 py-4 border-b border-gray-800 flex-shrink-0">
            <div>
              <h3 class="text-base font-semibold text-white leading-tight">{{ title }}</h3>
              <p v-if="subtitle" class="text-xs text-gray-500 mt-0.5">{{ subtitle }}</p>
            </div>
            <button
              @click="$emit('update:modelValue', false)"
              class="ml-4 text-gray-500 hover:text-white transition-colors text-xl leading-none flex-shrink-0"
            >✕</button>
          </div>

          <!-- Cuerpo (scroll) -->
          <div class="overflow-y-auto flex-1 px-5 py-4">
            <slot />
          </div>

          <!-- Pie opcional -->
          <div v-if="$slots.footer" class="px-5 py-3 border-t border-gray-800 flex-shrink-0">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, required: true },
  title:      { type: String,  required: true },
  subtitle:   { type: String,  default: null  },
  maxWidth:   { type: String,  default: 'max-w-lg' },
  maxHeight:  { type: String,  default: null  },
})
defineEmits(['update:modelValue'])
</script>

<style scoped>
.modal-enter-active, .modal-leave-active { transition: opacity 0.15s ease; }
.modal-enter-from, .modal-leave-to       { opacity: 0; }
.modal-enter-active .relative,
.modal-leave-active .relative            { transition: transform 0.15s ease; }
.modal-enter-from .relative,
.modal-leave-to .relative                { transform: scale(0.97); }
</style>
