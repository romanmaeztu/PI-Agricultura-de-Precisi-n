# Machine Learning: calibración y entrenamiento

## 1. Qué predice el modelo actual

El modelo predictivo del proyecto estima:

```text
riego_bruto_mm
```

Es decir, la lámina de riego recomendada en milímetros. Después, el sistema convierte esa lámina a litros según la superficie de la parcela:

```text
litros_totales = riego_bruto_mm * superficie_m2
```

Por tanto, el modelo no predice directamente "número de goteros" ni diseño hidráulico. Predice la necesidad hídrica de la plantación.

## 2. Variables de entrada

Las variables usadas en el entrenamiento actual son:

| Grupo | Variables |
|---|---|
| Localización | estación AEMET, provincia |
| Tiempo | fecha transformada internamente en ciclo anual |
| Clima | ET0, lluvia, temperatura mínima, máxima y media |
| Cultivo | cultivo, fase fenológica, Kc |
| Parcela | marco m2/planta, eficiencia de riego, lluvia efectiva |

La superficie se usa después para convertir la lámina en litros del cliente.

## 3. Qué datos históricos se usan ahora

El entrenamiento actual usa datos históricos AEMET ya descargados y una etiqueta calculada por el motor agronómico:

```text
ETc = ET0 * Kc
lluvia_efectiva = lluvia * porcentaje_lluvia_efectiva
riego_neto = max(0, ETc - lluvia_efectiva)
riego_bruto = riego_neto / eficiencia_riego
```

Esto significa que el dataset es semisintético:

- Los datos climáticos son reales, proceden de AEMET.
- La etiqueta `riego_bruto_mm` procede del cálculo agronómico.

Esta aproximación es válida para un prototipo académico porque permite entrenar y validar la capa ML de forma reproducible. Sin embargo, no demuestra todavía que el agricultor riegue bien o mal en campo.

## 4. ¿Se puede saber si el agricultor riega bien o mal?

No de forma real sin datos de campo.

Para saberlo harían falta registros como:

| Dato real | Uso |
|---|---|
| Agua realmente aplicada | Comparar riego real contra recomendación |
| Estado hídrico del cultivo | Ver si hubo estrés o exceso |
| Producción obtenida | Relacionar riego con resultado agronómico |
| Incidencias | Explicar anomalías |
| Coste del agua y energía | Calcular eficiencia económica |

Sin esos datos, el sistema puede recomendar una dosis razonable, pero no puede afirmar que una práctica real concreta haya sido correcta o incorrecta.

## 5. Uso de valores predeterminados

Sí se pueden usar valores predeterminados para crear una referencia provisional. Por ejemplo:

```text
desviacion = (riego_aplicado_mm - riego_recomendado_mm) / riego_recomendado_mm
```

Un criterio inicial podría ser:

| Desviación frente a referencia | Clasificación provisional |
|---:|---|
| Menor que -15% | Déficit de riego |
| Entre -15% y +15% | Riego aceptable |
| Mayor que +15% | Exceso de riego |

Este criterio debe interpretarse como una regla de referencia provisional, no como una verdad agronómica absoluta. Para convertirlo en un servicio real, sería necesario validarlo con técnicos y datos reales de parcelas.

## 6. Entrenamiento ejecutado

El modelo Keras se ha entrenado con el dataset local:

```powershell
python -m irrigation_advisor.cli train-ml `
  --input-file data/resultados/dataset_ml_aemet.csv `
  --model-dir models/riego_predictivo_keras `
  --backend keras `
  --epochs 200
```

Resultado del entrenamiento:

| Métrica | Valor |
|---|---:|
| Filas de entrenamiento | 21 |
| Variables de entrada | 17 |
| MAE | 0,0913 mm |
| RMSE | 0,1180 mm |
| R2 | 0,9595 |

Estas métricas indican que el modelo aprende bien el patrón del dataset de ejemplo. La lectura correcta es:

```text
El modelo aproxima correctamente la referencia agronómica usada como etiqueta.
```

No debe interpretarse como:

```text
El modelo ya está validado con agricultores reales.
```

## 7. Predicción generada

Se ha generado una predicción para olivar, Sevilla Aeropuerto, del 1 al 7 de mayo de 2024:

```powershell
python -m irrigation_advisor.cli predict-ml `
  --model-dir models/riego_predictivo_keras `
  --weather-file data/resultados/comparativa_aemet_sevilla.csv `
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

Resultado resumido:

| Resultado | Valor |
|---|---:|
| Riego total agronómico | 97.156,11 L |
| Riego total ML | 94.522,69 L |
| Riego medio diario ML | 13.503,24 L/día |
| Lámina media diaria ML | 3,86 mm/día |

## 8. Cómo pasaría a modelo real

Para convertirlo en un servicio predictivo real, el dataset debería cambiar de esta forma:

| Prototipo actual | Servicio real |
|---|---|
| `riego_bruto_mm` calculado por fórmula | `riego_optimo_mm` validado en campo |
| Datos AEMET históricos | AEMET + registros reales de parcela |
| Validación interna | Validación con campañas agrícolas reales |
| Predicción del prototipo | Recomendación comercial calibrada |

La estructura del proyecto ya permite ese salto. Lo que falta no es código base, sino datos reales de operación.

## 9. Pronóstico a siete días

El modelo podría utilizarse para estimar la recomendación de riego de la semana siguiente, pero necesita una entrada meteorológica futura. El ML no predice por sí mismo la lluvia ni la temperatura; esas variables deben proceder de una fuente de predicción meteorológica.

Flujo propuesto:

```text
predicción meteorológica 7 días + cultivo + fase + superficie -> riego recomendado futuro
```

Condiciones necesarias:

- Predicción diaria de temperatura máxima y mínima.
- Predicción diaria de lluvia en milímetros o variable equivalente justificable.
- Localización asociada a la parcela.
- Aviso de incertidumbre si solo se dispone de probabilidad de precipitación.
- Calibración posterior con riegos reales aplicados y respuesta del cultivo.

Por tanto, el proyecto queda preparado para esta ampliación, pero la versión actual se defiende con datos históricos reales y resultados reproducibles.

## 10. Síntesis técnica para documentación

> El modelo ML del prototipo se entrena con históricos meteorológicos de AEMET y una etiqueta agronómica calculada, por lo que predice la demanda esperada de riego según cultivo, fase y localización. Para convertirlo en un servicio comercial plenamente validado, sería necesario calibrarlo con datos reales de riego aplicado, estado del cultivo y producción en parcelas reales. Para una recomendación futura a siete días, el modelo tendría que recibir predicción meteorológica diaria como entrada, ya que no predice el clima por sí mismo.
