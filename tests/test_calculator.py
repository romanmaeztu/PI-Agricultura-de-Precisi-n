from datetime import date
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest

from irrigation_advisor.calculator import (
    build_crop_profile,
    build_soil_profile,
    estimate_et0_hargreaves,
    recommend_irrigation,
)
from irrigation_advisor.cli import main
from irrigation_advisor.models import IrrigationSystem, WeatherDay


class CalculatorTests(unittest.TestCase):
    def test_daily_irrigation_for_olive_drip(self) -> None:
        crop = build_crop_profile("olivar", "desarrollo")
        soil = build_soil_profile("franco", root_depth_m=0.60)
        system = IrrigationSystem(
            area_m2=10000,
            efficiency=0.90,
            plant_spacing_m2=8,
            emitters_per_plant=2,
            emitter_flow_lph=4,
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
        self.assertAlmostEqual(day.runtime_hours, 4.36, places=2)

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
                    "--soil",
                    "franco",
                    "--area-m2",
                    "1000",
                    "--emitters-per-plant",
                    "2",
                    "--emitter-flow-lph",
                    "4",
                ]
            )

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["crop"]["kc"], 0.75)
        self.assertEqual(result["soil"]["root_depth_m"], 0.7)
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
                    "--soil",
                    "franco",
                    "--area-m2",
                    "1000",
                    "--emitters-per-plant",
                    "2",
                    "--emitter-flow-lph",
                    "4",
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
                    "--soil",
                    "franco",
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


if __name__ == "__main__":
    unittest.main()
