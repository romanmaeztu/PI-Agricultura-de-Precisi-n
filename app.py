from __future__ import annotations

import json
from datetime import date
from html import escape
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import streamlit as st

from irrigation_advisor.aemet_client import AemetClient
from irrigation_advisor.cli import (
    build_single_crop_report,
    recommendation_to_dict,
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
STAGE_LABELS = {
    "inicio": "Inicio",
    "desarrollo": "Desarrollo",
    "media": "Fase media",
    "madurez": "Madurez",
}
CROP_LABELS = {
    "almendro": "Almendro",
    "citricos": "Cítricos",
    "olivar": "Olivar",
}


def main() -> None:
    st.set_page_config(
        page_title="Riego predictivo",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_theme()
    render_hero()
    st.session_state.setdefault("last_recommendation", None)

    st.markdown('<div class="section-kicker">Configuración del escenario</div>', unsafe_allow_html=True)
    source_options = ["Cache local", "CSV local", "AEMET API"]
    source_index = 1 if Path(DEFAULT_WEATHER_FILE).exists() else (0 if Path(DEFAULT_CACHE_FILE).exists() else 2)
    station = ""
    province = "SEVILLA"
    station_name = "AEROPUERTO"
    with st.expander("Origen de datos y estación meteorológica", expanded=False):
        source = st.radio(
            "Datos climáticos",
            source_options,
            horizontal=True,
            index=source_index,
            help="La demo estable usa CSV local; la cache local evita nuevas peticiones y la API consulta AEMET directamente.",
        )
        if source in {"Cache local", "AEMET API"}:
            station, province, station_name = render_station_selector(source=source)
        else:
            st.info("Modo de demostración estable con CSV local versionado.")

    with st.form("recommendation_form"):
        st.markdown("### Parcela y cultivo")
        location_col, date_col, crop_col = st.columns([1.1, 1, 1])
        with location_col:
            if source == "CSV local":
                province = st.text_input("Provincia", value="SEVILLA", key="csv_province")
                station_name = st.text_input("Zona o estación de referencia", value="AEROPUERTO", key="csv_station_name")
            else:
                st.text_input(
                    "Estación seleccionada",
                    value=f"{province} | {station_name}",
                    disabled=True,
                    key="selected_station_display",
                )
            area_m2 = st.number_input(
                "Superficie de la parcela (m²)",
                min_value=1.0,
                value=3500.0,
                step=100.0,
                help="Tamaño total sobre el que se convierte la lámina de riego en litros.",
            )

        with date_col:
            start = st.date_input("Fecha inicial", value=date(2024, 5, 1))
            end = st.date_input("Fecha final", value=date(2024, 5, 7))

        with crop_col:
            crop_options = sorted(CROP_DEFAULTS)
            crop = st.selectbox(
                "Cultivo",
                options=crop_options,
                index=crop_options.index("olivar"),
                format_func=lambda value: CROP_LABELS.get(value, value.title()),
            )
            stage_options = list(STAGE_LABELS)
            stage = st.selectbox(
                "Fase del cultivo",
                options=stage_options,
                index=stage_options.index("media"),
                format_func=lambda value: STAGE_LABELS[value],
            )

        st.markdown(
            '<div class="form-note">El cálculo principal se basa en localización, fechas, cultivo, fase y superficie. Los parámetros técnicos quedan agrupados debajo.</div>',
            unsafe_allow_html=True,
        )

        cache_file = DEFAULT_CACHE_FILE
        weather_file = DEFAULT_WEATHER_FILE
        irrigation_efficiency = 0.90
        effective_rainfall_ratio = 0.80
        use_ml_prediction = True
        ml_model_dir = DEFAULT_MODEL_DIR

        with st.expander("Configuración avanzada del cálculo", expanded=False):
            data_col, irrigation_col, ml_col = st.columns(3)
            with data_col:
                station = st.text_input(
                    "Indicativo AEMET",
                    value=station,
                    disabled=source != "CSV local",
                    help="Código técnico de la estación meteorológica.",
                )
                cache_file = st.text_input(
                    "Cache SQLite",
                    value=DEFAULT_CACHE_FILE,
                    disabled=source != "Cache local",
                )
                weather_file = st.text_input(
                    "CSV climático",
                    value=DEFAULT_WEATHER_FILE,
                    disabled=source != "CSV local",
                )
            with irrigation_col:
                irrigation_efficiency = st.slider(
                    "Eficiencia de riego",
                    min_value=0.50,
                    max_value=1.00,
                    value=0.90,
                    step=0.01,
                    help="Porcentaje del agua aplicada que se considera aprovechable por el cultivo.",
                )
                effective_rainfall_ratio = st.slider(
                    "Lluvia efectiva",
                    min_value=0.00,
                    max_value=1.00,
                    value=0.80,
                    step=0.05,
                    help="Parte de la lluvia que se descuenta de la necesidad de riego.",
                )
            with ml_col:
                use_ml_prediction = st.checkbox("Usar modelo ML entrenado", value=True)
                ml_model_dir = st.text_input(
                    "Directorio del modelo ML",
                    value=DEFAULT_MODEL_DIR,
                    disabled=not use_ml_prediction,
                )

        submitted = st.form_submit_button(
            "Calcular recomendación de riego",
            type="primary",
            use_container_width=True,
        )

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

        st.session_state["last_recommendation"] = recommendation

    if st.session_state["last_recommendation"] is None:
        render_empty_state()
    else:
        render_recommendation(st.session_state["last_recommendation"])


def hero_background_data_uri() -> str:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 420">
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#123225"/>
          <stop offset="1" stop-color="#2f6b45"/>
        </linearGradient>
        <linearGradient id="field" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#5b7f37"/>
          <stop offset="1" stop-color="#98b65f"/>
        </linearGradient>
      </defs>
      <rect width="1280" height="420" fill="url(#sky)"/>
      <circle cx="1060" cy="80" r="74" fill="#e1b64a" opacity="0.75"/>
      <path d="M0 250 C240 210 420 265 650 230 C860 198 1050 228 1280 190 L1280 420 L0 420 Z" fill="url(#field)"/>
      <path d="M0 305 C220 276 420 320 640 292 C840 265 1050 292 1280 260" fill="none" stroke="#dfe8b8" stroke-width="10" opacity="0.45"/>
      <path d="M0 350 C240 330 420 375 640 342 C840 315 1050 346 1280 318" fill="none" stroke="#2f5e88" stroke-width="8" opacity="0.55"/>
      <g opacity="0.42" stroke="#e7f0c7" stroke-width="2">
        <path d="M115 420 L380 244"/>
        <path d="M265 420 L505 238"/>
        <path d="M430 420 L650 230"/>
        <path d="M595 420 L808 220"/>
        <path d="M770 420 L970 218"/>
        <path d="M940 420 L1122 214"/>
      </g>
    </svg>
    """
    return f"data:image/svg+xml,{quote(svg)}"


def apply_theme() -> None:
    hero_bg = hero_background_data_uri()
    st.markdown(
        f"""
        <style>
        :root {{
            --bg: #f6f3ea;
            --panel: #ffffff;
            --ink: #14202a;
            --muted: #5d6b63;
            --green: #2e6b45;
            --blue: #2f5e88;
            --orange: #c4622d;
            --gold: #d8a23a;
            --line: #d5ddcf;
        }}
        .stApp {{
            background: var(--bg);
            color: var(--ink);
        }}
        .block-container {{
            padding-top: 1.25rem;
            padding-bottom: 3rem;
            max-width: 1180px;
        }}
        .hero-irrigation {{
            min-height: 250px;
            border-radius: 18px;
            background-image:
                linear-gradient(90deg, rgba(13, 19, 33, 0.92), rgba(13, 19, 33, 0.60), rgba(46, 107, 69, 0.18)),
                url("{hero_bg}");
            background-size: cover;
            background-position: center;
            color: white;
            padding: 34px 40px;
            margin-bottom: 26px;
            box-shadow: 0 18px 45px rgba(20, 32, 42, 0.18);
        }}
        .hero-irrigation h1 {{
            margin: 0;
            max-width: 760px;
            font-size: clamp(2.1rem, 4vw, 3.7rem);
            line-height: 1.02;
            letter-spacing: 0;
        }}
        .hero-irrigation p {{
            max-width: 650px;
            margin: 18px 0 0;
            font-size: 1.05rem;
            color: #ecf5e8;
        }}
        .eyebrow {{
            margin-bottom: 14px;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0;
            color: #d8e9bf;
            text-transform: uppercase;
        }}
        .badge-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 26px;
        }}
        .badge {{
            padding: 8px 12px;
            border: 1px solid rgba(255,255,255,.30);
            background: rgba(255,255,255,.12);
            color: white;
            border-radius: 999px;
            font-size: .82rem;
            font-weight: 700;
        }}
        .section-kicker {{
            color: var(--green);
            font-weight: 800;
            font-size: .82rem;
            text-transform: uppercase;
            margin: 4px 0 10px;
        }}
        .form-note, .result-note {{
            background: #eef4ef;
            border-left: 4px solid var(--green);
            padding: 14px 16px;
            color: var(--ink);
            margin: 14px 0 10px;
            border-radius: 8px;
        }}
        .empty-state {{
            margin-top: 22px;
            padding: 24px 28px;
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 14px;
            color: var(--muted);
        }}
        .result-heading {{
            margin: 28px 0 14px;
        }}
        .result-heading h2 {{
            margin: 0;
            color: var(--ink);
            font-size: 1.8rem;
        }}
        .result-heading p {{
            margin: 6px 0 0;
            color: var(--muted);
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin: 16px 0 18px;
        }}
        .metric-card {{
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 18px 18px 16px;
            min-height: 132px;
        }}
        .metric-card strong {{
            display: block;
            color: var(--green);
            font-size: .78rem;
            text-transform: uppercase;
            margin-bottom: 10px;
        }}
        .metric-card .value {{
            color: var(--ink);
            font-size: 1.85rem;
            line-height: 1.08;
            font-weight: 800;
        }}
        .metric-card span {{
            display: block;
            margin-top: 10px;
            color: var(--muted);
            font-size: .84rem;
            line-height: 1.35;
        }}
        .context-strip {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin: 10px 0 20px;
        }}
        .context-item {{
            background: #edf2ea;
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 12px 14px;
        }}
        .context-item b {{
            display: block;
            color: var(--muted);
            font-size: .76rem;
            text-transform: uppercase;
            margin-bottom: 5px;
        }}
        .context-item span {{
            color: var(--ink);
            font-weight: 750;
        }}
        .ml-box {{
            border: 1px solid #d9e4d6;
            background: linear-gradient(135deg, #ffffff, #eef4ef);
            border-radius: 16px;
            padding: 18px;
            margin-top: 16px;
        }}
        div[data-testid="stForm"] {{
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 22px 24px 18px;
            box-shadow: 0 12px 34px rgba(20, 32, 42, 0.08);
        }}
        div[data-testid="stExpander"] {{
            border-color: var(--line);
            border-radius: 12px;
            background: rgba(255,255,255,.72);
        }}
        .stButton > button, .stDownloadButton > button {{
            border-radius: 10px;
            font-weight: 800;
        }}
        .stButton > button[kind="primary"],
        div[data-testid="stFormSubmitButton"] button {{
            background: var(--green);
            border-color: var(--green);
            color: #ffffff;
        }}
        .stButton > button[kind="primary"]:hover,
        div[data-testid="stFormSubmitButton"] button:hover {{
            background: #245739;
            border-color: #245739;
            color: #ffffff;
        }}
        @media (max-width: 900px) {{
            .metric-grid, .context-strip {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
        }}
        @media (max-width: 640px) {{
            .hero-irrigation {{
                padding: 26px 22px;
            }}
            .metric-grid, .context-strip {{
                grid-template-columns: 1fr;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <section class="hero-irrigation">
            <div class="eyebrow">Agricultura de precisión</div>
            <h1>Recomendación predictiva de riego para parcelas agrícolas</h1>
            <p>Estimación de agua por localización, cultivo, fechas y superficie usando datos meteorológicos oficiales y una capa de Machine Learning.</p>
            <div class="badge-row">
                <div class="badge">AEMET</div>
                <div class="badge">Olivar</div>
                <div class="badge">Cítricos</div>
                <div class="badge">Almendro</div>
                <div class="badge">ML</div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state() -> None:
    st.markdown(
        """
        <div class="empty-state">
            Selecciona una parcela, un cultivo y un periodo. La recomendación aparecerá como litros totales, litros diarios, litros por planta y lámina media de riego.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_station_selector(source: str) -> tuple[str, str, str]:
    try:
        stations = load_cached_station_inventory() if source == "Cache local" else load_aemet_station_inventory()
    except Exception as exc:  # noqa: BLE001 - Streamlit should keep a manual fallback.
        st.warning(f"No se pudo cargar el inventario de estaciones: {exc}")
        station = st.text_input("Indicativo AEMET", value="")
        province = st.text_input("Provincia", value="SEVILLA")
        station_name = st.text_input("Nombre de estación", value="AEROPUERTO")
        return station, province, station_name
    if not stations:
        st.warning("La cache local no contiene estaciones. Ejecuta sync-aemet-cache antes de usar este modo.")
        station = st.text_input("Indicativo AEMET", value="")
        province = st.text_input("Provincia", value="SEVILLA")
        station_name = st.text_input("Nombre de estación", value="AEROPUERTO")
        return station, province, station_name

    provinces = [ALL_PROVINCES] + sorted({item["provincia"] for item in stations if item["provincia"]})
    province = st.selectbox(
        "Provincia de la estación",
        options=provinces,
        index=province_default_index(provinces, preferred=ALL_PROVINCES),
        key="station_province_filter",
    )
    filtered_stations = filter_station_options(stations=stations, province=province)
    station_by_label = {station_option_label(item): item for item in filtered_stations}
    selected_label = st.selectbox(
        "Estación meteorológica AEMET",
        options=list(station_by_label),
        index=station_default_index(list(station_by_label), preferred="SEVILLA AEROPUERTO"),
        key="station_selector",
    )
    selected_station = station_by_label[selected_label]
    st.caption(f"Estación seleccionada: {selected_station['nombre']} ({selected_station['indicativo']})")
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
    location = recommendation["location"]
    period = recommendation["period"]

    render_result_header(location=location, plot=plot, period=period)
    render_context_strip(
        [
            ("Cultivo", f"{format_crop(plot['crop'])} · {format_stage(plot['stage'])}"),
            ("Periodo", f"{period['start']} a {period['end']}"),
            ("Superficie", f"{plot['area_m2']:,.0f} m²"),
            ("Estación", location.get("station_name") or location.get("station") or "N/D"),
        ]
    )
    render_metric_cards(
        [
            (
                "Riego total",
                f"{result['total_liters']:,.0f} L",
                "Agua total para toda la parcela en el periodo seleccionado.",
            ),
            (
                "Riego medio diario",
                f"{result['avg_liters_day']:,.0f} L/día",
                "Media diaria para toda la parcela.",
            ),
            (
                "Litros por planta",
                format_liters(result["avg_liters_plant_day"]),
                "Media diaria por planta según el marco del cultivo.",
            ),
            (
                "Lámina diaria",
                f"{result['avg_gross_mm_day']:.2f} mm/día",
                "Profundidad media diaria. 1 mm equivale a 1 L/m².",
            ),
        ]
    )
    render_metric_cards(
        [
            ("ET0 media", f"{climate['et0_avg_mm_day']:.2f} mm/día", "Demanda atmosférica media del periodo."),
            ("Lluvia total", f"{climate['rain_total_mm']:.2f} mm", "Precipitación acumulada."),
            ("ETc media", f"{result['avg_etc_mm_day']:.2f} mm/día", "Consumo estimado del cultivo."),
            (
                "Plantas estimadas",
                format_optional_number(plot.get("plants_estimated")),
                "Estimación según marco medio del cultivo.",
            ),
        ]
    )

    if "ml_prediction" in recommendation:
        render_ml_prediction(recommendation["ml_prediction"])

    report_markdown = clean_report_markdown(recommendation)
    report_json = json.dumps(clean_report_dict(recommendation), ensure_ascii=False, indent=2)
    download_col_a, download_col_b = st.columns(2)
    with download_col_a:
        st.download_button(
            "Descargar informe Markdown",
            data=report_markdown,
            file_name="recomendacion_riego.md",
            mime="text/markdown",
            on_click="ignore",
            use_container_width=True,
        )
    with download_col_b:
        st.download_button(
            "Descargar informe JSON",
            data=report_json,
            file_name="recomendacion_riego.json",
            mime="application/json",
            on_click="ignore",
            use_container_width=True,
        )


def render_ml_prediction(ml_prediction: dict) -> None:
    summary = ml_prediction["summary"]
    st.markdown("### Predicción ML")
    render_metric_cards(
        [
            ("Riego total ML", f"{summary['total_liters']:,.0f} L", "Predicción total para toda la parcela."),
            ("Riego medio ML", f"{summary['avg_liters_day']:,.0f} L/día", "Predicción media diaria."),
            ("Litros/planta ML", format_liters(summary["avg_liters_plant_day"]), "Predicción media diaria por planta."),
            ("Lámina ML", f"{summary['avg_gross_mm_day']:.2f} mm/día", "Lámina media diaria predicha."),
        ]
    )


def render_result_header(location: dict, plot: dict, period: dict) -> None:
    station_name = location.get("station_name") or location.get("station") or "N/D"
    province = location.get("province") or "N/D"
    crop = format_crop(plot["crop"])
    st.markdown(
        f"""
        <div class="result-heading">
            <h2>Recomendación para {escape(crop)} en {escape(str(province))}</h2>
            <p>{escape(str(station_name))} · {escape(str(period["days"]))} días calculados</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_cards(cards: list[tuple[str, str, str]]) -> None:
    html = ['<div class="metric-grid">']
    for title, value, note in cards:
        html.append(
            '<div class="metric-card">'
            "<strong>{title}</strong>"
            '<div class="value">{value}</div>'
            "<span>{note}</span>"
            "</div>".format(
                title=escape(title),
                value=escape(value),
                note=escape(note),
            )
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def render_context_strip(items: list[tuple[str, str]]) -> None:
    html = ['<div class="context-strip">']
    for title, value in items:
        html.append(
            '<div class="context-item">'
            "<b>{title}</b>"
            "<span>{value}</span>"
            "</div>".format(title=escape(title), value=escape(value))
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def clean_report_dict(recommendation: dict) -> dict:
    report = {
        "servicio": "recomendacion_riego",
        "localizacion": recommendation["location"],
        "periodo": recommendation["period"],
        "parcela": recommendation["plot"],
        "clima": recommendation["climate"],
        "recomendacion": recommendation["recommendation"],
        "metodo": recommendation["method"],
    }
    if "ml_prediction" in recommendation:
        report["prediccion_ml"] = {
            "resumen": recommendation["ml_prediction"]["summary"],
            "nota": recommendation["ml_prediction"].get("note"),
        }
    return report


def clean_report_markdown(recommendation: dict) -> str:
    clean = clean_report_dict(recommendation)
    location = clean["localizacion"]
    period = clean["periodo"]
    plot = clean["parcela"]
    climate = clean["clima"]
    result = clean["recomendacion"]
    lines = [
        "# Informe de recomendación de riego",
        "",
        "## Escenario",
        f"- Localización: {location.get('province') or 'N/D'} - {location.get('station_name') or location.get('station') or 'N/D'}",
        f"- Periodo: {period['start']} a {period['end']} ({period['days']} días)",
        f"- Cultivo: {format_crop(plot['crop'])} ({format_stage(plot['stage'])})",
        f"- Superficie: {plot['area_m2']:,.0f} m²",
        "",
        "## Recomendación principal",
        f"- Riego total del periodo: {result['total_liters']:,.0f} L",
        f"- Riego medio diario: {result['avg_liters_day']:,.0f} L/día",
        f"- Litros por planta: {format_liters(result['avg_liters_plant_day'])}/día",
        f"- Lámina diaria: {result['avg_gross_mm_day']:.2f} mm/día",
        "",
        "## Datos climáticos resumen",
        f"- ET0 media: {climate['et0_avg_mm_day']:.2f} mm/día",
        f"- ETc media del cultivo: {result['avg_etc_mm_day']:.2f} mm/día",
        f"- Lluvia total: {climate['rain_total_mm']:.2f} mm",
    ]
    if "prediccion_ml" in clean:
        summary = clean["prediccion_ml"]["resumen"]
        lines.extend(
            [
                "",
                "## Predicción ML",
                f"- Riego total ML: {summary['total_liters']:,.0f} L",
                f"- Riego medio ML: {summary['avg_liters_day']:,.0f} L/día",
                f"- Litros por planta ML: {format_liters(summary['avg_liters_plant_day'])}/día",
                f"- Lámina ML: {summary['avg_gross_mm_day']:.2f} mm/día",
            ]
        )
    lines.extend(
        [
            "",
            "## Método",
            f"- Fórmula: {clean['metodo']['formula']}",
            f"- Nota: {clean['metodo']['note']}",
            "",
        ]
    )
    return "\n".join(lines)


def format_crop(value: str) -> str:
    return CROP_LABELS.get(value, value.replace("_", " ").title())


def format_stage(value: str) -> str:
    return STAGE_LABELS.get(value, value.replace("_", " ").title())


def format_liters(value: float | None) -> str:
    if value is None:
        return "N/D"
    return f"{value:.2f} L/planta"


def format_optional_number(value: object) -> str:
    if value is None:
        return "N/D"
    if isinstance(value, (int, float)):
        return f"{value:,.0f}"
    return str(value)


if __name__ == "__main__":
    main()
