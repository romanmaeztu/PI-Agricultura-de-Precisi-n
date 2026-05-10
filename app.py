from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

from irrigation_advisor.aemet_client import AemetClient
from irrigation_advisor.cli import (
    build_single_crop_report,
    recommendation_to_dict,
    recommendation_to_markdown,
    resolve_station_from_args,
    weather_days_from_export,
)
from irrigation_advisor.ml import predict_irrigation_with_model
from irrigation_advisor.models import CROP_DEFAULTS, SOIL_DEFAULTS


DEFAULT_WEATHER_FILE = "data/resultados/comparativa_aemet_sevilla.csv"
DEFAULT_MODEL_DIR = "models/riego_predictivo"


def main() -> None:
    st.set_page_config(
        page_title="Recomendacion de riego",
        layout="wide",
    )

    st.title("Recomendacion de riego")

    with st.form("recommendation_form"):
        source = st.radio(
            "Datos climaticos",
            ["CSV local", "AEMET API"],
            horizontal=True,
            index=0 if Path(DEFAULT_WEATHER_FILE).exists() else 1,
        )

        location_col, date_col = st.columns(2)
        with location_col:
            station = st.text_input("Indicativo AEMET", value="")
            province = st.text_input("Provincia", value="SEVILLA")
            station_name = st.text_input("Nombre de estacion", value="AEROPUERTO")
            weather_file = st.text_input(
                "CSV climatico",
                value=DEFAULT_WEATHER_FILE,
                disabled=source != "CSV local",
            )

        with date_col:
            start = st.date_input("Fecha inicial", value=date(2024, 5, 1))
            end = st.date_input("Fecha final", value=date(2024, 5, 7))
            crop = st.selectbox("Cultivo", options=sorted(CROP_DEFAULTS), index=sorted(CROP_DEFAULTS).index("olivar"))
            stage = st.selectbox("Fase", options=["inicio", "desarrollo", "media", "madurez"], index=2)

        plot_col, irrigation_col = st.columns(2)
        with plot_col:
            soil = st.selectbox("Suelo", options=sorted(SOIL_DEFAULTS), index=sorted(SOIL_DEFAULTS).index("franco"))
            area_m2 = st.number_input("Superficie (m2)", min_value=1.0, value=3500.0, step=100.0)
            current_soil_moisture = st.number_input(
                "Humedad inicial volumetrica",
                min_value=0.0,
                max_value=0.69,
                value=0.0,
                step=0.01,
            )
            use_current_moisture = st.checkbox("Calcular primer riego hasta capacidad de campo")

        with irrigation_col:
            irrigation_efficiency = st.slider("Eficiencia de riego", min_value=0.50, max_value=1.00, value=0.90, step=0.01)
            effective_rainfall_ratio = st.slider("Lluvia efectiva", min_value=0.00, max_value=1.00, value=0.80, step=0.05)
            emitters_per_plant = st.number_input("Goteros por planta", min_value=1, value=2, step=1)
            emitter_flow_lph = st.number_input("Caudal por gotero (L/h)", min_value=0.1, value=4.0, step=0.5)
            use_ml_prediction = st.checkbox("Usar modelo ML entrenado")
            ml_model_dir = st.text_input(
                "Directorio del modelo ML",
                value=DEFAULT_MODEL_DIR,
                disabled=not use_ml_prediction,
            )

        submitted = st.form_submit_button("Calcular recomendacion", type="primary")

    if submitted:
        args = build_args(
            station=station,
            province=province,
            station_name=station_name,
            start=start.isoformat(),
            end=end.isoformat(),
            crop=crop,
            stage=stage,
            soil=soil,
            area_m2=area_m2,
            irrigation_efficiency=irrigation_efficiency,
            effective_rainfall_ratio=effective_rainfall_ratio,
            current_soil_moisture=current_soil_moisture if use_current_moisture else None,
            emitters_per_plant=emitters_per_plant,
            emitter_flow_lph=emitter_flow_lph,
        )
        try:
            recommendation = calculate_recommendation(
                source=source,
                weather_file=weather_file,
                args=args,
                ml_model_dir=ml_model_dir if use_ml_prediction else None,
            )
        except Exception as exc:  # noqa: BLE001 - Streamlit should show user-facing errors.
            st.error(str(exc))
            return

        render_recommendation(recommendation)


def build_args(
    station: str,
    province: str,
    station_name: str,
    start: str,
    end: str,
    crop: str,
    stage: str,
    soil: str,
    area_m2: float,
    irrigation_efficiency: float,
    effective_rainfall_ratio: float,
    current_soil_moisture: float | None,
    emitters_per_plant: int,
    emitter_flow_lph: float,
) -> SimpleNamespace:
    return SimpleNamespace(
        station=station.strip() or None,
        province=province.strip() or None,
        station_name=station_name.strip() or None,
        start=start,
        end=end,
        latitude=None,
        crop=crop,
        stage=stage,
        kc=None,
        soil=soil,
        root_depth_m=None,
        field_capacity=None,
        wilting_point=None,
        max_depletion_fraction=None,
        area_m2=area_m2,
        irrigation_efficiency=irrigation_efficiency,
        effective_rainfall_ratio=effective_rainfall_ratio,
        current_soil_moisture=current_soil_moisture,
        plant_spacing_m2=None,
        emitters_per_plant=emitters_per_plant,
        emitter_flow_lph=emitter_flow_lph,
    )


def calculate_recommendation(
    source: str,
    weather_file: str,
    args: SimpleNamespace,
    ml_model_dir: str | None = None,
) -> dict:
    if date.fromisoformat(args.end) < date.fromisoformat(args.start):
        raise ValueError("La fecha final no puede ser anterior a la inicial")

    if source == "CSV local":
        weather_days, station_id, station_name, province = weather_days_from_export(
            input_file=weather_file,
            station_id=args.station,
            province=args.province,
            station_name=args.station_name,
            start=args.start,
            end=args.end,
        )
    else:
        client = AemetClient()
        station = resolve_station_from_args(client=client, args=args)
        station_id = station.indicativo
        station_name = station.nombre
        province = station.provincia
        weather_days = client.get_daily_climate(
            station_id=station_id,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
            latitude_deg=station.latitude_deg,
        )

    report = build_single_crop_report(args=args, weather_days=weather_days)
    recommendation = recommendation_to_dict(
        report=report,
        station_id=station_id,
        station_name=station_name,
        province=province,
        start=args.start,
        end=args.end,
    )
    if ml_model_dir:
        recommendation["ml_prediction"] = predict_irrigation_with_model(
            model_dir=ml_model_dir,
            weather_days=weather_days,
            args=args,
            station_id=station_id,
            station_name=station_name,
            province=province,
        )
    return recommendation


def render_recommendation(recommendation: dict) -> None:
    result = recommendation["recommendation"]
    plot = recommendation["plot"]
    climate = recommendation["climate"]

    metric_cols = st.columns(4)
    metric_cols[0].metric("Riego medio diario", f"{result['avg_liters_day']:,.0f} L/dia")
    metric_cols[1].metric("Tiempo medio", format_hours(result["avg_runtime_hours_day"]))
    metric_cols[2].metric("Litros por planta", format_liters(result["avg_liters_plant_day"]))
    metric_cols[3].metric("Lamina diaria", f"{result['avg_gross_mm_day']:.2f} mm")

    info_cols = st.columns(3)
    info_cols[0].metric("Superficie", f"{plot['area_m2']:,.0f} m2")
    info_cols[1].metric("ET0 media", f"{climate['et0_avg_mm_day']:.2f} mm/dia")
    info_cols[2].metric("Lluvia total", f"{climate['rain_total_mm']:.2f} mm")

    if "ml_prediction" in recommendation:
        render_ml_prediction(recommendation["ml_prediction"])

    st.subheader("Detalle diario")
    st.dataframe(recommendation["daily"], use_container_width=True, hide_index=True)

    report_markdown = recommendation_to_markdown(recommendation)
    st.download_button(
        "Descargar informe Markdown",
        data=report_markdown,
        file_name="recomendacion_riego.md",
        mime="text/markdown",
    )
    st.download_button(
        "Descargar informe JSON",
        data=json.dumps(recommendation, ensure_ascii=False, indent=2),
        file_name="recomendacion_riego.json",
        mime="application/json",
    )


def render_ml_prediction(ml_prediction: dict) -> None:
    st.subheader("Prediccion ML")
    summary = ml_prediction["summary"]
    model = ml_prediction["model"]
    cols = st.columns(4)
    cols[0].metric("Riego medio ML", f"{summary['avg_liters_day']:,.0f} L/dia")
    cols[1].metric("Tiempo medio ML", format_hours(summary["avg_runtime_hours_day"]))
    cols[2].metric("Litros/planta ML", format_liters(summary["avg_liters_plant_day"]))
    cols[3].metric("Lamina ML", f"{summary['avg_gross_mm_day']:.2f} mm")

    metrics = model.get("metrics") or {}
    if metrics:
        st.caption(
            "Modelo {model_type}. MAE {mae} mm; RMSE {rmse} mm; R2 {r2}.".format(
                model_type=model["model_type"],
                mae=format_optional_metric(metrics.get("mae_mm")),
                rmse=format_optional_metric(metrics.get("rmse_mm")),
                r2=format_optional_metric(metrics.get("r2")),
            )
        )
    st.dataframe(ml_prediction["daily"], use_container_width=True, hide_index=True)


def format_hours(value: float | None) -> str:
    if value is None:
        return "N/D"
    return f"{value:.2f} h/dia"


def format_liters(value: float | None) -> str:
    if value is None:
        return "N/D"
    return f"{value:.2f} L/planta/dia"


def format_optional_metric(value: object) -> str:
    if value is None:
        return "N/D"
    return str(value)


if __name__ == "__main__":
    main()
