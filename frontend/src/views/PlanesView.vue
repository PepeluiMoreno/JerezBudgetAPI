<template>
  <div>
    <div class="section-header">
      <div>
        <h2 class="section-title">Planes, Convenios y Proyectos</h2>
        <p class="section-subtitle">Planes vigentes, convenios firmados y proyectos activos — {{ cityName }}</p>
      </div>
    </div>
    <PlaceholderSection
      sprint="S16"
      icon="📋"
      title="Módulo de Planes y Convenios en desarrollo"
      description="Mostrará los planes municipales vigentes, convenios firmados con otras administraciones
        y proyectos activos con su estado de ejecución. Fuente de datos pendiente de confirmar."
      :pending="[
        'Confirmar fuente de datos (portal transparencia, CSV, manual)',
        'Modelo de datos: planes, convenios, proyectos',
        'ETL de carga y actualización',
        'Resolver GraphQL: planes, convenios, proyectos',
      ]"
    />
  </div>
</template>

<script setup>
import PlaceholderSection from '../components/PlaceholderSection.vue'
defineProps({ peerGroup: String })
const cityName = import.meta.env.VITE_CITY_NAME || 'Jerez de la Frontera'
</script>
