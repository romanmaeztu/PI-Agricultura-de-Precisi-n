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
from irrigation_advisor.models import CROP_DEFAULTS
from irrigation_advisor.weather_cache import AemetCache, DEFAULT_CACHE_DB


DEFAULT_WEATHER_FILE = "data/demo/aemet_sevilla_mayo_2024.csv"
DEFAULT_MODEL_DIR = "models/riego_predictivo"
DEFAULT_CACHE_FILE = DEFAULT_CACHE_DB
ALL_PROVINCES = "Todas las provincias"


def main() -> None:
    st.set_page_config(
        page_title="Recomendacion de riego",
        layout="wide",
    )

    st.title("Recomendacion de riego")

    source_options = ["Cache local", "CSV local", "AEMET API"]
    source_index = 1 if Path(DEFAULT_WEATHER_FILE).exists() else (0 if Path(DEFAULT_CACHE_FILE).exists() else 2)
    source = st.radio(
        "Datos climaticos",
        source_options,
        horizontal=True,
        index=source_index,
    )

    station = ""
    province = "SEVILLA"
    station_name = "AEROPUERTO"
    if source in {"Cache local", "AEMET API"}:
        station, province, station_name = render_station_selector(source=source)

    with st.form("recommendation_form"):
        location_col, date_col = st.columns(2)
        with location_col:
            if source == "CSV local":
                station = st.text_input("Indicativo AEMET", value="")
                province = st.text_input("Provincia", value="SEVILLA")
                station_name = st.text_input("Nombre de estacion", value="AEROPUERTO")
            else:
                st.text_input("Indicativo AEMET", value=station, disabled=True)
                st.text_input("Provincia", value=province, disabled=True)
                st.text_input("Nombre de estacion", value=station_name, disabled=True)
            cache_file = st.text_input(
                "Cache SQLite",
                value=DEFAULT_CACHE_FILE,
                disabled=source != "Cache local",
            )
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
            area_m2 = st.number_input("Superficie (m2)", min_value=1.0, value=3500.0, step=100.0)

        with irrigation_col:
            irrigation_efficiency = st.slider("Eficiencia de riego", min_value=0.50, max_value=1.00, value=0.90, step=0.01)
            effective_rainfall_ratio = st.slider("Lluvia efectiva", min_value=0.00, max_value=1.00, value=0.80, step=0.05)
            use_ml_prediction = st.checkbox("Usar modelo ML entrenado", value=True)
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
            area_m2=area_m2,
            irrigation_efficiency=irrigation_efficiency,
            effective_rainfall_ratio=effective_rainfall_ratio,
        )
        try:
            recommendation = calculate_recommendation(
                source=source,
                weather_file=weather_file,
                cache_file=cache_file,
                args=args,
                ml_model_dir=ml_model_dir if use_ml_prediction else None,
            )
        except Exception as exc:  # noqa: BLE001 - Streamlit should show user-facing errors.
            st.error(str(exc))
            return

        render_recommendation(recommendation)


def render_station_selector(source: str) -> tuple[str, str, str]:
    try:
        stations = load_cached_station_inventory() if source == "Cache local" else load_aemet_station_inventory()
    except Exception as exc:  # noqa: BLE001 - Streamlit should keep a manual fallback.
        st.warning(f"No se pudo cargar el inventario de estaciones: {exc}")
        station = st.text_input("Indicativo AEMET", value="")
        province = st.text_input("Provincia", value="SEVILLA")
        station_name = st.text_input("Nombre de estacion", value="AEROPUERTO")
        return station, province, station_name
    if not stations:
        st.warning("La cache local no contiene estaciones. Ejecuta sync-aemet-cache antes de usar este modo.")
        station = st.text_input("Indicativo AEMET", value="")
        province = st.text_input("Provincia", value="SEVILLA")
        station_name = st.text_input("Nombre de estacion", value="AEROPUERTO")
        return station, province, station_name

    provinces = [ALL_PROVINCES] + sorted({item["provincia"] for item in stations if item["provincia"]})
    province = st.selectbox(
        "Provincia",
        options=provinces,
        index=province_default_index(provinces, preferred=ALL_PROVINCES),
    )
    filtered_stations = filter_station_options(stations=stations, province=province)
    station_by_label = {station_option_label(item): item for item in filtered_stations}
    selected_label = st.selectbox(
        "Estacion AEMET",
        options=list(station_by_label),
        index=station_default_index(list(station_by_label), preferred="SEVILLA AEROPUERTO"),
    )
    selected_station = station_by_label[selected_label]
    st.caption(f"Indicativo: {selected_station['indicativo']}")
    return (
        selected_station["indicativo"],
        selected_station["provincia"],
        selected_station["nombre"],
    )


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def load_aemet_station_inventory() -> list[dict[str, str | float | None]]:
    client = AemetClient()
    return [
        {
            "indicativo": station.indicativo,
            "nombre": station.nombre,
            "provincia": station.provincia,
            "latitude_deg": station.latitude_deg,
            "longitude_deg": station.longitude_deg,
        }
        for station in client.get_station_inventory()
    ]


@st.cache_data(ttl=5 * 60, show_spinner=False)
def load_cached_station_inventory() -> list[dict[str, str | float | None]]:
    cache = AemetCache(DEFAULT_CACHE_FILE)
    return [
        {
            "indicativo": station.indicativo,
            "nombre": station.nombre,
            "provincia": station.provincia,
            "latitude_deg": station.latitude_deg,
            "longitude_deg": station.longitude_deg,
        }
        for station in cache.get_stations()
    ]


def filter_station_options(
    stations: list[dict[str, str | float | None]],
    province: str,
) -> list[dict[str, str | float | None]]:
    if province == ALL_PROVINCES:
        return sorted(stations, key=station_sort_key)
    return sorted(
        [station for station in stations if station["provincia"] == province],
        key=station_sort_key,
    )


def station_option_label(station: dict[str, str | float | None]) -> str:
    return "{provincia} | {nombre} | {indicativo}".format(
        provincia=station["provincia"] or "N/D",
        nombre=station["nombre"] or "N/D",
        indicativo=station["indicativo"] or "N/D",
    )


def station_sort_key(station: dict[str, str | float | None]) -> tuple[str, str, str]:
    return (
        str(station["provincia"] or ""),
        str(station["nombre"] or ""),
        str(station["indicativo"] or ""),
    )


def province_default_index(provinces: list[str], preferred: str) -> int:
    return provinces.index(preferred) if preferred in provinces else 0


def station_default_index(labels: list[str], preferred: str) -> int:
    for index, label in enumerate(labels):
        if preferred in label:
            return index
    return 0


def build_args(
    station: str,
    province: str,
    station_name: str,
    start: str,
    end: str,
    crop: str,
    stage: str,
    area_m2: float,
    irrigation_efficiency: float,
    effective_rainfall_ratio: float,
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
        area_m2=area_m2,
        irrigation_efficiency=irrigation_efficiency,
        effective_rainfall_ratio=effective_rainfall_ratio,
        plant_spacing_m2=None,
    )


def calculate_recommendation(
    source: str,
    weather_file: str,
    cache_file: str,
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
    elif source == "Cache local":
        cache = AemetCache(cache_file)
        station = resolve_station_from_args(client=cache, args=args)
        source_data = cache.get_weather_source(
            station_id=station.indicativo,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
        )
        weather_days = source_data.weather_days
        station_id = source_data.station_id
        station_name = source_data.station_name
        province = source_data.province
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
    metric_cols[0].metric("Riego total", f"{result['total_liters']:,.0f} L")
    metric_cols[0].caption("Agua total para toda la parcela en el periodo seleccionado.")
    metric_cols[1].metric("Riego medio diario", f"{result['avg_liters_day']:,.0f} L/dia")
    metric_cols[1].caption("Media diaria para toda la parcela.")
    metric_cols[2].metric("Litros por planta", format_liters(result["avg_liters_plant_day"]))
    metric_cols[2].caption("Media diaria por planta segun el marco del cultivo.")
    metric_cols[3].metric("Lamina diaria", f"{result['avg_gross_mm_day']:.2f} mm")
    metric_cols[3].caption("Profundidad media diaria de riego. 1 mm equivale a 1 L/m2.")

    info_cols = st.columns(3)
    info_cols[0].metric("Superficie", f"{plot['area_m2']:,.0f} m2")
    info_cols[0].caption("Dimension de la parcela usada para convertir mm a litros.")
    info_cols[1].metric("ET0 media", f"{climate['et0_avg_mm_day']:.2f} mm/dia")
    info_cols[1].caption("Evapotranspiracion de referencia media del periodo.")
    info_cols[2].metric("Lluvia total", f"{climate['rain_total_mm']:.2f} mm")
    info_cols[2].caption("Precipitacion acumulada del periodo seleccionado.")

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
    cols[0].metric("Riego total ML", f"{summary['total_liters']:,.0f} L")
    cols[0].caption("Prediccion total para toda la parcela en el periodo.")
    cols[1].metric("Riego medio ML", f"{summary['avg_liters_day']:,.0f} L/dia")
    cols[1].caption("Prediccion media diaria para toda la parcela.")
    cols[2].metric("Litros/planta ML", format_liters(summary["avg_liters_plant_day"]))
    cols[2].caption("Prediccion media diaria por planta.")
    cols[3].metric("Lamina ML", f"{summary['avg_gross_mm_day']:.2f} mm")
    cols[3].caption("Lamina media diaria predicha por el modelo.")

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


def format_liters(value: float | None) -> str:
    if value is None:
        return "N/D"
    return f"{value:.2f} L/planta"


def format_optional_metric(value: object) -> str:
    if value is None:
        return "N/D"
    return str(value)


if __name__ == "__main__":
    main()
