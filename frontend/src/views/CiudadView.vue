<template>
  <div>
    <div class="section-header">
      <div>
        <h2 class="section-title">Ciudad</h2>
        <p class="section-subtitle">Indicadores físicos y socioeconómicos — {{ cityName }}</p>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      <!-- Tarjeta: Población -->
      <div class="kpi-card">
        <div class="text-2xl mb-2">👥</div>
        <div class="kpi-label">Población (Padrón INE)</div>
        <div class="kpi-value mt-1">213.730</div>
        <div class="text-xs text-gray-500 mt-1">Padrón 2023 · Fuente: INE</div>
      </div>

      <!-- Tarjeta: Superficie -->
      <div class="kpi-card">
        <div class="text-2xl mb-2">📐</div>
        <div class="kpi-label">Superficie del término municipal</div>
        <div class="kpi-value mt-1">1.188 km²</div>
        <div class="text-xs text-gray-500 mt-1">Uno de los municipios más extensos de España</div>
      </div>

      <!-- Tarjeta: Paro registrado -->
      <div class="kpi-card">
        <div class="text-2xl mb-2">📉</div>
        <div class="kpi-label">Paro registrado (SEPE)</div>
        <div class="kpi-value mt-1">–</div>
        <div class="text-xs text-gray-500 mt-1">Pendiente sincronización ODM</div>
      </div>

      <!-- Tarjeta: Renta media -->
      <div class="kpi-card">
        <div class="text-2xl mb-2">💳</div>
        <div class="kpi-label">Renta media por hogar (INE Atlas)</div>
        <div class="kpi-value mt-1">–</div>
        <div class="text-xs text-gray-500 mt-1">Pendiente sincronización ODM</div>
      </div>
    </div>

    <div class="bg-gray-800 border border-gray-700 rounded-xl p-8 text-center">
      <div class="text-4xl mb-4">🗺️</div>
      <h3 class="text-lg font-medium text-gray-300 mb-2">Datos socioeconómicos en desarrollo — Sprint S13</h3>
      <p class="text-sm text-gray-500 max-w-md mx-auto">
        Esta sección mostrará series históricas de población (INE Padrón),
        paro registrado (SEPE), renta media por distrito (INE Atlas)
        y pernoctaciones turísticas (EOH), comparadas con el grupo de municipios seleccionado.
      </p>
      <div class="mt-6 text-left inline-block">
        <ul class="text-xs text-gray-600 space-y-1 font-mono">
          <li>• Datos: webhook ODM → tablas <code>ine_padron_municipal</code>, <code>sepe_paro_municipal</code></li>
          <li>• Resolver GraphQL: <code>socioeconomico.py</code> (S15)</li>
          <li>• Mapa de distritos: OSM relation {{ osmRelation }}</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({ peerGroup: String })
const cityName = import.meta.env.VITE_CITY_NAME || 'Jerez de la Frontera'
const osmRelation = import.meta.env.VITE_CITY_OSM_RELATION_ID || '340744'
</script>
