# Modelos predictivos

Este directorio guarda modelos entrenados localmente. Los artefactos de modelo se ignoran en Git porque pueden crecer mucho y dependen del dataset usado.

Flujo recomendado:

```powershell
python -m pip install -r requirements-ml.txt
```

```powershell
python -m irrigation_advisor.cli train-ml `
  --input-file data/resultados/comparativa_aemet_sevilla.csv `
  --model-dir models/riego_predictivo `
  --backend auto
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
| Dataset | `data/resultados/dataset_ml_aemet.csv` |
| Filas | 21 |
| Variables de entrada | 17 |
| Backend | `keras_mlp` |
| Target | `riego_bruto_mm` |
| MAE | 0.0913 mm |
| RMSE | 0.1180 mm |
| R2 | 0.9595 |

Estas metricas validan que el modelo aprende la referencia agronomica del dataset local. No equivalen a una validacion con datos reales de agricultores.
