# Estado de preparación del proyecto

## 1. Documentación disponible

La documentación del proyecto queda organizada en los siguientes materiales:

| Elemento | Ruta | Estado |
|---|---|---|
| Memoria en Word | `docs/memoria_proyecto_intermodular.docx` | Generada |
| Memoria en Markdown | `docs/memoria_proyecto_intermodular.md` | Fuente editable |
| Código de la app | `app.py` | Implementado |
| Motor de cálculo | `irrigation_advisor/` | Implementado |
| Pruebas unitarias | `tests/test_calculator.py` | Implementadas |
| Capturas de la app | `docs/capturas/` | Actualizadas |
| Demostración reproducible | `docs/demo_presentacion_estable.md` | Preparada |
| README técnico | `README.md` | Actualizado |
| Repositorio GitHub | `https://github.com/romanmaeztu/PI-Agricultura-de-Precisi-n` | Subido |

## 2. Alcance implementado

- Selección de fuente climática: AEMET API, caché local o CSV.
- Selección de estación AEMET por provincia o inventario nacional.
- Selección de cultivo: olivar, cítricos y almendro.
- Selección de fase fenológica.
- Entrada de superficie de parcela.
- Cálculo de riego recomendado en:
  - litros totales del periodo,
  - litros medios diarios,
  - litros medios por planta,
  - lámina media diaria en mm.
- Capa ML entrenable para predecir `riego_bruto_mm`.
- Interfaz Streamlit.
- Exportaciones CSV/JSON/Markdown.
- Pruebas unitarias.

## 3. Alcance no implementado

- Sensores IoT en campo.
- Lecturas reales de humedad del suelo.
- NDVI o imágenes satelitales.
- Conductividad eléctrica del suelo.
- BigQuery desplegado en Google Cloud.
- ROI económico con datos reales de clientes.
- Validación agronómica en parcela real.

Estos puntos se documentan como mejoras futuras o limitaciones actuales, no como funcionalidades ya desarrolladas.

## 4. Comandos de validación

Ejecutar desde la raíz del proyecto:

```powershell
python -m unittest discover -s tests -v
```

Resultado esperado:

```text
Ran 26 tests
OK
```

Ejecutar la aplicación:

```powershell
python -m streamlit run app.py
```

Abrir en navegador:

```text
http://localhost:8501
```

Si el puerto 8501 está ocupado, Streamlit propondrá otro puerto.

## 5. Procedimiento de demostración funcional

1. Abrir la app Streamlit.
2. Elegir `CSV local` para evitar saturar AEMET durante la exposición.
3. Usar el archivo `data/demo/aemet_sevilla_enero_junio_2024.csv`.
4. Mostrar el inventario nacional AEMET y seleccionar estación, fechas, cultivo, fase y superficie.
5. Activar el modelo ML para mostrar la capa predictiva.
6. Pulsar `Calcular recomendación`.
7. Revisar los resultados principales:
   - `Riego total`: agua total para toda la parcela en el periodo.
   - `Riego medio diario`: media diaria para toda la parcela.
   - `Litros por planta`: media diaria por planta según el marco del cultivo.
   - `Lámina diaria`: profundidad media diaria de riego; 1 mm equivale a 1 L/m2.
8. Mostrar las descargas Markdown/JSON.

## 6. Revisión final de coherencia

| Pregunta | Respuesta técnica |
|---|---|
| ¿El proyecto calcula agua por goteros? | No. Calcula necesidad hídrica de la plantación; el reparto hidráulico queda fuera del alcance. |
| ¿El suelo interviene en la app? | No como entrada del cliente. El flujo principal usa AEMET, cultivo, fase, superficie, lluvia efectiva y eficiencia. |
| ¿BigQuery está desplegado? | No. Queda cerrado como referencia teórica/futura, no como implementación. |
| ¿IoT está implementado? | No. Se menciona solo como mejora futura. |
| ¿Qué predice el ML? | Predice `riego_bruto_mm`, es decir, la lámina de riego recomendada antes de convertirla a litros. |
| ¿Puede recomendar a siete días futuros? | La arquitectura está preparada, pero necesita una predicción meteorológica futura fiable. El ML no predice el clima por sí solo. |
| ¿Qué limitación principal tiene el modelo? | Ha aprendido sobre históricos AEMET y etiquetas generadas por el cálculo agronómico; para servicio comercial real requiere datos medidos en campo. |

## 7. Control de calidad previo a la presentación

- Revisar que la portada de la memoria tenga nombre, centro, ciclo, módulo y fecha correctos.
- Confirmar con el tutor si exige PDF además de Word.
- Comprobar que la API key de AEMET no se entrega dentro del código.
- Ejecutar pruebas el mismo día de la presentación.
- Verificar que GitHub muestra el último commit.
