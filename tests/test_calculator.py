from datetime import date
from contextlib import redirect_stdout
from pathlib import Path
from io import StringIO
from types import SimpleNamespace
import csv
import json
import tempfile
import unittest

import irrigation_advisor.cli as cli_module
from app import (
    ALL_PROVINCES,
    filter_station_options,
    filter_station_options_by_query,
    province_default_index,
    station_default_index,
    station_option_label,
)
from irrigation_advisor.aemet_client import Station
from irrigation_advisor.calculator import (
    build_crop_profile,
    build_soil_profile,
    estimate_et0_hargreaves,
    recommend_irrigation,
)
from irrigation_advisor.cli import compare_crop_reports, main, reports_to_daily_export_rows
from irrigation_advisor.cli import build_single_crop_report, recommendation_to_dict, recommendation_to_markdown
from irrigation_advisor.ml import training_examples_from_rows
from irrigation_advisor.models import IrrigationSystem, WeatherDay
from irrigation_advisor.weather_cache import AemetCache


class CalculatorTests(unittest.TestCase):
    def test_daily_irrigation_for_olive(self) -> None:
        crop = build_crop_profile("olivar", "desarrollo")
        soil = build_soil_profile("franco", root_depth_m=0.60)
        system = IrrigationSystem(
            area_m2=10000,
            efficiency=0.90,
            plant_spacing_m2=8,
        )
        report = recommend_irrigation(
            weather_days=[WeatherDay(date=date(2024, 5, 1), et0_mm=5.6, rain_mm=0)],
            crop=crop,
            soil=soil,
            system=system,
        )

        day = report.days[0]
        self.assertAlmostEqual(day.etc_mm, 3.92, places=2)
        self.assertAlmostEqual(day.gross_irrigation_mm, 4.36, places=2)
        self.assertAlmostEqual(day.liters_per_plant, 34.84, places=2)

    def test_effective_rain_reduces_irrigation(self) -> None:
        crop = build_crop_profile("olivar", "desarrollo")
        soil = build_soil_profile("franco")
        system = IrrigationSystem(area_m2=1000, efficiency=1.0)
        report = recommend_irrigation(
            weather_days=[WeatherDay(date=date(2024, 5, 1), et0_mm=5, rain_mm=2)],
            crop=crop,
            soil=soil,
            system=system,
        )

        self.assertAlmostEqual(report.days[0].net_irrigation_mm, 1.9, places=2)

    def test_first_irrigation_to_field_capacity(self) -> None:
        crop = build_crop_profile("olivar", "desarrollo")
        soil = build_soil_profile("franco", root_depth_m=0.40)
        system = IrrigationSystem(area_m2=1000, efficiency=0.90)
        report = recommend_irrigation(
            weather_days=[WeatherDay(date=date(2024, 5, 1), et0_mm=0, rain_mm=0)],
            crop=crop,
            soil=soil,
            system=system,
            current_soil_moisture=0.10,
        )

        self.assertAlmostEqual(report.first_irrigation_mm or 0, 66.67, places=2)

    def test_hargreaves_returns_positive_et0(self) -> None:
        et0 = estimate_et0_hargreaves(
            tmin_c=15,
            tmax_c=30,
            latitude_deg=37.4,
            day=date(2024, 5, 1),
        )

        self.assertGreater(et0, 0)
        self.assertLess(et0, 10)

    def test_crop_profiles_have_different_irrigation_variables(self) -> None:
        olivar = build_crop_profile("olivar", "desarrollo")
        citricos = build_crop_profile("citricos", "media")
        almendro = build_crop_profile("almendro", "media")

        self.assertEqual(olivar.plant_spacing_m2, 8.0)
        self.assertEqual(citricos.plant_spacing_m2, 20.0)
        self.assertEqual(almendro.plant_spacing_m2, 30.0)
        self.assertLess(citricos.max_depletion_fraction, almendro.max_depletion_fraction)

    def test_cli_applies_selected_crop_defaults(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "manual",
                    "--et0",
                    "5",
                    "--rain-mm",
                    "0",
                    "--crop",
                    "citricos",
                    "--stage",
                    "media",
                    "--area-m2",
                    "1000",
                ]
            )

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["crop"]["kc"], 0.75)
        self.assertEqual(result["system"]["plant_spacing_m2"], 20.0)

    def test_cli_compare_returns_three_crop_ranking(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "compare",
                    "--et0",
                    "5",
                    "--rain-mm",
                    "0",
                    "--stage",
                    "media",
                    "--area-m2",
                    "1000",
                ]
            )

        result = json.loads(output.getvalue())
        crops = {row["crop"]: row for row in result["crops"]}
        self.assertEqual(exit_code, 0)
        self.assertEqual(set(crops), {"olivar", "citricos", "almendro"})
        self.assertEqual(result["ranking"]["lowest_irrigation_crop"], "olivar")
        self.assertEqual(result["ranking"]["highest_irrigation_crop"], "almendro")
        self.assertAlmostEqual(crops["almendro"]["total_liters"], 5000.0, places=2)

    def test_cli_compare_markdown_outputs_table(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "compare",
                    "--et0",
                    "5",
                    "--rain-mm",
                    "0",
                    "--stage",
                    "media",
                    "--area-m2",
                    "1000",
                    "--output",
                    "markdown",
                ]
            )

        text = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("| Cultivo | Kc |", text)
        self.assertIn("| almendro |", text)
        self.assertIn("Menor demanda: olivar", text)

    def test_cli_export_comparison_writes_csv_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "comparativa_riego.csv"
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "export-comparison",
                        "--et0",
                        "5",
                        "--rain-mm",
                        "0",
                        "--stage",
                        "media",
                        "--area-m2",
                        "1000",
                        "--output-file",
                        str(output_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_file.exists())
            with output_file.open("r", encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["fecha"], date.today().isoformat())
            self.assertIn("cultivo", rows[0])
            self.assertIn("litros_totales", rows[0])
            self.assertEqual({row["cultivo"] for row in rows}, {"olivar", "citricos", "almendro"})

    def test_cli_export_comparison_writes_json_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "comparativa_riego.json"
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "export-comparison",
                        "--et0",
                        "5",
                        "--rain-mm",
                        "0",
                        "--stage",
                        "media",
                        "--area-m2",
                        "1000",
                        "--output-file",
                        str(output_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            rows = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["fecha"], date.today().isoformat())
            self.assertEqual({row["cultivo"] for row in rows}, {"olivar", "citricos", "almendro"})

    def test_cli_summarize_results_writes_csv_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "comparativa.csv"
            summary_file = Path(tmp_dir) / "resumen.csv"
            with redirect_stdout(StringIO()):
                main(
                    [
                        "export-comparison",
                        "--et0",
                        "5",
                        "--rain-mm",
                        "0",
                        "--stage",
                        "media",
                        "--area-m2",
                        "1000",
                        "--output-file",
                        str(input_file),
                    ]
                )

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "summarize-results",
                        "--input-file",
                        str(input_file),
                        "--output-file",
                        str(summary_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            with summary_file.open("r", encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["cultivo"], "olivar")
            self.assertEqual(rows[0]["ranking_demanda"], "1")
            self.assertEqual(rows[-1]["cultivo"], "almendro")
            self.assertGreater(float(rows[-1]["porcentaje_incremento_vs_minimo"]), 0)

    def test_cli_summarize_results_writes_markdown_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "comparativa.csv"
            summary_file = Path(tmp_dir) / "resumen.md"
            with redirect_stdout(StringIO()):
                main(
                    [
                        "export-comparison",
                        "--et0",
                        "5",
                        "--rain-mm",
                        "0",
                        "--stage",
                        "media",
                        "--area-m2",
                        "1000",
                        "--output-file",
                        str(input_file),
                    ]
                )

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "summarize-results",
                        "--input-file",
                        str(input_file),
                        "--output-file",
                        str(summary_file),
                    ]
                )

            text = summary_file.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertIn("| Ranking | Cultivo |", text)
            self.assertIn("Menor demanda: olivar", text)

    def test_daily_export_rows_include_station_and_dates(self) -> None:
        args = SimpleNamespace(
            stage="media",
            area_m2=1000,
            irrigation_efficiency=0.90,
            effective_rainfall_ratio=0.80,
        )
        weather_days = [
            WeatherDay(date=date(2024, 5, 1), et0_mm=5.0, rain_mm=0.0, tmin_c=15.0, tmax_c=30.0, tmean_c=22.5),
            WeatherDay(date=date(2024, 5, 2), et0_mm=6.0, rain_mm=1.0, tmin_c=16.0, tmax_c=31.0, tmean_c=23.5),
        ]

        reports = compare_crop_reports(args=args, weather_days=weather_days)
        rows = reports_to_daily_export_rows(
            reports=reports,
            station_id="5783",
            station_name="SEVILLA AEROPUERTO",
            province="SEVILLA",
        )

        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["estacion"], "5783")
        self.assertEqual(rows[0]["nombre_estacion"], "SEVILLA AEROPUERTO")
        self.assertEqual({row["fecha"] for row in rows}, {"2024-05-01", "2024-05-02"})
        self.assertEqual({row["cultivo"] for row in rows}, {"olivar", "citricos", "almendro"})

    def test_customer_recommendation_contains_service_outputs(self) -> None:
        args = SimpleNamespace(
            crop="olivar",
            stage="media",
            kc=None,
            area_m2=3500,
            irrigation_efficiency=0.90,
            effective_rainfall_ratio=0.80,
            plant_spacing_m2=None,
        )
        weather_days = [
            WeatherDay(date=date(2024, 5, 1), et0_mm=5.0, rain_mm=0.0, tmin_c=15.0, tmax_c=30.0, tmean_c=22.5),
            WeatherDay(date=date(2024, 5, 2), et0_mm=6.0, rain_mm=1.0, tmin_c=16.0, tmax_c=31.0, tmean_c=23.5),
        ]

        report = build_single_crop_report(args=args, weather_days=weather_days)
        recommendation = recommendation_to_dict(
            report=report,
            station_id="5783",
            station_name="SEVILLA AEROPUERTO",
            province="SEVILLA",
            start="2024-05-01",
            end="2024-05-02",
        )
        markdown = recommendation_to_markdown(recommendation)

        self.assertEqual(recommendation["plot"]["crop"], "olivar")
        self.assertEqual(recommendation["plot"]["area_m2"], 3500)
        self.assertGreater(recommendation["recommendation"]["total_liters"], 0)
        self.assertIn("Informe de recomendacion de riego", markdown)
        self.assertIn("Riego medio diario", markdown)

    def test_cli_recommend_uses_weather_file_without_aemet_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            weather_file = Path(tmp_dir) / "weather.csv"
            output_file = Path(tmp_dir) / "recomendacion.md"
            weather_file.write_text(
                "\n".join(
                    [
                        "fecha,estacion,nombre_estacion,provincia,cultivo,fase,et0_mm,lluvia_mm,tmin_c,tmax_c,tmedia_c,kc,marco_m2_por_planta,etc_mm,riego_bruto_mm,litros_totales,litros_por_planta,ranking_demanda",
                        "2024-05-01,5783,SEVILLA AEROPUERTO,SEVILLA,olivar,media,5.0,0.0,15.0,30.0,22.5,0.7,8.0,3.5,3.89,38888.89,31.11,1",
                        "2024-05-02,5783,SEVILLA AEROPUERTO,SEVILLA,olivar,media,6.0,1.0,16.0,31.0,23.5,0.7,8.0,4.2,3.78,37777.78,30.22,1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "recommend",
                        "--station",
                        "5783",
                        "--start",
                        "2024-05-01",
                        "--end",
                        "2024-05-02",
                        "--weather-file",
                        str(weather_file),
                        "--crop",
                        "olivar",
                        "--stage",
                        "media",
                        "--area-m2",
                        "3500",
                        "--output-file",
                        str(output_file),
                    ]
                )

            text = output_file.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertIn("SEVILLA AEROPUERTO", text)
            self.assertIn("Superficie: 3500.00 m2", text)
            self.assertIn("Riego medio diario", text)

    def test_cli_recommend_resolves_station_from_weather_file_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            weather_file = Path(tmp_dir) / "weather.csv"
            output_file = Path(tmp_dir) / "recomendacion.md"
            weather_file.write_text(
                "\n".join(
                    [
                        "fecha,estacion,nombre_estacion,provincia,cultivo,fase,et0_mm,lluvia_mm,tmin_c,tmax_c,tmedia_c,kc,marco_m2_por_planta,etc_mm,riego_bruto_mm,litros_totales,litros_por_planta,ranking_demanda",
                        "2024-05-01,5783,SEVILLA AEROPUERTO,SEVILLA,olivar,media,5.0,0.0,15.0,30.0,22.5,0.7,8.0,3.5,3.89,38888.89,31.11,1",
                        "2024-05-02,5783,SEVILLA AEROPUERTO,SEVILLA,olivar,media,6.0,1.0,16.0,31.0,23.5,0.7,8.0,4.2,3.78,37777.78,30.22,1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "recommend",
                        "--province",
                        "SEVILLA",
                        "--station-name",
                        "AEROPUERTO",
                        "--start",
                        "2024-05-01",
                        "--end",
                        "2024-05-02",
                        "--weather-file",
                        str(weather_file),
                        "--crop",
                        "olivar",
                        "--stage",
                        "media",
                        "--area-m2",
                        "3500",
                        "--output-file",
                        str(output_file),
                    ]
                )

            text = output_file.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertIn("5783 - SEVILLA AEROPUERTO", text)
            self.assertIn("Riego medio diario", text)

    def test_ml_training_examples_include_crop_and_plot_features(self) -> None:
        rows = [
            {
                "fecha": "2024-05-01",
                "estacion": "5783",
                "provincia": "SEVILLA",
                "cultivo": "olivar",
                "fase": "media",
                "superficie_m2": "3500",
                "eficiencia_riego": "0.90",
                "lluvia_efectiva_ratio": "0.80",
                "et0_mm": "5.0",
                "lluvia_mm": "0.0",
                "tmin_c": "15.0",
                "tmax_c": "30.0",
                "tmedia_c": "22.5",
                "kc": "0.7",
                "marco_m2_por_planta": "8.0",
                "riego_bruto_mm": "3.89",
                "litros_totales": "13611.11",
            }
        ]

        examples = training_examples_from_rows(rows)

        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0].features["cultivo"], "olivar")
        self.assertEqual(examples[0].features["superficie_m2"], 3500)
        self.assertAlmostEqual(examples[0].target_mm, 3.89, places=2)

    def test_cli_train_ml_linear_and_predict_from_weather_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            weather_file = Path(tmp_dir) / "training.csv"
            model_dir = Path(tmp_dir) / "model"
            prediction_file = Path(tmp_dir) / "prediction.json"
            with redirect_stdout(StringIO()):
                main(
                    [
                        "export-comparison",
                        "--et0",
                        "5",
                        "--rain-mm",
                        "0",
                        "--stage",
                        "media",
                        "--area-m2",
                        "3500",
                        "--output-file",
                        str(weather_file),
                    ]
                )

            train_output = StringIO()
            with redirect_stdout(train_output):
                exit_code = main(
                    [
                        "train-ml",
                        "--input-file",
                        str(weather_file),
                        "--model-dir",
                        str(model_dir),
                        "--backend",
                        "linear",
                    ]
                )

            training_result = json.loads(train_output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(training_result["model_type"], "linear_ridge")
            self.assertTrue((model_dir / "model.json").exists())

            with redirect_stdout(StringIO()):
                exit_code = main(
                    [
                        "predict-ml",
                        "--model-dir",
                        str(model_dir),
                        "--start",
                        date.today().isoformat(),
                        "--end",
                        date.today().isoformat(),
                        "--weather-file",
                        str(weather_file),
                        "--crop",
                        "olivar",
                        "--stage",
                        "media",
                        "--area-m2",
                        "3500",
                        "--output",
                        "json",
                        "--output-file",
                        str(prediction_file),
                    ]
                )

            result = json.loads(prediction_file.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertIn("ml_prediction", result)
            self.assertEqual(result["ml_prediction"]["model"]["model_type"], "linear_ridge")
            self.assertGreater(result["ml_prediction"]["summary"]["avg_liters_day"], 0)

    def test_ml_prediction_outputs_only_water_dose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            weather_file = Path(tmp_dir) / "training.csv"
            model_dir = Path(tmp_dir) / "model"

            with redirect_stdout(StringIO()):
                main(
                    [
                        "export-comparison",
                        "--et0",
                        "5",
                        "--rain-mm",
                        "0",
                        "--stage",
                        "media",
                        "--area-m2",
                        "3500",
                        "--output-file",
                        str(weather_file),
                    ]
                )
                main(
                    [
                        "train-ml",
                        "--input-file",
                        str(weather_file),
                        "--model-dir",
                        str(model_dir),
                        "--backend",
                        "linear",
                    ]
                )

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "predict-ml",
                        "--model-dir",
                        str(model_dir),
                        "--weather-file",
                        str(weather_file),
                        "--start",
                        date.today().isoformat(),
                        "--end",
                        date.today().isoformat(),
                        "--crop",
                        "olivar",
                        "--stage",
                        "media",
                        "--area-m2",
                        "3500",
                        "--output",
                        "json",
                    ]
                )

            self.assertEqual(exit_code, 0)
            prediction = json.loads(output.getvalue())["ml_prediction"]
            self.assertGreater(prediction["summary"]["avg_gross_mm_day"], 0)
            self.assertNotIn("avg_runtime_hours_day", prediction["summary"])
            self.assertNotIn("predicted_runtime_hours", prediction["daily"][0])

    def test_cli_build_ml_dataset_crosses_stations_crops_and_stages(self) -> None:
        class FakeAemetClient:
            stations = [
                Station("5783", "SEVILLA AEROPUERTO", "SEVILLA", 37.42, -5.90),
                Station("5402", "CORDOBA AEROPUERTO", "CORDOBA", 37.84, -4.84),
            ]

            def get_station_inventory(self) -> list[Station]:
                return self.stations

            def find_station(self, station_id: str) -> Station | None:
                return next((station for station in self.stations if station.indicativo == station_id), None)

            def get_daily_climate(
                self,
                station_id: str,
                start: date,
                end: date,
                latitude_deg: float | None = None,
            ) -> list[WeatherDay]:
                return [
                    WeatherDay(date=date(2024, 5, 1), et0_mm=5.0, rain_mm=0.0, tmin_c=15.0, tmax_c=30.0, tmean_c=22.5),
                    WeatherDay(date=date(2024, 5, 2), et0_mm=6.0, rain_mm=1.0, tmin_c=16.0, tmax_c=31.0, tmean_c=23.5),
                ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_file = Path(tmp_dir) / "dataset_ml.csv"
            model_dir = Path(tmp_dir) / "model"
            original_client = cli_module.AemetClient
            cli_module.AemetClient = FakeAemetClient
            try:
                output = StringIO()
                with redirect_stdout(output):
                    exit_code = main(
                        [
                            "build-ml-dataset",
                            "--station",
                            "5783",
                            "--station",
                            "5402",
                            "--start",
                            "2024-05-01",
                            "--end",
                            "2024-05-02",
                            "--crop",
                            "olivar",
                            "--crop",
                            "almendro",
                            "--stage",
                            "media",
                            "--area-m2",
                            "3500",
                            "--output-file",
                            str(output_file),
                            "--train-model-dir",
                            str(model_dir),
                            "--backend",
                            "linear",
                        ]
                    )
            finally:
                cli_module.AemetClient = original_client

            result = json.loads(output.getvalue())
            with output_file.open("r", encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

            self.assertEqual(exit_code, 0)
            self.assertEqual(result["rows"], 8)
            self.assertEqual(len(rows), 8)
            self.assertEqual({row["estacion"] for row in rows}, {"5783", "5402"})
            self.assertEqual({row["cultivo"] for row in rows}, {"olivar", "almendro"})
            self.assertNotIn("suelo", rows[0])
            self.assertNotIn("profundidad_raices_m", rows[0])
            self.assertTrue((model_dir / "model.json").exists())

    def test_cli_build_ml_dataset_can_use_cached_weather_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            weather_file = Path(tmp_dir) / "cached_weather.csv"
            output_file = Path(tmp_dir) / "dataset_ml.csv"
            weather_file.write_text(
                "\n".join(
                    [
                        "fecha,estacion,nombre_estacion,provincia,et0_mm,lluvia_mm,tmin_c,tmax_c,tmedia_c",
                        "2024-05-01,5783,SEVILLA AEROPUERTO,SEVILLA,5.0,0.0,15.0,30.0,22.5",
                        "2024-05-01,5402,CORDOBA AEROPUERTO,CORDOBA,6.0,1.0,16.0,31.0,23.5",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "build-ml-dataset",
                        "--weather-file",
                        str(weather_file),
                        "--start",
                        "2024-05-01",
                        "--end",
                        "2024-05-01",
                        "--crop",
                        "olivar",
                        "--stage",
                        "media",
                        "--output-file",
                        str(output_file),
                    ]
                )

            result = json.loads(output.getvalue())
            with output_file.open("r", encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

            self.assertEqual(exit_code, 0)
            self.assertEqual(result["rows"], 2)
            self.assertEqual({row["estacion"] for row in rows}, {"5783", "5402"})
            self.assertNotIn("suelo", rows[0])

    def test_station_selector_helpers_filter_and_label_aemet_inventory(self) -> None:
        stations = [
            {"indicativo": "5402", "nombre": "CORDOBA AEROPUERTO", "provincia": "CORDOBA"},
            {"indicativo": "5783", "nombre": "SEVILLA AEROPUERTO", "provincia": "SEVILLA"},
        ]

        sevilla = filter_station_options(stations=stations, province="SEVILLA")
        all_stations = filter_station_options(stations=stations, province=ALL_PROVINCES)
        query_matches = filter_station_options_by_query(stations=all_stations, query="cordoba")
        labels = [station_option_label(station) for station in all_stations]

        self.assertEqual(len(sevilla), 1)
        self.assertEqual(sevilla[0]["indicativo"], "5783")
        self.assertEqual(query_matches[0]["indicativo"], "5402")
        self.assertIn("SEVILLA | SEVILLA AEROPUERTO | 5783", labels)
        self.assertEqual(province_default_index([ALL_PROVINCES, "SEVILLA"], preferred=ALL_PROVINCES), 0)
        self.assertEqual(station_default_index(labels, preferred="SEVILLA AEROPUERTO"), 1)

    def test_aemet_cache_stores_station_and_weather_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = AemetCache(str(Path(tmp_dir) / "aemet.sqlite"))
            station = Station("5783", "SEVILLA AEROPUERTO", "SEVILLA", 37.42, -5.90)
            weather_days = [
                WeatherDay(date=date(2024, 5, 1), et0_mm=4.0, rain_mm=0.0, tmin_c=10.0, tmax_c=22.0, tmean_c=16.0),
                WeatherDay(date=date(2024, 5, 2), et0_mm=4.5, rain_mm=1.0, tmin_c=11.0, tmax_c=23.0, tmean_c=17.0),
            ]

            self.assertEqual(cache.upsert_stations([station]), 1)
            self.assertEqual(cache.upsert_weather(station=station, weather_days=weather_days), 2)

            source = cache.get_weather_source(
                station_id="5783",
                start=date(2024, 5, 1),
                end=date(2024, 5, 2),
            )
            counts = cache.counts()

            self.assertEqual(source.station_name, "SEVILLA AEROPUERTO")
            self.assertEqual(len(source.weather_days), 2)
            self.assertEqual(counts["stations"], 1)
            self.assertEqual(counts["daily_weather"], 2)

    def test_aemet_cache_reports_missing_weather_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = AemetCache(str(Path(tmp_dir) / "aemet.sqlite"))
            station = Station("5783", "SEVILLA AEROPUERTO", "SEVILLA", 37.42, -5.90)
            cache.upsert_stations([station])
            cache.upsert_weather(
                station=station,
                weather_days=[
                    WeatherDay(date=date(2024, 5, 1), et0_mm=4.0, rain_mm=0.0),
                    WeatherDay(date=date(2024, 5, 3), et0_mm=5.0, rain_mm=0.0),
                ],
            )

            with self.assertRaisesRegex(ValueError, "Faltan 1 dias"):
                cache.get_weather_source(
                    station_id="5783",
                    start=date(2024, 5, 1),
                    end=date(2024, 5, 3),
                )

    def test_cli_recommend_uses_aemet_cache_without_api_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = AemetCache(str(Path(tmp_dir) / "aemet.sqlite"))
            station = Station("5783", "SEVILLA AEROPUERTO", "SEVILLA", 37.42, -5.90)
            cache.upsert_stations([station])
            cache.upsert_weather(
                station=station,
                weather_days=[
                    WeatherDay(date=date(2024, 5, 1), et0_mm=5.0, rain_mm=0.0, tmin_c=12.0, tmax_c=25.0, tmean_c=18.5)
                ],
            )

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "recommend",
                        "--cache-db",
                        str(cache.db_file),
                        "--station",
                        "5783",
                        "--start",
                        "2024-05-01",
                        "--end",
                        "2024-05-01",
                        "--crop",
                        "olivar",
                        "--stage",
                        "media",
                        "--area-m2",
                        "3500",
                        "--output",
                        "json",
                    ]
                )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["location"]["station"], "5783")
            self.assertEqual(result["period"]["days"], 1)
            self.assertGreater(result["recommendation"]["total_liters"], 0)

    def test_cli_build_ml_dataset_uses_aemet_cache_without_api_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = AemetCache(str(Path(tmp_dir) / "aemet.sqlite"))
            output_file = Path(tmp_dir) / "dataset.csv"
            station = Station("5783", "SEVILLA AEROPUERTO", "SEVILLA", 37.42, -5.90)
            cache.upsert_stations([station])
            cache.upsert_weather(
                station=station,
                weather_days=[
                    WeatherDay(date=date(2024, 5, 1), et0_mm=5.0, rain_mm=0.0, tmin_c=12.0, tmax_c=25.0, tmean_c=18.5)
                ],
            )

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    [
                        "build-ml-dataset",
                        "--cache-db",
                        str(cache.db_file),
                        "--station",
                        "5783",
                        "--start",
                        "2024-05-01",
                        "--end",
                        "2024-05-01",
                        "--crop",
                        "olivar",
                        "--stage",
                        "media",
                        "--output-file",
                        str(output_file),
                    ]
                )

            result = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["rows"], 1)
            self.assertEqual(result["stations_ok"], 1)
            self.assertTrue(output_file.exists())


if __name__ == "__main__":
    unittest.main()

