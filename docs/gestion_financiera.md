# Módulo: Gestión Financiera

Panel de sostenibilidad y transparencia financiera del grupo municipal de Jerez.
Datos procedentes de `transparencia.jerez.es` (portal A7), Ministerio de Hacienda (CONPREL) y `rendiciondecuentas.es`.

---

## Secciones del dashboard

### S1 — Ejecución Presupuestaria

Evolución mensual de la ejecución del presupuesto de gastos e ingresos. Permite detectar desviaciones entre crédito inicial, crédito definitivo y obligaciones reconocidas.

| KPI | Descripción | Umbral orientativo |
|---|---|---|
| % Ejecución Gastos | `obligaciones_reconocidas / credito_definitivo` | ≥ 85 % al cierre |
| % Ejecución Ingresos | `derechos_reconocidos / previsiones_definitivas` | ≥ 90 % al cierre |
| Desviación Capítulo I (Personal) | `oblig_reconocidas_cap1 / credito_definitivo_cap1 - 1` | ≤ ±5 % |
| Créditos suplementados | Importe total de modificaciones presupuestarias | Referencia interna |

**Recursos ODM:**
- `jerez_ejecucion_gastos` (FILE_SERIES, append)
- `jerez_ejecucion_ingresos` (FILE_SERIES, append)

---

### S2 — Periodo Medio de Pago (PMP)

Obligación legal Ley 3/2004 (modificada por Ley 15/2010): el PMP no debe superar 30 días.
Se publica mensualmente para el Ayuntamiento y cada empresa municipal por separado.

| KPI | Descripción | Umbral legal |
|---|---|---|
| PMP Ayuntamiento | Días promedio ponderado de pago (entidad principal) | ≤ 30 días |
| PMP Grupo Municipal | PMP agregado de todas las entidades | ≤ 30 días |
| Entidades en mora | Nº de entidades con PMP > 30 días en el mes | 0 objetivo |

**Recursos ODM:**
- `jerez_pmp_mensual` (FILE_SERIES, replace)

---

### S3 — Deuda Financiera

Estructura de la deuda financiera a 31/12. Permite analizar el perfil temporal y la concentración de acreedores.

| KPI | Descripción | Umbral orientativo |
|---|---|---|
| Deuda viva total | Importe total de préstamos y créditos pendientes | Referencia art. 53 TRLRHL |
| Deuda per cápita | `deuda_total / población` | Comparativa CONPREL |
| % Deuda largo plazo | `deuda_lp / deuda_total` | > 80 % (sostenible) |
| Carga financiera / ingresos | `amortizacion_anual + intereses / ingresos_corrientes` | ≤ 25 % |

**Recursos ODM:**
- `jerez_deuda_financiera` (FILE_SERIES, replace)

---

### S4 — Morosidad Trimestral (Ley 15/2010)

Informe trimestral obligatorio: pagos dentro/fuera de plazo, facturas pendientes y PMP acumulado.

| KPI | Descripción | Umbral legal |
|---|---|---|
| Facturas dentro de plazo (%) | % operaciones pagadas en ≤ 30 días | ≥ 100 % objetivo |
| Facturas fuera de plazo (importe) | Importe acumulado pagado tarde | 0 objetivo |
| Facturas pendientes de pago | Nº y € de facturas no pagadas al cierre del trimestre | Mínimo |
| PMP trimestral acumulado | Días desde recepción factura hasta pago | ≤ 30 días |

**Recursos ODM:**
- `jerez_morosidad_trimestral` (FILE_SERIES, replace)

---

### S5 — Coste Efectivo de Servicios (CESEL)

Informe anual de coste efectivo por servicio obligatorio (art. 116 ter LBRL). Permite comparar coste propio vs. externalizado y evaluar la eficiencia relativa entre municipios.

| KPI | Descripción | Umbral orientativo |
|---|---|---|
| Coste efectivo total | Suma de todos los servicios declarados | Referencia ejercicio anterior |
| Coste / habitante | `coste_total / población` | Comparativa CONPREL |
| Variación interanual | `(coste_n - coste_n1) / coste_n1` | ≤ IPC |
| Coste por servicio | Desglose por servicio mínimo obligatorio | Comparativa grupo pares |

**Recursos ODM:**
- `jerez_cesel` (FILE_SERIES, replace)

---

### S6 — Cuenta General / Indicadores de Sostenibilidad

44 KPIs de sostenibilidad calculados por el ICAC/MHAP a partir de la Cuenta General rendida al Tribunal de Cuentas. Fuente: `rendiciondecuentas.es`.

Tres bloques de ratios:

#### Equilibrio financiero (CREPA)
| KPI | Descripción | Umbral orientativo |
|---|---|---|
| Ahorro Bruto | `ingresos_corrientes - gastos_corrientes` | > 0 |
| Ahorro Neto | `ahorro_bruto - amortizacion_deuda` | > 0 |
| Resultado Presupuestario Ajustado | Superávit/déficit ajustado | ≥ 0 |
| Remanente de Tesorería para Gastos Generales (RTGG) | Liquidez acumulada | > 0 |
| Ratio de Deuda Viva / Ingresos Corrientes | Sostenibilidad de deuda | ≤ 75 % (art. 53) |

#### Sostenibilidad financiera
| KPI | Descripción | Umbral orientativo |
|---|---|---|
| Periodo Medio de Pago (anual) | PMP al cierre del ejercicio | ≤ 30 días |
| Indice de Endeudamiento | Deuda / activo total | < 60 % |
| Capacidad / Necesidad de Financiación | Superávit/déficit SEC | ≥ 0 (regla de gasto) |

#### Patrimonio neto e inversión
| KPI | Descripción |
|---|---|
| Grado de Inversión | `inversión_real / presupuesto_gastos` |
| Amortización del inmovilizado | % inmovilizado amortizado |
| Índice Financiero-Patrimonial | Fondos propios / activo |

**Recursos ODM:**
- `jerez_cuenta_general` (HTML_TABLE, replace) — **pendiente fetcher HTML_TABLE**

---

### S7 — Comparativa Municipal (CONPREL)

Liquidaciones presupuestarias de todos los municipios españoles. Permite posicionar a Jerez en su grupo de pares y comparar ratios clave.

| KPI | Descripción |
|---|---|
| Ingresos corrientes per cápita | Comparativa con mediana del grupo |
| Gastos corrientes per cápita | Comparativa con mediana del grupo |
| Ahorro bruto per cápita | Posición relativa en el grupo |
| Deuda per cápita | Posición relativa en el grupo |
| Ratio ejecución gastos | Jerez vs. mediana grupo |

**Recursos ODM:**
- `nacional_conprel` (FILE_SERIES, replace) — **pendiente URL de descarga verificada**

---

## Recursos ODM — resumen

| Recurso | Fetcher | Tabla | Estado |
|---|---|---|---|
| Jerez - Periodo Medio de Pago | FILE_SERIES | `jerez_pmp_mensual` | ✅ activo |
| Jerez - Ejecución Presupuestaria Gastos | FILE_SERIES | `jerez_ejecucion_gastos` | ✅ activo |
| Jerez - Ejecución Presupuestaria Ingresos | FILE_SERIES | `jerez_ejecucion_ingresos` | ✅ activo |
| Jerez - Coste Efectivo de Servicios (CESEL) | FILE_SERIES | `jerez_cesel` | ✅ activo |
| Jerez - Deuda Financiera | FILE_SERIES | `jerez_deuda_financiera` | ✅ activo |
| Jerez - Morosidad Trimestral (Ley 15/2010) | FILE_SERIES | `jerez_morosidad_trimestral` | ✅ activo |
| Jerez - Cuenta General (rendiciondecuentas.es) | HTML_TABLE | `jerez_cuenta_general` | ⏳ pending_fetcher |
| Hacienda - CONPREL Liquidaciones | FILE_SERIES | `nacional_conprel` | ⏳ pending_fetcher |

Definiciones completas en [data/odm_resources/gestion_financiera.json](../data/odm_resources/gestion_financiera.json).
Script de aprovisionamiento: [data/odm_resources/seed_resources.py](../data/odm_resources/seed_resources.py).
