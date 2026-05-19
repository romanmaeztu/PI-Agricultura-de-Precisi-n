# Datos de demo estable

Esta carpeta contiene datos pequenos y versionados para ejecutar la demostracion sin depender de nuevas peticiones a AEMET.

## Archivo principal

`aemet_sevilla_mayo_2024.csv`

- Fuente original: exportacion local generada con datos AEMET.
- Estacion: Sevilla Aeropuerto (`5783`).
- Periodo: 2024-05-01 a 2024-05-07.
- Cultivos incluidos: olivar, citricos y almendro.
- Fase: media.
- Superficie de referencia: 3.500 m2.

Durante la presentacion se recomienda usar la fuente `CSV local` y este archivo:

```text
data/demo/aemet_sevilla_mayo_2024.csv
```

Asi se evita saturar la API y se asegura que los resultados sean siempre reproducibles.
