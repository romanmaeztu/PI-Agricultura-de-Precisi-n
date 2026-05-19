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

## Configuracion recomendada en la app

| Campo | Valor |
|---|---|
| Datos climaticos | CSV local |
| CSV climatico | `data/demo/aemet_sevilla_mayo_2024.csv` |
| Indicativo AEMET | `5783` |
| Provincia | `SEVILLA` |
| Nombre de estacion | `AEROPUERTO` |
| Fecha inicial | `2024-05-01` |
| Fecha final | `2024-05-07` |
| Cultivo inicial | `olivar` |
| Fase | `media` |
| Superficie | `3500` m2 |
| Eficiencia de riego | `0.90` |
| Lluvia efectiva | `0.80` |
| Modelo ML | activado |
| Directorio modelo ML | `models/riego_predictivo` |

Esta configuracion no realiza llamadas nuevas a AEMET. Usa un CSV versionado y un modelo ligero versionado para asegurar estabilidad.

## Guion de demo

1. Explicar que se usa `CSV local` para evitar depender de la API durante la exposicion.
2. Mostrar la localizacion: Sevilla Aeropuerto, estacion `5783`.
3. Mostrar la parcela: olivar, fase media, 3.500 m2.
4. Pulsar `Calcular recomendacion`.
5. Explicar los cuatro resultados principales.
6. Activar o mostrar la prediccion ML.
7. Cambiar el cultivo a `citricos` y despues a `almendro` para demostrar que cambian las variables del cultivo.
8. Mostrar el detalle diario y la descarga del informe.

## Resultados esperados para olivar

| Indicador | Resultado aproximado |
|---|---:|
| Riego total del periodo | 97.156 L |
| Riego medio diario | 13.879 L/dia |
| Litros por planta | 31,72 L/planta/dia |
| Lamina diaria | 3,97 mm/dia |
| ET0 media | 5,10 mm/dia |
| Lluvia total | 0,00 mm |

Frase para defender:

```text
Para una parcela de olivar de 3.500 m2 en Sevilla Aeropuerto, durante la primera semana de mayo de 2024, el sistema recomienda aplicar aproximadamente 97.156 litros en total, equivalentes a unos 13.879 litros diarios.
```

## Comparacion rapida por cultivo

Con la misma localizacion, fechas y superficie:

| Cultivo | Lectura esperada |
|---|---|
| Olivar | Menor demanda de los tres cultivos en este escenario. |
| Citricos | Demanda intermedia por tener un Kc superior al olivar. |
| Almendro | Mayor demanda en fase media dentro de los tres perfiles configurados. |

La diferencia se explica porque cada cultivo aplica automaticamente sus parametros agronomicos, especialmente el `Kc` y el marco de plantacion.

## Plan B si la app falla

Si Streamlit no abre durante la presentacion:

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
La demo demuestra que el prototipo transforma datos climaticos y parametros de cultivo en una recomendacion concreta de agua para una parcela. No depende del numero de goteros, sino de la necesidad hidrica de la plantacion.
```
