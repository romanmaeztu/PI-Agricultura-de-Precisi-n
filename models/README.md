# Modelos predictivos

Este directorio guarda modelos entrenados localmente. Los artefactos de modelo se ignoran en Git porque pueden crecer mucho y dependen del dataset usado.

Flujo recomendado:

```powershell
python -m pip install -r requirements-ml.txt
```

```powershell
python -m irrigation_advisor.cli train-ml `
  --input-file data/demo/aemet_sevilla_enero_junio_2024.csv `
  --model-dir models/riego_predictivo `
  --backend linear
```

El backend `auto` usa Keras si TensorFlow esta disponible. Si no, entrena un modelo `linear_ridge` ligero para mantener el flujo operativo.

Para forzar TensorFlow/Keras:

```powershell
python -m irrigation_advisor.cli train-ml `
  --input-file data/resultados/dataset_ml_aemet.csv `
  --model-dir models/riego_predictivo_keras `
  --backend keras `
  --epochs 200
```

Ultimo entrenamiento demostrativo realizado:

| Campo | Valor |
|---|---:|
| Dataset | `data/demo/aemet_sevilla_enero_junio_2024.csv` |
| Filas | 546 |
| Variables de entrada | 17 |
| Backend | `linear_ridge` |
| Target | `riego_bruto_mm` |
| MAE | 0.3164 mm |
| RMSE | 0.5301 mm |
| R2 | 0.9337 |

Estas metricas validan que el modelo aprende la referencia agronomica del dataset local. No equivalen a una validacion con datos reales de agricultores.
