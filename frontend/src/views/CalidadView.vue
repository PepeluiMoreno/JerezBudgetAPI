<template>
  <div>
    <div class="section-header">
      <div>
        <h2 class="section-title">Calidad de Servicios</h2>
        <p class="section-subtitle">Cartas de Servicio, compromisos y KPIs — {{ cityName }}</p>
      </div>
    </div>
    <PlaceholderSection
      sprint="S14"
      icon="⭐"
      title="Módulo de Calidad de Servicios en desarrollo"
      description="Mostrará el catálogo de Cartas de Servicio con estado de cumplimiento de compromisos,
        evolución temporal por área funcional y cruce RRHH × Servicios (coste + plantilla + cumplimiento)."
      :pending="[
        'Integración con el proyecto ChoS (Cartas de Servicios)',
        'Definir método de integración: API, BD compartida o webhook',
        'Resolver GraphQL: cartasServicios, cumplimientoServicios',
        'Semáforo de cumplimiento por servicio',
        'Editor de KPIs composables',
      ]"
    />
  </div>
</template>

<script setup>
import PlaceholderSection from '../components/PlaceholderSection.vue'
defineProps({ peerGroup: String })
const cityName = import.meta.env.VITE_CITY_NAME || 'Jerez de la Frontera'
</script>
