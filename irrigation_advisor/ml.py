from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

from .calculator import build_crop_profile, build_soil_profile
from .models import IrrigationSystem, WeatherDay


TARGET_FIELD = "riego_bruto_mm"

NUMERIC_FIELDS = [
    "day_sin",
    "day_cos",
    "et0_mm",
    "lluvia_mm",
    "tmin_c",
    "tmax_c",
    "tmedia_c",
    "kc",
    "profundidad_raices_m",
    "marco_m2_por_planta",
    "agua_facilmente_disponible_mm",
    "eficiencia_riego",
    "lluvia_efectiva_ratio",
    "goteros_por_planta",
    "caudal_gotero_lph",
    "caudal_planta_lph",
]

CATEGORICAL_FIELDS = ["estacion", "provincia", "cultivo", "fase", "suelo"]


@dataclass(frozen=True)
class TrainingExample:
    features: dict[str, float | str]
    target_mm: float


@dataclass(frozen=True)
class FeatureSchema:
    numeric_fields: list[str]
    categorical_fields: list[str]
    numeric_means: dict[str, float]
    numeric_stds: dict[str, float]
    categories: dict[str, list[str]]

    def to_dict(self) -> dict:
        return {
            "numeric_fields": self.numeric_fields,
            "categorical_fields": self.categorical_fields,
            "numeric_means": self.numeric_means,
            "numeric_stds": self.numeric_stds,
            "categories": self.categories,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureSchema":
        return cls(
            numeric_fields=list(data["numeric_fields"]),
            categorical_fields=list(data["categorical_fields"]),
            numeric_means={key: float(value) for key, value in data["numeric_means"].items()},
            numeric_stds={key: float(value) for key, value in data["numeric_stds"].items()},
            categories={key: list(value) for key, value in data["categories"].items()},
        )


class IrrigationPredictor:
    def __init__(
        self,
        model_type: str,
        schema: FeatureSchema,
        metrics: dict,
        weights: list[float] | None = None,
        keras_model: object | None = None,
        target_mean: float = 0.0,
        target_std: float = 1.0,
    ) -> None:
        self.model_type = model_type
        self.schema = schema
        self.metrics = metrics
        self.weights = weights
        self.keras_model = keras_model
        self.target_mean = target_mean
        self.target_std = target_std or 1.0

    def predict_mm(self, rows: Iterable[dict]) -> list[float]:
        encoded = [encode_features(normalize_feature_input(row), self.schema) for row in rows]
        if self.model_type == "linear_ridge":
            if self.weights is None:
                raise ValueError("El modelo lineal no contiene pesos")
            return [max(0.0, dot(self.weights, [1.0] + row)) for row in encoded]
        if self.model_type == "keras_mlp":
            if self.keras_model is None:
                raise ValueError("El modelo Keras no esta cargado")
            try:
                import numpy as np
            except ModuleNotFoundError as exc:
                raise RuntimeError("La prediccion Keras requiere numpy instalado") from exc
            predictions = self.keras_model.predict(np.array(encoded, dtype="float32"), verbose=0)
            return [max(0.0, float(item[0]) * self.target_std + self.target_mean) for item in predictions]
        raise ValueError(f"Tipo de modelo no soportado: {self.model_type}")


def train_irrigation_model(
    input_file: str,
    model_dir: str,
    backend: str = "auto",
    epochs: int = 150,
    validation_ratio: float = 0.20,
    default_area_m2: float = 10000.0,
    default_emitters_per_plant: int = 2,
    default_emitter_flow_lph: float = 4.0,
    default_efficiency: float = 0.90,
    default_effective_rainfall_ratio: float = 0.80,
    seed: int = 42,
) -> dict:
    rows = read_rows(input_file)
    examples = training_examples_from_rows(
        rows=rows,
        default_area_m2=default_area_m2,
        default_emitters_per_plant=default_emitters_per_plant,
        default_emitter_flow_lph=default_emitter_flow_lph,
        default_efficiency=default_efficiency,
        default_effective_rainfall_ratio=default_effective_rainfall_ratio,
    )
    if len(examples) < 2:
        raise ValueError("Se necesitan al menos 2 filas validas para entrenar el modelo")

    if backend not in {"auto", "keras", "linear"}:
        raise ValueError("backend debe ser auto, keras o linear")

    output_dir = Path(model_dir)
    if backend in {"auto", "keras"}:
        try:
            return train_keras_model(
                examples=examples,
                output_dir=output_dir,
                epochs=epochs,
                validation_ratio=validation_ratio,
                seed=seed,
            )
        except RuntimeError as exc:
            if backend == "keras":
                raise
            result = train_linear_model(
                examples=examples,
                output_dir=output_dir,
                validation_ratio=validation_ratio,
                seed=seed,
            )
            result["backend_requested"] = backend
            result["fallback_reason"] = str(exc)
            return result

    return train_linear_model(
        examples=examples,
        output_dir=output_dir,
        validation_ratio=validation_ratio,
        seed=seed,
    )


def training_examples_from_rows(
    rows: list[dict],
    default_area_m2: float = 10000.0,
    default_emitters_per_plant: int = 2,
    default_emitter_flow_lph: float = 4.0,
    default_efficiency: float = 0.90,
    default_effective_rainfall_ratio: float = 0.80,
) -> list[TrainingExample]:
    examples = []
    for row in rows:
        target = optional_float(row.get(TARGET_FIELD))
        if target is None:
            continue
        features = row_to_features(
            row=row,
            default_area_m2=default_area_m2,
            default_emitters_per_plant=default_emitters_per_plant,
            default_emitter_flow_lph=default_emitter_flow_lph,
            default_efficiency=default_efficiency,
            default_effective_rainfall_ratio=default_effective_rainfall_ratio,
        )
        examples.append(TrainingExample(features=features, target_mm=max(0.0, target)))
    return examples


def row_to_features(
    row: dict,
    default_area_m2: float = 10000.0,
    default_emitters_per_plant: int = 2,
    default_emitter_flow_lph: float = 4.0,
    default_efficiency: float = 0.90,
    default_effective_rainfall_ratio: float = 0.80,
) -> dict[str, float | str]:
    day = parse_row_date(row)
    day_angle = (2 * math.pi * day.timetuple().tm_yday) / 366
    gross_mm = optional_float(row.get(TARGET_FIELD))
    liters_total = optional_float(row.get("litros_totales"))
    area_m2 = optional_float(row.get("superficie_m2"))
    if area_m2 is None and gross_mm and gross_mm > 0 and liters_total and liters_total > 0:
        area_m2 = liters_total / gross_mm
    if area_m2 is None or area_m2 <= 0:
        area_m2 = default_area_m2

    plant_spacing = optional_float(row.get("marco_m2_por_planta")) or 0.0
    plants = area_m2 / plant_spacing if plant_spacing > 0 else 0.0
    emitters = optional_float(row.get("goteros_por_planta")) or float(default_emitters_per_plant)
    emitter_flow = optional_float(row.get("caudal_gotero_lph")) or default_emitter_flow_lph
    flow_per_plant = optional_float(row.get("caudal_planta_lph"))
    if flow_per_plant is None:
        liters_per_plant = optional_float(row.get("litros_por_planta"))
        runtime = optional_float(row.get("horas_riego"))
        if liters_per_plant and runtime and runtime > 0:
            flow_per_plant = liters_per_plant / runtime
        else:
            flow_per_plant = emitters * emitter_flow

    tmin = optional_float(row.get("tmin_c"))
    tmax = optional_float(row.get("tmax_c"))
    tmean = optional_float(row.get("tmedia_c"))
    if tmean is None and tmin is not None and tmax is not None:
        tmean = (tmin + tmax) / 2.0

    return {
        "day_sin": math.sin(day_angle),
        "day_cos": math.cos(day_angle),
        "et0_mm": optional_float(row.get("et0_mm")) or 0.0,
        "lluvia_mm": optional_float(row.get("lluvia_mm")) or 0.0,
        "tmin_c": tmin or 0.0,
        "tmax_c": tmax or 0.0,
        "tmedia_c": tmean or 0.0,
        "kc": optional_float(row.get("kc")) or 0.0,
        "profundidad_raices_m": optional_float(row.get("profundidad_raices_m")) or 0.0,
        "marco_m2_por_planta": plant_spacing,
        "agua_facilmente_disponible_mm": optional_float(row.get("agua_facilmente_disponible_mm")) or 0.0,
        "superficie_m2": area_m2,
        "plantas_estimadas": plants,
        "eficiencia_riego": optional_float(row.get("eficiencia_riego")) or default_efficiency,
        "lluvia_efectiva_ratio": optional_float(row.get("lluvia_efectiva_ratio")) or default_effective_rainfall_ratio,
        "goteros_por_planta": emitters,
        "caudal_gotero_lph": emitter_flow,
        "caudal_planta_lph": flow_per_plant or 0.0,
        "estacion": str(row.get("estacion") or ""),
        "provincia": str(row.get("provincia") or ""),
        "cultivo": str(row.get("cultivo") or ""),
        "fase": str(row.get("fase") or ""),
        "suelo": str(row.get("suelo") or ""),
    }


def normalize_feature_input(row: dict) -> dict[str, float | str]:
    if all(field in row for field in NUMERIC_FIELDS) and all(field in row for field in CATEGORICAL_FIELDS):
        return row
    return row_to_features(row)


def train_linear_model(
    examples: list[TrainingExample],
    output_dir: Path,
    validation_ratio: float,
    seed: int,
) -> dict:
    train_examples, validation_examples = split_examples(examples, validation_ratio, seed)
    schema = build_feature_schema(train_examples)
    x_train = [encode_features(example.features, schema) for example in train_examples]
    y_train = [example.target_mm for example in train_examples]
    weights = fit_ridge_regression(x_train, y_train, ridge=0.001)
    predictor = IrrigationPredictor(
        model_type="linear_ridge",
        schema=schema,
        metrics={},
        weights=weights,
    )
    metrics = evaluate_predictor(predictor, validation_examples or train_examples)
    payload = {
        "model_type": "linear_ridge",
        "target": TARGET_FIELD,
        "created_at": datetime.now(UTC).isoformat(),
        "schema": schema.to_dict(),
        "weights": weights,
        "metrics": metrics,
        "backend_requested": "linear",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "model.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "model_dir": str(output_dir),
        "model_type": "linear_ridge",
        "target": TARGET_FIELD,
        "rows": len(examples),
        "features": encoded_feature_count(schema),
        "metrics": metrics,
    }


def train_keras_model(
    examples: list[TrainingExample],
    output_dir: Path,
    epochs: int,
    validation_ratio: float,
    seed: int,
) -> dict:
    try:
        import numpy as np
        import tensorflow as tf
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Keras no esta disponible. Instala tensorflow en un entorno compatible o usa --backend linear."
        ) from exc

    tf.keras.utils.set_random_seed(seed)
    train_examples, validation_examples = split_examples(examples, validation_ratio, seed)
    schema = build_feature_schema(train_examples)
    x_train = np.array([encode_features(example.features, schema) for example in train_examples], dtype="float32")
    y_train_raw = np.array([example.target_mm for example in train_examples], dtype="float32")
    target_mean = float(y_train_raw.mean())
    target_std = float(y_train_raw.std()) or 1.0
    y_train = (y_train_raw - target_mean) / target_std
    x_val = np.array([encode_features(example.features, schema) for example in validation_examples], dtype="float32")
    y_val_raw = np.array([example.target_mm for example in validation_examples], dtype="float32")
    y_val = (y_val_raw - target_mean) / target_std if len(y_val_raw) else None

    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(x_train.shape[1],)),
            tf.keras.layers.Dense(32, activation="relu"),
            tf.keras.layers.Dense(16, activation="relu"),
            tf.keras.layers.Dense(1),
        ]
    )
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.01), loss="mse", metrics=["mae"])
    validation_data = (x_val, y_val) if len(validation_examples) else None
    model.fit(x_train, y_train, epochs=epochs, verbose=0, validation_data=validation_data)

    predictor = IrrigationPredictor(
        model_type="keras_mlp",
        schema=schema,
        metrics={},
        keras_model=model,
        target_mean=target_mean,
        target_std=target_std,
    )
    metrics = evaluate_predictor(predictor, validation_examples or train_examples)
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save(output_dir / "model.keras")
    metadata = {
        "model_type": "keras_mlp",
        "target": TARGET_FIELD,
        "created_at": datetime.now(UTC).isoformat(),
        "schema": schema.to_dict(),
        "target_mean": target_mean,
        "target_std": target_std,
        "metrics": metrics,
        "backend_requested": "keras",
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "model_dir": str(output_dir),
        "model_type": "keras_mlp",
        "target": TARGET_FIELD,
        "rows": len(examples),
        "features": encoded_feature_count(schema),
        "metrics": metrics,
    }


def load_predictor(model_dir: str) -> IrrigationPredictor:
    path = Path(model_dir)
    linear_path = path / "model.json"
    keras_metadata_path = path / "metadata.json"
    if linear_path.exists():
        data = json.loads(linear_path.read_text(encoding="utf-8"))
        return IrrigationPredictor(
            model_type=data["model_type"],
            schema=FeatureSchema.from_dict(data["schema"]),
            metrics=data.get("metrics", {}),
            weights=[float(value) for value in data["weights"]],
        )
    if keras_metadata_path.exists():
        try:
            import tensorflow as tf
        except ModuleNotFoundError as exc:
            raise RuntimeError("Para cargar este modelo Keras falta instalar tensorflow") from exc
        data = json.loads(keras_metadata_path.read_text(encoding="utf-8"))
        return IrrigationPredictor(
            model_type=data["model_type"],
            schema=FeatureSchema.from_dict(data["schema"]),
            metrics=data.get("metrics", {}),
            keras_model=tf.keras.models.load_model(path / "model.keras"),
            target_mean=float(data.get("target_mean", 0.0)),
            target_std=float(data.get("target_std", 1.0)),
        )
    raise FileNotFoundError(f"No se encontro un modelo en {model_dir}")


def predict_irrigation_with_model(
    model_dir: str,
    weather_days: list[WeatherDay],
    args: SimpleNamespace,
    station_id: str,
    station_name: str | None,
    province: str | None,
) -> dict:
    predictor = load_predictor(model_dir)
    rows, system = prediction_rows_from_weather(
        weather_days=weather_days,
        args=args,
        station_id=station_id,
        province=province,
    )
    predicted_mm = predictor.predict_mm(rows)
    daily = []
    for row, gross_mm in zip(rows, predicted_mm):
        liters_total = gross_mm * system.area_m2
        liters_per_plant = gross_mm * system.plant_spacing_m2 if system.plant_spacing_m2 else None
        runtime_hours = None
        if liters_per_plant is not None and system.flow_per_plant_lph:
            runtime_hours = liters_per_plant / system.flow_per_plant_lph
        daily.append(
            {
                "date": row["fecha"],
                "predicted_gross_irrigation_mm": round(gross_mm, 2),
                "predicted_liters_total": round(liters_total, 2),
                "predicted_liters_per_plant": round(liters_per_plant, 2)
                if liters_per_plant is not None
                else None,
                "predicted_runtime_hours": round(runtime_hours, 2)
                if runtime_hours is not None
                else None,
            }
        )

    days = len(daily)
    total_liters = sum(day["predicted_liters_total"] for day in daily)
    runtime_values = [day["predicted_runtime_hours"] for day in daily if day["predicted_runtime_hours"] is not None]
    plant_values = [day["predicted_liters_per_plant"] for day in daily if day["predicted_liters_per_plant"] is not None]
    gross_values = [day["predicted_gross_irrigation_mm"] for day in daily]
    return {
        "model": {
            "model_dir": model_dir,
            "model_type": predictor.model_type,
            "target": TARGET_FIELD,
            "metrics": predictor.metrics,
        },
        "location": {
            "station": station_id,
            "station_name": station_name,
            "province": province,
        },
        "summary": {
            "total_liters": round(total_liters, 2),
            "avg_liters_day": round(total_liters / days, 2) if days else 0.0,
            "avg_gross_mm_day": round(sum(gross_values) / days, 2) if days else 0.0,
            "avg_liters_plant_day": round(sum(plant_values) / len(plant_values), 2) if plant_values else None,
            "avg_runtime_hours_day": round(sum(runtime_values) / len(runtime_values), 2) if runtime_values else None,
        },
        "daily": daily,
        "note": "Prediccion supervisada sobre historicos AEMET exportados y variables de cultivo/parcela.",
    }


def prediction_rows_from_weather(
    weather_days: list[WeatherDay],
    args: SimpleNamespace,
    station_id: str,
    province: str | None,
) -> tuple[list[dict], IrrigationSystem]:
    crop = build_crop_profile(crop=args.crop, stage=args.stage, kc=getattr(args, "kc", None))
    root_depth_m = getattr(args, "root_depth_m", None) or crop.root_depth_m
    max_depletion_fraction = getattr(args, "max_depletion_fraction", None) or crop.max_depletion_fraction
    soil = build_soil_profile(
        soil=args.soil,
        root_depth_m=root_depth_m,
        field_capacity=getattr(args, "field_capacity", None),
        wilting_point=getattr(args, "wilting_point", None),
        max_depletion_fraction=max_depletion_fraction,
    )
    plant_spacing_m2 = getattr(args, "plant_spacing_m2", None) or crop.plant_spacing_m2
    system = IrrigationSystem(
        area_m2=args.area_m2,
        efficiency=args.irrigation_efficiency,
        plant_spacing_m2=plant_spacing_m2,
        emitters_per_plant=getattr(args, "emitters_per_plant", None),
        emitter_flow_lph=getattr(args, "emitter_flow_lph", None),
    )
    rows = []
    for day in weather_days:
        rows.append(
            {
                "fecha": day.date.isoformat(),
                "estacion": station_id,
                "provincia": province,
                "cultivo": crop.name,
                "fase": crop.stage,
                "suelo": soil.name,
                "et0_mm": day.et0_mm,
                "lluvia_mm": day.rain_mm,
                "tmin_c": day.tmin_c,
                "tmax_c": day.tmax_c,
                "tmedia_c": day.tmean_c,
                "kc": crop.kc,
                "profundidad_raices_m": root_depth_m,
                "marco_m2_por_planta": plant_spacing_m2,
                "agua_facilmente_disponible_mm": soil.readily_available_water_mm,
                "superficie_m2": system.area_m2,
                "eficiencia_riego": system.efficiency,
                "lluvia_efectiva_ratio": getattr(args, "effective_rainfall_ratio", 0.80),
                "goteros_por_planta": system.emitters_per_plant,
                "caudal_gotero_lph": system.emitter_flow_lph,
                "caudal_planta_lph": system.flow_per_plant_lph,
            }
        )
    return rows, system


def build_feature_schema(examples: list[TrainingExample]) -> FeatureSchema:
    numeric_means = {}
    numeric_stds = {}
    for field in NUMERIC_FIELDS:
        values = [float(example.features[field]) for example in examples]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        numeric_means[field] = mean
        numeric_stds[field] = math.sqrt(variance) or 1.0

    categories = {
        field: sorted({str(example.features[field]) for example in examples if str(example.features[field])})
        for field in CATEGORICAL_FIELDS
    }
    return FeatureSchema(
        numeric_fields=list(NUMERIC_FIELDS),
        categorical_fields=list(CATEGORICAL_FIELDS),
        numeric_means=numeric_means,
        numeric_stds=numeric_stds,
        categories=categories,
    )


def encode_features(features: dict[str, float | str], schema: FeatureSchema) -> list[float]:
    encoded = []
    for field in schema.numeric_fields:
        value = float(features.get(field) or 0.0)
        encoded.append((value - schema.numeric_means[field]) / schema.numeric_stds[field])
    for field in schema.categorical_fields:
        value = str(features.get(field) or "")
        encoded.extend(1.0 if value == category else 0.0 for category in schema.categories.get(field, []))
    return encoded


def encoded_feature_count(schema: FeatureSchema) -> int:
    return len(schema.numeric_fields) + sum(len(values) for values in schema.categories.values())


def split_examples(
    examples: list[TrainingExample],
    validation_ratio: float,
    seed: int,
) -> tuple[list[TrainingExample], list[TrainingExample]]:
    shuffled = list(examples)
    random.Random(seed).shuffle(shuffled)
    if len(shuffled) < 5:
        return shuffled, shuffled
    validation_count = max(1, int(len(shuffled) * validation_ratio))
    return shuffled[validation_count:], shuffled[:validation_count]


def fit_ridge_regression(x: list[list[float]], y: list[float], ridge: float) -> list[float]:
    if not x:
        raise ValueError("No hay datos de entrenamiento")
    x_aug = [[1.0] + row for row in x]
    feature_count = len(x_aug[0])
    matrix = [[0.0 for _ in range(feature_count)] for _ in range(feature_count)]
    vector = [0.0 for _ in range(feature_count)]
    for row, target in zip(x_aug, y):
        for i in range(feature_count):
            vector[i] += row[i] * target
            for j in range(feature_count):
                matrix[i][j] += row[i] * row[j]
    for index in range(1, feature_count):
        matrix[index][index] += ridge
    return solve_linear_system(matrix, vector)


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            augmented[pivot][col] = 1e-12
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        for item in range(col, n + 1):
            augmented[col][item] /= pivot_value
        for row in range(n):
            if row == col:
                continue
            factor = augmented[row][col]
            for item in range(col, n + 1):
                augmented[row][item] -= factor * augmented[col][item]
    return [augmented[row][n] for row in range(n)]


def evaluate_predictor(predictor: IrrigationPredictor, examples: list[TrainingExample]) -> dict:
    if not examples:
        return {"mae_mm": None, "rmse_mm": None, "r2": None, "rows": 0}
    predictions = predictor.predict_mm(example.features for example in examples)
    actuals = [example.target_mm for example in examples]
    errors = [prediction - actual for prediction, actual in zip(predictions, actuals)]
    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = math.sqrt(sum(error**2 for error in errors) / len(errors))
    mean_actual = sum(actuals) / len(actuals)
    ss_tot = sum((actual - mean_actual) ** 2 for actual in actuals)
    ss_res = sum(error**2 for error in errors)
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot else 1.0
    return {
        "mae_mm": round(mae, 4),
        "rmse_mm": round(rmse, 4),
        "r2": round(r2, 4),
        "rows": len(examples),
    }


def dot(weights: list[float], values: list[float]) -> float:
    return sum(weight * value for weight, value in zip(weights, values))


def read_rows(input_file: str) -> list[dict]:
    input_path = Path(input_file)
    if input_path.suffix.lower() == ".json":
        data = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("El JSON debe contener una lista de filas")
        return data
    with input_path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def parse_row_date(row: dict) -> date:
    value = str(row.get("fecha") or "")
    if not value:
        return date(2000, 1, 1)
    return date.fromisoformat(value)


def optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace(",", "."))
