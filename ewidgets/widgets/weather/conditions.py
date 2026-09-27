"""What each WMO weather code (as Open-Meteo reports it) is called, and its icon."""

# WMO weather code -> (description, day icon, night icon)
_CLEAR = ("weather-clear-symbolic", "weather-clear-night-symbolic")
_FEW_CLOUDS = ("weather-few-clouds-symbolic", "weather-few-clouds-night-symbolic")
_OVERCAST = ("weather-overcast-symbolic",) * 2
_FOG = ("weather-fog-symbolic",) * 2
_DRIZZLE = ("weather-showers-scattered-symbolic",) * 2
_RAIN = ("weather-showers-symbolic",) * 2
_SNOW = ("weather-snow-symbolic",) * 2
_STORM = ("weather-storm-symbolic",) * 2
WMO_CODES = {
    0: ("Clear", *_CLEAR),
    1: ("Mainly clear", *_FEW_CLOUDS),
    2: ("Partly cloudy", *_FEW_CLOUDS),
    3: ("Overcast", *_OVERCAST),
    45: ("Fog", *_FOG),
    48: ("Rime fog", *_FOG),
    51: ("Light drizzle", *_DRIZZLE),
    53: ("Drizzle", *_DRIZZLE),
    55: ("Heavy drizzle", *_DRIZZLE),
    56: ("Icy drizzle", *_DRIZZLE),
    57: ("Icy drizzle", *_DRIZZLE),
    61: ("Light rain", *_RAIN),
    63: ("Rain", *_RAIN),
    65: ("Heavy rain", *_RAIN),
    66: ("Freezing rain", *_RAIN),
    67: ("Freezing rain", *_RAIN),
    71: ("Light snow", *_SNOW),
    73: ("Snow", *_SNOW),
    75: ("Heavy snow", *_SNOW),
    77: ("Snow grains", *_SNOW),
    80: ("Light showers", *_DRIZZLE),
    81: ("Showers", *_RAIN),
    82: ("Heavy showers", *_RAIN),
    85: ("Snow showers", *_SNOW),
    86: ("Snow showers", *_SNOW),
    95: ("Thunderstorm", *_STORM),
    96: ("Hailstorm", *_STORM),
    99: ("Hailstorm", *_STORM),
}
UNKNOWN = ("Unknown", "weather-severe-alert-symbolic", "weather-severe-alert-symbolic")
DESCRIPTIONS = sorted({description for description, _, _ in (*WMO_CODES.values(), UNKNOWN)})


def describe(code: int, is_day: bool = True) -> tuple[str, str]:
    description, day_icon, night_icon = WMO_CODES.get(code, UNKNOWN)
    return description, day_icon if is_day else night_icon
