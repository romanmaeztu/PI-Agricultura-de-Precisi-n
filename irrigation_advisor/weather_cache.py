from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Iterator

from .aemet_client import Station
from .models import WeatherDay


DEFAULT_CACHE_DB = "data/aemet_cache.sqlite"


@dataclass(frozen=True)
class WeatherSource:
    weather_days: list[WeatherDay]
    station_id: str
    station_name: str | None
    province: str | None


class AemetCache:
    def __init__(self, db_file: str = DEFAULT_CACHE_DB) -> None:
        self.db_file = Path(db_file)
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stations (
                    indicativo TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    provincia TEXT NOT NULL,
                    latitude_deg REAL,
                    longitude_deg REAL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_weather (
                    estacion TEXT NOT NULL,
                    fecha TEXT NOT NULL,
                    nombre_estacion TEXT,
                    provincia TEXT,
                    et0_mm REAL NOT NULL,
                    lluvia_mm REAL NOT NULL,
                    tmin_c REAL,
                    tmax_c REAL,
                    tmedia_c REAL,
                    source TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (estacion, fecha)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stations_province ON stations (provincia)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_date ON daily_weather (fecha)")

    def upsert_stations(self, stations: Iterable[Station]) -> int:
        rows = [
            (
                station.indicativo,
                station.nombre,
                station.provincia,
                station.latitude_deg,
                station.longitude_deg,
                timestamp_now(),
            )
            for station in stations
            if station.indicativo
        ]
        if not rows:
            return 0
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO stations (
                    indicativo, nombre, provincia, latitude_deg, longitude_deg, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(indicativo) DO UPDATE SET
                    nombre = excluded.nombre,
                    provincia = excluded.provincia,
                    latitude_deg = excluded.latitude_deg,
                    longitude_deg = excluded.longitude_deg,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
        return len(rows)

    def get_stations(self) -> list[Station]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT indicativo, nombre, provincia, latitude_deg, longitude_deg
                FROM stations
                ORDER BY provincia, nombre, indicativo
                """
            ).fetchall()
        return [station_from_row(row) for row in rows]

    def get_station_inventory(self) -> list[Station]:
        return self.get_stations()

    def find_station(self, station_id: str) -> Station | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT indicativo, nombre, provincia, latitude_deg, longitude_deg
                FROM stations
                WHERE indicativo = ?
                """,
                (station_id,),
            ).fetchone()
        return station_from_row(row) if row else None

    def upsert_weather(self, station: Station, weather_days: Iterable[WeatherDay], source: str = "aemet") -> int:
        rows = [
            (
                station.indicativo,
                day.date.isoformat(),
                station.nombre,
                station.provincia,
                day.et0_mm,
                day.rain_mm,
                day.tmin_c,
                day.tmax_c,
                day.tmean_c,
                source,
                timestamp_now(),
            )
            for day in weather_days
        ]
        if not rows:
            return 0
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO daily_weather (
                    estacion, fecha, nombre_estacion, provincia, et0_mm, lluvia_mm,
                    tmin_c, tmax_c, tmedia_c, source, fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(estacion, fecha) DO UPDATE SET
                    nombre_estacion = excluded.nombre_estacion,
                    provincia = excluded.provincia,
                    et0_mm = excluded.et0_mm,
                    lluvia_mm = excluded.lluvia_mm,
                    tmin_c = excluded.tmin_c,
                    tmax_c = excluded.tmax_c,
                    tmedia_c = excluded.tmedia_c,
                    source = excluded.source,
                    fetched_at = excluded.fetched_at
                """,
                rows,
            )
        return len(rows)

    def get_weather_days(self, station_id: str, start: date, end: date) -> list[WeatherDay]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT fecha, et0_mm, lluvia_mm, tmin_c, tmax_c, tmedia_c
                FROM daily_weather
                WHERE estacion = ? AND fecha BETWEEN ? AND ?
                ORDER BY fecha
                """,
                (station_id, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [
            WeatherDay(
                date=date.fromisoformat(row["fecha"]),
                et0_mm=float(row["et0_mm"]),
                rain_mm=float(row["lluvia_mm"]),
                tmin_c=row["tmin_c"],
                tmax_c=row["tmax_c"],
                tmean_c=row["tmedia_c"],
            )
            for row in rows
        ]

    def get_weather_source(self, station_id: str, start: date, end: date) -> WeatherSource:
        station = self.find_station(station_id)
        weather_days = self.get_weather_days(station_id=station_id, start=start, end=end)
        missing = missing_dates(weather_days=weather_days, start=start, end=end)
        if missing:
            first = missing[0].isoformat()
            last = missing[-1].isoformat()
            raise ValueError(
                f"La cache no contiene todos los dias solicitados para {station_id}. "
                f"Faltan {len(missing)} dias ({first} a {last}). Ejecuta sync-aemet-cache."
            )
        return WeatherSource(
            weather_days=weather_days,
            station_id=station_id,
            station_name=station.nombre if station else None,
            province=station.provincia if station else None,
        )

    def missing_ranges(self, station_id: str, start: date, end: date) -> list[tuple[date, date]]:
        existing_days = self.get_weather_days(station_id=station_id, start=start, end=end)
        return compact_date_ranges(missing_dates(weather_days=existing_days, start=start, end=end))

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            station_count = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
            weather_count = conn.execute("SELECT COUNT(*) FROM daily_weather").fetchone()[0]
        return {"stations": int(station_count), "daily_weather": int(weather_count)}

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def station_from_row(row: sqlite3.Row) -> Station:
    return Station(
        indicativo=str(row["indicativo"]),
        nombre=str(row["nombre"]),
        provincia=str(row["provincia"]),
        latitude_deg=row["latitude_deg"],
        longitude_deg=row["longitude_deg"],
    )


def timestamp_now() -> str:
    return datetime.now(UTC).isoformat()


def iter_dates(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def missing_dates(weather_days: list[WeatherDay], start: date, end: date) -> list[date]:
    found = {day.date for day in weather_days}
    return [day for day in iter_dates(start, end) if day not in found]


def compact_date_ranges(days: list[date]) -> list[tuple[date, date]]:
    if not days:
        return []
    sorted_days = sorted(days)
    ranges: list[tuple[date, date]] = []
    range_start = sorted_days[0]
    previous = sorted_days[0]
    for current in sorted_days[1:]:
        if current == previous + timedelta(days=1):
            previous = current
            continue
        ranges.append((range_start, previous))
        range_start = current
        previous = current
    ranges.append((range_start, previous))
    return ranges
