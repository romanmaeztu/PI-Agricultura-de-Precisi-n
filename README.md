# Sistema de recomendacion de riego con AEMET

Este MVP calcula cuanto regar una parcela a partir de datos climaticos de AEMET y parametros agronomicos del cultivo, suelo y sistema de riego. Es un primer escalon tecnico: antes de entrenar ML, el calculo debe ser trazable y defendible.

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

6. Si se indica humedad inicial del suelo, calcula tambien el primer riego para llevar el perfil hasta capacidad de campo:

```text
primer_riego_mm = (capacidad_campo - humedad_actual) * profundidad_raices_m * 1000 / eficiencia
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

```powershell
python -m irrigation_advisor.cli aemet `
  --station 5783 `
  --start 2024-05-01 `
  --end 2024-05-07 `
  --crop olivar `
  --stage desarrollo `
  --soil franco `
  --area-m2 10000 `
  --root-depth-m 0.60 `
  --irrigation-efficiency 0.90 `
  --plant-spacing-m2 8 `
  --emitters-per-plant 2 `
  --emitter-flow-lph 4
```

Ejemplo sin API, util para validar el algoritmo:

```powershell
python -m irrigation_advisor.cli manual `
  --et0 5.6 `
  --rain-mm 0 `
  --crop olivar `
  --stage desarrollo `
  --soil franco `
  --area-m2 10000 `
  --plant-spacing-m2 8 `
  --emitters-per-plant 2 `
  --emitter-flow-lph 4
```

## Variables principales

- `ET0`: evapotranspiracion de referencia, en mm/dia.
- `Kc`: coeficiente de cultivo segun especie y fase fenologica.
- `ETc`: evapotranspiracion real del cultivo, en mm/dia.
- `rain_mm`: precipitacion diaria.
- `effective_rainfall_ratio`: fraccion de lluvia considerada util. Por defecto: `0.80`.
- `field_capacity`: capacidad de campo del suelo, en fraccion volumetrica.
- `wilting_point`: punto de marchitez permanente, en fraccion volumetrica.
- `root_depth_m`: profundidad efectiva de raices.
- `irrigation_efficiency`: eficiencia del sistema de riego. En goteo suele ser alta, pero debe justificarse.

## Limites del MVP

- No sustituye la calibracion en campo con sensores de humedad.
- Los valores de `Kc`, capacidad de campo y punto de marchitez son valores iniciales; deben ajustarse con bibliografia y datos reales de la parcela.
- AEMET no siempre publica todas las variables necesarias para Penman-Monteith. Por eso se usa Hargreaves-Samani como estimacion cuando faltan radiacion, viento o humedad.
- El modulo calcula una recomendacion agronomica. El modelo ML debe entrenarse despues con historico suficiente y una variable objetivo validada.

## Referencias

[1] Agencia Estatal de Meteorologia, "AEMET OpenData: informacion del servicio," AEMET, 2026. [Online]. Available: https://opendata.aemet.es/centrodedescargas/info. [Accessed: May 6, 2026].

[2] Agencia Estatal de Meteorologia, "AEMET OpenData: ejemplos de programas cliente," AEMET, 2026. [Online]. Available: https://opendata.aemet.es/centrodedescargas/ejemProgramas. [Accessed: May 6, 2026].

[3] R. G. Allen, L. S. Pereira, D. Raes, and M. Smith, *Crop evapotranspiration: Guidelines for computing crop water requirements*, FAO Irrigation and Drainage Paper 56. Rome, Italy: FAO, 1998.
