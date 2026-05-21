# Demostración reproducible del sistema

## Objetivo

Verificar que el sistema funciona de extremo a extremo mediante un escenario controlado y reproducible:

```text
localizacion + fechas + cultivo + superficie -> recomendacion de riego
```

El escenario permite comprobar la conexión entre datos climáticos, parámetros de cultivo, cálculo agronómico, predicción ML y generación de informes.

## Requisitos previos de ejecución

Ejecutar desde la raiz del proyecto:

```powershell
python -m unittest discover -s tests -v
```

Resultado esperado:

```text
Ran 26 tests
OK
```

Arrancar la aplicacion:

```powershell
python -m streamlit run app.py
```

Si Streamlit propone un puerto distinto a `8501`, usar el enlace que muestre la consola.

## Configuración recomendada en la app

| Campo | Valor |
|---|---|
| Datos climáticos | CSV local |
| CSV climático | `data/demo/aemet_sevilla_enero_junio_2024.csv` |
| Indicativo AEMET | `5783` |
| Provincia | `SEVILLA` |
| Nombre de estación | `AEROPUERTO` |
| Fecha inicial | `2024-05-01` |
| Fecha final | `2024-05-07` |
| Cultivo inicial | `olivar` |
| Fase | `media` |
| Superficie | `3500` m2 |
| Eficiencia de riego | `0.90` |
| Lluvia efectiva | `0.80` |
| Modelo ML | activado |
| Directorio modelo ML | `models/riego_predictivo` |

Esta configuración no realiza llamadas nuevas a AEMET. Usa un CSV semestral versionado y un modelo ligero versionado para asegurar estabilidad. La app muestra el inventario nacional de estaciones AEMET, pero en modo CSV local el cálculo queda fijado a Sevilla Aeropuerto porque el dataset local solo contiene esa estación.

## Secuencia funcional

1. Seleccionar `CSV local` para trabajar con datos versionados y evitar nuevas peticiones a la API.
2. Consultar el inventario nacional AEMET y confirmar que el cálculo CSV utiliza Sevilla Aeropuerto, estación `5783`.
3. Configurar la parcela: olivar, fase media, 3.500 m2.
4. Ejecutar `Calcular recomendación`.
5. Revisar los resultados principales de riego.
6. Revisar la predicción ML asociada al mismo escenario.
7. Cambiar el cultivo a `cítricos` y después a `almendro` para comprobar la variación de demanda hídrica.
8. Generar el informe Markdown/JSON.

## Resultados esperados para olivar

| Indicador | Resultado aproximado |
|---|---:|
| Riego total del periodo | 97.156 L |
| Riego medio diario | 13.879 L/día |
| Litros por planta | 31,72 L/planta/día |
| Lámina diaria | 3,97 mm/día |
| ET0 media | 5,10 mm/día |
| Lluvia total | 0,00 mm |

Interpretación de resultados:

```text
Para una parcela de olivar de 3.500 m2 en Sevilla Aeropuerto, durante la primera semana de mayo de 2024, el sistema recomienda aplicar aproximadamente 97.156 litros en total, equivalentes a unos 13.879 litros diarios.
```

## Comparación rápida por cultivo

Con la misma localización, fechas y superficie:

| Cultivo | Lectura esperada |
|---|---|
| Olivar | Menor demanda de los tres cultivos en este escenario. |
| Cítricos | Demanda intermedia por tener un Kc superior al olivar. |
| Almendro | Mayor demanda en fase media dentro de los tres perfiles configurados. |

La diferencia se explica porque cada cultivo aplica automáticamente sus parámetros agronómicos, especialmente el `Kc` y el marco de plantación.

## Escenario para demostrar lluvia efectiva

Con el mismo CSV local puede mostrarse una semana lluviosa:

| Campo | Valor |
|---|---|
| Fecha inicial | `2024-03-27` |
| Fecha final | `2024-04-02` |
| Cultivo | `olivar` |
| Superficie | `3500` m2 |

Resultados esperados:

| Indicador | Resultado aproximado |
|---|---:|
| Lluvia total | 106,80 mm |
| ET0 media | 2,72 mm/día |
| ETc media | 1,91 mm/día |
| Riego total del periodo | 18.620 L |
| Riego medio diario | 2.660 L/día |
| Lámina diaria | 0,76 mm/día |

Este escenario permite explicar que los días con lluvia suficiente quedan con riego recomendado igual a cero. La fórmula diaria aplicada es `riego neto = max(0, ETc - lluvia efectiva)`.

## Evidencias alternativas de funcionamiento

Si Streamlit no estuviera disponible, la funcionalidad puede verificarse con evidencias locales ya documentadas:

1. Mostrar las capturas en `docs/capturas/`.
2. Abrir `docs/simulacion_parcela_demo.md`.
3. Mostrar el comando CLI y los resultados esperados.
4. Explicar que el calculo esta validado por pruebas unitarias.

Comando CLI equivalente:

```powershell
python -m irrigation_advisor.cli predict-ml `
  --model-dir models/riego_predictivo `
  --weather-file data/demo/aemet_sevilla_enero_junio_2024.csv `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --crop olivar `
  --stage media `
  --area-m2 3500 `
  --output markdown
```

## Conclusión técnica de la demostración

```text
La demostración verifica que el prototipo transforma datos climáticos y parámetros de cultivo en una recomendación concreta de agua para una parcela. No depende del número de goteros, sino de la necesidad hídrica de la plantación.
```

## Extensión prevista a siete días

La demostración estable usa históricos AEMET para garantizar reproducibilidad. La arquitectura podría ampliarse a una recomendación futura de siete días conectando una fuente de predicción meteorológica. En ese caso, la app tomaría temperatura y lluvia previstas, calcularía ET0/ETc, descontaría lluvia efectiva y generaría la recomendación anticipada.

Esta ampliación no se presenta como validación principal porque depende de la calidad de la predicción meteorológica disponible. Si la fuente solo entrega probabilidad de lluvia y no precipitación en milímetros, el sistema debe mostrar la recomendación como estimación con incertidumbre.
