"""Finds where you are and fetches its forecast from Open-Meteo. Everything
here blocks, so it runs on a worker thread. See docs/weather-api-research.md.

The location comes from, in order: a city set in ~/.config/ewidgets/ewidgets.conf
([weather] city=Kyiv), GeoClue, then an IP lookup.
"""

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from gi.repository import Gio, GLib

from ... import APP_ID

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
IP_LOCATION_URL = "http://ip-api.com/json/?fields=status,lat,lon,city"
HTTP_TIMEOUT_S = 10
USER_AGENT = "EWidgets"
CONFIG_PATH = Path(GLib.get_user_config_dir()) / "ewidgets" / "ewidgets.conf"
CACHE_PATH = Path(GLib.get_user_cache_dir()) / "ewidgets" / "weather.json"
# More than the card shows, so a cached forecast still covers the hours and
# days ahead for a while.
FORECAST_HOURS = 24
FORECAST_DAYS = 7

GEOCLUE = "org.freedesktop.GeoClue2"
GEOCLUE_CLIENT = "org.freedesktop.GeoClue2.Client"
GEOCLUE_ACCURACY_STREET = 6  # Wi-Fi positioning; no GPS
GEOCLUE_TIMEOUT_S = 15


type Location = tuple[float, float, str | None]  # latitude, longitude, place name


def _get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        return json.load(response)


def _configured_city() -> str | None:
    keyfile = GLib.KeyFile()
    try:
        keyfile.load_from_file(str(CONFIG_PATH), GLib.KeyFileFlags.NONE)
        return keyfile.get_string("weather", "city").strip() or None
    except GLib.Error:
        return None


def _geocode(city: str) -> Location:
    results = _get_json(GEOCODING_URL, {"name": city, "count": 1}).get("results")
    if not results:
        raise LookupError(f"no such place: {city}")
    return results[0]["latitude"], results[0]["longitude"], results[0]["name"]


def _geoclue_location() -> Location:
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)

    def call(path: str, iface: str, method: str, args: GLib.Variant | None = None) -> Any:
        return bus.call_sync(GEOCLUE, path, iface, method, args, None, Gio.DBusCallFlags.NONE, -1, None).unpack()

    def get(path: str, iface: str, prop: str) -> Any:
        return call(path, "org.freedesktop.DBus.Properties", "Get", GLib.Variant("(ss)", (iface, prop)))[0]

    def set_(prop: str, value: GLib.Variant) -> None:
        call(client, "org.freedesktop.DBus.Properties", "Set", GLib.Variant("(ssv)", (GEOCLUE_CLIENT, prop, value)))

    client = call("/org/freedesktop/GeoClue2/Manager", "org.freedesktop.GeoClue2.Manager", "GetClient")[0]
    set_("DesktopId", GLib.Variant("s", APP_ID))
    set_("RequestedAccuracyLevel", GLib.Variant("u", GEOCLUE_ACCURACY_STREET))
    call(client, GEOCLUE_CLIENT, "Start")
    try:
        deadline = time.monotonic() + GEOCLUE_TIMEOUT_S
        while (location := get(client, GEOCLUE_CLIENT, "Location")) == "/":
            if time.monotonic() > deadline:
                raise TimeoutError("GeoClue found no location")
            time.sleep(0.2)
        iface = "org.freedesktop.GeoClue2.Location"
        return get(location, iface, "Latitude"), get(location, iface, "Longitude"), None
    finally:
        call(client, GEOCLUE_CLIENT, "Stop")


def _ip_location() -> Location:
    info = _get_json(IP_LOCATION_URL)
    if info.get("status") != "success":
        raise LookupError("IP lookup failed")
    return info["lat"], info["lon"], info.get("city")


def _locate() -> Location:
    city = _configured_city()
    if city:
        return _geocode(city)
    try:
        return _geoclue_location()
    except (GLib.Error, TimeoutError):
        return _ip_location()


def fetch_forecast() -> dict[str, Any]:
    latitude, longitude, place = _locate()
    forecast = _get_json(
        FORECAST_URL,
        {
            "latitude": round(latitude, 4),
            "longitude": round(longitude, 4),
            "current": "temperature_2m,weather_code,is_day",
            "hourly": "temperature_2m,weather_code,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "forecast_hours": FORECAST_HOURS,
            "forecast_days": FORECAST_DAYS,
            "timezone": "auto",
        },
    )
    forecast["place"] = place
    forecast["fetched_at"] = time.time()
    return forecast


def load_cache() -> dict[str, Any] | None:
    try:
        return json.loads(CACHE_PATH.read_text())
    except (OSError, ValueError):
        return None


def save_cache(forecast: dict[str, Any]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(forecast))
    except OSError:
        pass
