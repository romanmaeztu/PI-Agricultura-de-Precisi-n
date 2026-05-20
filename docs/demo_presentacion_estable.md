# Demo estable para la defensa

## Objetivo

Mostrar dentro de la presentacion que el sistema funciona de extremo a extremo:

```text
localizacion + fechas + cultivo + superficie -> recomendacion de riego
```

La demo esta pensada para ocupar entre 6 y 8 minutos dentro de una defensa total de 30 minutos.

## Preparacion antes de exponer

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
| CSV climático | `data/demo/aemet_sevilla_mayo_2024.csv` |
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

Esta configuración no realiza llamadas nuevas a AEMET. Usa un CSV versionado y un modelo ligero versionado para asegurar estabilidad. La app muestra el inventario nacional de estaciones AEMET, pero en modo CSV local el cálculo queda fijado a Sevilla Aeropuerto porque el dataset de demo solo contiene esa estación.

## Guion de demo

1. Explicar que se usa `CSV local` para evitar depender de la API durante la exposición.
2. Mostrar el inventario nacional AEMET y aclarar que el CSV local calcula con Sevilla Aeropuerto, estación `5783`.
3. Mostrar la parcela: olivar, fase media, 3.500 m2.
4. Pulsar `Calcular recomendación`.
5. Explicar los cuatro resultados principales.
6. Activar o mostrar la predicción ML.
7. Cambiar el cultivo a `cítricos` y después a `almendro` para demostrar que cambian las variables del cultivo.
8. Mostrar la descarga del informe Markdown/JSON.

## Resultados esperados para olivar

| Indicador | Resultado aproximado |
|---|---:|
| Riego total del periodo | 97.156 L |
| Riego medio diario | 13.879 L/día |
| Litros por planta | 31,72 L/planta/día |
| Lámina diaria | 3,97 mm/día |
| ET0 media | 5,10 mm/día |
| Lluvia total | 0,00 mm |

Frase para defender:

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

## Plan B si la app falla

Si Streamlit no abre durante la presentación:

1. Mostrar las capturas en `docs/capturas/`.
2. Abrir `docs/simulacion_parcela_demo.md`.
3. Mostrar el comando CLI y los resultados esperados.
4. Explicar que el calculo esta validado por pruebas unitarias.

Comando CLI equivalente:

```powershell
python -m irrigation_advisor.cli predict-ml `
  --model-dir models/riego_predictivo `
  --weather-file data/demo/aemet_sevilla_mayo_2024.csv `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --crop olivar `
  --stage media `
  --area-m2 3500 `
  --output markdown
```

## Frase de cierre de la demo

```text
La demo demuestra que el prototipo transforma datos climáticos y parámetros de cultivo en una recomendación concreta de agua para una parcela. No depende del número de goteros, sino de la necesidad hídrica de la plantación.
```
