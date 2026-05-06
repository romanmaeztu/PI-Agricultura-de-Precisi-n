from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


SOIL_DEFAULTS: dict[str, tuple[float, float]] = {
    "arenoso": (0.10, 0.05),
    "franco_arenoso": (0.15, 0.07),
    "franco": (0.25, 0.12),
    "franco_arcilloso": (0.31, 0.16),
    "arcilloso": (0.37, 0.22),
}


CROP_KC_DEFAULTS: dict[str, dict[str, float]] = {
    "olivar": {
        "inicio": 0.65,
        "desarrollo": 0.70,
        "media": 0.70,
        "madurez": 0.65,
    },
    "citricos": {
        "inicio": 0.65,
        "desarrollo": 0.70,
        "media": 0.75,
        "madurez": 0.70,
    },
    "almendro": {
        "inicio": 0.50,
        "desarrollo": 0.75,
        "media": 0.90,
        "madurez": 0.65,
    },
}


@dataclass(frozen=True)
class SoilProfile:
    name: str
    field_capacity: float
    wilting_point: float
    root_depth_m: float = 0.60
    max_depletion_fraction: float = 0.50

    @property
    def total_available_water_mm(self) -> float:
        return max(0.0, (self.field_capacity - self.wilting_point) * self.root_depth_m * 1000.0)

    @property
    def readily_available_water_mm(self) -> float:
        return self.total_available_water_mm * self.max_depletion_fraction


@dataclass(frozen=True)
class CropProfile:
    name: str
    stage: str
    kc: float


@dataclass(frozen=True)
class IrrigationSystem:
    area_m2: float
    efficiency: float = 0.90
    plant_spacing_m2: Optional[float] = None
    emitters_per_plant: Optional[int] = None
    emitter_flow_lph: Optional[float] = None

    @property
    def plants(self) -> Optional[float]:
        if not self.plant_spacing_m2 or self.plant_spacing_m2 <= 0:
            return None
        return self.area_m2 / self.plant_spacing_m2

    @property
    def flow_per_plant_lph(self) -> Optional[float]:
        if not self.emitters_per_plant or not self.emitter_flow_lph:
            return None
        return self.emitters_per_plant * self.emitter_flow_lph


@dataclass(frozen=True)
class WeatherDay:
    date: date
    et0_mm: float
    rain_mm: float = 0.0
    tmin_c: Optional[float] = None
    tmax_c: Optional[float] = None
    tmean_c: Optional[float] = None


@dataclass(frozen=True)
class DayRecommendation:
    date: date
    et0_mm: float
    kc: float
    etc_mm: float
    rain_mm: float
    effective_rain_mm: float
    net_irrigation_mm: float
    gross_irrigation_mm: float
    liters_total: float
    liters_per_plant: Optional[float]
    runtime_hours: Optional[float]


@dataclass(frozen=True)
class IrrigationReport:
    crop: CropProfile
    soil: SoilProfile
    system: IrrigationSystem
    days: list[DayRecommendation]
    first_irrigation_mm: Optional[float] = None

    @property
    def total_gross_irrigation_mm(self) -> float:
        return sum(day.gross_irrigation_mm for day in self.days)

    @property
    def total_liters(self) -> float:
        return sum(day.liters_total for day in self.days)

