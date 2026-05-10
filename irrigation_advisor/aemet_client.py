from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .calculator import estimate_et0_hargreaves
from .models import WeatherDay


BASE_URL = "https://opendata.aemet.es/opendata/api"


class AemetError(RuntimeError):
    """Raised when AEMET OpenData cannot return usable data."""


@dataclass(frozen=True)
class Station:
    indicativo: str
    nombre: str
    provincia: str
    latitude_deg: Optional[float]
    longitude_deg: Optional[float]


class AemetClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = BASE_URL, timeout: int = 30) -> None:
        load_env_file()
        self.api_key = api_key or os.getenv("AEMET_API_KEY")
        if not self.api_key:
            raise AemetError("Falta AEMET_API_KEY. Definela como variable de entorno.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_station_inventory(self) -> list[Station]:
        data = self._get_aemet_resource("/valores/climatologicos/inventarioestaciones/todasestaciones/")
        return [parse_station(item) for item in data]

    def get_daily_climate(
        self,
        station_id: str,
        start: date,
        end: date,
        latitude_deg: Optional[float] = None,
    ) -> list[WeatherDay]:
        if end < start:
            raise ValueError("La fecha final no puede ser anterior a la inicial")

        endpoint = (
            "/valores/climatologicos/diarios/datos/"
            f"fechaini/{quote(format_aemet_date(start), safe='')}/"
            f"fechafin/{quote(format_aemet_date(end), safe='')}/"
            f"estacion/{quote(station_id)}"
        )
        rows = self._get_aemet_resource(endpoint)
        days: list[WeatherDay] = []
        for row in rows:
            record_date = date.fromisoformat(row["fecha"])
            rain_mm = parse_aemet_float(row.get("prec"), default=0.0)
            tmin = parse_aemet_float(row.get("tmin"))
            tmax = parse_aemet_float(row.get("tmax"))
            tmean = parse_aemet_float(row.get("tmed"))
            et0 = parse_aemet_float(row.get("et0"))

            if et0 is None:
                if latitude_deg is None or tmin is None or tmax is None:
                    raise AemetError(
                        "AEMET no aporta ET0 en esta respuesta. Indica latitud o usa modo manual."
                    )
                et0 = estimate_et0_hargreaves(
                    tmin_c=tmin,
                    tmax_c=tmax,
                    latitude_deg=latitude_deg,
                    day=record_date,
                )

            days.append(
                WeatherDay(
                    date=record_date,
                    et0_mm=et0,
                    rain_mm=rain_mm,
                    tmin_c=tmin,
                    tmax_c=tmax,
                    tmean_c=tmean,
                )
            )
        return days

    def find_station(self, station_id: str) -> Optional[Station]:
        return next(
            (station for station in self.get_station_inventory() if station.indicativo == station_id),
            None,
        )

    def _get_aemet_resource(self, endpoint: str) -> Any:
        metadata = self._request_json(f"{self.base_url}{endpoint}", params={"api_key": self.api_key})
        status = int(metadata.get("estado", 0))
        if status != 200:
            message = metadata.get("descripcion", "respuesta no valida")
            raise AemetError(f"AEMET devolvio estado {status}: {message}")

        data_url = metadata.get("datos")
        if not data_url:
            raise AemetError("La respuesta de AEMET no contiene URL temporal de datos")
        return self._request_json(data_url)

    def _request_json(self, url: str, params: Optional[dict[str, str]] = None) -> Any:
        if params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(params)}"
        request = Request(url, headers={"cache-control": "no-cache", "accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read()
        except HTTPError as exc:
            raise AemetError(f"Error HTTP de AEMET: {exc.code}") from exc
        except URLError as exc:
            raise AemetError(f"No se pudo conectar con AEMET: {exc.reason}") from exc

        text = decode_payload(payload)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AemetError("AEMET devolvio una respuesta no JSON") from exc


def format_aemet_date(value: date) -> str:
    return f"{value.isoformat()}T00:00:00UTC"


def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def decode_payload(payload: bytes) -> str:
    for encoding in ("utf-8", "latin-1", "iso-8859-15"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def parse_aemet_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.upper() in {"IP", "ACUM"}:
        return default
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return default


def parse_station(row: dict[str, Any]) -> Station:
    return Station(
        indicativo=str(row.get("indicativo", "")).strip(),
        nombre=str(row.get("nombre", "")).strip(),
        provincia=str(row.get("provincia", "")).strip(),
        latitude_deg=parse_aemet_coordinate(row.get("latitud")),
        longitude_deg=parse_aemet_coordinate(row.get("longitud")),
    )


def parse_aemet_coordinate(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    hemisphere = text[-1].upper()
    numeric = text[:-1] if hemisphere in {"N", "S", "E", "W"} else text
    if len(numeric) < 4:
        return None

    try:
        if len(numeric) in {6, 7}:
            degrees = int(numeric[:-4])
            minutes = int(numeric[-4:-2])
            seconds = int(numeric[-2:])
            decimal = degrees + minutes / 60 + seconds / 3600
        else:
            decimal = float(numeric.replace(",", "."))
    except ValueError:
        return None

    if hemisphere in {"S", "W"}:
        decimal *= -1
    return decimal
