from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path
from typing import Sequence

from .aemet_client import AemetClient
from .calculator import build_crop_profile, build_soil_profile, recommend_irrigation
from .models import CROP_DEFAULTS, IrrigationReport, IrrigationSystem, WeatherDay


EXPORT_FIELDNAMES = [
    "fecha",
    "estacion",
    "nombre_estacion",
    "provincia",
    "cultivo",
    "fase",
    "suelo",
    "et0_mm",
    "lluvia_mm",
    "tmin_c",
    "tmax_c",
    "tmedia_c",
    "kc",
    "profundidad_raices_m",
    "marco_m2_por_planta",
    "agua_facilmente_disponible_mm",
    "etc_mm",
    "riego_bruto_mm",
    "litros_totales",
    "litros_por_planta",
    "horas_riego",
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
    "suelo",
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
    "horas_riego_medias",
    "diferencia_litros_vs_minimo",
    "porcentaje_incremento_vs_minimo",
    "ranking_demanda",
]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "stations":
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
        client = AemetClient()
        station = client.find_station(args.station)
        latitude = args.latitude or (station.latitude_deg if station else None)
        weather_days = client.get_daily_climate(
            station_id=args.station,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
            latitude_deg=latitude,
        )
        reports = compare_crop_reports(args=args, weather_days=weather_days)
        rows = reports_to_daily_export_rows(
            reports=reports,
            soil_name=args.soil,
            station_id=args.station,
            station_name=station.nombre if station else None,
            province=station.provincia if station else None,
        )
        output_format = args.file_format or infer_export_format(args.output_file)
        write_export(rows=rows, output_file=args.output_file, output_format=output_format)
        print(
            json.dumps(
                {
                    "output_file": str(Path(args.output_file)),
                    "format": output_format,
                    "station": args.station,
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

    crop = build_crop_profile(crop=args.crop, stage=args.stage, kc=args.kc)
    root_depth_m = args.root_depth_m if args.root_depth_m is not None else crop.root_depth_m
    max_depletion_fraction = (
        args.max_depletion_fraction
        if args.max_depletion_fraction is not None
        else crop.max_depletion_fraction
    )
    soil = build_soil_profile(
        soil=args.soil,
        root_depth_m=root_depth_m,
        field_capacity=args.field_capacity,
        wilting_point=args.wilting_point,
        max_depletion_fraction=max_depletion_fraction,
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
        emitters_per_plant=args.emitters_per_plant,
        emitter_flow_lph=args.emitter_flow_lph,
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
        current_soil_moisture=args.current_soil_moisture,
    )
    print(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="irrigation-advisor",
        description="Recomendacion de riego a partir de AEMET, suelo, cultivo y sistema de riego.",
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

    subparsers.add_parser("crops", help="Muestra los tres perfiles de cultivo configurados.")

    compare = subparsers.add_parser("compare", help="Compara riego de olivar, citricos y almendro.")
    compare.add_argument("--date", default=date.today().isoformat())
    compare.add_argument("--et0", type=float, required=True)
    compare.add_argument("--rain-mm", type=float, default=0.0)
    compare.add_argument("--stage", required=True, help="Fase comun: inicio, desarrollo, media, madurez.")
    compare.add_argument("--soil", required=True, help="Tipo: arenoso, franco_arenoso, franco, franco_arcilloso, arcilloso.")
    compare.add_argument("--area-m2", type=float, required=True, help="Superficie de la parcela en m2.")
    compare.add_argument("--field-capacity", type=float)
    compare.add_argument("--wilting-point", type=float)
    compare.add_argument("--irrigation-efficiency", type=float, default=0.90)
    compare.add_argument("--effective-rainfall-ratio", type=float, default=0.80)
    compare.add_argument("--current-soil-moisture", type=float, help="Humedad volumetrica actual, por ejemplo 0.18.")
    compare.add_argument("--emitters-per-plant", type=int)
    compare.add_argument("--emitter-flow-lph", type=float)
    compare.add_argument("--output", choices=["json", "markdown"], default="json")

    export = subparsers.add_parser("export-comparison", help="Exporta la comparativa de cultivos a CSV o JSON.")
    export.add_argument("--date", default=date.today().isoformat())
    export.add_argument("--et0", type=float, required=True)
    export.add_argument("--rain-mm", type=float, default=0.0)
    export.add_argument("--stage", required=True, help="Fase comun: inicio, desarrollo, media, madurez.")
    export.add_argument("--soil", required=True, help="Tipo: arenoso, franco_arenoso, franco, franco_arcilloso, arcilloso.")
    export.add_argument("--area-m2", type=float, required=True, help="Superficie de la parcela en m2.")
    export.add_argument("--field-capacity", type=float)
    export.add_argument("--wilting-point", type=float)
    export.add_argument("--irrigation-efficiency", type=float, default=0.90)
    export.add_argument("--effective-rainfall-ratio", type=float, default=0.80)
    export.add_argument("--current-soil-moisture", type=float, help="Humedad volumetrica actual, por ejemplo 0.18.")
    export.add_argument("--emitters-per-plant", type=int)
    export.add_argument("--emitter-flow-lph", type=float)
    export.add_argument("--output-file", default="data/resultados/comparativa_riego.csv")
    export.add_argument("--file-format", choices=["csv", "json"], help="Si se omite, se infiere por extension.")

    export_aemet = subparsers.add_parser(
        "export-aemet-comparison",
        help="Exporta comparativa diaria de cultivos con datos reales AEMET.",
    )
    export_aemet.add_argument("--station", required=True, help="Indicativo de estacion AEMET.")
    export_aemet.add_argument("--start", required=True, help="Fecha inicial YYYY-MM-DD.")
    export_aemet.add_argument("--end", required=True, help="Fecha final YYYY-MM-DD.")
    export_aemet.add_argument("--latitude", type=float, help="Latitud decimal si AEMET no aporta ET0.")
    export_aemet.add_argument("--stage", required=True, help="Fase comun: inicio, desarrollo, media, madurez.")
    export_aemet.add_argument("--soil", required=True, help="Tipo: arenoso, franco_arenoso, franco, franco_arcilloso, arcilloso.")
    export_aemet.add_argument("--area-m2", type=float, required=True, help="Superficie de la parcela en m2.")
    export_aemet.add_argument("--field-capacity", type=float)
    export_aemet.add_argument("--wilting-point", type=float)
    export_aemet.add_argument("--irrigation-efficiency", type=float, default=0.90)
    export_aemet.add_argument("--effective-rainfall-ratio", type=float, default=0.80)
    export_aemet.add_argument("--current-soil-moisture", type=float, help="Humedad volumetrica actual, por ejemplo 0.18.")
    export_aemet.add_argument("--emitters-per-plant", type=int)
    export_aemet.add_argument("--emitter-flow-lph", type=float)
    export_aemet.add_argument("--output-file", default="data/resultados/comparativa_aemet.csv")
    export_aemet.add_argument("--file-format", choices=["csv", "json"], help="Si se omite, se infiere por extension.")

    summary = subparsers.add_parser("summarize-results", help="Resume un CSV/JSON de riego por cultivo.")
    summary.add_argument("--input-file", required=True)
    summary.add_argument("--output-file", default="data/resultados/resumen_riego.csv")
    summary.add_argument("--file-format", choices=["csv", "json", "markdown"], help="Si se omite, se infiere por extension.")
    return parser


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--crop", required=True, help="Cultivo: olivar, citricos, almendro...")
    parser.add_argument("--stage", required=True, help="Fase: inicio, desarrollo, media, madurez.")
    parser.add_argument("--soil", required=True, help="Tipo: arenoso, franco_arenoso, franco, franco_arcilloso, arcilloso.")
    parser.add_argument("--area-m2", type=float, required=True, help="Superficie de la parcela en m2.")
    parser.add_argument("--root-depth-m", type=float, help="Sobrescribe la profundidad de raices del cultivo.")
    parser.add_argument("--field-capacity", type=float)
    parser.add_argument("--wilting-point", type=float)
    parser.add_argument("--max-depletion-fraction", type=float, help="Sobrescribe la fraccion de agotamiento del cultivo.")
    parser.add_argument("--irrigation-efficiency", type=float, default=0.90)
    parser.add_argument("--effective-rainfall-ratio", type=float, default=0.80)
    parser.add_argument("--current-soil-moisture", type=float, help="Humedad volumetrica actual, por ejemplo 0.18.")
    parser.add_argument("--plant-spacing-m2", type=float, help="Sobrescribe la superficie asignada por planta.")
    parser.add_argument("--emitters-per-plant", type=int)
    parser.add_argument("--emitter-flow-lph", type=float)
    parser.add_argument("--kc", type=float, help="Sobrescribe el Kc por defecto.")


def report_to_dict(report: IrrigationReport) -> dict:
    return {
        "crop": {
            "name": report.crop.name,
            "stage": report.crop.stage,
            "kc": round(report.crop.kc, 3),
            "default_root_depth_m": report.crop.root_depth_m,
            "default_plant_spacing_m2": report.crop.plant_spacing_m2,
            "default_max_depletion_fraction": report.crop.max_depletion_fraction,
        },
        "soil": {
            "name": report.soil.name,
            "field_capacity": report.soil.field_capacity,
            "wilting_point": report.soil.wilting_point,
            "root_depth_m": report.soil.root_depth_m,
            "total_available_water_mm": round(report.soil.total_available_water_mm, 2),
            "readily_available_water_mm": round(report.soil.readily_available_water_mm, 2),
        },
        "system": {
            "area_m2": report.system.area_m2,
            "efficiency": report.system.efficiency,
            "plant_spacing_m2": report.system.plant_spacing_m2,
            "plants": round(report.system.plants, 2) if report.system.plants else None,
            "flow_per_plant_lph": report.system.flow_per_plant_lph,
        },
        "first_irrigation_mm": round(report.first_irrigation_mm, 2)
        if report.first_irrigation_mm is not None
        else None,
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
                "runtime_hours": round(item.runtime_hours, 2)
                if item.runtime_hours is not None
                else None,
            }
            for item in report.days
        ],
    }


def compare_crop_reports(args: argparse.Namespace, weather_days: list[WeatherDay]) -> list[IrrigationReport]:
    reports: list[IrrigationReport] = []
    for crop_name in CROP_DEFAULTS:
        crop = build_crop_profile(crop=crop_name, stage=args.stage)
        soil = build_soil_profile(
            soil=args.soil,
            root_depth_m=crop.root_depth_m,
            field_capacity=args.field_capacity,
            wilting_point=args.wilting_point,
            max_depletion_fraction=crop.max_depletion_fraction,
        )
        system = IrrigationSystem(
            area_m2=args.area_m2,
            efficiency=args.irrigation_efficiency,
            plant_spacing_m2=crop.plant_spacing_m2,
            emitters_per_plant=args.emitters_per_plant,
            emitter_flow_lph=args.emitter_flow_lph,
        )
        reports.append(
            recommend_irrigation(
                weather_days=weather_days,
                crop=crop,
                soil=soil,
                system=system,
                effective_rainfall_ratio=args.effective_rainfall_ratio,
                current_soil_moisture=args.current_soil_moisture,
            )
        )
    return reports


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
        soil_name=args.soil,
        stage=args.stage,
    )


def comparison_to_dict(
    reports: list[IrrigationReport],
    date_value: str,
    et0_mm: float,
    rain_mm: float,
    soil_name: str,
    stage: str,
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
            "soil": soil_name,
            "stage": stage,
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
        "root_depth_m": report.crop.root_depth_m,
        "plant_spacing_m2": report.crop.plant_spacing_m2,
        "readily_available_water_mm": round(report.soil.readily_available_water_mm, 2),
        "etc_mm": round(first_day.etc_mm, 2),
        "gross_irrigation_mm": round(first_day.gross_irrigation_mm, 2),
        "total_gross_irrigation_mm": round(report.total_gross_irrigation_mm, 2),
        "total_liters": round(report.total_liters, 2),
        "liters_per_plant": round(first_day.liters_per_plant, 2)
        if first_day.liters_per_plant is not None
        else None,
        "runtime_hours": round(first_day.runtime_hours, 2)
        if first_day.runtime_hours is not None
        else None,
    }


def comparison_to_markdown(comparison: dict) -> str:
    lines = [
        "| Cultivo | Kc | Raices (m) | Marco (m2/planta) | ETc (mm) | Riego bruto (mm) | Litros totales | L/planta | Horas |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in comparison["crops"]:
        lines.append(
            "| {crop} | {kc:.3f} | {root_depth_m:.2f} | {plant_spacing_m2:.2f} | "
            "{etc_mm:.2f} | {gross_irrigation_mm:.2f} | {total_liters:.2f} | "
            "{liters_per_plant} | {runtime_hours} |".format(
                crop=row["crop"],
                kc=row["kc"],
                root_depth_m=row["root_depth_m"],
                plant_spacing_m2=row["plant_spacing_m2"],
                etc_mm=row["etc_mm"],
                gross_irrigation_mm=row["gross_irrigation_mm"],
                total_liters=row["total_liters"],
                liters_per_plant=format_optional_number(row["liters_per_plant"]),
                runtime_hours=format_optional_number(row["runtime_hours"]),
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
                "suelo": scenario["soil"],
                "et0_mm": scenario["et0_mm"],
                "lluvia_mm": scenario["rain_mm"],
                "tmin_c": None,
                "tmax_c": None,
                "tmedia_c": None,
                "kc": row["kc"],
                "profundidad_raices_m": row["root_depth_m"],
                "marco_m2_por_planta": row["plant_spacing_m2"],
                "agua_facilmente_disponible_mm": row["readily_available_water_mm"],
                "etc_mm": row["etc_mm"],
                "riego_bruto_mm": row["gross_irrigation_mm"],
                "litros_totales": row["total_liters"],
                "litros_por_planta": row["liters_per_plant"],
                "horas_riego": row["runtime_hours"],
                "ranking_demanda": ranking[row["crop"]],
            }
        )
    return rows


def reports_to_daily_export_rows(
    reports: list[IrrigationReport],
    soil_name: str,
    station_id: str,
    station_name: str | None,
    province: str | None,
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
                    "suelo": soil_name,
                    "et0_mm": round(day.et0_mm, 2),
                    "lluvia_mm": round(day.rain_mm, 2),
                    "tmin_c": round(day.tmin_c, 2) if day.tmin_c is not None else None,
                    "tmax_c": round(day.tmax_c, 2) if day.tmax_c is not None else None,
                    "tmedia_c": round(day.tmean_c, 2) if day.tmean_c is not None else None,
                    "kc": round(report.crop.kc, 3),
                    "profundidad_raices_m": report.crop.root_depth_m,
                    "marco_m2_por_planta": report.crop.plant_spacing_m2,
                    "agua_facilmente_disponible_mm": round(report.soil.readily_available_water_mm, 2),
                    "etc_mm": round(day.etc_mm, 2),
                    "riego_bruto_mm": round(day.gross_irrigation_mm, 2),
                    "litros_totales": round(day.liters_total, 2),
                    "litros_por_planta": round(day.liters_per_plant, 2)
                    if day.liters_per_plant is not None
                    else None,
                    "horas_riego": round(day.runtime_hours, 2)
                    if day.runtime_hours is not None
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
                "suelo": first_value(crop_rows, "suelo"),
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
                "horas_riego_medias": round(average(crop_rows, "horas_riego"), 2),
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


def crop_defaults_to_dict() -> dict:
    return {
        crop_name: {
            "root_depth_m": crop_data["root_depth_m"],
            "plant_spacing_m2": crop_data["plant_spacing_m2"],
            "max_depletion_fraction": crop_data["max_depletion_fraction"],
            "kc": crop_data["kc"],
        }
        for crop_name, crop_data in CROP_DEFAULTS.items()
    }


if __name__ == "__main__":
    raise SystemExit(main())
