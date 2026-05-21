# Exposición técnica del proyecto

## 1. Apertura

El proyecto desarrolla un prototipo de servicio predictivo de riego para agricultura de precisión. El sistema permite seleccionar una zona, una parcela y un cultivo para obtener una recomendación clara de cuánta agua debe aplicarse.

El sistema se apoya en datos meteorológicos oficiales de AEMET, parámetros agronómicos de cultivo y una capa de Machine Learning.

## 2. Problema

El problema abordado es la gestión ineficiente del agua en cultivos agrícolas. En situaciones de escasez hídrica, regar de más supone desperdicio de agua y costes; regar de menos puede afectar al cultivo.

Por eso el proyecto no se centra en cuántos goteros tiene la instalación, sino en la necesidad hídrica de la plantación:

```text
¿Cuánta agua necesita esta parcela, con este cultivo, en este periodo climático?
```

## 3. Objetivo general

Desarrollar un sistema de análisis de datos basado en información meteorológica, parámetros agronómicos y Machine Learning para optimizar la recomendación de riego en cultivos agrícolas.

## 4. Escalera de objetivos específicos

| Escalón | Objetivo | Evidencia |
|---:|---|---|
| 1 | Definir variables climáticas, de cultivo y parcela. | Modelos de datos y tabla de variables. |
| 2 | Conectar con AEMET. | Cliente API, selector de estaciones y caché local. |
| 3 | Calcular la recomendación de riego. | Motor agronómico en Python. |
| 4 | Comparar tres cultivos. | Olivar, cítricos y almendro. |
| 5 | Integrar Machine Learning. | Modelo entrenable para `riego_bruto_mm`. |
| 6 | Crear interfaz. | App Streamlit. |
| 7 | Documentar y validar. | Memoria, capturas, pruebas y GitHub. |

## 5. Explicación técnica del cálculo

El cálculo sigue una lógica agronómica trazable:

```text
ETc = ET0 * Kc
lluvia_efectiva = lluvia * porcentaje_lluvia_efectiva
riego_neto = max(0, ETc - lluvia_efectiva)
riego_bruto = riego_neto / eficiencia_riego
litros_totales = riego_bruto * superficie_m2
litros_por_planta = riego_bruto * marco_m2_por_planta
```

La ET0 procede de AEMET o se estima con Hargreaves-Samani cuando es necesario. El Kc depende del cultivo y de la fase fenológica.

## 6. Interfaz de la aplicación

La app permite:

- Elegir fuente de datos: caché local, CSV local o AEMET API.
- Ver el inventario nacional AEMET y filtrar estaciones por provincia o nombre.
- Elegir estación AEMET; en el modo CSV local reproducible se usa Sevilla Aeropuerto porque el dataset versionado contiene esa estación.
- Elegir fechas.
- Elegir cultivo y fase.
- Introducir superficie de la parcela.
- Ajustar eficiencia de riego y lluvia efectiva.
- Activar predicción ML.
- Descargar informe Markdown o JSON.

Los resultados principales son:

| Resultado | Significado |
|---|---|
| Riego total | Agua total para toda la parcela durante el periodo. |
| Riego medio diario | Media diaria para toda la parcela. |
| Litros por planta | Media diaria por planta según el marco del cultivo. |
| Lámina diaria | Profundidad media diaria de riego en mm. |

## 7. Papel del Machine Learning

El Machine Learning entra como una capa predictiva. El modelo aprende a predecir:

```text
riego_bruto_mm
```

Las entradas son variables climáticas y agronómicas aplicadas realmente en el sistema:

- estación,
- provincia,
- fecha,
- ET0,
- lluvia,
- temperaturas,
- cultivo,
- fase,
- Kc,
- marco de plantación,
- eficiencia de riego,
- lluvia efectiva.

La salida del modelo es una lámina de riego en milímetros. Después se convierte a litros según la superficie del cliente.

El entrenamiento actual usa históricos AEMET y una etiqueta agronómica calculada por el propio motor del proyecto. Por tanto, el modelo aprende la demanda esperada según la referencia técnica, no el comportamiento real de un agricultor concreto.

Delimitación técnica:

```text
El modelo predice la demanda hídrica esperada; para saber si un agricultor riega bien o mal habría que calibrarlo con riegos reales aplicados, estado del cultivo y producción.
```

## 8. Alcance no implementado

El prototipo delimita de forma expresa los siguientes elementos:

- IoT no está implementado; queda como mejora futura.
- BigQuery no está desplegado; queda como referencia teórica/futura.
- El suelo y la humedad inicial no forman parte del flujo principal de cálculo.
- El sistema no calcula diseño hidráulico de goteros.
- El modelo todavía no ha sido validado con datos reales de riego aplicado en campo.

Esta delimitación evita atribuir al sistema funcionalidades no desarrolladas y facilita una valoración técnica rigurosa.

## 9. Procedimiento de demostración funcional

1. Abrir Streamlit.
2. Usar `CSV local`.
3. Usar `data/demo/aemet_sevilla_enero_junio_2024.csv`.
4. Mostrar el inventario nacional AEMET y seleccionar estación `5783`, Sevilla Aeropuerto.
5. Elegir `olivar`, fase `media`, superficie `3500 m2`.
6. Activar ML con `models/riego_predictivo`.
7. Calcular recomendación.
8. Revisar cada métrica.
9. Cambiar cultivo a `cítricos` o `almendro` y comprobar que la demanda cambia.
10. Descargar informe Markdown o JSON.
11. Revisar las pruebas unitarias superadas.

## 10. Cuestiones técnicas frecuentes

| Cuestión | Respuesta técnica |
|---|---|
| ¿Por qué AEMET? | Porque es una fuente oficial, pública y trazable de datos meteorológicos. |
| ¿Por qué caché local? | Para no saturar la API y poder repetir cálculos sin depender de peticiones constantes. |
| ¿Qué aporta ML si ya hay fórmula? | Permite convertir el cálculo trazable en una capa predictiva entrenable y ampliable con datos reales futuros. |
| ¿El modelo ya es comercial? | Es un prototipo. Para uso comercial necesita validación con datos reales de campo. |
| ¿Por qué quitar sensores IoT? | Porque no están implementados. Se mantienen como mejora futura para evitar declarar funcionalidades inexistentes. |
| ¿Por qué no BigQuery? | Porque el volumen actual no lo exige y no se ha desplegado. El proyecto funciona con CSV/JSON y caché local. |
| ¿Cómo se mide el agua? | En mm de lámina de riego y en litros convertidos por superficie. |
| ¿Qué significa 1 mm de riego? | Equivale a 1 litro por metro cuadrado. |

## 11. Cierre

La conclusión principal es que el proyecto consigue un prototipo funcional, reproducible y técnicamente justificable. Permite pasar de datos meteorológicos oficiales a una recomendación de riego comprensible para un cliente, con una capa ML preparada para evolucionar cuando existan datos reales de campo.
