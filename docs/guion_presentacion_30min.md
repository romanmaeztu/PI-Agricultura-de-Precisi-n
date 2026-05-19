# Guion de presentación de 30 minutos

## 1. Portada - 1 min

Presentar el proyecto como un prototipo de servicio predictivo de riego.

Frase clave:

> El objetivo es que un cliente pueda elegir zona, cultivo, fechas y superficie, y obtener cuánta agua debe aplicar.

## 2. Estructura de defensa - 1 min

Explicar que la demo no dura 30 minutos, sino 6-8 minutos dentro de la presentación.

## 3. Problema - 3 min

Explicar el riesgo doble:

- Regar de menos: estrés hídrico.
- Regar de más: desperdicio de agua y coste.

Pregunta central:

> ¿Cuánta agua necesita esta parcela, con este cultivo, en este periodo climático?

## 4. Objetivos - 3 min

Usar la escalera:

1. Variables.
2. AEMET.
3. Cálculo.
4. Cultivos.
5. ML.
6. Interfaz.
7. Validación.

## 5. Alcance - 2 min

Dejar muy claro:

- Sí se calcula necesidad hídrica.
- No se calcula diseño de goteros.
- IoT y BigQuery quedan como mejora futura.
- No hay validación comercial con parcelas reales.

## 6. Arquitectura - 3 min

Explicar el flujo:

```text
cliente -> Streamlit -> AEMET/CSV -> ETL -> cálculo + ML -> informe
```

## 7. Datos de entrada - 2 min

Explicar que solo se usan variables necesarias:

- Localización.
- Clima.
- Cultivo.
- Parcela.

## 8. Cálculo agronómico - 4 min

Explicar la fórmula:

```text
ETc = ET0 * Kc
riego_bruto = max(0, ETc - lluvia_efectiva) / eficiencia
litros = riego_bruto * superficie
```

Frase clave:

> Un milímetro de riego equivale a un litro por metro cuadrado.

## 9. Comparación de cultivos - 2 min

Explicar que con el mismo clima cambia la demanda:

- Olivar: menor demanda.
- Cítricos: demanda intermedia.
- Almendro: mayor demanda en este escenario.

## 10. Machine Learning - 4 min

Explicar con rigor:

- El modelo predice `riego_bruto_mm`.
- Los litros se calculan después con la superficie.
- En la demo se usa un modelo estable versionado.
- Para uso comercial real harían falta datos reales de riego aplicado.

Frase clave:

> El ML aprende la referencia agronómica del sistema; todavía no valida si un agricultor riega bien o mal en campo.

## 11. Demo estable - 1 min

Antes de ejecutar, explicar:

- Se usa CSV local para no depender de AEMET en directo.
- El escenario es Sevilla Aeropuerto, olivar, 3.500 m2.

## 12. Demo/resultados - 6-8 min

Ejecutar la app y explicar:

- Riego total: agua total para la parcela en el periodo.
- Riego medio diario: media diaria para toda la parcela.
- Litros por planta: media diaria por planta.
- Lámina diaria: profundidad media; 1 mm = 1 L/m2.
- Predicción ML: resultado muy cercano al cálculo agronómico.

Resultado esperado:

```text
Riego total: 97.156 L
Riego medio diario: 13.879 L/día
Litros por planta: 31,72 L/planta
Lámina diaria: 3,97 mm
```

## 13. Validación - 2 min

Mostrar:

- 26 pruebas unitarias superadas.
- GitHub actualizado.
- Datos de demo versionados.
- Exportación Markdown/JSON.

## 14. Limitaciones - 2 min

Defender con honestidad:

- No IoT real.
- No BigQuery desplegado.
- No validación con campo real.
- No diseño de goteros.

## 15. Mejoras futuras - 2 min

Explicar el camino:

1. Calibrar con riegos reales.
2. Añadir predicción meteorológica.
3. Gestionar usuarios y parcelas.
4. Desplegar servicio cloud.

## 16. Cierre - 1 min

Frase final:

> El proyecto demuestra que se puede pasar de datos meteorológicos oficiales a una recomendación de riego clara, trazable y ampliable con Machine Learning.

## 17. Referencias - 30 s

Indicar que las referencias están en formato IEEE y ampliadas en la memoria.
