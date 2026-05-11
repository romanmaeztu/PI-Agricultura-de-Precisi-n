# Resultados generados

Esta carpeta esta reservada para datasets generados por la CLI.

Ejemplo:

```powershell
python -m irrigation_advisor.cli export-comparison `
  --et0 5.6 `
  --rain-mm 0 `
  --stage media `
  --soil franco `
  --area-m2 10000 `
  --output-file data/resultados/comparativa_riego.csv
```

Los archivos CSV/JSON resultantes sirven como entrada inicial para resultados, dashboard y futura ingesta en BigQuery.

Para generar un informe de recomendacion para un cliente:

```powershell
python -m irrigation_advisor.cli recommend `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --crop olivar `
  --stage media `
  --soil franco `
  --area-m2 3500 `
  --emitters-per-plant 2 `
  --emitter-flow-lph 4 `
  --output-file data/resultados/recomendacion_cliente_olivar.md
```

Si `comparativa_aemet_sevilla.csv` ya existe, se puede usar como cache:

```powershell
python -m irrigation_advisor.cli recommend `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --weather-file data/resultados/comparativa_aemet_sevilla.csv `
  --crop olivar `
  --stage media `
  --soil franco `
  --area-m2 3500 `
  --emitters-per-plant 2 `
  --emitter-flow-lph 4 `
  --output-file data/resultados/recomendacion_cliente_olivar.md
```

Para generar datos reales desde AEMET:

```powershell
python -m irrigation_advisor.cli export-aemet-comparison `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --stage media `
  --soil franco `
  --area-m2 10000 `
  --output-file data/resultados/comparativa_aemet_sevilla.csv
```

Para resumir la comparativa:

```powershell
python -m irrigation_advisor.cli summarize-results `
  --input-file data/resultados/comparativa_aemet_sevilla.csv `
  --output-file data/resultados/resumen_aemet_sevilla.md
```

Para generar un dataset historico listo para ML:

```powershell
python -m irrigation_advisor.cli build-ml-dataset `
  --weather-file data/resultados/comparativa_aemet_sevilla.csv `
  --province SEVILLA `
  --station-name AEROPUERTO `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --soil franco `
  --soil franco_arcilloso `
  --output-file data/resultados/dataset_ml_aemet.csv `
  --train-model-dir models/riego_predictivo
```
