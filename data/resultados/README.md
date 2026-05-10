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

