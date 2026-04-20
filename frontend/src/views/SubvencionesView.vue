<template>
  <div>
    <div class="section-header">
      <div>
        <h2 class="section-title">Subvenciones</h2>
        <p class="section-subtitle">Subvenciones recibidas y concedidas — {{ cityName }}</p>
      </div>
    </div>
    <PlaceholderSection
      sprint="S15"
      icon="🏦"
      title="Módulo de Subvenciones en desarrollo"
      description="Mostrará las subvenciones recibidas por el ayuntamiento y las concedidas a terceros,
        obtenidas de la Base de Datos Nacional de Subvenciones (BDNS) de infosubvenciones.es.
        Comparativa nacional disponible al ser fuente pública."
      :pending="[
        'ETL BDNS: API infosubvenciones.es',
        'Modelo de datos: bdns_subvenciones',
        'Resolver GraphQL: subvenciones(year, tipo)',
        'Gráfico de evolución temporal',
        'Comparativa nacional con peer groups',
      ]"
    />
  </div>
</template>

<script setup>
import PlaceholderSection from '../components/PlaceholderSection.vue'
defineProps({ peerGroup: String })
const cityName = import.meta.env.VITE_CITY_NAME || 'Jerez de la Frontera'
</script>
