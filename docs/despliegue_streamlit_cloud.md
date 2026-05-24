# Despliegue en Streamlit Community Cloud

Este documento explica cómo publicar la aplicación para que pueda abrirse desde cualquier ordenador mediante una URL, sin depender de una ejecución local del proyecto.

## Objetivo

Publicar la interfaz Streamlit del proyecto en Streamlit Community Cloud usando el repositorio de GitHub:

```text
https://github.com/romanmaeztu/PI-Agricultura-de-Precisi-n
```

Una vez desplegada, la demostración se abre desde el navegador como una página web.

## Estado del repositorio

El repositorio ya contiene los elementos necesarios para el despliegue:

| Elemento | Ruta | Función |
|---|---|---|
| Aplicación principal | `app.py` | Punto de entrada de Streamlit. |
| Dependencias | `requirements.txt` | Instala Streamlit en el entorno cloud. |
| Dataset demo | `data/demo/aemet_sevilla_enero_junio_2024.csv` | Permite ejecutar la demo sin saturar la API de AEMET. |
| Modelo ML ligero | `models/riego_predictivo/model.json` | Modelo predictivo versionado usado por la demo estable. |
| Documentación demo | `docs/demo_presentacion_estable.md` | Valores recomendados para mostrar al jurado. |

## Pasos de despliegue

1. Entrar en:

```text
https://share.streamlit.io
```

2. Iniciar sesión con GitHub.

3. Pulsar `Create app`.

4. Elegir la opción equivalente a `Yup, I have an app`.

5. Rellenar los datos:

| Campo | Valor |
|---|---|
| Repository | `romanmaeztu/PI-Agricultura-de-Precisi-n` |
| Branch | `main` |
| Main file path | `app.py` |
| App URL | Nombre libre, por ejemplo `riego-predictivo-roman` |

6. En `Advanced settings`, seleccionar Python `3.12` si aparece la opción.

7. No introducir la API key de AEMET en el repositorio. Para la demo principal no hace falta, porque se usa `CSV local`.

8. Pulsar `Deploy`.

## Configuración recomendada para la demo

Dentro de la app desplegada:

| Campo | Valor recomendado |
|---|---|
| Fuente de datos | `CSV local` |
| Archivo | `data/demo/aemet_sevilla_enero_junio_2024.csv` |
| Estación | `Sevilla Aeropuerto (5783)` |
| Cultivo | `Olivar` |
| Fase | `Fase media` |
| Superficie | `3500 m²` |
| Fecha sin lluvia | `2024-05-01` a `2024-05-07` |
| Fecha con lluvia | `2024-03-27` a `2024-04-02` |

## Resultados esperados

### Escenario seco

Periodo: `2024-05-01` a `2024-05-07`.

| Indicador | Valor esperado |
|---|---:|
| Riego total | 97.156 L |
| Riego medio diario | 13.879 L/día |
| Litros por planta | 31,72 L/planta/día |
| Lámina diaria | 3,97 mm/día |
| ET0 media | 5,10 mm/día |
| ETc media | 3,57 mm/día |
| Lluvia total | 0,00 mm |
| Predicción ML | 94.523 L |

### Escenario con lluvia

Periodo: `2024-03-27` a `2024-04-02`.

| Indicador | Valor esperado |
|---|---:|
| Lluvia total | 106,80 mm |
| ET0 media | 2,72 mm/día |
| ETc media | 1,91 mm/día |
| Riego total | 18.620 L |
| Riego medio diario | 2.660 L/día |
| Lámina diaria | 0,76 mm/día |

Este escenario permite demostrar que la lluvia efectiva se descuenta del cálculo y que, cuando la precipitación cubre la demanda del cultivo, el riego recomendado para ese día puede ser 0 L.

## Uso de AEMET API en Cloud

La demo principal no necesita API key porque trabaja con CSV local. Si se quiere activar el modo `AEMET API`, la clave debe configurarse como secreto de Streamlit Cloud, nunca dentro del código ni en GitHub.

Ejemplo de secreto:

```toml
AEMET_API_KEY = "valor_de_la_clave"
```

## Plan de contingencia

Si Streamlit Cloud no carga en el salón de actos:

1. Usar el portátil propio con la app ya probada.
2. Abrir el repositorio local.
3. Ejecutar `INICIAR_DEMO_STREAMLIT.bat`.
4. Abrir `http://localhost:8501`.

## Referencias técnicas

- Streamlit Docs, "Deploy your app on Community Cloud": https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- Streamlit Docs, "File organization for your Community Cloud app": https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization
- Streamlit Docs, "App dependencies for your Community Cloud app": https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
