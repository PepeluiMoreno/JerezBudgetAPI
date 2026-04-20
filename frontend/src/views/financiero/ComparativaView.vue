<template>
  <div>
    <PageHeader
      title="Comparativa Municipal"
      subtitle="Liquidaciones CONPREL frente al grupo de pares"
    />

    <div class="bg-gray-800 border border-gray-700 rounded-xl p-8 text-center">
      <div class="text-4xl mb-4">📊</div>
      <h3 class="text-lg font-medium text-gray-300 mb-2">En desarrollo — Sprint S12</h3>
      <p class="text-sm text-gray-500 max-w-md mx-auto">
        Mostrará liquidaciones CONPREL de los municipios del grupo de pares seleccionado.
        Requiere el resolver GraphQL <code class="text-blue-400">conprelComparativa</code>.
      </p>
      <div class="mt-6 text-left inline-block">
        <p class="text-xs text-gray-600 font-mono">Pendiente:</p>
        <ul class="text-xs text-gray-600 mt-1 space-y-1 font-mono">
          <li>• resolver <code>conprelComparativa(year, peerGroupId)</code></li>
          <li>• resolver <code>peerGroups</code></li>
          <li>• seed peer groups en BD</li>
          <li>• gráfico de barras comparativo por capítulo</li>
          <li>• ranking de municipios por gasto €/hab</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
import PageHeader from '../../components/PageHeader.vue'
</script>
