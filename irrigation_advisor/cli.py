from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

from .aemet_client import AemetClient, Station
from .calculator import build_crop_profile, build_soil_profile, recommend_irrigation
from .ml import predict_irrigation_with_model, train_irrigation_model
from .models import CROP_DEFAULTS, IrrigationReport, IrrigationSystem, WeatherDay
from .weather_cache import AemetCache, DEFAULT_CACHE_DB


DEFAULT_TECHNICAL_SOIL = "franco"

EXPORT_FIELDNAMES = [
    "fecha",
    "estacion",
    "nombre_estacion",
    "provincia",
    "cultivo",
    "fase",
    "superficie_m2",
    "eficiencia_riego",
    "lluvia_efectiva_ratio",
    "et0_mm",
    "lluvia_mm",
    "tmin_c",
    "tmax_c",
    "tmedia_c",
    "kc",
    "marco_m2_por_planta",
    "etc_mm",
    "riego_bruto_mm",
    "litros_totales",
    "litros_por_planta",
    "ranking_demanda",
]


SUMMARY_FIELDNAMES = [
    "estacion",
    "nombre_estacion",
    "provincia",
    "fecha_inicio",
    "fecha_fin",
    "cultivo",
    "fase",
    "dias_analizados",
    "et0_media_mm",
    "lluvia_total_mm",
    "tmin_media_c",
    "tmax_media_c",
    "tmedia_media_c",
    "kc",
    "riego_total_litros",
    "riego_medio_litros_dia",
    "riego_medio_mm_dia",
    "etc_media_mm_dia",
    "litros_por_planta_medio",
    "diferencia_litros_vs_minimo",
    "porcentaje_incremento_vs_minimo",
    "ranking_demanda",
]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "stations":
        if args.from_cache:
            stations = AemetCache(args.cache_db).get_stations()
        else:
            client = AemetClient()
            stations = client.get_station_inventory()
        if args.province:
            province = args.province.lower()
            stations = [item for item in stations if province in item.provincia.lower()]
        if args.name:
            name = args.name.lower()
            stations = [item for item in stations if name in item.nombre.lower()]
        print(
            json.dumps(
                [
                    {
                        "station": item.indicativo,
                        "name": item.nombre,
                        "province": item.provincia,
                        "latitude": item.latitude_deg,
                        "longitude": item.longitude_deg,
                    }
                    for item in stations
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "sync-aemet-cache":
        result = sync_aemet_cache(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "crops":
        print(json.dumps(crop_defaults_to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "compare":
        comparison = build_comparison_from_args(args)
        if args.output == "markdown":
            print(comparison_to_markdown(comparison))
        else:
            print(json.dumps(comparison, ensure_ascii=False, indent=2))
        return 0

    if args.command == "export-comparison":
        comparison = build_comparison_from_args(args)
        output_format = args.file_format or infer_export_format(args.output_file)
        rows = comparison_to_export_rows(comparison=comparison)
        write_export(rows=rows, output_file=args.output_file, output_format=output_format)
        print(
            json.dumps(
                {
                    "output_file": str(Path(args.output_file)),
                    "format": output_format,
                    "rows": len(rows),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "export-aemet-comparison":
        weather_days, station_id, station_name, province = load_weather_from_args(args)
        reports = compare_crop_reports(args=args, weather_days=weather_days)
        rows = reports_to_daily_export_rows(
            reports=reports,
            station_id=station_id,
            station_name=station_name,
            province=province,
            effective_rainfall_ratio=args.effective_rainfall_ratio,
        )
        output_format = args.file_format or infer_export_format(args.output_file)
        write_export(rows=rows, output_file=args.output_file, output_format=output_format)
        print(
            json.dumps(
                {
                    "output_file": str(Path(args.output_file)),
                    "format": output_format,
                    "station": station_id,
                    "station_name": station_name,
                    "province": province,
                    "start": args.start,
                    "end": args.end,
                    "weather_days": len(weather_days),
                    "rows": len(rows),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "build-ml-dataset":
        result = build_ml_dataset_from_aemet(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "summarize-results":
        rows = read_export_rows(args.input_file)
        summary_rows = summarize_export_rows(rows)
        output_format = args.file_format or infer_summary_format(args.output_file)
        write_summary(rows=summary_rows, output_file=args.output_file, output_format=output_format)
        print(
            json.dumps(
                {
                    "input_file": str(Path(args.input_file)),
                    "output_file": str(Path(args.output_file)),
                    "format": output_format,
                    "rows": len(summary_rows),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "train-ml":
        result = train_irrigation_model(
            input_file=args.input_file,
            model_dir=args.model_dir,
            backend=args.backend,
            epochs=args.epochs,
            validation_ratio=args.validation_ratio,
            default_area_m2=args.default_area_m2,
            default_efficiency=args.default_efficiency,
            default_effective_rainfall_ratio=args.default_effective_rainfall_ratio,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "recommend":
        weather_days, station_id, station_name, province = load_weather_from_args(args)
        report = build_single_crop_report(args=args, weather_days=weather_days)
        recommendation = recommendation_to_dict(
            report=report,
            station_id=station_id,
            station_name=station_name,
            province=province,
            start=args.start,
            end=args.end,
        )
        if args.ml_model_dir:
            recommendation["ml_prediction"] = predict_irrigation_with_model(
                model_dir=args.ml_model_dir,
                weather_days=weather_days,
                args=args,
                station_id=station_id,
                station_name=station_name,
                province=province,
            )
        write_or_print_recommendation(
            recommendation=recommendation,
            output=args.output,
            output_file=args.output_file,
        )
        return 0

    if args.command == "predict-ml":
        weather_days, station_id, station_name, province = load_weather_from_args(args)
        report = build_single_crop_report(args=args, weather_days=weather_days)
        recommendation = recommendation_to_dict(
            report=report,
            station_id=station_id,
            station_name=station_name,
            province=province,
            start=args.start,
            end=args.end,
        )
        recommendation["ml_prediction"] = predict_irrigation_with_model(
            model_dir=args.model_dir,
            weather_days=weather_days,
            args=args,
            station_id=station_id,
            station_name=station_name,
            province=province,
        )
        write_or_print_recommendation(
            recommendation=recommendation,
            output=args.output,
            output_file=args.output_file,
        )
        return 0

    crop = build_crop_profile(crop=args.crop, stage=args.stage, kc=args.kc)
    soil = build_soil_profile(
        soil=DEFAULT_TECHNICAL_SOIL,
        root_depth_m=crop.root_depth_m,
        max_depletion_fraction=crop.max_depletion_fraction,
    )
    plant_spacing_m2 = (
        args.plant_spacing_m2
        if args.plant_spacing_m2 is not None
        else crop.plant_spacing_m2
    )
    system = IrrigationSystem(
        area_m2=args.area_m2,
        efficiency=args.irrigation_efficiency,
        plant_spacing_m2=plant_spacing_m2,
    )

    if args.command == "manual":
        weather_days = [
            WeatherDay(
                date=date.fromisoformat(args.date),
                et0_mm=args.et0,
                rain_mm=args.rain_mm,
            )
        ]
    elif args.command == "aemet":
        client = AemetClient()
        latitude = args.latitude
        if latitude is None:
            station = next(
                (item for item in client.get_station_inventory() if item.indicativo == args.station),
                None,
            )
            latitude = station.latitude_deg if station else None
        weather_days = client.get_daily_climate(
            station_id=args.station,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
            latitude_deg=latitude,
        )
    else:
        parser.error("Comando no reconocido")

    report = recommend_irrigation(
        weather_days=weather_days,
        crop=crop,
        soil=soil,
        system=system,
        effective_rainfall_ratio=args.effective_rainfall_ratio,
        current_soil_moisture=None,
    )
    print(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="irrigation-advisor",
        description="Recomendacion de riego a partir de AEMET, cultivo y superficie de parcela.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    manual = subparsers.add_parser("manual", help="Calculo con ET0 y lluvia introducidas manualmente.")
    manual.add_argument("--date", default=date.today().isoformat())
    manual.add_argument("--et0", type=float, required=True)
    manual.add_argument("--rain-mm", type=float, default=0.0)
    add_common_arguments(manual)

    aemet = subparsers.add_parser("aemet", help="Calculo con datos diarios de AEMET OpenData.")
    aemet.add_argument("--station", required=True, help="Indicativo de estacion AEMET.")
    aemet.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD.")
    aemet.add_argument("--end", required=True, help="Fecha final YYYY-MM-DD.")
    aemet.add_argument("--latitude", type=float, help="Latitud decimal si AEMET no aporta ET0.")
    add_common_arguments(aemet)

    stations = subparsers.add_parser("stations", help="Busca estaciones AEMET por provincia o nombre.")
    stations.add_argument("--province", help="Filtro por provincia, por ejemplo SEVILLA.")
    stations.add_argument("--name", help="Filtro por nombre de estacion.")
    stations.add_argument("--from-cache", action="store_true", help="Lee el inventario desde la cache SQLite local.")
    stations.add_argument("--cache-db", default=DEFAULT_CACHE_DB, help="Ruta de la cache SQLite.")

    sync_cache = subparsers.add_parser(
        "sync-aemet-cache",
        help="Sincroniza estaciones y datos diarios AEMET en una cache SQLite local.",
    )
    sync_cache.add_argument("--db-file", default=DEFAULT_CACHE_DB, help="Ruta de la cache SQLite.")
    sync_cache.add_argument("--station", action="append", help="Indicativo AEMET. Puede repetirse.")
    sync_cache.add_argument("--province", help="Provincia para filtrar estaciones.")
    sync_cache.add_argument("--station-name", help="Texto del nombre de estacion.")
    sync_cache.add_argument("--start", help="Fecha inicial YYYY-MM-DD. Si se omite, solo actualiza estaciones.")
    sync_cache.add_argument("--end", help="Fecha final YYYY-MM-DD. Si se omite, solo actualiza estaciones.")
    sync_cache.add_argument("--max-stations", type=int, default=25, help="Limite de estaciones por ejecucion.")
    sync_cache.add_argument("--all-stations", action="store_true", help="Sincroniza todas las estaciones filtradas.")
    sync_cache.add_argument("--force", action="store_true", help="Vuelve a descargar aunque los dias ya existan.")
    sync_cache.add_argument("--request-delay", type=float, default=1.0, help="Pausa entre peticiones a AEMET.")
    sync_cache.add_argument("--retries", type=int, default=2, help="Reintentos por rango fallido.")
    sync_cache.add_argument("--retry-delay", type=float, default=10.0, help="Pausa entre reintentos.")
    sync_cache.add_argument("--strict", action="store_true", help="Detiene el proceso ante el primer fallo.")

    subparsers.add_parser("crops", help="Muestra los tres perfiles de cultivo configurados.")

    compare = subparsers.add_parser("compare", help="Compara riego de olivar, citricos y almendro.")
    compare.add_argument("--date", default=date.today().isoformat())
    compare.add_argument("--et0", type=float, required=True)
    compare.add_argument("--rain-mm", type=float, default=0.0)
    compare.add_argument("--stage", required=True, help="Fase comun: inicio, desarrollo, media, madurez.")
    compare.add_argument("--area-m2", type=float, required=True, help="Superficie de la parcela en m2.")
    compare.add_argument("--irrigation-efficiency", type=float, default=0.90)
    compare.add_argument("--effective-rainfall-ratio", type=float, default=0.80)
    compare.add_argument("--output", choices=["json", "markdown"], default="json")

    export = subparsers.add_parser("export-comparison", help="Exporta la comparativa de cultivos a CSV o JSON.")
    export.add_argument("--date", default=date.today().isoformat())
    export.add_argument("--et0", type=float, required=True)
    export.add_argument("--rain-mm", type=float, default=0.0)
    export.add_argument("--stage", required=True, help="Fase comun: inicio, desarrollo, media, madurez.")
    export.add_argument("--area-m2", type=float, required=True, help="Superficie de la parcela en m2.")
    export.add_argument("--irrigation-efficiency", type=float, default=0.90)
    export.add_argument("--effective-rainfall-ratio", type=float, default=0.80)
    export.add_argument("--output-file", default="data/resultados/comparativa_riego.csv")
    export.add_argument("--file-format", choices=["csv", "json"], help="Si se omite, se infiere por extension.")

    export_aemet = subparsers.add_parser(
        "export-aemet-comparison",
        help="Exporta comparativa diaria de cultivos con datos reales AEMET.",
    )
    export_aemet.add_argument("--station", help="Indicativo de estacion AEMET.")
    export_aemet.add_argument("--province", help="Provincia para buscar estacion, por ejemplo SEVILLA.")
    export_aemet.add_argument("--station-name", help="Texto del nombre de estacion, por ejemplo AEROPUERTO.")
    export_aemet.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD.")
    export_aemet.add_argument("--end", required=True, help="Fecha final YYYY-MM-DD.")
    export_aemet.add_argument("--latitude", type=float, help="Latitud decimal si AEMET no aporta ET0.")
    export_aemet.add_argument("--cache-db", help="Lee los datos climaticos desde la cache SQLite en vez de llamar a AEMET.")
    export_aemet.add_argument("--stage", required=True, help="Fase comun: inicio, desarrollo, media, madurez.")
    export_aemet.add_argument("--area-m2", type=float, required=True, help="Superficie de la parcela en m2.")
    export_aemet.add_argument("--irrigation-efficiency", type=float, default=0.90)
    export_aemet.add_argument("--effective-rainfall-ratio", type=float, default=0.80)
    export_aemet.add_argument("--output-file", default="data/resultados/comparativa_aemet.csv")
    export_aemet.add_argument("--file-format", choices=["csv", "json"], help="Si se omite, se infiere por extension.")

    ml_dataset = subparsers.add_parser(
        "build-ml-dataset",
        help="Construye un dataset historico ML cruzando estaciones AEMET, cultivos y fases.",
    )
    ml_dataset.add_argument("--station", action="append", help="Indicativo AEMET. Puede repetirse.")
    ml_dataset.add_argument("--province", help="Provincia para filtrar estaciones, por ejemplo SEVILLA.")
    ml_dataset.add_argument("--station-name", help="Texto del nombre de estacion, por ejemplo AEROPUERTO.")
    ml_dataset.add_argument("--weather-file", help="CSV/JSON AEMET ya exportado para construir el dataset sin llamar a la API.")
    ml_dataset.add_argument("--cache-db", help="Cache SQLite AEMET para construir el dataset sin llamar a la API.")
    ml_dataset.add_argument("--max-stations", type=int, default=3)
    ml_dataset.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD.")
    ml_dataset.add_argument("--end", required=True, help="Fecha final YYYY-MM-DD.")
    ml_dataset.add_argument("--crop", action="append", choices=sorted(CROP_DEFAULTS), help="Cultivo. Puede repetirse.")
    ml_dataset.add_argument(
        "--stage",
        action="append",
        choices=["inicio", "desarrollo", "media", "madurez"],
        help="Fase fenologica. Puede repetirse. Si se omite, usa todas.",
    )
    ml_dataset.add_argument("--area-m2", type=float, default=10000.0, help="Superficie base de simulacion.")
    ml_dataset.add_argument("--irrigation-efficiency", type=float, default=0.90)
    ml_dataset.add_argument("--effective-rainfall-ratio", type=float, default=0.80)
    ml_dataset.add_argument("--output-file", default="data/resultados/dataset_ml_aemet.csv")
    ml_dataset.add_argument("--file-format", choices=["csv", "json"], help="Si se omite, se infiere por extension.")
    ml_dataset.add_argument("--strict", action="store_true", help="Detiene el proceso si una estacion falla.")
    ml_dataset.add_argument("--train-model-dir", help="Entrena un modelo al terminar de generar el dataset.")
    ml_dataset.add_argument("--backend", choices=["auto", "keras", "linear"], default="auto")
    ml_dataset.add_argument("--epochs", type=int, default=150)

    summary = subparsers.add_parser("summarize-results", help="Resume un CSV/JSON de riego por cultivo.")
    summary.add_argument("--input-file", required=True)
    summary.add_argument("--output-file", default="data/resultados/resumen_riego.csv")
    summary.add_argument("--file-format", choices=["csv", "json", "markdown"], help="Si se omite, se infiere por extension.")

    train_ml = subparsers.add_parser("train-ml", help="Entrena un modelo predictivo con historicos AEMET exportados.")
    train_ml.add_argument("--input-file", required=True, help="CSV/JSON creado con export-aemet-comparison.")
    train_ml.add_argument("--model-dir", default="models/riego_predictivo")
    train_ml.add_argument("--backend", choices=["auto", "keras", "linear"], default="auto")
    train_ml.add_argument("--epochs", type=int, default=150)
    train_ml.add_argument("--validation-ratio", type=float, default=0.20)
    train_ml.add_argument("--default-area-m2", type=float, default=10000.0)
    train_ml.add_argument("--default-efficiency", type=float, default=0.90)
    train_ml.add_argument("--default-effective-rainfall-ratio", type=float, default=0.80)

    recommend = subparsers.add_parser("recommend", help="Genera una recomendacion de riego para un cliente.")
    recommend.add_argument("--station", help="Indicativo de estacion AEMET.")
    recommend.add_argument("--province", help="Provincia para buscar estacion, por ejemplo SEVILLA.")
    recommend.add_argument("--station-name", help="Texto del nombre de estacion, por ejemplo AEROPUERTO.")
    recommend.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD.")
    recommend.add_argument("--end", required=True, help="Fecha final YYYY-MM-DD.")
    recommend.add_argument("--latitude", type=float, help="Latitud decimal si AEMET no aporta ET0.")
    recommend.add_argument("--weather-file", help="CSV/JSON de AEMET ya exportado para evitar llamar de nuevo a la API.")
    recommend.add_argument("--cache-db", help="Cache SQLite AEMET para evitar llamar de nuevo a la API.")
    add_common_arguments(recommend)
    recommend.add_argument("--output", choices=["json", "markdown"], default="markdown")
    recommend.add_argument("--output-file", help="Ruta opcional para guardar el informe.")
    recommend.add_argument("--ml-model-dir", help="Directorio de modelo entrenado para anadir prediccion ML.")

    predict_ml = subparsers.add_parser("predict-ml", help="Predice riego con un modelo ML entrenado.")
    predict_ml.add_argument("--model-dir", required=True, help="Directorio creado por train-ml.")
    predict_ml.add_argument("--station", help="Indicativo de estacion AEMET.")
    predict_ml.add_argument("--province", help="Provincia para buscar estacion, por ejemplo SEVILLA.")
    predict_ml.add_argument("--station-name", help="Texto del nombre de estacion, por ejemplo AEROPUERTO.")
    predict_ml.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD.")
    predict_ml.add_argument("--end", required=True, help="Fecha final YYYY-MM-DD.")
    predict_ml.add_argument("--latitude", type=float, help="Latitud decimal si AEMET no aporta ET0.")
    predict_ml.add_argument("--weather-file", help="CSV/JSON de AEMET ya exportado para evitar llamar de nuevo a la API.")
    predict_ml.add_argument("--cache-db", help="Cache SQLite AEMET para evitar llamar de nuevo a la API.")
    add_common_arguments(predict_ml)
    predict_ml.add_argument("--output", choices=["json", "markdown"], default="markdown")
    predict_ml.add_argument("--output-file", help="Ruta opcional para guardar el informe.")
    return parser


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--crop", required=True, help="Cultivo: olivar, citricos, almendro...")
    parser.add_argument("--stage", required=True, help="Fase: inicio, desarrollo, media, madurez.")
    parser.add_argument("--area-m2", type=float, required=True, help="Superficie de la parcela en m2.")
    parser.add_argument("--irrigation-efficiency", type=float, default=0.90)
    parser.add_argument("--effective-rainfall-ratio", type=float, default=0.80)
    parser.add_argument("--plant-spacing-m2", type=float, help="Sobrescribe la superficie asignada por planta.")
    parser.add_argument("--kc", type=float, help="Sobrescribe el Kc por defecto.")


def build_ml_dataset_from_aemet(args: argparse.Namespace) -> dict:
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    crop_names = args.crop or list(CROP_DEFAULTS)
    stages = args.stage or ["inicio", "desarrollo", "media", "madurez"]
    rows: list[dict] = []
    errors: list[dict] = []

    if args.weather_file:
        weather_sources = weather_sources_from_export(args)
        station_count = len(weather_sources)
    elif args.cache_db:
        weather_sources = weather_sources_from_cache(args)
        station_count = len(weather_sources)
    else:
        client = AemetClient()
        stations = resolve_dataset_stations(client=client, args=args)
        station_count = len(stations)
        weather_sources = []
        for station in stations:
            try:
                weather_sources.append(
                    (
                        client.get_daily_climate(
                            station_id=station.indicativo,
                            start=start,
                            end=end,
                            latitude_deg=station.latitude_deg,
                        ),
                        station.indicativo,
                        station.nombre,
                        station.provincia,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - report station-level dataset failures.
                if args.strict:
                    raise
                errors.append(
                    {
                        "station": station.indicativo,
                        "station_name": station.nombre,
                        "province": station.provincia,
                        "error": str(exc),
                    }
                )

    for weather_days, station_id, station_name, province in weather_sources:
        for stage in stages:
            scenario_args = SimpleNamespace(
                stage=stage,
                area_m2=args.area_m2,
                irrigation_efficiency=args.irrigation_efficiency,
                effective_rainfall_ratio=args.effective_rainfall_ratio,
            )
            reports = compare_crop_reports(
                args=scenario_args,
                weather_days=weather_days,
                crop_names=crop_names,
            )
            rows.extend(
                reports_to_daily_export_rows(
                    reports=reports,
                    station_id=station_id,
                    station_name=station_name,
                    province=province,
                    effective_rainfall_ratio=args.effective_rainfall_ratio,
                )
            )

    if not rows:
        raise ValueError("No se pudo generar ningun dato para el dataset ML")

    output_format = args.file_format or infer_export_format(args.output_file)
    write_export(rows=rows, output_file=args.output_file, output_format=output_format)
    result = {
        "output_file": str(Path(args.output_file)),
        "format": output_format,
        "stations_requested": station_count,
        "stations_ok": len({row["estacion"] for row in rows}),
        "rows": len(rows),
        "crops": crop_names,
        "stages": stages,
        "errors": errors,
    }
    if args.train_model_dir:
        result["training"] = train_irrigation_model(
            input_file=args.output_file,
            model_dir=args.train_model_dir,
            backend=args.backend,
            epochs=args.epochs,
            default_area_m2=args.area_m2,
            default_efficiency=args.irrigation_efficiency,
            default_effective_rainfall_ratio=args.effective_rainfall_ratio,
        )
    return result


def sync_aemet_cache(args: argparse.Namespace) -> dict:
    cache = AemetCache(args.db_file)
    client = AemetClient()
    stations = client.get_station_inventory()
    stations_upserted = cache.upsert_stations(stations)

    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    if (start is None) != (end is None):
        raise ValueError("Indica --start y --end juntos, o ninguno para sincronizar solo estaciones")
    if start and end and end < start:
        raise ValueError("La fecha final no puede ser anterior a la inicial")

    selected = resolve_sync_stations(stations=stations, args=args)
    if not args.all_stations:
        if args.max_stations <= 0:
            raise ValueError("--max-stations debe ser positivo")
        selected = selected[: args.max_stations]

    result = {
        "db_file": str(Path(args.db_file)),
        "stations_inventory": len(stations),
        "stations_upserted": stations_upserted,
        "stations_selected": len(selected),
        "weather_rows_upserted": 0,
        "ranges_requested": 0,
        "errors": [],
        "counts": cache.counts(),
    }
    if start is None or end is None:
        result["mode"] = "stations_only"
        return result

    for station_index, station in enumerate(selected, start=1):
        ranges = [(start, end)] if args.force else cache.missing_ranges(station.indicativo, start, end)
        if not ranges:
            continue
        for range_start, range_end in ranges:
            try:
                weather_days = fetch_daily_climate_with_retries(
                    client=client,
                    station=station,
                    start=range_start,
                    end=range_end,
                    retries=args.retries,
                    retry_delay=args.retry_delay,
                )
                result["ranges_requested"] += 1
                result["weather_rows_upserted"] += cache.upsert_weather(station=station, weather_days=weather_days)
            except Exception as exc:  # noqa: BLE001 - station-level ETL should continue unless strict.
                error = {
                    "station": station.indicativo,
                    "station_name": station.nombre,
                    "province": station.provincia,
                    "start": range_start.isoformat(),
                    "end": range_end.isoformat(),
                    "error": str(exc),
                }
                result["errors"].append(error)
                if args.strict:
                    raise
            if args.request_delay > 0 and station_index < len(selected):
                time.sleep(args.request_delay)

    result["mode"] = "weather"
    result["counts"] = cache.counts()
    return result


def fetch_daily_climate_with_retries(
    client: AemetClient,
    station: Station,
    start: date,
    end: date,
    retries: int,
    retry_delay: float,
) -> list[WeatherDay]:
    attempts = max(0, retries) + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return client.get_daily_climate(
                station_id=station.indicativo,
                start=start,
                end=end,
                latitude_deg=station.latitude_deg,
            )
        except Exception as exc:  # noqa: BLE001 - retry wrapper preserves final error.
            last_error = exc
            if attempt < attempts - 1 and retry_delay > 0:
                time.sleep(retry_delay)
    if last_error:
        raise last_error
    return []


def resolve_sync_stations(stations: list[Station], args: argparse.Namespace) -> list[Station]:
    if args.station:
        by_id = {station.indicativo: station for station in stations}
        missing = [station_id for station_id in args.station if station_id not in by_id]
        if missing:
            raise ValueError(f"No se encontraron estaciones AEMET: {', '.join(missing)}")
        return unique_stations([by_id[station_id] for station_id in args.station])

    matches = filter_stations(stations=stations, province=args.province, station_name=args.station_name)
    if not matches:
        raise ValueError("No se encontraron estaciones AEMET para sincronizar")
    return matches


def resolve_dataset_stations(client: AemetClient, args: argparse.Namespace) -> list[Station]:
    if args.station:
        stations = []
        for station_id in args.station:
            station = client.find_station(station_id)
            if station is None:
                raise ValueError(f"No se encontro la estacion AEMET: {station_id}")
            stations.append(station)
        return unique_stations(stations)

    matches = filter_stations(
        stations=client.get_station_inventory(),
        province=args.province,
        station_name=args.station_name,
    )
    if not matches:
        raise ValueError("No se encontraron estaciones AEMET para generar el dataset")
    if args.max_stations <= 0:
        raise ValueError("--max-stations debe ser positivo")
    return matches[: args.max_stations]


def weather_sources_from_export(args: argparse.Namespace) -> list[tuple[list[WeatherDay], str, str | None, str | None]]:
    rows = read_export_rows(args.weather_file)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    requested_stations = set(args.station or [])
    province_filter = normalize_text(args.province)
    name_filter = normalize_text(args.station_name)
    grouped: dict[str, dict[str, dict]] = {}
    metadata: dict[str, dict[str, str | None]] = {}

    for row in rows:
        station_id = str(row.get("estacion", "")).strip()
        if not station_id:
            continue
        if requested_stations and station_id not in requested_stations:
            continue
        province = str(row.get("provincia", "")).strip()
        station_name = str(row.get("nombre_estacion", "")).strip()
        if province_filter and province_filter not in normalize_text(province):
            continue
        if name_filter and name_filter not in normalize_text(station_name):
            continue
        row_date_text = str(row.get("fecha", "")).strip()
        if not row_date_text:
            continue
        row_date = date.fromisoformat(row_date_text)
        if row_date < start or row_date > end:
            continue
        grouped.setdefault(station_id, {}).setdefault(row_date_text, row)
        metadata.setdefault(
            station_id,
            {
                "station_name": station_name or None,
                "province": province or None,
            },
        )

    if not grouped:
        raise ValueError("No hay datos climaticos en el archivo para los filtros indicados")

    sources = []
    for station_id in sorted(grouped)[: args.max_stations]:
        station_rows = grouped[station_id]
        weather_days = [
            WeatherDay(
                date=date.fromisoformat(row_date_text),
                et0_mm=to_float(row.get("et0_mm")),
                rain_mm=to_float(row.get("lluvia_mm")),
                tmin_c=optional_float(row.get("tmin_c")),
                tmax_c=optional_float(row.get("tmax_c")),
                tmean_c=optional_float(row.get("tmedia_c")),
            )
            for row_date_text, row in sorted(station_rows.items())
        ]
        station_metadata = metadata[station_id]
        sources.append(
            (
                weather_days,
                station_id,
                station_metadata["station_name"],
                station_metadata["province"],
            )
        )
    return sources


def weather_sources_from_cache(args: argparse.Namespace) -> list[tuple[list[WeatherDay], str, str | None, str | None]]:
    cache = AemetCache(args.cache_db)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    stations = resolve_dataset_stations(client=cache, args=args)
    sources = []
    for station in stations:
        source = cache.get_weather_source(station_id=station.indicativo, start=start, end=end)
        sources.append(
            (
                source.weather_days,
                source.station_id,
                source.station_name,
                source.province,
            )
        )
    return sources


def unique_stations(stations: list[Station]) -> list[Station]:
    seen = set()
    result = []
    for station in stations:
        if station.indicativo in seen:
            continue
        seen.add(station.indicativo)
        result.append(station)
    return result


def load_weather_from_args(args: argparse.Namespace) -> tuple[list[WeatherDay], str, str | None, str | None]:
    weather_file = getattr(args, "weather_file", None)
    if weather_file:
        return weather_days_from_export(
            input_file=weather_file,
            station_id=args.station,
            province=args.province,
            station_name=args.station_name,
            start=args.start,
            end=args.end,
        )

    cache_db = getattr(args, "cache_db", None)
    if cache_db:
        cache = AemetCache(cache_db)
        station = resolve_station_from_args(client=cache, args=args)
        source = cache.get_weather_source(
            station_id=station.indicativo,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
        )
        return source.weather_days, source.station_id, source.station_name, source.province

    client = AemetClient()
    station = resolve_station_from_args(client=client, args=args)
    latitude = args.latitude or (station.latitude_deg if station else None)
    weather_days = client.get_daily_climate(
        station_id=station.indicativo,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        latitude_deg=latitude,
    )
    return (
        weather_days,
        station.indicativo,
        station.nombre if station else None,
        station.provincia if station else None,
    )


def resolve_station_from_args(client: AemetClient, args: argparse.Namespace) -> Station:
    station_id = getattr(args, "station", None)
    province = getattr(args, "province", None)
    station_name = getattr(args, "station_name", None)

    if station_id:
        station = client.find_station(station_id)
        if station is None:
            raise ValueError(f"No se encontro la estacion AEMET: {station_id}")
        return station

    if not province and not station_name:
        raise ValueError("Indica --station o usa --province/--station-name para buscar estacion AEMET")

    matches = filter_stations(
        stations=client.get_station_inventory(),
        province=province,
        station_name=station_name,
    )
    if not matches:
        raise ValueError("No se encontraron estaciones AEMET con los filtros indicados")
    return matches[0]


def filter_stations(
    stations: list[Station],
    province: str | None,
    station_name: str | None,
) -> list[Station]:
    province_filter = normalize_text(province)
    name_filter = normalize_text(station_name)
    matches = []
    for station in stations:
        province_match = not province_filter or province_filter in normalize_text(station.provincia)
        name_match = not name_filter or name_filter in normalize_text(station.nombre)
        if province_match and name_match:
            matches.append(station)

    return sorted(
        matches,
        key=lambda station: (
            0 if name_filter and normalize_text(station.nombre) == name_filter else 1,
            station.provincia,
            station.nombre,
            station.indicativo,
        ),
    )


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().lower()


def report_to_dict(report: IrrigationReport) -> dict:
    return {
        "crop": {
            "name": report.crop.name,
            "stage": report.crop.stage,
            "kc": round(report.crop.kc, 3),
            "default_plant_spacing_m2": report.crop.plant_spacing_m2,
        },
        "system": {
            "area_m2": report.system.area_m2,
            "efficiency": report.system.efficiency,
            "plant_spacing_m2": report.system.plant_spacing_m2,
            "plants": round(report.system.plants, 2) if report.system.plants else None,
        },
        "total_gross_irrigation_mm": round(report.total_gross_irrigation_mm, 2),
        "total_liters": round(report.total_liters, 2),
        "days": [
            {
                "date": item.date.isoformat(),
                "et0_mm": round(item.et0_mm, 2),
                "tmin_c": round(item.tmin_c, 2) if item.tmin_c is not None else None,
                "tmax_c": round(item.tmax_c, 2) if item.tmax_c is not None else None,
                "tmean_c": round(item.tmean_c, 2) if item.tmean_c is not None else None,
                "kc": round(item.kc, 3),
                "etc_mm": round(item.etc_mm, 2),
                "rain_mm": round(item.rain_mm, 2),
                "effective_rain_mm": round(item.effective_rain_mm, 2),
                "net_irrigation_mm": round(item.net_irrigation_mm, 2),
                "gross_irrigation_mm": round(item.gross_irrigation_mm, 2),
                "liters_total": round(item.liters_total, 2),
                "liters_per_plant": round(item.liters_per_plant, 2)
                if item.liters_per_plant is not None
                else None,
            }
            for item in report.days
        ],
    }


def compare_crop_reports(
    args: argparse.Namespace,
    weather_days: list[WeatherDay],
    crop_names: list[str] | None = None,
) -> list[IrrigationReport]:
    reports: list[IrrigationReport] = []
    for crop_name in crop_names or list(CROP_DEFAULTS):
        crop = build_crop_profile(crop=crop_name, stage=args.stage)
        soil = build_soil_profile(
            soil=DEFAULT_TECHNICAL_SOIL,
            root_depth_m=crop.root_depth_m,
            max_depletion_fraction=crop.max_depletion_fraction,
        )
        system = IrrigationSystem(
            area_m2=args.area_m2,
            efficiency=args.irrigation_efficiency,
            plant_spacing_m2=crop.plant_spacing_m2,
        )
        reports.append(
            recommend_irrigation(
                weather_days=weather_days,
                crop=crop,
                soil=soil,
                system=system,
                effective_rainfall_ratio=args.effective_rainfall_ratio,
                current_soil_moisture=None,
            )
        )
    return reports


def build_single_crop_report(args: argparse.Namespace, weather_days: list[WeatherDay]) -> IrrigationReport:
    crop = build_crop_profile(crop=args.crop, stage=args.stage, kc=args.kc)
    soil = build_soil_profile(
        soil=DEFAULT_TECHNICAL_SOIL,
        root_depth_m=crop.root_depth_m,
        max_depletion_fraction=crop.max_depletion_fraction,
    )
    plant_spacing_m2 = (
        args.plant_spacing_m2
        if args.plant_spacing_m2 is not None
        else crop.plant_spacing_m2
    )
    system = IrrigationSystem(
        area_m2=args.area_m2,
        efficiency=args.irrigation_efficiency,
        plant_spacing_m2=plant_spacing_m2,
    )
    return recommend_irrigation(
        weather_days=weather_days,
        crop=crop,
        soil=soil,
        system=system,
        effective_rainfall_ratio=args.effective_rainfall_ratio,
        current_soil_moisture=None,
    )


def weather_days_from_export(
    input_file: str,
    station_id: str | None,
    province: str | None,
    station_name: str | None,
    start: str,
    end: str,
) -> tuple[list[WeatherDay], str, str | None, str | None]:
    rows = read_export_rows(input_file)
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    by_date: dict[str, dict] = {}
    selected_station_id = station_id
    selected_station_name = None
    selected_province = None
    province_filter = normalize_text(province)
    name_filter = normalize_text(station_name)
    for row in rows:
        row_station_id = str(row.get("estacion", "")).strip()
        row_province = str(row.get("provincia", "")).strip()
        row_station_name = str(row.get("nombre_estacion", "")).strip()
        if selected_station_id and row_station_id != selected_station_id:
            continue
        if province_filter and province_filter not in normalize_text(row_province):
            continue
        if name_filter and name_filter not in normalize_text(row_station_name):
            continue
        row_date_text = str(row.get("fecha", ""))
        if not row_date_text:
            continue
        row_date = date.fromisoformat(row_date_text)
        if row_date < start_date or row_date > end_date:
            continue
        if selected_station_id is None:
            selected_station_id = row_station_id
        if row_station_id != selected_station_id:
            continue
        by_date.setdefault(row_date_text, row)
        selected_station_name = selected_station_name or first_value([row], "nombre_estacion")
        selected_province = selected_province or first_value([row], "provincia")

    weather_days = []
    for row_date_text in sorted(by_date):
        row = by_date[row_date_text]
        weather_days.append(
            WeatherDay(
                date=date.fromisoformat(row_date_text),
                et0_mm=to_float(row.get("et0_mm")),
                rain_mm=to_float(row.get("lluvia_mm")),
                tmin_c=optional_float(row.get("tmin_c")),
                tmax_c=optional_float(row.get("tmax_c")),
                tmean_c=optional_float(row.get("tmedia_c")),
            )
        )
    if not weather_days:
        raise ValueError("No hay datos climaticos en el archivo para la estacion y fechas indicadas")
    return weather_days, selected_station_id or "", selected_station_name, selected_province


def recommendation_to_dict(
    report: IrrigationReport,
    station_id: str,
    station_name: str | None,
    province: str | None,
    start: str,
    end: str,
) -> dict:
    days = len(report.days)
    daily_liters = [day.liters_total for day in report.days]
    daily_liters_per_plant = [
        day.liters_per_plant for day in report.days if day.liters_per_plant is not None
    ]
    total_liters = sum(daily_liters)
    return {
        "service": "recomendacion_riego",
        "location": {
            "station": station_id,
            "station_name": station_name,
            "province": province,
        },
        "period": {
            "start": start,
            "end": end,
            "days": days,
        },
        "plot": {
            "crop": report.crop.name,
            "stage": report.crop.stage,
            "area_m2": report.system.area_m2,
            "area_ha": round(report.system.area_m2 / 10000, 4),
            "plants_estimated": round(report.system.plants, 2) if report.system.plants else None,
        },
        "climate": {
            "et0_avg_mm_day": round(average_recommendation(report, "et0_mm"), 2),
            "rain_total_mm": round(sum(day.rain_mm for day in report.days), 2),
            "tmin_avg_c": round(average_recommendation(report, "tmin_c"), 2),
            "tmax_avg_c": round(average_recommendation(report, "tmax_c"), 2),
            "tmean_avg_c": round(average_recommendation(report, "tmean_c"), 2),
        },
        "recommendation": {
            "total_liters": round(total_liters, 2),
            "avg_liters_day": round(total_liters / days, 2) if days else 0,
            "avg_gross_mm_day": round(average_recommendation(report, "gross_irrigation_mm"), 2),
            "avg_etc_mm_day": round(average_recommendation(report, "etc_mm"), 2),
            "avg_liters_plant_day": round(sum(daily_liters_per_plant) / len(daily_liters_per_plant), 2)
            if daily_liters_per_plant
            else None,
        },
        "daily": [
            {
                "date": day.date.isoformat(),
                "et0_mm": round(day.et0_mm, 2),
                "rain_mm": round(day.rain_mm, 2),
                "etc_mm": round(day.etc_mm, 2),
                "gross_irrigation_mm": round(day.gross_irrigation_mm, 2),
                "liters_total": round(day.liters_total, 2),
                "liters_per_plant": round(day.liters_per_plant, 2)
                if day.liters_per_plant is not None
                else None,
            }
            for day in report.days
        ],
        "method": {
            "formula": "ETc = ET0 * Kc; riego_bruto = max(0, ETc - lluvia_efectiva) / eficiencia",
            "note": "Estimacion agronomica basada en AEMET y parametros de parcela; requiere validacion de campo para operacion real.",
        },
    }


def recommendation_to_markdown(recommendation: dict) -> str:
    location = recommendation["location"]
    period = recommendation["period"]
    plot = recommendation["plot"]
    climate = recommendation["climate"]
    result = recommendation["recommendation"]
    lines = [
        "# Informe de recomendacion de riego",
        "",
        "## Datos del cliente",
        "",
        f"- Estacion AEMET: {location['station']} - {location['station_name'] or 'N/D'} ({location['province'] or 'N/D'})",
        f"- Periodo climatico: {period['start']} a {period['end']} ({period['days']} dias)",
        f"- Cultivo: {plot['crop']} ({plot['stage']})",
        f"- Superficie: {plot['area_m2']:.2f} m2 ({plot['area_ha']:.4f} ha)",
    ]
    if plot["plants_estimated"] is not None:
        lines.append(f"- Plantas estimadas: {plot['plants_estimated']:.2f}")

    lines.extend(
        [
            "",
            "## Condiciones climaticas",
            "",
            f"- ET0 media: {climate['et0_avg_mm_day']:.2f} mm/dia",
            f"- Lluvia total: {climate['rain_total_mm']:.2f} mm",
            f"- Temperatura media: {climate['tmean_avg_c']:.2f} C",
            "",
            "## Recomendacion",
            "",
            f"- Riego total del periodo: {result['total_liters']:.2f} L",
            f"- Riego medio diario: {result['avg_liters_day']:.2f} L/dia",
            f"- Lamina media diaria: {result['avg_gross_mm_day']:.2f} mm/dia",
        ]
    )
    if result["avg_liters_plant_day"] is not None:
        lines.append(f"- Litros medios por planta: {result['avg_liters_plant_day']:.2f} L/planta/dia")

    ml_prediction = recommendation.get("ml_prediction")
    if ml_prediction:
        ml_summary = ml_prediction["summary"]
        ml_model = ml_prediction["model"]
        lines.extend(
            [
                "",
                "## Prediccion ML",
                "",
                f"- Modelo: {ml_model['model_type']} ({ml_model['target']})",
                f"- Riego total ML: {ml_summary['total_liters']:.2f} L",
                f"- Riego medio diario ML: {ml_summary['avg_liters_day']:.2f} L/dia",
                f"- Lamina media diaria ML: {ml_summary['avg_gross_mm_day']:.2f} mm/dia",
            ]
        )
        if ml_summary["avg_liters_plant_day"] is not None:
            lines.append(f"- Litros medios por planta ML: {ml_summary['avg_liters_plant_day']:.2f} L/planta/dia")
        metrics = ml_model.get("metrics") or {}
        if metrics:
            lines.append(
                "- Validacion: MAE {mae} mm, RMSE {rmse} mm, R2 {r2}".format(
                    mae=format_optional_number(metrics.get("mae_mm")),
                    rmse=format_optional_number(metrics.get("rmse_mm")),
                    r2=format_optional_number(metrics.get("r2")),
                )
            )

    lines.extend(
        [
            "",
            "## Detalle diario",
            "",
            "| Fecha | ET0 (mm) | Lluvia (mm) | ETc (mm) | Riego bruto (mm) | Litros | L/planta |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for day in recommendation["daily"]:
        lines.append(
            "| {date} | {et0:.2f} | {rain:.2f} | {etc:.2f} | {gross:.2f} | {liters:.2f} | {plant} |".format(
                date=day["date"],
                et0=day["et0_mm"],
                rain=day["rain_mm"],
                etc=day["etc_mm"],
                gross=day["gross_irrigation_mm"],
                liters=day["liters_total"],
                plant=format_optional_number(day["liters_per_plant"]),
            )
        )

    if ml_prediction:
        lines.extend(
            [
                "",
                "## Detalle diario ML",
                "",
                "| Fecha | Riego ML (mm) | Litros ML | L/planta ML |",
                "|---|---:|---:|---:|",
            ]
        )
        for day in ml_prediction["daily"]:
            lines.append(
                "| {date} | {gross:.2f} | {liters:.2f} | {plant} |".format(
                    date=day["date"],
                    gross=day["predicted_gross_irrigation_mm"],
                    liters=day["predicted_liters_total"],
                    plant=format_optional_number(day["predicted_liters_per_plant"]),
                )
            )

    lines.extend(
        [
            "",
            "## Metodo",
            "",
            recommendation["method"]["formula"],
            "",
            recommendation["method"]["note"],
        ]
    )
    return "\n".join(lines) + "\n"


def write_or_print_recommendation(
    recommendation: dict,
    output: str,
    output_file: str | None,
) -> None:
    if output == "json":
        payload = json.dumps(recommendation, ensure_ascii=False, indent=2) + "\n"
    else:
        payload = recommendation_to_markdown(recommendation)

    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
        print(
            json.dumps(
                {
                    "output_file": str(output_path),
                    "format": output,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print(payload, end="")


def average_recommendation(report: IrrigationReport, attr: str) -> float:
    values = [getattr(day, attr) for day in report.days if getattr(day, attr) is not None]
    if not values:
        return 0.0
    return sum(values) / len(values)


def build_comparison_from_args(args: argparse.Namespace) -> dict:
    weather_days = [
        WeatherDay(
            date=date.fromisoformat(args.date),
            et0_mm=args.et0,
            rain_mm=args.rain_mm,
        )
    ]
    reports = compare_crop_reports(args=args, weather_days=weather_days)
    return comparison_to_dict(
        reports=reports,
        date_value=args.date,
        et0_mm=args.et0,
        rain_mm=args.rain_mm,
        stage=args.stage,
        area_m2=args.area_m2,
        irrigation_efficiency=args.irrigation_efficiency,
        effective_rainfall_ratio=args.effective_rainfall_ratio,
    )


def comparison_to_dict(
    reports: list[IrrigationReport],
    date_value: str,
    et0_mm: float,
    rain_mm: float,
    stage: str,
    area_m2: float,
    irrigation_efficiency: float,
    effective_rainfall_ratio: float,
) -> dict:
    rows = [comparison_row(report) for report in reports]
    sorted_rows = sorted(rows, key=lambda row: row["total_liters"])
    lowest = sorted_rows[0]
    highest = sorted_rows[-1]
    return {
        "scenario": {
            "date": date_value,
            "et0_mm": et0_mm,
            "rain_mm": rain_mm,
            "stage": stage,
            "area_m2": area_m2,
            "irrigation_efficiency": irrigation_efficiency,
            "effective_rainfall_ratio": effective_rainfall_ratio,
        },
        "ranking": {
            "lowest_irrigation_crop": lowest["crop"],
            "highest_irrigation_crop": highest["crop"],
            "difference_liters": round(highest["total_liters"] - lowest["total_liters"], 2),
            "difference_gross_mm": round(
                highest["total_gross_irrigation_mm"] - lowest["total_gross_irrigation_mm"],
                2,
            ),
        },
        "crops": rows,
    }


def comparison_row(report: IrrigationReport) -> dict:
    first_day = report.days[0]
    return {
        "crop": report.crop.name,
        "stage": report.crop.stage,
        "kc": round(report.crop.kc, 3),
        "plant_spacing_m2": report.crop.plant_spacing_m2,
        "etc_mm": round(first_day.etc_mm, 2),
        "gross_irrigation_mm": round(first_day.gross_irrigation_mm, 2),
        "total_gross_irrigation_mm": round(report.total_gross_irrigation_mm, 2),
        "total_liters": round(report.total_liters, 2),
        "liters_per_plant": round(first_day.liters_per_plant, 2)
        if first_day.liters_per_plant is not None
        else None,
    }


def comparison_to_markdown(comparison: dict) -> str:
    lines = [
        "| Cultivo | Kc | Marco (m2/planta) | ETc (mm) | Riego bruto (mm) | Litros totales | L/planta |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in comparison["crops"]:
        lines.append(
            "| {crop} | {kc:.3f} | {plant_spacing_m2:.2f} | "
            "{etc_mm:.2f} | {gross_irrigation_mm:.2f} | {total_liters:.2f} | "
            "{liters_per_plant} |".format(
                crop=row["crop"],
                kc=row["kc"],
                plant_spacing_m2=row["plant_spacing_m2"],
                etc_mm=row["etc_mm"],
                gross_irrigation_mm=row["gross_irrigation_mm"],
                total_liters=row["total_liters"],
                liters_per_plant=format_optional_number(row["liters_per_plant"]),
            )
        )
    ranking = comparison["ranking"]
    lines.append("")
    lines.append(
        "Menor demanda: {lowest}. Mayor demanda: {highest}. Diferencia: {liters:.2f} L.".format(
            lowest=ranking["lowest_irrigation_crop"],
            highest=ranking["highest_irrigation_crop"],
            liters=ranking["difference_liters"],
        )
    )
    return "\n".join(lines)


def format_optional_number(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def comparison_to_export_rows(comparison: dict) -> list[dict]:
    ranking = {
        row["crop"]: position
        for position, row in enumerate(
            sorted(comparison["crops"], key=lambda item: item["total_liters"]),
            start=1,
        )
    }
    scenario = comparison["scenario"]
    rows = []
    for row in comparison["crops"]:
        rows.append(
            {
                "fecha": scenario["date"],
                "estacion": None,
                "nombre_estacion": None,
                "provincia": None,
                "cultivo": row["crop"],
                "fase": row["stage"],
                "superficie_m2": scenario["area_m2"],
                "eficiencia_riego": scenario["irrigation_efficiency"],
                "lluvia_efectiva_ratio": scenario["effective_rainfall_ratio"],
                "et0_mm": scenario["et0_mm"],
                "lluvia_mm": scenario["rain_mm"],
                "tmin_c": None,
                "tmax_c": None,
                "tmedia_c": None,
                "kc": row["kc"],
                "marco_m2_por_planta": row["plant_spacing_m2"],
                "etc_mm": row["etc_mm"],
                "riego_bruto_mm": row["gross_irrigation_mm"],
                "litros_totales": row["total_liters"],
                "litros_por_planta": row["liters_per_plant"],
                "ranking_demanda": ranking[row["crop"]],
            }
        )
    return rows


def reports_to_daily_export_rows(
    reports: list[IrrigationReport],
    station_id: str,
    station_name: str | None,
    province: str | None,
    effective_rainfall_ratio: float | None = None,
) -> list[dict]:
    rows = []
    if not reports:
        return rows
    day_count = len(reports[0].days)
    for day_index in range(day_count):
        day_rows = []
        for report in reports:
            day = report.days[day_index]
            day_rows.append(
                {
                    "fecha": day.date.isoformat(),
                    "estacion": station_id,
                    "nombre_estacion": station_name,
                    "provincia": province,
                    "cultivo": report.crop.name,
                    "fase": report.crop.stage,
                    "superficie_m2": report.system.area_m2,
                    "eficiencia_riego": report.system.efficiency,
                    "lluvia_efectiva_ratio": effective_rainfall_ratio,
                    "et0_mm": round(day.et0_mm, 2),
                    "lluvia_mm": round(day.rain_mm, 2),
                    "tmin_c": round(day.tmin_c, 2) if day.tmin_c is not None else None,
                    "tmax_c": round(day.tmax_c, 2) if day.tmax_c is not None else None,
                    "tmedia_c": round(day.tmean_c, 2) if day.tmean_c is not None else None,
                    "kc": round(report.crop.kc, 3),
                    "marco_m2_por_planta": report.crop.plant_spacing_m2,
                    "etc_mm": round(day.etc_mm, 2),
                    "riego_bruto_mm": round(day.gross_irrigation_mm, 2),
                    "litros_totales": round(day.liters_total, 2),
                    "litros_por_planta": round(day.liters_per_plant, 2)
                    if day.liters_per_plant is not None
                    else None,
                }
            )
        ranking = {
            row["cultivo"]: position
            for position, row in enumerate(
                sorted(day_rows, key=lambda item: item["litros_totales"]),
                start=1,
            )
        }
        for row in day_rows:
            row["ranking_demanda"] = ranking[row["cultivo"]]
            rows.append(row)
    return rows


def write_export(rows: list[dict], output_file: str, output_format: str) -> None:
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        with output_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=EXPORT_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        return
    if output_format == "json":
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(rows, file, ensure_ascii=False, indent=2)
            file.write("\n")
        return
    raise ValueError(f"Formato no soportado: {output_format}")


def infer_export_format(output_file: str) -> str:
    suffix = Path(output_file).suffix.lower()
    if suffix == ".json":
        return "json"
    return "csv"


def read_export_rows(input_file: str) -> list[dict]:
    input_path = Path(input_file)
    if input_path.suffix.lower() == ".json":
        with input_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            raise ValueError("El JSON de entrada debe contener una lista de filas")
        return data

    with input_path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def summarize_export_rows(rows: list[dict]) -> list[dict]:
    if not rows:
        return []

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        crop = str(row.get("cultivo", "")).strip()
        if not crop:
            continue
        grouped.setdefault(crop, []).append(row)

    summary_rows = []
    for crop, crop_rows in grouped.items():
        dates = sorted({str(row.get("fecha", "")) for row in crop_rows if row.get("fecha")})
        days = len(dates) or len(crop_rows)
        total_liters = sum(to_float(row.get("litros_totales")) for row in crop_rows)
        summary_rows.append(
            {
                "estacion": first_value(crop_rows, "estacion"),
                "nombre_estacion": first_value(crop_rows, "nombre_estacion"),
                "provincia": first_value(crop_rows, "provincia"),
                "fecha_inicio": dates[0] if dates else None,
                "fecha_fin": dates[-1] if dates else None,
                "cultivo": crop,
                "fase": first_value(crop_rows, "fase"),
                "dias_analizados": days,
                "et0_media_mm": round(average(crop_rows, "et0_mm"), 2),
                "lluvia_total_mm": round(sum(to_float(row.get("lluvia_mm")) for row in crop_rows), 2),
                "tmin_media_c": round(average(crop_rows, "tmin_c"), 2),
                "tmax_media_c": round(average(crop_rows, "tmax_c"), 2),
                "tmedia_media_c": round(average(crop_rows, "tmedia_c"), 2),
                "kc": round(average(crop_rows, "kc"), 3),
                "riego_total_litros": round(total_liters, 2),
                "riego_medio_litros_dia": round(total_liters / days, 2) if days else 0,
                "riego_medio_mm_dia": round(average(crop_rows, "riego_bruto_mm"), 2),
                "etc_media_mm_dia": round(average(crop_rows, "etc_mm"), 2),
                "litros_por_planta_medio": round(average(crop_rows, "litros_por_planta"), 2),
            }
        )

    summary_rows.sort(key=lambda row: row["riego_total_litros"])
    minimum_liters = summary_rows[0]["riego_total_litros"] if summary_rows else 0
    for index, row in enumerate(summary_rows, start=1):
        difference = row["riego_total_litros"] - minimum_liters
        row["diferencia_litros_vs_minimo"] = round(difference, 2)
        row["porcentaje_incremento_vs_minimo"] = (
            round((difference / minimum_liters) * 100, 2) if minimum_liters else 0
        )
        row["ranking_demanda"] = index
    return summary_rows


def write_summary(rows: list[dict], output_file: str, output_format: str) -> None:
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        with output_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        return
    if output_format == "json":
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(rows, file, ensure_ascii=False, indent=2)
            file.write("\n")
        return
    if output_format == "markdown":
        output_path.write_text(summary_to_markdown(rows), encoding="utf-8")
        return
    raise ValueError(f"Formato no soportado: {output_format}")


def summary_to_markdown(rows: list[dict]) -> str:
    lines = [
        "| Ranking | Cultivo | Dias | ET0 media (mm) | Lluvia total (mm) | Riego total (L) | Riego medio (L/dia) | Incremento vs minimo |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {ranking} | {cultivo} | {dias} | {et0:.2f} | {lluvia:.2f} | {total:.2f} | {medio:.2f} | {incremento:.2f}% |".format(
                ranking=row["ranking_demanda"],
                cultivo=row["cultivo"],
                dias=row["dias_analizados"],
                et0=row["et0_media_mm"],
                lluvia=row["lluvia_total_mm"],
                total=row["riego_total_litros"],
                medio=row["riego_medio_litros_dia"],
                incremento=row["porcentaje_incremento_vs_minimo"],
            )
        )
    if rows:
        lowest = rows[0]
        highest = rows[-1]
        lines.append("")
        lines.append(
            "Menor demanda: {lowest}. Mayor demanda: {highest}. Diferencia acumulada: {difference:.2f} L.".format(
                lowest=lowest["cultivo"],
                highest=highest["cultivo"],
                difference=highest["diferencia_litros_vs_minimo"],
            )
        )
    return "\n".join(lines) + "\n"


def infer_summary_format(output_file: str) -> str:
    suffix = Path(output_file).suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    return "csv"


def first_value(rows: list[dict], key: str) -> str | None:
    for row in rows:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def average(rows: list[dict], key: str) -> float:
    values = [to_float(row.get(key)) for row in rows if row.get(key) not in (None, "")]
    if not values:
        return 0.0
    return sum(values) / len(values)


def to_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace(",", "."))


def optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return to_float(value)


def crop_defaults_to_dict() -> dict:
    return {
        crop_name: {
            "plant_spacing_m2": crop_data["plant_spacing_m2"],
            "kc": crop_data["kc"],
        }
        for crop_name, crop_data in CROP_DEFAULTS.items()
    }


if __name__ == "__main__":
    raise SystemExit(main())
