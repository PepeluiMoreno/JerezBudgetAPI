/**
 * Router — CityDashboard
 *
 * 7 secciones del panel + rutas de admin (redirect al backend Jinja2).
 * Cada sección tiene una ruta base y, donde aplica, sub-rutas.
 */

// Sección 1 — Ciudad (indicadores socio-económicos)
import CiudadView from '../views/CiudadView.vue'

// Sección 2 — Gestión Económico-Financiera
import FinancieroView from '../views/FinancieroView.vue'
import RigorView from '../views/financiero/RigorView.vue'
import SostenibilidadView from '../views/financiero/SostenibilidadView.vue'
import ComparativaView from '../views/financiero/ComparativaView.vue'
import ExploradorView   from '../views/financiero/ExploradorView.vue'
import RecaudacionView  from '../views/financiero/RecaudacionView.vue'
import PmpView              from '../views/financiero/PmpView.vue'
import DeudaMorosidadView  from '../views/financiero/DeudaMorosidadView.vue'

// Sección 3 — Recursos Humanos
import RecursosHumanosView from '../views/RecursosHumanosView.vue'

// Sección 4 — Calidad de Servicios
import CalidadView from '../views/CalidadView.vue'

// Sección 5 — Planes, Convenios y Proyectos
import PlanesView from '../views/PlanesView.vue'

// Sección 6 — Subvenciones
import SubvencionesView from '../views/SubvencionesView.vue'

// Sección 7 — Contratación Pública
import ContratacionView from '../views/ContratacionView.vue'

export const routes = [
  {
    path: '/',
    redirect: '/ciudad',
  },

  // ── 1. Ciudad ──────────────────────────────────────────────────
  {
    path: '/ciudad',
    component: CiudadView,
    meta: { section: 'ciudad', label: 'Ciudad', icon: '🏙️' },
  },

  // ── 2. Gestión Económico-Financiera ───────────────────────────
  {
    path: '/financiero',
    component: FinancieroView,
    meta: { section: 'financiero', label: 'Gestión Financiera', icon: '💰' },
    redirect: '/financiero/rigor',
    children: [
      {
        path: 'rigor',
        component: RigorView,
        meta: { label: 'Rigor Presupuestario' },
      },
      {
        path: 'sostenibilidad',
        component: SostenibilidadView,
        meta: { label: 'Sostenibilidad Financiera' },
      },
      {
        path: 'comparativa',
        component: ComparativaView,
        meta: { label: 'Comparativa Municipal' },
      },
      {
        path: 'explorador',
        component: ExploradorView,
        meta: { label: 'Explorador de Líneas' },
      },
      {
        path: 'recaudacion',
        component: RecaudacionView,
        meta: { label: 'Eficacia en Recaudación' },
      },
      {
        path: 'pmp',
        component: PmpView,
        meta: { label: 'Período Medio de Pago' },
      },
      {
        path: 'deuda-morosidad',
        component: DeudaMorosidadView,
        meta: { label: 'Deuda y Morosidad' },
      },
    ],
  },

  // ── 3. Recursos Humanos ───────────────────────────────────────
  {
    path: '/rrhh',
    component: RecursosHumanosView,
    meta: { section: 'rrhh', label: 'Recursos Humanos', icon: '👥' },
  },

  // ── 4. Calidad de Servicios ───────────────────────────────────
  {
    path: '/calidad',
    component: CalidadView,
    meta: { section: 'calidad', label: 'Calidad de Servicios', icon: '⭐' },
  },

  // ── 5. Planes, Convenios y Proyectos ──────────────────────────
  {
    path: '/planes',
    component: PlanesView,
    meta: { section: 'planes', label: 'Planes y Convenios', icon: '📋' },
  },

  // ── 6. Subvenciones ───────────────────────────────────────────
  {
    path: '/subvenciones',
    component: SubvencionesView,
    meta: { section: 'subvenciones', label: 'Subvenciones', icon: '🏦' },
  },

  // ── 7. Contratación Pública ───────────────────────────────────
  {
    path: '/contratacion',
    component: ContratacionView,
    meta: { section: 'contratacion', label: 'Contratación Pública', icon: '📄' },
  },
]
