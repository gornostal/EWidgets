"""The weather card: current weather, the next 5 hours and the next 5 days.

Network requests run on a worker thread so the blade never stutters, and the
last forecast is cached so the card has something to show as soon as the
blade opens.
"""

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from gi.repository import GLib, Gtk, Pango

from ..carousel import Carousel, CarouselDots
from .conditions import DESCRIPTIONS, describe
from .forecast import fetch_forecast, load_cache, save_cache

# Open-Meteo updates hourly.
REFRESH_INTERVAL_S = 30 * 60
HOURS = 5
DAYS = 5
HOUR_COLUMN_WIDTH = 40
DAY_COLUMN_WIDTH = 46  # room for a high and a low
HOUR_SPACING = 10  # at least; the hours spread out to fill a wider card


def _degrees(value: float) -> str:
    return f"{round(value)}°"


class _Column(Gtk.Box):
    """One hour or day: a caption, an icon and a temperature, or a day's high and low."""

    def __init__(self, low: bool = False) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_size_request(DAY_COLUMN_WIDTH if low else HOUR_COLUMN_WIDTH, -1)
        self.caption = Gtk.Label(label="–", css_classes=["forecast-caption"])
        self.icon = Gtk.Image(icon_name="content-loading-symbolic", pixel_size=16)
        temps = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER)
        self.high = Gtk.Label(label="–", css_classes=["forecast-temp", "numeric"])
        temps.append(self.high)
        self.low: Gtk.Label | None = None
        if low:
            self.low = Gtk.Label(css_classes=["forecast-low", "numeric"])
            temps.append(self.low)
        for child in (self.caption, self.icon, temps):
            self.append(child)

    def set(self, caption: str, icon: str, high: str, low: str | None = None) -> None:
        self.caption.set_label(caption)
        self.icon.set_from_icon_name(icon)
        self.high.set_label(high)
        if self.low:
            self.low.set_label(low or "")


class Weather(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["weather"])
        self._forecast = load_cache()
        self._fetching = False
        self._failed = False
        self._timer = 0

        self._carousel = Carousel(on_page_changed=lambda page: self._dots.set_page(page))
        self._carousel.append(self._build_now_page())
        self._carousel.append(self._build_days_page())
        self._dots = CarouselDots(self._carousel)
        self.append(self._carousel)
        self.append(self._dots)

        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)
        self._render()

    def _build_now_page(self) -> Gtk.Box:
        # The current weather beside the hours, so the card is no taller
        # than the media player's.
        page = Gtk.Box(spacing=8)
        current = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        self._icon = Gtk.Image(icon_name="content-loading-symbolic", pixel_size=64)
        current.append(self._icon)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self._temp = Gtk.Label(label="–", xalign=0, css_classes=["weather-temp", "numeric"])
        # max_width_chars=1 keeps longer text (like "Weather unavailable") from
        # widening the card; _fit_summary sets its actual width.
        self._summary = Gtk.Label(
            label="Loading…",
            xalign=0,
            ellipsize=Pango.EllipsizeMode.END,
            max_width_chars=1,
            css_classes=["weather-summary"],
        )
        self._summary.connect("realize", self._fit_summary)
        text.append(self._temp)
        text.append(self._summary)
        current.append(text)
        page.append(current)

        self._hours = [_Column() for _ in range(HOURS)]
        hours = self._row(self._hours, spacing=HOUR_SPACING)
        hours.set_valign(Gtk.Align.CENTER)
        hours.set_hexpand(True)
        page.append(hours)
        return page

    def _build_days_page(self) -> Gtk.Box:
        self._days = [_Column(low=True) for _ in range(DAYS)]
        row = self._row(self._days)
        row.set_valign(Gtk.Align.CENTER)
        return row

    @staticmethod
    def _fit_summary(label: Gtk.Label) -> None:
        # Exactly as wide as the longest description, so the card keeps its
        # width whatever the weather. Measured once realized, when the label
        # has the blade's font.
        width = max(label.create_pango_layout(text).get_pixel_size()[0] for text in DESCRIPTIONS)
        label.set_size_request(width, -1)

    @staticmethod
    def _row(columns: list[_Column], spacing: int = 0) -> Gtk.Box:
        row = Gtk.Box(homogeneous=True, spacing=spacing)
        for column in columns:
            row.append(column)
        return row

    # Refreshing

    def _on_map(self, _widget: Gtk.Widget) -> None:
        self._render()  # moves the hours along, even from the cache
        fetched_at = (self._forecast or {}).get("fetched_at", 0)
        if time.time() - fetched_at >= REFRESH_INTERVAL_S:
            self._refresh()
        self._timer = GLib.timeout_add_seconds(REFRESH_INTERVAL_S, self._refresh)

    def _on_unmap(self, _widget: Gtk.Widget) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _refresh(self) -> bool:
        if not self._fetching:
            self._fetching = True
            threading.Thread(target=self._fetch_in_background, daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def _fetch_in_background(self) -> None:
        try:
            forecast = fetch_forecast()
        except Exception as e:  # noqa: BLE001 - any failure just keeps the old forecast
            print(f"ewidgets: weather update failed: {e}")
            forecast = None
        else:
            save_cache(forecast)
        GLib.idle_add(self._on_fetched, forecast)

    def _on_fetched(self, forecast: dict[str, Any] | None) -> bool:
        self._fetching = False
        self._failed = forecast is None
        if forecast:
            self._forecast = forecast
        self._render()
        return GLib.SOURCE_REMOVE

    # Drawing

    def _render(self) -> None:
        forecast = self._forecast
        if not forecast:
            self._summary.set_label("Weather unavailable" if self._failed else "Loading…")
            return
        place = forecast.get("place")
        credit = "Weather data by Open-Meteo.com"
        self.set_tooltip_text(f"{place}\n{credit}" if place else credit)

        # Open-Meteo gives times as local times at the forecast's location.
        now = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=forecast["utc_offset_seconds"])

        current = forecast["current"]
        description, icon = describe(current["weather_code"], current["is_day"])
        self._icon.set_from_icon_name(icon)
        self._temp.set_label(_degrees(current["temperature_2m"]))
        self._summary.set_label(description)

        hourly = forecast["hourly"]
        upcoming = [i for i, t in enumerate(hourly["time"]) if datetime.fromisoformat(t) > now]
        for column, i in zip(self._hours, upcoming, strict=False):
            _, icon = describe(hourly["weather_code"][i], hourly["is_day"][i])
            column.set(
                datetime.fromisoformat(hourly["time"][i]).strftime("%H:00"), icon, _degrees(hourly["temperature_2m"][i])
            )

        daily = forecast["daily"]
        days = [i for i, d in enumerate(daily["time"]) if datetime.fromisoformat(d).date() >= now.date()]
        for n, (column, i) in enumerate(zip(self._days, days, strict=False)):
            day = datetime.fromisoformat(daily["time"][i])
            _, icon = describe(daily["weather_code"][i])
            column.set(
                "Today" if n == 0 and day.date() == now.date() else day.strftime("%a"),
                icon,
                _degrees(daily["temperature_2m_max"][i]),
                _degrees(daily["temperature_2m_min"][i]),
            )
