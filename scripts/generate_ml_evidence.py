from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "resultados" / "dataset_ml_aemet.csv"
PREDICTION_MD = ROOT / "data" / "resultados" / "prediccion_ml_olivar.md"
LINEAR_MODEL = ROOT / "models" / "riego_predictivo" / "model.json"
KERAS_MODEL = ROOT / "models" / "riego_predictivo_keras" / "metadata.json"
OUTPUT_DIR = ROOT / "docs" / "ml_proceso"
GRAPH_DIR = OUTPUT_DIR / "graficas"
TABLE_DIR = OUTPUT_DIR / "tablas"


def u(text: str) -> str:
    return text.encode("ascii").decode("unicode_escape")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_number(value: str) -> float:
    value = value.strip()
    if "," in value and "." in value:
        return float(value.replace(".", "").replace(",", "."))
    if "," in value:
        return float(value.replace(",", "."))
    return float(value)


def parse_ml_daily_table(path: Path) -> list[dict[str, float | str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    capture = False
    rows: list[dict[str, float | str]] = []
    for line in lines:
        if line.startswith("| Fecha | Riego ML"):
            capture = True
            continue
        if capture and line.startswith("|---"):
            continue
        if capture:
            if not line.startswith("|") or not line.strip():
                break
            parts = [part.strip() for part in line.strip("|").split("|")]
            if len(parts) != 4:
                continue
            rows.append(
                {
                    "fecha": parts[0],
                    "riego_ml_mm": parse_number(parts[1]),
                    "litros_ml": parse_number(parts[2]),
                    "litros_planta_ml": parse_number(parts[3]),
                }
            )
    return rows


def load_metrics() -> list[dict[str, object]]:
    models = [
        ("lineal_ridge", LINEAR_MODEL),
        ("keras_mlp", KERAS_MODEL),
    ]
    rows: list[dict[str, object]] = []
    for label, path in models:
        data = json.loads(path.read_text(encoding="utf-8"))
        metrics = data["metrics"]
        rows.append(
            {
                "modelo": label,
                "target": data["target"],
                "mae_mm": metrics["mae_mm"],
                "rmse_mm": metrics["rmse_mm"],
                "r2": metrics["r2"],
                "filas_validacion": metrics["rows"],
            }
        )
    return rows


def build_summary_tables(dataset: list[dict[str, str]], ml_rows: list[dict[str, float | str]]) -> None:
    variable_rows = [
        {
            "grupo": "Localizacion",
            "variable": "estacion, provincia",
            "uso": "Identifica la zona climatica de origen AEMET.",
        },
        {
            "grupo": "Fecha",
            "variable": "fecha, day_sin, day_cos",
            "uso": "Representa el momento del año y permite codificar estacionalidad.",
        },
        {
            "grupo": "Clima",
            "variable": "ET0, lluvia, Tmin, Tmax, Tmedia",
            "uso": "Describe la demanda atmosferica y la precipitacion disponible.",
        },
        {
            "grupo": "Cultivo",
            "variable": "cultivo, fase, Kc",
            "uso": "Ajusta la demanda climatica a cada cultivo.",
        },
        {
            "grupo": "Parcela",
            "variable": "marco_m2_por_planta, eficiencia_riego, lluvia_efectiva_ratio",
            "uso": "Convierte la necesidad neta en dosis bruta y litros por planta.",
        },
        {
            "grupo": "Salida",
            "variable": "riego_bruto_mm",
            "uso": "Variable objetivo que aprende el modelo.",
        },
    ]
    write_csv(TABLE_DIR / "variables_ml.csv", variable_rows, ["grupo", "variable", "uso"])

    crop_summary: list[dict[str, object]] = []
    for crop in sorted({row["cultivo"] for row in dataset}):
        rows = [row for row in dataset if row["cultivo"] == crop]
        crop_summary.append(
            {
                "cultivo": crop,
                "filas": len(rows),
                "kc_medio": round(sum(float(row["kc"]) for row in rows) / len(rows), 3),
                "riego_medio_mm_dia": round(sum(float(row["riego_bruto_mm"]) for row in rows) / len(rows), 2),
                "litros_medios_dia": round(sum(float(row["litros_totales"]) for row in rows) / len(rows), 2),
            }
        )
    write_csv(
        TABLE_DIR / "resumen_dataset_por_cultivo.csv",
        crop_summary,
        ["cultivo", "filas", "kc_medio", "riego_medio_mm_dia", "litros_medios_dia"],
    )

    olivar = [row for row in dataset if row["cultivo"] == "olivar"]
    ml_by_date = {str(row["fecha"]): row for row in ml_rows}
    comparison_rows: list[dict[str, object]] = []
    for row in olivar:
        ml = ml_by_date.get(row["fecha"])
        if not ml:
            continue
        comparison_rows.append(
            {
                "fecha": row["fecha"],
                "et0_mm": row["et0_mm"],
                "riego_agronomico_mm": row["riego_bruto_mm"],
                "riego_ml_mm": ml["riego_ml_mm"],
                "litros_agronomico": row["litros_totales"],
                "litros_ml": ml["litros_ml"],
            }
        )
    write_csv(
        TABLE_DIR / "olivar_agronomico_vs_ml.csv",
        comparison_rows,
        ["fecha", "et0_mm", "riego_agronomico_mm", "riego_ml_mm", "litros_agronomico", "litros_ml"],
    )

    metrics_rows = load_metrics()
    write_csv(
        TABLE_DIR / "metricas_modelos.csv",
        metrics_rows,
        ["modelo", "target", "mae_mm", "rmse_mm", "r2", "filas_validacion"],
    )


def style_axes(ax) -> None:
    ax.grid(axis="y", color="#D9DED7", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#A8B3A4")
    ax.spines["bottom"].set_color("#A8B3A4")


def save_dataset_by_crop_chart(dataset: list[dict[str, str]]) -> None:
    crops = ["olivar", "citricos", "almendro"]
    values = []
    for crop in crops:
        rows = [row for row in dataset if row["cultivo"] == crop]
        values.append(sum(float(row["riego_bruto_mm"]) for row in rows) / len(rows))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(["Olivar", "Citricos", "Almendro"], values, color=["#2E6B45", "#D5A23D", "#8C6B4A"])
    ax.set_title("Riego medio diario aprendido por cultivo", fontsize=13, weight="bold")
    ax.set_ylabel(u("Riego bruto medio (mm/d\\u00eda)"))
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(GRAPH_DIR / "01_riego_medio_por_cultivo.png", dpi=160)
    plt.close(fig)


def save_olivar_series_chart(dataset: list[dict[str, str]], ml_rows: list[dict[str, float | str]]) -> None:
    olivar = [row for row in dataset if row["cultivo"] == "olivar"]
    ml_by_date = {row["fecha"]: row for row in ml_rows}
    dates = [row["fecha"][5:] for row in olivar]
    et0 = [float(row["et0_mm"]) for row in olivar]
    agr = [float(row["riego_bruto_mm"]) for row in olivar]
    ml = [float(ml_by_date[row["fecha"]]["riego_ml_mm"]) for row in olivar]

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(dates, et0, marker="o", color="#6F8FA6", label="ET0")
    ax.plot(dates, agr, marker="o", color="#2E6B45", label="Riego agronomico")
    ax.plot(dates, ml, marker="o", linestyle="--", color="#D5A23D", label="Prediccion ML")
    ax.set_title(u("Olivar: ET0, c\\u00e1lculo agron\\u00f3mico y predicci\\u00f3n ML"), fontsize=13, weight="bold")
    ax.set_ylabel(u("mm/d\\u00eda"))
    ax.legend(frameon=False)
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(GRAPH_DIR / "02_olivar_et0_agronomico_ml.png", dpi=160)
    plt.close(fig)


def save_liters_comparison_chart(dataset: list[dict[str, str]], ml_rows: list[dict[str, float | str]]) -> None:
    olivar = [row for row in dataset if row["cultivo"] == "olivar"]
    ml_by_date = {row["fecha"]: row for row in ml_rows}
    dates = [row["fecha"][5:] for row in olivar]
    agr = [float(row["litros_totales"]) for row in olivar]
    ml = [float(ml_by_date[row["fecha"]]["litros_ml"]) for row in olivar]

    fig, ax = plt.subplots(figsize=(9, 4.8))
    x = list(range(len(dates)))
    width = 0.38
    ax.bar([i - width / 2 for i in x], agr, width=width, color="#2E6B45", label=u("Agron\\u00f3mico"))
    ax.bar([i + width / 2 for i in x], ml, width=width, color="#D5A23D", label="ML")
    ax.set_xticks(x)
    ax.set_xticklabels(dates)
    ax.set_title(u("Comparaci\\u00f3n diaria de litros: c\\u00e1lculo base vs ML"), fontsize=13, weight="bold")
    ax.set_ylabel(u("Litros/d\\u00eda"))
    ax.legend(frameon=False)
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(GRAPH_DIR / "03_litros_agronomico_vs_ml.png", dpi=160)
    plt.close(fig)


def save_metrics_chart() -> None:
    metrics = load_metrics()
    labels = [str(row["modelo"]) for row in metrics]
    mae = [float(row["mae_mm"]) for row in metrics]
    rmse = [float(row["rmse_mm"]) for row in metrics]
    r2 = [float(row["r2"]) for row in metrics]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    x = list(range(len(labels)))
    axes[0].bar([i - 0.18 for i in x], mae, width=0.35, color="#2E6B45", label="MAE")
    axes[0].bar([i + 0.18 for i in x], rmse, width=0.35, color="#D5A23D", label="RMSE")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels)
    axes[0].set_ylabel("Error (mm)")
    axes[0].set_title("Error del modelo")
    axes[0].legend(frameon=False)
    style_axes(axes[0])

    axes[1].bar(labels, r2, color="#6F8FA6")
    axes[1].set_ylim(0, 1.05)
    axes[1].set_ylabel("R2")
    axes[1].set_title(u("Ajuste de regresi\\u00f3n"))
    style_axes(axes[1])

    fig.suptitle(u("M\\u00e9tricas de validaci\\u00f3n ML"), fontsize=13, weight="bold")
    fig.tight_layout()
    fig.savefig(GRAPH_DIR / "04_metricas_modelos.png", dpi=160)
    plt.close(fig)


def main() -> None:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    dataset = read_csv(DATASET)
    ml_rows = parse_ml_daily_table(PREDICTION_MD)
    build_summary_tables(dataset, ml_rows)
    save_dataset_by_crop_chart(dataset)
    save_olivar_series_chart(dataset, ml_rows)
    save_liters_comparison_chart(dataset, ml_rows)
    save_metrics_chart()
    print(f"Evidencias ML generadas en {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
