import unittest
from datetime import date

from outfit_engine import recommend_outfits, seasonal_trends
from weather import Weather


class OutfitEngineTests(unittest.TestCase):
    def setUp(self):
        self.mild_weather = Weather(
            city="東京",
            current_temperature=18,
            feels_like=17,
            humidity=55,
            high=22,
            low=15,
            rain_probability=10,
            wind_speed=12,
            code=1,
            updated_at="2026-10-12T09:00",
        )

    def test_returns_requested_number_of_unique_looks_for_each_audience(self):
        for audience in ("メンズ", "レディース"):
            with self.subTest(audience=audience):
                outfits = recommend_outfits(
                    self.mild_weather, audience, date(2026, 10, 12), count=3
                )
                self.assertEqual(len(outfits), 3)
                self.assertEqual(len({outfit.title for outfit in outfits}), 3)

    def test_default_recommendation_count_is_five_for_both_audiences(self):
        for audience in ("メンズ", "レディース"):
            with self.subTest(audience=audience):
                outfits = recommend_outfits(
                    self.mild_weather, audience, date(2026, 10, 12)
                )
                self.assertEqual(len(outfits), 5)

    def test_recommendations_change_between_consecutive_days(self):
        today = date(2026, 10, 12)
        tomorrow = date(2026, 10, 13)
        for audience in ("メンズ", "レディース"):
            with self.subTest(audience=audience):
                today_titles = {
                    outfit.title
                    for outfit in recommend_outfits(
                        self.mild_weather, audience, today
                    )
                }
                tomorrow_titles = {
                    outfit.title
                    for outfit in recommend_outfits(
                        self.mild_weather, audience, tomorrow
                    )
                }
                self.assertNotEqual(today_titles, tomorrow_titles)

    def test_rain_adds_waterproof_clothing_and_an_umbrella(self):
        rainy = Weather(
            **{
                **self.mild_weather.__dict__,
                "rain_probability": 70,
            }
        )
        outfit = recommend_outfits(
            rainy, "メンズ", date(2026, 10, 12), count=1
        )[0]
        self.assertIn("撥水", outfit.shoes)
        self.assertIn("傘", outfit.accessory)

    def test_hot_and_cold_weather_change_the_recommended_layers(self):
        hot = Weather(**{**self.mild_weather.__dict__, "high": 30, "low": 24})
        cold = Weather(**{**self.mild_weather.__dict__, "high": 9, "low": 2})

        hot_outfit = recommend_outfits(hot, "レディース", date(2026, 7, 1), 1)[0]
        cold_outfit = recommend_outfits(cold, "レディース", date(2026, 12, 1), 1)[0]

        self.assertNotEqual(cold_outfit.outerwear, "アウターなし")
        self.assertNotEqual(hot_outfit.top, cold_outfit.top)

    def test_current_rain_code_triggers_rain_gear_even_if_probability_is_low(self):
        rainy = Weather(**{**self.mild_weather.__dict__, "code": 61})
        outfit = recommend_outfits(
            rainy, "レディース", date(2026, 10, 12), count=1
        )[0]
        self.assertIn("撥水", outfit.shoes)
        self.assertIn("傘", outfit.accessory)

    def test_feels_like_and_humidity_adjust_layers_and_tops(self):
        feels_cold = Weather(
            **{
                **self.mild_weather.__dict__,
                "feels_like": 10,
            }
        )
        hot_and_humid = Weather(
            **{
                **self.mild_weather.__dict__,
                "current_temperature": 27,
                "feels_like": 29,
                "humidity": 80,
                "high": 30,
                "low": 24,
            }
        )

        cold_outfit = recommend_outfits(
            feels_cold, "メンズ", date(2026, 10, 12), count=1
        )[0]
        humid_outfit = recommend_outfits(
            hot_and_humid, "レディース", date(2026, 7, 1), count=1
        )[0]

        self.assertIn("保温インナー", cold_outfit.top)
        self.assertNotEqual(cold_outfit.outerwear, "アウターなし")
        self.assertIn("通気性", humid_outfit.top)

    def test_seasonal_trend_cues_follow_the_month(self):
        self.assertIn("レトロスポーツ", seasonal_trends(date(2026, 10, 12)))
        self.assertIn("スポーツMIX", seasonal_trends(date(2026, 7, 1)))

    def test_color_preference_applies_selected_palette_to_each_look(self):
        default_outfits = recommend_outfits(
            self.mild_weather,
            "メンズ",
            date(2026, 10, 12),
            count=4,
        )
        preferred_outfits = recommend_outfits(
            self.mild_weather,
            "メンズ",
            date(2026, 10, 12),
            count=4,
            preferred_palette="赤×ブルー",
        )
        self.assertTrue(all(outfit.color_style == "赤×ブルー" for outfit in preferred_outfits))
        self.assertTrue(
            all(
                len(outfit.colors) == 3
                and all(color.startswith("#") for _, color in outfit.colors)
                for outfit in preferred_outfits
            )
        )
        default_by_title = {outfit.title: outfit for outfit in default_outfits}
        self.assertTrue(
            any(
                default_by_title[outfit.title].colors != outfit.colors
                for outfit in preferred_outfits
            )
        )

    def test_monochrome_palette_varies_for_each_of_five_looks(self):
        for audience in ("メンズ", "レディース"):
            with self.subTest(audience=audience):
                outfits = recommend_outfits(
                    self.mild_weather,
                    audience,
                    date(2026, 10, 12),
                    preferred_palette="モノトーン",
                )
                self.assertEqual(len(outfits), 5)
                self.assertTrue(all(outfit.color_style == "モノトーン" for outfit in outfits))
                self.assertEqual(len({outfit.colors for outfit in outfits}), 5)

    def test_invalid_palette_is_rejected(self):
        with self.assertRaises(ValueError):
            recommend_outfits(
                self.mild_weather,
                "メンズ",
                date(2026, 10, 12),
                preferred_palette="未登録カラー",
            )

    def test_invalid_audience_and_count_are_rejected(self):
        with self.assertRaises(ValueError):
            recommend_outfits(self.mild_weather, "全員", date(2026, 10, 12))
        with self.assertRaises(ValueError):
            recommend_outfits(self.mild_weather, "メンズ", date(2026, 10, 12), 6)


if __name__ == "__main__":
    unittest.main()
