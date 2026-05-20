# Simulación de parcela: validación funcional de cálculo y predicción

## 1. Objetivo

Esta simulación verifica que el sistema puede recibir una localización, una superficie y un cultivo, y devolver una recomendación de riego técnicamente justificable.

El caso se plantea como una parcela de ejemplo. No representa una finca real validada en campo, sino una validación funcional del servicio.

## 2. Escenario simulado

| Parámetro | Valor aplicado |
|---|---|
| Nombre del caso | Parcela X |
| Localización climática | Sevilla Aeropuerto |
| Estación AEMET | `5783` |
| Provincia | Sevilla |
| Fuente de datos | CSV local de validación generado desde AEMET |
| Periodo climático | 2024-05-01 a 2024-05-07 |
| Cultivo | Olivar |
| Fase fenológica | Media |
| Superficie | 3.500 m2 |
| Marco del cultivo | 8 m2/planta |
| Plantas estimadas | 437,50 plantas |
| Kc aplicado | 0,70 |
| Eficiencia de riego | 0,90 |
| Lluvia efectiva | 80% de la lluvia registrada |
| Modelo ML | `models/riego_predictivo_keras` |

La simulación usa `CSV local` para evitar nuevas peticiones a AEMET durante la validación.

## 3. Comando ejecutado

```powershell
python -m irrigation_advisor.cli predict-ml `
  --model-dir models/riego_predictivo_keras `
  --weather-file data/demo/aemet_sevilla_mayo_2024.csv `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --crop olivar `
  --stage media `
  --area-m2 3500 `
  --output markdown `
  --output-file data/resultados/prediccion_ml_olivar.md
```

## 4. Fórmula aplicada

El cálculo agronómico sigue esta secuencia:

```text
ETc = ET0 * Kc
lluvia_efectiva = lluvia * 0,80
riego_neto = max(0, ETc - lluvia_efectiva)
riego_bruto = riego_neto / eficiencia_riego
litros_totales = riego_bruto * superficie_m2
litros_por_planta = riego_bruto * marco_m2_por_planta
```

En esta simulación:

```text
Kc = 0,70
eficiencia_riego = 0,90
superficie_m2 = 3500
marco_m2_por_planta = 8
```

## 5. Ejemplo de cálculo de un día

Día 2024-05-01:

| Variable | Valor |
|---|---:|
| ET0 | 4,02 mm |
| Lluvia | 0,00 mm |
| Kc | 0,70 |
| Eficiencia | 0,90 |

Cálculo:

```text
ETc = 4,02 * 0,70 = 2,81 mm
lluvia_efectiva = 0,00 * 0,80 = 0,00 mm
riego_neto = max(0, 2,81 - 0,00) = 2,81 mm
riego_bruto = 2,81 / 0,90 = 3,13 mm
litros_totales = 3,13 * 3500 = 10.943,33 L
litros_por_planta = 3,13 * 8 = 25,01 L/planta
```

Este resultado coincide con el detalle diario calculado por el motor agronómico.

## 6. Resultados del periodo

| Indicador | Resultado |
|---|---:|
| ET0 media | 5,10 mm/día |
| Lluvia total | 0,00 mm |
| Temperatura media | 17,66 °C |
| Riego total recomendado | 97.156,11 L |
| Riego medio diario | 13.879,44 L/día |
| Lámina media diaria | 3,97 mm/día |
| Litros medios por planta | 31,72 L/planta/día |

Interpretación:

```text
Para esta parcela de olivar de 3.500 m2, en Sevilla Aeropuerto y durante el periodo 2024-05-01 a 2024-05-07, el sistema recomienda aplicar aproximadamente 97.156 L en total, equivalente a una media de 13.879 L/día.
```

## 7. Detalle diario del cálculo agronómico

| Fecha | ET0 (mm) | Lluvia (mm) | ETc (mm) | Riego bruto (mm) | Litros totales | L/planta |
|---|---:|---:|---:|---:|---:|---:|
| 2024-05-01 | 4,02 | 0,00 | 2,81 | 3,13 | 10.943,33 | 25,01 |
| 2024-05-02 | 4,39 | 0,00 | 3,07 | 3,41 | 11.950,56 | 27,32 |
| 2024-05-03 | 5,04 | 0,00 | 3,53 | 3,92 | 13.720,00 | 31,36 |
| 2024-05-04 | 5,84 | 0,00 | 4,09 | 4,54 | 15.897,78 | 36,34 |
| 2024-05-05 | 5,13 | 0,00 | 3,59 | 3,99 | 13.965,00 | 31,92 |
| 2024-05-06 | 5,24 | 0,00 | 3,67 | 4,08 | 14.264,44 | 32,60 |
| 2024-05-07 | 6,03 | 0,00 | 4,22 | 4,69 | 16.415,00 | 37,52 |

## 8. Predicción Machine Learning

El modelo Keras entrenado predice también la lámina de riego bruto:

```text
target = riego_bruto_mm
```

Resultados ML:

| Indicador ML | Resultado |
|---|---:|
| Riego total ML | 97.160,14 L |
| Riego medio diario ML | 13.880,02 L/día |
| Lámina media diaria ML | 3,97 mm/día |
| Litros medios por planta ML | 31,73 L/planta/día |
| MAE del modelo | 0,09 mm |
| RMSE del modelo | 0,12 mm |
| R2 del modelo | 0,96 |

Comparación:

| Método | Riego total | Diferencia |
|---|---:|---:|
| Cálculo agronómico | 97.156,11 L | - |
| Predicción ML | 97.160,14 L | +4,03 L |

La diferencia acumulada es muy baja en este ejemplo porque el modelo ha aprendido la referencia agronómica del dataset local.

## 9. Detalle diario ML

| Fecha | Riego ML (mm) | Litros ML | L/planta ML |
|---|---:|---:|---:|
| 2024-05-01 | 3,13 | 10.955,03 | 25,04 |
| 2024-05-02 | 3,41 | 11.935,02 | 27,28 |
| 2024-05-03 | 3,92 | 13.720,03 | 31,36 |
| 2024-05-04 | 4,54 | 15.890,04 | 36,32 |
| 2024-05-05 | 3,99 | 13.965,02 | 31,92 |
| 2024-05-06 | 4,08 | 14.279,99 | 32,64 |
| 2024-05-07 | 4,69 | 16.415,01 | 37,52 |

## 10. Validación funcional

La simulación valida los siguientes puntos:

| Comprobación | Evidencia |
|---|---|
| El sistema acepta una localización | Usa estación AEMET `5783`, Sevilla Aeropuerto. |
| El sistema adapta el cálculo al cultivo | Usa olivar en fase media con Kc 0,70. |
| El sistema adapta el resultado a la parcela | Convierte mm a litros usando 3.500 m2. |
| El sistema genera recomendación diaria | Produce tabla diaria del 1 al 7 de mayo. |
| El sistema genera predicción ML | Usa modelo Keras para estimar `riego_bruto_mm`. |
| El resultado es explicable | Cada valor se deriva de ET0, Kc, lluvia, eficiencia y superficie. |

## 11. Conclusión de la simulación

La parcela simulada necesitaría aproximadamente:

```text
97.156 L durante la semana
13.879 L/día de media
31,72 L/planta/día
3,97 mm/día de lámina media
```

El modelo ML ofrece un resultado prácticamente equivalente:

```text
97.160 L durante la semana
```

Por tanto, la simulación valida que el prototipo funciona como servicio de recomendación: recibe datos climáticos, cultivo y superficie; calcula la necesidad hídrica; y genera una predicción ML coherente con la referencia agronómica.

La limitación sigue siendo la misma: el modelo está calibrado con una referencia agronómica calculada, no con riegos reales aplicados en campo. Para convertirlo en servicio comercial plenamente validado habría que incorporar registros reales de riego, estado del cultivo y producción.
