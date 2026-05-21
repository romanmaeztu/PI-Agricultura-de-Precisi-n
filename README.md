# Sistema de recomendación de riego con AEMET

Este prototipo calcula cuánta agua debe aplicarse en una parcela a partir de datos climáticos de AEMET, el cultivo seleccionado y la superficie indicada. La solución prioriza un cálculo trazable, reproducible y comprensible antes de incorporar una explotación comercial del servicio predictivo.

## Documentación técnica

- Memoria técnica en Word: `docs/memoria_proyecto_intermodular.docx`.
- Memoria base en Markdown: `docs/memoria_proyecto_intermodular.md`.
- Estado de preparación del proyecto: `docs/checklist_entrega_final.md`.
- Documento de exposición técnica: `docs/guion_defensa.md`.
- Explicación de ML, calibración y entrenamiento: `docs/ml_calibracion_y_entrenamiento.md`.
- Evidencias completas del proceso ML: `docs/ml_proceso/README.md`.
- Simulación funcional de una parcela: `docs/simulacion_parcela_demo.md`.
- Demostración reproducible del sistema: `docs/demo_presentacion_estable.md`.
- Presentación académica del proyecto: `docs/presentacion_defensa_tfg_riego_jurado.pptx`.
- Capturas de la interfaz: `docs/capturas/`.

## Logica de calculo

1. Se obtiene ET0 diaria.
   - Si AEMET aporta temperatura maxima y minima, el sistema estima ET0 con Hargreaves-Samani.
   - Si ya se conoce ET0, puede introducirse manualmente en modo `manual`.
2. Se calcula la evapotranspiracion del cultivo:

```text
ETc = ET0 * Kc
```

3. Se resta la lluvia efectiva:

```text
necesidad_neta_mm = max(0, ETc - lluvia_efectiva)
```

4. Se corrige por eficiencia del sistema de riego:

```text
dosis_bruta_mm = necesidad_neta_mm / eficiencia_riego
```

5. Se convierte a litros:

```text
1 mm = 1 L/m2
litros_totales = dosis_bruta_mm * superficie_m2
```

## Uso

Copiar `.env.example` como `.env` o definir la variable de entorno:

```powershell
$env:AEMET_API_KEY = "tu_api_key"
```

Ejemplo con datos historicos de AEMET:

```powershell
python -m irrigation_advisor.cli stations --province SEVILLA
```

El comando anterior sirve para localizar el `station` que corresponde a la zona de estudio. En el modo `aemet`, la latitud de la estacion se intenta recuperar automaticamente para estimar ET0 cuando AEMET no la entregue de forma directa.

Para ver los tres cultivos configurados:

```powershell
python -m irrigation_advisor.cli crops
```

Cada cultivo aplica automaticamente sus variables por defecto:

| Cultivo | Marco por planta | Kc fase media | Fases disponibles |
|---|---:|---:|---|
| `olivar` | 8 m2 | 0.70 | inicio, desarrollo, media, madurez |
| `citricos` | 20 m2 | 0.75 | inicio, desarrollo, media, madurez |
| `almendro` | 30 m2 | 0.90 | inicio, desarrollo, media, madurez |

```powershell
python -m irrigation_advisor.cli aemet `
  --station 5783 `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --crop olivar `
  --stage desarrollo `
  --area-m2 10000 `
  --irrigation-efficiency 0.90
```

Ejemplo sin API, util para validar el algoritmo:

```powershell
python -m irrigation_advisor.cli manual `
  --et0 5.6 `
  --rain-mm 0 `
  --crop olivar `
  --stage desarrollo `
  --area-m2 10000
```

## Servicio de recomendacion para cliente

El flujo orientado a cliente parte de una estacion AEMET, periodo, cultivo y superficie. Devuelve un informe con litros totales, litros diarios, lamina de riego y litros por planta.

```powershell
python -m irrigation_advisor.cli recommend `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --crop olivar `
  --stage media `
  --area-m2 3500 `
  --output markdown `
  --output-file data/resultados/recomendacion_cliente_olivar.md
```

Si ya existe un CSV descargado desde AEMET, puede reutilizarse como cache para evitar nuevas peticiones a la API:

```powershell
python -m irrigation_advisor.cli recommend `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --weather-file data/demo/aemet_sevilla_enero_junio_2024.csv `
  --crop olivar `
  --stage media `
  --area-m2 3500 `
  --output-file data/resultados/recomendacion_cliente_olivar.md
```

La salida responde a la pregunta comercial:

```text
Para esta parcela, cultivo y periodo climatico, cuanta agua debe distribuir el cliente.
```

Tambien puede usarse el indicativo AEMET directamente con `--station 5783`. Si no se indica `--station`, el sistema busca en el inventario de AEMET por provincia y nombre de estacion.

## Interfaz web

Instalar dependencias:

```powershell
python -m pip install -r requirements.txt
```

Ejecutar la app:

```powershell
python -m streamlit run app.py
```

La interfaz permite consultar 920 estaciones del inventario AEMET de España mediante filtro por provincia y nombre, además de cultivo y superficie. Puede trabajar con AEMET API, caché local o con un CSV climático ya exportado. Para una ejecución reproducible se utiliza `CSV local` con `data/demo/aemet_sevilla_enero_junio_2024.csv`; en ese modo el cálculo queda fijado a Sevilla Aeropuerto porque el CSV contiene esa estación.

El CSV local cubre Sevilla Aeropuerto desde `2024-01-01` hasta `2024-06-30`. Para demostrar la reducción por lluvia efectiva en la defensa, puede usarse el periodo `2024-03-27` a `2024-04-02`, con 106,80 mm de lluvia acumulada.

## Capa predictiva ML/Keras

El proyecto ya incluye una capa predictiva entrenable. El objetivo del modelo es predecir `riego_bruto_mm` a partir de historicos AEMET exportados y variables de cultivo/parcela: estacion, provincia, fecha, ET0, lluvia, temperaturas, cultivo, fase, Kc, marco de plantacion y eficiencia. La superficie se aplica despues para convertir la lamina predicha a litros del cliente.

Las variables hidraulicas del reparto no forman parte del objetivo del servicio. La recomendacion se centra en la necesidad hidrica: milimetros de riego, litros totales y litros por planta.

La capa agronomica sigue siendo la referencia trazable. La capa ML aprende sobre el historico generado/validado y permite ofrecer una prediccion como servicio. Cuando existan datos reales de riego aplicado en campo, la misma estructura puede sustituir la variable objetivo por una variable medida.

Instalar dependencias ML:

```powershell
python -m pip install -r requirements-ml.txt
```

Entrenar modelo:

```powershell
python -m irrigation_advisor.cli train-ml `
  --input-file data/resultados/comparativa_aemet_sevilla.csv `
  --model-dir models/riego_predictivo `
  --backend auto
```

Para construir un dataset historico mayor desde AEMET:

```powershell
python -m irrigation_advisor.cli build-ml-dataset `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-03-01 `
  --end 2024-09-30 `
  --crop olivar `
  --crop citricos `
  --crop almendro `
  --stage inicio `
  --stage desarrollo `
  --stage media `
  --stage madurez `
  --area-m2 10000 `
  --output-file data/resultados/dataset_ml_aemet.csv
```

Si AEMET limita temporalmente las peticiones o ya existe un CSV descargado, puede construirse el dataset ML desde cache:

```powershell
python -m irrigation_advisor.cli build-ml-dataset `
  --weather-file data/resultados/comparativa_aemet_sevilla.csv `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --output-file data/resultados/dataset_ml_aemet.csv
```

Tambien puede generar el dataset y entrenar el modelo en el mismo paso:

```powershell
python -m irrigation_advisor.cli build-ml-dataset `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-03-01 `
  --end 2024-09-30 `
  --output-file data/resultados/dataset_ml_aemet.csv `
  --train-model-dir models/riego_predictivo `
  --backend auto
```

`--backend auto` intenta entrenar con Keras si TensorFlow esta disponible. Si no lo esta, entrena un modelo `linear_ridge` ligero para mantener el flujo funcionando. Para forzar Keras:

```powershell
python -m irrigation_advisor.cli train-ml `
  --input-file data/resultados/comparativa_aemet_sevilla.csv `
  --model-dir models/riego_predictivo_keras `
  --backend keras `
  --epochs 200
```

Predecir con el modelo entrenado:

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
  --output markdown
```

Tambien se puede anadir la prediccion ML al informe de cliente:

```powershell
python -m irrigation_advisor.cli recommend `
  --weather-file data/resultados/comparativa_aemet_sevilla.csv `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --crop olivar `
  --stage media `
  --area-m2 3500 `
  --ml-model-dir models/riego_predictivo
```

Si se usa el modelo TensorFlow/Keras entrenado, sustituir `models/riego_predictivo` por `models/riego_predictivo_keras`.

## Comparativa de cultivos

Para comparar los tres cultivos con el mismo escenario climatico y superficie:

```powershell
python -m irrigation_advisor.cli compare `
  --et0 5.6 `
  --rain-mm 0 `
  --stage media `
  --area-m2 10000
```

Para obtener una tabla Markdown que pueda pegarse en resultados:

```powershell
python -m irrigation_advisor.cli compare `
  --et0 5.6 `
  --rain-mm 0 `
  --stage media `
  --area-m2 10000 `
  --output markdown
```

Esta comparativa mantiene constantes ET0, lluvia, superficie y eficiencia. Lo que cambia es el perfil agronomico del cultivo: `Kc` y marco por planta.

## Exportacion de datos

Para generar un dataset CSV preparado para resultados y dashboard:

```powershell
python -m irrigation_advisor.cli export-comparison `
  --et0 5.6 `
  --rain-mm 0 `
  --stage media `
  --area-m2 10000 `
  --output-file data/resultados/comparativa_riego.csv
```

Tambien se puede exportar a JSON cambiando la extension:

```powershell
python -m irrigation_advisor.cli export-comparison `
  --et0 5.6 `
  --rain-mm 0 `
  --stage media `
  --area-m2 10000 `
  --output-file data/resultados/comparativa_riego.json
```

Columnas principales del CSV:

```text
fecha,estacion,nombre_estacion,provincia,cultivo,fase,superficie_m2,eficiencia_riego,lluvia_efectiva_ratio,et0_mm,lluvia_mm,tmin_c,tmax_c,tmedia_c,kc,marco_m2_por_planta,etc_mm,riego_bruto_mm,litros_totales,litros_por_planta,ranking_demanda
```

## Exportacion con AEMET real

Para generar el mismo dataset usando datos reales de una estacion AEMET:

```powershell
python -m irrigation_advisor.cli export-aemet-comparison `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --stage media `
  --area-m2 10000 `
  --output-file data/resultados/comparativa_aemet_sevilla.csv
```

La clave de AEMET debe estar fuera del codigo, como variable de entorno o en un archivo `.env` ignorado por Git:

```powershell
$env:AEMET_API_KEY = "tu_api_key"
```

Si AEMET no devuelve ET0 directamente, el programa estima ET0 con Hargreaves-Samani a partir de temperatura maxima, minima y latitud de la estacion.

## Cache local AEMET

Para evitar saturar AEMET, el flujo recomendado es sincronizar datos una vez y consultar despues la cache local SQLite:

```powershell
python -m irrigation_advisor.cli sync-aemet-cache `
  --db-file data/aemet_cache.sqlite
```

El comando anterior descarga el inventario nacional de estaciones y lo guarda localmente. Para cargar datos climaticos diarios de forma controlada:

```powershell
python -m irrigation_advisor.cli sync-aemet-cache `
  --db-file data/aemet_cache.sqlite `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --request-delay 1.5 `
  --max-stations 1
```

Para sincronizar varias estaciones, aumenta `--max-stations`. Para una carga nacional completa, usa `--all-stations`, pero debe ejecutarse por periodos cortos y con pausa entre peticiones:

```powershell
python -m irrigation_advisor.cli sync-aemet-cache `
  --db-file data/aemet_cache.sqlite `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --all-stations `
  --request-delay 2
```

Una vez cargada la cache, la recomendacion se puede calcular sin llamar a AEMET:

```powershell
python -m irrigation_advisor.cli recommend `
  --cache-db data/aemet_cache.sqlite `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --crop olivar `
  --stage media `
  --area-m2 3500
```

El dataset ML tambien puede construirse desde la cache:

```powershell
python -m irrigation_advisor.cli build-ml-dataset `
  --cache-db data/aemet_cache.sqlite `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --output-file data/resultados/dataset_ml_aemet.csv
```

La interfaz Streamlit incluye el modo `Cache local`, pensado como opcion principal para el servicio predictivo. De este modo, AEMET actua como fuente oficial de actualizacion y la aplicacion trabaja contra una base propia.

## Resumen de resultados

Para resumir un CSV diario por cultivo:

```powershell
python -m irrigation_advisor.cli summarize-results `
  --input-file data/resultados/comparativa_aemet_sevilla.csv `
  --output-file data/resultados/resumen_aemet_sevilla.csv
```

Para obtener una tabla Markdown lista para pegar en resultados:

```powershell
python -m irrigation_advisor.cli summarize-results `
  --input-file data/resultados/comparativa_aemet_sevilla.csv `
  --output-file data/resultados/resumen_aemet_sevilla.md
```

El resumen calcula:

```text
dias_analizados, et0_media_mm, lluvia_total_mm, riego_total_litros, riego_medio_litros_dia, riego_medio_mm_dia, litros_por_planta_medio, diferencia_litros_vs_minimo, porcentaje_incremento_vs_minimo, ranking_demanda
```

## Pruebas

Ejecutar las pruebas desde la raiz del proyecto:

```powershell
python -m unittest discover -s tests -v
```

## Variables principales

- `ET0`: evapotranspiracion de referencia, en mm/dia.
- `Kc`: coeficiente de cultivo segun especie y fase fenologica.
- `ETc`: evapotranspiracion real del cultivo, en mm/dia.
- `rain_mm`: precipitacion diaria.
- `effective_rainfall_ratio`: fraccion de lluvia considerada util. Por defecto: `0.80`.
- `plant_spacing_m2`: superficie asignada por planta. Se aplica segun cultivo salvo que se sobrescriba.
- `irrigation_efficiency`: eficiencia aplicada para pasar de riego neto a riego bruto.
- `area_m2`: superficie de la parcela usada para convertir milimetros en litros.

## Límites del prototipo

- No sustituye una validacion agronomica en campo.
- Los valores de `Kc` y marco por planta son valores iniciales; deben ajustarse con bibliografia y datos reales de la parcela.
- AEMET no siempre publica ET0 directamente. Por eso se usa Hargreaves-Samani como estimacion cuando faltan datos completos.
- El modulo calcula una recomendacion agronomica. El modelo ML debe entrenarse despues con historico suficiente y una variable objetivo validada.

## Etica y licencia

- La prediccion ML se presenta como apoyo a la decision, no como sustituto de supervision tecnica.
- La API Key de AEMET y posibles datos privados de parcelas deben quedar fuera del repositorio.
- La documentacion se publica bajo CC BY-NC-SA 4.0. Ver `LICENSE.md`.
- El codigo fuente mantiene finalidad academica; si se libera como software reutilizable, debe definirse una licencia de software especifica.

## Referencias

[1] Agencia Estatal de Meteorologia, "AEMET OpenData: informacion del servicio," AEMET, 2026. [Online]. Available: https://opendata.aemet.es/centrodedescargas/info. [Accessed: May 6, 2026].

[2] Agencia Estatal de Meteorologia, "AEMET OpenData: ejemplos de programas cliente," AEMET, 2026. [Online]. Available: https://opendata.aemet.es/centrodedescargas/ejemProgramas. [Accessed: May 6, 2026].

[3] R. G. Allen, L. S. Pereira, D. Raes, and M. Smith, *Crop evapotranspiration: Guidelines for computing crop water requirements*, FAO Irrigation and Drainage Paper 56. Rome, Italy: FAO, 1998.
