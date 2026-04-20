<template>
  <div>
    <div class="section-header">
      <div>
        <h2 class="section-title">Recursos Humanos</h2>
        <p class="section-subtitle">Plantilla, RPT, organigrama y KPIs de personal — {{ cityName }}</p>
      </div>
    </div>
    <PlaceholderSection
      sprint="S13"
      icon="👥"
      title="Módulo de Recursos Humanos en desarrollo"
      description="Mostrará la Relación de Puestos de Trabajo (RPT) con filtros por grupo, área funcional y vinculación.
        KPIs clave: coste de personal / habitante, puestos / 1.000 hab., ratio de vacantes, estructura de plantilla."
      :pending="[
        'Modelo RPT (models/rpt.py) + migración 0006',
        'ETL PDFs transparencia.jerez.es con pdfplumber',
        'Resolver GraphQL: rptPuestos, rptResumen',
        'Gráfico de estructura (treemap por área y grupo)',
        'Comparativa coste personal €/hab vs peer group',
      ]"
    />
  </div>
</template>

<script setup>
import PlaceholderSection from '../components/PlaceholderSection.vue'
defineProps({ peerGroup: String })
const cityName = import.meta.env.VITE_CITY_NAME || 'Jerez de la Frontera'
</script>
