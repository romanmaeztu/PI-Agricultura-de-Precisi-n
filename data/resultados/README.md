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

Para generar datos reales desde AEMET:

```powershell
python -m irrigation_advisor.cli export-aemet-comparison `
  --station 5783 `
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
