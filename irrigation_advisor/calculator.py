from __future__ import annotations

import math
from datetime import date
from typing import Iterable, Optional

from .models import (
    CROP_DEFAULTS,
    SOIL_DEFAULTS,
    CropProfile,
    DayRecommendation,
    IrrigationReport,
    IrrigationSystem,
    SoilProfile,
    WeatherDay,
)


def build_soil_profile(
    soil: str,
    root_depth_m: float = 0.60,
    field_capacity: Optional[float] = None,
    wilting_point: Optional[float] = None,
    max_depletion_fraction: float = 0.50,
) -> SoilProfile:
    key = soil.lower().replace(" ", "_")
    if field_capacity is None or wilting_point is None:
        if key not in SOIL_DEFAULTS:
            valid = ", ".join(sorted(SOIL_DEFAULTS))
            raise ValueError(f"Tipo de suelo no reconocido: {soil}. Opciones: {valid}")
        default_fc, default_wp = SOIL_DEFAULTS[key]
        field_capacity = default_fc if field_capacity is None else field_capacity
        wilting_point = default_wp if wilting_point is None else wilting_point

    if not 0 < wilting_point < field_capacity < 0.70:
        raise ValueError("La relacion debe cumplir 0 < PMP < CC < 0.70")
    if root_depth_m <= 0:
        raise ValueError("La profundidad de raices debe ser positiva")
    if not 0 < max_depletion_fraction <= 1:
        raise ValueError("La fraccion de agotamiento debe estar entre 0 y 1")

    return SoilProfile(
        name=key,
        field_capacity=field_capacity,
        wilting_point=wilting_point,
        root_depth_m=root_depth_m,
        max_depletion_fraction=max_depletion_fraction,
    )


def build_crop_profile(crop: str, stage: str, kc: Optional[float] = None) -> CropProfile:
    crop_key = crop.lower().replace(" ", "_")
    stage_key = stage.lower().replace(" ", "_")
    if crop_key not in CROP_DEFAULTS:
        valid = ", ".join(sorted(CROP_DEFAULTS))
        raise ValueError(f"Cultivo no reconocido: {crop}. Opciones: {valid}")

    defaults = CROP_DEFAULTS[crop_key]
    kc_by_stage = defaults["kc"]
    if not isinstance(kc_by_stage, dict):
        raise ValueError(f"Perfil de cultivo invalido: {crop_key}")

    if kc is None:
        if stage_key not in kc_by_stage:
            valid = {
                crop_name: sorted(crop_data["kc"])
                for crop_name, crop_data in CROP_DEFAULTS.items()
            }
            raise ValueError(f"Cultivo/fase no reconocido: {crop}/{stage}. Opciones: {valid}")
        kc = float(kc_by_stage[stage_key])
    if not 0 < kc < 2:
        raise ValueError("Kc debe estar entre 0 y 2")
    return CropProfile(
        name=crop_key,
        stage=stage_key,
        kc=kc,
        root_depth_m=float(defaults["root_depth_m"]),
        plant_spacing_m2=float(defaults["plant_spacing_m2"]),
        max_depletion_fraction=float(defaults["max_depletion_fraction"]),
    )


def estimate_et0_hargreaves(
    tmin_c: float,
    tmax_c: float,
    latitude_deg: float,
    day: date,
) -> float:
    if tmax_c < tmin_c:
        raise ValueError("tmax_c no puede ser menor que tmin_c")
    tmean_c = (tmax_c + tmin_c) / 2.0
    ra = extraterrestrial_radiation_mm_day(latitude_deg=latitude_deg, day_of_year=day.timetuple().tm_yday)
    et0 = 0.0023 * (tmean_c + 17.8) * math.sqrt(max(0.0, tmax_c - tmin_c)) * ra
    return max(0.0, et0)


def extraterrestrial_radiation_mm_day(latitude_deg: float, day_of_year: int) -> float:
    lat_rad = math.radians(latitude_deg)
    dr = 1 + 0.033 * math.cos((2 * math.pi / 365) * day_of_year)
    solar_declination = 0.409 * math.sin((2 * math.pi / 365) * day_of_year - 1.39)
    sunset_angle = math.acos(
        max(-1.0, min(1.0, -math.tan(lat_rad) * math.tan(solar_declination)))
    )
    gsc = 0.0820
    ra_mj_m2_day = (
        (24 * 60 / math.pi)
        * gsc
        * dr
        * (
            sunset_angle * math.sin(lat_rad) * math.sin(solar_declination)
            + math.cos(lat_rad) * math.cos(solar_declination) * math.sin(sunset_angle)
        )
    )
    return ra_mj_m2_day * 0.408


def effective_rainfall(rain_mm: float, ratio: float = 0.80) -> float:
    if rain_mm <= 0:
        return 0.0
    if not 0 <= ratio <= 1:
        raise ValueError("El ratio de lluvia efectiva debe estar entre 0 y 1")
    return rain_mm * ratio


def first_irrigation_to_field_capacity_mm(
    soil: SoilProfile,
    current_soil_moisture: float,
    efficiency: float,
) -> float:
    if not 0 <= current_soil_moisture < 0.70:
        raise ValueError("La humedad actual debe estar entre 0 y 0.70")
    if current_soil_moisture >= soil.field_capacity:
        return 0.0
    net_mm = (soil.field_capacity - current_soil_moisture) * soil.root_depth_m * 1000.0
    return net_mm / efficiency


def recommend_irrigation(
    weather_days: Iterable[WeatherDay],
    crop: CropProfile,
    soil: SoilProfile,
    system: IrrigationSystem,
    effective_rainfall_ratio: float = 0.80,
    current_soil_moisture: Optional[float] = None,
) -> IrrigationReport:
    if system.area_m2 <= 0:
        raise ValueError("La superficie debe ser positiva")
    if not 0 < system.efficiency <= 1:
        raise ValueError("La eficiencia debe estar entre 0 y 1")

    recommendations: list[DayRecommendation] = []
    for day in weather_days:
        etc_mm = day.et0_mm * crop.kc
        eff_rain_mm = effective_rainfall(day.rain_mm, effective_rainfall_ratio)
        net_mm = max(0.0, etc_mm - eff_rain_mm)
        gross_mm = net_mm / system.efficiency
        liters_total = gross_mm * system.area_m2
        liters_per_plant = None

        if system.plant_spacing_m2:
            liters_per_plant = gross_mm * system.plant_spacing_m2

        recommendations.append(
            DayRecommendation(
                date=day.date,
                et0_mm=day.et0_mm,
                tmin_c=day.tmin_c,
                tmax_c=day.tmax_c,
                tmean_c=day.tmean_c,
                kc=crop.kc,
                etc_mm=etc_mm,
                rain_mm=day.rain_mm,
                effective_rain_mm=eff_rain_mm,
                net_irrigation_mm=net_mm,
                gross_irrigation_mm=gross_mm,
                liters_total=liters_total,
                liters_per_plant=liters_per_plant,
            )
        )

    first_mm = None
    if current_soil_moisture is not None:
        first_mm = first_irrigation_to_field_capacity_mm(
            soil=soil,
            current_soil_moisture=current_soil_moisture,
            efficiency=system.efficiency,
        )

    return IrrigationReport(
        crop=crop,
        soil=soil,
        system=system,
        days=recommendations,
        first_irrigation_mm=first_mm,
    )
