<template>
  <aside class="w-60 flex-shrink-0 bg-gray-800 border-r border-gray-700 flex flex-col">

    <!-- Cabecera -->
    <div class="p-5 border-b border-gray-700">
      <div class="flex items-center gap-3">
        <img src="/ocm-logo.jpg" alt="OCM Jerez" class="w-9 h-9 rounded-full object-cover flex-shrink-0" />
        <div>
          <h1 class="text-lg font-bold leading-tight">
            <span class="text-blue-400">City</span><span class="text-white">Dashboard</span>
          </h1>
          <p class="text-xs text-gray-400 leading-tight">Panel de Control Municipal</p>
        </div>
      </div>
    </div>

    <!-- Navegación -->
    <nav class="flex-1 p-3 space-y-1 overflow-y-auto">

      <!-- 1. Ciudad -->
      <router-link to="/ciudad" class="nav-item" :class="{ active: isActive('/ciudad') }">
        <span class="text-base">🏙️</span>
        <span>Ciudad</span>
      </router-link>

      <!-- 2. Gestión Económico-Financiera (expandible) -->
      <div>
        <router-link
          to="/financiero/rigor"
          class="nav-item"
          :class="{ active: isActive('/financiero') }"
        >
          <span class="text-base">💰</span>
          <span class="flex-1">Gestión Financiera</span>
          <span class="text-gray-500 text-xs">{{ isActive('/financiero') ? '▾' : '▸' }}</span>
        </router-link>
        <div v-if="isActive('/financiero')" class="ml-8 mt-1 space-y-1">
          <router-link to="/financiero/rigor" class="nav-item text-xs py-1.5"
            :class="{ active: route.path === '/financiero/rigor' }">
            Rigor presupuestario
          </router-link>
          <router-link to="/financiero/sostenibilidad" class="nav-item text-xs py-1.5"
            :class="{ active: route.path === '/financiero/sostenibilidad' }">
            Sostenibilidad
          </router-link>
          <router-link to="/financiero/comparativa" class="nav-item text-xs py-1.5"
            :class="{ active: route.path === '/financiero/comparativa' }">
            Comparativa municipal
          </router-link>
          <router-link to="/financiero/explorador" class="nav-item text-xs py-1.5"
            :class="{ active: route.path === '/financiero/explorador' }">
            Explorador de líneas
          </router-link>
          <router-link to="/financiero/recaudacion" class="nav-item text-xs py-1.5"
            :class="{ active: route.path === '/financiero/recaudacion' }">
            Eficacia en recaudación
          </router-link>
          <router-link to="/financiero/pmp" class="nav-item text-xs py-1.5"
            :class="{ active: route.path === '/financiero/pmp' }">
            Período Medio de Pago
          </router-link>
          <router-link to="/financiero/deuda-morosidad" class="nav-item text-xs py-1.5"
            :class="{ active: route.path === '/financiero/deuda-morosidad' }">
            Deuda y Morosidad
          </router-link>
        </div>
      </div>

      <!-- 3. Recursos Humanos -->
      <router-link to="/rrhh" class="nav-item" :class="{ active: isActive('/rrhh') }">
        <span class="text-base">👥</span>
        <span>Recursos Humanos</span>
        <span class="badge-gray ml-auto text-xs">S13</span>
      </router-link>

      <!-- 4. Calidad de Servicios -->
      <router-link to="/calidad" class="nav-item" :class="{ active: isActive('/calidad') }">
        <span class="text-base">⭐</span>
        <span>Calidad de Servicios</span>
        <span class="badge-gray ml-auto text-xs">S14</span>
      </router-link>

      <!-- 5. Planes, Convenios y Proyectos -->
      <router-link to="/planes" class="nav-item" :class="{ active: isActive('/planes') }">
        <span class="text-base">📋</span>
        <span>Planes y Convenios</span>
        <span class="badge-gray ml-auto text-xs">S16</span>
      </router-link>

      <!-- 6. Subvenciones -->
      <router-link to="/subvenciones" class="nav-item" :class="{ active: isActive('/subvenciones') }">
        <span class="text-base">🏦</span>
        <span>Subvenciones</span>
        <span class="badge-gray ml-auto text-xs">S15</span>
      </router-link>

      <!-- 7. Contratación Pública -->
      <router-link to="/contratacion" class="nav-item" :class="{ active: isActive('/contratacion') }">
        <span class="text-base">📄</span>
        <span>Contratación Pública</span>
        <span class="badge-gray ml-auto text-xs">S15</span>
      </router-link>
    </nav>

    <!-- Pie -->
    <div class="p-3 border-t border-gray-700 space-y-2">
      <a
        href="/admin"
        target="_blank"
        class="nav-item text-xs text-gray-500 hover:text-gray-300"
      >
        <span>⚙️</span>
        <span>Administración</span>
        <span class="ml-auto">↗</span>
      </a>
      <div class="flex items-center justify-between px-4 text-xs text-gray-600">
        <span>API</span>
        <span
          class="inline-block h-2 w-2 rounded-full"
          :class="apiOk ? 'bg-green-500' : 'bg-red-500 animate-pulse'"
        ></span>
      </div>
      <!-- Copyright -->
      <div class="px-4 pt-1 pb-1">
        <p class="text-xs text-gray-600 leading-snug">
          © Observatorio Ciudadano Municipal de Jerez
        </p>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const apiOk = ref(false)

function isActive(prefix) {
  return route.path.startsWith(prefix)
}

let timer = null
async function checkApi() {
  try {
    const r = await fetch('/health', { signal: AbortSignal.timeout(4000) })
    apiOk.value = r.ok
  } catch {
    apiOk.value = false
  }
}

onMounted(() => {
  checkApi()
  timer = setInterval(checkApi, 20000)
})
onUnmounted(() => clearInterval(timer))
</script>
