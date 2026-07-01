from types import SimpleNamespace

from zhijia_guardian.benchmarks.carla_weather import (
    WEATHER_CASES,
    WEATHER_PROFILES,
    _carla_weather,
)


def test_weather_profiles_are_held_out_by_split():
    assert WEATHER_CASES == (
        "normal",
        "perception_confidence_drop",
        "planning_collision_risk",
        "control_delay",
    )
    assert [(profile.name, profile.split) for profile in WEATHER_PROFILES] == [
        ("heavy_rain_day", "train"),
        ("dense_fog_dawn", "val"),
        ("night_storm", "test"),
    ]


def test_weather_profile_maps_to_carla_parameters():
    class WeatherParameters:
        pass

    fake_carla = SimpleNamespace(WeatherParameters=WeatherParameters)
    weather = _carla_weather(fake_carla, WEATHER_PROFILES[-1])

    assert weather.precipitation == 90.0
    assert weather.fog_density == 50.0
    assert weather.sun_altitude_angle == -25.0
    assert not hasattr(weather, "name")
    assert not hasattr(weather, "split")
