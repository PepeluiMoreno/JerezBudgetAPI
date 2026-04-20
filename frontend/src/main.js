import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import ECharts from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, GaugeChart } from 'echarts/charts'
import {
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, DatasetComponent
} from 'echarts/components'

import './assets/main.css'
import App from './App.vue'
import { routes } from './router/index.js'

// ECharts: registrar solo lo que se usa (tree-shaking)
use([
  CanvasRenderer,
  LineChart, BarChart, GaugeChart,
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, DatasetComponent,
])

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const app = createApp(App)
app.component('VChart', ECharts)
app.use(router)
app.mount('#app')
