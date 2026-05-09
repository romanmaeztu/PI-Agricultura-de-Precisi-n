from __future__ import annotations

import argparse
import json
from datetime import date
from typing import Sequence

from .aemet_client import AemetClient
from .calculator import build_crop_profile, build_soil_profile, recommend_irrigation
from .models import CROP_DEFAULTS, IrrigationReport, IrrigationSystem, WeatherDay


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
        weather_days = [
            WeatherDay(
                date=date.fromisoformat(args.date),
                et0_mm=args.et0,
                rain_mm=args.rain_mm,
            )
        ]
        reports = compare_crop_reports(args=args, weather_days=weather_days)
        comparison = comparison_to_dict(
            reports=reports,
            date_value=args.date,
            et0_mm=args.et0,
            rain_mm=args.rain_mm,
            soil_name=args.soil,
            stage=args.stage,
        )
        if args.output == "markdown":
            print(comparison_to_markdown(comparison))
        else:
            print(json.dumps(comparison, ensure_ascii=False, indent=2))
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
