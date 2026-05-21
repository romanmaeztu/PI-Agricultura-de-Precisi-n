# Datos de demo estable

Esta carpeta contiene datos pequenos y versionados para ejecutar la demostracion sin depender de nuevas peticiones a AEMET.

## Archivo principal

`aemet_sevilla_enero_junio_2024.csv`

- Fuente original: exportacion local generada con datos AEMET.
- Estacion: Sevilla Aeropuerto (`5783`).
- Periodo: 2024-01-01 a 2024-06-30.
- Cultivos incluidos: olivar, citricos y almendro.
- Fase: media.
- Superficie de referencia: 3.500 m2.

Durante la presentacion se recomienda usar la fuente `CSV local` y este archivo:

```text
data/demo/aemet_sevilla_enero_junio_2024.csv
```

Asi se evita saturar la API y se asegura que los resultados sean siempre reproducibles.

## Prueba con lluvia

Para demostrar que la lluvia reduce el riego, usar:

- Fecha inicial: `2024-03-27`.
- Fecha final: `2024-04-02`.
- Cultivo: `olivar`.

En ese periodo la lluvia acumulada registrada en Sevilla Aeropuerto es de 106,8 mm. El sistema descuenta la lluvia efectiva y deja varios dias con riego recomendado igual a cero.

## Prueba sin lluvia

Para mantener la comparativa original de mayo, usar:

- Fecha inicial: `2024-05-01`.
- Fecha final: `2024-05-07`.
