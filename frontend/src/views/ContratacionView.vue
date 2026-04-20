<template>
  <div>
    <div class="section-header">
      <div>
        <h2 class="section-title">Contratación Pública</h2>
        <p class="section-subtitle">Licitaciones activas y contratos adjudicados — {{ cityName }}</p>
      </div>
    </div>
    <PlaceholderSection
      sprint="S15"
      icon="📄"
      title="Módulo de Contratación Pública en desarrollo"
      description="Mostrará las licitaciones activas y contratos adjudicados del ayuntamiento,
        obtenidos de la Plataforma de Contratos del Sector Público (PLACE/PCSP).
        Comparativa nacional disponible al ser fuente pública."
      :pending="[
        'ETL PLACE/PCSP: API contrataciondelestado.es',
        'Modelo de datos: place_contratos',
        'Resolver GraphQL: contratos(year, tipo, estado)',
        'Tabla de licitaciones activas',
        'Análisis de adjudicatarios recurrentes',
      ]"
    />
  </div>
</template>

<script setup>
import PlaceholderSection from '../components/PlaceholderSection.vue'
defineProps({ peerGroup: String })
const cityName = import.meta.env.VITE_CITY_NAME || 'Jerez de la Frontera'
</script>
